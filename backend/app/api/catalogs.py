from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    HolidayCreate,
    HolidayPublic,
    TrendCreate,
    TrendPublic,
    TrendUpdate,
)
from app.services.brand_service import (
    create_brand_holiday,
    create_trend,
    list_trends,
    require_brand,
    update_trend,
)
from app.services.catalog_service import list_holidays, parse_year_month

router = APIRouter(tags=["catalogs"])


@router.get("/holidays", response_model=list[HolidayPublic])
def get_holidays(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    brand_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[HolidayPublic]:
    if brand_id is not None:
        require_brand(db, user, brand_id)
    resolved_year, resolved_month = parse_year_month(year, month)
    return [
        HolidayPublic.model_validate(item)
        for item in list_holidays(db, resolved_year, resolved_month, brand_id)
    ]


@router.post(
    "/brands/{brand_id}/holidays",
    response_model=HolidayPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_brand_holiday(
    brand_id: UUID,
    payload: HolidayCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HolidayPublic:
    return HolidayPublic.model_validate(create_brand_holiday(db, user, brand_id, payload))


@router.get("/brands/{brand_id}/trends", response_model=list[TrendPublic])
def get_trends(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TrendPublic]:
    return [TrendPublic.model_validate(item) for item in list_trends(db, user, brand_id)]


@router.post(
    "/brands/{brand_id}/trends",
    response_model=TrendPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_trend(
    brand_id: UUID,
    payload: TrendCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendPublic:
    return TrendPublic.model_validate(create_trend(db, user, brand_id, payload))


@router.patch("/trends/{trend_id}", response_model=TrendPublic)
def patch_trend(
    trend_id: UUID,
    payload: TrendUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendPublic:
    return TrendPublic.model_validate(update_trend(db, user, trend_id, payload))
