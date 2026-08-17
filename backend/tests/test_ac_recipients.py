from fastapi.testclient import TestClient

from tests.helpers import auth_header, create_brand, register_user


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def test_recipient_unique_lowercase_and_crud(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    created = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "Owner@Example.com", "name": "Owner"},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "owner@example.com"
    assert body["status"] == "active"
    assert body["source"] == "manual"
    duplicate = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "owner@example.com"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert _error(duplicate)["code"] == "recipient_exists"
    listed = client.get(f"/api/v1/brands/{brand_id}/recipients", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    recipient_id = body["id"]
    patched = client.patch(
        f"/api/v1/recipients/{recipient_id}",
        json={"status": "unsubscribed", "name": "Was owner"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "unsubscribed"
    assert patched.json()["name"] == "Was owner"
    deleted = client.delete(f"/api/v1/recipients/{recipient_id}", headers=headers)
    assert deleted.status_code == 204
    empty = client.get(f"/api/v1/brands/{brand_id}/recipients", headers=headers)
    assert empty.json() == []


def test_foreign_recipient_is_not_found(client: TestClient) -> None:
    owner = register_user(client).json()
    stranger = register_user(client, email="x@example.com", workspace_name="X").json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    recipient_id = client.post(
        f"/api/v1/brands/{brand_id}/recipients",
        json={"email": "a@example.com"},
        headers=headers,
    ).json()["id"]
    denied = client.patch(
        f"/api/v1/recipients/{recipient_id}",
        json={"status": "unsubscribed"},
        headers=auth_header(stranger["tokens"]),
    )
    assert denied.status_code == 404
    assert _error(denied)["code"] == "not_found"
