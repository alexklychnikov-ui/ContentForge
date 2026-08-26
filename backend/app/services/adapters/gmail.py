import logging
import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

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
from app.services.metrics import from_gmail_meta
from app.services.recipient_service import GMAIL_RECIPIENT_CAP, list_active_recipients
from app.services.token_crypto import TokenEncryptionError, decrypt_secret

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
SMTP_TIMEOUT = 30.0
QUOTA_MARKERS = (
    "quota",
    "dailylimit",
    "daily sending",
    "daily user sending",
    "5.4.5",
    "rate limit",
)
_GREETING_LINE_RE = re.compile(
    r"^(привет|здравствуй(?:те)?|добрый день|добрый вечер|hello|hi)\b",
    re.IGNORECASE,
)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def with_recipient_greeting(body: str, name: str | None) -> str:
    cleaned = (name or "").strip()
    greeting = f"Привет, {cleaned}!" if cleaned else "Привет!"
    text = body or ""
    if "\n" in text:
        first_line, rest = text.split("\n", 1)
    else:
        first_line, rest = text, ""
    if _GREETING_LINE_RE.match(first_line.strip()):
        remainder = rest.lstrip("\n")
        return f"{greeting}\n\n{remainder}" if remainder else greeting
    if text.strip():
        return f"{greeting}\n\n{text}"
    return f"{greeting}\n\n"


def is_quota_error(exc: BaseException) -> bool:
    code = getattr(exc, "smtp_code", None)
    raw = getattr(exc, "smtp_error", b"")
    if isinstance(raw, bytes):
        detail = raw.decode("utf-8", "replace")
    else:
        detail = str(raw or "")
    blob = f"{code} {detail} {exc}".lower()
    return any(marker in blob for marker in QUOTA_MARKERS)


def smtp_error_to_adapter(exc: BaseException, app_password: str | None) -> AdapterError:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return AdapterError("unauthorized", "Gmail SMTP auth failed", retryable=False)
    if is_quota_error(exc):
        return AdapterError("rate_limited", "Gmail daily quota exceeded", retryable=False)
    code = getattr(exc, "smtp_code", None)
    retryable = True if code is None else int(code) < 500
    safe = redact_secret(str(exc), app_password)
    return AdapterError("adapter_error", safe or "Gmail SMTP error", retryable=retryable)


def build_email_message(
    from_email: str,
    to_email: str,
    payload: dict | None,
    recipient_name: str | None = None,
) -> EmailMessage:
    data = payload or {}
    subject = str(data.get("subject") or data.get("title") or "").strip()
    if not subject:
        raise AdapterError("bad_request", "Нет темы письма", retryable=False)
    body = with_recipient_greeting(
        str(data.get("body_markdown") or data.get("body_html") or ""),
        recipient_name,
    )
    preheader = str(data.get("preheader") or "")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid()
    msg.set_content(body or " ")
    html_parts = []
    if preheader:
        html_parts.append(
            f'<div style="display:none;max-height:0;overflow:hidden">{escape_html(preheader)}</div>'
        )
    escaped = escape_html(body)
    paragraphs = [part.strip() for part in escaped.split("\n\n") if part.strip()]
    html_parts.extend(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in paragraphs or [""])
    msg.add_alternative("".join(html_parts), subtype="html")
    return msg


def smtp_send_one(
    from_email: str,
    app_password: str,
    to_email: str,
    message: EmailMessage,
) -> str:
    password = (app_password or "").replace(" ", "")
    if not message.get("Message-ID"):
        message["Message-ID"] = make_msgid()
    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(from_email, password)
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        logger.warning("gmail_smtp_error type=%s", type(exc).__name__)
        raise smtp_error_to_adapter(exc, app_password) from None
    except OSError:
        logger.warning("gmail_smtp_error type=OSError")
        raise AdapterError("adapter_error", "Gmail SMTP network error", retryable=True) from None
    except Exception as exc:
        logger.warning("gmail_smtp_error type=%s", type(exc).__name__)
        raise AdapterError("adapter_error", "Gmail SMTP error", retryable=True) from None
    return str(message["Message-ID"])


def _app_password(account: ChannelAccount) -> str:
    if not account.token_ciphertext:
        raise AdapterError("missing_credentials", "Нет токена канала", retryable=False)
    try:
        return decrypt_secret(account.token_ciphertext)
    except TokenEncryptionError as exc:
        raise AdapterError("missing_credentials", "Не удалось расшифровать токен", retryable=False) from exc


def _from_email(account: ChannelAccount) -> str:
    meta = account.meta or {}
    value = str(meta.get("gmail_from") or account.external_account_id or "").strip().lower()
    if not value:
        raise AdapterError("bad_request", "Не указан from_email", retryable=False)
    return value


class GmailAdapter(ChannelAdapter):
    supports_autopost = True

    def publish(
        self,
        db: Session,
        account: ChannelAccount,
        variant: ContentVariant,
        publication: Publication,
    ) -> AdapterResult:
        password = _app_password(account)
        from_email = _from_email(account)
        recipients = list_active_recipients(db, account.brand_id, limit=GMAIL_RECIPIENT_CAP)
        if not recipients:
            raise AdapterError("no_recipients", "Нет активных получателей", retryable=False)
        logger.info("gmail_send recipient_count=%s", len(recipients))
        sent_ids: list[str] = []
        failed = 0
        first_id: str | None = None
        stop_error: AdapterError | None = None
        for recipient in recipients:
            message = build_email_message(
                from_email,
                recipient.email,
                variant.payload,
                recipient_name=recipient.name,
            )
            try:
                message_id = smtp_send_one(from_email, password, recipient.email, message)
            except AdapterError as exc:
                failed += 1
                if exc.code in {"rate_limited", "unauthorized", "missing_credentials"}:
                    stop_error = exc
                    break
                continue
            sent_ids.append(str(recipient.id))
            if first_id is None:
                first_id = message_id
        meta = {
            "sent_count": len(sent_ids),
            "failed_count": failed,
            "recipient_ids": sent_ids,
        }
        publication.meta = {**(publication.meta or {}), **meta}
        if first_id is None:
            raise stop_error or AdapterError("adapter_error", "Gmail send failed", retryable=False)
        return AdapterResult(external_id=first_id, meta=meta)

    def fetch_metrics(self, account: ChannelAccount, publication: Publication) -> dict:
        return from_gmail_meta(publication.meta)

    def health(self, account: ChannelAccount) -> ChannelHealth:
        return ciphertext_health(account)

    def limits(self) -> AdapterLimits:
        return AdapterLimits(max_text_len=100_000, requires_media=False)
