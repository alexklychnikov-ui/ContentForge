import json
import logging
from typing import Any, Callable

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "cf3-v2"


class AIJobError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}


def _llm_credentials() -> tuple[str, str | None, str]:
    settings = get_settings()
    proxy_key = (settings.proxy_api_key or "").strip()
    proxy_base = (settings.proxy_base_url or "").strip() or None
    openai_key = (settings.openai_api_key or "").strip()
    api_key = proxy_key or openai_key
    if not api_key:
        raise AIJobError("upstream_unavailable", "LLM API key is not configured")
    model = (settings.openai_model or "").strip() or "anthropic/claude-sonnet-5-5"
    return api_key, proxy_base if proxy_key else None, model


def _call_openai(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
) -> tuple[str, dict[str, int]]:
    api_key, base_url, model = _llm_credentials()
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    # Claude via ProxyAPI accepts JSON mode through OpenAI-compatible translation.
    create_kwargs["response_format"] = {"type": "json_object"}
    try:
        response = client.chat.completions.create(**create_kwargs)
    except OpenAIError as exc:
        message = str(exc).lower()
        if "response_format" in message:
            create_kwargs.pop("response_format", None)
            try:
                response = client.chat.completions.create(**create_kwargs)
            except OpenAIError as retry_exc:
                logger.warning("openai_error type=%s", type(retry_exc).__name__)
                raise AIJobError("upstream_unavailable", "LLM request failed") from retry_exc
        else:
            logger.warning("openai_error type=%s", type(exc).__name__)
            raise AIJobError("upstream_unavailable", "LLM request failed") from exc
    content = response.choices[0].message.content or ""
    usage = response.usage
    meta = {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
    logger.info(
        "openai_ok model=%s base=%s prompt_tokens=%s completion_tokens=%s",
        model,
        base_url or "default",
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
            {"reason": "pydantic", "errors": exc.errors(include_url=False)[:8]},
        ) from exc


def _repair_hint(error: AIJobError) -> str:
    parts = [f"Error code: {error.code}.", error.message]
    if error.details:
        parts.append(json.dumps(error.details, ensure_ascii=False))
    return " ".join(parts) + " Return corrected JSON only, no markdown."


def complete_json(
    model_cls: type[BaseModel],
    messages: list[dict[str, str]],
    extra_validator: Callable[[BaseModel], AIJobError | None] | None = None,
    *,
    temperature: float = 0.4,
    max_repairs: int = 2,
) -> tuple[BaseModel, dict[str, Any]]:
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    current_messages = list(messages)
    last_error: AIJobError | None = None
    repaired = False

    for attempt in range(max_repairs + 1):
        temp = temperature if attempt == 0 else min(temperature, 0.2)
        raw, usage = _call_openai(current_messages, temperature=temp)
        usage_total = {
            "prompt_tokens": usage_total["prompt_tokens"] + usage["prompt_tokens"],
            "completion_tokens": usage_total["completion_tokens"] + usage["completion_tokens"],
            "total_tokens": usage_total["total_tokens"] + usage["total_tokens"],
        }
        parsed, error = _try_validate(model_cls, raw, extra_validator)
        if parsed is not None:
            return parsed, {
                "usage": usage_total,
                "repaired": repaired,
                "prompt_version": PROMPT_VERSION,
            }
        assert error is not None
        last_error = error
        if attempt >= max_repairs:
            break
        repaired = True
        current_messages = [
            *messages,
            {
                "role": "user",
                "content": "Your previous JSON failed validation. " + _repair_hint(error),
            },
        ]

    assert last_error is not None
    raise last_error


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
