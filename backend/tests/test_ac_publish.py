import logging
import os
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ChannelType,
    Membership,
    MembershipRole,
    Publication,
    PublicationStatus,
    User,
)
from app.security import utc_now
from app.services.adapters import get_adapter
from app.services.adapters.base import AdapterCapabilityError, AdapterError
from app.services.adapters.gmail import is_quota_error, smtp_error_to_adapter, smtp_send_one
from app.services.adapters.manual import ManualCopyAdapter
from app.services.adapters.telegram import (
    TELEGRAM_API_BASE,
    _health_reason,
    build_telegram_url,
    http_loopback_as_socks5h,
    redact_proxy_url,
    telegram_api,
    telegram_http_client,
    telegram_result_or_raise,
)
from app.services.adapters.vk import VkAdapter, variant_text, vk_result_or_raise, wall_url
from app.services.adapters.wordpress import (
    build_wordpress_posts_url,
    wordpress_create_post,
    wordpress_http_client,
    wordpress_result_or_raise,
)
from app.services.publish_worker import run_publish_due
from tests.gmail_mock import install_gmail_mock, quota_handler
from tests.helpers import auth_header, create_brand, register_user
from tests.openai_mock import install_openai_mock
from tests.telegram_mock import (
    DEFAULT_MESSAGE_ID,
    install_telegram_mock,
    parse_error_handler,
    unauthorized_handler,
)
from tests.vk_mock import (
    DEFAULT_POST_ID,
    install_vk_mock,
    rate_limited_handler,
    unauthorized_handler as vk_unauthorized_handler,
)


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


def _variant(client: TestClient, headers: dict, brand_id: str, text: str | None = None) -> str:
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
    if text is not None:
        patched = client.patch(
            f"/api/v1/content/{piece.json()['id']}/variants/{variant_id}",
            json={"payload": {"text": text, "cta": "Кейс"}},
            headers=headers,
        )
        assert patched.status_code == 200
    return variant_id


def _schedule(client, headers, brand_id, variant_id, channel_id, **extra):
    body = {"variant_id": variant_id, "channel_account_id": channel_id, **extra}
    return client.post(f"/api/v1/brands/{brand_id}/publications", json=body, headers=headers)


def test_ac11_success_sets_published_and_external_id(
    client: TestClient, db: Session, monkeypatch
) -> None:
    calls = install_telegram_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    due = utc_now() + timedelta(minutes=2)
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=due.isoformat(),
        idempotency_key="ac11-key",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "scheduled"
    run_publish_due(db, now=due)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.published
    assert row.external_id == str(DEFAULT_MESSAGE_ID)
    sends = [item for item in calls if item["method"] in {"sendMessage", "sendPhoto"}]
    assert len(sends) == 1
    assert "GOOD-TOKEN" not in str(sends[0]["data"])
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["external_id"] == str(DEFAULT_MESSAGE_ID)
    assert "GOOD-TOKEN" not in listed.text


def test_ac12_idempotency_no_duplicate(client: TestClient, db: Session, monkeypatch) -> None:
    calls = install_telegram_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    now = utc_now()
    first = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="same-key",
    )
    assert first.status_code == 201
    second = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="same-key",
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    run_publish_due(db, now=now)
    db.commit()
    replay = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="same-key",
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "published"
    assert replay.json()["external_id"] == str(DEFAULT_MESSAGE_ID)
    retry = client.post(
        f"/api/v1/publications/{first.json()['id']}/retry",
        headers=headers,
    )
    assert retry.status_code == 409
    run_publish_due(db, now=now + timedelta(minutes=1))
    db.commit()
    sends = [item for item in calls if item["method"] in {"sendMessage", "sendPhoto"}]
    assert len(sends) == 1
    rows = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers).json()
    assert len(rows) == 1


