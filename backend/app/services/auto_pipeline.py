import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session_factory
from app.errors import AppError
from app.models import (
    BrandProfile,
    ChannelAccount,
    ChannelStatus,
    ContentPiece,
    ContentPlan,
    ContentVariant,
    JobType,
    PieceStatus,
    PlanItem,
    PlanStatus,
    Publication,
    PublicationStatus,
    User,
)
from app.security import as_utc, utc_now
from app.services.ai_schemas import PRIMARY_TEXT_FIELD
from app.services.job_service import create_job, dispatch_job
from app.services.publish_service import schedule_publication_internal
from app.services.stopwords import find_stopwords, payload_text

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_TICK = 20
FALLBACK_TZ = "Europe/Moscow"


def resolve_brand_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or FALLBACK_TZ)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return ZoneInfo(FALLBACK_TZ)


def compute_slot_at(item_date: date, hour: int, tz_name: str) -> datetime:
    tz = resolve_brand_tz(tz_name)
    local = datetime(
        item_date.year,
        item_date.month,
        item_date.day,
        int(hour) % 24,
        0,
        0,
        tzinfo=tz,
    )
    return as_utc(local)


def is_slot_eligible(now: datetime, slot_at: datetime, lead_hours: int) -> bool:
    moment = as_utc(now)
    when = as_utc(slot_at)
    if moment > when:
        return False
    return (when - moment) <= timedelta(hours=max(int(lead_hours), 0))


def run_prepare_plan_slots_job() -> dict[str, int]:
    db = get_session_factory()()
    try:
        stats = run_prepare_plan_slots(db)
        db.commit()
        return stats
    except Exception:
        db.rollback()
        logger.exception("prepare_plan_slots_failed")
        raise
    finally:
        db.close()


def run_prepare_plan_slots(db: Session, now: datetime | None = None) -> dict[str, int]:
    moment = as_utc(now or utc_now())
    stats = {
        "brands": 0,
        "considered": 0,
        "enqueued": 0,
        "scheduled": 0,
        "skipped": 0,
    }
    brands = list(
        db.scalars(
            select(BrandProfile).where(
                BrandProfile.auto_pipeline_enabled.is_(True),
                BrandProfile.deleted_at.is_(None),
            )
        ).all()
    )
    stats["brands"] = len(brands)
    budget = MAX_ITEMS_PER_TICK

    for brand in brands:
        if budget <= 0:
            break
        plans = list(
            db.scalars(
                select(ContentPlan)
                .options(selectinload(ContentPlan.items))
                .where(
                    ContentPlan.brand_id == brand.id,
                    ContentPlan.status == PlanStatus.approved,
                )
            ).all()
        )
        for plan in plans:
            if budget <= 0:
                break
            if not plan.items:
                continue
            creator = db.get(User, plan.created_by)
            if creator is None:
                logger.warning("prepare_plan_slots_missing_creator plan_id=%s", plan.id)
                continue
            items = sorted(plan.items, key=lambda row: (row.date, row.sort_order, str(row.id)))
            for item in items:
                if budget <= 0:
                    break
                slot_at = compute_slot_at(
                    item.date,
                    brand.default_slot_hour,
                    brand.timezone,
                )
                if not is_slot_eligible(moment, slot_at, brand.auto_pipeline_lead_hours):
                    continue
                stats["considered"] += 1
                budget -= 1
                outcome = _prepare_item(db, brand, item, creator, slot_at)
                stats[outcome] += 1

    logger.info(
        "prepare_plan_slots brands=%s considered=%s enqueued=%s scheduled=%s skipped=%s",
        stats["brands"],
        stats["considered"],
        stats["enqueued"],
        stats["scheduled"],
        stats["skipped"],
    )
    return stats


