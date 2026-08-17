from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import MediaPublic
from app.services.media_service import get_media, media_file_path, media_to_public, save_upload

router = APIRouter(tags=["media"])


@router.post(
    "/brands/{brand_id}/media",
    response_model=MediaPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_media(
    brand_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaPublic:
    return media_to_public(save_upload(db, user, brand_id, file))


@router.get("/media/{media_id}", response_model=MediaPublic)
def get_media_item(
    media_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaPublic:
    return media_to_public(get_media(db, user, media_id))


@router.get("/media/{media_id}/file")
def get_media_file(
    media_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    asset = get_media(db, user, media_id)
    path = media_file_path(asset)
    return FileResponse(
        path,
        media_type=asset.mime,
        headers={"X-Content-Type-Options": "nosniff"},
    )
