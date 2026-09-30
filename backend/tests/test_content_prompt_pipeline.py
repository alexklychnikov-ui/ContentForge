from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
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
    Membership,
    MembershipRole,
    PieceStatus,
    User,
    Workspace,
)
from app.services.ai_client import AIJobError, PROMPT_VERSION
from app.services.ai_jobs import (
    CONTENT_SYSTEM,
    CONTENT_SYSTEM_V2,
    PROMPT_VERSION_CONTENT_V2,
    execute_generate_content,
)
from app.services.ai_schemas import SocialPostAI
from app.services.knowledge_grounding import (
    GroundingReference,
    GroundingResult,
    GroundingStatus,
)
from tests.openai_mock import openai_ok


def _seed_brand(db: Session, *, knowledge_mode: KnowledgeMode = KnowledgeMode.off) -> tuple[BrandProfile, User, ContentPiece]:
    user = User(email=f"u-{uuid4().hex[:8]}@example.com", password_hash="x")
    workspace = Workspace(name="WS")
    db.add_all([user, workspace])
    db.flush()
    db.add(
        Membership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MembershipRole.owner,
        )
    )
    brand = BrandProfile(
        workspace_id=workspace.id,
        name="NODEX",
        niche="B2B",
        audience="маркетологи",
        voice_tone="прямо",
        stopwords=["гарантия"],
        offers=["аудит"],
        example_posts=["кейс"],
        default_locale=Locale.ru,
    )
    db.add(brand)
    db.flush()
    db.add(
        BrandContentProfile(
            brand_id=brand.id,
            positioning="Python/AI",
            audience_segments=["МСБ"],
            audience_pains=["размытое ТЗ"],
            content_pillars=["практика"],
            proof_facts=["деплой за неделю"],
            preferred_cta_styles=["выбор 1/2"],
            banned_openers=["В современном мире"],
            structure_rules="боль → сцена → практика → takeaway → CTA",
            platform_policies={"telegram": "коротко, без hard sell"},
            knowledge_mode=knowledge_mode,
            knowledge_filters=[],
            require_human_approval=True,
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
    return brand, user, piece


def _job(user: User, piece: ContentPiece, **extra) -> Job:
    payload = {
        "piece_id": str(piece.id),
        "variant_label": "A",
        "channel_type": "telegram",
        "extra_instructions": "про автоматизацию",
        **extra,
    }
    return Job(
        type=JobType.generate_content,
        status=JobStatus.queued,
        payload=payload,
        created_by=user.id,
    )


def test_social_post_ai_accepts_legacy_payload() -> None:
    parsed = SocialPostAI.model_validate(
        {"text": "Старый пост", "cta": "Написать", "hashtags": ["b2b"]}
    )
    assert parsed.text == "Старый пост"
    assert parsed.headline == ""
    assert parsed.lead == ""
    assert parsed.scene == ""
    assert parsed.takeaway == ""
    assert parsed.cta == "Написать"
    assert parsed.hashtags == ["b2b"]


def test_social_generate_required_blocked_skips_openai(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand, user, piece = _seed_brand(db, knowledge_mode=KnowledgeMode.required)
    job = _job(user, piece)
    db.add(job)
    db.flush()

    openai_calls: list = []

    def _openai(*args, **kwargs):
        openai_calls.append((args, kwargs))
        raise AssertionError("OpenAI must not be called when grounding blocked")

    monkeypatch.setattr("app.services.ai_jobs.complete_json", _openai)
    monkeypatch.setattr(
        "app.services.ai_jobs.ground_knowledge",
        lambda *_a, **_k: GroundingResult(
            status=GroundingStatus.blocked,
            error_code="unavailable",
            error_message="LightRAG unavailable",
        ),
    )

    with pytest.raises(AIJobError) as exc_info:
        execute_generate_content(db, job, brand)

    assert exc_info.value.code == "grounding_blocked"
    assert "LightRAG" in exc_info.value.message
    assert openai_calls == []
    variants = list(db.scalars(select(ContentVariant).where(ContentVariant.piece_id == piece.id)))
    assert variants == []


def test_social_generate_grounded_includes_fence_and_brief(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand, user, piece = _seed_brand(db, knowledge_mode=KnowledgeMode.required)
    job = _job(user, piece)
    db.add(job)
    db.flush()

    captured: dict = {}

    def _openai(model_cls, messages, **kwargs):
        captured["messages"] = messages
        return openai_ok(model_cls, messages, **kwargs)

    monkeypatch.setattr("app.services.ai_jobs.complete_json", _openai)
    monkeypatch.setattr(
        "app.services.ai_jobs.ground_knowledge",
        lambda *_a, **_k: GroundingResult(
            status=GroundingStatus.grounded,
            context="Факт: бот без процесса ломается на 3-й неделе",
            references=[GroundingReference(id="1", file_path="cases/bot.md")],
        ),
    )

    result = execute_generate_content(db, job, brand)
    assert result["grounding_status"] == "grounded"
    assert result["prompt_version"] == PROMPT_VERSION_CONTENT_V2

    system = captured["messages"][0]["content"]
    user_msg = captured["messages"][1]["content"]
    assert system == CONTENT_SYSTEM_V2
    assert "<<<UNTRUSTED_KNOWLEDGE" in user_msg
    assert "UNTRUSTED_KNOWLEDGE>>>" in user_msg
    assert "бот без процесса" in user_msg
    assert "content_brief" in user_msg
    assert "размытое ТЗ" in user_msg
    assert "В современном мире" in user_msg
    assert "боль → сцена" in user_msg

    variant = db.scalars(select(ContentVariant).where(ContentVariant.piece_id == piece.id)).one()
    meta = variant.payload["_meta"]
    assert meta["grounding_status"] == "grounded"
    assert meta["prompt_version"] == PROMPT_VERSION_CONTENT_V2
    assert meta["knowledge_mode"] == "required"
    assert meta["references"] == [{"id": "1", "file_path": "cases/bot.md"}]
    assert "text" in variant.payload


def test_social_generate_knowledge_off_skips_lightrag(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand, user, piece = _seed_brand(db, knowledge_mode=KnowledgeMode.off)
    profile = db.get(BrandContentProfile, brand.id)
    assert profile is not None
    profile.structure_rules = ""
    profile.content_pillars = []
    profile.banned_openers = []
    profile.audience_pains = []
    db.flush()

    job = _job(user, piece)
    db.add(job)
    db.flush()

    captured: dict = {}
    ground_calls: list = []

    def _openai(model_cls, messages, **kwargs):
        captured["messages"] = messages
        return openai_ok(model_cls, messages, **kwargs)

    def _ground(*args, **kwargs):
        ground_calls.append(1)
        raise AssertionError("LightRAG must not be called when knowledge_mode=off")

    monkeypatch.setattr("app.services.ai_jobs.complete_json", _openai)
    monkeypatch.setattr("app.services.ai_jobs.ground_knowledge", _ground)

    result = execute_generate_content(db, job, brand)
    assert result["grounding_status"] == "skipped"
    assert ground_calls == []
    assert captured["messages"][0]["content"] == CONTENT_SYSTEM
    assert "<<<UNTRUSTED_KNOWLEDGE" not in captured["messages"][1]["content"]
    assert result["prompt_version"] == PROMPT_VERSION

    variant = db.scalars(select(ContentVariant).where(ContentVariant.piece_id == piece.id)).one()
    assert variant.payload["_meta"]["knowledge_mode"] == "off"
    assert variant.payload["_meta"]["grounding_status"] == "skipped"


def test_social_generate_ungrounded_continues_with_warning(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand, user, piece = _seed_brand(db, knowledge_mode=KnowledgeMode.optional)
    job = _job(user, piece)
    db.add(job)
    db.flush()

    monkeypatch.setattr("app.services.ai_jobs.complete_json", openai_ok)
    monkeypatch.setattr(
        "app.services.ai_jobs.ground_knowledge",
        lambda *_a, **_k: GroundingResult(
            status=GroundingStatus.ungrounded,
            error_code="empty",
            error_message="LightRAG returned empty context",
            warning="LightRAG returned empty context",
        ),
    )

    result = execute_generate_content(db, job, brand)
    assert result["grounding_status"] == "ungrounded"
    assert result.get("grounding_warning")
    variant = db.scalars(select(ContentVariant).where(ContentVariant.piece_id == piece.id)).one()
    assert variant.payload["_meta"]["warning"] == "LightRAG returned empty context"