def test_ac15_cancel_scheduled_not_published(client: TestClient, db: Session, monkeypatch) -> None:
    calls = install_telegram_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    due = utc_now() + timedelta(minutes=5)
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=due.isoformat(),
    )
    cancelled = client.post(
        f"/api/v1/publications/{created.json()['id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    run_publish_due(db, now=due + timedelta(minutes=1))
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.cancelled
    assert row.external_id is None
    sends = [item for item in calls if item["method"] in {"sendMessage", "sendPhoto"}]
    assert sends == []


def test_ac19_revoke_cancels_future(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    future = utc_now() + timedelta(hours=2)
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=future.isoformat(),
        idempotency_key="future-post",
    )
    assert created.status_code == 201
    revoked = client.delete(f"/api/v1/channels/{channel['id']}", headers=headers)
    assert revoked.status_code == 204
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "cancelled"
    assert rows[0]["id"] == created.json()["id"]
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.cancelled


def test_ac13_bad_token_failed_then_dead(client: TestClient, db: Session, monkeypatch) -> None:
    install_telegram_mock(monkeypatch, unauthorized_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id, token="999:BAD-TOKEN")
    variant_id = _variant(client, headers, brand_id)
    t0 = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=t0.isoformat(),
        idempotency_key="bad-token",
    )
    assert created.status_code == 201
    pub_id = UUID(created.json()["id"])
    run_publish_due(db, now=t0)
    db.commit()
    db.expire_all()
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.status is PublicationStatus.scheduled
    assert row.error_code == "unauthorized"
    assert row.attempt_count == 1
    assert "BAD-TOKEN" not in (row.error_message or "")
    run_publish_due(db, now=t0 + timedelta(minutes=1))
    db.commit()
    db.expire_all()
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.attempt_count == 2
    assert row.status is PublicationStatus.scheduled
    run_publish_due(db, now=t0 + timedelta(minutes=6))
    db.commit()
    db.expire_all()
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.attempt_count == 3
    assert row.status is PublicationStatus.dead
    assert row.external_id is None
    assert row.error_code == "unauthorized"


def test_parse_error_fails_without_retry_storm(
    client: TestClient, db: Session, monkeypatch
) -> None:
    install_telegram_mock(monkeypatch, parse_error_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id, text="broken <unclosed")
    t0 = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=t0.isoformat(),
    )
    run_publish_due(db, now=t0)
    db.commit()
    db.expire_all()
    pub_id = UUID(created.json()["id"])
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.error_code == "parse_error"
    assert row.attempt_count == 1
    run_publish_due(db, now=t0 + timedelta(minutes=20))
    db.commit()
    db.expire_all()
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.attempt_count == 1


def _connect_vk(
    client: TestClient,
    headers: dict,
    brand_id: str,
    *,
    token: str = "vk-community-token",
    group_id: str = "1",
):
    created = client.post(
        f"/api/v1/brands/{brand_id}/channels/vk/credentials",
        json={"pdn_consent": True, "access_token": token, "group_id": group_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_vk_autopost_sets_wall_url(client: TestClient, db: Session, monkeypatch) -> None:
    calls = install_vk_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_vk(client, headers, brand_id, group_id="241074885")
    variant_id = _variant(client, headers, brand_id, text="VK post body")
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="vk-ac-key",
    )
    assert created.status_code == 201
    run_publish_due(db, now=now + timedelta(minutes=1))
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.published
    assert row.external_id == str(DEFAULT_POST_ID)
    assert row.external_url == f"https://vk.com/wall-241074885_{DEFAULT_POST_ID}"
    posts = [item for item in calls if item["method"] == "wall.post"]
    assert len(posts) == 1
    assert posts[0]["params"]["owner_id"] == "-241074885"
    assert posts[0]["params"]["from_group"] == 1
    assert posts[0]["params"]["guid"] == "vk-ac-key"
    assert "VK post body" in str(posts[0]["params"]["message"])
    assert "vk-community-token" not in str(posts[0]["params"])
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["external_url"] == row.external_url
    assert "vk-community-token" not in listed.text


def test_vk_empty_text_no_http(client: TestClient, db: Session, monkeypatch) -> None:
    calls = install_vk_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_vk(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id, text="   ")
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
    )
    assert created.status_code == 201
    run_publish_due(db, now=now + timedelta(minutes=1))
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.error_code == "bad_request"
    assert row.attempt_count == 1
    assert not any(item["method"] == "wall.post" for item in calls)


