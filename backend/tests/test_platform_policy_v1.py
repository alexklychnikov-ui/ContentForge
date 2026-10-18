import pytest
from pydantic import ValidationError

from app.models import ContentType
from app.services.platform_policy import (
    NODEX_PLATFORM_POLICIES_V1,
    PlatformPolicyV1,
    get_effective_platform_policy,
    merge_v1_policies,
    normalize_legacy_policy,
    parse_policy_v1,
    policy_to_storage,
)
from app.models import BrandContentProfile, KnowledgeMode


def test_instagram_rejects_article_in_policy():
    policy = parse_policy_v1(NODEX_PLATFORM_POLICIES_V1["instagram"])
    assert not policy.allows_content_type(ContentType.article)
    assert policy.allows_content_type(ContentType.social_post)


def test_vk_max_text_length():
    policy = parse_policy_v1(NODEX_PLATFORM_POLICIES_V1["vk"])
    assert policy.max_text_length == 4096


def test_legacy_normalizer_preserves_extra_instructions():
    policy = normalize_legacy_policy("tenchat", "короткий пост; без hard sell")
    assert policy.schema_version == "platform_policy_v1"
    assert "hard sell" in policy.extra_instructions
    assert policy.allows_content_type("social_post")


def test_merge_v1_policies_validates_schema():
    merged = merge_v1_policies(
        None,
        {"vk": {"schema": "platform_policy_v1", "platform": "vk", "allowed_content_types": ["social_post"]}},
    )
    assert "vk" in merged
    assert merged["vk"]["schema"] == "platform_policy_v1"


def test_invalid_policy_schema_raises():
    with pytest.raises(ValidationError):
        parse_policy_v1({"schema": "wrong", "platform": "vk", "allowed_content_types": ["social_post"]})


def test_effective_policy_dual_read_legacy_when_flag_off(monkeypatch):
    monkeypatch.setenv("PLATFORM_POLICY_V1_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    profile = BrandContentProfile(
        brand_id=__import__("uuid").uuid4(),
        positioning="",
        audience_segments=[],
        audience_pains=[],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=[],
        banned_openers=[],
        structure_rules="",
        platform_policies={"vk": "legacy vk rule"},
        platform_policies_v1={"vk": NODEX_PLATFORM_POLICIES_V1["vk"]},
        platform_policies_version=1,
        knowledge_mode=KnowledgeMode.off,
        knowledge_filters=[],
        require_human_approval=True,
    )
    settings = get_settings()
    policy, source = get_effective_platform_policy(profile, "vk", settings)
    assert source == "legacy_normalized"
    assert policy.extra_instructions == "legacy vk rule"
    get_settings.cache_clear()


def test_effective_policy_reads_v1_when_flag_on(monkeypatch):
    monkeypatch.setenv("PLATFORM_POLICY_V1_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    profile = BrandContentProfile(
        brand_id=__import__("uuid").uuid4(),
        positioning="",
        audience_segments=[],
        audience_pains=[],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=[],
        banned_openers=[],
        structure_rules="",
        platform_policies={"vk": "legacy vk rule"},
        platform_policies_v1={"vk": NODEX_PLATFORM_POLICIES_V1["vk"]},
        platform_policies_version=1,
        knowledge_mode=KnowledgeMode.off,
        knowledge_filters=[],
        require_human_approval=True,
    )
    settings = get_settings()
    policy, source = get_effective_platform_policy(profile, "vk", settings)
    assert source == "v1"
    assert policy.grounding_requirement.value == "required"
    get_settings.cache_clear()


def test_policy_roundtrip_storage():
    original = parse_policy_v1(NODEX_PLATFORM_POLICIES_V1["tenchat"])
    stored = policy_to_storage(original)
    again = parse_policy_v1(stored)
    assert again.platform == "tenchat"
    assert again.allowed_content_types == ["social_post", "article"]
