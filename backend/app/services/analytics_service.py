import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.errors import AppError
from app.logutil import job_id_ctx, log_event, publication_id_ctx
from app.models import (
    AnalyticsSnapshot,
    ChannelAccount,
    ChannelType,
    Publication,
    PublicationStatus,
    User,
)
from app.security import as_utc, utc_now
from app.services.adapters import get_adapter
from app.services.audit import scrub_secrets
from app.services.brand_service import require_brand
from app.services.metrics import split_adapter_payload
from app.services.publish_service import require_publication

logger = logging.getLogger(__name__)

SYNC_YOUNG = timedelta(days=14)
SYNC_MAX_AGE = timedelta(days=30)
SYNC_YOUNG_EVERY = timedelta(hours=6)
SYNC_OLD_EVERY = timedelta(days=1)
PUBLISHED_STATUSES = {PublicationStatus.published, PublicationStatus.published_manual}
FAILED_STATUSES = {PublicationStatus.failed, PublicationStatus.dead}


def latest_snapshot_map(
    db: Session, publication_ids: list[UUID]
) -> dict[UUID, AnalyticsSnapshot]:
    if not publication_ids:
        return {}
    rows = list(
        db.scalars(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.publication_id.in_(publication_ids))
            .order_by(AnalyticsSnapshot.captured_at.desc())
        ).all()
    )
    latest: dict[UUID, AnalyticsSnapshot] = {}
    for row in rows:
        latest.setdefault(row.publication_id, row)
    return latest


def _due_for_sync(
    publication: Publication, last: AnalyticsSnapshot | None, now: datetime, force: bool
) -> bool:
    if publication.status not in PUBLISHED_STATUSES:
        return False
    published_at = as_utc(publication.published_at or publication.created_at)
    age = now - published_at
    if age > SYNC_MAX_AGE:
        return False
    if force or last is None:
        return True
    interval = SYNC_YOUNG_EVERY if age <= SYNC_YOUNG else SYNC_OLD_EVERY
    return now - as_utc(last.captured_at) >= interval


def capture_publication(
    db: Session, publication: Publication, now: datetime | None = None
) -> AnalyticsSnapshot:
    moment = as_utc(now or utc_now())
    channel = db.get(ChannelAccount, publication.channel_account_id)
    if channel is None:
        payload = {"availability": "unavailable", "metrics": {}, "unavailable": [], "raw": {}}
        normalized, raw = split_adapter_payload(payload)
    else:
        adapter = get_adapter(channel.type)
        payload = adapter.fetch_metrics(channel, publication)
        normalized, raw = split_adapter_payload(payload if isinstance(payload, dict) else {})
    token = publication_id_ctx.set(str(publication.id))
    try:
        log_event(
            logger,
            "analytics_capture",
            publication_id=publication.id,
            availability=normalized.get("availability"),
        )
    finally:
        publication_id_ctx.reset(token)
    row = AnalyticsSnapshot(
        publication_id=publication.id,
        captured_at=moment,
        normalized=normalized,
        raw=raw,
    )
    db.add(row)
    db.flush()
    return row


def run_analytics_sync(
    db: Session, now: datetime | None = None, force: bool = False
) -> dict[str, int]:
    moment = as_utc(now or utc_now())
    pubs = list(
        db.scalars(
            select(Publication).where(Publication.status.in_(tuple(PUBLISHED_STATUSES)))
        ).all()
    )
    latest = latest_snapshot_map(db, [row.id for row in pubs])
    captured = 0
    skipped = 0
    for publication in pubs:
        if not _due_for_sync(publication, latest.get(publication.id), moment, force):
            skipped += 1
            continue
        capture_publication(db, publication, moment)
        captured += 1
    return {"captured": captured, "skipped": skipped, "published": len(pubs)}


def run_analytics_sync_job() -> dict[str, int]:
    job_token = job_id_ctx.set("sync_analytics")
    db = get_session_factory()()
    try:
        stats = run_analytics_sync(db)
        db.commit()
        log_event(logger, "analytics_sync_done", **stats)
        return stats
    except Exception:
        db.rollback()
        logger.exception("analytics_sync_failed job_id=sync_analytics")
        raise
    finally:
        db.close()
        job_id_ctx.reset(job_token)


def _in_range(publication: Publication, start: datetime, end: datetime) -> bool:
    point = as_utc(publication.published_at or publication.scheduled_at)
    return start <= point <= end


def brand_summary(
    db: Session,
    user: User,
    brand_id: UUID,
    from_at: datetime,
    to_at: datetime,
) -> dict:
    brand, _membership = require_brand(db, user, brand_id)
    start = as_utc(from_at)
    end = as_utc(to_at)
    if end < start:
        raise AppError(422, "validation_error", "from должен быть раньше to")
    pubs = list(
        db.scalars(
            select(Publication)
            .join(ChannelAccount, Publication.channel_account_id == ChannelAccount.id)
            .where(ChannelAccount.brand_id == brand.id)
        ).all()
    )
    in_period = [row for row in pubs if _in_range(row, start, end)]
    latest = latest_snapshot_map(db, [row.id for row in in_period])
    channels: dict[ChannelType, dict] = {}
    for publication in in_period:
        channel = db.get(ChannelAccount, publication.channel_account_id)
        if channel is None:
            continue
        bucket = channels.setdefault(
            channel.type,
            {
                "channel_type": channel.type.value,
                "publications": 0,
                "failed": 0,
                "sums": {},
                "counts": {},
            },
        )
        bucket["publications"] += 1
        if publication.status in FAILED_STATUSES:
            bucket["failed"] += 1
        snapshot = latest.get(publication.id)
        metrics = (snapshot.normalized or {}).get("metrics") if snapshot is not None else {}
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if not isinstance(value, int):
                continue
            bucket["sums"][key] = bucket["sums"].get(key, 0) + value
            bucket["counts"][key] = bucket["counts"].get(key, 0) + 1
    items = []
    for channel_type in ChannelType:
        bucket = channels.get(channel_type)
        if bucket is None:
            continue
        metrics = {}
        for key, total in bucket["sums"].items():
            n = bucket["counts"][key]
            metrics[key] = {"sum": total, "avg": total / n, "availability": "available"}
        if not metrics:
            availability = "unavailable"
        else:
            availability = "partial"
        items.append(
            {
                "channel_type": bucket["channel_type"],
                "publications": bucket["publications"],
                "failed": bucket["failed"],
                "availability": availability,
                "metrics": metrics,
            }
        )
    return {"from": start.isoformat(), "to": end.isoformat(), "channels": items}


def publication_analytics(db: Session, user: User, publication_id: UUID) -> dict:
    publication = require_publication(db, user, publication_id)
    rows = list(
        db.scalars(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.publication_id == publication.id)
            .order_by(AnalyticsSnapshot.captured_at.desc())
        ).all()
    )
    snapshots = [
        {
            "id": str(row.id),
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
            "availability": (row.normalized or {}).get("availability") or "unavailable",
            "normalized": row.normalized or {},
            "raw": scrub_secrets(row.raw or {}),
        }
        for row in rows
    ]
    return {"publication_id": str(publication.id), "snapshots": snapshots}