def test_vk_rate_limited_is_retryable(client: TestClient, db: Session, monkeypatch) -> None:
    install_vk_mock(monkeypatch, rate_limited_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_vk(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id, text="flood me")
    t0 = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=t0.isoformat(),
    )
    run_publish_due(db, now=t0)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.scheduled
    assert row.error_code == "rate_limited"
    assert row.attempt_count == 1


def test_vk_unauthorized_non_retryable(client: TestClient, db: Session, monkeypatch) -> None:
    install_vk_mock(monkeypatch, vk_unauthorized_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_vk(client, headers, brand_id, token="vk-bad-token")
    variant_id = _variant(client, headers, brand_id, text="auth fail")
    t0 = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=t0.isoformat(),
    )
    run_publish_due(db, now=t0)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.error_code == "unauthorized"
    assert row.attempt_count == 1
    assert "vk-bad-token" not in (row.error_message or "")


def test_watchdog_publishing_without_external_id(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
    )
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    row.status = PublicationStatus.publishing
    row.updated_at = now - timedelta(minutes=11)
    db.commit()
    run_publish_due(db, now=now)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.error_code == "watchdog_timeout"
    assert row.status is PublicationStatus.scheduled
    assert row.external_id is None


@pytest.mark.skipif(os.environ.get("TELEGRAM_SMOKE") != "1", reason="live telegram disabled")
def test_ac11_live_smoke(client: TestClient, db: Session) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not chat_id:
        pytest.skip("TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID required")
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = client.post(
        f"/api/v1/brands/{brand_id}/channels/telegram/credentials",
        json={
            "pdn_consent": True,
            "bot_token": token,
            "channel_id": chat_id,
        },
        headers=headers,
    ).json()
    variant_id = _variant(client, headers, brand_id, text="ContentForge smoke")
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="live-smoke",
    )
    assert created.status_code == 201
    run_publish_due(db, now=now)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.published
    assert row.external_id


def test_publications_require_auth_and_brand_scope(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    stranger = register_user(client, email="other@example.com", workspace_name="Other").json()
    headers = auth_header(owner["tokens"])
    other = auth_header(stranger["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    created = _schedule(client, headers, brand_id, variant_id, channel["id"])
    assert created.status_code == 201
    pub_id = created.json()["id"]
    assert client.get(f"/api/v1/brands/{brand_id}/publications").status_code == 401
    assert (
        client.post(
            f"/api/v1/brands/{brand_id}/publications",
            json={"variant_id": variant_id, "channel_account_id": channel["id"]},
        ).status_code
        == 401
    )
    assert client.post(f"/api/v1/publications/{pub_id}/cancel").status_code == 401
    assert client.post(f"/api/v1/publications/{pub_id}/retry").status_code == 401
    assert (
        client.post(
            f"/api/v1/publications/{pub_id}/mark-manual",
            json={"external_url": "https://example.com"},
        ).status_code
        == 401
    )
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=other)
    assert listed.status_code == 404
    cancel = client.post(f"/api/v1/publications/{pub_id}/cancel", headers=other)
    assert cancel.status_code == 404
    retry = client.post(f"/api/v1/publications/{pub_id}/retry", headers=other)
    assert retry.status_code == 404
    manual = client.post(
        f"/api/v1/publications/{pub_id}/mark-manual",
        json={"external_url": "https://example.com"},
        headers=other,
    )
    assert manual.status_code == 404


def test_viewer_cannot_schedule_or_cancel(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    viewer_user = register_user(client, email="viewer@example.com", workspace_name="Skip").json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_telegram(client, headers, brand_id)
    variant_id = _variant(client, headers, brand_id)
    created = _schedule(client, headers, brand_id, variant_id, channel["id"])
    assert created.status_code == 201
    owner_row = db.query(User).filter(User.email == "owner@example.com").one()
    viewer_row = db.query(User).filter(User.email == "viewer@example.com").one()
    owner_membership = (
        db.query(Membership)
        .filter(Membership.user_id == owner_row.id, Membership.role == MembershipRole.owner)
        .one()
    )
    db.add(
        Membership(
            workspace_id=owner_membership.workspace_id,
            user_id=viewer_row.id,
            role=MembershipRole.viewer,
        )
    )
    db.commit()
    viewer = auth_header(viewer_user["tokens"])
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=viewer)
    assert listed.status_code == 200
    denied = _schedule(client, viewer, brand_id, variant_id, channel["id"])
    assert denied.status_code == 403
    cancel = client.post(
        f"/api/v1/publications/{created.json()['id']}/cancel",
        headers=viewer,
    )
    assert cancel.status_code == 403


def test_telegram_url_pinned_rejects_ssrf_payloads() -> None:
    token = "123:ABC-TOKEN"
    url = build_telegram_url(token, "sendMessage")
    assert url == f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    assert url.startswith("https://api.telegram.org/bot")
    with pytest.raises(AdapterError) as method_exc:
        build_telegram_url(token, "http://127.0.0.1/steal")
    assert method_exc.value.code == "bad_request"
    for bad in (
        "https://evil.example/x",
        "x@127.0.0.1",
        "abc/../sendMessage",
        "123:tok?host=evil",
        "123:tok#frag",
        "123:tok tok",
    ):
        with pytest.raises(AdapterError) as token_exc:
            build_telegram_url(bad, "sendMessage")
        assert token_exc.value.code == "unauthorized"


def test_telegram_http_client_disables_redirects_and_env_proxy() -> None:
    with telegram_http_client() as client:
        assert client.follow_redirects is False
        assert client.trust_env is False


def test_telegram_http_client_omits_proxy_when_unset(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "")
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", FakeClient)
    with telegram_http_client():
        pass
    assert len(captured) == 1
    assert "proxy" not in captured[0]
    assert captured[0]["trust_env"] is False
    assert captured[0]["follow_redirects"] is False


def test_telegram_http_client_uses_proxy_when_set(monkeypatch) -> None:
    proxy = "http://127.0.0.1:7890"
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", proxy)
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", FakeClient)
    with telegram_http_client():
        pass
    assert captured[0]["proxy"] == proxy
    assert captured[0]["trust_env"] is False


def test_telegram_http_client_uses_proxy_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "http://127.0.0.1:12335")
    get_settings.cache_clear()
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", FakeClient)
    try:
        with telegram_http_client():
            pass
        assert captured[0]["proxy"] == "http://127.0.0.1:12335"
        assert captured[0]["trust_env"] is False
        assert captured[0]["follow_redirects"] is False
    finally:
        monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "")
        get_settings.cache_clear()


