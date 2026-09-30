from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BrandContentProfile,
    BrandProfile,
    ChannelAccount,
    ChannelStatus,
    ChannelType,
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
from app.services.ai_jobs import _maybe_auto_schedule, execute_generate_content
from app.services.content_quality import lint_social_post
from app.services.content_profile_service import ensure_content_profile
from tests.helpers import auth_header, create_brand, register_user
from tests.openai_mock import install_openai_mock, openai_ok


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch) -> None:
    install_openai_mock(monkeypatch)


def _profile(**overrides) -> BrandContentProfile:
    data = {
        "brand_id": uuid4(),
        "positioning": "x",
        "audience_segments": [],
        "audience_pains": ["боль"],
        "content_pillars": ["практика"],
        "proof_facts": [],
        "preferred_cta_styles": ["выбор 1/2"],
        "banned_openers": ["В современном мире"],
        "structure_rules": "боль → сцена → практика",
        "platform_policies": {},
        "knowledge_mode": KnowledgeMode.off,
        "knowledge_filters": [],
        "require_human_approval": True,
    }
    data.update(overrides)
    return BrandContentProfile(**data)


def test_lint_catches_banned_opener_and_missing_scene() -> None:
    profile = _profile()
    result = lint_social_post(
        {
            "text": "В современном мире все автоматизируют маркетинг",
            "lead": "",
            "scene": "",
            "takeaway": "Сделай бриф",
            "cta": "Написать",
        },
        profile,
        stopwords=["гарантия"],
    )
    assert "banned_opener:text:В современном мире" in result.blockers
    assert "missing_scene" in result.blockers
    assert "missing_lead" not in result.blockers  # first lines of text act as hook


def test_lint_missing_lead_when_text_empty() -> None:
    profile = _profile(preferred_cta_styles=[])
    result = lint_social_post(
        {"text": "", "lead": "", "scene": "сцена", "takeaway": "вывод", "cta": ""},
        profile,
    )
    assert "empty_text" in result.blockers
    assert "missing_lead" in result.blockers
    assert "missing_cta" in result.warnings


def _seed(db: Session, *, require_human_approval: bool = True) -> tuple[BrandProfile, User, ContentPiece]:
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
            platform_policies={},
            knowledge_mode=KnowledgeMode.off,
            knowledge_filters=[],
            require_human_approval=require_human_approval,
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


def _good_payload(**extra) -> dict:
    payload = {
        "text": "Клиент принёс размытое ТЗ и ждёт ясный план",
        "headline": "ТЗ без критериев",
        "lead": "Клиент ждёт ясный следующий шаг",
        "scene": "Разбор брифа на созвоне",
        "takeaway": "Сначала зафиксировать критерий успеха",
        "cta": "Напишите 1 или 2",
        "hashtags": ["b2b"],
        "alt_text": "обложка",
        "_meta": {},
    }
    payload.update(extra)
    return payload


def test_approve_blocked_when_blockers(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={
            "structure_rules": "боль → сцена",
            "banned_openers": ["В современном мире"],
            "preferred_cta_styles": ["выбор 1/2"],
        },
        headers=headers,
    )
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "social_post"},
        headers=headers,
    ).json()
    variant = client.post(
        f"/api/v1/content/{piece['id']}/variants",
        json={
            "label": "A",
            "payload": {
                "text": "В современном мире всё сложно",
                "lead": "",
                "scene": "",
                "takeaway": "вывод",
                "cta": "ok",
            },
        },
        headers=headers,
    ).json()
    blocked = client.post(
        f"/api/v1/content/{piece['id']}/variants/{variant['id']}/approve",
        headers=headers,
    )
    assert blocked.status_code == 409
    body = blocked.json()["error"]
    assert body["code"] == "quality_blockers"
    assert any("banned_opener" in item for item in body["details"]["blockers"])
    assert "missing_scene" in body["details"]["blockers"]


