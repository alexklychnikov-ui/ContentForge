from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import RecipientCreate, RecipientPatch, RecipientPublic
from app.services.recipient_service import (
    create_recipient,
    delete_recipient,
    list_recipients,
    patch_recipient,
)

router = APIRouter(tags=["recipients"])


@router.get("/brands/{brand_id}/recipients", response_model=list[RecipientPublic])
def get_recipients(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecipientPublic]:
    return [RecipientPublic.model_validate(item) for item in list_recipients(db, user, brand_id)]


@router.post(
    "/brands/{brand_id}/recipients",
    response_model=RecipientPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_recipient(
    brand_id: UUID,
    payload: RecipientCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipientPublic:
    return RecipientPublic.model_validate(create_recipient(db, user, brand_id, payload))


@router.patch("/recipients/{recipient_id}", response_model=RecipientPublic)
def patch_recipient_item(
    recipient_id: UUID,
    payload: RecipientPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipientPublic:
    return RecipientPublic.model_validate(patch_recipient(db, user, recipient_id, payload))


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipient(
    recipient_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    delete_recipient(db, user, recipient_id)
