from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    PlanItemCreate,
    PlanItemPublic,
    PlanItemUpdate,
    PlanPatch,
    PlanPublic,
)
from app.services.plan_service import (
    add_plan_item,
    delete_plan_item,
    get_plan,
    list_plans,
    patch_plan,
    patch_plan_item,
)

router = APIRouter(tags=["plans"])


@router.get("/brands/{brand_id}/plans", response_model=list[PlanPublic])
def get_brand_plans(
    brand_id: UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PlanPublic]:
    return [PlanPublic.model_validate(plan) for plan in list_plans(db, user, brand_id, year, month)]


@router.get("/plans/{plan_id}", response_model=PlanPublic)
def get_plan_detail(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanPublic:
    return PlanPublic.model_validate(get_plan(db, user, plan_id))


@router.patch("/plans/{plan_id}", response_model=PlanPublic)
def patch_plan_detail(
    plan_id: UUID,
    payload: PlanPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanPublic:
    return PlanPublic.model_validate(patch_plan(db, user, plan_id, payload))


@router.post(
    "/plans/{plan_id}/items",
    response_model=PlanItemPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_plan_item(
    plan_id: UUID,
    payload: PlanItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanItemPublic:
    return PlanItemPublic.model_validate(add_plan_item(db, user, plan_id, payload))


@router.patch("/plans/{plan_id}/items/{item_id}", response_model=PlanItemPublic)
def patch_item(
    plan_id: UUID,
    item_id: UUID,
    payload: PlanItemUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanItemPublic:
    return PlanItemPublic.model_validate(patch_plan_item(db, user, plan_id, item_id, payload))


@router.delete("/plans/{plan_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    plan_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    delete_plan_item(db, user, plan_id, item_id)
