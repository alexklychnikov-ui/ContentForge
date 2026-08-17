"""identity, brand kit, holidays, trends

Revision ID: 0002_identity
Revises: 0001_baseline
Create Date: 2026-08-17
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.catalogs.ru_holidays import SEED_YEARS, holidays_for_year

revision: str = "0002_identity"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("openai_soft_quota_tokens", sa.Integer(), nullable=True),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )

    op.create_table(
        "brand_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("niche", sa.Text(), nullable=False, server_default=""),
        sa.Column("audience", sa.Text(), nullable=False, server_default=""),
        sa.Column("voice_tone", sa.Text(), nullable=False, server_default=""),
        sa.Column("stopwords", sa.JSON(), nullable=False),
        sa.Column("offers", sa.JSON(), nullable=False),
        sa.Column("example_posts", sa.JSON(), nullable=False),
        sa.Column("default_locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "holidays",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False, server_default="RU"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_holidays_date", "holidays", ["date"])
    op.create_index(
        "uq_holidays_system_date_country",
        "holidays",
        ["date", "country"],
        unique=True,
        postgresql_where=sa.text("source = 'system'"),
        sqlite_where=sa.text("source = 'system'"),
    )

    op.create_table(
        "trend_signals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(["brand_id"], ["brand_profiles.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("jti", name="uq_refresh_tokens_jti"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)

    holidays_table = sa.table(
        "holidays",
        sa.column("id", sa.Uuid),
        sa.column("date", sa.Date),
        sa.column("name", sa.String),
        sa.column("country", sa.String),
        sa.column("source", sa.String),
        sa.column("brand_id", sa.Uuid),
    )
    rows = []
    for year in SEED_YEARS:
        for holiday_date, name in holidays_for_year(year):
            rows.append(
                {
                    "id": uuid4(),
                    "date": holiday_date,
                    "name": name,
                    "country": "RU",
                    "source": "system",
                    "brand_id": None,
                }
            )
    if rows:
        op.bulk_insert(holidays_table, rows)


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("trend_signals")
    op.drop_index("uq_holidays_system_date_country", table_name="holidays")
    op.drop_index("ix_holidays_date", table_name="holidays")
    op.drop_table("holidays")
    op.drop_table("brand_profiles")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
