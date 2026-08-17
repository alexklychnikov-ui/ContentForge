"""publications state machine

Revision ID: 0005_publications
Revises: 0004_channels_media
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_publications"
down_revision: Union[str, None] = "0004_channels_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("variant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("channel_account_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1024), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("experiment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["content_variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["channel_account_id"], ["channel_accounts.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_publications_idempotency_key"),
    )
    op.create_index(
        "ix_publications_status_scheduled_at",
        "publications",
        ["status", "scheduled_at"],
    )
    op.create_index("ix_publications_channel_account_id", "publications", ["channel_account_id"])
    op.create_index("ix_publications_variant_id", "publications", ["variant_id"])


def downgrade() -> None:
    op.drop_index("ix_publications_variant_id", table_name="publications")
    op.drop_index("ix_publications_channel_account_id", table_name="publications")
    op.drop_index("ix_publications_status_scheduled_at", table_name="publications")
    op.drop_table("publications")
