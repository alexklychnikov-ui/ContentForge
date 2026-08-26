import logging

import httpx
from sqlalchemy.orm import Session

from app.models import ChannelAccount, ChannelStatus, ContentVariant, Publication
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
from app.services.token_crypto import TokenEncryptionError, decrypt_secret

logger = logging.getLogger(__name__)

VK_API_HOST = "api.vk.com"
VK_API_BASE = f"https://{VK_API_HOST}"
VK_API_VERSION = "5.199"
HEALTH_TIMEOUT = 10.0
PUBLISH_TIMEOUT = 30.0
MAX_TEXT = 4096
VK_METHODS = frozenset({"groups.getById", "wall.post"})
RATE_LIMIT_CODES = frozenset({6, 9, 14, 29})
AUTH_DENIED_CODES = frozenset({5, 15, 27, 203, 214})


def variant_text(payload: dict | None) -> str:
    data = payload or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return ""
    parts = [text]
    cta = data.get("cta")
    if cta:
        parts.append(str(cta))
    tags = data.get("hashtags") or []
    if isinstance(tags, list) and tags:
        parts.append(" ".join(f"#{str(tag).lstrip('#')}" for tag in tags if tag))
    return "\n\n".join(part for part in parts if part)


def wall_url(group_id: str, post_id: int | str) -> str:
    return f"https://vk.com/wall-{group_id}_{post_id}"


def vk_http_client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)


def vk_result_or_raise(response: httpx.Response, token: str) -> object:
    try:
        payload = response.json()
    except ValueError:
        raise AdapterError("adapter_error", "VK returned non-JSON", retryable=True) from None

    if response.status_code == 429:
        raise AdapterError("rate_limited", "VK rate limit", retryable=True)
    if response.status_code in {401, 403}:
        raise AdapterError("unauthorized", "VK access denied", retryable=False)
    if response.status_code >= 500:
        raise AdapterError("adapter_error", "VK server error", retryable=True)

    if not isinstance(payload, dict):
        raise AdapterError("adapter_error", "VK response invalid", retryable=False)

    error = payload.get("error")
    if isinstance(error, dict):
        raw_code = error.get("error_code")
        try:
            error_code = int(raw_code) if raw_code is not None else None
        except (TypeError, ValueError):
            error_code = None
        error_msg = str(error.get("error_msg") or "")
        safe = redact_secret(error_msg, token)
        lowered = error_msg.lower()
        if (
            error_code in RATE_LIMIT_CODES
            or "flood" in lowered
            or "captcha" in lowered
            or "too many" in lowered
        ):
            raise AdapterError("rate_limited", safe or "VK rate limit", retryable=True)
        if error_code in AUTH_DENIED_CODES or "access denied" in lowered or "auth" in lowered:
            raise AdapterError("unauthorized", safe or "VK access denied", retryable=False)
        logger.warning("vk_api_error code=%s", error_code)
        raise AdapterError("adapter_error", safe or "VK request failed", retryable=False)

    if response.status_code >= 400:
        raise AdapterError("adapter_error", "VK request failed", retryable=False)

    if "response" not in payload:
        raise AdapterError("adapter_error", "VK response missing result", retryable=False)
    return payload["response"]


def vk_api(
    method: str,
    token: str,
    params: dict | None = None,
    *,
    timeout: float = PUBLISH_TIMEOUT,
) -> object:
    if method not in VK_METHODS:
        raise AdapterError("bad_request", "Unsupported VK method", retryable=False)
    url = f"{VK_API_BASE}/method/{method}"
    body = {**(params or {}), "access_token": token, "v": VK_API_VERSION}
    try:
        with vk_http_client(timeout) as client:
            response = client.post(url, data=body)
    except httpx.HTTPError:
        logger.warning("vk_http_error method=%s", method)
        raise AdapterError("adapter_error", "VK network error", retryable=True) from None
    return vk_result_or_raise(response, token)


def _access_token(account: ChannelAccount) -> str:
    if not account.token_ciphertext:
        raise AdapterError("missing_credentials", "Нет токена канала", retryable=False)
    try:
        return decrypt_secret(account.token_ciphertext)
    except TokenEncryptionError as exc:
        raise AdapterError("missing_credentials", "Не удалось расшифровать токен", retryable=False) from exc


def _group_id(account: ChannelAccount) -> str:
    group_id = str((account.meta or {}).get("group_id") or "").strip()
    if not group_id or not group_id.isdigit():
        raise AdapterError("bad_request", "Не указан group_id", retryable=False)
    return group_id


def _health_reason(exc: AdapterError) -> str:
    if exc.code == "missing_credentials":
        return "Не удалось расшифровать токен. Revoke и подключите канал заново."
    if exc.code == "unauthorized":
        return "Неверный community token или нет доступа к сообществу."
    if exc.code == "bad_request":
        return "Не указан group_id."
    lowered = (exc.message or "").lower()
    if exc.code == "adapter_error" and "network" in lowered:
        return "Нет связи с api.vk.com."
    return "Проверка VK не удалась."


class VkAdapter(ChannelAdapter):
    supports_autopost = True

    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        group_id = _group_id(account)
        text = variant_text(variant.payload)
        if not text.strip():
            raise AdapterError("bad_request", "Пустой текст для VK", retryable=False)
        if len(text) > self.limits().max_text_len:
            raise AdapterError("too_long", "Текст длиннее лимита VK", retryable=False)
        token = _access_token(account)
        params: dict[str, str | int] = {
            "owner_id": f"-{group_id}",
            "from_group": 1,
            "message": text,
        }
        if publication.idempotency_key:
            params["guid"] = publication.idempotency_key
        logger.info("vk_wall_post group_id=%s", group_id)
        result = vk_api("wall.post", token, params, timeout=PUBLISH_TIMEOUT)
        post_id = None
        if isinstance(result, dict):
            post_id = result.get("post_id")
        if post_id is None:
            raise AdapterError("adapter_error", "VK did not return post_id", retryable=False)
        return AdapterResult(
            external_id=str(post_id),
            external_url=wall_url(group_id, post_id),
        )

    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        return empty_unavailable(reason="vk_insights_unavailable")

    def health(self, account: ChannelAccount) -> ChannelHealth:
        stub = ciphertext_health(account)
        if not stub.ok or stub.status != ChannelStatus.connected:
            return stub
        try:
            token = _access_token(account)
            group_id = _group_id(account)
            vk_api(
                "groups.getById",
                token,
                {"group_id": group_id},
                timeout=HEALTH_TIMEOUT,
            )
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
            reason="groups.getById ok",
        )

    def limits(self) -> AdapterLimits:
        return AdapterLimits(max_text_len=MAX_TEXT, requires_media=False)
