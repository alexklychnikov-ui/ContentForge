from __future__ import annotations

from typing import Any

from app.models import BrandContentProfile, BrandProfile, PlanItem
from app.services.platform_policy import (
    PlatformPolicyV1,
    get_effective_platform_policy,
    policy_to_storage,
)


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
        policy, _source = get_effective_platform_policy(profile, channel)
        platform_policy = policy.extra_instructions or ""
        if not platform_policy:
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


def build_content_brief_v2(
    brand: BrandProfile,
    profile: BrandContentProfile | None,
    *,
    plan_item: PlanItem | None = None,
    theme: str = "",
    hook: str = "",
    goal: str = "",
    channel_type: str | None = None,
    content_type: str = "social_post",
    retrieval_status: str = "",
    proof_source_refs: list[str] | None = None,
) -> dict[str, Any]:
    channel = (channel_type or "").strip().lower() or None
    policy: PlatformPolicyV1 | None = None
    policy_version = 0
    if profile is not None and channel:
        policy, _source = get_effective_platform_policy(profile, channel)
        policy_version = int(getattr(profile, "platform_policies_version", 0) or 0)

    segment = ""
    pain = ""
    takeaway = ""
    scene_seed = ""
    image_concept = ""
    if plan_item is not None:
        segment = plan_item.audience_segment or ""
        pain = plan_item.audience_pain or ""
        takeaway = plan_item.takeaway or ""
        scene_seed = plan_item.scene_seed or ""
        image_concept = plan_item.image_concept or ""

    if profile is not None:
        if not segment and profile.audience_segments:
            segment = profile.audience_segments[0]
        if not pain and profile.audience_pains:
            pain = profile.audience_pains[0]

    legacy = build_content_brief(
        brand,
        profile,
        theme=theme,
        hook=hook,
        goal=goal,
        channel_type=channel,
    )
    return {
        "target_platform": channel or "",
        "content_type": content_type,
        "content_format": "default",
        "audience_segment": segment,
        "pain": pain,
        "scene_seed": scene_seed or hook or theme,
        "proof_source_refs": list(proof_source_refs or []),
        "takeaway": takeaway,
        "cta_mode": (
            profile.preferred_cta_styles[0]
            if profile and profile.preferred_cta_styles
            else ""
        ),
        "image_concept": image_concept,
        "retrieval_status": retrieval_status,
        "policy_snapshot": policy_to_storage(policy) if policy else {},
        "policy_version": policy_version,
        "prompt_versions": {},
        "theme": theme or "",
        "hook": hook or "",
        "goal": goal or "",
        "content_brief_legacy": legacy,
    }
