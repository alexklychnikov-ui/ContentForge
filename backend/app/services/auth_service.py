from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.errors import AppError
from app.models import Membership, MembershipRole, RefreshToken, User, Workspace
from app.schemas import AuthResponse, TokenPair, UserPublic, WorkspacePublic
from app.security import (
    as_utc,
    decode_token,
    encode_token,
    hash_password,
    utc_now,
    verify_dummy_password,
    verify_password,
)
from app.services.audit import write_audit
from app.services.rate_limit import login_rate_limiter


def _issue_tokens(db: Session, user: User) -> TokenPair:
    settings = get_settings()
    access, _, _ = encode_token(user.id, "access", settings.jwt_access_ttl_seconds)
    refresh, refresh_jti, refresh_exp = encode_token(
        user.id, "refresh", settings.jwt_refresh_ttl_seconds
    )
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            expires_at=refresh_exp,
        )
    )
    db.flush()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_in=settings.jwt_access_ttl_seconds,
    )


def _primary_membership(user: User) -> Membership:
    if not user.memberships:
        raise AppError(500, "error", "У пользователя нет workspace")
    owners = [m for m in user.memberships if m.role == MembershipRole.owner]
    return owners[0] if owners else user.memberships[0]


def _auth_response(user: User, membership: Membership, tokens: TokenPair) -> AuthResponse:
    return AuthResponse(
        user=UserPublic.model_validate(user),
        workspace=WorkspacePublic(
            id=membership.workspace.id,
            name=membership.workspace.name,
            created_at=membership.workspace.created_at,
            openai_soft_quota_tokens=membership.workspace.openai_soft_quota_tokens,
            role=membership.role,
        ),
        tokens=tokens,
    )


def _user_with_workspace(db: Session, user_id: UUID) -> User:
    user = db.scalars(
        select(User)
        .options(joinedload(User.memberships).joinedload(Membership.workspace))
        .where(User.id == user_id)
    ).unique().one_or_none()
    if user is None:
        raise AppError(401, "unauthorized", "Необходима авторизация")
    return user


def register_user(db: Session, email: str, password: str, workspace_name: str) -> AuthResponse:
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise AppError(409, "email_taken", "Этот email уже зарегистрирован")

    user = User(email=email, password_hash=hash_password(password), is_active=True)
    workspace = Workspace(name=workspace_name)
    membership = Membership(user=user, workspace=workspace, role=MembershipRole.owner)
    db.add_all([user, workspace, membership])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "email_taken", "Этот email уже зарегистрирован") from exc

    tokens = _issue_tokens(db, user)
    return _auth_response(user, membership, tokens)


def login_user(db: Session, email: str, password: str, ip: str) -> AuthResponse:
    login_rate_limiter.check(ip, email)
    user = db.scalars(
        select(User)
        .options(joinedload(User.memberships).joinedload(Membership.workspace))
        .where(User.email == email)
    ).unique().one_or_none()
    if user is None or not user.is_active:
        verify_dummy_password(password)
        login_rate_limiter.record_failure(ip, email)
        raise AppError(401, "invalid_credentials", "Неверный email или пароль")
    if not verify_password(user.password_hash, password):
        login_rate_limiter.record_failure(ip, email)
        raise AppError(401, "invalid_credentials", "Неверный email или пароль")

    login_rate_limiter.reset(ip, email)
    tokens = _issue_tokens(db, user)
    membership = _primary_membership(user)
    write_audit(
        db,
        actor_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        ip=ip,
        data={},
    )
    return _auth_response(user, membership, tokens)


def refresh_tokens(db: Session, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, "refresh")
        user_id = UUID(str(payload["sub"]))
        jti = str(payload["jti"])
    except (ValueError, KeyError) as exc:
        raise AppError(401, "invalid_refresh", "Недействительный refresh-токен") from exc

    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    now = utc_now()
    if (
        stored is None
        or stored.user_id != user_id
        or stored.revoked_at is not None
        or as_utc(stored.expires_at) <= now
    ):
        raise AppError(401, "invalid_refresh", "Недействительный refresh-токен")

    stored.revoked_at = now
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "invalid_refresh", "Недействительный refresh-токен")
    return _issue_tokens(db, user)


def logout_user(db: Session, user: User) -> None:
    now = utc_now()
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    for token in tokens:
        token.revoked_at = now


def get_user_by_access_token(db: Session, token: str) -> User:
    try:
        payload = decode_token(token, "access")
        user_id = UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise AppError(401, "unauthorized", "Необходима авторизация") from exc
    user = _user_with_workspace(db, user_id)
    if not user.is_active:
        raise AppError(401, "unauthorized", "Необходима авторизация")
    return user