def test_http_loopback_as_socks5h() -> None:
    assert http_loopback_as_socks5h("http://127.0.0.1:12335") == "socks5h://127.0.0.1:12335"
    assert http_loopback_as_socks5h("http://user:s3cret@127.0.0.1:12335") == "socks5h://user:s3cret@127.0.0.1:12335"
    assert http_loopback_as_socks5h("socks5://127.0.0.1:12335") is None
    assert http_loopback_as_socks5h("http://proxy.example.com:8080") is None


def test_telegram_api_retries_loopback_http_as_socks5h(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "http://127.0.0.1:12335")
    monkeypatch.delenv("TELEGRAM_HTTPS_PROXY", raising=False)
    calls: list[str | None] = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"id": 1, "is_bot": True, "username": "x"}}

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs.get("proxy"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            if len(calls) == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return FakeResp()

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", Client)
    result = telegram_api("123:tokentok", "getMe", {})
    assert result["is_bot"] is True
    assert calls == ["http://127.0.0.1:12335", "socks5h://127.0.0.1:12335"]


def test_health_reason_proxy_http_on_socks(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "http://127.0.0.1:12335")
    text = _health_reason(AdapterError("adapter_error", "proxy_http_on_socks", retryable=True))
    assert "SOCKS5" in text
    assert "via=proxy" in text
    assert "socks5h://" in text


def test_telegram_http_client_passes_socks5_proxy_kwarg(monkeypatch) -> None:
    proxy = "socks5://127.0.0.1:1080"
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", proxy)
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", FakeClient)
    with telegram_http_client():
        pass
    assert captured[0]["proxy"] == proxy
    assert "proxy" in captured[0]


def test_telegram_http_client_blank_proxy_is_direct(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "   ")
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", FakeClient)
    with telegram_http_client():
        pass
    assert "proxy" not in captured[0]


def test_telegram_health_reason_via_direct_or_proxy_redacts_creds(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "")
    direct = _health_reason(AdapterError("adapter_error", "Telegram network error"))
    assert "via=direct" in direct
    assert "http://" not in direct
    creds_proxy = "http://user:s3cret@127.0.0.1:7890"
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", creds_proxy)
    proxied = _health_reason(AdapterError("adapter_error", "Telegram network error"))
    assert "via=proxy" in proxied
    assert "s3cret" not in proxied
    assert creds_proxy not in proxied
    assert "user:s3cret" not in proxied
    redacted = redact_proxy_url(creds_proxy)
    assert "s3cret" not in redacted
    assert redacted.startswith("http://***@127.0.0.1:7890")


def test_telegram_http_error_log_has_via_without_proxy_url(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        get_settings(),
        "telegram_https_proxy",
        "http://user:s3cret@127.0.0.1:7890",
    )

    class BoomClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("fail")

    monkeypatch.setattr("app.services.adapters.telegram.httpx.Client", BoomClient)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(AdapterError) as exc:
            telegram_api("123:tokentok", "getMe", {})
    assert exc.value.code == "adapter_error"
    text = caplog.text
    assert "via=proxy" in text
    assert "s3cret" not in text
    assert "127.0.0.1:7890" not in text
    assert "s3cret" not in exc.value.message


def test_telegram_error_description_redacts_bot_token() -> None:
    token = "123:SECRET-BOT-TOKEN"
    response = SimpleNamespace(
        status_code=401,
        json=lambda: {
            "ok": False,
            "error_code": 401,
            "description": f"Unauthorized: bot {token} invalid",
        },
    )
    with pytest.raises(AdapterError) as exc:
        telegram_result_or_raise(response, token)
    assert exc.value.code == "unauthorized"
    assert token not in exc.value.message
    assert "SECRET-BOT-TOKEN" not in exc.value.message
    assert exc.value.__cause__ is None


def _connect_wordpress(client: TestClient, headers: dict, brand_id: str) -> dict:
    created = client.post(
        f"/api/v1/brands/{brand_id}/channels/wordpress/credentials",
        json={
            "pdn_consent": True,
            "site_url": "https://blog.example",
            "username": "admin",
            "app_password": "wp-app-pass",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _connect_gmail(client: TestClient, headers: dict, brand_id: str, password: str = "gmail-app-pass") -> dict:
    created = client.post(
        f"/api/v1/brands/{brand_id}/channels/gmail/credentials",
        json={
            "pdn_consent": True,
            "from_email": "me@gmail.com",
            "app_password": password,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _typed_variant(
    client: TestClient,
    headers: dict,
    brand_id: str,
    piece_type: str,
    channel_type: str,
) -> str:
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": piece_type},
        headers=headers,
    )
    assert piece.status_code == 201
    generated = client.post(
        f"/api/v1/content/{piece.json()['id']}/generate",
        json={"variant_label": "A", "channel_type": channel_type},
        headers=headers,
    )
    assert generated.status_code == 202
    return client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers
    ).json()["result"]["variant_id"]


def test_ac14_wordpress_stays_manual_copy(client: TestClient, db: Session, monkeypatch) -> None:
    wp_calls: list[dict] = []
    monkeypatch.setattr(
        "app.services.adapters.wordpress.wordpress_create_post",
        lambda *args, **kwargs: wp_calls.append({"args": args, "kwargs": kwargs}),
    )
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_wordpress(client, headers, brand_id)
    variant_id = _typed_variant(client, headers, brand_id, "article", "wordpress")
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="ac14-wp",
    )
    assert created.status_code == 201
    run_publish_due(db, now=now)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.scheduled
    assert row.external_id is None
    assert len(wp_calls) == 0
    marked = client.post(
        f"/api/v1/publications/{created.json()['id']}/mark-manual",
        json={"external_url": "https://blog.example/p/manual"},
        headers=headers,
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "published_manual"
    assert marked.json()["external_url"] == "https://blog.example/p/manual"
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "published_manual"
    assert "wp-app-pass" not in listed.text


def test_ac23_gmail_mocked_smtp(client: TestClient, db: Session, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    password = "gmail-app-pass-SECRET"
    calls = install_gmail_mock(monkeypatch)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_gmail(client, headers, brand_id, password=password)
    added = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "self@example.com", "name": "Me"},
        headers=headers,
    )
    assert added.status_code == 201
    skipped = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "skip@example.com", "name": "Skip"},
        headers=headers,
    )
    assert skipped.status_code == 201
    client.patch(
        f"/api/v1/recipients/{skipped.json()['id']}",
        json={"status": "unsubscribed"},
        headers=headers,
    )
    variant_id = _typed_variant(client, headers, brand_id, "email", "gmail")
    now = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=now.isoformat(),
        idempotency_key="ac23-gmail",
    )
    assert created.status_code == 201
    run_publish_due(db, now=now)
    db.commit()
    db.expire_all()
    row = db.get(Publication, UUID(created.json()["id"]))
    assert row is not None
    assert row.status is PublicationStatus.published
    assert row.external_id
    assert (row.meta or {}).get("sent_count", 0) >= 1
    assert (row.meta or {}).get("failed_count", 0) == 0
    assert len(calls) == 1
    assert calls[0]["from_email"] == "me@gmail.com"
    assert calls[0]["to_email"] == "self@example.com"
    listed = client.get(f"/api/v1/brands/{brand_id}/publications", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["meta"]["sent_count"] >= 1
    channels = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers)
    assert channels.status_code == 200
    assert password not in channels.text
    assert password not in listed.text
    assert password not in caplog.text


