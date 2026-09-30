from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 12_000
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
QUERY_MODES = frozenset({"mix", "local", "global", "hybrid", "naive", "bypass"})
DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF = 0.7


class LightRAGError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LightRAGAuthError(LightRAGError):
    pass


class LightRAGUnavailableError(LightRAGError):
    pass


@dataclass(frozen=True)
class LightRAGReference:
    reference_id: str
    file_path: str
    content: str | None = None


@dataclass(frozen=True)
class LightRAGQueryResult:
    response: str
    references: list[LightRAGReference] = field(default_factory=list)
    truncated: bool = False


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _parse_retry_after(value: str | None, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return max(float(value.strip()), 0.0)
    except ValueError:
        return fallback


class LightRAGClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 180,
        *,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.retry_attempts = max(0, int(retry_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.max_chars = max(0, int(max_chars))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LightRAGClient:
        cfg = settings or get_settings()
        return cls(
            base_url=cfg.lightrag_url,
            api_key=cfg.lightrag_api_key,
            timeout_seconds=cfg.lightrag_timeout_seconds,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        allow_retry: bool = True,
    ) -> httpx.Response:
        if not self.base_url:
            raise LightRAGUnavailableError("LightRAG URL is not configured")
        url = f"{self.base_url}{path}"
        attempts = self.retry_attempts + 1 if allow_retry else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                with self._http_client() as client:
                    response = client.request(
                        method.upper(),
                        url,
                        headers=self._headers(),
                        json=json_body,
                    )
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "lightrag_timeout method=%s path=%s attempt=%s",
                    method.upper(),
                    path,
                    attempt + 1,
                )
                if attempt < attempts - 1:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise LightRAGUnavailableError("LightRAG request timed out") from exc
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "lightrag_transport method=%s path=%s attempt=%s err=%s",
                    method.upper(),
                    path,
                    attempt + 1,
                    type(exc).__name__,
                )
                if attempt < attempts - 1:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise LightRAGUnavailableError("LightRAG transport error") from exc

            if response.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                delay = self.retry_backoff_seconds * (attempt + 1)
                if response.status_code == 429:
                    delay = _parse_retry_after(
                        response.headers.get("Retry-After"),
                        delay,
                    )
                logger.warning(
                    "lightrag_retry method=%s path=%s status=%s attempt=%s delay=%.2f",
                    method.upper(),
                    path,
                    response.status_code,
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue
            return response

        if last_error is not None:
            raise LightRAGUnavailableError("LightRAG request failed") from last_error
        raise LightRAGUnavailableError("LightRAG request failed")

    def _raise_for_status(self, response: httpx.Response, *, action: str) -> None:
        status = response.status_code
        if status in {401, 403}:
            logger.warning("lightrag_auth action=%s status=%s", action, status)
            raise LightRAGAuthError(
                "LightRAG authentication failed",
                status_code=status,
            )
        if status in RETRYABLE_STATUS:
            logger.warning("lightrag_unavailable action=%s status=%s", action, status)
            raise LightRAGUnavailableError(
                f"LightRAG unavailable ({status})",
                status_code=status,
            )
        if not (200 <= status < 300):
            logger.warning("lightrag_error action=%s status=%s", action, status)
            raise LightRAGError(
                f"LightRAG {action} failed ({status})",
                status_code=status,
            )

    def health(self) -> bool:
        response = self._request("GET", "/health", allow_retry=True)
        self._raise_for_status(response, action="health")
        return True

    def query(
        self,
        query: str,
        mode: str = "mix",
        *,
        only_need_context: bool = True,
        include_references: bool = True,
        max_chars: int | None = None,
    ) -> LightRAGQueryResult:
        text = (query or "").strip()
        if len(text) < 3:
            raise LightRAGError("query must be at least 3 characters")
        query_mode = (mode or "mix").strip().lower()
        if query_mode not in QUERY_MODES:
            raise LightRAGError(f"unsupported query mode: {mode}")

        response = self._request(
            "POST",
            "/query",
            json_body={
                "query": text,
                "mode": query_mode,
                "only_need_context": only_need_context,
                "include_references": include_references,
            },
            allow_retry=True,
        )
        self._raise_for_status(response, action="query")

        try:
            payload = response.json()
        except ValueError as exc:
            raise LightRAGError("LightRAG returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise LightRAGError("LightRAG response is not an object")

        raw_answer = payload.get("response")
        if raw_answer is None:
            raw_answer = payload.get("answer") or payload.get("result") or ""
        answer = str(raw_answer).strip()
        cap = self.max_chars if max_chars is None else max(0, int(max_chars))
        answer, truncated = _truncate(answer, cap)

        references: list[LightRAGReference] = []
        raw_refs = payload.get("references")
        if isinstance(raw_refs, list):
            for item in raw_refs:
                if not isinstance(item, dict):
                    continue
                ref_id = str(
                    item.get("reference_id")
                    or item.get("id")
                    or item.get("referenceId")
                    or ""
                ).strip()
                file_path = str(item.get("file_path") or item.get("filePath") or "").strip()
                content_raw = item.get("content")
                content = str(content_raw) if content_raw is not None else None
                if content is not None:
                    content, _ = _truncate(content, cap)
                if not ref_id and not file_path:
                    continue
                references.append(
                    LightRAGReference(
                        reference_id=ref_id or file_path,
                        file_path=file_path,
                        content=content,
                    )
                )

        logger.info(
            "lightrag_query_ok mode=%s chars=%s refs=%s truncated=%s",
            query_mode,
            len(answer),
            len(references),
            truncated,
        )
        return LightRAGQueryResult(
            response=answer,
            references=references,
            truncated=truncated,
        )


def get_lightrag_client() -> LightRAGClient:
    return LightRAGClient.from_settings()
