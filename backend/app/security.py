import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

TokenType = Literal["access", "refresh"]

_TEST_HASHER = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
_PROD_HASHER = PasswordHasher()


def _hasher() -> PasswordHasher:
    if os.environ.get("TESTING") == "1":
        return _TEST_HASHER
    return _PROD_HASHER


_DUMMY_PASSWORD_HASH = _hasher().hash("contentforge-dummy-password")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    verify_password(_DUMMY_PASSWORD_HASH, password)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def encode_token(
    user_id: UUID,
    token_type: TokenType,
    ttl_seconds: int,
    jti: str | None = None,
) -> tuple[str, str, datetime]:
    settings = get_settings()
    now = utc_now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    token_jti = jti or str(uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": token_type,
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, token_jti, expires_at


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "jti", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("typ") != expected_type:
        raise ValueError("invalid token type")
    return payload