def test_approve_succeeds_clears_path(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={
            "structure_rules": "боль → сцена",
            "preferred_cta_styles": ["выбор 1/2"],
            "require_human_approval": True,
        },
        headers=headers,
    )
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "social_post"},
        headers=headers,
    ).json()
    variant = client.post(
        f"/api/v1/content/{piece['id']}/variants",
        json={"label": "A", "payload": _good_payload()},
        headers=headers,
    ).json()
    approved = client.post(
        f"/api/v1/variants/{variant['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "ready"
    meta = body["variants"][0]["payload"]["_meta"]
    assert meta["approved_at"]
    assert meta["approved_by"]


def test_review_endpoint_persists_quality(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    piece = client.post(
        f"/api/v1/brands/{brand_id}/content",
        json={"type": "social_post"},
        headers=headers,
    ).json()
    variant = client.post(
        f"/api/v1/content/{piece['id']}/variants",
        json={"label": "A", "payload": _good_payload()},
        headers=headers,
    ).json()
    reviewed = client.post(
        f"/api/v1/variants/{variant['id']}/review",
        json={"run_ai": True},
        headers=headers,
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["ai_review"]["overall"] == 4
    assert body["approved"] is False
    loaded = client.get(f"/api/v1/content/{piece['id']}", headers=headers).json()
    quality = loaded["variants"][0]["payload"]["_meta"]["quality"]
    assert quality["ai_review"]["pass"] is True


def test_auto_schedule_skipped_when_approval_required(db: Session) -> None:
    brand, user, piece = _seed(db, require_human_approval=True)
    variant = ContentVariant(piece_id=piece.id, label="A", payload=_good_payload(), revision=1)
    db.add(variant)
    db.flush()
    job = Job(
        type=JobType.generate_content,
        status=JobStatus.succeeded,
        payload={
            "piece_id": str(piece.id),
            "auto_schedule": True,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "channel_type": "telegram",
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    out: dict = {}
    _maybe_auto_schedule(db, job, brand, variant, [], out)
    assert out["auto_schedule_error"] == "approval_required"


def test_auto_schedule_allowed_when_approved(db: Session) -> None:
    brand, user, piece = _seed(db, require_human_approval=True)
    piece.status = PieceStatus.ready
    payload = _good_payload()
    payload["_meta"] = {
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": str(user.id),
        "quality": {"blockers": [], "warnings": [], "lint": {"scores": None}},
    }
    variant = ContentVariant(piece_id=piece.id, label="A", payload=payload, revision=1)
    db.add(variant)
    db.add(
        ChannelAccount(
            brand_id=brand.id,
            type=ChannelType.telegram,
            status=ChannelStatus.connected,
            display_name="tg",
            external_account_id="-1001",
            meta={"channel_id": "-1001"},
        )
    )
    db.flush()
    job = Job(
        type=JobType.generate_content,
        status=JobStatus.succeeded,
        payload={
            "piece_id": str(piece.id),
            "auto_schedule": True,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "channel_type": "telegram",
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    out: dict = {}
    _maybe_auto_schedule(db, job, brand, variant, [], out)
    assert "publication_id" in out
    assert "auto_schedule_error" not in out


def test_auto_schedule_allowed_when_approval_disabled(db: Session) -> None:
    brand, user, piece = _seed(db, require_human_approval=False)
    payload = _good_payload()
    payload["_meta"] = {
        "quality": {"blockers": [], "warnings": [], "lint": {"scores": None}},
    }
    variant = ContentVariant(piece_id=piece.id, label="A", payload=payload, revision=1)
    db.add(variant)
    db.add(
        ChannelAccount(
            brand_id=brand.id,
            type=ChannelType.telegram,
            status=ChannelStatus.connected,
            display_name="tg",
            external_account_id="-1001",
            meta={"channel_id": "-1001"},
        )
    )
    db.flush()
    job = Job(
        type=JobType.generate_content,
        status=JobStatus.succeeded,
        payload={
            "piece_id": str(piece.id),
            "auto_schedule": True,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "channel_type": "telegram",
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    out: dict = {}
    _maybe_auto_schedule(db, job, brand, variant, [], out)
    assert "publication_id" in out


def test_generate_stores_quality_for_v2(db: Session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai_jobs.complete_json", openai_ok)
    brand, user, piece = _seed(db, require_human_approval=True)
    profile = ensure_content_profile(db, brand.id)
    assert profile.structure_rules
    job = Job(
        type=JobType.generate_content,
        status=JobStatus.queued,
        payload={
            "piece_id": str(piece.id),
            "variant_label": "A",
            "channel_type": "telegram",
            "extra_instructions": "",
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    result = execute_generate_content(db, job, brand)
    variant = db.get(ContentVariant, UUID(str(result["variant_id"])))
    assert variant is not None
    quality = variant.payload["_meta"]["quality"]
    assert "blockers" in quality
    assert "lint" in quality
