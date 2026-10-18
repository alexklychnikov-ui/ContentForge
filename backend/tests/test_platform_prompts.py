from app.services.platform_policy import parse_policy_v1, NODEX_PLATFORM_POLICIES_V1
from app.services.platform_prompts import social_post_system_prompt


def test_vk_prompt_includes_max_length():
    policy = parse_policy_v1(NODEX_PLATFORM_POLICIES_V1["vk"])
    prompt = social_post_system_prompt("vk", policy)
    assert "4096" in prompt
    assert "VK:" in prompt


def test_instagram_prompt_mentions_alt_text():
    prompt = social_post_system_prompt("instagram", None)
    assert "alt_text" in prompt or "Instagram" in prompt


def test_tenchat_distinct_from_vk():
    vk = social_post_system_prompt("vk", None)
    tc = social_post_system_prompt("tenchat", None)
    assert vk != tc
