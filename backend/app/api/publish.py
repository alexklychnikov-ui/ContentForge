from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import PublicationStatus, User
from app.schemas import MarkManualRequest, PublicationPublic, ScheduleRequest
from app.services.publish_service import (
    cancel_publication,
    list_publications,
    mark_manual,
    retry_publication,
    schedule_publication,
)

router = APIRouter(tags=["publish"])


def _public(row) -> PublicationPublic:
    channel = row.channel
    variant = row.variant
    return PublicationPublic.model_validate(
        {
            "id": row.id,
            "variant_id": row.variant_id,
            "channel_account_id": row.channel_account_id,
            "scheduled_at": row.scheduled_at,
            "status": row.status,
            "external_id": row.external_id,
            "external_url": row.external_url,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "attempt_count": row.attempt_count,
            "idempotency_key": row.idempotency_key,
            "experiment_id": row.experiment_id,
            "published_at": row.published_at,
            "meta": row.meta,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "channel_type": channel.type,
            "channel_display_name": channel.display_name,
            "piece_id": variant.piece_id if variant is not None else None,
        }
    )


@router.get("/brands/{brand_id}/publications", response_model=list[PublicationPublic])
def get_publications(
    brand_id: UUID,
    status: PublicationStatus | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PublicationPublic]:
    return [
        _public(row)
        for row in list_publications(db, user, brand_id, status, from_at, to_at)
    ]


@router.post("/brands/{brand_id}/publications")
def post_publication(
    brand_id: UUID,
    payload: ScheduleRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    row, created = schedule_publication(
        db, user, brand_id, payload, ip=client_ip(request)
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        content=jsonable_encoder(_public(row)),
    )


@router.post("/publications/{publication_id}/cancel", response_model=PublicationPublic)
def post_cancel(
    publication_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublicationPublic:
    return _public(cancel_publication(db, user, publication_id, ip=client_ip(request)))


@router.post("/publications/{publication_id}/retry", response_model=PublicationPublic)
def post_retry(
    publication_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublicationPublic:
    return _public(retry_publication(db, user, publication_id, ip=client_ip(request)))


@router.post("/publications/{publication_id}/mark-manual", response_model=PublicationPublic)
def post_mark_manual(
    publication_id: UUID,
    payload: MarkManualRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublicationPublic:
    return _public(mark_manual(db, user, publication_id, payload, ip=client_ip(request)))
