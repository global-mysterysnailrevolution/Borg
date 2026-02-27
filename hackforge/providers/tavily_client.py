"""Async client for the Tavily Search API.

Tavily provides AI-optimised web search with deep content extraction.
Reference: https://docs.tavily.com/docs/tavily-api/rest_api
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TavilyError(Exception):
    """Base error for all Tavily client failures."""


class TavilyAuthError(TavilyError):
    """Raised when the API key is rejected."""


class TavilyRateLimitError(TavilyError):
    """Raised when the rate limit is exceeded."""


class TavilySearchError(TavilyError):
    """Raised when a search request fails."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class TavilyResult:
    """A single search result returned by Tavily."""

    title: str
    url: str
    content: str
    score: float = 0.0
    raw_content: str | None = None


@dataclass
class TavilySearchResponse:
    """Full response from a Tavily search call."""

    query: str
    answer: str | None
    results: list[TavilyResult] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    response_time: float = 0.0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TavilyClient:
    """Async HTTP client that wraps the Tavily Search REST API.

    Usage::

        cfg = ProviderConfig(api_key="tvly-...", base_url="https://api.tavily.com")
        async with TavilyClient(cfg) as client:
            resp = await client.search("best AI coding tools 2024")
            print(resp.answer)
    """

    _SEARCH_ENDPOINT = "/search"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> TavilyClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url or "https://api.tavily.com",
                timeout=self._config.timeout,
                headers={"Content-Type": "application/json"},
            )

    async def close(self) -> None:
        """Cleanly close the underlying HTTP connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request and return the parsed JSON body."""
        await self._ensure_client()
        assert self._client is not None  # for type-checkers

        try:
            response = await self._client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise TavilySearchError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise TavilySearchError(f"Network error: {exc}") from exc

        if response.status_code == 401:
            raise TavilyAuthError("Invalid or missing Tavily API key.")
        if response.status_code == 429:
            raise TavilyRateLimitError("Tavily rate limit exceeded.")
        if response.status_code >= 400:
            raise TavilySearchError(
                f"Tavily API error {response.status_code}: {response.text}"
            )

        return response.json()

    def _parse_response(self, query: str, data: dict[str, Any]) -> TavilySearchResponse:
        """Convert the raw API response dict into a TavilySearchResponse."""
        raw_results: list[dict[str, Any]] = data.get("results", [])
        results = [
            TavilyResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
                raw_content=r.get("raw_content"),
            )
            for r in raw_results
        ]
        return TavilySearchResponse(
            query=query,
            answer=data.get("answer"),
            results=results,
            follow_up_questions=data.get("follow_up_questions", []),
            response_time=float(data.get("response_time", 0.0)),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "advanced",
        include_raw_content: bool = False,
    ) -> TavilySearchResponse:
        """Run a Tavily web search.

        Args:
            query: Natural-language search query.
            max_results: Number of results to return (1–20).
            search_depth: ``"basic"`` for fast results, ``"advanced"`` for deep
                extraction (default).
            include_raw_content: Whether to include the raw HTML/markdown content
                alongside the summarised ``content`` field.

        Returns:
            A :class:`TavilySearchResponse` with an AI-synthesised ``answer``
            and individual ``results``.
        """
        payload: dict[str, Any] = {
            "api_key": self._config.api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": True,
            "include_raw_content": include_raw_content,
            "max_results": max(1, min(max_results, 20)),
        }
        data = await self._post(self._SEARCH_ENDPOINT, payload)
        return self._parse_response(query, data)

    async def search_for_vendors(self, url: str) -> TavilySearchResponse:
        """Search for information about a vendor given its website URL.

        Constructs a rich query designed to surface pricing pages, API docs,
        integration details, and competitive context for the vendor at *url*.

        Args:
            url: The vendor's primary website URL (e.g. ``"https://example.com"``).

        Returns:
            A :class:`TavilySearchResponse` focused on vendor intelligence.
        """
        query = (
            f"site:{url} OR \"{url}\" "
            "API pricing documentation integrations features review"
        )
        return await self.search(query, max_results=10, search_depth="advanced")

    async def find_api_docs(self, tool_name: str) -> TavilySearchResponse:
        """Search for official API documentation for a named tool or service.

        Args:
            tool_name: The name of the tool, SDK, or service to look up
                (e.g. ``"Stripe"`` or ``"LangChain"``).

        Returns:
            A :class:`TavilySearchResponse` whose results point to documentation
            pages, quickstart guides, and SDK references.
        """
        query = (
            f"{tool_name} official API documentation "
            "quickstart reference guide SDK examples"
        )
        return await self.search(query, max_results=10, search_depth="advanced")
