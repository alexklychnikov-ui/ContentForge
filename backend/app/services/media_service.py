import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import MediaAsset, MediaKind, User
from app.schemas import MediaPublic
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand

MAX_MEDIA_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {
    "image/jpeg": ("jpeg", b"\xff\xd8\xff"),
    "image/jpg": ("jpeg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}
CANONICAL_MIME = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def media_to_public(asset: MediaAsset) -> MediaPublic:
    return MediaPublic(
        id=asset.id,
        brand_id=asset.brand_id,
        kind=asset.kind,
        storage_key=asset.storage_key,
        mime=asset.mime,
        width=asset.width,
        height=asset.height,
        checksum=asset.checksum,
        url=f"/api/v1/media/{asset.id}/file",
    )


def _sniff_kind(header: bytes, content_type: str | None) -> str:
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared in ALLOWED_MIME:
        ext, magic = ALLOWED_MIME[declared]
        if ext == "webp":
            if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
                return ext
        elif header.startswith(magic):
            return ext
        raise AppError(415, "unsupported_media_type", "Файл не соответствует заявленному типу")
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    raise AppError(415, "unsupported_media_type", "Допустимы только jpeg, png и webp")


def _media_dir(brand_id: UUID) -> Path:
    root = Path(get_settings().media_root)
    path = root / str(brand_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(db: Session, user: User, brand_id: UUID, upload: UploadFile) -> MediaAsset:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    header = upload.file.read(16)
    if not header:
        raise AppError(400, "validation_error", "Пустой файл")
    kind = _sniff_kind(header, upload.content_type)
    digest = hashlib.sha256()
    digest.update(header)
    size = len(header)
    asset_id = uuid4()
    storage_key = f"{brand.id}/{asset_id}.{kind}"
    dest = _media_dir(brand.id) / f"{asset_id}.{kind}"
    try:
        with dest.open("wb") as out:
            out.write(header)
            while True:
                chunk = upload.file.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_MEDIA_BYTES:
                    raise AppError(413, "file_too_large", "Файл больше 10 МБ")
                digest.update(chunk)
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    asset = MediaAsset(
        id=asset_id,
        brand_id=brand.id,
        kind=MediaKind.image,
        storage_key=storage_key,
        mime=CANONICAL_MIME[kind],
        checksum=digest.hexdigest(),
    )
    db.add(asset)
    db.flush()
    return asset


def get_media(db: Session, user: User, media_id: UUID) -> MediaAsset:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise AppError(404, "not_found", "Медиа не найдено")
    try:
        require_brand(db, user, asset.brand_id)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Медиа не найдено") from exc
        raise
    return asset


def media_file_path(asset: MediaAsset) -> Path:
    root = Path(get_settings().media_root).resolve()
    path = (root / asset.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError(404, "not_found", "Файл не найден")
    return path
