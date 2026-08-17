import json
import logging
from typing import Any, Callable

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "cf3-v1"


class AIJobError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}


def _call_openai(messages: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise AIJobError("upstream_unavailable", "OpenAI API key is not configured")
    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.4,
        )
    except OpenAIError as exc:
        logger.warning("openai_error type=%s", type(exc).__name__)
        raise AIJobError("upstream_unavailable", "OpenAI request failed") from exc
    content = response.choices[0].message.content or ""
    usage = response.usage
    meta = {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
    logger.info(
        "openai_ok model=%s prompt_tokens=%s completion_tokens=%s",
        settings.openai_model,
        meta["prompt_tokens"],
        meta["completion_tokens"],
    )
    return content, meta


def _parse_model(model_cls: type[BaseModel], raw: str) -> BaseModel:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIJobError("schema_invalid", "Модель вернула не JSON", {"reason": "json"}) from exc
    if not isinstance(data, dict):
        raise AIJobError("schema_invalid", "Модель вернула не объект", {"reason": "not_object"})
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise AIJobError(
            "schema_invalid",
            "JSON не прошёл схему",
            {"reason": "pydantic"},
        ) from exc


def complete_json(
    model_cls: type[BaseModel],
    messages: list[dict[str, str]],
    extra_validator: Callable[[BaseModel], AIJobError | None] | None = None,
) -> tuple[BaseModel, dict[str, Any]]:
    raw, usage = _call_openai(messages)
    parsed, error = _try_validate(model_cls, raw, extra_validator)
    if parsed is not None:
        return parsed, {"usage": usage, "repaired": False, "prompt_version": PROMPT_VERSION}

    repair_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                "Your previous JSON failed validation. "
                f"Error code: {error.code}. Return corrected JSON only, no markdown."
            ),
        },
    ]
    raw2, usage2 = _call_openai(repair_messages)
    parsed2, error2 = _try_validate(model_cls, raw2, extra_validator)
    usage_total = {
        "prompt_tokens": usage["prompt_tokens"] + usage2["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"] + usage2["completion_tokens"],
        "total_tokens": usage["total_tokens"] + usage2["total_tokens"],
    }
    if parsed2 is None:
        assert error2 is not None
        raise error2
    return parsed2, {"usage": usage_total, "repaired": True, "prompt_version": PROMPT_VERSION}


def _try_validate(
    model_cls: type[BaseModel],
    raw: str,
    extra_validator: Callable[[BaseModel], AIJobError | None] | None,
) -> tuple[BaseModel | None, AIJobError | None]:
    try:
        parsed = _parse_model(model_cls, raw)
    except AIJobError as exc:
        return None, exc
    if extra_validator is not None:
        problem = extra_validator(parsed)
        if problem is not None:
            return None, problem
    return parsed, None
