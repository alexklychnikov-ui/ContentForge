from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import KnowledgeMode
from app.services.knowledge_grounding import GroundingStatus, ground_knowledge
from app.services.lightrag_client import (
    LightRAGAuthError,
    LightRAGClient,
    LightRAGUnavailableError,
)
from tests.helpers import auth_header, create_brand, register_user


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        headers: dict | None = None,
        *,
        bad_json: bool = False,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {}
        self._bad_json = bad_json

    def json(self) -> dict:
        if self._bad_json:
            raise ValueError("bad json")
        return self._payload


class _FakeClient:
    def __init__(self, handler) -> None:
        self._handler = handler

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args) -> None:
        return None

    def request(self, method: str, url: str, **kwargs) -> _FakeResponse:
        return self._handler(method, url, **kwargs)


def _profile(
    *,
    mode: KnowledgeMode = KnowledgeMode.optional,
    filters: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        brand_id="brand-1",
        knowledge_mode=mode,
        knowledge_filters=filters or [],
    )


def test_lightrag_query_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(method: str, url: str, **kwargs) -> _FakeResponse:
        assert method == "POST"
        assert url.endswith("/query")
        assert kwargs["headers"]["X-API-Key"] == "secret"
        body = kwargs["json"]
        assert body["query"] == "python ai"
        assert body["mode"] == "mix"
        assert body["only_need_context"] is True
        assert body["include_references"] is True
        return _FakeResponse(
            payload={
                "response": "context about python",
                "references": [
                    {
                        "reference_id": "1",
                        "file_path": "docs/python.md",
                        "content": "snippet",
                    }
                ],
            }
        )

    monkeypatch.setattr(
        LightRAGClient,
        "_http_client",
        lambda self: _FakeClient(handler),
    )
    client = LightRAGClient(
        base_url="https://lightrag.example",
        api_key="secret",
        timeout_seconds=5,
        retry_attempts=0,
    )
    result = client.query("python ai")
    assert result.response == "context about python"
    assert len(result.references) == 1
    assert result.references[0].file_path == "docs/python.md"


def test_lightrag_query_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LightRAGClient,
        "_http_client",
        lambda self: _FakeClient(lambda *a, **k: _FakeResponse(status_code=401)),
    )
    client = LightRAGClient(
        base_url="https://lightrag.example",
        api_key="bad",
        retry_attempts=0,
    )
    with pytest.raises(LightRAGAuthError):
        client.query("python ai")


def test_lightrag_query_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    class BoomClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def request(self, *args, **kwargs):
            return boom()

    monkeypatch.setattr(LightRAGClient, "_http_client", lambda self: BoomClient())
    client = LightRAGClient(
        base_url="https://lightrag.example",
        api_key="secret",
        retry_attempts=0,
    )
    with pytest.raises(LightRAGUnavailableError):
        client.query("python ai")


def test_lightrag_query_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LightRAGClient,
        "_http_client",
        lambda self: _FakeClient(
            lambda *a, **k: _FakeResponse(payload={"response": "", "references": []})
        ),
    )
    client = LightRAGClient(
        base_url="https://lightrag.example",
        api_key="secret",
        retry_attempts=0,
    )
    result = client.query("python ai")
    assert result.response == ""
    assert result.references == []


def test_lightrag_truncates_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LightRAGClient,
        "_http_client",
        lambda self: _FakeClient(
            lambda *a, **k: _FakeResponse(payload={"response": "x" * 100})
        ),
    )
    client = LightRAGClient(
        base_url="https://lightrag.example",
        api_key="secret",
        retry_attempts=0,
        max_chars=20,
    )
    result = client.query("python ai", max_chars=20)
    assert result.response == "x" * 20
    assert result.truncated is True


def test_grounding_off_skips() -> None:
    result = ground_knowledge(_profile(mode=KnowledgeMode.off), "python ai")
    assert result.status == GroundingStatus.skipped
    assert result.context == ""
    assert result.references == []


def test_grounding_required_blocks_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(response="", references=[])
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.required),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.blocked
    assert result.error_code == "empty"


def test_grounding_optional_ungrounded_on_failure() -> None:
    fake = MagicMock()
    fake.query.side_effect = LightRAGUnavailableError("down")
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.optional),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.ungrounded
    assert result.error_code == "unavailable"
    assert result.warning


