from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError
from app.models import (
    ACTIVE_PLAN_STATUSES,
    ContentPlan,
    ContentType,
    Job,
    JobType,
    PlanItem,
    PlanStatus,
    User,
)
from app.schemas import GeneratePlanRequest, PlanItemCreate, PlanItemUpdate, PlanPatch
from app.services.audit import write_audit
from app.services.brand_kit import assert_can_generate_plan
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.job_service import create_job, dispatch_job, inflight_generate_plan


def _active_plan(db: Session, brand_id: UUID, year: int, month: int) -> ContentPlan | None:
    return db.scalar(
        select(ContentPlan).where(
            ContentPlan.brand_id == brand_id,
            ContentPlan.year == year,
            ContentPlan.month == month,
            ContentPlan.status.in_(ACTIVE_PLAN_STATUSES),
        )
    )


def _require_targets(payload: GeneratePlanRequest) -> dict[str, int]:
    allowed = {item.value for item in ContentType}
    if not payload.channels:
        raise AppError(422, "validation_error", "Укажите хотя бы один канал")
    targets: dict[str, int] = {}
    for key, value in payload.targets.items():
        if key not in allowed:
            raise AppError(422, "validation_error", f"Неизвестный тип {key}")
        if value > 0:
            targets[key] = value
    if not targets:
        raise AppError(422, "validation_error", "Укажите targets больше нуля")
    return targets


def enqueue_generate_plan(
    db: Session, user: User, brand_id: UUID, payload: GeneratePlanRequest, ip: str | None = None
) -> Job:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    assert_can_generate_plan(brand)
    targets = _require_targets(payload)
    existing = _active_plan(db, brand.id, payload.year, payload.month)
    if existing is not None:
        if existing.status is PlanStatus.generating:
            raise AppError(409, "plan_active_exists", "Генерация плана уже выполняется")
        if existing.status is PlanStatus.draft:
            if not payload.confirm:
                raise AppError(
                    409,
                    "plan_active_exists",
                    "Черновик плана на этот месяц уже есть",
                    {"plan_id": str(existing.id)},
                )
            existing.status = PlanStatus.archived
            db.flush()
        elif existing.status is PlanStatus.approved:
            if not payload.create_revision:
                raise AppError(
                    409,
                    "plan_active_exists",
                    "Утверждённый план на этот месяц уже есть",
                    {"plan_id": str(existing.id)},
                )
            existing.status = PlanStatus.archived
            db.flush()
    inflight = inflight_generate_plan(db, brand, payload.year, payload.month)
    if inflight is not None:
        raise AppError(409, "plan_active_exists", "Генерация плана уже выполняется")
    job = create_job(
        db,
        user=user,
        job_type=JobType.generate_plan,
        payload={
            "brand_id": str(brand.id),
            "year": payload.year,
            "month": payload.month,
            "channels": [item.value for item in payload.channels],
            "targets": targets,
            "locale": payload.locale.value,
            "include_holidays": payload.include_holidays,
            "include_trends": payload.include_trends,
        },
        idempotency_key=payload.idempotency_key,
    )
    if job.status.value != "queued":
        return job
    dispatch_job(db, job)
    write_audit(
        db,
        actor_id=user.id,
        action="generate_plan",
        entity_type="job",
        entity_id=job.id,
        ip=ip,
        data={"brand_id": str(brand.id), "year": payload.year, "month": payload.month},
    )
    return job


def list_plans(
    db: Session, user: User, brand_id: UUID, year: int | None, month: int | None
) -> list[ContentPlan]:
    brand, _membership = require_brand(db, user, brand_id)
    query = (
        select(ContentPlan)
        .options(selectinload(ContentPlan.items))
        .where(ContentPlan.brand_id == brand.id)
    )
    if year is not None:
        query = query.where(ContentPlan.year == year)
    if month is not None:
        query = query.where(ContentPlan.month == month)
    return list(db.scalars(query.order_by(ContentPlan.created_at.desc())).all())


def get_plan(db: Session, user: User, plan_id: UUID) -> ContentPlan:
    plan = db.scalar(
        select(ContentPlan).options(selectinload(ContentPlan.items)).where(ContentPlan.id == plan_id)
    )
    if plan is None:
        raise AppError(404, "not_found", "План не найден")
    try:
        require_brand(db, user, plan.brand_id)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "План не найден") from exc
        raise
    return plan


def patch_plan(db: Session, user: User, plan_id: UUID, payload: PlanPatch) -> ContentPlan:
    plan = get_plan(db, user, plan_id)
    require_brand(db, user, plan.brand_id, MUTATE_BRAND_ROLES)
    if payload.status is None:
        return plan
    current = plan.status
    target = payload.status
    allowed = (
        (current is PlanStatus.draft and target is PlanStatus.approved)
        or (current in {PlanStatus.draft, PlanStatus.approved} and target is PlanStatus.archived)
    )
    if not allowed:
        raise AppError(409, "conflict", "Недопустимый переход статуса плана")
    plan.status = target
    db.flush()
    return plan


def _editable_plan(db: Session, user: User, plan_id: UUID) -> ContentPlan:
    plan = get_plan(db, user, plan_id)
    require_brand(db, user, plan.brand_id, MUTATE_BRAND_ROLES)
    if plan.status is not PlanStatus.draft:
        raise AppError(409, "conflict", "Слоты можно менять только в черновике")
    return plan


def add_plan_item(db: Session, user: User, plan_id: UUID, payload: PlanItemCreate) -> PlanItem:
    plan = _editable_plan(db, user, plan_id)
    order = max((item.sort_order for item in plan.items), default=-1) + 1
    item = PlanItem(
        plan_id=plan.id,
        date=payload.date,
        channel_type=payload.channel_type,
        content_type=payload.content_type,
        theme=payload.theme,
        goal=payload.goal,
        hook=payload.hook,
        sort_order=order,
    )
    db.add(item)
    db.flush()
    return item


def patch_plan_item(
    db: Session, user: User, plan_id: UUID, item_id: UUID, payload: PlanItemUpdate
) -> PlanItem:
    plan = _editable_plan(db, user, plan_id)
    item = next((row for row in plan.items if row.id == item_id), None)
    if item is None:
        raise AppError(404, "not_found", "Слот не найден")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    db.flush()
    return item


def delete_plan_item(db: Session, user: User, plan_id: UUID, item_id: UUID) -> None:
    plan = _editable_plan(db, user, plan_id)
    item = next((row for row in plan.items if row.id == item_id), None)
    if item is None:
        raise AppError(404, "not_found", "Слот не найден")
    db.delete(item)
    db.flush()
