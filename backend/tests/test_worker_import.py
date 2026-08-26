from app.celery_app import (
    celery_app,
    generate_content,
    generate_plan,
    ping,
    prepare_plan_slots,
    publish_due,
    rewrite,
    sync_analytics,
)
from app.main import app


def test_worker_imports_api_app() -> None:
    assert app.title == "ContentForge"
    assert celery_app.main == "contentforge"


def test_ping_task_registered() -> None:
    assert "contentforge.ping" in celery_app.tasks
    assert ping() == {"status": "ok"}


def test_ai_queue_tasks_registered() -> None:
    assert "contentforge.generate_plan" in celery_app.tasks
    assert "contentforge.generate_content" in celery_app.tasks
    assert "contentforge.rewrite" in celery_app.tasks
    assert generate_plan.name == "contentforge.generate_plan"
    assert generate_content.name == "contentforge.generate_content"
    assert rewrite.name == "contentforge.rewrite"
    assert "contentforge.publish_due" in celery_app.tasks
    assert publish_due.name == "contentforge.publish_due"
    assert "publish-due" in celery_app.conf.beat_schedule
    assert "contentforge.sync_analytics" in celery_app.tasks
    assert sync_analytics.name == "contentforge.sync_analytics"
    assert "sync-analytics" in celery_app.conf.beat_schedule
    assert "contentforge.prepare_plan_slots" in celery_app.tasks
    assert prepare_plan_slots.name == "contentforge.prepare_plan_slots"
    assert "prepare-plan-slots" in celery_app.conf.beat_schedule
