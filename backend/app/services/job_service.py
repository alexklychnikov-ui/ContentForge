import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BrandProfile, Job, JobStatus, JobType, User
from app.services.brand_service import require_brand
from app.services.job_runner import run_job_in_session
from app.task_registry import TASKS


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


def dispatch_job(db: Session, job: Job) -> None:
    if job.status is not JobStatus.queued:
        return
    if os.environ.get("TESTING") == "1":
        run_job_in_session(db, job.id)
        return
    db.commit()
    task = TASKS.get(job.type)
    if task is None:
        raise RuntimeError(f"Celery task not registered for {job.type}")
    task.delay(str(job.id))


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
    for job in jobs:
        payload = job.payload or {}
        if (
            str(payload.get("brand_id")) == brand_key
            and int(payload.get("year") or 0) == year
            and int(payload.get("month") or 0) == month
        ):
            return job
    return None
