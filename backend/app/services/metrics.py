from typing import Any

SOCIAL_METRICS = (
    "impressions",
    "reach",
    "likes",
    "comments",
    "shares",
    "clicks",
    "saves",
    "views",
)
GMAIL_FACT_METRICS = ("sent", "failed")
GMAIL_UNAVAILABLE_METRICS = ("opened", "clicked", "unsubscribed")
ALL_METRIC_KEYS = SOCIAL_METRICS + GMAIL_FACT_METRICS + GMAIL_UNAVAILABLE_METRICS
KNOWN_METRICS = frozenset(ALL_METRIC_KEYS)


def empty_unavailable(*, reason: str = "not_supported") -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "metrics": {},
        "unavailable": list(ALL_METRIC_KEYS),
        "raw": {"reason": reason},
    }


def pack_available(metrics: dict[str, int], *, raw: dict | None = None) -> dict[str, Any]:
    available = {
        key: int(value)
        for key, value in metrics.items()
        if key in KNOWN_METRICS and isinstance(value, int)
    }
    unavailable = [key for key in ALL_METRIC_KEYS if key not in available]
    if not available:
        availability = "unavailable"
    elif unavailable:
        availability = "partial"
    else:
        availability = "available"
    return {
        "availability": availability,
        "metrics": available,
        "unavailable": unavailable,
        "raw": raw or {},
    }


def from_gmail_meta(meta: dict | None) -> dict[str, Any]:
    data = meta or {}
    facts: dict[str, int] = {}
    sent = data.get("sent_count")
    failed = data.get("failed_count")
    if isinstance(sent, int):
        facts["sent"] = sent
    if isinstance(failed, int):
        facts["failed"] = failed
    return pack_available(facts, raw={"source": "publication.meta"})


def split_adapter_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    normalized = {
        "availability": payload.get("availability") or "unavailable",
        "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
        "unavailable": payload.get("unavailable")
        if isinstance(payload.get("unavailable"), list)
        else list(ALL_METRIC_KEYS),
    }
    metrics = {
        key: int(value)
        for key, value in normalized["metrics"].items()
        if key in KNOWN_METRICS and isinstance(value, int)
    }
    normalized["metrics"] = metrics
    if not metrics:
        normalized["availability"] = "unavailable"
        normalized["unavailable"] = list(ALL_METRIC_KEYS)
    return normalized, raw
