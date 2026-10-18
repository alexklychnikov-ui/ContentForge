from __future__ import annotations

import hashlib
import json
from typing import Any

PUBLISHABLE_SCALAR_KEYS = (
    "headline",
    "lead",
    "scene",
    "body",
    "text",
    "body_markdown",
    "takeaway",
    "cta",
    "hashtags",
    "alt_text",
    "title",
    "excerpt",
    "seo_title",
    "seo_description",
    "slug",
    "target_platform",
    "content_type",
    "subject",
    "preheader",
)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    return value


def canonical_publishable_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    out: dict[str, Any] = {}
    for key in PUBLISHABLE_SCALAR_KEYS:
        if key not in data:
            continue
        value = data[key]
        if value is None:
            continue
        if key == "hashtags" and isinstance(value, list):
            out[key] = [_normalize_value(v) for v in value if str(v).strip()]
        else:
            out[key] = _normalize_value(value)
    return dict(sorted(out.items(), key=lambda item: item[0]))


def payload_checksum(payload: dict[str, Any] | None) -> str:
    canonical = canonical_publishable_payload(payload)
    raw = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def store_checksum_meta(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload or {})
    meta = dict(merged.get("_meta") or {})
    meta["payload_checksum"] = payload_checksum(merged)
    merged["_meta"] = meta
    return merged


def clear_text_approval(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload or {})
    meta = dict(merged.get("_meta") or {})
    meta.pop("approved_at", None)
    meta.pop("approved_by", None)
    meta.pop("approval", None)
    merged["_meta"] = meta
    return merged


def approval_matches(variant_revision: int, payload: dict[str, Any] | None) -> bool:
    meta = (payload or {}).get("_meta")
    if not isinstance(meta, dict):
        return False
    approval = meta.get("approval")
    if isinstance(approval, dict):
        if int(approval.get("revision") or 0) != variant_revision:
            return False
        expected = str(approval.get("payload_checksum") or "")
        return expected == payload_checksum(payload)
    if meta.get("approved_at"):
        return int(meta.get("approved_revision") or variant_revision) == variant_revision
    return False
