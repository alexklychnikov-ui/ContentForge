from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import User
from app.schemas import (
    BrandCreate,
    BrandPublic,
    BrandUpdate,
    GeneratePlanRequest,
    JobAccepted,
    brand_to_public,
)
from app.services.brand_service import (
    create_brand,
    delete_brand,
    list_brands,
    require_brand,
    update_brand,
)
from app.services.plan_service import enqueue_generate_plan

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("", response_model=list[BrandPublic])
def get_brands(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BrandPublic]:
    return [brand_to_public(brand) for brand in list_brands(db, user)]


@router.post("", response_model=BrandPublic, status_code=status.HTTP_201_CREATED)
def post_brand(
    payload: BrandCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandPublic:
    return brand_to_public(create_brand(db, user, payload, ip=client_ip(request)))


@router.get("/{brand_id}", response_model=BrandPublic)
def get_brand(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandPublic:
    brand, _membership = require_brand(db, user, brand_id)
    return brand_to_public(brand)


@router.patch("/{brand_id}", response_model=BrandPublic)
def patch_brand(
    brand_id: UUID,
    payload: BrandUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandPublic:
    return brand_to_public(update_brand(db, user, brand_id, payload, ip=client_ip(request)))


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_brand(
    brand_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    delete_brand(db, user, brand_id, ip=client_ip(request))


@router.post("/{brand_id}/plans/generate", response_model=JobAccepted, status_code=202)
def generate_plan(
    brand_id: UUID,
    payload: GeneratePlanRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobAccepted:
    job = enqueue_generate_plan(db, user, brand_id, payload, ip=client_ip(request))
    return JobAccepted(job_id=job.id)
