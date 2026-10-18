from uuid import uuid4

import pytest

from app.errors import AppError
from app.models import (
    BrandContentProfile,
    BrandProfile,
    ChannelAccount,
    ChannelStatus,
    ChannelType,
    ContentPiece,
    ContentType,
    ContentVariant,
    KnowledgeMode,
    Locale,
    PieceStatus,
)
from app.services.content_quality import store_approval_on_payload
from app.services.publication_gate import assert_publication_ready
from app.services.variant_checksum import payload_checksum, store_checksum_meta


def _setup(db):
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
    profile = BrandContentProfile(
        brand_id=brand.id,
        positioning="",
        audience_segments=[],
        audience_pains=["боль"],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=[],
        banned_openers=[],
        structure_rules="боль → сцена",
        platform_policies={},
        knowledge_mode=KnowledgeMode.required,
        knowledge_filters=[],
        require_human_approval=True,
    )
    db.add(profile)
    piece = ContentPiece(
        brand_id=brand.id,
        type=ContentType.social_post,
        locale=Locale.ru,
        status=PieceStatus.draft,
    )
    db.add(piece)
    db.flush()
    payload = store_checksum_meta(
        {
            "text": "текст",
            "lead": "лид",
            "scene": "сцена",
            "takeaway": "вывод",
            "cta": "1 или 2?",
        }
    )
    variant = ContentVariant(piece_id=piece.id, label="A", payload=payload, revision=1)
    db.add(variant)
    channel = ChannelAccount(
        brand_id=brand.id,
        type=ChannelType.vk,
        display_name="VK",
        status=ChannelStatus.connected,
        token_ciphertext="x",
        meta={"group_id": "123"},
    )
    db.add(channel)
    db.flush()
    return brand, profile, variant, channel


def test_gate_skipped_when_flag_off(db, monkeypatch):
    monkeypatch.setenv("CENTRAL_PUBLICATION_GATE_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    brand, profile, variant, channel = _setup(db)
    snap = assert_publication_ready(
        db, brand=brand, variant=variant, channel=channel, profile=profile
    )
    assert snap == {}
    get_settings.cache_clear()


def test_gate_blocks_unapproved_when_flag_on(db, monkeypatch):
    monkeypatch.setenv("CENTRAL_PUBLICATION_GATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    brand, profile, variant, channel = _setup(db)
    with pytest.raises(AppError) as exc:
        assert_publication_ready(
            db, brand=brand, variant=variant, channel=channel, profile=profile
        )
    assert exc.value.code == "publication_not_ready"
    get_settings.cache_clear()


def test_gate_passes_with_approval(db, monkeypatch):
    monkeypatch.setenv("CENTRAL_PUBLICATION_GATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    brand, profile, variant, channel = _setup(db)
    channel.type = ChannelType.tenchat
    checksum = payload_checksum(variant.payload)
    variant.payload = store_approval_on_payload(
        variant.payload,
        approved_at="now",
        approved_by="user",
        revision=variant.revision,
        checksum=checksum,
    )
    variant.piece.status = PieceStatus.ready
    snap = assert_publication_ready(
        db, brand=brand, variant=variant, channel=channel, profile=profile
    )
    assert snap["payload_checksum"] == checksum
    get_settings.cache_clear()
