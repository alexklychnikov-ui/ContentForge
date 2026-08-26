from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BrandProfile,
    ChannelType,
    ContentPlan,
    ContentType,
    Job,
    JobType,
    PlanGoal,
    PlanItem,
    PlanStatus,
    User,
)
from app.services.auto_pipeline import compute_slot_at, is_slot_eligible, run_prepare_plan_slots
from tests.helpers import auth_header, create_brand, register_user


def test_slot_eligible_inside_lead_window() -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    slot = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
    assert is_slot_eligible(now, slot, lead_hours=24) is True
    assert is_slot_eligible(now, slot, lead_hours=12) is False


def test_slot_eligible_rejects_past() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    slot = datetime(2026, 8, 26, 11, 0, tzinfo=timezone.utc)
    assert is_slot_eligible(now, slot, lead_hours=24) is False


def test_compute_slot_at_moscow_noon() -> None:
    slot = compute_slot_at(date(2026, 8, 26), hour=12, tz_name="Europe/Moscow")
    assert slot == datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def test_compute_slot_at_bad_tz_falls_back() -> None:
    slot = compute_slot_at(date(2026, 8, 26), hour=12, tz_name="Not/AZone")
    assert slot == datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def test_brand_patch_auto_pipeline_fields(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand = create_brand(client, headers).json()
    assert brand["auto_pipeline_enabled"] is False
    assert brand["auto_pipeline_lead_hours"] == 24
    assert brand["default_slot_hour"] == 12
    patched = client.patch(
        f"/api/v1/brands/{brand['id']}",
        json={
            "auto_pipeline_enabled": True,
            "auto_pipeline_lead_hours": 48,
            "default_slot_hour": 9,
        },
        headers=headers,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["auto_pipeline_enabled"] is True
    assert body["auto_pipeline_lead_hours"] == 48
    assert body["default_slot_hour"] == 9


def test_prepare_enqueues_generate_when_enabled(
    client: TestClient, db: Session, monkeypatch
) -> None:
    # Avoid generate_content running live: prepare only creates the job row when we stub dispatch.
    enqueued: list[str] = []

    def _capture_dispatch(_db: Session, job: Job) -> None:
        enqueued.append(str(job.id))

    monkeypatch.setattr("app.services.auto_pipeline.dispatch_job", _capture_dispatch)

    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_body = create_brand(client, headers).json()
    brand_id = UUID(brand_body["id"])
    client.patch(
        f"/api/v1/brands/{brand_id}",
        json={"auto_pipeline_enabled": True, "auto_pipeline_lead_hours": 48, "default_slot_hour": 12},
        headers=headers,
    )
    db.expire_all()
    brand = db.get(BrandProfile, brand_id)
    assert brand is not None
    user = db.query(User).filter(User.email == "owner@example.com").one()
    item_date = date(2026, 8, 27)
    plan = ContentPlan(
        brand_id=brand.id,
        year=2026,
        month=8,
        status=PlanStatus.approved,
        params={},
        model="test",
        created_by=user.id,
    )
    db.add(plan)
    db.flush()
    item = PlanItem(
        plan_id=plan.id,
        date=item_date,
        channel_type=ChannelType.telegram,
        content_type=ContentType.social_post,
        theme="Тема",
        goal=PlanGoal.awareness,
        hook="Хук",
        sort_order=0,
    )
    db.add(item)
    db.commit()

    slot = compute_slot_at(item_date, brand.default_slot_hour, brand.timezone)
    now = slot - timedelta(hours=6)
    before = db.query(Job).filter(Job.type == JobType.generate_content).count()
    stats = run_prepare_plan_slots(db, now=now)
    db.commit()

    assert stats["brands"] == 1
    assert stats["considered"] == 1
    assert stats["enqueued"] == 1
    assert len(enqueued) == 1
    after = db.query(Job).filter(Job.type == JobType.generate_content).count()
    assert after == before + 1
    job = db.get(Job, UUID(enqueued[0]))
    assert job is not None
    assert job.payload.get("auto_schedule") is True
    assert job.payload.get("variant_label") == "A"
