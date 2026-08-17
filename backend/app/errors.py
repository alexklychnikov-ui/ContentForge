from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    secret_fields = {
        "password",
        "refresh_token",
        "access_token",
        "password_hash",
        "bot_token",
        "app_password",
        "token",
        "token_ciphertext",
        "refresh_ciphertext",
    }
    cleaned: list[dict[str, Any]] = []
    for item in errors:
        loc = item.get("loc", ())
        loc_names = {str(part) for part in loc}
        entry: dict[str, Any] = {
            "loc": list(loc),
            "msg": item.get("msg"),
            "type": item.get("type"),
        }
        if loc_names.isdisjoint(secret_fields) and "input" in item:
            entry["input"] = item.get("input")
        cleaned.append(entry)
    return cleaned


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code == 204:
        return JSONResponse(status_code=204, content=None)
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = str(detail.get("code"))
        message = str(detail.get("message", code))
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message, details))
    code_by_status = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }
    code = code_by_status.get(exc.status_code, "error")
    message = detail if isinstance(detail, str) else code
    return JSONResponse(status_code=exc.status_code, content=error_body(code, str(message)))


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Ошибка валидации",
            {"errors": _sanitize_validation_errors(exc.errors())},
        ),
    )
