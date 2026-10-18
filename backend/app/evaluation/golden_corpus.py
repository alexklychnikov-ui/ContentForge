from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "data" / "nodex_golden_corpus.json"

MVP_PLATFORMS = frozenset({"vk", "instagram", "tenchat"})
SOCIAL = "social_post"
ARTICLE = "article"


def load_golden_corpus(path: Path | None = None) -> dict[str, Any]:
    p = path or CORPUS_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def validate_corpus_structure(corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    topics = corpus.get("topics")
    if not isinstance(topics, list) or not topics:
        errors.append("topics must be a non-empty list")
        return errors

    rubric = corpus.get("rubric_dimensions")
    if not isinstance(rubric, list) or len(rubric) < 4:
        errors.append("rubric_dimensions must list at least 4 dimensions")

    by_platform: dict[str, list[dict[str, Any]]] = {p: [] for p in MVP_PLATFORMS}
    for i, item in enumerate(topics):
        if not isinstance(item, dict):
            errors.append(f"topic[{i}] must be object")
            continue
        platform = item.get("platform")
        ctype = item.get("content_type")
        theme = item.get("theme")
        if platform not in MVP_PLATFORMS:
            errors.append(f"topic[{i}] invalid platform: {platform}")
        if ctype not in (SOCIAL, ARTICLE):
            errors.append(f"topic[{i}] invalid content_type: {ctype}")
        if not isinstance(theme, str) or not theme.strip():
            errors.append(f"topic[{i}] missing theme")
        if platform in by_platform:
            by_platform[platform].append(item)

    for platform, items in by_platform.items():
        if len(items) < 4:
            errors.append(f"{platform}: need at least 4 topics, got {len(items)}")
        types = {t.get("content_type") for t in items}
        if SOCIAL not in types:
            errors.append(f"{platform}: missing social_post")
        if platform == "instagram" and ARTICLE in types:
            errors.append("instagram: article must not be in golden corpus for MVP")
        if platform in ("vk", "tenchat") and ARTICLE not in types:
            errors.append(f"{platform}: missing article long-form sample")

    return errors
