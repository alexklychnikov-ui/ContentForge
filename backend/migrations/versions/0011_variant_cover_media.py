"""content variant cover media id

Revision ID: 0011_variant_cover_media
Revises: 0010_plan_item_brief_fields
Create Date: 2026-10-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_variant_cover_media"
down_revision: Union[str, None] = "0010_plan_item_brief_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_variants",
        sa.Column("cover_media_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_content_variants_cover_media_id",
        "content_variants",
        "media_assets",
        ["cover_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_content_variants_cover_media_id", "content_variants", type_="foreignkey")
    op.drop_column("content_variants", "cover_media_id")
