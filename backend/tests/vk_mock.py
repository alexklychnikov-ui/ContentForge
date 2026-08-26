from app.services.adapters.base import AdapterError

DEFAULT_POST_ID = 77


def install_vk_mock(monkeypatch, handler=None) -> list[dict]:
    calls: list[dict] = []

    def fake(
        method: str,
        token: str,
        params: dict | None = None,
        *,
        timeout: float = 30.0,
    ) -> object:
        calls.append(
            {
                "method": method,
                "token": token,
                "params": dict(params or {}),
                "timeout": timeout,
            }
        )
        if handler is not None:
            return handler(method, token, params, timeout=timeout)
        if method == "groups.getById":
            return [{"id": int((params or {}).get("group_id") or 1), "name": "test"}]
        if method == "wall.post":
            return {"post_id": DEFAULT_POST_ID}
        raise AssertionError(f"unexpected vk method {method}")

    monkeypatch.setattr("app.services.adapters.vk.vk_api", fake)
    return calls


def unauthorized_handler(method, token, params, timeout=30.0):
    raise AdapterError("unauthorized", "VK access denied", retryable=False)


def rate_limited_handler(method, token, params, timeout=30.0):
    raise AdapterError("rate_limited", "VK rate limit", retryable=True)
