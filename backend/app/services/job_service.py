import logging
import os
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BrandProfile, Job, JobStatus, JobType, User
from app.security import utc_now
from app.services.brand_service import require_brand
from app.services.job_runner import run_job_in_session
from app.task_registry import TASKS

logger = logging.getLogger(__name__)

# Queued jobs with no Celery pickup (e.g. dispatch failed after commit) block retries.
STUCK_QUEUED_AFTER = timedelta(minutes=2)


def create_job(
    db: Session,
    *,
    user: User,
    job_type: JobType,
    payload: dict,
    idempotency_key: str | None = None,
) -> Job:
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == key))
        if existing is not None:
            return existing
    job = Job(
        type=job_type,
        status=JobStatus.queued,
        payload=payload,
        created_by=user.id,
        idempotency_key=key,
    )
    db.add(job)
    db.flush()
    return job


def _ensure_celery_tasks() -> None:
    """API process does not import celery_app by default; populate TASKS lazily."""
    if TASKS:
        return
    import app.celery_app  # noqa: F401


def dispatch_job(db: Session, job: Job) -> None:
    if job.status is not JobStatus.queued:
        return
    if os.environ.get("TESTING") == "1":
        run_job_in_session(db, job.id)
        return
    _ensure_celery_tasks()
    task = TASKS.get(job.type)
    if task is None:
        job.status = JobStatus.failed
        job.error = f"Celery task not registered for {job.type}"
        db.commit()
        raise RuntimeError(job.error)
    job_id = job.id
    job_type = job.type
    db.commit()
    try:
        async_result = task.delay(str(job_id))
        logger.info(
            "celery_enqueued job_id=%s task_id=%s type=%s",
            job_id,
            getattr(async_result, "id", None),
            job_type,
        )
    except Exception as exc:
        logger.exception("celery_enqueue_failed job_id=%s", job_id)
        stuck = db.get(Job, job_id)
        if stuck is not None and stuck.status is JobStatus.queued:
            stuck.status = JobStatus.failed
            stuck.error = f"enqueue_failed: {exc}"
            db.commit()
        raise


def get_job(db: Session, user: User, job_id: UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(404, "not_found", "Задача не найдена")
    brand_id = job.payload.get("brand_id") if isinstance(job.payload, dict) else None
    if brand_id:
        try:
            require_brand(db, user, UUID(str(brand_id)))
        except AppError as exc:
            if exc.status_code == 404:
                raise AppError(404, "not_found", "Задача не найдена") from exc
            raise
        return job
    if job.created_by != user.id:
        raise AppError(404, "not_found", "Задача не найдена")
    return job


def inflight_generate_plan(
    db: Session, brand: BrandProfile, year: int, month: int
) -> Job | None:
    jobs = db.scalars(
        select(Job).where(
            Job.type == JobType.generate_plan,
            Job.status.in_((JobStatus.queued, JobStatus.running)),
        )
    ).all()
    brand_key = str(brand.id)
    now = utc_now()
    for job in jobs:
        payload = job.payload or {}
        if not (
            str(payload.get("brand_id")) == brand_key
            and int(payload.get("year") or 0) == year
            and int(payload.get("month") or 0) == month
        ):
            continue
        if (
            job.status is JobStatus.queued
            and job.created_at is not None
            and now - job.created_at > STUCK_QUEUED_AFTER
        ):
            job.status = JobStatus.failed
            job.error = "stuck_queued_timeout"
            db.flush()
            logger.warning("generate_plan_stuck_queued job_id=%s age=%s", job.id, now - job.created_at)
            continue
        return job
    return None
