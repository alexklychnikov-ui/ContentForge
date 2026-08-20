from uuid import uuid4

import pytest

from app.config import get_settings
from app.services.meta_oauth import (
    build_meta_auth_url,
    decode_meta_oauth_state,
    encode_meta_oauth_state,
    meta_redirect_uri,
)


def test_meta_oauth_state_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "meta_app_id", "1382440990693447")
    monkeypatch.setattr(
        get_settings(),
        "public_api_url",
        "https://kitchen.alexklyvibe.ru",
    )
    user_id = uuid4()
    brand_id = uuid4()
    state = encode_meta_oauth_state(user_id, brand_id)
    decoded_user, decoded_brand = decode_meta_oauth_state(state)
    assert decoded_user == user_id
    assert decoded_brand == brand_id
    url = build_meta_auth_url(state)
    assert "facebook.com" in url
    assert "instagram_content_publish" in url
    assert meta_redirect_uri() == "https://kitchen.alexklyvibe.ru/api/v1/channels/oauth/callback"
