from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.models import User
from app.services.auth_service import get_user_by_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise AppError(401, "unauthorized", "Необходима авторизация")
    return get_user_by_access_token(db, creds.credentials)
