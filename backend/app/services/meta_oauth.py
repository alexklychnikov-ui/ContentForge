import logging
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import ChannelType, User
from app.schemas import ChannelCredentialsRequest
from app.security import as_utc, utc_now
from app.services.channel_service import save_credentials

logger = logging.getLogger(__name__)

META_GRAPH = "https://graph.facebook.com/v21.0"
META_DIALOG = "https://www.facebook.com/v21.0/dialog/oauth"
META_SCOPES = ",".join(
    [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
        "pages_read_engagement",
        "business_management",
    ]
)


def meta_redirect_uri() -> str:
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/v1/channels/oauth/callback"


def encode_meta_oauth_state(user_id: UUID, brand_id: UUID) -> str:
    settings = get_settings()
    now = utc_now()
    expires_at = now + timedelta(minutes=15)
    payload = {
        "sub": str(user_id),
        "bid": str(brand_id),
        "typ": "meta_oauth",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_meta_oauth_state(state: str) -> tuple[UUID, UUID]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            state,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "bid", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise AppError(400, "invalid_state", "Некорректный OAuth state") from exc
    if payload.get("typ") != "meta_oauth":
        raise AppError(400, "invalid_state", "Некорректный OAuth state")
    return UUID(str(payload["sub"])), UUID(str(payload["bid"]))


def build_meta_auth_url(state: str) -> str:
    settings = get_settings()
    if not settings.meta_app_id:
        raise AppError(503, "meta_not_configured", "META_APP_ID не задан на сервере")
    query = urlencode(
        {
            "client_id": settings.meta_app_id,
            "redirect_uri": meta_redirect_uri(),
            "scope": META_SCOPES,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{META_DIALOG}?{query}"


def _graph_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0, follow_redirects=False, trust_env=False) as client:
        response = client.get(f"{META_GRAPH}{path}", params=params)
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "meta_error", "Meta вернула не-JSON") from exc
    if response.status_code >= 400 or not isinstance(payload, dict):
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("error", {}).get("message") or payload.get("error_description") or "")
        raise AppError(502, "meta_error", message or "Ошибка Meta Graph API")
    return payload


def exchange_code_for_token(code: str) -> str:
    settings = get_settings()
    if not settings.meta_app_secret:
        raise AppError(503, "meta_not_configured", "META_APP_SECRET не задан на сервере")
    payload = _graph_get(
        "/oauth/access_token",
        {
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": meta_redirect_uri(),
            "code": code,
        },
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise AppError(502, "meta_error", "Meta не вернула access_token")
    return token


def resolve_instagram_account(user_access_token: str) -> tuple[str, str, str]:
    payload = _graph_get(
        "/me/accounts",
        {
            "access_token": user_access_token,
            "fields": "id,name,access_token,instagram_business_account",
        },
    )
    pages = payload.get("data")
    if not isinstance(pages, list):
        raise AppError(502, "meta_error", "Не удалось получить страницы Facebook")
    for page in pages:
        if not isinstance(page, dict):
            continue
        ig = page.get("instagram_business_account")
        if not isinstance(ig, dict) or not ig.get("id"):
            continue
        page_token = str(page.get("access_token") or user_access_token)
        ig_user_id = str(ig["id"])
        page_name = str(page.get("name") or "Instagram")
        return page_token, ig_user_id, page_name
    raise AppError(
        400,
        "no_instagram_account",
        "У Facebook Page нет привязанного Instagram Professional. Проверьте ContentForge Test.",
    )


def complete_instagram_oauth(
    db: Session,
    user: User,
    brand_id: UUID,
    code: str,
    ip: str | None = None,
) -> None:
    user_token = exchange_code_for_token(code)
    page_token, ig_user_id, page_name = resolve_instagram_account(user_token)
    save_credentials(
        db,
        user,
        brand_id,
        ChannelType.instagram,
        ChannelCredentialsRequest(
            pdn_consent=True,
            display_name=page_name,
            access_token=page_token,
            ig_user_id=ig_user_id,
            scopes=META_SCOPES.split(","),
            external_account_id=ig_user_id,
        ),
        ip=ip,
    )
    logger.info("instagram_oauth_connected brand_id=%s ig_user_id=%s", brand_id, ig_user_id)
