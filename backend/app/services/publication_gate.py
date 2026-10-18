from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import AppError
from app.models import BrandContentProfile, BrandProfile, ChannelAccount, ContentType, ContentVariant
from app.services.content_profile_service import ensure_content_profile
from app.services.content_quality import get_quality_blockers, is_variant_approved, run_formal_lint_for_variant
from app.services.platform_policy import get_effective_platform_policy
from app.services.variant_checksum import approval_matches, payload_checksum


def _cover_approved(variant: ContentVariant) -> bool:
    cover_id = getattr(variant, "cover_media_id", None)
    if cover_id is None:
        return False
    meta = (variant.payload or {}).get("_meta")
    if not isinstance(meta, dict):
        return False
    cover = meta.get("cover")
    if not isinstance(cover, dict):
        return False
    return (
        int(cover.get("revision") or -1) == variant.revision
        and str(cover.get("media_id")) == str(cover_id)
        and bool(cover.get("approved_at"))
    )


def assert_publication_ready(
    db: Session,
    *,
    brand: BrandProfile,
    variant: ContentVariant,
    channel: ChannelAccount,
    profile: BrandContentProfile | None = None,
    settings: Settings | None = None,
    channel_type_override: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.central_publication_gate_enabled:
        return {}

    profile = profile or ensure_content_profile(db, brand.id)
    piece = variant.piece
    platform = (channel_type_override or channel.type.value).strip().lower()
    policy, _src = get_effective_platform_policy(profile, platform)

    blockers: list[str] = []
    if not policy.allows_content_type(piece.type):
        blockers.append("platform_content_type_not_allowed")

    lint = run_formal_lint_for_variant(variant, piece, profile, brand)
    blockers.extend(lint.blockers)
    blockers.extend(get_quality_blockers(variant.payload))

    if profile.require_human_approval and not is_variant_approved(variant, piece):
        blockers.append("text_not_approved")
    elif not approval_matches(variant.revision, variant.payload):
        blockers.append("stale_approval")

    if policy.media_required:
        cover_id = getattr(variant, "cover_media_id", None)
        if cover_id is None:
            blockers.append("cover_required")
        elif not _cover_approved(variant):
            blockers.append("cover_not_approved")

    if policy.max_text_length and piece.type in (ContentType.social_post, ContentType.article):
        from app.services.adapters.vk import variant_text

        text = variant_text(variant.payload)
        if len(text) > policy.max_text_length:
            blockers.append("text_length_exceeded")

    if blockers:
        raise AppError(
            422,
            "publication_not_ready",
            "Публикация заблокирована gate",
            {"blockers": sorted(set(blockers))},
        )

    checksum = payload_checksum(variant.payload)
    cover_id = getattr(variant, "cover_media_id", None)
    cover_checksum = None
    if cover_id is not None:
        from app.models import MediaAsset

        media = db.get(MediaAsset, cover_id)
        if media is not None:
            cover_checksum = media.checksum

    return {
        "variant_id": str(variant.id),
        "revision": variant.revision,
        "payload_checksum": checksum,
        "policy_version": int(getattr(profile, "platform_policies_version", 0) or 0),
        "cover_media_id": str(cover_id) if cover_id else None,
        "cover_checksum": cover_checksum,
        "platform": platform,
    }


def verify_publication_snapshot(
    publication_meta: dict[str, Any] | None,
    variant: ContentVariant,
    db: Session,
) -> None:
    settings = get_settings()
    if not settings.central_publication_gate_enabled:
        return
    snap = (publication_meta or {}).get("gate_snapshot")
    if not isinstance(snap, dict):
        raise AppError(409, "stale_variant", "У публикации нет gate snapshot")

    current_checksum = payload_checksum(variant.payload)
    if int(snap.get("revision") or 0) != variant.revision:
        raise AppError(409, "stale_variant", "Ревизия варианта изменилась")
    if str(snap.get("payload_checksum") or "") != current_checksum:
        raise AppError(409, "stale_variant", "Checksum варианта изменился")

    cover_id = getattr(variant, "cover_media_id", None)
    snap_cover = snap.get("cover_media_id")
    if snap_cover and str(cover_id or "") != str(snap_cover):
        raise AppError(409, "stale_cover", "Обложка изменилась")

    if snap_cover and snap.get("cover_checksum"):
        from app.models import MediaAsset

        media = db.get(MediaAsset, UUID(str(snap_cover)))
        if media is None or media.checksum != snap.get("cover_checksum"):
            raise AppError(409, "stale_cover", "Checksum обложки не совпадает")
