from datetime import date

from pydantic import BaseModel, Field

from app.models import ChannelType, ContentType, PlanGoal


class PlanItemAI(BaseModel):
    date: date
    channel_type: ChannelType
    content_type: ContentType
    theme: str = Field(min_length=1)
    goal: PlanGoal
    hook: str = Field(min_length=1)


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
