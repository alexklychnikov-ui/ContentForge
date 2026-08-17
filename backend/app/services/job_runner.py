import logging
from typing import assert_never
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.logutil import job_id_ctx, log_event
from app.models import BrandProfile, Job, JobStatus, JobType
from app.services.ai_client import AIJobError
from app.services.ai_jobs import execute_generate_content, execute_generate_plan, execute_rewrite
from app.services.brand_kit import is_brand_kit_complete

logger = logging.getLogger(__name__)


def run_job_in_worker(job_id: str) -> None:
    db = get_session_factory()()
    try:
        run_job_in_session(db, UUID(job_id))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ai_job_worker_failed job_id=%s", job_id)
        raise
    finally:
        db.close()


def run_job_in_session(db: Session, job_id: UUID) -> None:
    token = job_id_ctx.set(str(job_id))
    try:
        _run_job_in_session(db, job_id)
    finally:
        job_id_ctx.reset(token)


def _run_job_in_session(db: Session, job_id: UUID) -> None:
    job = db.get(Job, job_id)
    if job is None:
        logger.warning("ai_job_missing job_id=%s", job_id)
        return
    if job.status in {JobStatus.succeeded, JobStatus.failed}:
        return
    job.status = JobStatus.running
    db.flush()
    log_event(logger, "ai_job_running", job_id=job.id, type=job.type.value)
    try:
        brand_id = job.payload.get("brand_id")
        brand = db.get(BrandProfile, UUID(str(brand_id))) if brand_id else None
        if brand is None or brand.deleted_at is not None:
            raise AIJobError("not_found", "Бренд не найден")
        if job.type is JobType.generate_plan and not is_brand_kit_complete(brand):
            raise AIJobError("brand_kit_incomplete", "Сначала заполните Brand Kit")
        with db.begin_nested():
            if job.type is JobType.generate_plan:
                result = execute_generate_plan(db, job, brand)
            elif job.type is JobType.generate_content:
                result = execute_generate_content(db, job, brand)
            elif job.type is JobType.rewrite:
                result = execute_rewrite(db, job, brand)
            else:
                assert_never(job.type)
        job.status = JobStatus.succeeded
        job.result = result
        job.error = None
    except AIJobError as exc:
        _fail_job(job, exc.code, exc.message, exc.details)
    except Exception:
        logger.exception("ai_job_failed job_id=%s type=%s", job.id, job.type.value)
        _fail_job(job, "internal_error", "AI job failed", {})
    db.flush()


def _fail_job(job: Job, code: str, message: str, details: dict) -> None:
    job.status = JobStatus.failed
    job.error = code
    job.result = {"error": {"code": code, "message": message, "details": details}}
