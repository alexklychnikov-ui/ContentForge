from uuid import uuid4

from fastapi.testclient import TestClient

from tests.helpers import BRAND_PAYLOAD, add_editor, auth_header, create_brand, register_user


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def test_ac03_foreign_brand_id_is_not_found(client: TestClient) -> None:
    owner = register_user(client).json()
    created = create_brand(client, auth_header(owner["tokens"]))
    assert created.status_code == 201
    brand_id = created.json()["id"]
    assert created.json()["onboarding_completed"] is True
    assert "password" not in created.json()
    assert "access_token" not in created.json()
    assert "refresh_token" not in created.json()
    assert "password_hash" not in created.json()

    stranger = register_user(client, email="other@example.com", workspace_name="Other").json()
    headers = auth_header(stranger["tokens"])
    leaked = client.get(f"/api/v1/brands/{brand_id}", headers=headers)
    assert leaked.status_code in {403, 404}
    error = _error(leaked)
    assert error["code"] in {"forbidden", "not_found"}
    assert brand_id not in leaked.text or error["code"] in {"forbidden", "not_found"}
    assert "NODEX" not in leaked.text
    assert "маркетологи" not in leaked.text

    listed = client.get("/api/v1/brands", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []

    patched = client.patch(
        f"/api/v1/brands/{brand_id}",
        json={"name": "Hacked"},
        headers=headers,
    )
    assert patched.status_code in {403, 404}
    assert "Hacked" not in patched.text


def test_unknown_brand_id_same_as_foreign(client: TestClient) -> None:
    owner = register_user(client).json()
    missing = client.get(f"/api/v1/brands/{uuid4()}", headers=auth_header(owner["tokens"]))
    assert missing.status_code == 404
    assert _error(missing)["code"] == "not_found"


def test_delete_brand_owner_only(client: TestClient, db) -> None:
    owner = register_user(client).json()
    editor_user = register_user(client, email="editor@example.com", workspace_name="Editor WS").json()
    brand = create_brand(client, auth_header(owner["tokens"]))
    brand_id = brand.json()["id"]
    add_editor(db, "owner@example.com", "editor@example.com")
    denied = client.delete(
        f"/api/v1/brands/{brand_id}",
        headers=auth_header(editor_user["tokens"]),
    )
    assert denied.status_code == 403
    assert _error(denied)["code"] == "forbidden"
    removed = client.delete(
        f"/api/v1/brands/{brand_id}",
        headers=auth_header(owner["tokens"]),
    )
    assert removed.status_code == 204
    gone = client.get(f"/api/v1/brands/{brand_id}", headers=auth_header(owner["tokens"]))
    assert gone.status_code == 404


def test_generate_plan_blocked_without_kit(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    draft = create_brand(client, headers, offers=[], example_posts=[])
    assert draft.status_code == 201
    assert draft.json()["onboarding_completed"] is False
    blocked = client.post(
        f"/api/v1/brands/{draft.json()['id']}/plans/generate",
        json={"year": 2026, "month": 9},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "brand_kit_incomplete"

    completed = client.patch(
        f"/api/v1/brands/{draft.json()['id']}",
        json={"offers": ["аудит"]},
        headers=headers,
    )
    assert completed.json()["onboarding_completed"] is True


def test_get_brands_does_not_leak_secrets(client: TestClient) -> None:
    owner = register_user(client).json()
    create_brand(client, auth_header(owner["tokens"]))
    listed = client.get("/api/v1/brands", headers=auth_header(owner["tokens"]))
    assert listed.status_code == 200
    raw = listed.text.lower()
    assert "password" not in raw
    assert "access_token" not in raw
    assert "refresh_token" not in raw
    assert listed.json()[0]["name"] == BRAND_PAYLOAD["name"]
