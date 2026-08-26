"""brand auto pipeline fields

Revision ID: 0007_brand_auto_pipeline
Revises: 0006_analytics_experiments
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_brand_auto_pipeline"
down_revision: Union[str, None] = "0006_analytics_experiments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_profiles",
        sa.Column(
            "auto_pipeline_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "brand_profiles",
        sa.Column(
            "auto_pipeline_lead_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
    )
    op.add_column(
        "brand_profiles",
        sa.Column(
            "default_slot_hour",
            sa.Integer(),
            nullable=False,
            server_default="12",
        ),
    )


def downgrade() -> None:
    op.drop_column("brand_profiles", "default_slot_hour")
    op.drop_column("brand_profiles", "auto_pipeline_lead_hours")
    op.drop_column("brand_profiles", "auto_pipeline_enabled")
