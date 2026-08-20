from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import ENV_FILE, get_settings
from app.models import ChannelAccount, ChannelStatus
from app.services.adapters.base import AdapterError
from app.services.token_crypto import (
    TokenEncryptionError,
    decrypt_secret,
    encrypt_secret,
    get_fernet,
)
from tests.helpers import auth_header, create_brand, register_user
from tests.openai_mock import install_openai_mock
from tests.telegram_mock import install_telegram_mock, unauthorized_handler

SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "bot_token",
    "app_password",
    "password",
    "password_hash",
    "token_ciphertext",
    "refresh_ciphertext",
}


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch) -> None:
    install_openai_mock(monkeypatch)


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def _assert_no_secrets(payload) -> None:
    if isinstance(payload, dict):
        lowered = {str(key).lower() for key in payload}
        assert lowered.isdisjoint(SECRET_KEYS)
        for value in payload.values():
            _assert_no_secrets(value)
        return
    if isinstance(payload, list):
        for item in payload:
            _assert_no_secrets(item)


def _connect(client: TestClient, headers: dict, brand_id: str, channel_type: str, body: dict):
    return client.post(
        f"/api/v1/brands/{brand_id}/channels/{channel_type}/credentials",
        json=body,
        headers=headers,
    )


def test_ac18_get_channels_has_no_token_fields(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    created = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "display_name": "NODEX TG",
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    )
    assert created.status_code == 201
    body = created.json()
    _assert_no_secrets(body)
    assert "123:SECRET-BOT-TOKEN" not in str(body)
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    _assert_no_secrets(rows)
    assert rows[0]["status"] == "connected"
    assert rows[0]["type"] == "telegram"
    assert "123:SECRET-BOT-TOKEN" not in str(rows)
    stored = db.get(ChannelAccount, UUID(rows[0]["id"]))
    assert stored is not None
    assert stored.token_ciphertext
    assert stored.token_ciphertext != "123:SECRET-BOT-TOKEN"
    assert "SECRET-BOT-TOKEN" not in stored.token_ciphertext


def test_pdn_consent_required(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    denied = _connect(
        client,
        headers,
        brand_id,
        "gmail",
        {
            "pdn_consent": False,
            "from_email": "me@gmail.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )
    assert denied.status_code == 400
    assert _error(denied)["code"] == "pdn_consent_required"


def test_credentials_all_types_and_health_stub(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    payloads = {
        "telegram": {"pdn_consent": True, "bot_token": "123:tg-token-value", "channel_id": "-1001"},
        "wordpress": {
            "pdn_consent": True,
            "site_url": "https://blog.example",
            "username": "admin",
            "app_password": "wp-app-pass",
        },
        "gmail": {
            "pdn_consent": True,
            "from_email": "Owner@Gmail.com",
            "app_password": "gmail-app-pass",
        },
        "vk": {"pdn_consent": True, "access_token": "vk-community-token", "group_id": "1"},
        "instagram": {
            "pdn_consent": True,
            "access_token": "ig-token",
            "ig_user_id": "1784",
            "refresh_token": "ig-refresh",
        },
    }
    ids = []
    for channel_type, body in payloads.items():
        response = _connect(client, headers, brand_id, channel_type, body)
        assert response.status_code == 201, response.text
        _assert_no_secrets(response.json())
        ids.append(response.json()["id"])
    health = client.post(f"/api/v1/channels/{ids[0]}/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["status"] == "connected"
    assert health.json()["ok"] is True


def test_health_error_without_ciphertext_and_revoke(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    created = _connect(
        client,
        headers,
        brand_id,
        "vk",
        {"pdn_consent": True, "access_token": "vk-secret"},
    )
    channel_id = created.json()["id"]
    row = db.get(ChannelAccount, UUID(channel_id))
    assert row is not None
    row.token_ciphertext = None
    db.commit()
    health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["status"] == "error"
    assert health.json()["ok"] is False
    revoked = client.delete(f"/api/v1/channels/{channel_id}", headers=headers)
    assert revoked.status_code == 204
    db.expire_all()
    row = db.get(ChannelAccount, UUID(channel_id))
    assert row is not None
    assert row.token_ciphertext is None
    assert row.refresh_ciphertext is None
    assert row.status.value == "revoked"
    assert row.revoked_at is not None
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    _assert_no_secrets(listed)
    assert listed == []


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = "smtp-app-password-value"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert "smtp-app-password-value" not in ciphertext
    assert decrypt_secret(ciphertext) == plaintext


def test_missing_token_encryption_key_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    get_fernet.cache_clear()
    try:
        with pytest.raises(TokenEncryptionError, match="TOKEN_ENCRYPTION_KEY"):
            get_fernet()
    finally:
        get_settings.cache_clear()
        get_fernet.cache_clear()


def test_invalid_token_encryption_key_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    get_settings.cache_clear()
    get_fernet.cache_clear()
    try:
        with pytest.raises(TokenEncryptionError, match="invalid"):
            get_fernet()
    finally:
        get_settings.cache_clear()
        get_fernet.cache_clear()


def test_ac22_gmail_no_recipients_409(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel = _connect(
        client,
        headers,
        brand_id,
        "gmail",
        {
            "pdn_consent": True,
            "from_email": "me@gmail.com",
            "app_password": "gmail-app-pass",
        },
    ).json()
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "email"},
        headers=headers,
    ).json()
    generated = client.post(
        f"/api/v1/content/{piece['id']}/generate",
        json={"variant_label": "A", "channel_type": "gmail"},
        headers=headers,
    )
    assert generated.status_code == 202
    variant_id = client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers
    ).json()["result"]["variant_id"]
    blocked = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={"variant_id": variant_id, "channel_account_id": channel["id"]},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "no_recipients"
    added = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "Self@example.com", "name": "Me"},
        headers=headers,
    )
    assert added.status_code == 201
    assert added.json()["email"] == "self@example.com"
    allowed = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={"variant_id": variant_id, "channel_account_id": channel["id"]},
        headers=headers,
    )
    assert allowed.status_code == 201
    assert allowed.json()["status"] == "scheduled"


def test_foreign_channel_is_not_found(client: TestClient) -> None:
    owner = register_user(client).json()
    stranger = register_user(client, email="other@example.com", workspace_name="Other").json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {"pdn_consent": True, "bot_token": "123:t-token-value", "channel_id": "-1001"},
    ).json()["id"]
    missing = client.get(
        f"/api/v1/brands/{brand_id}/channels",
        headers=auth_header(stranger["tokens"]),
    )
    assert missing.status_code == 404
    health = client.post(
        f"/api/v1/channels/{channel_id}/health",
        headers=auth_header(stranger["tokens"]),
    )
    assert health.status_code == 404
    unknown = client.post(
        f"/api/v1/channels/{uuid4()}/health",
        headers=headers,
    )
    assert unknown.status_code == 404
    assert health.json() == unknown.json()


