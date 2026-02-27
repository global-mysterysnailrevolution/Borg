"""Async HTTP client for the Fastino Labs TLM API."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class FastinoAPIError(Exception):
    """Raised when the Fastino API returns an unexpected error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FastinoAuthError(FastinoAPIError):
    """Raised when the API key is missing, invalid, or revoked (HTTP 401/403)."""


class FastinoRateLimitError(FastinoAPIError):
    """Raised when the API returns HTTP 429 Too Many Requests."""


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


async def _sleep_backoff(attempt: int) -> None:
    """Exponential backoff: 1s, 2s, 4s for attempts 0, 1, 2."""
    delay = 2**attempt
    logger.debug("Retrying after %.1fs (attempt %d/%d)", delay, attempt + 1, _MAX_RETRIES)
    await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# FastinoClient
# ---------------------------------------------------------------------------


class FastinoClient:
    """Async client for the Fastino Labs TLM API.

    Usage::

        async with FastinoClient() as client:
            result = await client.extract(text="Hello world")

    The API key is read from the ``FASTINO_API_KEY`` environment variable.
    The request timeout is read from ``FASTINO_TIMEOUT`` (default: 15 seconds).
    """

    BASE_URL = "https://api.fastino.ai/v1"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("FASTINO_API_KEY", "")
        if not self._api_key:
            raise FastinoAuthError(
                "FASTINO_API_KEY environment variable is not set. "
                "Obtain an API key from https://fastino.ai and export it before starting the server."
            )

        _timeout_env = os.environ.get("FASTINO_TIMEOUT", "15")
        try:
            _timeout_value = float(_timeout_env)
        except ValueError:
            logger.warning(
                "Invalid FASTINO_TIMEOUT value %r; falling back to 15 seconds.", _timeout_env
            )
            _timeout_value = 15.0

        self._timeout = timeout if timeout is not None else _timeout_value
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "FastinoClient":
        self._client = self._build_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "fastino-mcp/0.1.0",
            },
            timeout=httpx.Timeout(self._timeout),
        )

    @property
    def _http(self) -> httpx.AsyncClient:
        """Return the underlying httpx client, creating one lazily if needed."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST *payload* to *path*, retrying on transient errors.

        Raises:
            FastinoAuthError: on HTTP 401 or 403.
            FastinoRateLimitError: when retries are exhausted after HTTP 429.
            FastinoAPIError: for any other non-2xx response.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._http.post(path, json=payload)
            except httpx.TimeoutException as exc:
                last_exc = FastinoAPIError(f"Request to {path} timed out: {exc}")
                if attempt < _MAX_RETRIES - 1:
                    await _sleep_backoff(attempt)
                continue
            except httpx.RequestError as exc:
                last_exc = FastinoAPIError(f"Network error reaching {path}: {exc}")
                if attempt < _MAX_RETRIES - 1:
                    await _sleep_backoff(attempt)
                continue

            # ---- Auth errors (never retried) ----
            if response.status_code in (401, 403):
                raise FastinoAuthError(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Check that FASTINO_API_KEY is correct and has not been revoked.",
                    status_code=response.status_code,
                )

            # ---- Rate-limit / server errors (retried) ----
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_exc = FastinoRateLimitError(
                    f"Received HTTP {response.status_code} from {path}.",
                    status_code=response.status_code,
                )
                if attempt < _MAX_RETRIES - 1:
                    await _sleep_backoff(attempt)
                continue

            # ---- Other non-2xx ----
            if response.is_error:
                _body = _safe_json(response)
                _msg = _body.get("detail") or _body.get("message") or response.text
                raise FastinoAPIError(
                    f"API error {response.status_code}: {_msg}",
                    status_code=response.status_code,
                )

            # ---- Success ----
            return response.json()

        # All retries exhausted
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Public API endpoints
    # ------------------------------------------------------------------

    async def extract(self, text: str, entity_types: list[str] | None = None) -> dict[str, Any]:
        """POST /extract — GLiNER-based named-entity recognition."""
        payload: dict[str, Any] = {"text": text}
        if entity_types is not None:
            payload["entity_types"] = entity_types
        return await self._post("/extract", payload)

    async def classify(
        self,
        text: str,
        labels: list[str],
        multi_label: bool = False,
    ) -> dict[str, Any]:
        """POST /classify — zero-shot text classification."""
        return await self._post(
            "/classify",
            {"text": text, "labels": labels, "multi_label": multi_label},
        )

    async def detect_pii(
        self,
        text: str,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /detect-pii — identify personally-identifiable information."""
        payload: dict[str, Any] = {"text": text}
        if categories is not None:
            payload["categories"] = categories
        return await self._post("/detect-pii", payload)

    async def extract_structured(
        self,
        text: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /extract-structured — extract JSON matching a user-supplied schema."""
        return await self._post("/extract-structured", {"text": text, "schema": schema})

    async def analyze(
        self,
        text: str,
        prompt: str,
        model: str = "fastino-flash",
    ) -> dict[str, Any]:
        """POST /analyze — open-ended content analysis with an optional model hint."""
        return await self._post(
            "/analyze",
            {"text": text, "prompt": prompt, "model": model},
        )

    # ------------------------------------------------------------------
    # GLiNER2 advanced endpoints
    # ------------------------------------------------------------------

    async def extract_relations(
        self,
        text: str,
        relation_types: list[str],
    ) -> dict[str, Any]:
        """POST /extract-relations — GLiNER2 relation extraction as directional tuples."""
        return await self._post(
            "/extract-relations",
            {"text": text, "relation_types": relation_types},
        )

    async def multi_task(
        self,
        text: str,
        entities: dict[str, str] | None = None,
        classification: dict[str, list[str]] | None = None,
        relations: list[str] | None = None,
        structure: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /multi-task — GLiNER2 combined extraction in a single pass."""
        payload: dict[str, Any] = {"text": text}
        if entities is not None:
            payload["entities"] = entities
        if classification is not None:
            payload["classification"] = classification
        if relations is not None:
            payload["relations"] = relations
        if structure is not None:
            payload["structure"] = structure
        return await self._post("/multi-task", payload)

    # ------------------------------------------------------------------
    # Pioneer personalization endpoints
    # ------------------------------------------------------------------

    async def pioneer_ingest(
        self,
        user_id: str,
        data: list[dict[str, Any]],
        data_type: str = "event",
    ) -> dict[str, Any]:
        """POST /pioneer/ingest — ingest user events/documents into memory graph."""
        return await self._post(
            "/pioneer/ingest",
            {"user_id": user_id, "data": data, "data_type": data_type},
        )

    async def pioneer_retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """POST /pioneer/retrieve — retrieve relevant memory snippets for a user."""
        return await self._post(
            "/pioneer/retrieve",
            {"user_id": user_id, "query": query, "top_k": top_k},
        )

    async def pioneer_summarize(
        self,
        user_id: str,
        focus: str = "",
    ) -> dict[str, Any]:
        """POST /pioneer/summarize — generate deterministic user summary."""
        payload: dict[str, Any] = {"user_id": user_id}
        if focus:
            payload["focus"] = focus
        return await self._post("/pioneer/summarize", payload)

    async def pioneer_query(
        self,
        user_id: str,
        question: str,
    ) -> dict[str, Any]:
        """POST /pioneer/query — ask a natural-language question about user profile."""
        return await self._post(
            "/pioneer/query",
            {"user_id": user_id, "question": question},
        )

    async def pioneer_delete(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """DELETE /pioneer/users — delete a user's personalization data."""
        return await self._post("/pioneer/delete", {"user_id": user_id})


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {}
