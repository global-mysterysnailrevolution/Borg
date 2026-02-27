"""Async client for the Modulate ToxMod voice-moderation API.

Modulate ToxMod analyses audio content for toxicity, hate speech, and other
harmful behaviour in voice communications.  When Modulate cannot produce a
transcript (e.g. the endpoint is unavailable), this client falls back to
Reka AI's multimodal audio-understanding capability.

Reference: https://modulate.ai/docs
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ModulateError(Exception):
    """Base error for all Modulate client failures."""


class ModulateAuthError(ModulateError):
    """Raised when the API key is rejected (HTTP 401/403)."""


class ModulateRateLimitError(ModulateError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class ModulateAPIError(ModulateError):
    """Raised for any other non-2xx Modulate API response."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ToxicityFlag:
    """A single toxicity signal detected in the audio."""

    category: str          # e.g. "hate_speech", "harassment", "profanity"
    confidence: float      # 0.0 – 1.0
    timestamp_start: float = 0.0   # seconds from start of audio
    timestamp_end: float = 0.0
    severity: str = "low"  # "low" | "medium" | "high"


@dataclass
class AudioAnalysisResult:
    """Result from ``analyze_audio`` or ``analyze_voice_segment``."""

    audio_url: str
    flagged: bool
    overall_score: float           # 0.0 = clean, 1.0 = extremely toxic
    flags: list[ToxicityFlag] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptResult:
    """Result from ``get_transcript``."""

    audio_url: str
    transcript: str
    source: str = "modulate"       # "modulate" or "reka_fallback"
    confidence: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ModulateClient:
    """Async HTTP client for the Modulate ToxMod voice-moderation API.

    Provides toxicity analysis for remote audio URLs and raw audio segments.
    Transcription falls back to Reka AI when the Modulate transcription
    endpoint is unavailable or unconfigured.

    Usage::

        cfg = ProviderConfig(
            api_key="mod-...",
            base_url="https://api.modulate.ai/v1",
        )
        async with ModulateClient(cfg) as client:
            result = await client.analyze_audio("https://cdn.example.com/clip.mp3")
            if result.flagged:
                print(f"Toxicity detected: score={result.overall_score:.2f}")
                for flag in result.flags:
                    print(f"  {flag.category} ({flag.severity}): {flag.confidence:.2%}")
    """

    def __init__(
        self,
        config: ProviderConfig,
        reka_config: ProviderConfig | None = None,
    ) -> None:
        """Initialise the Modulate client.

        Args:
            config: Modulate provider configuration (API key, base URL, timeout).
            reka_config: Optional Reka AI provider config used as a transcription
                fallback.  When provided and the Modulate transcript endpoint fails,
                the client will call Reka's audio-understanding model instead.
        """
        self._config = config
        self._reka_config = reka_config
        self._client: httpx.AsyncClient | None = None
        self._reka_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ModulateClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url or "https://api.modulate.ai/v1",
                timeout=self._config.timeout,
                headers={
                    "X-API-Key": self._config.api_key,
                    "Content-Type": "application/json",
                },
            )

    async def _ensure_reka_client(self) -> bool:
        """Lazily initialise the Reka fallback client.  Returns True if available."""
        if self._reka_config is None or not self._reka_config.api_key:
            return False
        if self._reka_client is None:
            self._reka_client = httpx.AsyncClient(
                base_url=self._reka_config.base_url or "https://api.reka.ai/v2",
                timeout=self._reka_config.timeout,
                headers={
                    "Authorization": f"Bearer {self._reka_config.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return True

    async def close(self) -> None:
        """Cleanly close all HTTP connection pools."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._reka_client is not None:
            await self._reka_client.aclose()
            self._reka_client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request to Modulate and return the parsed JSON body."""
        await self._ensure_client()
        assert self._client is not None

        try:
            response = await self._client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise ModulateAPIError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ModulateAPIError(f"Network error: {exc}") from exc

        if response.status_code in (401, 403):
            raise ModulateAuthError(
                f"Modulate authentication failed (HTTP {response.status_code})."
            )
        if response.status_code == 429:
            raise ModulateRateLimitError("Modulate rate limit exceeded.")
        if response.status_code >= 400:
            raise ModulateAPIError(
                f"Modulate API error {response.status_code}: {response.text}"
            )

        return response.json()

    @staticmethod
    def _parse_flags(raw_flags: list[dict[str, Any]]) -> list[ToxicityFlag]:
        flags: list[ToxicityFlag] = []
        for f in raw_flags:
            flags.append(
                ToxicityFlag(
                    category=f.get("category", f.get("type", "unknown")),
                    confidence=float(f.get("confidence", f.get("score", 0.0))),
                    timestamp_start=float(f.get("timestamp_start", f.get("start", 0.0))),
                    timestamp_end=float(f.get("timestamp_end", f.get("end", 0.0))),
                    severity=f.get("severity", "low"),
                )
            )
        return flags

    def _parse_analysis(self, audio_url: str, data: dict[str, Any]) -> AudioAnalysisResult:
        raw_flags: list[dict[str, Any]] = data.get(
            "flags", data.get("toxicity_flags", data.get("detections", []))
        )
        flags = self._parse_flags(raw_flags)
        overall_score = float(
            data.get("overall_score", data.get("toxicity_score", data.get("score", 0.0)))
        )
        return AudioAnalysisResult(
            audio_url=audio_url,
            flagged=bool(data.get("flagged", data.get("is_toxic", len(flags) > 0))),
            overall_score=overall_score,
            flags=flags,
            metadata=data.get("metadata", {}),
            raw=data,
        )

    # ------------------------------------------------------------------
    # Reka fallback helpers
    # ------------------------------------------------------------------

    async def _reka_transcribe(self, audio_url: str) -> TranscriptResult:
        """Use Reka AI to transcribe *audio_url* when Modulate is unavailable."""
        reka_available = await self._ensure_reka_client()
        if not reka_available:
            raise ModulateAPIError(
                "Transcription failed: Modulate transcription endpoint is unavailable "
                "and no Reka fallback config was supplied."
            )
        assert self._reka_client is not None

        # Reka's multimodal API supports audio URLs via the video_url content type.
        payload: dict[str, Any] = {
            "model": "reka-core",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": audio_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Please transcribe this audio exactly as spoken. "
                                "Output only the transcript text, no commentary."
                            ),
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.0,
        }
        try:
            response = await self._reka_client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise ModulateAPIError(
                f"Reka transcription fallback failed: {exc}"
            ) from exc

        transcript_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return TranscriptResult(
            audio_url=audio_url,
            transcript=transcript_text,
            source="reka_fallback",
            confidence=0.0,  # Reka does not provide a confidence score here
            raw=data,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_audio(self, audio_url: str) -> AudioAnalysisResult:
        """Submit a remote audio file for toxicity analysis.

        The audio at *audio_url* must be publicly accessible (or pre-signed).
        Modulate will download, process, and return toxicity signals.

        Args:
            audio_url: Publicly accessible URL of the audio file
                (MP3, WAV, OGG, FLAC, M4A supported).

        Returns:
            An :class:`AudioAnalysisResult` with an ``overall_score``,
            ``flagged`` status, and individual :class:`ToxicityFlag` objects.
        """
        payload: dict[str, Any] = {"audio_url": audio_url}
        data = await self._post("/analyze", payload)
        return self._parse_analysis(audio_url, data)

    async def analyze_voice_segment(
        self,
        audio_data: bytes,
        content_type: str = "audio/wav",
    ) -> AudioAnalysisResult:
        """Submit raw audio bytes for toxicity analysis.

        The audio is base64-encoded and sent inline.  Use this when the audio
        is not accessible via a public URL (e.g. live stream segments).

        Args:
            audio_data: Raw audio bytes.
            content_type: MIME type of the audio (default ``"audio/wav"``).

        Returns:
            An :class:`AudioAnalysisResult` with toxicity signals.
        """
        encoded = base64.b64encode(audio_data).decode("ascii")
        payload: dict[str, Any] = {
            "audio_data": encoded,
            "content_type": content_type,
        }
        data = await self._post("/analyze", payload)
        # Use a synthetic URL for result labelling since there is no real URL.
        return self._parse_analysis("data://inline-audio", data)

    async def get_transcript(
        self,
        audio_url: str,
        use_reka_fallback: bool = True,
    ) -> TranscriptResult:
        """Retrieve a speech-to-text transcript for *audio_url*.

        Attempts the Modulate ``/transcript`` endpoint first.  If that call
        fails (e.g. the feature is not available on the current plan) and
        *use_reka_fallback* is ``True``, this method transparently retries
        using Reka AI's audio understanding model.

        Args:
            audio_url: Publicly accessible URL of the audio file.
            use_reka_fallback: Whether to attempt Reka transcription when
                Modulate is unable to produce a transcript (default ``True``).

        Returns:
            A :class:`TranscriptResult` with ``transcript`` text and
            ``source`` indicating which backend produced it.
        """
        try:
            payload: dict[str, Any] = {"audio_url": audio_url}
            data = await self._post("/transcript", payload)
            segments: list[dict[str, Any]] = data.get("segments", [])
            # Reconstruct full transcript from segments if not supplied directly.
            transcript_text: str = data.get(
                "transcript",
                " ".join(s.get("text", "") for s in segments),
            )
            return TranscriptResult(
                audio_url=audio_url,
                transcript=transcript_text,
                source="modulate",
                confidence=float(data.get("confidence", 0.0)),
                segments=segments,
                raw=data,
            )
        except ModulateAPIError:
            if use_reka_fallback:
                return await self._reka_transcribe(audio_url)
            raise
