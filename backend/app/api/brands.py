from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.errors import AppError
from app.models import User
from app.schemas import (
    BrandContentProfileOut,
    BrandContentProfileUpdate,
    BrandCreate,
    BrandPublic,
    BrandUpdate,
    GeneratePlanRequest,
    GroundingReferenceOut,
    GroundingResultOut,
    JobAccepted,
    KnowledgePreviewRequest,
    brand_to_public,
)
from app.services.brand_service import (
    create_brand,
    delete_brand,
    list_brands,
    require_brand,
    update_brand,
)
from app.services.content_profile_service import (
    apply_content_profile_preset,
    get_or_create_content_profile,
    update_content_profile,
)
from app.services.knowledge_grounding import GroundingStatus, ground_knowledge
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


@router.get("/{brand_id}/content-profile", response_model=BrandContentProfileOut)
def get_content_profile(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandContentProfileOut:
    return get_or_create_content_profile(db, user, brand_id)


@router.patch("/{brand_id}/content-profile", response_model=BrandContentProfileOut)
def patch_content_profile(
    brand_id: UUID,
    payload: BrandContentProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandContentProfileOut:
    return update_content_profile(db, user, brand_id, payload)


@router.post(
    "/{brand_id}/content-profile/preset/{preset_id}",
    response_model=BrandContentProfileOut,
)
def post_content_profile_preset(
    brand_id: UUID,
    preset_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrandContentProfileOut:
    return apply_content_profile_preset(db, user, brand_id, preset_id)


@router.post("/{brand_id}/knowledge/preview", response_model=GroundingResultOut)
def preview_knowledge(
    brand_id: UUID,
    payload: KnowledgePreviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroundingResultOut:
    profile = get_or_create_content_profile(db, user, brand_id)
    result = ground_knowledge(
        profile,
        payload.query,
        mode=(payload.mode or "mix"),
    )
    if result.status == GroundingStatus.blocked:
        status_code = 503 if result.error_code in {"unavailable", "auth"} else 409
        raise AppError(
            status_code,
            result.error_code or "knowledge_blocked",
            result.error_message or "Knowledge grounding blocked",
        )
    return GroundingResultOut(
        status=result.status.value,
        context=result.context,
        references=[
            GroundingReferenceOut(id=ref.id, file_path=ref.file_path)
            for ref in result.references
        ],
        error_message=result.error_message,
        warning=result.warning,
        error_code=result.error_code,
    )


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
