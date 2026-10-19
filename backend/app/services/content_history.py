from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ChannelAccount,
    ChannelType,
    ContentPiece,
    ContentVariant,
    PieceStatus,
    Publication,
)


def recent_posts_for_platform(
    db: Session,
    brand_id: UUID,
    channel: str,
    *,
    limit: int = 12,
    exclude_piece_id: UUID | None = None,
) -> list[dict[str, str]]:
    """Recent post snippets for a brand+channel to reduce repetition in generation."""
    channel_key = (channel or "").strip().lower()
    if not channel_key:
        return []

    rows = db.scalars(
        select(ContentVariant)
        .join(ContentPiece)
        .options(selectinload(ContentVariant.piece).selectinload(ContentPiece.plan_item))
        .where(
            ContentPiece.brand_id == brand_id,
            ContentPiece.status != PieceStatus.archived,
        )
        .order_by(ContentPiece.created_at.desc())
        .limit(80)
    ).all()

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for variant in rows:
        piece = variant.piece
        if exclude_piece_id is not None and piece.id == exclude_piece_id:
            continue
        payload = variant.payload or {}
        target = str(payload.get("target_platform") or "").strip().lower()
        plan_ch = ""
        if piece.plan_item is not None:
            plan_ch = piece.plan_item.channel_type.value
        if target != channel_key and plan_ch != channel_key:
            continue
        headline = str(payload.get("headline") or payload.get("title") or "").strip()
        text = str(payload.get("text") or payload.get("body_markdown") or "").strip()
        theme = ""
        if piece.plan_item is not None:
            theme = (piece.plan_item.theme or "").strip()
        if not headline and not text and not theme:
            continue
        fingerprint = (headline or text or theme)[:160]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(
            {
                "headline": headline[:120],
                "theme": theme[:160],
                "text": text[:280],
            }
        )
        if len(out) >= limit:
            break

    if len(out) >= limit:
        return out

    try:
        channel_enum = ChannelType(channel_key)
    except ValueError:
        return out

    pubs = db.scalars(
        select(Publication)
        .join(ContentVariant)
        .join(ContentPiece)
        .join(ChannelAccount, Publication.channel_account_id == ChannelAccount.id)
        .options(
            selectinload(Publication.variant)
            .selectinload(ContentVariant.piece)
            .selectinload(ContentPiece.plan_item)
        )
        .where(
            ContentPiece.brand_id == brand_id,
            ChannelAccount.type == channel_enum,
        )
        .order_by(Publication.created_at.desc())
        .limit(limit)
    ).all()
    for pub in pubs:
        variant = pub.variant
        if variant is None:
            continue
        piece = variant.piece
        if exclude_piece_id is not None and piece.id == exclude_piece_id:
            continue
        payload = variant.payload or {}
        headline = str(payload.get("headline") or payload.get("title") or "").strip()
        text = str(payload.get("text") or payload.get("body_markdown") or "").strip()
        theme = ""
        if piece.plan_item is not None:
            theme = (piece.plan_item.theme or "").strip()
        fingerprint = (headline or text or theme)[:160]
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(
            {
                "headline": headline[:120],
                "theme": theme[:160],
                "text": text[:280],
            }
        )
        if len(out) >= limit:
            break
    return out
