import logging
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Publication, PublicationStatus
from app.security import utc_now
from app.services.analytics_service import run_analytics_sync
from app.services.audit import scrub_secrets
from app.services.publish_worker import run_publish_due
from tests.gmail_mock import install_gmail_mock
from tests.helpers import auth_header, create_brand, register_user
from tests.openai_mock import install_openai_mock


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch) -> None:
    install_openai_mock(monkeypatch)


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def _connect_telegram(client: TestClient, headers: dict, brand_id: str, token: str = "123:GOOD-TOKEN"):
    created = client.post(
        f"/api/v1/brands/{brand_id}/channels/telegram/credentials",
        json={
            "pdn_consent": True,
            "display_name": "NODEX TG",
            "bot_token": token,
            "channel_id": "-100123",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _connect_gmail(client: TestClient, headers: dict, brand_id: str, password: str):
    created = client.post(
        f"/api/v1/brands/{brand_id}/channels/gmail/credentials",
        json={
            "pdn_consent": True,
            "display_name": "Gmail",
            "from_email": "me@gmail.com",
            "app_password": password,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _piece_with_variant(
    client: TestClient, headers: dict, brand_id: str, text: str = "Hello TG"
) -> tuple[str, str]:
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "social_post"},
        headers=headers,
    )
    assert piece.status_code == 201
    generated = client.post(
        f"/api/v1/content/{piece.json()['id']}/generate",
        json={"variant_label": "A", "channel_type": "telegram"},
        headers=headers,
    )
    assert generated.status_code == 202
    variant_id = client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers
    ).json()["result"]["variant_id"]
    patched = client.patch(
        f"/api/v1/content/{piece.json()['id']}/variants/{variant_id}",
        json={"payload": {"text": text, "cta": "Кейс"}},
        headers=headers,
    )
    assert patched.status_code == 200
    return piece.json()["id"], variant_id


def _assert_no_fake_zeros(block: dict) -> None:
    availability = block.get("availability")
    metrics = block.get("metrics") or {}
    unavailable = block.get("unavailable") or []
    if isinstance(block.get("normalized"), dict):
        availability = block["normalized"].get("availability", availability)
        metrics = block["normalized"].get("metrics") or metrics
        unavailable = block["normalized"].get("unavailable") or unavailable
    if availability == "unavailable":
        assert metrics == {}
    for key in unavailable:
        assert key not in metrics
    for key, value in metrics.items():
        if isinstance(value, dict):
            assert value.get("availability") == "available"
            assert "sum" in value or "avg" in value or "value" in value


def test_ac16_summary_does_not_present_zero_when_unavailable(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    _piece_id, variant_id = _piece_with_variant(client, headers, brand_id)
    now = utc_now()
    created = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={
            "variant_id": variant_id,
            "channel_account_id": channel["id"],
            "scheduled_at": now.isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201
    run_publish_due(db, now=now)
    db.commit()
    stats = run_analytics_sync(db, now=now, force=True)
    db.commit()
    assert stats["captured"] >= 1
    start = (now - timedelta(days=1)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    summary = client.get(
        f"/api/v1/brands/{brand_id}/analytics/summary",
        params={"from": start, "to": end},
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    telegram = next(item for item in body["channels"] if item["channel_type"] == "telegram")
    assert telegram["publications"] >= 1
    _assert_no_fake_zeros(telegram)
    assert telegram["availability"] in {"unavailable", "partial"}
    assert telegram["metrics"].get("impressions") != 0
    assert "impressions" not in telegram["metrics"]
    analytics = client.get(
        f"/api/v1/publications/{created.json()['id']}/analytics",
        headers=headers,
    )
    assert analytics.status_code == 200
    snapshots = analytics.json()["snapshots"]
    assert snapshots
    snap = snapshots[0]
    assert snap["availability"] == "unavailable"
    _assert_no_fake_zeros(snap)
    assert snap["normalized"]["metrics"] == {}
    assert 0 not in (snap["normalized"].get("metrics") or {}).values()


def test_gmail_metrics_sent_failed_opens_unavailable(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch)
    install_gmail_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_gmail(client, headers, brand_id, password="gmail-app-pass-SECRET")
    added = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "self@example.com"},
        headers=headers,
    )
    assert added.status_code == 201
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "email"},
        headers=headers,
    )
    assert piece.status_code == 201
    generated = client.post(
        f"/api/v1/content/{piece.json()['id']}/generate",
        json={"variant_label": "A", "channel_type": "gmail"},
        headers=headers,
    )
    assert generated.status_code == 202
    variant_id = client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers
    ).json()["result"]["variant_id"]
    now = utc_now()
    created = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={
            "variant_id": variant_id,
            "channel_account_id": channel["id"],
            "scheduled_at": now.isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    run_publish_due(db, now=now)
    db.commit()
    run_analytics_sync(db, now=now, force=True)
    db.commit()
    start = (now - timedelta(days=1)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    summary = client.get(
        f"/api/v1/brands/{brand_id}/analytics/summary",
        params={"from": start, "to": end},
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    gmail = next(item for item in summary.json()["channels"] if item["channel_type"] == "gmail")
    assert gmail["metrics"]["sent"]["sum"] >= 1
    assert gmail["metrics"]["failed"]["availability"] == "available"
    assert "opened" not in gmail["metrics"]
    assert "clicked" not in gmail["metrics"]
    detail = client.get(
        f"/api/v1/publications/{created.json()['id']}/analytics",
        headers=headers,
    )
    assert detail.status_code == 200
    snap = detail.json()["snapshots"][0]
    assert snap["normalized"]["metrics"]["sent"] >= 1
    assert "failed" in snap["normalized"]["metrics"]
    assert "opened" in snap["normalized"]["unavailable"]
    assert "clicked" in snap["normalized"]["unavailable"]
    assert "opened" not in snap["normalized"]["metrics"]
    _assert_no_fake_zeros(snap)


def test_ac17_sequential_experiment_two_publications_declare_winner(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    _connect_telegram(client, headers, brand_id)
    piece_id, variant_a = _piece_with_variant(client, headers, brand_id, "Variant A")
    variant_b_resp = client.post(
        f"/api/v1/content/{piece_id}/variants",
        json={"label": "B", "payload": {"text": "Variant B"}},
        headers=headers,
    )
    assert variant_b_resp.status_code == 201
    variant_b = variant_b_resp.json()["id"]
    now = utc_now()
    created = client.post(
        f"/api/v1/brands/{brand_id}/experiments",
        json={
            "piece_id": piece_id,
            "variant_a_id": variant_a,
            "variant_b_id": variant_b,
            "channel_type": "telegram",
            "mode": "sequential",
            "primary_metric": "impressions",
            "window_start": now.isoformat(),
            "window_end": (now + timedelta(days=7)).isoformat(),
            "schedule_a": (now + timedelta(minutes=1)).isoformat(),
            "schedule_b": (now + timedelta(minutes=5)).isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    early = client.post(f"/api/v1/experiments/{experiment_id}/winner", json={"variant_id": variant_a}, headers=headers)
    assert early.status_code == 409
    started = client.post(f"/api/v1/experiments/{experiment_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"
    pubs = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert pubs.status_code == 200
    experiment_pubs = [row for row in pubs.json() if row.get("experiment_id") == experiment_id]
    assert len(experiment_pubs) == 2
    times = sorted(row["scheduled_at"] for row in experiment_pubs)
    assert times[0] != times[1]
    still_open = client.post(
        f"/api/v1/experiments/{experiment_id}/winner",
        json={"variant_id": variant_a},
        headers=headers,
    )
    assert still_open.status_code == 409
    assert _error(still_open)["code"] == "window_open"
    stopped = client.post(f"/api/v1/experiments/{experiment_id}/stop", headers=headers)
    assert stopped.status_code == 200
    winner = client.post(
        f"/api/v1/experiments/{experiment_id}/winner",
        json={"variant_id": variant_a},
        headers=headers,
    )
    assert winner.status_code == 200, winner.text
    assert winner.json()["status"] == "completed"
    assert winner.json()["winner_variant_id"] == variant_a
    detail = client.get(f"/api/v1/experiments/{experiment_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["metrics"]["publication_ids"]) == 2
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "declare_winner")).all()
    assert len(logs) == 1
    assert logs[0].entity_id == UUID(experiment_id)


def test_ac21_logs_have_no_password_or_token_plaintext(
    client: TestClient, db: Session, monkeypatch, caplog
) -> None:
    install_openai_mock(monkeypatch)
    caplog.set_level(logging.DEBUG)
    password = "AuthPass-SECRET-99"
    token = "123:BOT-TOKEN-SECRET"
    registered = register_user(client, email="sec@example.com", password=password).json()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "sec@example.com", "password": password},
    )
    assert login.status_code == 200
    headers = auth_header(registered["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id, token=token)
    _piece_id, variant_id = _piece_with_variant(client, headers, brand_id)
    now = utc_now()
    created = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={
            "variant_id": variant_id,
            "channel_account_id": channel["id"],
            "scheduled_at": now.isoformat(),
            "idempotency_key": "ac21-pub",
        },
        headers=headers,
    )
    assert created.status_code == 201
    run_publish_due(db, now=now)
    db.commit()
    text = caplog.text
    assert password not in text
    assert token not in text
    assert "BOT-TOKEN-SECRET" not in text
    assert "AuthPass-SECRET-99" not in text
    access = registered["tokens"]["access_token"]
    refresh = registered["tokens"]["refresh_token"]
    assert access not in text
    assert refresh not in text
    logs = db.scalars(select(AuditLog)).all()
    assert logs
    for row in logs:
        dumped = str(row.data)
        assert password not in dumped
        assert token not in dumped
        assert "BOT-TOKEN-SECRET" not in dumped
        assert "AuthPass-SECRET-99" not in dumped
        assert access not in dumped
        assert refresh not in dumped
    pub = db.get(Publication, UUID(created.json()["id"]))
    assert pub is not None
    assert pub.status is PublicationStatus.published
    publish_logs = [row for row in logs if row.action == "publish"]
    assert publish_logs


def test_analytics_experiments_isolated_across_workspaces(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_openai_mock(monkeypatch)
    owner = register_user(client).json()
    stranger = register_user(client, email="other@example.com", workspace_name="Other").json()
    headers = auth_header(owner["tokens"])
    other = auth_header(stranger["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    piece_id, variant_a = _piece_with_variant(client, headers, brand_id, "Variant A")
    variant_b = client.post(
        f"/api/v1/content/{piece_id}/variants",
        json={"label": "B", "payload": {"text": "Variant B"}},
        headers=headers,
    ).json()["id"]
    now = utc_now()
    created = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={
            "variant_id": variant_a,
            "channel_account_id": channel["id"],
            "scheduled_at": now.isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201
    pub_id = created.json()["id"]
    run_publish_due(db, now=now)
    db.commit()
    run_analytics_sync(db, now=now, force=True)
    db.commit()
    experiment = client.post(
        f"/api/v1/brands/{brand_id}/experiments",
        json={
            "piece_id": piece_id,
            "variant_a_id": variant_a,
            "variant_b_id": variant_b,
            "channel_type": "telegram",
            "mode": "sequential",
            "primary_metric": "impressions",
            "window_start": now.isoformat(),
            "window_end": (now + timedelta(days=7)).isoformat(),
            "schedule_a": (now + timedelta(minutes=1)).isoformat(),
            "schedule_b": (now + timedelta(minutes=5)).isoformat(),
        },
        headers=headers,
    )
    assert experiment.status_code == 201, experiment.text
    experiment_id = experiment.json()["id"]
    start = (now - timedelta(days=1)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    summary_path = f"/api/v1/brands/{brand_id}/analytics/summary"
    assert client.get(summary_path, params={"from": start, "to": end}).status_code == 401
    assert client.get(f"/api/v1/publications/{pub_id}/analytics").status_code == 401
    assert client.get(f"/api/v1/brands/{brand_id}/experiments").status_code == 401
    assert client.get(f"/api/v1/experiments/{experiment_id}").status_code == 401
    assert (
        client.get(summary_path, params={"from": start, "to": end}, headers=other).status_code
        == 404
    )
    assert client.get(f"/api/v1/publications/{pub_id}/analytics", headers=other).status_code == 404
    listed = client.get(f"/api/v1/brands/{brand_id}/experiments", headers=other)
    assert listed.status_code == 404
    assert client.get(f"/api/v1/experiments/{experiment_id}", headers=other).status_code == 404
    assert client.post(f"/api/v1/experiments/{experiment_id}/start", headers=other).status_code == 404
    assert client.post(f"/api/v1/experiments/{experiment_id}/stop", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/v1/experiments/{experiment_id}/winner",
            json={"variant_id": variant_a},
            headers=other,
        ).status_code
        == 404
    )
    own = client.get(summary_path, params={"from": start, "to": end}, headers=headers)
    assert own.status_code == 200
    assert "channels" in own.json()
    detail = client.get(f"/api/v1/publications/{pub_id}/analytics", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["publication_id"] == pub_id


def test_audit_scrub_drops_secret_keys_and_values() -> None:
    cleaned = scrub_secrets(
        {
            "channel_type": "telegram",
            "bot_token": "123:BOT-TOKEN-SECRET",
            "app_password": "gmail-app-pass-SECRET",
            "api_key": "sk-live-SECRET",
            "note": "token=LEAKED-TOKEN password=LEAKED-PASS",
            "nested": {"refresh_token": "refresh-SECRET", "ok": True},
        }
    )
    assert "bot_token" not in cleaned
    assert "app_password" not in cleaned
    assert "api_key" not in cleaned
    assert cleaned["channel_type"] == "telegram"
    assert "LEAKED-TOKEN" not in cleaned["note"]
    assert "LEAKED-PASS" not in cleaned["note"]
    assert "refresh_token" not in cleaned["nested"]
    assert cleaned["nested"]["ok"] is True


def test_audit_log_append_only(db: Session, client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "password12"},
    )
    row = db.scalars(select(AuditLog).where(AuditLog.action == "login")).first()
    assert row is not None
    row.action = "tamper"
    try:
        db.flush()
        raise AssertionError("AuditLog update must be rejected")
    except ValueError as exc:
        assert "append-only" in str(exc)
        db.rollback()
