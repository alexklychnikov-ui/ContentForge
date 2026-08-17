import logging
import os
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import ChannelAccount, ChannelStatus, ContentVariant, MediaAsset, Publication
from app.schemas import ChannelHealth
from app.services.adapters.base import (
    AdapterError,
    AdapterLimits,
    AdapterResult,
    ChannelAdapter,
    ciphertext_health,
    redact_secret,
)
from app.services.metrics import empty_unavailable
from app.services.media_service import media_file_path
from app.services.token_crypto import TokenEncryptionError, decrypt_secret

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_METHODS = frozenset({"getMe", "sendMessage", "sendPhoto"})
_UNSAFE_TOKEN_CHARS = frozenset("/\\?#@ \t\r\n")
HTML_PARSE_MODE = "HTML"
SEND_TIMEOUT = 30.0
MAX_TEXT = 4096
MAX_CAPTION = 1024
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SOCKS_RETRY_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ProxyError,
    httpx.ReadError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def variant_text(payload: dict | None) -> str:
    data = payload or {}
    if data.get("text"):
        parts = [str(data["text"])]
        cta = data.get("cta")
        if cta:
            parts.append(str(cta))
        tags = data.get("hashtags") or []
        if isinstance(tags, list) and tags:
            parts.append(" ".join(f"#{str(tag).lstrip('#')}" for tag in tags if tag))
        return "\n\n".join(part for part in parts if part)
    title = data.get("title") or data.get("subject") or ""
    body = data.get("body_markdown") or data.get("excerpt") or ""
    return "\n\n".join(part for part in (str(title), str(body)) if part).strip()


def _media_id(payload: dict | None) -> UUID | None:
    raw = (payload or {}).get("media_id") or (payload or {}).get("image_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def telegram_proxy_url() -> str | None:
    # Request-time env first: uvicorn --reload / worker spawn can keep empty get_settings lru_cache.
    env = (os.environ.get("TELEGRAM_HTTPS_PROXY") or "").strip()
    if env:
        return env
    value = (get_settings().telegram_https_proxy or "").strip()
    return value or None


def telegram_via() -> str:
    return "proxy" if telegram_proxy_url() else "direct"


def redact_proxy_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    if not (parts.username or parts.password):
        return url
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, f"***@{netloc}", parts.path, parts.query, parts.fragment))


def http_loopback_as_socks5h(proxy: str) -> str | None:
    parts = urlsplit(proxy)
    if parts.scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS or parts.port is None:
        return None
    return urlunsplit(("socks5h", parts.netloc, "", "", ""))


def _client_for_proxy(proxy: str | None) -> httpx.Client:
    try:
        if proxy:
            return httpx.Client(
                timeout=SEND_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                proxy=proxy,
            )
        return httpx.Client(timeout=SEND_TIMEOUT, follow_redirects=False, trust_env=False)
    except ImportError:
        logger.warning("telegram_http_error method=client via=proxy")
        raise AdapterError(
            "adapter_error",
            "SOCKS proxy requires httpx[socks]",
            retryable=False,
        ) from None


def telegram_http_client() -> httpx.Client:
    return _client_for_proxy(telegram_proxy_url())


def _telegram_post(
    client: httpx.Client,
    url: str,
    data: dict | None,
    files: dict | None,
) -> httpx.Response:
    if files:
        return client.post(url, data=data or {}, files=files)
    return client.post(url, json=data or {})


def _network_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.RemoteProtocolError):
        return "proxy_http_on_socks"
    return "Telegram network error"


def build_telegram_url(token: str, method: str) -> str:
    if method not in TELEGRAM_METHODS:
        raise AdapterError("bad_request", "Unsupported Telegram method", retryable=False)
    if not token or any(ch in token for ch in _UNSAFE_TOKEN_CHARS) or "://" in token:
        raise AdapterError("unauthorized", "Неверный bot token", retryable=False)
    return f"{TELEGRAM_API_BASE}/bot{token}/{method}"


def telegram_result_or_raise(response: httpx.Response, token: str) -> dict:
    try:
        payload = response.json()
    except ValueError:
        raise AdapterError("adapter_error", "Telegram returned non-JSON", retryable=True) from None
    error_code = payload.get("error_code") if isinstance(payload, dict) else None
    description = str(payload.get("description") or "") if isinstance(payload, dict) else ""
    safe = redact_secret(description, token)
    if response.status_code == 429 or error_code == 429:
        raise AdapterError("rate_limited", "Telegram rate limit", retryable=True)
    if response.status_code == 400 or error_code == 400:
        lowered = description.lower()
        code = "parse_error" if "parse" in lowered or "entities" in lowered else "bad_request"
        raise AdapterError(code, safe or "Telegram rejected the request", retryable=False)
    if response.status_code in {401, 403} or error_code in {401, 403}:
        raise AdapterError("unauthorized", safe or "Неверный bot token", retryable=True)
    if response.status_code >= 500:
        raise AdapterError("adapter_error", "Telegram server error", retryable=True)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise AdapterError("adapter_error", safe or "Telegram request failed", retryable=False)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AdapterError("adapter_error", "Telegram response missing result", retryable=False)
    return result


