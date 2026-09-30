from fastapi.testclient import TestClient

from tests.helpers import auth_header, create_brand, register_user


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def test_get_content_profile_lazy_creates_empty(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]

    response = client.get(f"/api/v1/brands/{brand_id}/content-profile", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["brand_id"] == brand_id
    assert body["positioning"] == ""
    assert body["audience_segments"] == []
    assert body["audience_pains"] == []
    assert body["content_pillars"] == []
    assert body["proof_facts"] == []
    assert body["preferred_cta_styles"] == []
    assert body["banned_openers"] == []
    assert body["structure_rules"] == ""
    assert body["platform_policies"] == {}
    assert body["knowledge_mode"] == "off"
    assert body["knowledge_filters"] == []
    assert body["require_human_approval"] is True

    again = client.get(f"/api/v1/brands/{brand_id}/content-profile", headers=headers)
    assert again.status_code == 200
    assert again.json()["brand_id"] == brand_id


def test_patch_content_profile_updates_fields(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]

    patched = client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={
            "positioning": "Python/AI",
            "audience_segments": ["МСБ"],
            "knowledge_mode": "optional",
            "require_human_approval": False,
        },
        headers=headers,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["positioning"] == "Python/AI"
    assert body["audience_segments"] == ["МСБ"]
    assert body["knowledge_mode"] == "optional"
    assert body["require_human_approval"] is False


def test_apply_alexander_personal_preset(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]

    applied = client.post(
        f"/api/v1/brands/{brand_id}/content-profile/preset/alexander_personal",
        headers=headers,
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["knowledge_mode"] == "required"
    assert body["require_human_approval"] is True
    assert "Python/AI" in body["positioning"]
    assert "малый бизнес" in body["audience_segments"]
    assert "размытое ТЗ" in body["audience_pains"]
    assert "практика/ошибка+фикс" in body["content_pillars"]
    assert "выбор 1/2" in body["preferred_cta_styles"]
    assert "В современном мире" in body["banned_openers"]
    assert "боль → сцена" in body["structure_rules"]
    assert "tenchat" in body["platform_policies"]
    assert "hard sell" in body["platform_policies"]["tenchat"]


def test_content_profile_foreign_workspace_denied(client: TestClient) -> None:
    owner = register_user(client).json()
    brand_id = create_brand(client, auth_header(owner["tokens"])).json()["id"]

    stranger = register_user(
        client, email="other@example.com", workspace_name="Other"
    ).json()
    headers = auth_header(stranger["tokens"])

    leaked = client.get(f"/api/v1/brands/{brand_id}/content-profile", headers=headers)
    assert leaked.status_code in {403, 404}
    assert _error(leaked)["code"] in {"forbidden", "not_found"}

    patched = client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={"positioning": "hack"},
        headers=headers,
    )
    assert patched.status_code in {403, 404}

    preset = client.post(
        f"/api/v1/brands/{brand_id}/content-profile/preset/alexander_personal",
        headers=headers,
    )
    assert preset.status_code in {403, 404}
