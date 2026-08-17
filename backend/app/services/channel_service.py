import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.errors import AppError
from app.models import (
    ChannelAccount,
    ChannelStatus,
    ChannelType,
    Membership,
    User,
)
from app.schemas import ChannelCredentialsRequest, ChannelHealth, ChannelPublic
from app.security import utc_now
from app.services.adapters import get_adapter
from app.services.audit import write_audit
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.publish_service import cancel_scheduled_for_channel
from app.services.token_crypto import encrypt_secret

META_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "bot_token",
    "app_password",
    "password",
    "token_ciphertext",
    "refresh_ciphertext",
}


_TELEGRAM_BOT_TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]{8,}$")
_TELEGRAM_AT_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$")
_TELEGRAM_CHAT_RE = re.compile(r"^-100\d+$")


def public_meta(meta: dict | None) -> dict:
    return {key: value for key, value in (meta or {}).items() if key.lower() not in META_SECRET_KEYS}


def channel_to_public(account: ChannelAccount) -> ChannelPublic:
    status = account.status
    if account.revoked_at is not None or account.status == ChannelStatus.revoked:
        status = ChannelStatus.revoked
    return ChannelPublic(
        id=account.id,
        brand_id=account.brand_id,
        type=account.type,
        display_name=account.display_name,
        status=status,
        scopes=list(account.scopes or []),
        token_expires_at=account.token_expires_at,
        external_account_id=account.external_account_id,
        meta=public_meta(account.meta),
        revoked_at=account.revoked_at,
    )


def require_channel(
    db: Session,
    user: User,
    channel_id: UUID,
    allowed_roles: set | None = None,
) -> tuple[ChannelAccount, Membership]:
    account = db.get(ChannelAccount, channel_id)
    if account is None:
        raise AppError(404, "not_found", "Канал не найден")
    try:
        _brand, membership = require_brand(db, user, account.brand_id, allowed_roles)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Канал не найден") from exc
        raise
    return account, membership


def list_channels(db: Session, user: User, brand_id: UUID) -> list[ChannelAccount]:
    brand, _membership = require_brand(db, user, brand_id)
    return list(
        db.scalars(
            select(ChannelAccount)
            .where(
                ChannelAccount.brand_id == brand.id,
                ChannelAccount.revoked_at.is_(None),
                ChannelAccount.status != ChannelStatus.revoked,
            )
            .order_by(ChannelAccount.created_at.desc())
        ).all()
    )


def _require_field(value: str | None, field: str) -> str:
    stripped = (value or "").strip()
    if not stripped:
        raise AppError(400, "validation_error", f"Не указан {field}", {"field": field})
    return stripped


def _require_telegram_bot_token(value: str) -> str:
    if not _TELEGRAM_BOT_TOKEN_RE.fullmatch(value):
        raise AppError(
            422,
            "validation_error",
            "Неверный bot token: вставьте token от @BotFather",
            {"field": "bot_token"},
        )
    return value


def _require_telegram_channel_id(value: str) -> str:
    if _TELEGRAM_AT_RE.fullmatch(value) or _TELEGRAM_CHAT_RE.fullmatch(value):
        return value
    raise AppError(
        422,
        "validation_error",
        "нужен @channel или -100…, не email",
        {"field": "channel_id"},
    )


