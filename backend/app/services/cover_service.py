from __future__ import annotations

import hashlib
import logging
from typing import Any
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
    concept = payload.get("image_concept") or payload.get("headline") or payload.get("theme") or "tech scene"
    return (
        "Dark cinematic high-tech marketing scene, navy background, cyan glow, "
        "no text, no logo, no watermark, single focal subject, square composition. "
        f"Concept: {concept}"
    )


def _generate_scene_bytes(prompt: str) -> bytes:
    settings = get_settings()
    if not settings.openai_api_key:
        return placeholder_scene_bytes()
    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.openai_image_model
    try:
        result = client.images.generate(
            model=model,
            prompt=prompt,
            size="1024x1024",
            n=1,
            response_format="b64_json",
        )
    except Exception as exc:
        logger.warning("openai_image_error type=%s", type(exc).__name__)
        raise AIJobError("adapter_error", "OpenAI Images недоступен", retryable=True) from exc
    item = result.data[0] if result.data else None
    if item is None or not item.b64_json:
        raise AIJobError("adapter_error", "OpenAI Images не вернул данные", retryable=True)
    import base64

    return base64.b64decode(item.b64_json)


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
