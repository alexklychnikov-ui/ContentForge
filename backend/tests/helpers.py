from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Membership, MembershipRole, User

BRAND_PAYLOAD = {
    "name": "NODEX",
    "niche": "B2B SaaS",
    "audience": "маркетологи агентств",
    "voice_tone": "прямо, без воды",
    "stopwords": ["гарантия"],
    "offers": ["аудит контента"],
    "example_posts": ["Кейс запуска за 14 дней"],
    "default_locale": "ru",
    "timezone": "Europe/Moscow",
}


def register_user(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = "password12",
    workspace_name: str = "Acme",
):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "workspace_name": workspace_name},
    )


def auth_header(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_brand(client: TestClient, headers: dict[str, str], **overrides):
    payload = {**BRAND_PAYLOAD, **overrides}
    return client.post("/api/v1/brands", json=payload, headers=headers)


def add_editor(db: Session, owner_email: str, editor_email: str) -> None:
    owner = db.query(User).filter(User.email == owner_email).one()
    editor = db.query(User).filter(User.email == editor_email).one()
    owner_membership = (
        db.query(Membership)
        .filter(Membership.user_id == owner.id, Membership.role == MembershipRole.owner)
        .one()
    )
    db.add(
        Membership(
            workspace_id=owner_membership.workspace_id,
            user_id=editor.id,
            role=MembershipRole.editor,
        )
    )
    db.commit()
