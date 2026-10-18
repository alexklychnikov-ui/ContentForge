from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.models import BrandContentProfile, ContentType

POLICY_SCHEMA = "platform_policy_v1"


class GroundingRequirement(str, Enum):
    off = "off"
    optional = "optional"
    required = "required"


class PlatformPolicyV1(BaseModel):
    schema_version: Literal["platform_policy_v1"] = Field(
        default=POLICY_SCHEMA, alias="schema"
    )
    platform: str = Field(min_length=1, max_length=32)
    allowed_content_types: list[str] = Field(min_length=1)
    max_text_length: int | None = Field(default=None, ge=1)
    hook_max_chars: int | None = Field(default=None, ge=1)
    body_max_chars: int | None = Field(default=None, ge=1)
    cta_mode: str = Field(default="choice_1_2")
    hashtags_max: int | None = Field(default=None, ge=0)
    media_required: bool = False
    grounding_requirement: GroundingRequirement = GroundingRequirement.optional
    allowed_retrieval_statuses: list[str] = Field(
        default_factory=lambda: ["success", "empty", "unavailable", "skipped"]
    )
    extra_instructions: str = ""

    model_config = {"populate_by_name": True}

    @field_validator("platform", mode="before")
    @classmethod
    def _norm_platform(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def _norm_types(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [str(v).strip().lower() for v in value]
        return value

    def allows_content_type(self, content_type: ContentType | str) -> bool:
        key = content_type.value if isinstance(content_type, ContentType) else str(content_type).lower()
        return key in self.allowed_content_types


class ContentBriefV2(BaseModel):
    target_platform: str
    content_type: str
    content_format: str = "default"
    audience_segment: str = ""
    pain: str = ""
    scene_seed: str = ""
    proof_source_refs: list[str] = Field(default_factory=list)
    takeaway: str = ""
    cta_mode: str = ""
    image_concept: str = ""
    retrieval_status: str = ""
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    policy_version: int = 0
    prompt_versions: dict[str, str] = Field(default_factory=dict)


def normalize_legacy_policy(platform: str, legacy: str) -> PlatformPolicyV1:
    platform_key = platform.strip().lower()
    defaults = _default_policy_for_platform(platform_key)
    if legacy.strip():
        defaults.extra_instructions = legacy.strip()
    return defaults


def _default_policy_for_platform(platform: str) -> PlatformPolicyV1:
    if platform == "vk":
        return PlatformPolicyV1(
            platform="vk",
            allowed_content_types=["social_post", "article"],
            max_text_length=4096,
            media_required=True,
            grounding_requirement=GroundingRequirement.optional,
            extra_instructions="VK: лонг-пост до 4096 символов; обложка желательна.",
        )
    if platform == "instagram":
        return PlatformPolicyV1(
            platform="instagram",
            allowed_content_types=["social_post"],
            hashtags_max=30,
            media_required=True,
            grounding_requirement=GroundingRequirement.optional,
            extra_instructions="Instagram: caption + hashtags + alt; без статей в MVP.",
        )
    if platform == "tenchat":
        return PlatformPolicyV1(
            platform="tenchat",
            allowed_content_types=["social_post", "article"],
            grounding_requirement=GroundingRequirement.optional,
            extra_instructions="TenChat: сцена, практика, уносимый ход; long-form экспериментальный.",
        )
    return PlatformPolicyV1(
        platform=platform,
        allowed_content_types=["social_post", "article", "email"],
        extra_instructions="",
    )


def parse_policy_v1(raw: dict[str, Any] | PlatformPolicyV1) -> PlatformPolicyV1:
    if isinstance(raw, PlatformPolicyV1):
        return raw
    return PlatformPolicyV1.model_validate(raw)


def policy_to_storage(policy: PlatformPolicyV1) -> dict[str, Any]:
    return policy.model_dump(by_alias=True)


NODEX_PLATFORM_POLICIES_V1: dict[str, dict[str, Any]] = {
    "vk": policy_to_storage(
        PlatformPolicyV1(
            platform="vk",
            allowed_content_types=["social_post", "article"],
            max_text_length=4096,
            media_required=True,
            grounding_requirement=GroundingRequirement.required,
            extra_instructions=(
                "VK Nodex: hook в первых строках; без hard sell; "
                "конкретная сцена из практики; CTA 1/2."
            ),
        )
    ),
    "instagram": policy_to_storage(
        PlatformPolicyV1(
            platform="instagram",
            allowed_content_types=["social_post"],
            hashtags_max=25,
            media_required=True,
            grounding_requirement=GroundingRequirement.optional,
            extra_instructions=(
                "Instagram Nodex: короткий caption; релевантные hashtags; "
                "alt text обязателен; квадратная обложка."
            ),
        )
    ),
    "tenchat": policy_to_storage(
        PlatformPolicyV1(
            platform="tenchat",
            allowed_content_types=["social_post", "article"],
            grounding_requirement=GroundingRequirement.required,
            extra_instructions=(
                "TenChat Nodex: боль → сцена → практика → takeaway → CTA; "
                "действие на 48 часов; без нейрошаблонов."
            ),
        )
    ),
}


def get_effective_platform_policy(
    profile: BrandContentProfile,
    platform: str,
    settings: Settings | None = None,
) -> tuple[PlatformPolicyV1, str]:
    settings = settings or get_settings()
    platform_key = platform.strip().lower()
    v1_store = getattr(profile, "platform_policies_v1", None) or {}
    legacy = profile.platform_policies or {}

    if settings.platform_policy_v1_enabled and isinstance(v1_store, dict):
        raw = v1_store.get(platform_key)
        if raw:
            return parse_policy_v1(raw), "v1"

    legacy_str = legacy.get(platform_key) or legacy.get(platform) or ""
    if isinstance(legacy_str, str) and legacy_str.strip():
        return normalize_legacy_policy(platform_key, legacy_str), "legacy_normalized"

    return _default_policy_for_platform(platform_key), "default"


def merge_v1_policies(
    current: dict[str, Any] | None, updates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    out = dict(current or {})
    for platform, policy_dict in updates.items():
        key = platform.strip().lower()
        parsed = parse_policy_v1({**policy_dict, "platform": key})
        out[key] = policy_to_storage(parsed)
    return out
