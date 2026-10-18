"""platform policies v1 storage

Revision ID: 0009_platform_policies_v1
Revises: 0008_brand_content_profile
Create Date: 2026-10-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_platform_policies_v1"
down_revision: Union[str, None] = "0008_brand_content_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_content_profiles",
        sa.Column("platform_policies_v1", sa.JSON(), nullable=True),
    )
    op.add_column(
        "brand_content_profiles",
        sa.Column(
            "platform_policies_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("brand_content_profiles", "platform_policies_version")
    op.drop_column("brand_content_profiles", "platform_policies_v1")
