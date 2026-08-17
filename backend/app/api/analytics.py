from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.services.analytics_service import brand_summary, publication_analytics

router = APIRouter(tags=["analytics"])


@router.get("/brands/{brand_id}/analytics/summary")
def get_brand_analytics_summary(
    brand_id: UUID,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if from_at is None or to_at is None:
        raise AppError(422, "validation_error", "Укажите from и to")
    return brand_summary(db, user, brand_id, from_at, to_at)


@router.get("/publications/{publication_id}/analytics")
def get_publication_analytics(
    publication_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return publication_analytics(db, user, publication_id)
