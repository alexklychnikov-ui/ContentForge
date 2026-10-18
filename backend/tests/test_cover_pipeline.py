from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BrandContentProfile,
    BrandProfile,
    ContentPiece,
    ContentType,
    ContentVariant,
    Job,
    JobStatus,
    JobType,
    KnowledgeMode,
    Locale,
    PieceStatus,
    User,
)
from app.services.cover_compositor import composite_cover, placeholder_scene_bytes
from app.services.job_runner import run_job_in_session
from app.services.variant_checksum import payload_checksum, store_checksum_meta


def test_compositor_produces_jpeg():
    jpeg = composite_cover(placeholder_scene_bytes(), headline="Nodex AI")
    assert jpeg[:2] == b"\xff\xd8"


def test_generate_cover_job(db: Session, monkeypatch):
    monkeypatch.setenv("COVER_GENERATION_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.cover_service._generate_scene_bytes",
        lambda _prompt: placeholder_scene_bytes(),
    )

    brand = BrandProfile(
        workspace_id=uuid4(),
        name="Nodex",
        niche="AI",
        audience="МСБ",
        voice_tone="прямо",
        default_locale=Locale.ru,
    )
    db.add(brand)
    db.flush()
    db.add(
        BrandContentProfile(
            brand_id=brand.id,
            positioning="",
            audience_segments=[],
            audience_pains=[],
            content_pillars=[],
            proof_facts=[],
            preferred_cta_styles=[],
            banned_openers=[],
            structure_rules="",
            platform_policies={},
            knowledge_mode=KnowledgeMode.off,
            knowledge_filters=[],
            require_human_approval=False,
        )
    )
    piece = ContentPiece(
        brand_id=brand.id,
        type=ContentType.social_post,
        locale=Locale.ru,
        status=PieceStatus.draft,
    )
    db.add(piece)
    db.flush()
    payload = store_checksum_meta({"text": "hello", "headline": "Hook"})
    variant = ContentVariant(piece_id=piece.id, label="A", payload=payload, revision=1)
    db.add(variant)
    user = User(email=f"u-{uuid4().hex[:6]}@t.com", password_hash="x")
    db.add(user)
    db.flush()
    checksum = payload_checksum(variant.payload)
    job = Job(
        type=JobType.generate_cover,
        status=JobStatus.queued,
        payload={
            "brand_id": str(brand.id),
            "variant_id": str(variant.id),
            "expected_revision": 1,
            "expected_payload_checksum": checksum,
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    run_job_in_session(db, job.id)
    db.refresh(variant)
    assert job.status is JobStatus.succeeded
    assert variant.cover_media_id is not None
    get_settings.cache_clear()
