from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    ChannelAccount,
    ChannelStatus,
    ChannelType,
    ContentPiece,
    ContentVariant,
    Experiment,
    ExperimentMode,
    ExperimentStatus,
    Publication,
    User,
)
from app.schemas import ExperimentCreate, ScheduleRequest, WinnerRequest
from app.security import as_utc, utc_now
from app.services.analytics_service import latest_snapshot_map
from app.services.audit import write_audit
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.metrics import KNOWN_METRICS
from app.services.publish_service import schedule_publication

ACTIVE_EXPERIMENT = (ExperimentStatus.draft, ExperimentStatus.running)


def _telegram_channel(db: Session, brand_id: UUID) -> ChannelAccount:
    channel = db.scalar(
        select(ChannelAccount)
        .where(
            ChannelAccount.brand_id == brand_id,
            ChannelAccount.type == ChannelType.telegram,
            ChannelAccount.status == ChannelStatus.connected,
            ChannelAccount.revoked_at.is_(None),
        )
        .order_by(ChannelAccount.created_at.desc())
    )
    if channel is None:
        raise AppError(409, "no_channel", "Нет подключённого Telegram-канала")
    return channel


def variant_metric(snapshot, primary_metric: str) -> int | None:
    if snapshot is None:
        return None
    metrics = (snapshot.normalized or {}).get("metrics") or {}
    value = metrics.get(primary_metric)
    if isinstance(value, int):
        return value
    return None


def require_experiment(
    db: Session, user: User, experiment_id: UUID, mutate: bool = False
) -> Experiment:
    row = db.get(Experiment, experiment_id)
    if row is None:
        raise AppError(404, "not_found", "Эксперимент не найден")
    piece = db.get(ContentPiece, row.piece_id)
    if piece is None:
        raise AppError(404, "not_found", "Эксперимент не найден")
    roles = MUTATE_BRAND_ROLES if mutate else None
    try:
        require_brand(db, user, piece.brand_id, roles)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Эксперимент не найден") from exc
        raise
    return row


def list_experiments(db: Session, user: User, brand_id: UUID) -> list[Experiment]:
    brand, _membership = require_brand(db, user, brand_id)
    return list(
        db.scalars(
            select(Experiment)
            .join(ContentPiece, Experiment.piece_id == ContentPiece.id)
            .where(ContentPiece.brand_id == brand.id)
            .order_by(Experiment.created_at.desc())
        ).all()
    )


def experiment_publications(db: Session, experiment_id: UUID) -> list[Publication]:
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.experiment_id == experiment_id)
            .order_by(Publication.scheduled_at.asc())
        ).all()
    )


def create_experiment(
    db: Session,
    user: User,
    brand_id: UUID,
    payload: ExperimentCreate,
    ip: str | None = None,
) -> Experiment:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    if payload.channel_type is not ChannelType.telegram or payload.mode is not ExperimentMode.sequential:
        raise AppError(409, "unsupported_mode", "MVP поддерживает только sequential Telegram")
    if payload.primary_metric not in KNOWN_METRICS:
        raise AppError(422, "validation_error", "Неизвестная первичная метрика")
    window_start = as_utc(payload.window_start)
    window_end = as_utc(payload.window_end)
    schedule_a = as_utc(payload.schedule_a)
    schedule_b = as_utc(payload.schedule_b)
    if window_end <= window_start:
        raise AppError(422, "validation_error", "window_end должен быть позже window_start")
    if schedule_b <= schedule_a:
        raise AppError(422, "validation_error", "schedule_b должен быть позже schedule_a")
    if payload.variant_a_id == payload.variant_b_id:
        raise AppError(422, "validation_error", "Варианты A и B должны отличаться")
    piece = db.get(ContentPiece, payload.piece_id)
    if piece is None or piece.brand_id != brand.id:
        raise AppError(404, "not_found", "Материал не найден")
    variant_a = db.get(ContentVariant, payload.variant_a_id)
    variant_b = db.get(ContentVariant, payload.variant_b_id)
    if (
        variant_a is None
        or variant_b is None
        or variant_a.piece_id != piece.id
        or variant_b.piece_id != piece.id
    ):
        raise AppError(404, "not_found", "Вариант не найден")
    active = db.scalar(
        select(Experiment).where(
            Experiment.piece_id == piece.id,
            Experiment.status.in_(ACTIVE_EXPERIMENT),
        )
    )
    if active is not None:
        raise AppError(409, "experiment_active", "У материала уже есть активный эксперимент")
    row = Experiment(
        piece_id=piece.id,
        variant_a_id=variant_a.id,
        variant_b_id=variant_b.id,
        channel_type=payload.channel_type,
        mode=payload.mode,
        primary_metric=payload.primary_metric,
        window_start=window_start,
        window_end=window_end,
        schedule_a=schedule_a,
        schedule_b=schedule_b,
        status=ExperimentStatus.draft,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="create_experiment",
        entity_type="experiment",
        entity_id=row.id,
        ip=ip,
        data={"piece_id": str(piece.id), "mode": row.mode.value},
    )
    return row


