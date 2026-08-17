import logging
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from sqlalchemy.orm import Session

from app.models import ChannelAccount, ContentVariant, Publication
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

WP_TIMEOUT = 30.0
ALLOWED_SCHEMES = frozenset({"http", "https"})
POSTS_PATH = "wp-json/wp/v2/posts"


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_html(text: str) -> str:
    escaped = escape_html(text or "")
    parts = [part.strip() for part in escaped.split("\n\n") if part.strip()]
    if not parts:
        return "<p></p>"
    return "".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in parts)


def variant_post_fields(payload: dict | None) -> dict:
    data = payload or {}
    title = str(data.get("title") or data.get("subject") or data.get("text") or "").strip()
    if not title:
        raise AdapterError("bad_request", "Нет заголовка статьи", retryable=False)
    body = str(data.get("body_markdown") or data.get("excerpt") or data.get("text") or "")
    excerpt = str(data.get("excerpt") or "")
    slug = str(data.get("slug") or "").strip()
    fields = {
        "title": title,
        "content": markdown_to_html(body),
        "status": "publish",
        "excerpt": excerpt,
    }
    if slug:
        fields["slug"] = slug
    return fields


def wordpress_http_client() -> httpx.Client:
    return httpx.Client(timeout=WP_TIMEOUT, follow_redirects=False, trust_env=False)


def build_wordpress_posts_url(site_url: str) -> str:
    original = site_url or ""
    raw = original.strip()
    if not raw or any(ord(ch) < 32 for ch in original):
        raise AdapterError("bad_request", "Некорректный site_url", retryable=False)
        raise AdapterError("bad_request", "Некорректный site_url", retryable=False)
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise AdapterError("bad_request", "Некорректный site_url", retryable=False)
    if parsed.username or parsed.password or not parsed.hostname:
        raise AdapterError("bad_request", "Некорректный site_url", retryable=False)
    if parsed.params or parsed.query or parsed.fragment:
        raise AdapterError("bad_request", "Некорректный site_url", retryable=False)
    base_path = parsed.path.rstrip("/") + "/"
    base = urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), base_path, "", "", ""))
    return urljoin(base, POSTS_PATH)


def wordpress_result_or_raise(response: httpx.Response, app_password: str) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = ""
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("code") or "")
    safe = redact_secret(message, app_password)
    if response.status_code == 429:
        raise AdapterError("rate_limited", "WordPress rate limit", retryable=True)
    if response.status_code in {401, 403}:
        raise AdapterError("unauthorized", safe or "Неверный Application Password", retryable=True)
    if response.status_code == 400:
        raise AdapterError("bad_request", safe or "WordPress rejected the request", retryable=False)
    if response.status_code >= 500:
        raise AdapterError("adapter_error", "WordPress server error", retryable=True)
    if response.status_code >= 400:
        raise AdapterError("adapter_error", safe or "WordPress request failed", retryable=False)
    if not isinstance(payload, dict) or payload.get("id") is None:
        raise AdapterError("adapter_error", "WordPress response missing id", retryable=False)
    return payload


def wordpress_create_post(
    site_url: str,
    username: str,
    app_password: str,
    payload: dict,
) -> dict:
    url = build_wordpress_posts_url(site_url)
    password = (app_password or "").replace(" ", "")
    try:
        with wordpress_http_client() as client:
            response = client.post(url, json=payload, auth=(username, password))
    except httpx.HTTPError:
        logger.warning("wordpress_http_error")
        raise AdapterError("adapter_error", "WordPress network error", retryable=True) from None
    except Exception:
        logger.warning("wordpress_http_error")
        raise AdapterError("adapter_error", "WordPress request failed", retryable=True) from None
    return wordpress_result_or_raise(response, app_password)


def _app_password(account: ChannelAccount) -> str:
    if not account.token_ciphertext:
        raise AdapterError("missing_credentials", "Нет токена канала", retryable=False)
    try:
        return decrypt_secret(account.token_ciphertext)
    except TokenEncryptionError as exc:
        raise AdapterError("missing_credentials", "Не удалось расшифровать токен", retryable=False) from exc


class WordPressAdapter(ChannelAdapter):
    supports_autopost = True

    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        password = _app_password(account)
        meta = account.meta or {}
        site_url = str(meta.get("site_url") or meta.get("blog_url") or account.external_account_id or "")
        username = str(meta.get("username") or "")
        if not site_url or not username:
            raise AdapterError("bad_request", "Не указаны site_url или username", retryable=False)
        fields = variant_post_fields(variant.payload)
        logger.info("wordpress_publish host=%s", urlparse(site_url).hostname)
        result = wordpress_create_post(site_url, username, password, fields)
        external_id = str(result["id"])
        link = result.get("link")
        return AdapterResult(
            external_id=external_id,
            external_url=str(link) if link else None,
        )

    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        return empty_unavailable(reason="wordpress_views_unavailable")

    def health(self, account: ChannelAccount) -> ChannelHealth:
        return ciphertext_health(account)

    def limits(self) -> AdapterLimits:
        return AdapterLimits(max_text_len=100_000, requires_media=False)
