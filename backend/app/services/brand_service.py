from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    BrandProfile,
    Holiday,
    HolidaySource,
    Membership,
    MembershipRole,
    TrendSignal,
    TrendStatus,
    User,
)
from app.schemas import BrandCreate, BrandUpdate, HolidayCreate, TrendCreate, TrendUpdate
from app.security import utc_now
from app.services.audit import write_audit
from app.services.brand_kit import sync_onboarding_timestamp


MUTATE_BRAND_ROLES = {MembershipRole.owner, MembershipRole.editor}
DELETE_BRAND_ROLES = {MembershipRole.owner}


def get_membership(db: Session, user_id: UUID, workspace_id: UUID) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.workspace_id == workspace_id,
        )
    )


def primary_workspace_id(user: User) -> UUID:
    if not user.memberships:
        raise AppError(403, "forbidden", "Нет доступа к workspace")
    owners = [m for m in user.memberships if m.role == MembershipRole.owner]
    membership = owners[0] if owners else user.memberships[0]
    return membership.workspace_id


def require_brand(
    db: Session,
    user: User,
    brand_id: UUID,
    allowed_roles: set[MembershipRole] | None = None,
) -> tuple[BrandProfile, Membership]:
    brand = db.get(BrandProfile, brand_id)
    if brand is None or brand.deleted_at is not None:
        raise AppError(404, "not_found", "Бренд не найден")
    membership = get_membership(db, user.id, brand.workspace_id)
    if membership is None:
        raise AppError(404, "not_found", "Бренд не найден")
    if allowed_roles is not None and membership.role not in allowed_roles:
        raise AppError(403, "forbidden", "Недостаточно прав")
    return brand, membership


def list_brands(db: Session, user: User) -> list[BrandProfile]:
    workspace_id = primary_workspace_id(user)
    return list(
        db.scalars(
            select(BrandProfile)
            .where(
                BrandProfile.workspace_id == workspace_id,
                BrandProfile.deleted_at.is_(None),
            )
            .order_by(BrandProfile.created_at.desc())
        ).all()
    )


def create_brand(
    db: Session, user: User, payload: BrandCreate, ip: str | None = None
) -> BrandProfile:
    workspace_id = primary_workspace_id(user)
    membership = get_membership(db, user.id, workspace_id)
    if membership is None or membership.role not in MUTATE_BRAND_ROLES:
        raise AppError(403, "forbidden", "Недостаточно прав")
    brand = BrandProfile(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        niche=payload.niche.strip(),
        audience=payload.audience.strip(),
        voice_tone=payload.voice_tone.strip(),
        stopwords=list(payload.stopwords),
        offers=list(payload.offers),
        example_posts=list(payload.example_posts),
        default_locale=payload.default_locale,
        timezone=payload.timezone,
    )
    sync_onboarding_timestamp(brand)
    db.add(brand)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="create_brand",
        entity_type="brand",
        entity_id=brand.id,
        ip=ip,
        data={"name": brand.name},
    )
    return brand


def update_brand(
    db: Session, user: User, brand_id: UUID, payload: BrandUpdate, ip: str | None = None
) -> BrandProfile:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(brand, field, value)
    sync_onboarding_timestamp(brand)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="update_brand",
        entity_type="brand",
        entity_id=brand.id,
        ip=ip,
        data={"fields": sorted(data.keys())},
    )
    return brand


def delete_brand(db: Session, user: User, brand_id: UUID, ip: str | None = None) -> None:
    brand, _membership = require_brand(db, user, brand_id, DELETE_BRAND_ROLES)
    brand.deleted_at = utc_now()
    write_audit(
        db,
        actor_id=user.id,
        action="delete_brand",
        entity_type="brand",
        entity_id=brand.id,
        ip=ip,
        data={},
    )
    db.flush()


def list_trends(db: Session, user: User, brand_id: UUID) -> list[TrendSignal]:
    brand, _membership = require_brand(db, user, brand_id)
    return list(
        db.scalars(
            select(TrendSignal)
            .where(or_(TrendSignal.brand_id == brand.id, TrendSignal.brand_id.is_(None)))
            .order_by(TrendSignal.title)
        ).all()
    )


def create_trend(db: Session, user: User, brand_id: UUID, payload: TrendCreate) -> TrendSignal:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    trend = TrendSignal(
        brand_id=brand.id,
        title=payload.title.strip(),
        note=payload.note,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        status=TrendStatus.active,
    )
    db.add(trend)
    db.flush()
    return trend


def update_trend(db: Session, user: User, trend_id: UUID, payload: TrendUpdate) -> TrendSignal:
    trend = db.get(TrendSignal, trend_id)
    if trend is None or trend.brand_id is None:
        raise AppError(404, "not_found", "Тренд не найден")
    try:
        require_brand(db, user, trend.brand_id, MUTATE_BRAND_ROLES)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Тренд не найден") from exc
        raise
    data = payload.model_dump(exclude_unset=True)
    archived = data.pop("archived", None)
    if archived is True:
        trend.status = TrendStatus.archived
    elif archived is False:
        trend.status = TrendStatus.active
    for field, value in data.items():
        if isinstance(value, str) and field == "title":
            value = value.strip()
        setattr(trend, field, value)
    db.flush()
    return trend


def create_brand_holiday(
    db: Session, user: User, brand_id: UUID, payload: HolidayCreate
) -> Holiday:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    holiday = Holiday(
        date=payload.date,
        name=payload.name.strip(),
        country=payload.country.upper(),
        source=HolidaySource.brand,
        brand_id=brand.id,
    )
    db.add(holiday)
    db.flush()
    return holiday
