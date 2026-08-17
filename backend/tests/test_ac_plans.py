from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentPlan
from tests.helpers import auth_header, create_brand, register_user
from tests.openai_mock import PLAN_JAN, install_openai_mock, openai_count_mismatch, openai_invalid


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch) -> None:
    install_openai_mock(monkeypatch)


def _generate(client: TestClient, headers: dict, brand_id: str, body: dict | None = None):
    return client.post(
        f"/api/v1/brands/{brand_id}/plans/generate",
        json=body or PLAN_JAN,
        headers=headers,
    )


def test_ac04_no_kit_no_generate(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    draft = create_brand(client, headers, offers=[], example_posts=[])
    assert draft.json()["onboarding_completed"] is False
    blocked = _generate(client, headers, draft.json()["id"])
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "brand_kit_incomplete"


def test_ac20_generate_returns_202(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    response = _generate(client, headers, brand_id)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job.status_code == 200
    body = job.json()
    assert body["status"] in {"succeeded", "failed"}
    assert body["id"] == job_id


def test_ac05_slot_count_and_holidays(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    client.post(
        f"/api/v1/brands/{brand_id}/trends",
        json={"title": "AI-рассылки", "note": "рост интереса", "starts_on": "2026-01-01"},
        headers=headers,
    )
    response = _generate(client, headers, brand_id)
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=headers).json()
    assert job["status"] == "succeeded"
    result = job["result"]
    expected = sum(PLAN_JAN["targets"].values())
    assert result["item_count"] == expected
    holidays = result["holidays_considered"]
    assert any("Новый год" in item["name"] for item in holidays)
    plan = client.get(f"/api/v1/plans/{result['plan_id']}", headers=headers).json()
    assert len(plan["items"]) == expected
    themes = " ".join(item["theme"] for item in plan["items"])
    holiday_in_theme = "Новый год" in themes
    holiday_in_panel = any("Новый год" in item["name"] for item in plan["params"]["holidays_considered"])
    assert holiday_in_theme or holiday_in_panel
    assert any(item["title"] == "AI-рассылки" for item in result["trends_considered"])


def test_ac06_invalid_json_does_not_persist_plan(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch, openai_invalid)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    response = _generate(client, headers, brand_id)
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=headers).json()
    assert job["status"] == "failed"
    assert job["error"] == "schema_invalid"
    plans = db.scalars(select(ContentPlan)).all()
    assert plans == []


def test_ac06_count_mismatch_does_not_persist_plan(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch, openai_count_mismatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    response = _generate(client, headers, brand_id)
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=headers).json()
    assert job["status"] == "failed"
    assert job["error"] == "schema_count_mismatch"
    assert db.scalars(select(ContentPlan)).all() == []


def test_ac07_approve_then_conflict_or_revision(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    first = _generate(client, headers, brand_id)
    plan_id = client.get(f"/api/v1/jobs/{first.json()['job_id']}", headers=headers).json()["result"][
        "plan_id"
    ]
    approved = client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"status": "approved"},
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    conflict = _generate(client, headers, brand_id)
    assert conflict.status_code == 409
    assert _error(conflict)["code"] == "plan_active_exists"
    revision = _generate(client, headers, brand_id, {**PLAN_JAN, "create_revision": True})
    assert revision.status_code == 202
    old = client.get(f"/api/v1/plans/{plan_id}", headers=headers).json()
    assert old["status"] == "archived"
    new_job = client.get(f"/api/v1/jobs/{revision.json()['job_id']}", headers=headers).json()
    assert new_job["status"] == "succeeded"
    assert new_job["result"]["plan_id"] != plan_id


def test_draft_regenerate_requires_confirm(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    first = _generate(client, headers, brand_id)
    assert first.status_code == 202
    blocked = _generate(client, headers, brand_id)
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "plan_active_exists"
    confirmed = _generate(client, headers, brand_id, {**PLAN_JAN, "confirm": True})
    assert confirmed.status_code == 202
    job = client.get(f"/api/v1/jobs/{confirmed.json()['job_id']}", headers=headers).json()
    assert job["status"] == "succeeded"


def test_foreign_plan_and_job_are_not_found(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    generated = _generate(client, headers, brand_id).json()
    job_id = generated["job_id"]
    plan_id = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()["result"]["plan_id"]
    stranger = register_user(client, email="other@example.com", workspace_name="Other").json()
    other = auth_header(stranger["tokens"])
    plan = client.get(f"/api/v1/plans/{plan_id}", headers=other)
    assert plan.status_code == 404
    assert _error(plan)["code"] == "not_found"
    job = client.get(f"/api/v1/jobs/{job_id}", headers=other)
    assert job.status_code == 404
    assert _error(job)["code"] == "not_found"
    missing = client.get(f"/api/v1/jobs/{uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json() == job.json()
