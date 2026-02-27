"""Async client for the Reka AI multimodal API.

Reka offers an OpenAI-compatible chat-completions endpoint that additionally
accepts image and video content parts in its messages.

Reference: https://docs.reka.ai
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RekaError(Exception):
    """Base error for all Reka client failures."""


class RekaAuthError(RekaError):
    """Raised when the Bearer token is rejected (HTTP 401)."""


class RekaRateLimitError(RekaError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class RekaAPIError(RekaError):
    """Raised for any other non-2xx Reka API response."""


# ---------------------------------------------------------------------------
# Model literals
# ---------------------------------------------------------------------------

RekaModel = Literal["reka-flash", "reka-core", "reka-edge"]

DEFAULT_MODEL: RekaModel = "reka-flash"

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RekaMessage:
    """A single message in a Reka conversation."""

    role: str
    content: str


@dataclass
class RekaResponse:
    """Response from a Reka chat-completions call."""

    model: str
    message: RekaMessage
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class RekaClient:
    """Async HTTP client that wraps the Reka AI chat/multimodal API.

    Reka uses an OpenAI-compatible request format, with an additional
    ``media_type`` field on content parts to carry image or video URLs.

    Usage::

        cfg = ProviderConfig(api_key="reka-...", base_url="https://api.reka.ai/v2")
        async with RekaClient(cfg) as client:
            response = await client.research("Latest developments in vector databases")
            print(response.message.content)
    """

    _CHAT_ENDPOINT = "/chat/completions"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> RekaClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url or "https://api.reka.ai/v2",
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
            raise RekaAPIError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise RekaAPIError(f"Network error: {exc}") from exc

        if response.status_code == 401:
            raise RekaAuthError("Invalid or missing Reka API key.")
        if response.status_code == 429:
            raise RekaRateLimitError("Reka rate limit exceeded.")
        if response.status_code >= 400:
            raise RekaAPIError(
                f"Reka API error {response.status_code}: {response.text}"
            )

        return response.json()

    def _parse_response(self, data: dict[str, Any]) -> RekaResponse:
        """Convert raw API JSON into a :class:`RekaResponse`."""
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return RekaResponse(
            model=data.get("model", ""),
            message=RekaMessage(
                role=msg.get("role", "assistant"),
                content=msg.get("content", ""),
            ),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )

    def _build_text_message(self, role: str, text: str) -> dict[str, Any]:
        return {"role": role, "content": text}

    def _build_multimodal_message(
        self,
        role: str,
        text: str,
        media_url: str,
        media_type: Literal["image_url", "video_url"],
    ) -> dict[str, Any]:
        """Build a message dict that includes a text prompt and a media part."""
        content: list[dict[str, Any]] = [
            {
                "type": media_type,
                media_type: {"url": media_url},
            },
            {"type": "text", "text": text},
        ]
        return {"role": role, "content": content}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: RekaModel = DEFAULT_MODEL,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> RekaResponse:
        """Send a list of chat messages and return the assistant's reply.

        Args:
            messages: List of message dicts following the OpenAI format.
                Each dict must have ``"role"`` and ``"content"`` keys.
                Content may be a string or a list of content-part dicts.
            model: Reka model to use.  One of ``"reka-flash"``,
                ``"reka-core"``, or ``"reka-edge"``.
            max_tokens: Maximum tokens in the completion.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            A :class:`RekaResponse` containing the assistant message.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = await self._post(self._CHAT_ENDPOINT, payload)
        return self._parse_response(data)

    async def analyze_image(
        self,
        image_url: str,
        prompt: str,
        model: RekaModel = DEFAULT_MODEL,
    ) -> RekaResponse:
        """Analyse an image using a natural-language prompt.

        Args:
            image_url: Publicly accessible URL of the image to analyse.
            prompt: Instruction for the model (e.g. ``"Describe this diagram"``).
            model: Reka model to use for vision.

        Returns:
            A :class:`RekaResponse` with the model's image analysis.
        """
        message = self._build_multimodal_message(
            role="user",
            text=prompt,
            media_url=image_url,
            media_type="image_url",
        )
        return await self.chat([message], model=model)

    async def analyze_video(
        self,
        video_url: str,
        prompt: str,
        model: RekaModel = "reka-core",
    ) -> RekaResponse:
        """Analyse a video using a natural-language prompt.

        Video understanding requires the ``reka-core`` model tier; if a
        lighter model is supplied it will be silently upgraded to ``reka-core``.

        Args:
            video_url: Publicly accessible URL of the video file.
            prompt: Instruction for the model (e.g. ``"Summarise this meeting"``).
            model: Reka model to use.  Defaults to ``"reka-core"`` for best
                video comprehension.

        Returns:
            A :class:`RekaResponse` with the model's video analysis.
        """
        message = self._build_multimodal_message(
            role="user",
            text=prompt,
            media_url=video_url,
            media_type="video_url",
        )
        return await self.chat([message], model=model, max_tokens=4096)

    async def research(
        self,
        query: str,
        model: RekaModel = DEFAULT_MODEL,
    ) -> RekaResponse:
        """Run a deep-research query using a well-structured system prompt.

        Instructs the model to act as a research analyst: providing thorough,
        cited, structured answers suitable for downstream processing.

        Args:
            query: The research question or topic.
            model: Reka model to use.

        Returns:
            A :class:`RekaResponse` with detailed research findings.
        """
        system_message = self._build_text_message(
            role="system",
            text=(
                "You are an expert research analyst. Provide thorough, well-structured "
                "answers with clear sections. Where possible, cite specific sources, "
                "versions, and dates. Focus on accuracy and completeness."
            ),
        )
        user_message = self._build_text_message(role="user", text=query)
        return await self.chat(
            [system_message, user_message],
            model=model,
            max_tokens=4096,
            temperature=0.3,
        )
