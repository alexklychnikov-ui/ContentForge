from app.services.adapters.base import AdapterError

DEFAULT_POST_ID = 99
DEFAULT_POST_LINK = "https://blog.example/p/99"


def install_wordpress_mock(monkeypatch, handler=None) -> list[dict]:
    calls: list[dict] = []

    def fake(site_url: str, username: str, app_password: str, payload: dict) -> dict:
        calls.append(
            {
                "site_url": site_url,
                "username": username,
                "payload": payload,
            }
        )
        if handler is not None:
            return handler(site_url, username, app_password, payload)
        return {"id": DEFAULT_POST_ID, "link": DEFAULT_POST_LINK}

    monkeypatch.setattr("app.services.adapters.wordpress.wordpress_create_post", fake)
    return calls


def unauthorized_wp_handler(site_url, username, app_password, payload):
    raise AdapterError("unauthorized", "Неверный Application Password", retryable=True)
