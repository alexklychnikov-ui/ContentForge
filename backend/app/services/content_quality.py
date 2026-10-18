from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models import (
    BrandContentProfile,
    BrandProfile,
    ContentPiece,
    ContentType,
    ContentVariant,
    KnowledgeMode,
    PieceStatus,
)
from app.services.platform_policy import get_effective_platform_policy
from app.services.stopwords import find_stopwords, payload_text
from app.services.variant_checksum import approval_matches


class QualityLintResult(BaseModel):
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scores: dict[str, float] | None = None


def _str_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _first_lines(text: str, n: int = 2) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:n])


def _has_hook(payload: dict[str, Any]) -> bool:
    if _str_field(payload, "lead"):
        return True
    text = _str_field(payload, "text")
    return bool(_first_lines(text))


def _starts_with_banned(hay: str, banned: list[str]) -> list[str]:
    folded = hay.casefold().lstrip()
    hits: list[str] = []
    for opener in banned:
        needle = str(opener).strip()
        if not needle:
            continue
        if folded.startswith(needle.casefold()):
            hits.append(opener)
    return hits


def _require_structure(profile: BrandContentProfile) -> bool:
    if profile.knowledge_mode is not KnowledgeMode.off:
        return True
    return bool((profile.structure_rules or "").strip())


def lint_social_post(
    payload: dict[str, Any] | None,
    profile: BrandContentProfile,
    stopwords: list[str] | None = None,
) -> QualityLintResult:
    data = dict(payload or {})
    blockers: list[str] = []
    warnings: list[str] = []

    text = _str_field(data, "text")
    if not text:
        blockers.append("empty_text")

    if not _has_hook(data):
        blockers.append("missing_lead")

    require_struct = _require_structure(profile)
    if require_struct and not _str_field(data, "scene"):
        blockers.append("missing_scene")
    if require_struct and not _str_field(data, "takeaway"):
        blockers.append("missing_takeaway")

    cta = _str_field(data, "cta")
    preferred = list(profile.preferred_cta_styles or [])
    if not cta:
        if preferred:
            blockers.append("missing_cta")
        else:
            warnings.append("missing_cta")

    banned = list(profile.banned_openers or [])
    if banned:
        lead = _str_field(data, "lead")
        for source, label in ((text, "text"), (lead, "lead")):
            if not source:
                continue
            hits = _starts_with_banned(source, banned)
            for opener in hits:
                blockers.append(f"banned_opener:{label}:{opener}")

    hits = find_stopwords(payload_text(data), list(stopwords or []))
    for word in hits:
        warnings.append(f"stopword:{word}")

    return QualityLintResult(blockers=blockers, warnings=warnings)


def lint_article(
    payload: dict[str, Any] | None,
    profile: BrandContentProfile,
    *,
    platform: str | None = None,
    stopwords: list[str] | None = None,
) -> QualityLintResult:
    data = dict(payload or {})
    blockers: list[str] = []
    warnings: list[str] = []

    title = _str_field(data, "title")
    body = _str_field(data, "body_markdown")
    if not title:
        blockers.append("missing_title")
    if not body:
        blockers.append("empty_body")

    if platform:
        policy, _src = get_effective_platform_policy(profile, platform)
        if not policy.allows_content_type(ContentType.article):
            blockers.append("platform_content_type_not_allowed")
        if policy.max_text_length:
            from app.services.adapters.vk import variant_text

            if len(variant_text(data)) > policy.max_text_length:
                blockers.append("text_length_exceeded")

    hits = find_stopwords(payload_text(data), list(stopwords or []))
    for word in hits:
        warnings.append(f"stopword:{word}")
    return QualityLintResult(blockers=blockers, warnings=warnings)


def lint_content_payload(
    *,
    content_type: ContentType,
    payload: dict[str, Any] | None,
    profile: BrandContentProfile,
    stopwords: list[str] | None = None,
    platform: str | None = None,
) -> QualityLintResult:
    if content_type is ContentType.social_post:
        return lint_social_post(payload, profile, stopwords)
    if content_type is ContentType.article:
        return lint_article(payload, profile, platform=platform, stopwords=stopwords)
    return QualityLintResult()


def quality_payload_from_lint(
    lint: QualityLintResult,
    *,
    ai_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "blockers": list(lint.blockers),
        "warnings": list(lint.warnings),
        "scores": lint.scores,
        "lint": {"scores": lint.scores},
    }
    if ai_review is not None:
        out["ai_review"] = ai_review
    return out


def get_quality_blockers(payload: dict[str, Any] | None) -> list[str]:
    meta = (payload or {}).get("_meta")
    if not isinstance(meta, dict):
        return []
    quality = meta.get("quality")
    if not isinstance(quality, dict):
        return []
    blockers = quality.get("blockers")
    if isinstance(blockers, list):
        return [str(item) for item in blockers]
    return []


def is_variant_approved(variant: ContentVariant, piece: ContentPiece | None = None) -> bool:
    if approval_matches(variant.revision, variant.payload):
        return True
    meta = (variant.payload or {}).get("_meta")
    if isinstance(meta, dict) and meta.get("approved_at") and not meta.get("approval"):
        return int(meta.get("approved_revision") or variant.revision) == variant.revision
    return False


def store_quality_on_payload(
    payload: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(payload or {})
    meta = dict(merged.get("_meta") or {})
    meta["quality"] = quality
    merged["_meta"] = meta
    return merged


def store_approval_on_payload(
    payload: dict[str, Any],
    *,
    approved_at: str,
    approved_by: str,
    revision: int,
    checksum: str,
) -> dict[str, Any]:
    merged = dict(payload or {})
    meta = dict(merged.get("_meta") or {})
    meta["approved_at"] = approved_at
    meta["approved_by"] = approved_by
    meta["approved_revision"] = revision
    meta["approval"] = {
        "revision": revision,
        "payload_checksum": checksum,
        "approved_at": approved_at,
        "approved_by": approved_by,
    }
    merged["_meta"] = meta
    return merged


def run_formal_lint_for_variant(
    variant: ContentVariant,
    piece: ContentPiece,
    profile: BrandContentProfile,
    brand: BrandProfile,
) -> QualityLintResult:
    platform = None
    if variant.payload and isinstance(variant.payload.get("target_platform"), str):
        platform = variant.payload["target_platform"]
    return lint_content_payload(
        content_type=piece.type,
        payload=variant.payload,
        profile=profile,
        stopwords=list(brand.stopwords or []),
        platform=platform,
    )
