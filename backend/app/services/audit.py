from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.logutil import redact_log_text, request_id_ctx
from app.models import AuditLog

_SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "ciphertext",
    "api_key",
    "apikey",
)


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                continue
            cleaned[key] = scrub_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    if isinstance(value, str):
        return redact_log_text(value)
    return value


def write_audit(
    db: Session,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    ip: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditLog:
    payload = scrub_secrets(data or {})
    request_id = request_id_ctx.get()
    if request_id and "request_id" not in payload:
        payload["request_id"] = request_id
    row = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        data=payload,
    )
    db.add(row)
    db.flush()
    return row
