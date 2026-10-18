import base64
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
from app.services.cover_service import _resolve_cover_copy
from app.services.job_runner import run_job_in_session
from app.services.variant_checksum import payload_checksum, store_checksum_meta


def test_compositor_produces_jpeg():
    jpeg = composite_cover(placeholder_scene_bytes(), headline="Nodex AI")
    assert jpeg[:2] == b"\xff\xd8"
    assert len(jpeg) > 5_000


def test_compositor_long_russian_headline():
    headline = (
        "Как за неделю собрать Telegram-бота на vibe coding без боли и лишней бюрократии"
    )
    jpeg = composite_cover(placeholder_scene_bytes(), headline=headline)
    assert jpeg[:2] == b"\xff\xd8"
    assert len(jpeg) > 8_000


def test_resolve_cover_copy_prefers_image_concept_and_clips_headline():
    headline, brief = _resolve_cover_copy(
        {
            "headline": "Короткий хук #ai #bots и ещё очень длинный хвост который надо обрезать до лимита",
            "lead": "Лид не должен победить headline",
            "image_concept": "desk with laptop and neon keyboard, top-down",
            "scene": "fallback scene",
        }
    )
    assert "#" not in headline
    assert len(headline) <= 56
    assert brief == "desk with laptop and neon keyboard, top-down"


def test_resolve_cover_copy_synthesizes_brief():
    headline, brief = _resolve_cover_copy(
        {
            "text": "Первая строка поста\nВторая",
            "takeaway": "Запусти бота за вечер",
        }
    )
    assert headline == "Первая строка поста"
    assert brief == "scene showing: Запусти бота за вечер"


def test_decode_image_result_b64():
    from app.services.cover_service import _decode_image_result

    raw = b"\xff\xd8\xff"
    out = _decode_image_result({"b64_json": base64.b64encode(raw).decode("ascii")})
    assert out == raw


def test_generate_scene_retries_without_response_format(monkeypatch):
    from app.services import cover_service

    class _Item:
        b64_json = base64.b64encode(b"\xff\xd8\xff").decode("ascii")
        url = None

    class _Result:
        data = [_Item()]

    calls: list[dict] = []

    class _Images:
        def generate(self, **kwargs):
            calls.append(kwargs)
            if "response_format" in kwargs:
                raise Exception("Unknown parameter: 'response_format'.")
            return _Result()

    class _Client:
        images = _Images()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "dall-e-2")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(cover_service, "OpenAI", lambda api_key: _Client())
    out = cover_service._generate_scene_bytes("scene")
    assert out[:2] == b"\xff\xd8"
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    get_settings.cache_clear()


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