def _secret_and_meta(
    channel_type: ChannelType, payload: ChannelCredentialsRequest
) -> tuple[str, str | None, dict, str | None]:
    meta: dict = {"pdn_consent": True, "pdn_consent_at": utc_now().isoformat()}
    refresh: str | None = None
    external_id = (payload.external_account_id or "").strip() or None

    if channel_type == ChannelType.telegram:
        secret = _require_telegram_bot_token(_require_field(payload.bot_token, "bot_token"))
        channel_id = _require_telegram_channel_id(_require_field(payload.channel_id, "channel_id"))
        meta["channel_id"] = channel_id
        return secret, refresh, meta, external_id or channel_id

    if channel_type == ChannelType.wordpress:
        secret = _require_field(payload.app_password, "app_password")
        site_url = _require_field(payload.site_url, "site_url")
        username = _require_field(payload.username, "username")
        meta["blog_url"] = site_url
        meta["site_url"] = site_url
        meta["username"] = username
        return secret, refresh, meta, external_id or site_url

    if channel_type == ChannelType.gmail:
        secret = _require_field(payload.app_password, "app_password")
        from_email = _require_field(
            str(payload.from_email) if payload.from_email else None, "from_email"
        ).lower()
        smtp_host = (payload.smtp_host or "smtp.gmail.com").strip() or "smtp.gmail.com"
        smtp_port = payload.smtp_port or 587
        meta["gmail_from"] = from_email
        meta["smtp_host"] = smtp_host
        meta["smtp_port"] = smtp_port
        return secret, refresh, meta, external_id or from_email

    if channel_type == ChannelType.vk:
        secret = _require_field(payload.access_token, "access_token")
        if payload.group_id:
            meta["group_id"] = payload.group_id.strip()
        return secret, refresh, meta, external_id or meta.get("group_id")

    if channel_type == ChannelType.instagram:
        secret = _require_field(payload.access_token, "access_token")
        ig_user_id = _require_field(payload.ig_user_id, "ig_user_id")
        meta["ig_user_id"] = ig_user_id
        if payload.refresh_token:
            refresh = payload.refresh_token.strip()
        return secret, refresh, meta, external_id or ig_user_id

    _never: ChannelType = channel_type
    raise AppError(400, "unsupported_channel", "Неизвестный тип канала", {"type": _never.value})


def save_credentials(
    db: Session,
    user: User,
    brand_id: UUID,
    channel_type: ChannelType,
    payload: ChannelCredentialsRequest,
    ip: str | None = None,
) -> ChannelAccount:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    if payload.pdn_consent is not True:
        raise AppError(400, "pdn_consent_required", "Необходимо согласие на обработку ПДн")
    secret, refresh_plain, meta, external_id = _secret_and_meta(channel_type, payload)
    display_name = (payload.display_name or "").strip() or channel_type.value
    account = ChannelAccount(
        brand_id=brand.id,
        type=channel_type,
        display_name=display_name,
        status=ChannelStatus.connected,
        scopes=list(payload.scopes or []),
        token_ciphertext=encrypt_secret(secret),
        refresh_ciphertext=encrypt_secret(refresh_plain) if refresh_plain else None,
        token_expires_at=payload.token_expires_at,
        external_account_id=external_id,
        meta=meta,
        revoked_at=None,
    )
    db.add(account)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="connect_channel",
        entity_type="channel_account",
        entity_id=account.id,
        ip=ip,
        data={"type": channel_type.value, "pdn_consent": True},
    )
    return account


def stub_health(db: Session, user: User, channel_id: UUID) -> ChannelHealth:
    account, _membership = require_channel(db, user, channel_id, MUTATE_BRAND_ROLES)
    result = get_adapter(account.type).health(account)
    account.status = result.status
    meta = dict(account.meta or {})
    if result.status == ChannelStatus.revoked:
        meta.pop("health_reason", None)
    elif result.reason:
        meta["health_reason"] = result.reason
    elif result.ok:
        meta["health_reason"] = "ok"
    else:
        meta.pop("health_reason", None)
    account.meta = meta
    flag_modified(account, "meta")
    db.flush()
    return result


def revoke_channel(db: Session, user: User, channel_id: UUID, ip: str | None = None) -> None:
    account, _membership = require_channel(db, user, channel_id, MUTATE_BRAND_ROLES)
    account.token_ciphertext = None
    account.refresh_ciphertext = None
    account.status = ChannelStatus.revoked
    account.revoked_at = utc_now()
    cancel_scheduled_for_channel(db, account.id)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="revoke_channel",
        entity_type="channel_account",
        entity_id=account.id,
        ip=ip,
        data={"type": account.type.value},
    )