def _prepare_item(
    db: Session,
    brand: BrandProfile,
    item: PlanItem,
    creator: User,
    slot_at: datetime,
) -> str:
    piece = _ensure_piece(db, brand, item)
    if _has_piece_channel_publication(db, piece.id, item.channel_type):
        return "skipped"

    if _variant_needs_generation(piece):
        job = create_job(
            db,
            user=creator,
            job_type=JobType.generate_content,
            payload={
                "brand_id": str(brand.id),
                "piece_id": str(piece.id),
                "variant_label": "A",
                "channel_type": item.channel_type.value,
                "auto_schedule": True,
                "scheduled_at": slot_at.isoformat(),
            },
            idempotency_key=f"auto-gen:{item.id}",
        )
        if job.status.value == "queued":
            dispatch_job(db, job)
        return "enqueued"

    variant = _variant_a(piece)
    if variant is None:
        return "skipped"
    channel = _connected_channel(db, brand.id, item.channel_type)
    if channel is None:
        logger.warning(
            "prepare_plan_slots_no_channel brand_id=%s channel_type=%s item_id=%s",
            brand.id,
            item.channel_type.value,
            item.id,
        )
        return "skipped"
    hits = find_stopwords(payload_text(variant.payload), list(brand.stopwords or []))
    if hits:
        logger.warning(
            "prepare_plan_slots_stopwords item_id=%s hits=%s",
            item.id,
            hits,
        )
        return "skipped"
    try:
        _pub, created = schedule_publication_internal(
            db,
            brand=brand,
            variant=variant,
            channel=channel,
            scheduled_at=slot_at,
            actor_id=creator.id,
            idempotency_key=f"auto-pub:{item.id}",
        )
    except AppError as exc:
        logger.warning(
            "prepare_plan_slots_schedule_failed item_id=%s code=%s",
            item.id,
            exc.code,
        )
        return "skipped"
    return "scheduled" if created else "skipped"


def _ensure_piece(db: Session, brand: BrandProfile, item: PlanItem) -> ContentPiece:
    if item.content_piece_id is not None:
        piece = db.scalar(
            select(ContentPiece)
            .options(selectinload(ContentPiece.variants))
            .where(ContentPiece.id == item.content_piece_id)
        )
        if piece is not None:
            return piece
    piece = ContentPiece(
        brand_id=brand.id,
        type=item.content_type,
        locale=brand.default_locale,
        status=PieceStatus.draft,
        plan_item_id=item.id,
    )
    db.add(piece)
    db.flush()
    item.content_piece_id = piece.id
    db.flush()
    return db.scalar(
        select(ContentPiece)
        .options(selectinload(ContentPiece.variants))
        .where(ContentPiece.id == piece.id)
    ) or piece


def _variant_a(piece: ContentPiece) -> ContentVariant | None:
    return next((row for row in (piece.variants or []) if row.label == "A"), None)


def _variant_needs_generation(piece: ContentPiece) -> bool:
    variants = list(piece.variants or [])
    if not variants:
        return True
    variant = _variant_a(piece)
    if variant is None:
        return True
    field = PRIMARY_TEXT_FIELD[piece.type]
    text = (variant.payload or {}).get(field)
    return not (isinstance(text, str) and text.strip())


def _has_piece_channel_publication(db: Session, piece_id, channel_type) -> bool:
    row = db.scalar(
        select(Publication.id)
        .join(ContentVariant, Publication.variant_id == ContentVariant.id)
        .join(ChannelAccount, Publication.channel_account_id == ChannelAccount.id)
        .where(
            ContentVariant.piece_id == piece_id,
            ChannelAccount.type == channel_type,
            Publication.status != PublicationStatus.cancelled,
        )
        .limit(1)
    )
    return row is not None


def _connected_channel(
    db: Session, brand_id, channel_type
) -> ChannelAccount | None:
    return db.scalar(
        select(ChannelAccount).where(
            ChannelAccount.brand_id == brand_id,
            ChannelAccount.type == channel_type,
            ChannelAccount.status == ChannelStatus.connected,
            ChannelAccount.revoked_at.is_(None),
        )
    )
