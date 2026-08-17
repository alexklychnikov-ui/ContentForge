from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import ChannelType, User
from app.schemas import ChannelCredentialsRequest, ChannelHealth, ChannelPublic
from app.services.channel_service import (
    channel_to_public,
    list_channels,
    revoke_channel,
    save_credentials,
    stub_health,
)

router = APIRouter(tags=["channels"])


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


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    channel_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    revoke_channel(db, user, channel_id, ip=client_ip(request))
