import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip, get_current_user
from app.errors import AppError
from app.models import ChannelType, User
from app.schemas import ChannelCredentialsRequest, ChannelHealth, ChannelPublic, OAuthStartResponse
from app.services.channel_service import (
    channel_to_public,
    list_channels,
    revoke_channel,
    save_credentials,
    stub_health,
)
from app.services.meta_oauth import (
    build_meta_auth_url,
    complete_instagram_oauth,
    decode_meta_oauth_state,
    encode_meta_oauth_state,
)

router = APIRouter(tags=["channels"])
logger = logging.getLogger(__name__)


@router.get("/brands/{brand_id}/channels", response_model=list[ChannelPublic])
def get_channels(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChannelPublic]:
    return [channel_to_public(item) for item in list_channels(db, user, brand_id)]


@router.post(
    "/brands/{brand_id}/channels/{type}/credentials",
    response_model=ChannelPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_credentials(
    brand_id: UUID,
    type: ChannelType,
    payload: ChannelCredentialsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChannelPublic:
    account = save_credentials(
        db, user, brand_id, type, payload, ip=client_ip(request)
    )
    return channel_to_public(account)


@router.post("/channels/{channel_id}/health", response_model=ChannelHealth)
def post_health(
    channel_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChannelHealth:
    return stub_health(db, user, channel_id)


@router.post(
    "/brands/{brand_id}/channels/instagram/oauth/start",
    response_model=OAuthStartResponse,
)
def instagram_oauth_start(
    brand_id: UUID,
    user: User = Depends(get_current_user),
) -> OAuthStartResponse:
    state = encode_meta_oauth_state(user.id, brand_id)
    return OAuthStartResponse(auth_url=build_meta_auth_url(state), state=state)


@router.get("/channels/oauth/callback")
def meta_oauth_callback(
    request: Request,
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    web = settings.public_web_url.rstrip("/")
    if error:
        detail = (error_description or error)[:180]
        return RedirectResponse(f"{web}/channels?oauth_error={detail}", status_code=302)
    if not code:
        return RedirectResponse(f"{web}/channels?oauth_error=missing_code", status_code=302)
    try:
        user_id, brand_id = decode_meta_oauth_state(state)
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise AppError(401, "unauthorized", "Пользователь не найден")
        complete_instagram_oauth(db, user, brand_id, code, ip=client_ip(request))
        db.commit()
    except AppError as exc:
        db.rollback()
        return RedirectResponse(
            f"{web}/channels?oauth_error={exc.message[:180]}",
            status_code=302,
        )
    except Exception:
        db.rollback()
        logger.exception("meta_oauth_callback_failed")
        return RedirectResponse(f"{web}/channels?oauth_error=oauth_failed", status_code=302)
    return RedirectResponse(f"{web}/channels?oauth=instagram_ok", status_code=302)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    channel_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    revoke_channel(db, user, channel_id, ip=client_ip(request))
