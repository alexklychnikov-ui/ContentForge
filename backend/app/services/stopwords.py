from typing import Any

from app.errors import AppError
from app.models import BrandProfile, ContentVariant, Membership, MembershipRole


def find_stopwords(text: str, stopwords: list[str]) -> list[str]:
    hay = text.casefold()
    hits: list[str] = []
    seen: set[str] = set()
    for word in stopwords:
        needle = str(word).strip().casefold()
        if not needle or needle in seen:
            continue
        if needle in hay:
            hits.append(word)
            seen.add(needle)
    return hits


def payload_text(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    parts: list[str] = []
    for value in payload.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if item is not None)
        elif isinstance(value, dict):
            parts.append(payload_text(value))
    return "\n".join(parts)


def variant_stopword_hits(brand: BrandProfile, variant: ContentVariant) -> list[str]:
    return find_stopwords(payload_text(variant.payload), list(brand.stopwords or []))


def assert_publish_allowed(
    brand: BrandProfile,
    variant: ContentVariant,
    membership: Membership,
    stopword_override: bool,
) -> list[str]:
    hits = variant_stopword_hits(brand, variant)
    if not hits:
        return []
    if not stopword_override:
        raise AppError(
            409,
            "stopword_violation",
            "Текст содержит стоп-слова бренда",
            {"hits": hits},
        )
    if membership.role is not MembershipRole.owner:
        raise AppError(403, "forbidden", "Override стоп-слов доступен только Owner")
    return hits
