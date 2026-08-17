import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.logutil import log_event, publication_id_ctx
from app.models import ChannelAccount, ChannelStatus, ContentVariant, Publication, PublicationStatus
from app.security import as_utc, utc_now
from app.services.adapters import get_adapter
from app.services.adapters.base import AdapterError
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
MAX_ATTEMPTS = 3
WATCHDOG_AFTER = timedelta(minutes=10)


def run_publish_due_job() -> dict[str, int]:
    db = get_session_factory()()
    try:
        stats = run_publish_due(db)
        db.commit()
        return stats
    except Exception:
        db.rollback()
        logger.exception("publish_due_failed")
        raise
    finally:
        db.close()


def run_publish_due(db: Session, now: datetime | None = None) -> dict[str, int]:
    moment = as_utc(now or utc_now())
    watchdog = recover_stuck_publishing(db, moment)
    due_ids = list(
        db.scalars(
            select(Publication.id).where(
                Publication.status == PublicationStatus.scheduled,
                Publication.scheduled_at <= moment,
            )
        ).all()
    )
    claimed = 0
    processed = 0
    for publication_id in due_ids:
        if not claim_scheduled(db, publication_id, moment):
            continue
        claimed += 1
        db.expire_all()
        process_publication(db, publication_id, moment)
        processed += 1
        db.flush()
    return {"watchdog": watchdog, "due": len(due_ids), "claimed": claimed, "processed": processed}


def claim_scheduled(db: Session, publication_id: UUID, now: datetime) -> bool:
    result = db.execute(
        update(Publication)
        .where(
            Publication.id == publication_id,
            Publication.status == PublicationStatus.scheduled,
            Publication.scheduled_at <= now,
        )
        .values(status=PublicationStatus.publishing, updated_at=now),
        execution_options={"synchronize_session": False},
    )
    return result.rowcount == 1


def recover_stuck_publishing(db: Session, now: datetime) -> int:
    cutoff = now - WATCHDOG_AFTER
    stuck_ids = list(
        db.scalars(
            select(Publication.id).where(
                Publication.status == PublicationStatus.publishing,
                Publication.external_id.is_(None),
                Publication.updated_at <= cutoff,
            )
        ).all()
    )
    for publication_id in stuck_ids:
        pub = db.get(Publication, publication_id)
        if pub is None or pub.status is not PublicationStatus.publishing or pub.external_id:
            continue
        _fail_publication(
            pub,
            AdapterError("watchdog_timeout", "Публикация зависла в publishing", retryable=True),
            now,
            increment=False,
        )
    db.flush()
    return len(stuck_ids)


def process_publication(db: Session, publication_id: UUID, now: datetime | None = None) -> None:
    moment = as_utc(now or utc_now())
    pub = db.get(Publication, publication_id)
    if pub is None or pub.status is not PublicationStatus.publishing:
        return
    token = publication_id_ctx.set(str(publication_id))
    try:
        _process_publication(db, pub, moment)
    finally:
        publication_id_ctx.reset(token)


def _process_publication(db: Session, pub: Publication, moment: datetime) -> None:
    if pub.external_id:
        _mark_published(pub, pub.external_id, pub.external_url, moment, None)
        return
    channel = db.get(ChannelAccount, pub.channel_account_id)
    variant = db.get(ContentVariant, pub.variant_id)
    log_event(logger, "publication_process", publication_id=pub.id)
    if channel is None or variant is None:
        _fail_publication(
            pub,
            AdapterError("not_found", "Канал или вариант не найден", retryable=False),
            moment,
        )
        return
    adapter = get_adapter(channel.type)
    if not adapter.supports_autopost:
        pub.status = PublicationStatus.scheduled
        pub.updated_at = moment
        return
    if channel.status is ChannelStatus.revoked or channel.revoked_at is not None:
        _fail_publication(
            pub,
            AdapterError("channel_revoked", "Канал отозван", retryable=False),
            moment,
        )
        return
    pub.attempt_count = int(pub.attempt_count or 0) + 1
    pub.updated_at = moment
    db.flush()
    try:
        result = adapter.publish(db, channel, variant, pub)
    except AdapterError as exc:
        _fail_publication(pub, exc, moment)
        return
    _mark_published(pub, result.external_id, result.external_url, moment, result.meta)
    variant.is_immutable = True
    write_audit(
        db,
        actor_id=None,
        action="publish",
        entity_type="publication",
        entity_id=pub.id,
        data={"channel_type": channel.type.value, "external_id": True},
    )


def _mark_published(
    pub: Publication,
    external_id: str,
    external_url: str | None,
    now: datetime,
    extra_meta: dict | None = None,
) -> None:
    pub.status = PublicationStatus.published
    pub.external_id = external_id
    pub.external_url = external_url
    pub.published_at = now
    pub.updated_at = now
    pub.error_code = None
    pub.error_message = None
    if extra_meta:
        pub.meta = {**(pub.meta or {}), **extra_meta}


def _fail_publication(
    pub: Publication,
    error: AdapterError,
    now: datetime,
    increment: bool = True,
) -> None:
    if increment:
        if pub.attempt_count <= 0:
            pub.attempt_count = 1
    pub.error_code = error.code
    pub.error_message = error.message
    pub.updated_at = now
    if not error.retryable:
        pub.status = PublicationStatus.failed
        return
    if pub.attempt_count >= MAX_ATTEMPTS:
        pub.status = PublicationStatus.dead
        return
    delay_index = max(pub.attempt_count - 1, 0)
    delay = RETRY_DELAYS[min(delay_index, len(RETRY_DELAYS) - 1)]
    pub.status = PublicationStatus.scheduled
    pub.scheduled_at = now + delay
