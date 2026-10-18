"""plan item brief fields for ContentBriefV2

Revision ID: 0010_plan_item_brief_fields
Revises: 0009_platform_policies_v1
Create Date: 2026-10-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_plan_item_brief_fields"
down_revision: Union[str, None] = "0009_platform_policies_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_items",
        sa.Column("audience_segment", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plan_items",
        sa.Column("audience_pain", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plan_items",
        sa.Column("takeaway", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plan_items",
        sa.Column("scene_seed", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plan_items",
        sa.Column("image_concept", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    for col in (
        "image_concept",
        "scene_seed",
        "takeaway",
        "audience_pain",
        "audience_segment",
    ):
        op.drop_column("plan_items", col)
