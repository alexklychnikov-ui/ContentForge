import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base
from app.security import utc_now


class MembershipRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"
    analyst = "analyst"
    viewer = "viewer"


class Locale(str, enum.Enum):
    ru = "ru"
    en = "en"


class HolidaySource(str, enum.Enum):
    system = "system"
    brand = "brand"


class TrendStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class TrendSource(str, enum.Enum):
    manual = "manual"
    provider = "provider"


class ChannelType(str, enum.Enum):
    instagram = "instagram"
    vk = "vk"
    telegram = "telegram"
    wordpress = "wordpress"
    gmail = "gmail"


class ChannelStatus(str, enum.Enum):
    connected = "connected"
    expired = "expired"
    missing_scopes = "missing_scopes"
    error = "error"
    revoked = "revoked"


class RecipientStatus(str, enum.Enum):
    active = "active"
    unsubscribed = "unsubscribed"


class RecipientSource(str, enum.Enum):
    manual = "manual"
    import_ = "import"


class MediaKind(str, enum.Enum):
    image = "image"


class ContentType(str, enum.Enum):
    social_post = "social_post"
    article = "article"
    email = "email"


class PlanStatus(str, enum.Enum):
    generating = "generating"
    draft = "draft"
    approved = "approved"
    archived = "archived"


class PlanGoal(str, enum.Enum):
    awareness = "awareness"
    traffic = "traffic"
    lead = "lead"
    retention = "retention"


class PieceStatus(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    archived = "archived"


class JobType(str, enum.Enum):
    generate_plan = "generate_plan"
    generate_content = "generate_content"
    rewrite = "rewrite"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class PublicationStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    publishing = "publishing"
    published = "published"
    published_manual = "published_manual"
    failed = "failed"
    dead = "dead"
    cancelled = "cancelled"


class ExperimentMode(str, enum.Enum):
    sequential = "sequential"
    gmail_split_list = "gmail_split_list"
    wordpress_title = "wordpress_title"


class ExperimentStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    tie = "tie"


ACTIVE_PLAN_STATUSES = (PlanStatus.generating, PlanStatus.draft, PlanStatus.approved)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")
    jobs: Mapped[list["Job"]] = relationship(back_populates="creator")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    openai_soft_quota_tokens: Mapped[int | None] = mapped_column(nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace")
    brands: Mapped[list["BrandProfile"]] = relationship(back_populates="workspace")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, native_enum=False, length=16), nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    niche: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_tone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stopwords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    offers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    example_posts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    default_locale: Mapped[Locale] = mapped_column(
        Enum(Locale, native_enum=False, length=8), nullable=False, default=Locale.ru
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Moscow")
    auto_pipeline_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_pipeline_lead_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    default_slot_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workspace: Mapped[Workspace] = relationship(back_populates="brands")
    holidays: Mapped[list["Holiday"]] = relationship(back_populates="brand")
    trends: Mapped[list["TrendSignal"]] = relationship(back_populates="brand")
    plans: Mapped[list["ContentPlan"]] = relationship(back_populates="brand")
    pieces: Mapped[list["ContentPiece"]] = relationship(back_populates="brand")
    channels: Mapped[list["ChannelAccount"]] = relationship(back_populates="brand")
    recipients: Mapped[list["EmailRecipient"]] = relationship(back_populates="brand")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="brand")


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (
        Index(
            "uq_holidays_system_date_country",
            "date",
            "country",
            unique=True,
            sqlite_where=text("source = 'system'"),
            postgresql_where=text("source = 'system'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False, default="RU")
    source: Mapped[HolidaySource] = mapped_column(
        Enum(HolidaySource, native_enum=False, length=16),
        nullable=False,
        default=HolidaySource.system,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=True
    )

    brand: Mapped[BrandProfile | None] = relationship(back_populates="holidays")


class TrendSignal(Base):
    __tablename__ = "trend_signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[TrendStatus] = mapped_column(
        Enum(TrendStatus, native_enum=False, length=16),
        nullable=False,
        default=TrendStatus.active,
    )
    source: Mapped[TrendSource] = mapped_column(
        Enum(TrendSource, native_enum=False, length=16),
        nullable=False,
        default=TrendSource.manual,
    )

    brand: Mapped[BrandProfile | None] = relationship(back_populates="trends")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=32), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16),
        nullable=False,
        default=JobStatus.queued,
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    creator: Mapped[User] = relationship(back_populates="jobs")


class ContentPlan(Base):
    __tablename__ = "content_plans"
    __table_args__ = (
        Index(
            "uq_content_plans_active_brand_month",
            "brand_id",
            "year",
            "month",
            unique=True,
            sqlite_where=text("status IN ('generating', 'draft', 'approved')"),
            postgresql_where=text("status IN ('generating', 'draft', 'approved')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, native_enum=False, length=16),
        nullable=False,
        default=PlanStatus.draft,
    )
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    brand: Mapped[BrandProfile] = relationship(back_populates="plans")
    items: Mapped[list["PlanItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanItem(Base):
    __tablename__ = "plan_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, native_enum=False, length=16), nullable=False
    )
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False, length=16), nullable=False
    )
    theme: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goal: Mapped[PlanGoal] = mapped_column(
        Enum(PlanGoal, native_enum=False, length=16),
        nullable=False,
        default=PlanGoal.awareness,
    )
    hook: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_piece_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "content_pieces.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_plan_items_content_piece_id",
        ),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    plan: Mapped[ContentPlan] = relationship(back_populates="items")
    pieces: Mapped[list["ContentPiece"]] = relationship(
        back_populates="plan_item",
        foreign_keys="ContentPiece.plan_item_id",
    )


class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False, length=16), nullable=False
    )
    locale: Mapped[Locale] = mapped_column(
        Enum(Locale, native_enum=False, length=8), nullable=False, default=Locale.ru
    )
    status: Mapped[PieceStatus] = mapped_column(
        Enum(PieceStatus, native_enum=False, length=16),
        nullable=False,
        default=PieceStatus.draft,
    )
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("plan_items.id", ondelete="SET NULL"), nullable=True
    )
    stopword_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    brand: Mapped[BrandProfile] = relationship(back_populates="pieces")
    plan_item: Mapped[PlanItem | None] = relationship(
        back_populates="pieces",
        foreign_keys=[plan_item_id],
    )
    variants: Mapped[list["ContentVariant"]] = relationship(
        back_populates="piece", cascade="all, delete-orphan"
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        back_populates="piece", cascade="all, delete-orphan"
    )


