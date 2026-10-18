from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import ChannelType, ContentVariant, User
from app.services.adapters.vk import variant_text
from app.services.brand_service import require_brand
from app.services.content_profile_service import ensure_content_profile
from app.services.media_service import media_to_public
from app.services.publication_gate import assert_publication_ready
from app.services.variant_checksum import payload_checksum


def build_manual_export(
    db: Session,
    user: User,
    variant_id: UUID,
    *,
    platform: str,
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if variant is None:
        raise AppError(404, "not_found", "Вариант не найден")
    piece = variant.piece
    brand, _membership = require_brand(db, user, piece.brand_id)
    profile = ensure_content_profile(db, brand.id)
    platform_key = platform.strip().lower()
    if platform_key not in {ChannelType.instagram.value, ChannelType.tenchat.value, ChannelType.vk.value}:
        raise AppError(400, "invalid_platform", "Неподдерживаемая платформа экспорта")

    from types import SimpleNamespace

    channel = SimpleNamespace(type=ChannelType(platform_key))
    assert_publication_ready(
        db,
        brand=brand,
        variant=variant,
        channel=channel,  # type: ignore[arg-type]
        profile=profile,
        channel_type_override=platform_key,
    )

    payload = variant.payload or {}
    cover = None
    if variant.cover_media_id is not None:
        from app.models import MediaAsset

        media = db.get(MediaAsset, variant.cover_media_id)
        if media is not None:
            pub = media_to_public(media)
            cover = {
                "media_id": str(media.id),
                "media_checksum": media.checksum,
                "download_url": pub.url,
                "filename": media.storage_key.rsplit("/", 1)[-1],
                "mime_type": media.mime,
                "expires_at": None,
            }

    text = variant_text(payload)
    hashtags = payload.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []

    return {
        "platform": platform_key,
        "content_type": piece.type.value,
        "title": payload.get("title"),
        "text": text,
        "hashtags": [str(h) for h in hashtags],
        "alt_text": payload.get("alt_text"),
        "revision": variant.revision,
        "payload_checksum": payload_checksum(payload),
        "policy_version": int(getattr(profile, "platform_policies_version", 0) or 0),
        "cover": cover,
    }
