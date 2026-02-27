"""Async client for the Senso AI knowledge-base API.

Senso provides a managed vector knowledge base: ingest documents, run
semantic search, evaluate content relevance, and retrieve per-tool
documentation collections.

Reference: https://docs.senso.ai
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SensoError(Exception):
    """Base error for all Senso client failures."""


class SensoAuthError(SensoError):
    """Raised when the Bearer token is rejected (HTTP 401)."""


class SensoRateLimitError(SensoError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class SensoAPIError(SensoError):
    """Raised for any other non-2xx Senso API response."""


class SensoNotFoundError(SensoError):
    """Raised when a requested resource does not exist (HTTP 404)."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    """Result from ``ingest_document``."""

    document_id: str
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeChunk:
    """A single chunk returned by ``search_knowledge``."""

    title: str
    content: str
    score: float = 0.0
    document_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Result from ``search_knowledge``."""

    query: str
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Result from ``evaluate_content``."""

    score: float
    relevant: bool
    reasoning: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDocsResult:
    """Result from ``get_tool_docs``."""

    tool_name: str
    documents: list[KnowledgeChunk] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SensoClient:
    """Async HTTP client for the Senso AI knowledge-base API.

    Usage::

        cfg = ProviderConfig(api_key="snso-...", base_url="https://api.senso.ai/v1")
        async with SensoClient(cfg) as client:
            await client.ingest_document(
                title="LangChain Overview",
                content="LangChain is a framework for building LLM apps...",
                metadata={"source": "langchain.com", "tool": "LangChain"},
            )
            results = await client.search_knowledge("LLM orchestration frameworks")
            for chunk in results.chunks:
                print(chunk.title, chunk.score)
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> SensoClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url or "https://api.senso.ai/v1",
                timeout=self._config.timeout,
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
            )

    async def close(self) -> None:
        """Cleanly close the underlying HTTP connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request and return the parsed JSON body."""
        await self._ensure_client()
        assert self._client is not None

        try:
            response = await self._client.request(
                method,
                endpoint,
                json=payload,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise SensoAPIError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise SensoAPIError(f"Network error: {exc}") from exc

        if response.status_code == 401:
            raise SensoAuthError("Invalid or missing Senso API key.")
        if response.status_code == 404:
            raise SensoNotFoundError(f"Resource not found: {endpoint}")
        if response.status_code == 429:
            raise SensoRateLimitError("Senso rate limit exceeded.")
        if response.status_code >= 400:
            raise SensoAPIError(
                f"Senso API error {response.status_code}: {response.text}"
            )

        return response.json()

    @staticmethod
    def _parse_chunk(raw: dict[str, Any]) -> KnowledgeChunk:
        return KnowledgeChunk(
            title=raw.get("title", raw.get("name", "")),
            content=raw.get("content", raw.get("text", "")),
            score=float(raw.get("score", raw.get("relevance", 0.0))),
            document_id=raw.get("document_id", raw.get("id", "")),
            metadata=raw.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult:
        """Add a document to the Senso knowledge base.

        The document will be chunked, embedded, and indexed automatically.
        Subsequent ``search_knowledge`` calls can retrieve it semantically.

        Args:
            title: Human-readable title for the document.
            content: Full text content of the document.
            metadata: Optional key-value metadata attached to the document
                (e.g. ``{"source": "url", "tool": "LangChain", "type": "docs"}``).

        Returns:
            An :class:`IngestResult` containing the assigned ``document_id``
            and ingestion ``status``.
        """
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "metadata": metadata or {},
        }
        data = await self._request("POST", "/documents", payload=payload)
        return IngestResult(
            document_id=data.get("document_id", data.get("id", "")),
            status=data.get("status", "ingested"),
            raw=data,
        )

    async def search_knowledge(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict[str, Any] | None = None,
    ) -> SearchResult:
        """Perform a semantic search over the knowledge base.

        Args:
            query: Natural-language search query.
            top_k: Number of chunks to return.
            metadata_filter: Optional key-value filter applied on document
                metadata before ranking (e.g. ``{"tool": "LangChain"}``).

        Returns:
            A :class:`SearchResult` with up to *top_k* :class:`KnowledgeChunk`
            objects ranked by relevance.
        """
        payload: dict[str, Any] = {
            "query": query,
            "top_k": top_k,
        }
        if metadata_filter:
            payload["filter"] = metadata_filter

        data = await self._request("POST", "/search", payload=payload)
        raw_chunks: list[dict[str, Any]] = data.get(
            "chunks", data.get("results", data.get("hits", []))
        )
        return SearchResult(
            query=query,
            chunks=[self._parse_chunk(c) for c in raw_chunks],
            raw=data,
        )

    async def evaluate_content(
        self,
        content: str,
        context: str,
        threshold: float = 0.5,
    ) -> EvaluationResult:
        """Evaluate how relevant *content* is to a given *context*.

        This endpoint uses the Senso relevance model to score whether a
        piece of text is useful given a user query or situational context.

        Args:
            content: The text to evaluate.
            context: The reference context or query against which to score.
            threshold: Relevance score above which ``relevant`` is set to
                ``True`` (default 0.5).

        Returns:
            An :class:`EvaluationResult` with a normalised ``score`` (0–1),
            a ``relevant`` boolean, and optional ``reasoning`` text.
        """
        payload: dict[str, Any] = {
            "content": content,
            "context": context,
        }
        data = await self._request("POST", "/evaluate", payload=payload)
        score = float(data.get("score", data.get("relevance", 0.0)))
        return EvaluationResult(
            score=score,
            relevant=score >= threshold,
            reasoning=data.get("reasoning", data.get("explanation", "")),
            raw=data,
        )

    async def get_tool_docs(
        self,
        tool_name: str,
        top_k: int = 20,
    ) -> ToolDocsResult:
        """Retrieve documentation chunks for a specific tool from the knowledge base.

        Convenience wrapper around ``search_knowledge`` that applies a metadata
        filter for the given tool name and returns a typed result.

        Args:
            tool_name: Canonical name of the tool (must match the ``tool``
                metadata field set during ingestion).
            top_k: Maximum number of documentation chunks to return.

        Returns:
            A :class:`ToolDocsResult` with the matching documentation chunks.
        """
        result = await self.search_knowledge(
            query=f"{tool_name} documentation API usage examples",
            top_k=top_k,
            metadata_filter={"tool": tool_name},
        )
        return ToolDocsResult(
            tool_name=tool_name,
            documents=result.chunks,
            raw=result.raw,
        )
