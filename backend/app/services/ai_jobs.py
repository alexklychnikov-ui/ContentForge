import calendar
import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    BrandProfile,
    ChannelType,
    ContentPiece,
    ContentPlan,
    ContentType,
    ContentVariant,
    Holiday,
    Job,
    PlanItem,
    PlanGoal,
    PlanStatus,
    TrendSignal,
    TrendStatus,
)
from app.services.ai_client import AIJobError, PROMPT_VERSION, complete_json
from app.services.ai_schemas import (
    CONTENT_SCHEMA_BY_TYPE,
    PRIMARY_TEXT_FIELD,
    PlanAIResult,
    RewriteAI,
)
from app.services.catalog_service import list_holidays
from app.services.stopwords import find_stopwords, payload_text

PLAN_SYSTEM = (
    "You are ContentForge planner. Return JSON {\"items\":[...]}. "
    "Each item: date (YYYY-MM-DD), channel_type, content_type, theme, goal, hook. "
    "goal must be one of: awareness, traffic, lead, retention. "
    "Do not invent prices, legal guarantees, or promo dates missing from context. "
    "Mix RU holidays into themes when they fall in the month. "
    "Use only provided channels and content types. Dates must be in the requested month."
)

CONTENT_SYSTEM = (
    "You are ContentForge copywriter. Return JSON for the requested content type. "
    "Follow brand voice. Do not invent prices, legal guarantees, or promo dates. "
    "Respect stopwords by not using them."
)

REWRITE_SYSTEM = (
    "You rewrite only the selected fragment. Return JSON {replacement: string}. "
    "Do not repeat the rest of the document."
)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def holidays_for_plan(db: Session, brand_id: UUID, year: int, month: int) -> list[Holiday]:
    return list_holidays(db, year, month, brand_id)


def trends_for_plan(db: Session, brand_id: UUID, year: int, month: int) -> list[TrendSignal]:
    start, end = month_bounds(year, month)
    rows = list(
        db.scalars(
            select(TrendSignal).where(
                TrendSignal.status == TrendStatus.active,
                or_(TrendSignal.brand_id == brand_id, TrendSignal.brand_id.is_(None)),
            )
        ).all()
    )
    matched: list[TrendSignal] = []
    for trend in rows:
        if trend.starts_on is not None and trend.starts_on > end:
            continue
        if trend.ends_on is not None and trend.ends_on < start:
            continue
        matched.append(trend)
    return matched


def _holiday_public(rows: list[Holiday]) -> list[dict[str, str]]:
    return [{"date": item.date.isoformat(), "name": item.name} for item in rows]


def _trend_public(rows: list[TrendSignal]) -> list[dict[str, str]]:
    return [{"title": item.title, "note": item.note} for item in rows]


def _wrap_context(payload: dict[str, Any]) -> str:
    return "<<<CONTEXT\n" + json.dumps(payload, ensure_ascii=False) + "\nCONTEXT>>>"


def _plan_schema_hint(
    channels: list[ChannelType],
    targets: dict[ContentType, int],
    year: int,
    month: int,
) -> str:
    channel_list = "|".join(item.value for item in channels)
    type_list = "|".join(key.value for key in targets)
    goals = "|".join(item.value for item in PlanGoal)
    return (
        f"Schema example item: "
        f'{{"date":"{year}-{month:02d}-01","channel_type":"{channels[0].value}",'
        f'"content_type":"{next(iter(targets)).value}","theme":"...","goal":"awareness","hook":"..."}}. '
        f"Allowed channel_type: {channel_list}. Allowed content_type: {type_list}. "
        f"Allowed goal: {goals}. Dates only in {year}-{month:02d}."
    )


