from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.errors import AppError
from app.models import (
    ChannelAccount,
    ChannelStatus,
    ChannelType,
    ContentType,
    ContentVariant,
    Publication,
    PublicationStatus,
    User,
)
from app.schemas import MarkManualRequest, ScheduleRequest
from app.security import as_utc, utc_now
from app.services.audit import write_audit
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.recipient_service import has_active_recipients
from app.services.stopwords import assert_publish_allowed


def assert_gmail_recipients(
    db: Session,
    brand_id: UUID,
    variant: ContentVariant,
    channel: ChannelAccount | None,
) -> None:
    is_gmail = channel is not None and channel.type == ChannelType.gmail
    is_email = variant.piece.type == ContentType.email
    if not (is_gmail or is_email):
        return
    if not has_active_recipients(db, brand_id):
        raise AppError(409, "no_recipients", "Нет активных получателей")


def list_publications(
    db: Session,
    user: User,
    brand_id: UUID,
    status: PublicationStatus | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> list[Publication]:
    brand, _membership = require_brand(db, user, brand_id)
    stmt = (
        select(Publication)
        .options(joinedload(Publication.channel), joinedload(Publication.variant))
        .join(ChannelAccount, Publication.channel_account_id == ChannelAccount.id)
        .where(ChannelAccount.brand_id == brand.id)
        .order_by(Publication.scheduled_at.desc())
    )
    if status is not None:
        stmt = stmt.where(Publication.status == status)
    if from_at is not None:
        stmt = stmt.where(Publication.scheduled_at >= as_utc(from_at))
    if to_at is not None:
        stmt = stmt.where(Publication.scheduled_at <= as_utc(to_at))
    return list(db.scalars(stmt).all())


def require_publication(
    db: Session, user: User, publication_id: UUID, mutate: bool = False
) -> Publication:
    row = db.get(Publication, publication_id)
    if row is None:
        raise AppError(404, "not_found", "Публикация не найдена")
    channel = db.get(ChannelAccount, row.channel_account_id)
    if channel is None:
        raise AppError(404, "not_found", "Публикация не найдена")
    roles = MUTATE_BRAND_ROLES if mutate else None
    try:
        require_brand(db, user, channel.brand_id, roles)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Публикация не найдена") from exc
        raise
    return row


def schedule_publication(
    db: Session,
    user: User,
    brand_id: UUID,
    payload: ScheduleRequest,
    ip: str | None = None,
) -> tuple[Publication, bool]:
    brand, membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    key = (payload.idempotency_key or "").strip() or None
    if key:
        existing = db.scalar(select(Publication).where(Publication.idempotency_key == key))
        if existing is not None:
            channel = db.get(ChannelAccount, existing.channel_account_id)
            if channel is None or channel.brand_id != brand.id:
                raise AppError(409, "idempotency_conflict", "Ключ идемпотентности уже использован")
            return existing, False
    variant = db.get(ContentVariant, payload.variant_id)
    if variant is None or variant.piece.brand_id != brand.id:
        raise AppError(404, "not_found", "Вариант не найден")
    hits = assert_publish_allowed(brand, variant, membership, payload.stopword_override)
    if payload.channel_account_id is None:
        raise AppError(400, "validation_error", "Не указан channel_account_id", {"field": "channel_account_id"})
    channel = db.get(ChannelAccount, payload.channel_account_id)
    if channel is None or channel.brand_id != brand.id:
        raise AppError(404, "not_found", "Канал не найден")
    if channel.status is ChannelStatus.revoked or channel.revoked_at is not None:
        raise AppError(409, "channel_revoked", "Канал отозван")
    assert_gmail_recipients(db, brand.id, variant, channel)
    if hits:
        write_audit(
            db,
            actor_id=user.id,
            action="stopword_override",
            entity_type="content_variant",
            entity_id=variant.id,
            ip=ip,
            data={"hits": hits, "piece_id": str(variant.piece_id)},
        )
        variant.piece.stopword_override = True
    scheduled_at = as_utc(payload.scheduled_at) if payload.scheduled_at else utc_now()
    row = Publication(
        variant_id=variant.id,
        channel_account_id=channel.id,
        scheduled_at=scheduled_at,
        status=PublicationStatus.scheduled,
        idempotency_key=key,
        meta={},
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        if key:
            existing = db.scalar(select(Publication).where(Publication.idempotency_key == key))
            if existing is not None:
                return existing, False
        raise AppError(409, "conflict", "Не удалось создать публикацию") from exc
    write_audit(
        db,
        actor_id=user.id,
        action="schedule_publication",
        entity_type="publication",
        entity_id=row.id,
        ip=ip,
        data={"channel_type": channel.type.value, "variant_id": str(variant.id)},
    )
    return row, True


def cancel_publication(
    db: Session, user: User, publication_id: UUID, ip: str | None = None
) -> Publication:
    row = require_publication(db, user, publication_id, mutate=True)
    if row.status is not PublicationStatus.scheduled:
        raise AppError(409, "invalid_status", "Отменить можно только scheduled")
    row.status = PublicationStatus.cancelled
    row.updated_at = utc_now()
    write_audit(
        db,
        actor_id=user.id,
        action="cancel_publication",
        entity_type="publication",
        entity_id=row.id,
        ip=ip,
        data={},
    )
    db.flush()
    return row


def retry_publication(
    db: Session, user: User, publication_id: UUID, ip: str | None = None
) -> Publication:
    row = require_publication(db, user, publication_id, mutate=True)
    if row.status not in {PublicationStatus.failed, PublicationStatus.dead}:
        raise AppError(409, "invalid_status", "Повторить можно только failed или dead")
    if row.external_id:
        return row
    row.status = PublicationStatus.scheduled
    row.scheduled_at = utc_now()
    row.attempt_count = 0
    row.error_code = None
    row.error_message = None
    row.updated_at = utc_now()
    write_audit(
        db,
        actor_id=user.id,
        action="retry_publication",
        entity_type="publication",
        entity_id=row.id,
        ip=ip,
        data={},
    )
    db.flush()
    return row


def mark_manual(
    db: Session,
    user: User,
    publication_id: UUID,
    payload: MarkManualRequest,
    ip: str | None = None,
) -> Publication:
    row = require_publication(db, user, publication_id, mutate=True)
    if row.status in {
        PublicationStatus.published,
        PublicationStatus.published_manual,
        PublicationStatus.cancelled,
        PublicationStatus.publishing,
    }:
        raise AppError(409, "invalid_status", "Нельзя отметить manual в текущем статусе")
    row.status = PublicationStatus.published_manual
    row.external_url = (payload.external_url or "").strip() or None
    row.published_at = utc_now()
    row.updated_at = utc_now()
    row.error_code = None
    row.error_message = None
    write_audit(
        db,
        actor_id=user.id,
        action="mark_manual",
        entity_type="publication",
        entity_id=row.id,
        ip=ip,
        data={"external_url": bool(row.external_url)},
    )
    db.flush()
    return row


def cancel_scheduled_for_channel(db: Session, channel_id: UUID) -> int:
    rows = list(
        db.scalars(
            select(Publication).where(
                Publication.channel_account_id == channel_id,
                Publication.status == PublicationStatus.scheduled,
            )
        ).all()
    )
    now = utc_now()
    for row in rows:
        row.status = PublicationStatus.cancelled
        row.updated_at = now
    db.flush()
    return len(rows)
