import logging
import re
from contextvars import ContextVar
from uuid import uuid4

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[str | None] = ContextVar("job_id", default=None)
publication_id_ctx: ContextVar[str | None] = ContextVar("publication_id", default=None)

_BOT_URL_RE = re.compile(r"/bot[^/\s]+/")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)(password|passwd|token|bot_token|app_password|refresh_token|access_token"
    r"|authorization)([\"'\s:=]+)([^\s\"',}]+)"
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+=/]+")


def redact_log_text(text: str) -> str:
    if not text:
        return text
    cleaned = _BOT_URL_RE.sub("/bot***/", text)
    cleaned = _SECRET_ASSIGN_RE.sub(r"\1\2***", cleaned)
    cleaned = _BEARER_RE.sub(r"\1***", cleaned)
    return cleaned


class SecretRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_log_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_log_text(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_log_text(item) if isinstance(item, str) else item for item in record.args
                )
        if record.exc_text:
            record.exc_text = redact_log_text(record.exc_text)
        return True


def configure_app_logging() -> None:
    root = logging.getLogger()
    if not any(isinstance(item, SecretRedactFilter) for item in root.filters):
        root.addFilter(SecretRedactFilter())
    app_logger = logging.getLogger("app")
    if not any(isinstance(item, SecretRedactFilter) for item in app_logger.filters):
        app_logger.addFilter(SecretRedactFilter())


def bind_request_id(header_value: str | None) -> str:
    value = (header_value or "").strip() or uuid4().hex
    request_id_ctx.set(value)
    return value


def structured_extra() -> dict[str, str]:
    extra: dict[str, str] = {}
    request_id = request_id_ctx.get()
    job_id = job_id_ctx.get()
    publication_id = publication_id_ctx.get()
    if request_id:
        extra["request_id"] = request_id
    if job_id:
        extra["job_id"] = job_id
    if publication_id:
        extra["publication_id"] = publication_id
    return extra


def log_event(logger: logging.Logger, message: str, **fields: object) -> None:
    parts = [message]
    merged = {**structured_extra(), **fields}
    for key, value in merged.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header_map = {key.decode().lower(): value.decode() for key, value in scope.get("headers") or []}
        request_id = bind_request_id(header_map.get("x-request-id"))
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status") or 500)
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        logger = logging.getLogger("app.http")
        try:
            await self.app(scope, receive, send_wrapper)
            log_event(
                logger,
                "http_request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
            )
        finally:
            request_id_ctx.set(None)