def execute_generate_plan(db: Session, job: Job, brand: BrandProfile) -> dict[str, Any]:
    payload = job.payload
    year = int(payload["year"])
    month = int(payload["month"])
    channels = [ChannelType(item) for item in payload.get("channels") or []]
    raw_targets = payload.get("targets") or {}
    targets = {ContentType(key): int(value) for key, value in raw_targets.items() if int(value) > 0}
    expected = sum(targets.values())
    include_holidays = bool(payload.get("include_holidays", True))
    include_trends = bool(payload.get("include_trends", True))
    holidays = holidays_for_plan(db, brand.id, year, month) if include_holidays else []
    trends = trends_for_plan(db, brand.id, year, month) if include_trends else []
    start, end = month_bounds(year, month)
    channel_values = {item.value for item in channels}

    context = {
        "year": year,
        "month": month,
        "channels": [item.value for item in channels],
        "targets": {key.value: value for key, value in targets.items()},
        "locale": payload.get("locale", brand.default_locale.value),
        "holidays": _holiday_public(holidays),
        "trends": _trend_public(trends),
        "brand": {
            "name": brand.name,
            "niche": brand.niche,
            "audience": brand.audience,
            "voice_tone": brand.voice_tone,
            "offers": list(brand.offers or []),
            "stopwords": list(brand.stopwords or []),
            "example_posts": list(brand.example_posts or []),
        },
        "item_count_required": expected,
    }
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {
            "role": "user",
            "content": _wrap_context(context)
            + f"\nReturn exactly {expected} items. "
            + _plan_schema_hint(channels, targets, year, month),
        },
    ]

    def _check(parsed: PlanAIResult) -> AIJobError | None:
        if len(parsed.items) != expected:
            return AIJobError(
                "schema_count_mismatch",
                f"items count must be {expected}, got {len(parsed.items)}",
                {"expected": expected, "got": len(parsed.items)},
            )
        by_type: dict[ContentType, int] = {key: 0 for key in ContentType}
        for item in parsed.items:
            if item.date < start or item.date > end:
                return AIJobError(
                    "schema_invalid",
                    f"item date {item.date.isoformat()} is outside {year}-{month:02d}",
                )
            if item.channel_type.value not in channel_values:
                return AIJobError(
                    "schema_invalid",
                    f"channel {item.channel_type.value} is not in requested channels",
                )
            by_type[item.content_type] = by_type.get(item.content_type, 0) + 1
        for content_type, count in targets.items():
            actual = by_type.get(content_type, 0)
            if actual != count:
                return AIJobError(
                    "schema_count_mismatch",
                    f"items for {content_type.value} must be {count}, got {actual}",
                    {"content_type": content_type.value, "expected": count, "got": actual},
                )
        return None

    result, meta = complete_json(PlanAIResult, messages, extra_validator=_check, temperature=0.2, max_repairs=2)
    assert isinstance(result, PlanAIResult)
    settings = get_settings()
    plan = ContentPlan(
        brand_id=brand.id,
        year=year,
        month=month,
        status=PlanStatus.draft,
        params={
            "channels": [item.value for item in channels],
            "targets": {key.value: value for key, value in targets.items()},
            "locale": payload.get("locale", brand.default_locale.value),
            "include_holidays": include_holidays,
            "include_trends": include_trends,
            "holidays_considered": _holiday_public(holidays),
            "trends_considered": _trend_public(trends),
        },
        model=settings.openai_model,
        created_by=job.created_by,
    )
    db.add(plan)
    db.flush()
    for index, item in enumerate(result.items):
        db.add(
            PlanItem(
                plan_id=plan.id,
                date=item.date,
                channel_type=item.channel_type,
                content_type=item.content_type,
                theme=item.theme,
                goal=item.goal,
                hook=item.hook,
                sort_order=index,
            )
        )
    db.flush()
    return {
        "plan_id": str(plan.id),
        "item_count": len(result.items),
        "holidays_considered": _holiday_public(holidays),
        "trends_considered": _trend_public(trends),
        "prompt_version": meta.get("prompt_version", PROMPT_VERSION),
        "usage": meta.get("usage") or {},
        "repaired": bool(meta.get("repaired")),
        "model": settings.openai_model,
    }