def start_experiment(
    db: Session, user: User, experiment_id: UUID, ip: str | None = None
) -> Experiment:
    row = require_experiment(db, user, experiment_id, mutate=True)
    if row.status is not ExperimentStatus.draft:
        raise AppError(409, "invalid_status", "Запустить можно только draft")
    piece = db.get(ContentPiece, row.piece_id)
    if piece is None:
        raise AppError(404, "not_found", "Материал не найден")
    channel = _telegram_channel(db, piece.brand_id)
    pub_a, _ = schedule_publication(
        db,
        user,
        piece.brand_id,
        ScheduleRequest(
            variant_id=row.variant_a_id,
            channel_account_id=channel.id,
            scheduled_at=row.schedule_a,
            idempotency_key=f"exp:{row.id}:A",
        ),
        ip=ip,
    )
    pub_b, _ = schedule_publication(
        db,
        user,
        piece.brand_id,
        ScheduleRequest(
            variant_id=row.variant_b_id,
            channel_account_id=channel.id,
            scheduled_at=row.schedule_b,
            idempotency_key=f"exp:{row.id}:B",
        ),
        ip=ip,
    )
    pub_a.experiment_id = row.id
    pub_b.experiment_id = row.id
    row.status = ExperimentStatus.running
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="start_experiment",
        entity_type="experiment",
        entity_id=row.id,
        ip=ip,
        data={"publication_a": str(pub_a.id), "publication_b": str(pub_b.id)},
    )
    return row


def stop_experiment(
    db: Session, user: User, experiment_id: UUID, ip: str | None = None
) -> Experiment:
    row = require_experiment(db, user, experiment_id, mutate=True)
    if row.status is not ExperimentStatus.running:
        raise AppError(409, "invalid_status", "Остановить можно только running")
    now = utc_now()
    if now < as_utc(row.window_end):
        row.window_end = now
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="stop_experiment",
        entity_type="experiment",
        entity_id=row.id,
        ip=ip,
        data={},
    )
    return row


def window_closed(row: Experiment, now=None) -> bool:
    moment = as_utc(now or utc_now())
    return moment >= as_utc(row.window_end)


def declare_winner(
    db: Session,
    user: User,
    experiment_id: UUID,
    payload: WinnerRequest,
    ip: str | None = None,
) -> Experiment:
    row = require_experiment(db, user, experiment_id, mutate=True)
    if row.status not in {ExperimentStatus.running, ExperimentStatus.tie}:
        raise AppError(409, "invalid_status", "Победителя можно объявить только для running или tie")
    if not window_closed(row):
        raise AppError(409, "window_open", "Окно эксперимента ещё не закрыто")
    if payload.variant_id not in {row.variant_a_id, row.variant_b_id}:
        raise AppError(422, "validation_error", "Победитель должен быть вариантом A или B")
    row.winner_variant_id = payload.variant_id
    row.status = ExperimentStatus.completed
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="declare_winner",
        entity_type="experiment",
        entity_id=row.id,
        ip=ip,
        data={"winner_variant_id": str(payload.variant_id)},
    )
    return row


def experiment_metrics(db: Session, row: Experiment) -> dict:
    pubs = experiment_publications(db, row.id)
    latest = latest_snapshot_map(db, [item.id for item in pubs])
    by_variant: dict[UUID, Publication] = {}
    for pub in pubs:
        by_variant.setdefault(pub.variant_id, pub)

    def side(variant_id: UUID) -> dict:
        pub = by_variant.get(variant_id)
        if pub is None:
            return {
                "publication_id": None,
                "availability": "unavailable",
                "value": None,
            }
        snapshot = latest.get(pub.id)
        value = variant_metric(snapshot, row.primary_metric)
        availability = "unavailable" if value is None else "available"
        if snapshot is not None:
            availability = (snapshot.normalized or {}).get("availability") or availability
            if value is None:
                availability = "unavailable"
        return {
            "publication_id": str(pub.id),
            "availability": availability if value is not None else "unavailable",
            "value": value,
        }

    variant_a = side(row.variant_a_id)
    variant_b = side(row.variant_b_id)
    leader = "unavailable"
    if variant_a["value"] is not None and variant_b["value"] is not None:
        if variant_a["value"] > variant_b["value"]:
            leader = "a"
        elif variant_b["value"] > variant_a["value"]:
            leader = "b"
        else:
            leader = "tie"
    return {
        "primary_metric": row.primary_metric,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "leader": leader,
        "window_closed": window_closed(row),
        "publication_ids": [str(item.id) for item in pubs],
    }
