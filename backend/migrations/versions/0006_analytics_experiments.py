"""analytics snapshots and sequential experiments

Revision ID: 0006_analytics_experiments
Revises: 0005_publications
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_analytics_experiments"
down_revision: Union[str, None] = "0005_publications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("piece_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_a_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_b_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="sequential"),
        sa.Column("primary_metric", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_a", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_b", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("winner_variant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["piece_id"], ["content_pieces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_a_id"], ["content_variants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["variant_b_id"], ["content_variants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["winner_variant_id"], ["content_variants.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_experiments_piece_id", "experiments", ["piece_id"])
    op.create_index(
        "uq_experiments_active_piece",
        "experiments",
        ["piece_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('draft', 'running')"),
        postgresql_where=sa.text("status IN ('draft', 'running')"),
    )

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("publication_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_analytics_snapshots_publication_captured",
        "analytics_snapshots",
        ["publication_id", "captured_at"],
    )

    op.create_foreign_key(
        "fk_publications_experiment_id",
        "publications",
        "experiments",
        ["experiment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_publications_experiment_id", "publications", type_="foreignkey")
    op.drop_index(
        "ix_analytics_snapshots_publication_captured", table_name="analytics_snapshots"
    )
    op.drop_table("analytics_snapshots")
    op.drop_index("uq_experiments_active_piece", table_name="experiments")
    op.drop_index("ix_experiments_piece_id", table_name="experiments")
    op.drop_table("experiments")
