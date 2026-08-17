from email.message import EmailMessage

from app.services.adapters.base import AdapterError

DEFAULT_MESSAGE_ID = "<cf-mock-1@gmail.com>"


def install_gmail_mock(monkeypatch, handler=None) -> list[dict]:
    calls: list[dict] = []

    def fake(from_email: str, app_password: str, to_email: str, message: EmailMessage) -> str:
        calls.append(
            {
                "from_email": from_email,
                "to_email": to_email,
                "subject": str(message.get("Subject") or ""),
                "message_id": str(message.get("Message-ID") or DEFAULT_MESSAGE_ID),
            }
        )
        if handler is not None:
            return handler(from_email, app_password, to_email, message)
        return str(message.get("Message-ID") or DEFAULT_MESSAGE_ID)

    monkeypatch.setattr("app.services.adapters.gmail.smtp_send_one", fake)
    return calls


def quota_handler(from_email, app_password, to_email, message):
    raise AdapterError("rate_limited", "Gmail daily quota exceeded", retryable=False)


def auth_handler(from_email, app_password, to_email, message):
    raise AdapterError("unauthorized", "Gmail SMTP auth failed", retryable=False)