class ContentVariant(Base):
    __tablename__ = "content_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    piece_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_pieces.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="A")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    piece: Mapped[ContentPiece] = relationship(back_populates="variants")
    publications: Mapped[list["Publication"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


@event.listens_for(AuditLog, "before_update")
def _audit_log_no_update(*_args: object, **_kwargs: object) -> None:
    raise ValueError("AuditLog is append-only")


@event.listens_for(AuditLog, "before_delete")
def _audit_log_no_delete(*_args: object, **_kwargs: object) -> None:
    raise ValueError("AuditLog is append-only")


class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, native_enum=False, length=16), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, native_enum=False, length=16),
        nullable=False,
        default=ChannelStatus.error,
    )
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    brand: Mapped[BrandProfile] = relationship(back_populates="channels")
    publications: Mapped[list["Publication"]] = relationship(back_populates="channel")


class EmailRecipient(Base):
    __tablename__ = "email_recipients"
    __table_args__ = (
        UniqueConstraint("brand_id", "email", name="uq_email_recipients_brand_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, native_enum=False, length=16),
        nullable=False,
        default=RecipientStatus.active,
    )
    source: Mapped[RecipientSource] = mapped_column(
        Enum(RecipientSource, native_enum=False, length=16),
        nullable=False,
        default=RecipientSource.manual,
    )

    brand: Mapped[BrandProfile] = relationship(back_populates="recipients")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, native_enum=False, length=16),
        nullable=False,
        default=MediaKind.image,
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    brand: Mapped[BrandProfile] = relationship(back_populates="media_assets")


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        Index("ix_publications_status_scheduled_at", "status", "scheduled_at"),
        Index("ix_publications_channel_account_id", "channel_account_id"),
        Index("ix_publications_variant_id", "variant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_variants.id", ondelete="CASCADE"), nullable=False
    )
    channel_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("channel_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, native_enum=False, length=32),
        nullable=False,
        default=PublicationStatus.scheduled,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    variant: Mapped[ContentVariant] = relationship(back_populates="publications")
    channel: Mapped[ChannelAccount] = relationship(back_populates="publications")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="publications")
    snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(
        back_populates="publication", cascade="all, delete-orphan"
    )


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        Index(
            "uq_experiments_active_piece",
            "piece_id",
            unique=True,
            sqlite_where=text("status IN ('draft', 'running')"),
            postgresql_where=text("status IN ('draft', 'running')"),
        ),
        Index("ix_experiments_piece_id", "piece_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    piece_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_pieces.id", ondelete="CASCADE"), nullable=False
    )
    variant_a_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_variants.id", ondelete="RESTRICT"), nullable=False
    )
    variant_b_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_variants.id", ondelete="RESTRICT"), nullable=False
    )
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, native_enum=False, length=16), nullable=False
    )
    mode: Mapped[ExperimentMode] = mapped_column(
        Enum(ExperimentMode, native_enum=False, length=32),
        nullable=False,
        default=ExperimentMode.sequential,
    )
    primary_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schedule_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schedule_b: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus, native_enum=False, length=16),
        nullable=False,
        default=ExperimentStatus.draft,
    )
    winner_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_variants.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    piece: Mapped[ContentPiece] = relationship(back_populates="experiments")
    publications: Mapped[list["Publication"]] = relationship(back_populates="experiment")


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        Index("ix_analytics_snapshots_publication_captured", "publication_id", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    normalized: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    publication: Mapped[Publication] = relationship(back_populates="snapshots")
