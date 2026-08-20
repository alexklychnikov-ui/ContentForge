from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models import ChannelType, ContentType, PlanGoal

_GOAL_ALIASES = {
    "awareness": PlanGoal.awareness,
    "traffic": PlanGoal.traffic,
    "lead": PlanGoal.lead,
    "leads": PlanGoal.lead,
    "retention": PlanGoal.retention,
    "engage": PlanGoal.retention,
    "engagement": PlanGoal.retention,
}


class PlanItemAI(BaseModel):
    date: date
    channel_type: ChannelType
    content_type: ContentType
    theme: str = Field(min_length=1)
    goal: PlanGoal
    hook: str = Field(min_length=1)

    @field_validator("channel_type", "content_type", mode="before")
    @classmethod
    def _lower_enum(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("goal", mode="before")
    @classmethod
    def _coerce_goal(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().lower()
            return _GOAL_ALIASES.get(key, key)
        return value

    @field_validator("theme", "hook", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class PlanAIResult(BaseModel):
    items: list[PlanItemAI]


class SocialPostAI(BaseModel):
    text: str = Field(min_length=1)
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    alt_text: str = ""


class ArticleAI(BaseModel):
    title: str = Field(min_length=1)
    excerpt: str = ""
    body_markdown: str = Field(min_length=1)
    seo_title: str = ""
    seo_description: str = ""
    slug: str = ""


class EmailAI(BaseModel):
    subject: str = Field(min_length=1)
    preheader: str = ""
    body_markdown: str = Field(min_length=1)


class RewriteAI(BaseModel):
    replacement: str


CONTENT_SCHEMA_BY_TYPE = {
    ContentType.social_post: SocialPostAI,
    ContentType.article: ArticleAI,
    ContentType.email: EmailAI,
}

PRIMARY_TEXT_FIELD = {
    ContentType.social_post: "text",
    ContentType.article: "body_markdown",
    ContentType.email: "body_markdown",
}