def test_gmail_quota_no_retry_storm(client: TestClient, db: Session, monkeypatch) -> None:
    install_gmail_mock(monkeypatch, quota_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect_gmail(client, headers, brand_id)
    added = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "self@example.com"},
        headers=headers,
    )
    assert added.status_code == 201
    variant_id = _typed_variant(client, headers, brand_id, "email", "gmail")
    t0 = utc_now()
    created = _schedule(
        client,
        headers,
        brand_id,
        variant_id,
        channel["id"],
        scheduled_at=t0.isoformat(),
    )
    run_publish_due(db, now=t0)
    db.commit()
    db.expire_all()
    pub_id = UUID(created.json()["id"])
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.error_code == "rate_limited"
    assert row.attempt_count == 1
    run_publish_due(db, now=t0 + timedelta(minutes=20))
    db.commit()
    db.expire_all()
    row = db.get(Publication, pub_id)
    assert row is not None
    assert row.status is PublicationStatus.failed
    assert row.attempt_count == 1


def test_manual_copy_channels_capability_error() -> None:
    for channel_type in (ChannelType.instagram, ChannelType.wordpress):
        adapter = get_adapter(channel_type)
        assert isinstance(adapter, ManualCopyAdapter)
        assert adapter.supports_autopost is False
        with pytest.raises(AdapterCapabilityError) as exc:
            adapter.publish(None, None, None, None)  # type: ignore[arg-type]
        assert exc.value.code == "manual_copy_required"
        assert exc.value.retryable is False
    vk = get_adapter(ChannelType.vk)
    assert isinstance(vk, VkAdapter)
    assert vk.supports_autopost is True
    assert get_adapter(ChannelType.gmail).supports_autopost is True


