from datetime import date as Date
from datetime import datetime as DateTime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import (
    BrandProfile,
    ChannelStatus,
    ChannelType,
    ContentType,
    ExperimentMode,
    ExperimentStatus,
    HolidaySource,
    JobStatus,
    JobType,
    Locale,
    MediaKind,
    MembershipRole,
    PieceStatus,
    PlanGoal,
    PlanStatus,
    PublicationStatus,
    RecipientSource,
    RecipientStatus,
    TrendSource,
    TrendStatus,
)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    is_active: bool
    created_at: DateTime


class WorkspacePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: DateTime
    openai_soft_quota_tokens: int | None = None
    role: MembershipRole | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(BaseModel):
    user: UserPublic
    workspace: WorkspacePublic
    tokens: TokenPair


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    workspace_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("workspace_name")
    @classmethod
    def strip_workspace_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("workspace_name is required")
        return stripped


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class BrandPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    niche: str
    audience: str
    voice_tone: str
    stopwords: list[str]
    offers: list[str]
    example_posts: list[str]
    default_locale: Locale
    timezone: str
    onboarding_completed_at: DateTime | None
    onboarding_completed: bool
    created_at: DateTime


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    niche: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    voice_tone: str = Field(min_length=1)
    stopwords: list[str] = Field(default_factory=list)
    offers: list[str] = Field(default_factory=list)
    example_posts: list[str] = Field(default_factory=list)
    default_locale: Locale = Locale.ru
    timezone: str = Field(default="Europe/Moscow", min_length=1, max_length=64)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    niche: str | None = None
    audience: str | None = None
    voice_tone: str | None = None
    stopwords: list[str] | None = None
    offers: list[str] | None = None
    example_posts: list[str] | None = None
    default_locale: Locale | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class HolidayPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date: Date
    name: str
    country: str
    source: HolidaySource
    brand_id: UUID | None


class HolidayCreate(BaseModel):
    date: Date
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="RU", min_length=2, max_length=8)


class TrendPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID | None
    title: str
    note: str
    starts_on: Date | None
    ends_on: Date | None
    status: TrendStatus
    source: TrendSource


class TrendCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    note: str = ""
    starts_on: Date | None = None
    ends_on: Date | None = None


class TrendUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = None
    starts_on: Date | None = None
    ends_on: Date | None = None
    status: TrendStatus | None = None
    archived: bool | None = None


class GeneratePlanRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    channels: list[ChannelType] = Field(default_factory=list)
    targets: dict[str, int] = Field(default_factory=dict)
    locale: Locale = Locale.ru
    include_holidays: bool = True
    include_trends: bool = True
    confirm: bool = False
    create_revision: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)


class JobAccepted(BaseModel):
    job_id: UUID


class JobPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: JobType
    status: JobStatus
    result: dict | None = None
    error: str | None = None
    created_at: DateTime


class PlanItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    date: Date
    channel_type: ChannelType
    content_type: ContentType
    theme: str
    goal: PlanGoal
    hook: str
    content_piece_id: UUID | None
    sort_order: int


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    year: int
    month: int
    status: PlanStatus
    params: dict
    model: str
    created_by: UUID
    created_at: DateTime
    items: list[PlanItemPublic] = Field(default_factory=list)


class PlanPatch(BaseModel):
    status: PlanStatus | None = None


class PlanItemCreate(BaseModel):
    date: Date
    channel_type: ChannelType
    content_type: ContentType
    theme: str = Field(min_length=1)
    goal: PlanGoal = PlanGoal.awareness
    hook: str = ""


class PlanItemUpdate(BaseModel):
    date: Date | None = None
    channel_type: ChannelType | None = None
    content_type: ContentType | None = None
    theme: str | None = Field(default=None, min_length=1)
    goal: PlanGoal | None = None
    hook: str | None = None


class ContentCreate(BaseModel):
    type: ContentType
    locale: Locale | None = None
    plan_item_id: UUID | None = None


class PiecePatch(BaseModel):
    status: PieceStatus | None = None


class VariantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    piece_id: UUID
    label: str
    payload: dict
    revision: int
    is_immutable: bool


class PiecePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    type: ContentType
    locale: Locale
    status: PieceStatus
    plan_item_id: UUID | None
    stopword_override: bool
    created_at: DateTime
    variants: list[VariantPublic] = Field(default_factory=list)


class GenerateContentRequest(BaseModel):
    variant_label: str = "A"
    channel_type: ChannelType | None = None
    extra_instructions: str = ""
    idempotency_key: str | None = Field(default=None, max_length=128)


class VariantCreate(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    payload: dict = Field(default_factory=dict)


class VariantPatch(BaseModel):
    payload: dict | None = None


class RewriteSelection(BaseModel):
    field: str | None = None
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class RewriteRequest(BaseModel):
    selection: RewriteSelection
    extra_instructions: str = ""
    idempotency_key: str | None = Field(default=None, max_length=128)


class ScheduleRequest(BaseModel):
    variant_id: UUID
    channel_account_id: UUID | None = None
    scheduled_at: DateTime | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    stopword_override: bool = False


class MarkManualRequest(BaseModel):
    external_url: str | None = Field(default=None, max_length=1024)


class PublicationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    channel_account_id: UUID
    scheduled_at: DateTime
    status: PublicationStatus
    external_id: str | None = None
    external_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int
    idempotency_key: str | None = None
    experiment_id: UUID | None = None
    published_at: DateTime | None = None
    meta: dict = Field(default_factory=dict)
    created_at: DateTime
    updated_at: DateTime


class ChannelCredentialsRequest(BaseModel):
    pdn_consent: bool = False
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    bot_token: str | None = None
    channel_id: str | None = None
    site_url: str | None = None
    username: str | None = None
    app_password: str | None = None
    from_email: EmailStr | None = None
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    access_token: str | None = None
    refresh_token: str | None = None
    group_id: str | None = None
    ig_user_id: str | None = None
    token_expires_at: DateTime | None = None
    scopes: list[str] = Field(default_factory=list)
    external_account_id: str | None = None


class ChannelPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    type: ChannelType
    display_name: str
    status: ChannelStatus
    scopes: list
    token_expires_at: DateTime | None
    external_account_id: str | None
    meta: dict
    revoked_at: DateTime | None


class ChannelHealth(BaseModel):
    id: UUID
    status: ChannelStatus
    ok: bool
    reason: str | None = None


class OAuthStartResponse(BaseModel):
    auth_url: str
    state: str


class RecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RecipientPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    status: RecipientStatus | None = None


class RecipientPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    email: str
    name: str | None
    status: RecipientStatus
    source: RecipientSource


class MediaPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    kind: MediaKind
    storage_key: str
    mime: str
    width: int | None
    height: int | None
    checksum: str
    url: str


class ExperimentCreate(BaseModel):
    piece_id: UUID
    variant_a_id: UUID
    variant_b_id: UUID
    channel_type: ChannelType
    mode: ExperimentMode = ExperimentMode.sequential
    primary_metric: str = Field(min_length=1, max_length=32)
    window_start: DateTime
    window_end: DateTime
    schedule_a: DateTime
    schedule_b: DateTime


class WinnerRequest(BaseModel):
    variant_id: UUID


class ExperimentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    piece_id: UUID
    variant_a_id: UUID
    variant_b_id: UUID
    channel_type: ChannelType
    mode: ExperimentMode
    primary_metric: str
    window_start: DateTime
    window_end: DateTime
    schedule_a: DateTime
    schedule_b: DateTime
    status: ExperimentStatus
    winner_variant_id: UUID | None = None
    created_at: DateTime
    metrics: dict | None = None


def brand_to_public(brand: BrandProfile) -> BrandPublic:
    return BrandPublic(
        id=brand.id,
        workspace_id=brand.workspace_id,
        name=brand.name,
        niche=brand.niche,
        audience=brand.audience,
        voice_tone=brand.voice_tone,
        stopwords=list(brand.stopwords or []),
        offers=list(brand.offers or []),
        example_posts=list(brand.example_posts or []),
        default_locale=brand.default_locale,
        timezone=brand.timezone,
        onboarding_completed_at=brand.onboarding_completed_at,
        onboarding_completed=brand.onboarding_completed_at is not None,
        created_at=brand.created_at,
    )
