import calendar
import json
import re

from app.services.ai_client import AIJobError, PROMPT_VERSION
from app.services.ai_schemas import (
    ArticleAI,
    EmailAI,
    PlanAIResult,
    RewriteAI,
    SocialPostAI,
)

CONTEXT_RE = re.compile(r"<<<CONTEXT\n(.*)\nCONTEXT>>>", re.S)

PLAN_JAN = {
    "year": 2026,
    "month": 1,
    "channels": ["telegram", "wordpress", "gmail"],
    "targets": {"social_post": 2, "article": 1, "email": 1},
    "locale": "ru",
}


def parse_context(messages: list[dict[str, str]]) -> dict:
    for message in reversed(messages):
        match = CONTEXT_RE.search(message.get("content") or "")
        if match:
            return json.loads(match.group(1))
    return {}


def build_plan_payload(context: dict) -> dict:
    year = int(context["year"])
    month = int(context["month"])
    channels = list(context["channels"])
    targets = dict(context["targets"])
    holidays = list(context.get("holidays") or [])
    last = calendar.monthrange(year, month)[1]
    sequence: list[str] = []
    for content_type, count in targets.items():
        sequence.extend([content_type] * int(count))
    items = []
    for index, content_type in enumerate(sequence):
        day = 1 + (index % last)
        theme = f"Тема {index + 1}"
        if holidays and index == 0:
            theme = f"{holidays[0]['name']}: контент к дате"
        items.append(
            {
                "date": f"{year:04d}-{month:02d}-{day:02d}",
                "channel_type": channels[index % len(channels)],
                "content_type": content_type,
                "theme": theme,
                "goal": "awareness",
                "hook": "Хук для аудитории",
            }
        )
    return {"items": items}


def openai_ok(model_cls, messages, extra_validator=None):
    context = parse_context(messages)
    if model_cls is PlanAIResult:
        data = build_plan_payload(context)
    elif model_cls is RewriteAI:
        selected = context.get("selected_text") or "X"
        data = {"replacement": f"NEW:{selected}"}
    elif model_cls is SocialPostAI:
        data = {
            "text": "Пост про оффер без запрещённых формулировок",
            "cta": "Написать нам",
            "hashtags": ["b2b"],
            "alt_text": "обложка",
        }
    elif model_cls is ArticleAI:
        data = {
            "title": "Статья про продукт",
            "excerpt": "Кратко",
            "body_markdown": "Тело статьи",
            "seo_title": "SEO",
            "seo_description": "desc",
            "slug": "statya",
        }
    elif model_cls is EmailAI:
        data = {
            "subject": "Письмо клиентам",
            "preheader": "pre",
            "body_markdown": "Текст письма",
        }
    else:
        raise AssertionError(f"unexpected schema {model_cls}")
    parsed = model_cls.model_validate(data)
    if extra_validator is not None:
        problem = extra_validator(parsed)
        if problem is not None:
            raise problem
    return parsed, {
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "repaired": False,
        "prompt_version": PROMPT_VERSION,
    }


def openai_invalid(_model_cls, _messages, extra_validator=None):
    raise AIJobError("schema_invalid", "Модель вернула не JSON")


def openai_count_mismatch(model_cls, messages, extra_validator=None):
    if model_cls is not PlanAIResult:
        return openai_ok(model_cls, messages, extra_validator)
    parsed = PlanAIResult.model_validate({"items": []})
    if extra_validator is not None:
        problem = extra_validator(parsed)
        if problem is not None:
            raise problem
    return parsed, {
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "repaired": True,
        "prompt_version": PROMPT_VERSION,
    }


def install_openai_mock(monkeypatch, impl=openai_ok) -> None:
    def _no_live(*_args, **_kwargs):
        raise AssertionError("live OpenAI must not be called in tests")

    monkeypatch.setattr("app.services.ai_jobs.complete_json", impl)
    monkeypatch.setattr("app.services.ai_client.complete_json", impl)
    monkeypatch.setattr("app.services.ai_client._call_openai", _no_live)
