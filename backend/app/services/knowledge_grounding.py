from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from app.models import BrandContentProfile, KnowledgeMode
from app.services.lightrag_client import (
    LightRAGAuthError,
    LightRAGClient,
    LightRAGError,
    LightRAGQueryResult,
    LightRAGUnavailableError,
    get_lightrag_client,
)

logger = logging.getLogger(__name__)


class GroundingStatus(str, Enum):
    skipped = "skipped"
    grounded = "grounded"
    ungrounded = "ungrounded"
    blocked = "blocked"


@dataclass(frozen=True)
class GroundingReference:
    id: str
    file_path: str


@dataclass(frozen=True)
class GroundingResult:
    status: GroundingStatus
    context: str = ""
    references: list[GroundingReference] = field(default_factory=list)
    error_message: str | None = None
    warning: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class _ScopedRefs:
    context: str
    references: list[GroundingReference]
    filter_miss: bool = False
    content_missing: bool = False
    warning: str | None = None


def _match_filters(reference_id: str, file_path: str, filters: list[str]) -> bool:
    haystacks = (
        (file_path or "").lower(),
        (reference_id or "").lower(),
    )
    for raw in filters:
        needle = (raw or "").strip().lower()
        if not needle:
            continue
        if any(needle in hay for hay in haystacks):
            return True
    return False


def _rebuild_context_from_refs(matched: list) -> str:
    parts: list[str] = []
    for item in matched:
        content = getattr(item, "content", None)
        if content is None:
            continue
        text = str(content).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _apply_filters(
    result: LightRAGQueryResult,
    filters: list[str],
) -> _ScopedRefs:
    cleaned = [item for item in (filters or []) if (item or "").strip()]
    raw_refs = list(result.references or [])

    if not cleaned:
        refs = [
            GroundingReference(id=item.reference_id, file_path=item.file_path)
            for item in raw_refs
        ]
        return _ScopedRefs(context=result.response, references=refs)

    matched = [
        item
        for item in raw_refs
        if _match_filters(item.reference_id, item.file_path, cleaned)
    ]
    if not matched:
        return _ScopedRefs(context="", references=[], filter_miss=True)

    refs = [
        GroundingReference(id=item.reference_id, file_path=item.file_path)
        for item in matched
    ]
    scoped = _rebuild_context_from_refs(matched)
    if not scoped:
        return _ScopedRefs(
            context="",
            references=refs,
            content_missing=True,
            warning="matched references have no usable content",
        )
    return _ScopedRefs(context=scoped, references=refs)


def _fail(mode: KnowledgeMode, code: str, message: str) -> GroundingResult:
    if mode == KnowledgeMode.required:
        return GroundingResult(
            status=GroundingStatus.blocked,
            error_code=code,
            error_message=message,
        )
    return GroundingResult(
        status=GroundingStatus.ungrounded,
        error_code=code,
        error_message=message,
        warning=message,
    )


def ground_knowledge(
    profile: BrandContentProfile,
    query: str,
    *,
    mode: str = "mix",
    client: LightRAGClient | None = None,
) -> GroundingResult:
    knowledge_mode = profile.knowledge_mode
    if knowledge_mode == KnowledgeMode.off:
        return GroundingResult(status=GroundingStatus.skipped)

    text = (query or "").strip()
    if len(text) < 3:
        return _fail(knowledge_mode, "empty", "query must be at least 3 characters")

    rag = client or get_lightrag_client()
    try:
        result = rag.query(text, mode=mode)
    except LightRAGAuthError as exc:
        logger.warning("grounding_auth brand=%s", profile.brand_id)
        return _fail(knowledge_mode, "auth", exc.message)
    except LightRAGUnavailableError as exc:
        logger.warning("grounding_unavailable brand=%s", profile.brand_id)
        return _fail(knowledge_mode, "unavailable", exc.message)
    except LightRAGError as exc:
        logger.warning("grounding_error brand=%s code=%s", profile.brand_id, type(exc).__name__)
        return _fail(knowledge_mode, "error", exc.message)

    scoped = _apply_filters(result, list(profile.knowledge_filters or []))

    if scoped.filter_miss:
        return _fail(knowledge_mode, "filtered", "knowledge filters removed all references")

    if scoped.content_missing:
        message = scoped.warning or "matched references have no usable content"
        return _fail(knowledge_mode, "filtered", message)

    if not scoped.context.strip() and not scoped.references:
        return _fail(knowledge_mode, "empty", "LightRAG returned empty context")

    logger.info(
        "grounding_ok brand=%s mode=%s chars=%s refs=%s",
        profile.brand_id,
        knowledge_mode.value,
        len(scoped.context),
        len(scoped.references),
    )
    return GroundingResult(
        status=GroundingStatus.grounded,
        context=scoped.context,
        references=scoped.references,
    )
