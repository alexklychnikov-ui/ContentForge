"""jobs, content plans, pieces, variants, audit stub

Revision ID: 0003_plans_content
Revises: 0002_identity
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_plans_content"
down_revision: Union[str, None] = "0002_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )
    op.create_index("ix_jobs_created_by", "jobs", ["created_by"])

    op.create_table(
        "content_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_content_plans_active_brand_month",
        "content_plans",
        ["brand_id", "year", "month"],
        unique=True,
        postgresql_where=sa.text("status IN ('generating', 'draft', 'approved')"),
        sqlite_where=sa.text("status IN ('generating', 'draft', 'approved')"),
    )

    op.create_table(
        "plan_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("channel_type", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("theme", sa.Text(), nullable=False, server_default=""),
        sa.Column("goal", sa.String(length=16), nullable=False, server_default="awareness"),
        sa.Column("hook", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_piece_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["plan_id"], ["content_plans.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "content_pieces",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("plan_item_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("stopword_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"], ondelete="SET NULL"),
    )

    op.create_foreign_key(
        "fk_plan_items_content_piece_id",
        "plan_items",
        "content_pieces",
        ["content_piece_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "content_variants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("piece_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False, server_default="A"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["piece_id"], ["content_pieces.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("content_variants")
    op.drop_constraint("fk_plan_items_content_piece_id", "plan_items", type_="foreignkey")
    op.drop_table("content_pieces")
    op.drop_table("plan_items")
    op.drop_index("uq_content_plans_active_brand_month", table_name="content_plans")
    op.drop_table("content_plans")
    op.drop_index("ix_jobs_created_by", table_name="jobs")
    op.drop_table("jobs")
