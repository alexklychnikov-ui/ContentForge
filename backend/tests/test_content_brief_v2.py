from uuid import uuid4

from app.models import BrandContentProfile, BrandProfile, KnowledgeMode, Locale, PlanItem
from app.services.content_brief import build_content_brief_v2
from app.services.platform_policy import NODEX_PLATFORM_POLICIES_V1


def test_brief_v2_includes_policy_snapshot_when_v1_enabled(monkeypatch):
    monkeypatch.setenv("PLATFORM_POLICY_V1_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    brand = BrandProfile(
        workspace_id=uuid4(),
        name="Nodex",
        niche="AI",
        audience="МСБ",
        voice_tone="прямо",
        default_locale=Locale.ru,
    )
    profile = BrandContentProfile(
        brand_id=uuid4(),
        positioning="test",
        audience_segments=["малый бизнес"],
        audience_pains=["размытое ТЗ"],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=["выбор 1/2"],
        banned_openers=[],
        structure_rules="",
        platform_policies={},
        platform_policies_v1={"vk": NODEX_PLATFORM_POLICIES_V1["vk"]},
        platform_policies_version=2,
        knowledge_mode=KnowledgeMode.required,
        knowledge_filters=[],
        require_human_approval=True,
    )
    item = PlanItem(
        plan_id=uuid4(),
        date=__import__("datetime").date.today(),
        channel_type=__import__("app.models", fromlist=["ChannelType"]).ChannelType.vk,
        content_type=__import__("app.models", fromlist=["ContentType"]).ContentType.social_post,
        theme="тема",
        hook="hook",
        audience_segment="сегмент из плана",
        audience_pain="боль из плана",
        takeaway="вывод",
        scene_seed="сцена",
        image_concept="HUD + smartphone",
    )
    brief = build_content_brief_v2(
        brand,
        profile,
        plan_item=item,
        theme="тема",
        hook="hook",
        channel_type="vk",
        content_type="social_post",
        retrieval_status="success",
        proof_source_refs=["doc-1"],
    )
    assert brief["target_platform"] == "vk"
    assert brief["audience_segment"] == "сегмент из плана"
    assert brief["policy_version"] == 2
    assert brief["policy_snapshot"].get("schema") == "platform_policy_v1"
    assert brief["retrieval_status"] == "success"
    assert brief["proof_source_refs"] == ["doc-1"]
    get_settings.cache_clear()
