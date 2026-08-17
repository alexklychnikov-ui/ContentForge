import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests.helpers import add_editor, auth_header, create_brand, register_user
from tests.openai_mock import install_openai_mock


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch) -> None:
    install_openai_mock(monkeypatch)


def _piece(client: TestClient, headers: dict, brand_id: str, piece_type: str = "social_post"):
    created = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": piece_type},
        headers=headers,
    )
    assert created.status_code == 201
    return created.json()


def test_ac08_generate_and_edit_variant_a(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    piece = _piece(client, headers, brand_id)
    generated = client.post(
        f"/api/v1/content/{piece['id']}/generate",
        json={"variant_label": "A", "channel_type": "telegram"},
        headers=headers,
    )
    assert generated.status_code == 202
    job = client.get(f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers).json()
    assert job["status"] == "succeeded"
    loaded = client.get(f"/api/v1/content/{piece['id']}", headers=headers).json()
    assert len(loaded["variants"]) == 1
    variant = loaded["variants"][0]
    assert variant["label"] == "A"
    assert variant["payload"]["text"]
    edited = client.patch(
        f"/api/v1/content/{piece['id']}/variants/{variant['id']}",
        json={"payload": {"text": "Отредактированный пост", "cta": "Кейс"}},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["payload"]["text"] == "Отредактированный пост"
    assert edited.json()["payload"]["cta"] == "Кейс"
    assert edited.json()["revision"] == variant["revision"] + 1


def test_ac09_stopword_blocks_schedule(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    piece = _piece(client, headers, brand_id)
    generated = client.post(
        f"/api/v1/content/{piece['id']}/generate",
        json={"variant_label": "A"},
        headers=headers,
    )
    job = client.get(f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers).json()
    variant_id = job["result"]["variant_id"]
    client.patch(
        f"/api/v1/content/{piece['id']}/variants/{variant_id}",
        json={"payload": {"text": "Даём гарантия результата"}},
        headers=headers,
    )
    blocked = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={"variant_id": variant_id, "stopword_override": False},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "stopword_violation"
    channel = client.post(
        f"/api/v1/brands/{brand_id}/channels/telegram/credentials",
        json={
            "pdn_consent": True,
            "bot_token": "123:STOPWORD-TOKEN",
            "channel_id": "-100123",
        },
        headers=headers,
    )
    assert channel.status_code == 201
    overridden = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={
            "variant_id": variant_id,
            "channel_account_id": channel.json()["id"],
            "stopword_override": True,
        },
        headers=headers,
    )
    assert overridden.status_code == 201
    assert overridden.json()["status"] == "scheduled"
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "stopword_override")).all()
    assert len(logs) == 1
    assert logs[0].data["hits"]


def test_ac09_editor_cannot_override(client: TestClient, db: Session) -> None:
    owner = register_user(client).json()
    editor_user = register_user(client, email="editor@example.com", workspace_name="Editor WS").json()
    owner_headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, owner_headers).json()["id"]
    piece = _piece(client, owner_headers, brand_id)
    generated = client.post(
        f"/api/v1/content/{piece['id']}/generate",
        json={"variant_label": "A"},
        headers=owner_headers,
    )
    variant_id = client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=owner_headers
    ).json()["result"]["variant_id"]
    client.patch(
        f"/api/v1/content/{piece['id']}/variants/{variant_id}",
        json={"payload": {"text": "гарантия"}},
        headers=owner_headers,
    )
    add_editor(db, "owner@example.com", "editor@example.com")
    denied = client.post(
        f"/api/v1/brands/{brand_id}/publications",
        json={"variant_id": variant_id, "stopword_override": True},
        headers=auth_header(editor_user["tokens"]),
    )
    assert denied.status_code == 403
    assert _error(denied)["code"] == "forbidden"


def test_ac10_rewrite_selection_isolation(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    piece = _piece(client, headers, brand_id)
    generated = client.post(
        f"/api/v1/content/{piece['id']}/generate",
        json={"variant_label": "A"},
        headers=headers,
    )
    variant_id = client.get(
        f"/api/v1/jobs/{generated.json()['job_id']}", headers=headers
    ).json()["result"]["variant_id"]
    source = "AAA BBB CCC"
    client.patch(
        f"/api/v1/content/{piece['id']}/variants/{variant_id}",
        json={"payload": {"text": source}},
        headers=headers,
    )
    rewritten = client.post(
        f"/api/v1/content/{piece['id']}/variants/{variant_id}/rewrite",
        json={"selection": {"field": "text", "start": 4, "end": 7}},
        headers=headers,
    )
    assert rewritten.status_code == 202
    job = client.get(f"/api/v1/jobs/{rewritten.json()['job_id']}", headers=headers).json()
    assert job["status"] == "succeeded"
    loaded = client.get(f"/api/v1/content/{piece['id']}", headers=headers).json()
    text = loaded["variants"][0]["payload"]["text"]
    assert text.startswith("AAA ")
    assert text.endswith(" CCC")
    assert "BBB" not in text or "NEW:BBB" in text
    assert text == "AAA NEW:BBB CCC"