def test_vk_wall_url_and_empty_variant_text() -> None:
    assert wall_url("1", 2) == "https://vk.com/wall-1_2"
    assert variant_text({"text": "  "}) == ""
    assert variant_text({"text": "hi", "cta": "go"}) == "hi\n\ngo"


def test_vk_result_maps_flood_and_auth(monkeypatch) -> None:
    token = "vk-secret-TOKEN"

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    with pytest.raises(AdapterError) as flood:
        vk_result_or_raise(
            FakeResponse(200, {"error": {"error_code": 9, "error_msg": "Flood control: " + token}}),
            token,
        )
    assert flood.value.code == "rate_limited"
    assert flood.value.retryable is True
    assert token not in flood.value.message

    with pytest.raises(AdapterError) as auth:
        vk_result_or_raise(
            FakeResponse(200, {"error": {"error_code": 15, "error_msg": "Access denied: " + token}}),
            token,
        )
    assert auth.value.code == "unauthorized"
    assert auth.value.retryable is False
    assert token not in auth.value.message

    with pytest.raises(AdapterError) as captcha:
        vk_result_or_raise(
            FakeResponse(200, {"error": {"error_code": 14, "error_msg": "Captcha needed"}}),
            token,
        )
    assert captcha.value.code == "rate_limited"
    assert captcha.value.retryable is True


