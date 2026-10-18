from datetime import date

from app.models import BrandContentProfile, ChannelType, ContentType, KnowledgeMode
from app.services.ai_jobs import _build_targets_per_channel, plan_slot_window
from app.services.platform_policy import PlatformPolicyV1


def test_future_month_full_range() -> None:
    start, end = plan_slot_window(2026, 12, today=date(2026, 10, 18))
    assert start == date(2026, 12, 1)
    assert end == date(2026, 12, 31)


def test_past_month_full_range() -> None:
    start, end = plan_slot_window(2026, 9, today=date(2026, 10, 18))
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_current_month_from_today() -> None:
    start, end = plan_slot_window(2026, 10, today=date(2026, 10, 18))
    assert start == date(2026, 10, 18)
    assert end == date(2026, 10, 31)


def test_first_day_of_month() -> None:
    start, end = plan_slot_window(2026, 10, today=date(2026, 10, 1))
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)


def test_targets_per_channel_no_profile() -> None:
    channels = [ChannelType.telegram, ChannelType.vk]
    targets = {
        ContentType.social_post: 2,
        ContentType.article: 1,
    }
    matrix = _build_targets_per_channel(channels, targets, None)
    assert matrix == {
        "telegram": {"social_post": 2, "article": 1},
        "vk": {"social_post": 2, "article": 1},
    }
    assert sum(sum(v.values()) for v in matrix.values()) == 6


def test_targets_per_channel_skips_email() -> None:
    channels = [ChannelType.telegram, ChannelType.vk]
    targets = {
        ContentType.social_post: 2,
        ContentType.email: 1,
    }
    matrix = _build_targets_per_channel(channels, targets, None)
    assert matrix == {
        "telegram": {"social_post": 2},
        "vk": {"social_post": 2},
    }


def test_targets_per_channel_respects_policy(monkeypatch) -> None:
    profile = BrandContentProfile(
        brand_id=None,  # type: ignore[arg-type]
        positioning="",
        audience_segments=[],
        audience_pains=[],
        content_pillars=[],
        proof_facts=[],
        preferred_cta_styles=[],
        banned_openers=[],
        structure_rules="",
        platform_policies={},
        platform_policies_v1=None,
        platform_policies_version=0,
        knowledge_mode=KnowledgeMode.off,
        knowledge_filters=[],
        require_human_approval=True,
    )
    policies = {
        "telegram": PlatformPolicyV1(
            platform="telegram",
            allowed_content_types=["social_post", "article"],
        ),
        "vk": PlatformPolicyV1(
            platform="vk",
            allowed_content_types=["social_post"],
        ),
    }

    def _fake_policy(_profile, platform: str, settings=None):
        return policies[platform], "test"

    monkeypatch.setattr("app.services.ai_jobs.get_effective_platform_policy", _fake_policy)
    channels = [ChannelType.telegram, ChannelType.vk]
    targets = {
        ContentType.social_post: 2,
        ContentType.article: 1,
    }
    matrix = _build_targets_per_channel(channels, targets, profile)
    assert matrix == {
        "telegram": {"social_post": 2, "article": 1},
        "vk": {"social_post": 2},
    }
    assert sum(sum(v.values()) for v in matrix.values()) == 5
