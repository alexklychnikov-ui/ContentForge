from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError
from app.models import (
    ContentPiece,
    ContentPlan,
    ContentType,
    ContentVariant,
    Job,
    JobType,
    PieceStatus,
    PlanItem,
    User,
)
from app.schemas import (
    ContentCreate,
    GenerateContentRequest,
    PiecePatch,
    RewriteRequest,
    VariantCreate,
    VariantPatch,
)
from app.services.ai_schemas import PRIMARY_TEXT_FIELD
from app.services.audit import write_audit
from app.services.brand_kit import assert_can_generate_plan
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.job_service import create_job, dispatch_job


def list_pieces(
    db: Session,
    user: User,
    brand_id: UUID,
    piece_type: ContentType | None,
    status: PieceStatus | None,
) -> list[ContentPiece]:
    brand, _membership = require_brand(db, user, brand_id)
    query = (
        select(ContentPiece)
        .options(selectinload(ContentPiece.variants))
        .where(ContentPiece.brand_id == brand.id)
    )
    if piece_type is not None:
        query = query.where(ContentPiece.type == piece_type)
    if status is not None:
        query = query.where(ContentPiece.status == status)
    return list(db.scalars(query.order_by(ContentPiece.created_at.desc())).all())


def create_piece(db: Session, user: User, brand_id: UUID, payload: ContentCreate) -> ContentPiece:
    brand, _membership = require_brand(db, user, brand_id, MUTATE_BRAND_ROLES)
    plan_item = None
    if payload.plan_item_id is not None:
        plan_item = db.get(PlanItem, payload.plan_item_id)
        plan = db.get(ContentPlan, plan_item.plan_id) if plan_item is not None else None
        if plan_item is None or plan is None or plan.brand_id != brand.id:
            raise AppError(404, "not_found", "Слот не найден")
    piece = ContentPiece(
        brand_id=brand.id,
        type=payload.type,
        locale=payload.locale or brand.default_locale,
        status=PieceStatus.draft,
        plan_item_id=plan_item.id if plan_item is not None else None,
    )
    db.add(piece)
    db.flush()
    if plan_item is not None:
        plan_item.content_piece_id = piece.id
    return piece


def get_piece(db: Session, user: User, piece_id: UUID) -> ContentPiece:
    piece = db.scalar(
        select(ContentPiece)
        .options(selectinload(ContentPiece.variants), selectinload(ContentPiece.plan_item))
        .where(ContentPiece.id == piece_id)
    )
    if piece is None:
        raise AppError(404, "not_found", "Материал не найден")
    try:
        require_brand(db, user, piece.brand_id)
    except AppError as exc:
        if exc.status_code == 404:
            raise AppError(404, "not_found", "Материал не найден") from exc
        raise
    return piece


def patch_piece(db: Session, user: User, piece_id: UUID, payload: PiecePatch) -> ContentPiece:
    piece = get_piece(db, user, piece_id)
    require_brand(db, user, piece.brand_id, MUTATE_BRAND_ROLES)
    if payload.status is not None:
        piece.status = payload.status
    db.flush()
    return piece


def enqueue_generate_content(
    db: Session,
    user: User,
    piece_id: UUID,
    payload: GenerateContentRequest,
    ip: str | None = None,
) -> Job:
    piece = get_piece(db, user, piece_id)
    brand, _membership = require_brand(db, user, piece.brand_id, MUTATE_BRAND_ROLES)
    assert_can_generate_plan(brand)
    job = create_job(
        db,
        user=user,
        job_type=JobType.generate_content,
        payload={
            "brand_id": str(brand.id),
            "piece_id": str(piece.id),
            "variant_label": payload.variant_label,
            "channel_type": payload.channel_type.value if payload.channel_type else None,
            "extra_instructions": payload.extra_instructions,
        },
        idempotency_key=payload.idempotency_key,
    )
    if job.status.value != "queued":
        return job
    dispatch_job(db, job)
    write_audit(
        db,
        actor_id=user.id,
        action="generate_content",
        entity_type="job",
        entity_id=job.id,
        ip=ip,
        data={"piece_id": str(piece.id), "variant_label": payload.variant_label},
    )
    return job


def add_variant(db: Session, user: User, piece_id: UUID, payload: VariantCreate) -> ContentVariant:
    piece = get_piece(db, user, piece_id)
    require_brand(db, user, piece.brand_id, MUTATE_BRAND_ROLES)
    variant = ContentVariant(
        piece_id=piece.id,
        label=payload.label,
        payload=payload.payload,
        revision=1,
    )
    db.add(variant)
    db.flush()
    return variant


def get_variant(db: Session, user: User, piece_id: UUID, variant_id: UUID) -> ContentVariant:
    piece = get_piece(db, user, piece_id)
    variant = next((row for row in piece.variants if row.id == variant_id), None)
    if variant is None:
        raise AppError(404, "not_found", "Вариант не найден")
    return variant


def patch_variant(
    db: Session, user: User, piece_id: UUID, variant_id: UUID, payload: VariantPatch
) -> ContentVariant:
    variant = get_variant(db, user, piece_id, variant_id)
    require_brand(db, user, variant.piece.brand_id, MUTATE_BRAND_ROLES)
    if variant.is_immutable:
        raise AppError(409, "conflict", "Опубликованный вариант нельзя менять")
    if payload.payload is not None:
        merged = dict(variant.payload or {})
        merged.update(payload.payload)
        variant.payload = merged
        variant.revision += 1
    db.flush()
    return variant


def enqueue_rewrite(
    db: Session, user: User, piece_id: UUID, variant_id: UUID, payload: RewriteRequest
) -> Job:
    variant = get_variant(db, user, piece_id, variant_id)
    brand, _membership = require_brand(db, user, variant.piece.brand_id, MUTATE_BRAND_ROLES)
    field = payload.selection.field or PRIMARY_TEXT_FIELD[variant.piece.type]
    source = (variant.payload or {}).get(field)
    if not isinstance(source, str):
        raise AppError(422, "validation_error", "Поле для rewrite не текстовое")
    start = payload.selection.start
    end = payload.selection.end
    if start < 0 or end > len(source) or start >= end:
        raise AppError(422, "validation_error", "Некорректный selection")
    job = create_job(
        db,
        user=user,
        job_type=JobType.rewrite,
        payload={
            "brand_id": str(brand.id),
            "piece_id": str(variant.piece_id),
            "variant_id": str(variant.id),
            "field": field,
            "start": start,
            "end": end,
            "extra_instructions": payload.extra_instructions,
        },
        idempotency_key=payload.idempotency_key,
    )
    if job.status.value != "queued":
        return job
    dispatch_job(db, job)
    return job
