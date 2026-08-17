from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import AppError
from app.models import MediaAsset, MediaKind
from app.services.media_service import MAX_MEDIA_BYTES, media_file_path
from tests.helpers import auth_header, create_brand, register_user

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_MAGIC = b"RIFF" + (40).to_bytes(4, "little") + b"WEBP" + b"\x00" * 28


def _error(response) -> dict:
    body = response.json()
    assert "error" in body
    return body["error"]


def test_media_accepts_images_and_rejects_oversize_and_mime(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    uploaded = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("shot.png", PNG_MAGIC, "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["mime"] == "image/png"
    assert body["kind"] == "image"
    assert len(body["checksum"]) == 64
    assert body["url"].endswith("/file")
    loaded = client.get(f"/api/v1/media/{body['id']}", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["checksum"] == body["checksum"]
    jpeg = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("a.jpg", JPEG_MAGIC, "image/jpeg")},
        headers=headers,
    )
    assert jpeg.status_code == 201
    webp = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("a.webp", WEBP_MAGIC, "image/webp")},
        headers=headers,
    )
    assert webp.status_code == 201
    wrong = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("notes.txt", b"hello world not an image", "text/plain")},
        headers=headers,
    )
    assert wrong.status_code == 415
    assert _error(wrong)["code"] == "unsupported_media_type"
    huge = b"\xff\xd8\xff" + b"\x00" * (MAX_MEDIA_BYTES)
    oversize = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("big.jpg", huge, "image/jpeg")},
        headers=headers,
    )
    assert oversize.status_code == 413
    assert _error(oversize)["code"] == "file_too_large"
    fetched = client.get(f"/api/v1/media/{body['id']}/file", headers=headers)
    assert fetched.status_code == 200
    assert fetched.headers.get("x-content-type-options") == "nosniff"
    assert fetched.headers.get("content-type", "").startswith("image/png")


def test_foreign_media_is_not_found(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
    owner = register_user(client).json()
    stranger = register_user(client, email="media-other@example.com", workspace_name="Other").json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    media_id = client.post(
        f"/api/v1/brands/{brand_id}/media",
        files={"file": ("shot.png", PNG_MAGIC, "image/png")},
        headers=headers,
    ).json()["id"]
    other = auth_header(stranger["tokens"])
    meta = client.get(f"/api/v1/media/{media_id}", headers=other)
    file_get = client.get(f"/api/v1/media/{media_id}/file", headers=other)
    unknown = client.get(f"/api/v1/media/{uuid4()}", headers=headers)
    assert meta.status_code == 404
    assert file_get.status_code == 404
    assert unknown.status_code == 404
    assert meta.json() == unknown.json()
    assert file_get.json() == meta.json()


def test_media_file_path_rejects_escape(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
    leaked = tmp_path.parent / "leak.bin"
    leaked.write_bytes(b"secret")
    asset = MediaAsset(
        id=uuid4(),
        brand_id=uuid4(),
        kind=MediaKind.image,
        storage_key=f"../{leaked.name}",
        mime="image/png",
        checksum="0" * 64,
    )
    with pytest.raises(AppError) as excinfo:
        media_file_path(asset)
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "not_found"
