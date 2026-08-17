from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import EmailRecipient, RecipientSource, RecipientStatus, User
from app.schemas import RecipientCreate, RecipientPatch
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand

GMAIL_RECIPIENT_CAP = 50


def list_recipients(db: Session, user: User, brand_id: UUID) -> list[EmailRecipient]:
    brand, _membership = require_brand(db, user, brand_id)
    return list(
        db.scalars(
            select(EmailRecipient)
            .where(EmailRecipient.brand_id == brand.id)
            .order_by(EmailRecipient.email)
        ).all()
    )


def has_active_recipients(db: Session, brand_id: UUID) -> bool:
    row = db.scalar(
        select(EmailRecipient.id).where(
            EmailRecipient.brand_id == brand_id,
            EmailRecipient.status == RecipientStatus.active,
        )
    )
    return row is not None


def list_active_recipients(
    db: Session, brand_id: UUID, limit: int = GMAIL_RECIPIENT_CAP
) -> list[EmailRecipient]:
    return list(
        db.scalars(
            select(EmailRecipient)
            .where(
                EmailRecipient.brand_id == brand_id,
                EmailRecipient.status == RecipientStatus.active,
            )
            .order_by(EmailRecipient.email)
            .limit(limit)
        ).all()
    )


def create_recipient(
    db: Session, user: User, brand_id: UUID, payload: RecipientCreate
) -> EmailRecipient:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    email = payload.email.strip().lower()
    existing = db.scalar(
        select(EmailRecipient).where(
            EmailRecipient.brand_id == brand.id,
            EmailRecipient.email == email,
        )
    )
    if existing is not None:
        raise AppError(409, "recipient_exists", "Получатель уже добавлен")
    row = EmailRecipient(
        brand_id=brand.id,
        email=email,
        name=(payload.name.strip() if payload.name else None),
        status=RecipientStatus.active,
        source=RecipientSource.manual,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(409, "recipient_exists", "Получатель уже добавлен") from exc
    return row


def require_recipient(
    db: Session, user: User, recipient_id: UUID, allowed_roles: set | None = None
) -> EmailRecipient:
    row = db.get(EmailRecipient, recipient_id)
    if row is None:
        raise AppError(404, "not_found", "Получатель не найден")
    try:
        require_brand(db, user, row.brand_id, allowed_roles)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Получатель не найден") from exc
        raise
    return row


def patch_recipient(
    db: Session, user: User, recipient_id: UUID, payload: RecipientPatch
) -> EmailRecipient:
    row = require_recipient(db, user, recipient_id, MUTATE_BRAND_ROLES)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def delete_recipient(db: Session, user: User, recipient_id: UUID) -> None:
    row = require_recipient(db, user, recipient_id, MUTATE_BRAND_ROLES)
    db.delete(row)
    db.flush()
