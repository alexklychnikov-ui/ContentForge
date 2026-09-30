"""brand content profile 1:1

Revision ID: 0008_brand_content_profile
Revises: 0007_brand_auto_pipeline
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_brand_content_profile"
down_revision: Union[str, None] = "0007_brand_auto_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_content_profiles",
        sa.Column("brand_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("positioning", sa.Text(), nullable=False, server_default=""),
        sa.Column("audience_segments", sa.JSON(), nullable=False),
        sa.Column("audience_pains", sa.JSON(), nullable=False),
        sa.Column("content_pillars", sa.JSON(), nullable=False),
        sa.Column("proof_facts", sa.JSON(), nullable=False),
        sa.Column("preferred_cta_styles", sa.JSON(), nullable=False),
        sa.Column("banned_openers", sa.JSON(), nullable=False),
        sa.Column("structure_rules", sa.Text(), nullable=False, server_default=""),
        sa.Column("platform_policies", sa.JSON(), nullable=False),
        sa.Column(
            "knowledge_mode",
            sa.String(length=16),
            nullable=False,
            server_default="off",
        ),
        sa.Column("knowledge_filters", sa.JSON(), nullable=False),
        sa.Column(
            "require_human_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("brand_content_profiles")