def test_telegram_channel_id_rejects_email(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    denied = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "alexandr_klychnikov@mail.ru",
        },
    )
    assert denied.status_code == 422
    err = _error(denied)
    assert err["code"] == "validation_error"
    assert "нужен @channel" in err["message"]


def test_telegram_channel_id_rejects_bot_user_id(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    denied = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "5477113632",
        },
    )
    assert denied.status_code == 422
    err = _error(denied)
    assert "user/bot id" in err["message"]


def test_telegram_channel_id_accepts_regular_group(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    created = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-5477113632",
        },
    )
    assert created.status_code == 201
    assert created.json()["meta"]["channel_id"] == "-5477113632"


def test_telegram_channel_id_accepts_at_username(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    created = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "@nodex_channel",
        },
    )
    assert created.status_code == 201
    assert created.json()["meta"]["channel_id"] == "@nodex_channel"


def test_telegram_bot_token_rejects_placeholder(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    denied = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {"pdn_consent": True, "bot_token": "testtoken", "channel_id": "@nodex_channel"},
    )
    assert denied.status_code == 422
    assert _error(denied)["code"] == "validation_error"


def test_telegram_health_unauthorized_sets_error_reason(
    client: TestClient, monkeypatch
) -> None:
    install_telegram_mock(monkeypatch, unauthorized_handler)
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    ).json()["id"]
    health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "error"
    assert body["ok"] is False
    assert "getMe" in (body.get("reason") or "")
    assert "via=direct" in (body.get("reason") or "")
    assert "http://" not in (body.get("reason") or "")
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    assert listed[0]["status"] == "error"
    assert "getMe" in str(listed[0]["meta"].get("health_reason") or "")
    assert "via=direct" in str(listed[0]["meta"].get("health_reason") or "")
    _assert_no_secrets(listed)
    _assert_no_secrets(body)


def test_telegram_health_decrypt_fail_is_error_not_500(
    client: TestClient, monkeypatch
) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    ).json()["id"]

    def boom(_ciphertext: str) -> str:
        raise TokenEncryptionError("ciphertext is invalid")

    monkeypatch.setattr("app.services.adapters.telegram.decrypt_secret", boom)
    health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "error"
    assert body["ok"] is False
    assert "расшифровать" in (body.get("reason") or "")
    assert "via=" not in (body.get("reason") or "")
    _assert_no_secrets(body)


def test_telegram_health_ok_reason_via_proxy_redacts_url(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        get_settings(),
        "telegram_https_proxy",
        "http://user:s3cret@127.0.0.1:7890",
    )
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    ).json()["id"]
    health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert health.status_code == 200
    body = health.json()
    assert body["ok"] is True
    assert "via=proxy" in (body.get("reason") or "")
    assert "s3cret" not in str(body)
    assert "127.0.0.1:7890" not in str(body)
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    listed_reason = str(listed[0]["meta"].get("health_reason") or "")
    assert "via=proxy" in listed_reason
    assert "getMe" in listed_reason
    assert "s3cret" not in listed_reason
    _assert_no_secrets(body)


