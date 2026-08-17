"""channel accounts, media assets, email recipients

Revision ID: 0004_channels_media
Revises: 0003_plans_content
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_channels_media"
down_revision: Union[str, None] = "0003_plans_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="error"),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=True),
        sa.Column("refresh_ciphertext", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_channel_accounts_brand_id", "channel_accounts", ["brand_id"])

    op.create_table(
        "email_recipients",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("brand_id", "email", name="uq_email_recipients_brand_email"),
    )
    op.create_index("ix_email_recipients_brand_id", "email_recipients", ["brand_id"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="image"),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_media_assets_brand_id", "media_assets", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_brand_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_email_recipients_brand_id", table_name="email_recipients")
    op.drop_table("email_recipients")
    op.drop_index("ix_channel_accounts_brand_id", table_name="channel_accounts")
    op.drop_table("channel_accounts")