def test_grounding_required_blocks_on_filter() -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(
        response="full unfiltered leak",
        references=[
            SimpleNamespace(
                reference_id="1",
                file_path="docs/other.md",
                content="other",
            ),
        ],
    )
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.required, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.blocked
    assert result.error_code == "filtered"
    assert result.context == ""


def test_grounding_optional_ungrounded_on_filter_miss() -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(
        response="full unfiltered leak",
        references=[
            SimpleNamespace(
                reference_id="1",
                file_path="docs/other.md",
                content="other",
            ),
        ],
    )
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.optional, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.ungrounded
    assert result.error_code == "filtered"
    assert result.context == ""
    assert "full unfiltered leak" not in (result.context or "")


def test_grounding_filters_rebuild_scoped_context() -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(
        response="FULL UNFILTERED RESPONSE SHOULD NOT LEAK",
        references=[
            SimpleNamespace(
                reference_id="1",
                file_path="docs/portfolio.md",
                content="portfolio fact A",
            ),
            SimpleNamespace(
                reference_id="2",
                file_path="docs/other.md",
                content="noise",
            ),
            SimpleNamespace(
                reference_id="portfolio-note",
                file_path="docs/misc.md",
                content="portfolio fact B",
            ),
        ],
    )
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.required, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.grounded
    assert result.context == "portfolio fact A\n\nportfolio fact B"
    assert "FULL UNFILTERED" not in result.context
    assert [ref.file_path for ref in result.references] == [
        "docs/portfolio.md",
        "docs/misc.md",
    ]


def test_grounding_filters_empty_refs_not_grounded_with_full_response() -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(
        response="FULL UNFILTERED RESPONSE SHOULD NOT LEAK",
        references=[],
    )
    required = ground_knowledge(
        _profile(mode=KnowledgeMode.required, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert required.status == GroundingStatus.blocked
    assert required.error_code == "filtered"
    assert required.context == ""

    optional = ground_knowledge(
        _profile(mode=KnowledgeMode.optional, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert optional.status == GroundingStatus.ungrounded
    assert optional.error_code == "filtered"
    assert optional.context == ""


def test_grounding_filters_matched_refs_without_content_not_grounded() -> None:
    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(
        response="FULL UNFILTERED RESPONSE SHOULD NOT LEAK",
        references=[
            SimpleNamespace(
                reference_id="1",
                file_path="docs/portfolio.md",
                content=None,
            ),
        ],
    )
    result = ground_knowledge(
        _profile(mode=KnowledgeMode.required, filters=["portfolio"]),
        "python ai",
        client=fake,
    )
    assert result.status == GroundingStatus.blocked
    assert result.error_code == "filtered"
    assert result.context == ""
    assert "FULL UNFILTERED" not in (result.context or "")


def test_knowledge_preview_endpoint_off(client: TestClient) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]

    response = client.post(
        f"/api/v1/brands/{brand_id}/knowledge/preview",
        json={"query": "python ai"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped"
    assert body["context"] == ""
    assert body["references"] == []


def test_knowledge_preview_required_maps_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    patched = client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={"knowledge_mode": "required"},
        headers=headers,
    )
    assert patched.status_code == 200

    fake = MagicMock()
    fake.query.return_value = SimpleNamespace(response="", references=[])
    monkeypatch.setattr(
        "app.services.knowledge_grounding.get_lightrag_client",
        lambda: fake,
    )

    response = client.post(
        f"/api/v1/brands/{brand_id}/knowledge/preview",
        json={"query": "python ai"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "empty"


def test_knowledge_preview_optional_ungrounded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = register_user(client).json()
    headers = auth_header(owner["tokens"])
    brand_id = create_brand(client, headers).json()["id"]
    patched = client.patch(
        f"/api/v1/brands/{brand_id}/content-profile",
        json={"knowledge_mode": "optional"},
        headers=headers,
    )
    assert patched.status_code == 200

    fake = MagicMock()
    fake.query.side_effect = LightRAGUnavailableError("down")
    monkeypatch.setattr(
        "app.services.knowledge_grounding.get_lightrag_client",
        lambda: fake,
    )

    response = client.post(
        f"/api/v1/brands/{brand_id}/knowledge/preview",
        json={"query": "python ai"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ungrounded"
    assert body["error_code"] == "unavailable"