def test_settings_env_file_is_backend_absolute() -> None:
    assert ENV_FILE.is_absolute()
    assert ENV_FILE.name == ".env"
    assert ENV_FILE.parent.name == "backend"


def test_telegram_health_via_proxy_when_env_set(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "http://127.0.0.1:12335")
    get_settings.cache_clear()
    try:
        assert get_settings().telegram_https_proxy == "http://127.0.0.1:12335"
        owner = register_user(client).json()
        headers = auth_header(owner["tokens"])
        brand_id = create_brand(client, headers).json()["id"]
        channel_id = _connect(
            client,
            headers,
            brand_id,
            "telegram",
            {
                "pdn_consent": True,
                "bot_token": "123:SECRET-BOT-TOKEN",
                "channel_id": "-100123",
            },
        ).json()["id"]
        health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
        assert health.status_code == 200
        body = health.json()
        assert body["ok"] is True
        assert "via=proxy" in (body.get("reason") or "")
        assert "via=direct" not in (body.get("reason") or "")
        listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
        listed_reason = str(listed[0]["meta"].get("health_reason") or "")
        assert "via=proxy" in listed_reason
        assert "getMe" in listed_reason
        _assert_no_secrets(body)
    finally:
        monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "")
        get_settings.cache_clear()


def test_telegram_health_network_error_via_proxy_when_env_set(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "http://127.0.0.1:12335")
    get_settings.cache_clear()

    def network_fail(_token, _method, _data, _files):
        raise AdapterError("adapter_error", "Telegram network error", retryable=True)

    try:
        install_telegram_mock(monkeypatch, network_fail)
        assert get_settings().telegram_https_proxy == "http://127.0.0.1:12335"
        owner = register_user(client).json()
        headers = auth_header(owner["tokens"])
        brand_id = create_brand(client, headers).json()["id"]
        channel_id = _connect(
            client,
            headers,
            brand_id,
            "telegram",
            {
                "pdn_consent": True,
                "bot_token": "123:SECRET-BOT-TOKEN",
                "channel_id": "-100123",
            },
        ).json()["id"]
        health = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
        assert health.status_code == 200
        body = health.json()
        assert body["ok"] is False
        reason = body.get("reason") or ""
        assert "api.telegram.org" in reason
        assert "via=proxy" in reason
        assert "via=direct" not in reason
        listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
        listed_reason = str(listed[0]["meta"].get("health_reason") or "")
        assert "via=proxy" in listed_reason
        assert "via=direct" not in listed_reason
        _assert_no_secrets(body)
    finally:
        monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "")
        get_settings.cache_clear()


def test_telegram_health_overwrites_stale_via_direct_when_proxy_set(
    client: TestClient, monkeypatch
) -> None:
    def network_fail(_token, _method, _data, _files):
        raise AdapterError("adapter_error", "Telegram network error", retryable=True)

    install_telegram_mock(monkeypatch, network_fail)
    monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "")
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "")
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    ).json()["id"]
    first = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert first.status_code == 200
    assert "via=direct" in (first.json().get("reason") or "")
    stale = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    assert "via=direct" in str(stale[0]["meta"].get("health_reason") or "")

    monkeypatch.setenv("TELEGRAM_HTTPS_PROXY", "http://127.0.0.1:12335")
    monkeypatch.setattr(get_settings(), "telegram_https_proxy", "http://127.0.0.1:12335")
    second = client.post(f"/api/v1/channels/{channel_id}/health", headers=headers)
    assert second.status_code == 200
    body = second.json()
    assert body["ok"] is False
    reason = body.get("reason") or ""
    assert "via=proxy" in reason
    assert "via=direct" not in reason
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    listed_reason = str(listed[0]["meta"].get("health_reason") or "")
    assert "via=proxy" in listed_reason
    assert "via=direct" not in listed_reason
    _assert_no_secrets(body)


def test_revoked_channel_excluded_from_list_even_if_status_error(
    client: TestClient, db: Session
) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    channel_id = _connect(
        client,
        headers,
        brand_id,
        "telegram",
        {
            "pdn_consent": True,
            "bot_token": "123:SECRET-BOT-TOKEN",
            "channel_id": "-100123",
        },
    ).json()["id"]
    live = _connect(
        client,
        headers,
        brand_id,
        "vk",
        {"pdn_consent": True, "access_token": "vk-secret"},
    ).json()["id"]
    revoked = client.delete(f"/api/v1/channels/{channel_id}", headers=headers)
    assert revoked.status_code == 204
    row = db.get(ChannelAccount, UUID(channel_id))
    assert row is not None
    row.status = ChannelStatus.error
    db.commit()
    listed = client.get(f"/api/v1/brands/{brand_id}/channels", headers=headers).json()
    ids = {item["id"] for item in listed}
    assert channel_id not in ids
    assert live in ids
    assert all(item["status"] != "revoked" for item in listed)
    assert all(item.get("revoked_at") is None for item in listed)
    _assert_no_secrets(listed)