def test_wordpress_url_pinned_rejects_ssrf_payloads() -> None:
    url = build_wordpress_posts_url("https://blog.example")
    assert url == "https://blog.example/wp-json/wp/v2/posts"
    nested = build_wordpress_posts_url("https://blog.example/subdir/")
    assert nested == "https://blog.example/subdir/wp-json/wp/v2/posts"
    with wordpress_http_client() as client:
        assert client.follow_redirects is False
        assert client.trust_env is False
    for bad in (
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:pass@blog.example",
        "https://blog.example?next=http://evil",
        "https://blog.example#x",
        "https://blog.example/\nHost: evil",
        "https://blog.example/\r\n",
        "",
    ):
        with pytest.raises(AdapterError) as exc:
            build_wordpress_posts_url(bad)
        assert exc.value.code == "bad_request"


def test_gmail_quota_error_not_mailbox_550() -> None:
    quota = smtplib.SMTPDataError(550, b"5.4.5 Daily sending quota exceeded")
    mapped = smtp_error_to_adapter(quota, "secret-pass")
    assert mapped.code == "rate_limited"
    assert mapped.retryable is False
    assert "secret-pass" not in mapped.message
    assert is_quota_error(quota) is True
    mailbox = smtplib.SMTPDataError(550, b"5.1.1 User unknown")
    assert is_quota_error(mailbox) is False
    other = smtp_error_to_adapter(mailbox, "secret-pass")
    assert other.code == "adapter_error"
    assert other.retryable is False
    assert "secret-pass" not in other.message
    auth = smtp_error_to_adapter(smtplib.SMTPAuthenticationError(535, b"bad"), "secret-pass")
    assert auth.code == "unauthorized"
    assert auth.retryable is False


def test_gmail_smtp_error_redacts_spaced_app_password() -> None:
    secret = "abcd efgh ijkl"
    mapped = smtp_error_to_adapter(
        smtplib.SMTPDataError(450, b"temp fail abcdefghijkl"),
        secret,
    )
    assert mapped.code == "adapter_error"
    assert "abcdefghijkl" not in mapped.message
    assert secret not in mapped.message
    assert "***" in mapped.message


def test_gmail_unexpected_smtp_error_no_password_in_logs(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    password = "gmail-app-pass-SECRET"

    def boom(*_args, **_kwargs):
        raise RuntimeError(f"login failed {password}")

    monkeypatch.setattr("smtplib.SMTP", boom)
    msg = EmailMessage()
    msg["Subject"] = "x"
    msg["From"] = "a@b.c"
    msg["To"] = "d@e.f"
    msg.set_content("hi")
    with pytest.raises(AdapterError) as exc:
        smtp_send_one("a@b.c", password, "d@e.f", msg)
    assert exc.value.code == "adapter_error"
    assert exc.value.__cause__ is None
    assert password not in exc.value.message
    assert password not in caplog.text


def test_wordpress_error_redacts_spaced_app_password() -> None:
    secret = "abcd efgh ijkl"
    response = SimpleNamespace(
        status_code=401,
        json=lambda: {"message": "invalid abcdefghijkl"},
    )
    with pytest.raises(AdapterError) as exc:
        wordpress_result_or_raise(response, secret)
    assert exc.value.code == "unauthorized"
    assert "abcdefghijkl" not in exc.value.message
    assert secret not in exc.value.message


def test_wordpress_unexpected_http_error_no_password_in_logs(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    password = "wp-app-pass-SECRET"

    class BoomClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            raise RuntimeError(f"connect failed {password}")

    monkeypatch.setattr(
        "app.services.adapters.wordpress.wordpress_http_client",
        lambda: BoomClient(),
    )
    with pytest.raises(AdapterError) as exc:
        wordpress_create_post("https://blog.example", "admin", password, {"title": "t"})
    assert exc.value.code == "adapter_error"
    assert exc.value.__cause__ is None
    assert password not in exc.value.message
    assert password not in caplog.text
