from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import (
    ChannelAccount,
    ChannelStatus,
    ChannelType,
    ContentPiece,
    ContentType,
    ContentVariant,
    Locale,
    MediaAsset,
    MediaKind,
    Publication,
    PublicationStatus,
)
from app.config import get_settings
from app.services.adapters.vk import VkAdapter
from tests.vk_mock import install_vk_mock


def test_vk_publish_attaches_cover(db: Session, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
    calls = install_vk_mock(monkeypatch)

    def fake_upload(token, group_id, file_path):
        assert file_path.is_file()
        return "photo-123_501"

    monkeypatch.setattr("app.services.adapters.vk._upload_wall_photo", fake_upload)

    brand_id = uuid4()
    piece = ContentPiece(
        brand_id=brand_id,
        type=ContentType.social_post,
        locale=Locale.ru,
    )
    db.add(piece)
    db.flush()
    asset = MediaAsset(
        brand_id=brand_id,
        kind=MediaKind.image,
        storage_key=f"{brand_id}/cover.jpg",
        mime="image/jpeg",
        checksum="abc",
    )
    db.add(asset)
    db.flush()
    cover_path = tmp_path / f"{brand_id}" / "cover.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"fake-jpeg")
    variant = ContentVariant(
        piece_id=piece.id,
        label="A",
        payload={"text": "VK post"},
        cover_media_id=asset.id,
    )
    db.add(variant)
    db.flush()
    channel = ChannelAccount(
        brand_id=brand_id,
        type=ChannelType.vk,
        display_name="VK",
        status=ChannelStatus.connected,
        token_ciphertext="enc",
        meta={"group_id": "123"},
    )
    db.add(channel)
    db.flush()
    pub = Publication(
        variant_id=variant.id,
        channel_account_id=channel.id,
        scheduled_at=__import__("app.security", fromlist=["utc_now"]).utc_now(),
        status=PublicationStatus.publishing,
    )
    db.add(pub)
    db.flush()

    monkeypatch.setattr(
        "app.services.adapters.vk._access_token",
        lambda _account: "token",
    )
    adapter = VkAdapter()
    result = adapter.publish(db, channel, variant, pub)
    assert result.external_id == "77"
    wall = next(c for c in calls if c["method"] == "wall.post")
    assert wall["params"].get("attachments") == "photo-123_501"
