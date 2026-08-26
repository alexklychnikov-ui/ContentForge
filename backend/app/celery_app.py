from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.logutil import configure_app_logging
from app.models import JobType
from app.services.analytics_service import run_analytics_sync_job
from app.services.auto_pipeline import run_prepare_plan_slots_job
from app.services.job_runner import run_job_in_worker
from app.services.publish_worker import run_publish_due_job
from app.task_registry import TASKS

configure_app_logging()
settings = get_settings()

celery_app = Celery(
    "contentforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="celery",
    beat_schedule={
        "publish-due": {
            "task": "contentforge.publish_due",
            "schedule": crontab(minute="*"),
        },
        "sync-analytics": {
            "task": "contentforge.sync_analytics",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "prepare-plan-slots": {
            "task": "contentforge.prepare_plan_slots",
            "schedule": crontab(minute=0),
        },
    },
    task_routes={
        "contentforge.generate_plan": {"queue": "ai"},
        "contentforge.generate_content": {"queue": "ai"},
        "contentforge.rewrite": {"queue": "ai"},
    },
)


@celery_app.task(name="contentforge.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="contentforge.generate_plan", queue="ai")
def generate_plan(job_id: str) -> None:
    run_job_in_worker(job_id)


@celery_app.task(name="contentforge.generate_content", queue="ai")
def generate_content(job_id: str) -> None:
    run_job_in_worker(job_id)


@celery_app.task(name="contentforge.rewrite", queue="ai")
def rewrite(job_id: str) -> None:
    run_job_in_worker(job_id)


@celery_app.task(name="contentforge.publish_due")
def publish_due() -> dict[str, int]:
    return run_publish_due_job()


@celery_app.task(name="contentforge.sync_analytics")
def sync_analytics() -> dict[str, int]:
    return run_analytics_sync_job()


@celery_app.task(name="contentforge.prepare_plan_slots")
def prepare_plan_slots() -> dict[str, int]:
    return run_prepare_plan_slots_job()


TASKS[JobType.generate_plan] = generate_plan
TASKS[JobType.generate_content] = generate_content
TASKS[JobType.rewrite] = rewrite
