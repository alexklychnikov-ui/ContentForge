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
    QualityReviewOut,
    RewriteRequest,
    VariantCreate,
    VariantPatch,
    VariantReviewRequest,
)
from app.security import utc_now
from app.services.ai_client import complete_json
from app.services.ai_schemas import PRIMARY_TEXT_FIELD, QualityReviewAI
from app.services.audit import write_audit
from app.services.brand_kit import assert_can_generate_plan
from app.services.brand_service import MUTATE_BRAND_ROLES, require_brand
from app.services.content_profile_service import ensure_content_profile
from app.services.content_quality import (
    is_variant_approved,
    quality_payload_from_lint,
    run_formal_lint_for_variant,
    store_approval_on_payload,
    store_quality_on_payload,
)
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


def _quality_out(variant: ContentVariant, piece: ContentPiece) -> QualityReviewOut:
    meta = (variant.payload or {}).get("_meta") or {}
    quality = meta.get("quality") if isinstance(meta, dict) else None
    if not isinstance(quality, dict):
        quality = {"blockers": [], "warnings": [], "lint": {}}
    blockers = list(quality.get("blockers") or [])
    warnings = list(quality.get("warnings") or [])
    lint_raw = quality.get("lint") if isinstance(quality.get("lint"), dict) else {}
    scores = quality.get("scores")
    if scores is None:
        scores = lint_raw.get("scores")
    lint = {
        "blockers": blockers,
        "warnings": warnings,
        "scores": scores,
    }
    return QualityReviewOut(
        blockers=blockers,
        warnings=warnings,
        scores=scores,
        lint=lint,
        ai_review=quality.get("ai_review"),
        approved=is_variant_approved(variant, piece),
    )


def review_variant(
    db: Session,
    user: User,
    piece_id: UUID,
    variant_id: UUID,
    payload: VariantReviewRequest | None = None,
) -> QualityReviewOut:
    variant = get_variant(db, user, piece_id, variant_id)
    piece = variant.piece
    brand, _membership = require_brand(db, user, piece.brand_id, MUTATE_BRAND_ROLES)
    profile = ensure_content_profile(db, brand.id)
    lint = run_formal_lint_for_variant(variant, piece, profile, brand)
    ai_review_data = None
    run_ai = True if payload is None else bool(payload.run_ai)
    if run_ai and piece.type is ContentType.social_post:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a content quality reviewer. Return JSON with scores 1-5 for "
                    "clarity, audience_pain, scene, practical_value, tone, uniqueness, cta, "
                    "formatting; overall 1-5; blocking_issues[]; recommendations[]; pass bool."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this social post JSON. Formal lint blockers: "
                    f"{lint.blockers}. Formal warnings: {lint.warnings}.\n"
                    f"Post: {variant.payload}"
                ),
            },
        ]
        result, _meta = complete_json(QualityReviewAI, messages, temperature=0.2)
        assert isinstance(result, QualityReviewAI)
        ai_review_data = result.model_dump(by_alias=True)
        if ai_review_data.get("blocking_issues"):
            for issue in ai_review_data["blocking_issues"]:
                code = f"ai:{issue}"
                if code not in lint.blockers:
                    lint.blockers.append(code)
    quality = quality_payload_from_lint(lint, ai_review=ai_review_data)
    variant.payload = store_quality_on_payload(variant.payload or {}, quality)
    db.flush()
    return _quality_out(variant, piece)


def approve_variant(
    db: Session,
    user: User,
    piece_id: UUID,
    variant_id: UUID,
) -> ContentPiece:
    variant = get_variant(db, user, piece_id, variant_id)
    piece = variant.piece
    brand, _membership = require_brand(db, user, piece.brand_id, MUTATE_BRAND_ROLES)
    profile = ensure_content_profile(db, brand.id)
    lint = run_formal_lint_for_variant(variant, piece, profile, brand)
    quality = quality_payload_from_lint(lint)
    existing_meta = (variant.payload or {}).get("_meta") or {}
    existing_quality = existing_meta.get("quality") if isinstance(existing_meta, dict) else None
    if isinstance(existing_quality, dict) and existing_quality.get("ai_review"):
        quality["ai_review"] = existing_quality["ai_review"]
    variant.payload = store_quality_on_payload(variant.payload or {}, quality)
    blockers = list(lint.blockers)
    if blockers:
        db.flush()
        raise AppError(
            409,
            "quality_blockers",
            "Материал не проходит quality gate",
            {"blockers": blockers},
        )
    now = utc_now().isoformat()
    variant.payload = store_approval_on_payload(
        variant.payload or {},
        approved_at=now,
        approved_by=str(user.id),
    )
    piece.status = PieceStatus.ready
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="approve_content",
        entity_type="content_variant",
        entity_id=variant.id,
        data={"piece_id": str(piece.id)},
    )
    return piece
