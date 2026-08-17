from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import ContentType, PieceStatus, User
from app.schemas import (
    ContentCreate,
    GenerateContentRequest,
    JobAccepted,
    PiecePatch,
    PiecePublic,
    RewriteRequest,
    VariantCreate,
    VariantPatch,
    VariantPublic,
)
from app.services.content_service import (
    add_variant,
    create_piece,
    enqueue_generate_content,
    enqueue_rewrite,
    get_piece,
    list_pieces,
    patch_piece,
    patch_variant,
)

router = APIRouter(tags=["content"])


@router.get("/brands/{brand_id}/content", response_model=list[PiecePublic])
def get_brand_content(
    brand_id: UUID,
    type: ContentType | None = Query(default=None),
    status: PieceStatus | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PiecePublic]:
    return [
        PiecePublic.model_validate(piece)
        for piece in list_pieces(db, user, brand_id, type, status)
    ]


@router.post(
    "/brands/{brand_id}/content",
    response_model=PiecePublic,
    status_code=status.HTTP_201_CREATED,
)
def post_piece(
    brand_id: UUID,
    payload: ContentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PiecePublic:
    return PiecePublic.model_validate(create_piece(db, user, brand_id, payload))


@router.get("/content/{piece_id}", response_model=PiecePublic)
def get_piece_detail(
    piece_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PiecePublic:
    return PiecePublic.model_validate(get_piece(db, user, piece_id))


@router.patch("/content/{piece_id}", response_model=PiecePublic)
def patch_piece_detail(
    piece_id: UUID,
    payload: PiecePatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PiecePublic:
    return PiecePublic.model_validate(patch_piece(db, user, piece_id, payload))


@router.post("/content/{piece_id}/generate", response_model=JobAccepted, status_code=202)
def generate_piece(
    piece_id: UUID,
    payload: GenerateContentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobAccepted:
    job = enqueue_generate_content(db, user, piece_id, payload, ip=client_ip(request))
    return JobAccepted(job_id=job.id)


@router.post(
    "/content/{piece_id}/variants",
    response_model=VariantPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_variant(
    piece_id: UUID,
    payload: VariantCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VariantPublic:
    return VariantPublic.model_validate(add_variant(db, user, piece_id, payload))


@router.patch("/content/{piece_id}/variants/{variant_id}", response_model=VariantPublic)
def patch_variant_detail(
    piece_id: UUID,
    variant_id: UUID,
    payload: VariantPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VariantPublic:
    return VariantPublic.model_validate(patch_variant(db, user, piece_id, variant_id, payload))


@router.post(
    "/content/{piece_id}/variants/{variant_id}/rewrite",
    response_model=JobAccepted,
    status_code=202,
)
def rewrite_variant(
    piece_id: UUID,
    variant_id: UUID,
    payload: RewriteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobAccepted:
    job = enqueue_rewrite(db, user, piece_id, variant_id, payload)
    return JobAccepted(job_id=job.id)
