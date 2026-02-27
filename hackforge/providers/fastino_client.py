"""Async client for the Fastino TLM (Text-Language Model) API.

Fastino provides lightweight, low-latency NLP endpoints for entity extraction,
text classification, PII detection, structured data extraction, and general
text analysis — without the cost of a full generative LLM call.

Reference: https://docs.fastino.ai
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FastinoError(Exception):
    """Base error for all Fastino client failures."""


class FastinoAuthError(FastinoError):
    """Raised when the Bearer token is rejected (HTTP 401)."""


class FastinoRateLimitError(FastinoError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class FastinoAPIError(FastinoError):
    """Raised for any other non-2xx Fastino API response."""


# ---------------------------------------------------------------------------
# Default entity types
# ---------------------------------------------------------------------------

DEFAULT_ENTITY_TYPES: list[str] = [
    "TOOL",
    "COMPANY",
    "API",
    "FRAMEWORK",
    "LANGUAGE",
    "PERSON",
]

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    """A single extracted named entity."""

    text: str
    entity_type: str
    start: int = 0
    end: int = 0
    confidence: float = 0.0


@dataclass
class ExtractionResult:
    """Result from ``extract_entities``."""

    entities: list[Entity] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Result from ``classify_text``."""

    label: str
    confidence: float
    all_scores: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PIIResult:
    """Result from ``detect_pii``."""

    has_pii: bool
    pii_entities: list[Entity] = field(default_factory=list)
    redacted_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredResult:
    """Result from ``extract_structured``."""

    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Result from ``analyze``."""

    result: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FastinoClient:
    """Async HTTP client for the Fastino TLM API.

    Provides fast, structured NLP operations: entity extraction, text
    classification, PII detection, schema-driven data extraction, and
    free-form analysis.

    Usage::

        cfg = ProviderConfig(api_key="fst-...", base_url="https://api.fastino.ai/v1")
        async with FastinoClient(cfg) as client:
            result = await client.extract_entities(
                "LangChain is a Python framework built by Harrison Chase.",
                entity_types=["TOOL", "PERSON", "LANGUAGE"],
            )
            for entity in result.entities:
                print(entity.text, entity.entity_type)
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> FastinoClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url or "https://api.fastino.ai/v1",
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

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request and return the parsed JSON body."""
        await self._ensure_client()
        assert self._client is not None

        try:
            response = await self._client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise FastinoAPIError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise FastinoAPIError(f"Network error: {exc}") from exc

        if response.status_code == 401:
            raise FastinoAuthError("Invalid or missing Fastino API key.")
        if response.status_code == 429:
            raise FastinoRateLimitError("Fastino rate limit exceeded.")
        if response.status_code >= 400:
            raise FastinoAPIError(
                f"Fastino API error {response.status_code}: {response.text}"
            )

        return response.json()

    @staticmethod
    def _parse_entity(raw: dict[str, Any]) -> Entity:
        return Entity(
            text=raw.get("text", ""),
            entity_type=raw.get("type", raw.get("entity_type", "")),
            start=int(raw.get("start", 0)),
            end=int(raw.get("end", 0)),
            confidence=float(raw.get("confidence", raw.get("score", 0.0))),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_entities(
        self,
        text: str,
        entity_types: list[str] | None = None,
    ) -> ExtractionResult:
        """Extract named entities from *text*.

        Args:
            text: The input text to process.
            entity_types: The entity categories to extract.  Defaults to
                ``["TOOL", "COMPANY", "API", "FRAMEWORK", "LANGUAGE", "PERSON"]``.

        Returns:
            An :class:`ExtractionResult` with a list of :class:`Entity` objects.
        """
        payload: dict[str, Any] = {
            "text": text,
            "entity_types": entity_types or DEFAULT_ENTITY_TYPES,
        }
        data = await self._post("/extract", payload)
        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        return ExtractionResult(
            entities=[self._parse_entity(e) for e in raw_entities],
            raw=data,
        )

    async def classify_text(
        self,
        text: str,
        labels: list[str],
        multi_label: bool = False,
    ) -> ClassificationResult:
        """Classify *text* into one of the provided *labels*.

        Args:
            text: The text to classify.
            labels: Candidate class labels.
            multi_label: If ``True``, the model may assign multiple labels.

        Returns:
            A :class:`ClassificationResult` with the top ``label`` and its
            ``confidence``, plus scores for all candidates.
        """
        payload: dict[str, Any] = {
            "text": text,
            "labels": labels,
            "multi_label": multi_label,
        }
        data = await self._post("/classify", payload)
        all_scores: dict[str, float] = {
            item["label"]: float(item.get("score", 0.0))
            for item in data.get("scores", [])
        }
        top_label: str = data.get("label", labels[0] if labels else "")
        top_confidence: float = float(data.get("confidence", data.get("score", 0.0)))
        return ClassificationResult(
            label=top_label,
            confidence=top_confidence,
            all_scores=all_scores,
            raw=data,
        )

    async def detect_pii(
        self,
        text: str,
        redact: bool = False,
    ) -> PIIResult:
        """Detect personally identifiable information in *text*.

        Args:
            text: The input text to scan.
            redact: If ``True``, request a redacted copy of the text with PII
                replaced by ``[REDACTED]`` placeholders.

        Returns:
            A :class:`PIIResult` indicating whether PII was found and listing
            each detected PII :class:`Entity`.
        """
        payload: dict[str, Any] = {"text": text, "redact": redact}
        data = await self._post("/detect-pii", payload)
        raw_entities: list[dict[str, Any]] = data.get("pii_entities", data.get("entities", []))
        pii_entities = [self._parse_entity(e) for e in raw_entities]
        return PIIResult(
            has_pii=bool(data.get("has_pii", len(pii_entities) > 0)),
            pii_entities=pii_entities,
            redacted_text=data.get("redacted_text"),
            raw=data,
        )

    async def extract_structured(
        self,
        text: str,
        schema: dict[str, Any],
    ) -> StructuredResult:
        """Extract structured data from *text* conforming to *schema*.

        The schema should be a JSON-Schema-compatible dict describing the
        expected output shape.  The API will attempt to fill each field
        from the natural-language input.

        Args:
            text: The source text to extract from.
            schema: A JSON-Schema dict defining the desired output structure.

        Returns:
            A :class:`StructuredResult` whose ``data`` dict mirrors the schema.
        """
        payload: dict[str, Any] = {"text": text, "schema": schema}
        data = await self._post("/extract", payload)
        return StructuredResult(
            data=data.get("data", data.get("result", {})),
            raw=data,
        )

    async def analyze(
        self,
        text: str,
        prompt: str,
    ) -> AnalysisResult:
        """Run a free-form analysis query against *text*.

        Use this when the other methods are too rigid.  Supply a
        natural-language *prompt* instructing the TLM what to extract or
        infer from *text*.

        Args:
            text: The document or snippet to analyse.
            prompt: Instruction describing what analysis to perform.

        Returns:
            An :class:`AnalysisResult` with the model's textual response.
        """
        payload: dict[str, Any] = {"text": text, "prompt": prompt}
        data = await self._post("/analyze", payload)
        return AnalysisResult(
            result=data.get("result", data.get("output", str(data))),
            raw=data,
        )
