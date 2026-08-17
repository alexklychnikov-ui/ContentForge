from app.services.adapters.base import AdapterError

DEFAULT_MESSAGE_ID = 42


def install_telegram_mock(monkeypatch, handler=None) -> list[dict]:
    calls: list[dict] = []

    def fake(token: str, method: str, data: dict | None = None, files: dict | None = None) -> dict:
        calls.append({"token": token, "method": method, "data": data or {}, "files": bool(files)})
        if handler is not None:
            return handler(token, method, data, files)
        if method == "getMe":
            return {"id": 1, "is_bot": True, "username": "nodex_bot"}
        if method in {"sendMessage", "sendPhoto"}:
            return {"message_id": DEFAULT_MESSAGE_ID, "chat": {"id": (data or {}).get("chat_id")}}
        raise AssertionError(f"unexpected telegram method {method}")

    monkeypatch.setattr("app.services.adapters.telegram.telegram_api", fake)
    return calls


def unauthorized_handler(token, method, data, files):
    raise AdapterError("unauthorized", "Unauthorized", retryable=True)


def parse_error_handler(token, method, data, files):
    if method in {"sendMessage", "sendPhoto"}:
        raise AdapterError("parse_error", "can't parse entities", retryable=False)
    return {"id": 1, "is_bot": True}