def telegram_api(
    token: str,
    method: str,
    data: dict | None = None,
    files: dict | None = None,
) -> dict:
    url = build_telegram_url(token, method)
    configured = telegram_proxy_url()
    attempts: list[str | None] = [configured]
    fallback = http_loopback_as_socks5h(configured) if configured else None
    if fallback:
        attempts.append(fallback)
    response: httpx.Response | None = None
    last_error: AdapterError | None = None
    for index, proxy in enumerate(attempts):
        try:
            with _client_for_proxy(proxy) as client:
                response = _telegram_post(client, url, data, files)
            break
        except AdapterError:
            raise
        except httpx.HTTPError as exc:
            logger.warning(
                "telegram_http_error method=%s via=%s err=%s",
                method,
                telegram_via(),
                type(exc).__name__,
            )
            last_error = AdapterError(
                "adapter_error",
                _network_error_message(exc),
                retryable=True,
            )
            can_retry = index + 1 < len(attempts) and isinstance(exc, _SOCKS_RETRY_ERRORS)
            if can_retry:
                continue
            raise last_error from None
    if response is None:
        raise last_error or AdapterError("adapter_error", "Telegram network error", retryable=True)
    return telegram_result_or_raise(response, token)


def _bot_token(account: ChannelAccount) -> str:
    if not account.token_ciphertext:
        raise AdapterError("missing_credentials", "Нет токена канала", retryable=False)
    try:
        return decrypt_secret(account.token_ciphertext)
    except TokenEncryptionError as exc:
        raise AdapterError("missing_credentials", "Не удалось расшифровать токен", retryable=False) from exc


def _with_via(message: str) -> str:
    text = f"{message} via={telegram_via()}"
    proxy = telegram_proxy_url()
    if proxy:
        text = text.replace(proxy, redact_proxy_url(proxy))
        parts = urlsplit(proxy)
        if parts.password:
            text = text.replace(parts.password, "***")
        if parts.username:
            text = text.replace(parts.username, "***")
    return text


def _health_reason(exc: AdapterError) -> str:
    if exc.code == "missing_credentials":
        return "Не удалось расшифровать токен. Revoke и подключите канал заново."
    if exc.code == "unauthorized":
        return _with_via("Неверный bot token (getMe).")
    lowered = (exc.message or "").lower()
    if exc.message == "SOCKS proxy requires httpx[socks]":
        return _with_via("SOCKS proxy requires httpx[socks].")
    if exc.message == "proxy_http_on_socks":
        return _with_via("Прокси SOCKS5, не HTTP CONNECT. Укажите socks5h://127.0.0.1:<порт>.")
    if exc.code == "adapter_error" and "network" in lowered:
        return _with_via("Нет связи с api.telegram.org.")
    return _with_via("Проверка Telegram не удалась.")


class TelegramAdapter(ChannelAdapter):
    supports_autopost = True

    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        token = _bot_token(account)
        chat_id = str((account.meta or {}).get("channel_id") or account.external_account_id or "")
        if not chat_id:
            raise AdapterError("bad_request", "Не указан channel_id", retryable=False)
        text = variant_text(variant.payload)
        if len(text) > self.limits().max_text_len:
            raise AdapterError("too_long", "Текст длиннее лимита Telegram", retryable=False)
        html = escape_html(text) if text else " "
        media_id = _media_id(variant.payload)
        method = "sendPhoto" if media_id else "sendMessage"
        logger.info("telegram_send method=%s chat_id=%s", method, chat_id)
        if media_id is not None:
            result = self._send_photo(db, account, token, chat_id, html, media_id)
        else:
            result = telegram_api(
                token,
                "sendMessage",
                {"chat_id": chat_id, "text": html, "parse_mode": HTML_PARSE_MODE},
            )
        message_id = result.get("message_id")
        if message_id is None:
            raise AdapterError("adapter_error", "Telegram did not return message_id", retryable=False)
        return AdapterResult(external_id=str(message_id))

    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        return empty_unavailable(reason="telegram_insights_unavailable")

    def health(self, account: ChannelAccount) -> ChannelHealth:
        stub = ciphertext_health(account)
        if not stub.ok or stub.status != ChannelStatus.connected:
            return stub
        try:
            token = _bot_token(account)
            telegram_api(token, "getMe", {})
        except AdapterError as exc:
            return ChannelHealth(
                id=account.id,
                status=ChannelStatus.error,
                ok=False,
                reason=_health_reason(exc),
            )
        return ChannelHealth(
            id=account.id,
            status=ChannelStatus.connected,
            ok=True,
            reason=_with_via("getMe ok"),
        )

    def limits(self) -> AdapterLimits:
        return AdapterLimits(max_text_len=MAX_TEXT, requires_media=False)

    def _send_photo(
        self,
        db: Session,
        account: ChannelAccount,
        token: str,
        chat_id: str,
        caption: str,
        media_id: UUID,
    ) -> dict:
        asset = db.get(MediaAsset, media_id)
        if asset is None or asset.brand_id != account.brand_id:
            return telegram_api(
                token,
                "sendMessage",
                {"chat_id": chat_id, "text": caption, "parse_mode": HTML_PARSE_MODE},
            )
        try:
            path = media_file_path(asset)
            photo_bytes = path.read_bytes()
        except AppError:
            return telegram_api(
                token,
                "sendMessage",
                {"chat_id": chat_id, "text": caption, "parse_mode": HTML_PARSE_MODE},
            )
        return telegram_api(
            token,
            "sendPhoto",
            {
                "chat_id": chat_id,
                "caption": caption[:MAX_CAPTION],
                "parse_mode": HTML_PARSE_MODE,
            },
            files={"photo": (path.name, photo_bytes, asset.mime)},
        )
