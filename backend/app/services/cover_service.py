from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any
from urllib.request import urlopen
from uuid import UUID, uuid4

from openai import OpenAI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import BrandProfile, ContentVariant, Job, JobStatus, JobType, MediaAsset, MediaKind
from app.services.ai_client import AIJobError
from app.services.cover_compositor import composite_cover, placeholder_scene_bytes
from app.services.media_service import _media_dir, CANONICAL_MIME
from app.services.variant_checksum import payload_checksum

logger = logging.getLogger(__name__)

MAX_COVER_JOBS_PER_REVISION = 3


def _scene_prompt(variant: ContentVariant) -> str:
    payload = variant.payload or {}
    concept = (
        str(payload.get("image_concept") or "").strip()
        or str(payload.get("scene") or "").strip()
        or str(payload.get("headline") or "").strip()
        or str(payload.get("theme") or "").strip()
        or "tech workspace scene"
    )
    # Concept first: generic "neon cinematic" style used to override the post brief.
    return (
        f"Create a square 1:1 marketing cover illustration that literally depicts this scene: {concept}. "
        "Follow the described objects, composition and setting as closely as possible. "
        "No readable text, no logos, no watermarks, no UI screenshots with letters. "
        "Clean product/editorial illustration, soft depth, navy/teal palette ok but do not replace the scene with abstract neon shapes."
    )


def _decode_image_result(item: Any) -> bytes:
    b64 = getattr(item, "b64_json", None) or (item.get("b64_json") if isinstance(item, dict) else None)
    if b64:
        return base64.b64decode(b64)
    url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
    if url:
        with urlopen(str(url), timeout=60) as response:  # noqa: S310 — OpenAI signed URL
            return response.read()
    raise AIJobError("adapter_error", "OpenAI Images не вернул данные")


def _generate_scene_bytes(prompt: str) -> bytes:
    settings = get_settings()
    if not settings.openai_api_key:
        return placeholder_scene_bytes()
    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.openai_image_model
    # gpt-image-* always returns b64 and rejects response_format.
    # dall-e-* may still accept response_format=b64_json when available on the account.
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1,
    }
    if str(model).startswith("dall-e"):
        kwargs["response_format"] = "b64_json"
    try:
        result = client.images.generate(**kwargs)
    except Exception as exc:
        message = str(exc)
        lower = message.lower()
        if "response_format" in lower and "response_format" in kwargs:
            logger.warning("openai_image_retry_without_response_format model=%s", model)
            kwargs.pop("response_format", None)
            try:
                result = client.images.generate(**kwargs)
            except Exception as retry_exc:
                logger.warning(
                    "openai_image_error type=%s detail=%s",
                    type(retry_exc).__name__,
                    str(retry_exc)[:240],
                )
                raise AIJobError(
                    "adapter_error",
                    "OpenAI Images недоступен",
                    {"detail": str(retry_exc)[:240]},
                ) from retry_exc
        else:
            logger.warning(
                "openai_image_error type=%s detail=%s",
                type(exc).__name__,
                message[:240],
            )
            raise AIJobError(
                "adapter_error",
                "OpenAI Images недоступен",
                {"detail": message[:240]},
            ) from exc
    item = result.data[0] if result.data else None
    if item is None:
        raise AIJobError("adapter_error", "OpenAI Images не вернул данные")
    return _decode_image_result(item)


def count_cover_jobs_for_revision(db: Session, variant_id: UUID, revision: int) -> int:
    rows = db.scalars(
        select(Job).where(
            Job.type == JobType.generate_cover,
            Job.status.in_([JobStatus.queued, JobStatus.running, JobStatus.succeeded]),
        )
    ).all()
    count = 0
    for row in rows:
        payload = row.payload or {}
        if str(payload.get("variant_id")) != str(variant_id):
            continue
        if int(payload.get("expected_revision") or 0) != revision:
            continue
        count += 1
    return count


def _save_cover_asset(db: Session, brand_id: UUID, jpeg_bytes: bytes) -> MediaAsset:
    digest = hashlib.sha256(jpeg_bytes).hexdigest()
    asset_id = uuid4()
    kind = "jpeg"
    storage_key = f"{brand_id}/{asset_id}.{kind}"
    dest = _media_dir(brand_id) / f"{asset_id}.{kind}"
    dest.write_bytes(jpeg_bytes)
    asset = MediaAsset(
        id=asset_id,
        brand_id=brand_id,
        kind=MediaKind.image,
        storage_key=storage_key,
        mime=CANONICAL_MIME[kind],
        width=1080,
        height=1080,
        checksum=digest,
    )
    db.add(asset)
    db.flush()
    return asset


def apply_cover_to_variant_cas(
    db: Session,
    *,
    variant_id: UUID,
    expected_revision: int,
    expected_checksum: str,
    media_id: UUID,
) -> bool:
    result = db.execute(
        update(ContentVariant)
        .where(
            ContentVariant.id == variant_id,
            ContentVariant.revision == expected_revision,
        )
        .values(cover_media_id=media_id)
    )
    if result.rowcount != 1:
        return False
    variant = db.get(ContentVariant, variant_id)
    if variant is None:
        return False
    current = payload_checksum(variant.payload)
    if current != expected_checksum:
        variant.cover_media_id = None
        db.flush()
        return False
    payload = dict(variant.payload or {})
    meta = dict(payload.get("_meta") or {})
    meta.pop("cover", None)
    payload["_meta"] = meta
    variant.payload = payload
    db.flush()
    return True


def execute_generate_cover(db: Session, job: Job, brand: BrandProfile) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cover_generation_enabled:
        raise AIJobError("feature_disabled", "Генерация обложек выключена")

    payload = job.payload
    variant_id = UUID(str(payload["variant_id"]))
    expected_revision = int(payload["expected_revision"])
    expected_checksum = str(payload["expected_payload_checksum"])

    variant = db.get(ContentVariant, variant_id)
    if variant is None or variant.piece.brand_id != brand.id:
        raise AIJobError("not_found", "Вариант не найден")

    if variant.revision != expected_revision:
        raise AIJobError("stale_variant", "Ревизия варианта изменилась")
    if payload_checksum(variant.payload) != expected_checksum:
        raise AIJobError("stale_variant", "Checksum варианта изменился")

    if count_cover_jobs_for_revision(db, variant.id, expected_revision) >= MAX_COVER_JOBS_PER_REVISION:
        raise AIJobError("cover_generation_limit", "Лимит генераций обложки для ревизии")

    scene_bytes = _generate_scene_bytes(_scene_prompt(variant))
    headline = str((variant.payload or {}).get("headline") or "")[:48]
    jpeg_bytes = composite_cover(scene_bytes, headline=headline)
    asset = _save_cover_asset(db, brand.id, jpeg_bytes)
    applied = apply_cover_to_variant_cas(
        db,
        variant_id=variant.id,
        expected_revision=expected_revision,
        expected_checksum=expected_checksum,
        media_id=asset.id,
    )
    return {
        "variant_id": str(variant.id),
        "media_id": str(asset.id),
        "applied": applied,
        "orphan": not applied,
    }
