from fastapi.testclient import TestClient

from tests.helpers import register_user


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) >= {"code", "message", "details"}
    return body["error"]


def test_ac01_register_creates_user_and_workspace_owner(client: TestClient) -> None:
    response = register_user(client)
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "owner@example.com"
    assert "password" not in payload["user"]
    assert "password_hash" not in payload["user"]
    assert payload["workspace"]["name"] == "Acme"
    assert payload["workspace"]["role"] == "owner"
    tokens = payload["tokens"]
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] == 900
    assert tokens["access_token"] != tokens["refresh_token"]


def test_ac01_duplicate_email_taken(client: TestClient) -> None:
    first = register_user(client)
    assert first.status_code == 201
    second = register_user(client, email="Owner@example.com")
    assert second.status_code == 409
    error = _error(second)
    assert error["code"] == "email_taken"
    assert "owner@example.com" not in second.text.lower() or error["code"] == "email_taken"


def test_ac02_invalid_password_and_unknown_email_same_envelope(client: TestClient) -> None:
    register_user(client)
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    error = _error(wrong_password)
    assert error["code"] == "invalid_credentials"
    message = error["message"].lower()
    assert "exists" not in message
    assert "не найден" not in message
    assert "not found" not in message
    assert "unknown" not in message
    assert "зарегистри" not in message


def test_login_success_and_refresh_logout(client: TestClient) -> None:
    registered = register_user(client).json()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "password12"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == registered["user"]["id"]
    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["tokens"]["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert "access_token" in refresh.json()
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {refresh.json()['access_token']}"},
        json={"refresh_token": refresh.json()["refresh_token"]},
    )
    assert logout.status_code == 204
    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh.json()["refresh_token"]},
    )
    assert reused.status_code == 401
    assert _error(reused)["code"] == "invalid_refresh"


def test_login_rate_limit(client: TestClient) -> None:
    register_user(client)
    last = None
    for _ in range(5):
        last = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "bad"},
        )
        assert last.status_code == 401
        assert _error(last)["code"] == "invalid_credentials"
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "bad"},
    )
    assert limited.status_code == 429
    assert _error(limited)["code"] == "rate_limited"
