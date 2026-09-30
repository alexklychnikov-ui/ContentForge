from __future__ import annotations

from typing import Any

from app.models import BrandContentProfile, BrandProfile


def build_content_brief(
    brand: BrandProfile,
    profile: BrandContentProfile | None,
    *,
    theme: str = "",
    hook: str = "",
    goal: str = "",
    channel_type: str | None = None,
    extra_instructions: str = "",
) -> dict[str, Any]:
    channel = (channel_type or "").strip().lower() or None
    platform_policy = ""
    if profile is not None and channel:
        policies = profile.platform_policies or {}
        platform_policy = str(policies.get(channel) or policies.get(channel_type or "") or "")

    brief: dict[str, Any] = {
        "theme": theme or "",
        "hook": hook or "",
        "goal": goal or "",
        "channel_type": channel or "",
        "extra_instructions": extra_instructions or "",
        "brand": {
            "name": brand.name,
            "niche": brand.niche,
            "audience": brand.audience,
            "voice_tone": brand.voice_tone,
            "offers": list(brand.offers or []),
            "stopwords": list(brand.stopwords or []),
            "example_posts": list(brand.example_posts or []),
        },
        "audience_segments": [],
        "audience_pains": [],
        "content_pillars": [],
        "proof_facts": [],
        "preferred_cta_styles": [],
        "banned_openers": [],
        "structure_rules": "",
        "platform_policy": platform_policy,
        "positioning": "",
    }
    if profile is None:
        return brief

    brief.update(
        {
            "positioning": profile.positioning or "",
            "audience_segments": list(profile.audience_segments or []),
            "audience_pains": list(profile.audience_pains or []),
            "content_pillars": list(profile.content_pillars or []),
            "proof_facts": list(profile.proof_facts or []),
            "preferred_cta_styles": list(profile.preferred_cta_styles or []),
            "banned_openers": list(profile.banned_openers or []),
            "structure_rules": profile.structure_rules or "",
        }
    )
    return brief