def execute_generate_content(db: Session, job: Job, brand: BrandProfile) -> dict[str, Any]:
    payload = job.payload
    piece = db.get(ContentPiece, UUID(str(payload["piece_id"])))
    if piece is None or piece.brand_id != brand.id:
        raise AIJobError("not_found", "Материал не найден")
    schema = CONTENT_SCHEMA_BY_TYPE[piece.type]
    label = str(payload.get("variant_label") or "A")
    channel = payload.get("channel_type")
    extra = str(payload.get("extra_instructions") or "")
    item = piece.plan_item
    context = {
        "type": piece.type.value,
        "locale": piece.locale.value,
        "channel_type": channel,
        "theme": item.theme if item is not None else "",
        "hook": item.hook if item is not None else "",
        "goal": item.goal.value if item is not None else "",
        "extra_instructions": extra,
        "brand": {
            "name": brand.name,
            "niche": brand.niche,
            "audience": brand.audience,
            "voice_tone": brand.voice_tone,
            "offers": list(brand.offers or []),
            "stopwords": list(brand.stopwords or []),
            "example_posts": list(brand.example_posts or []),
        },
    }
    messages = [
        {"role": "system", "content": CONTENT_SYSTEM},
        {"role": "user", "content": _wrap_context(context) + "\nReturn JSON for this type."},
    ]
    result, meta = complete_json(schema, messages)
    variant_payload = result.model_dump()
    variant = next((row for row in piece.variants if row.label == label), None)
    if variant is None:
        variant = ContentVariant(piece_id=piece.id, label=label, payload=variant_payload, revision=1)
        db.add(variant)
    else:
        if variant.is_immutable:
            raise AIJobError("conflict", "Вариант уже опубликован и иммутабелен")
        variant.payload = variant_payload
        variant.revision += 1
    db.flush()
    hits = find_stopwords(payload_text(variant_payload), list(brand.stopwords or []))
    settings = get_settings()
    return {
        "piece_id": str(piece.id),
        "variant_id": str(variant.id),
        "variant_label": label,
        "stopword_warning": bool(hits),
        "stopword_hits": hits,
        "prompt_version": meta.get("prompt_version", PROMPT_VERSION),
        "usage": meta.get("usage") or {},
        "repaired": bool(meta.get("repaired")),
        "model": settings.openai_model,
    }


def execute_rewrite(db: Session, job: Job, brand: BrandProfile) -> dict[str, Any]:
    payload = job.payload
    variant = db.get(ContentVariant, UUID(str(payload["variant_id"])))
    if variant is None:
        raise AIJobError("not_found", "Вариант не найден")
    piece = variant.piece
    if piece.brand_id != brand.id:
        raise AIJobError("not_found", "Вариант не найден")
    if variant.is_immutable:
        raise AIJobError("conflict", "Вариант уже опубликован и иммутабелен")
    field = str(payload.get("field") or PRIMARY_TEXT_FIELD[piece.type])
    start = int(payload["start"])
    end = int(payload["end"])
    current = dict(variant.payload or {})
    source = current.get(field)
    if not isinstance(source, str):
        raise AIJobError("validation_error", "Поле для rewrite не текстовое")
    if start < 0 or end > len(source) or start >= end:
        raise AIJobError("validation_error", "Некорректный selection")
    selected = source[start:end]
    prefix = source[:start]
    suffix = source[end:]
    context = {
        "field": field,
        "selected_text": selected,
        "type": piece.type.value,
        "extra_instructions": str(payload.get("extra_instructions") or ""),
        "voice_tone": brand.voice_tone,
        "stopwords": list(brand.stopwords or []),
    }
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {
            "role": "user",
            "content": _wrap_context(context) + "\nRewrite only selected_text.",
        },
    ]
    result, meta = complete_json(RewriteAI, messages)
    assert isinstance(result, RewriteAI)
    current[field] = prefix + result.replacement + suffix
    variant.payload = current
    variant.revision += 1
    db.flush()
    hits = find_stopwords(payload_text(current), list(brand.stopwords or []))
    return {
        "piece_id": str(piece.id),
        "variant_id": str(variant.id),
        "field": field,
        "stopword_warning": bool(hits),
        "prompt_version": meta.get("prompt_version", PROMPT_VERSION),
        "usage": meta.get("usage") or {},
        "repaired": bool(meta.get("repaired")),
    }
