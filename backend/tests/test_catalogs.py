from uuid import uuid4

from fastapi.testclient import TestClient

from tests.helpers import auth_header, create_brand, register_user


def test_holidays_seed_ru_current_year(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    response = client.get("/api/v1/holidays?year=2026&month=5", headers=headers)
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    dates = {item["date"] for item in response.json()}
    assert "День Победы" in names
    assert "2026-05-09" in dates
    assert all(item["source"] == "system" for item in response.json())
    assert all(item["country"] == "RU" for item in response.json())


def test_custom_holiday_and_trends(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand = create_brand(client, headers).json()
    brand_id = brand["id"]

    custom = client.post(
        f"/api/v1/brands/{brand_id}/holidays",
        json={"date": "2026-09-15", "name": "День клиента"},
        headers=headers,
    )
    assert custom.status_code == 201
    listed = client.get(
        f"/api/v1/holidays?year=2026&month=9&brand_id={brand_id}",
        headers=headers,
    )
    names = {item["name"] for item in listed.json()}
    assert "День знаний" in names
    assert "День клиента" in names

    stranger = register_user(client, email="x@example.com", workspace_name="X").json()
    foreign = client.get(
        f"/api/v1/holidays?year=2026&month=9&brand_id={brand_id}",
        headers=auth_header(stranger["tokens"]),
    )
    assert foreign.status_code in {403, 404}

    created_trend = client.post(
        f"/api/v1/brands/{brand_id}/trends",
        json={"title": "AI-рассылки", "note": "ручной сигнал"},
        headers=headers,
    )
    assert created_trend.status_code == 201
    trend_id = created_trend.json()["id"]
    trends = client.get(f"/api/v1/brands/{brand_id}/trends", headers=headers)
    assert trends.status_code == 200
    assert trends.json()[0]["status"] == "active"

    archived = client.patch(
        f"/api/v1/trends/{trend_id}",
        json={"archived": True},
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    blocked = client.get(
        f"/api/v1/brands/{brand_id}/trends",
        headers=auth_header(stranger["tokens"]),
    )
    assert blocked.status_code in {403, 404}
    assert "AI-рассылки" not in blocked.text

    stranger_headers = auth_header(stranger["tokens"])
    foreign_patch = client.patch(
        f"/api/v1/trends/{trend_id}",
        json={"archived": True},
        headers=stranger_headers,
    )
    missing_patch = client.patch(
        f"/api/v1/trends/{uuid4()}",
        json={"archived": True},
        headers=stranger_headers,
    )
    assert foreign_patch.status_code == 404
    assert missing_patch.status_code == 404
    assert foreign_patch.json() == missing_patch.json()
    assert foreign_patch.json()["error"]["code"] == "not_found"
    assert "AI-рассылки" not in foreign_patch.text
