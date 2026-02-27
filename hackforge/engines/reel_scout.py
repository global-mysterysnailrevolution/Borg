"""Reel Scout Engine — Instagram Reel Monitor for AI Tool Discovery.

Monitors Instagram profiles and hashtags for AI tool announcements, then
runs a full analysis pipeline on each reel:

  video analysis (Reka vision) → audio transcript (Reka / Modulate)
  → entity extraction (Fastino) → LinkIntel pipeline → structured report
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExtractedEntity(BaseModel):
    """A named entity (tool, API, method) pulled from reel content."""

    name: str
    entity_type: str = "tool"  # "tool" | "method" | "library" | "api"
    context: str = ""  # surrounding sentence for provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReelAnalysis(BaseModel):
    """Full analysis result for a single Instagram reel."""

    url: str
    scout_id: str = ""
    transcript: str = ""
    visual_description: str = ""
    entities: list[ExtractedEntity] = Field(default_factory=list)
    tools_found: list[str] = Field(default_factory=list)
    methods_found: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


class MonitorSession(BaseModel):
    """Tracks the state of an active monitoring session."""

    scout_id: str
    targets: list[str]
    interval_minutes: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True
    discoveries: list[ReelAnalysis] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ReelScoutEngine:
    """Monitors Instagram profiles for AI tool announcements in reels.

    Uses:
    - **Yutori** to scout/browse Instagram profiles and hashtag feeds.
    - **Reka** vision to analyse video frames for on-screen text and visuals.
    - **Reka / Modulate** to transcribe audio from reels.
    - **Fastino** to extract structured tool/method entities from transcripts.
    - **LinkIntelEngine** to deep-research each discovered tool.

    Usage::

        config = HackForgeConfig.load()
        engine = ReelScoutEngine(config)

        # Start a background monitor
        scout_id = await engine.start_monitoring(
            targets=["@someaiinfluencer", "#aigeneration"],
            interval_minutes=30,
        )

        # Later: get what was found
        discoveries = await engine.get_discoveries(scout_id)

        # Analyse a specific reel
        analysis = await engine.analyze_reel("https://www.instagram.com/reel/abc123/")

        # Stop the background monitor
        await engine.stop_monitoring(scout_id)
    """

    def __init__(self, config: HackForgeConfig) -> None:
        self._config = config
        self._sessions: dict[str, MonitorSession] = {}
        self._monitor_tasks: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_monitoring(
        self, targets: list[str], interval_minutes: int = 30
    ) -> str:
        """Start monitoring Instagram targets (profiles / hashtags) via Yutori scout.

        Spawns a background polling loop that calls ``analyze_reel`` on each
        new reel discovered at the given interval.

        Args:
            targets: List of Instagram profile handles (``@handle``) or hashtags
                     (``#tag``) to monitor.
            interval_minutes: How often to poll for new content (default: 30).

        Returns:
            A ``scout_id`` string that can be used to retrieve discoveries or
            stop monitoring.
        """
        scout_id = str(uuid.uuid4())
        session = MonitorSession(
            scout_id=scout_id,
            targets=targets,
            interval_minutes=interval_minutes,
        )
        self._sessions[scout_id] = session

        task = asyncio.create_task(
            self._monitor_loop(scout_id),
            name=f"reel-scout-{scout_id[:8]}",
        )
        self._monitor_tasks[scout_id] = task

        logger.info(
            "ReelScout: started monitoring %d target(s) [scout_id=%s, interval=%dm]",
            len(targets),
            scout_id,
            interval_minutes,
        )
        return scout_id

    async def analyze_reel(self, reel_url: str, scout_id: str = "") -> ReelAnalysis:
        """Analyse a single Instagram reel for AI tool / method content.

        Pipeline:
          1. Use Reka vision to describe video frames.
          2. Use Reka / Modulate to transcribe the audio track.
          3. Use Fastino to extract tool/method entities from the transcript.
          4. Feed discovered tools into the LinkIntel pipeline for enrichment.

        Args:
            reel_url: Full URL of the Instagram reel.
            scout_id: Optional scout session this reel belongs to.

        Returns:
            A :class:`ReelAnalysis` with all discovered content.
        """
        logger.info("ReelScout: analysing reel %s", reel_url)
        analysis = ReelAnalysis(url=reel_url, scout_id=scout_id)

        try:
            # Step 1: Visual analysis via Reka vision
            visual_desc = await self._analyze_video_visuals(reel_url)
            analysis.visual_description = visual_desc

            # Step 2: Audio transcription via Reka multimodal / Modulate
            transcript = await self._transcribe_audio(reel_url)
            analysis.transcript = transcript

            # Combine text sources for entity extraction
            combined_text = f"{visual_desc}\n\n{transcript}".strip()

            # Step 3: Entity extraction via Fastino
            entities = await self._extract_entities(combined_text)
            analysis.entities = entities

            # Classify into tools vs methods
            analysis.tools_found = [
                e.name for e in entities if e.entity_type in ("tool", "api", "library")
            ]
            analysis.methods_found = [
                e.name for e in entities if e.entity_type == "method"
            ]

            # Step 4: Feed into LinkIntel for deep research (fire-and-forget)
            if analysis.tools_found:
                asyncio.create_task(
                    self._enrich_via_link_intel(analysis.tools_found),
                    name=f"link-intel-{reel_url[-20:]}",
                )

        except Exception as exc:
            logger.exception("ReelScout: error analysing %s", reel_url)
            analysis.error = str(exc)

        return analysis

    async def get_discoveries(self, scout_id: str) -> list[ReelAnalysis]:
        """Return all reel analyses collected by a monitoring session.

        Args:
            scout_id: The session identifier returned by :meth:`start_monitoring`.

        Returns:
            List of :class:`ReelAnalysis` objects, newest first.

        Raises:
            KeyError: If ``scout_id`` is unknown.
        """
        if scout_id not in self._sessions:
            raise KeyError(f"Unknown scout_id: {scout_id!r}")
        session = self._sessions[scout_id]
        return sorted(session.discoveries, key=lambda a: a.timestamp, reverse=True)

    async def stop_monitoring(self, scout_id: str) -> None:
        """Stop the background monitoring loop for a session.

        Args:
            scout_id: The session identifier returned by :meth:`start_monitoring`.
        """
        if scout_id not in self._sessions:
            logger.warning("stop_monitoring called for unknown scout_id: %s", scout_id)
            return

        self._sessions[scout_id].active = False
        task = self._monitor_tasks.pop(scout_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info("ReelScout: stopped monitoring [scout_id=%s]", scout_id)

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _monitor_loop(self, scout_id: str) -> None:
        """Background coroutine that polls for new reels at the configured interval.

        Discovers new reel URLs via Yutori and analyses each one, appending
        results to the session's ``discoveries`` list.

        Args:
            scout_id: The session to run the loop for.
        """
        session = self._sessions[scout_id]
        interval_seconds = session.interval_minutes * 60

        while session.active:
            logger.debug("ReelScout: polling for new reels [scout_id=%s]", scout_id)
            try:
                for target in session.targets:
                    reel_urls = await self._discover_reel_urls(target)
                    for url in reel_urls:
                        # Avoid re-analysing already-seen URLs
                        seen = {a.url for a in session.discoveries}
                        if url not in seen:
                            analysis = await self.analyze_reel(url, scout_id=scout_id)
                            session.discoveries.append(analysis)
            except Exception as exc:
                logger.warning(
                    "ReelScout: polling error [scout_id=%s]: %s", scout_id, exc
                )

            await asyncio.sleep(interval_seconds)

    # ------------------------------------------------------------------
    # Yutori scouting
    # ------------------------------------------------------------------

    async def _discover_reel_urls(self, target: str) -> list[str]:
        """Use Yutori to discover recent reel URLs for a profile or hashtag.

        Calls the Yutori browse/scout API to navigate Instagram and extract
        reel links from the feed or explore page.

        Args:
            target: An Instagram handle (``@handle``) or hashtag (``#tag``).

        Returns:
            List of discovered reel URLs (may be empty if none found or
            if Yutori is not configured).
        """
        if not self._config.yutori.api_key:
            logger.debug("Yutori not configured — cannot discover reels for %s", target)
            return []

        # Build the Instagram URL from the target
        if target.startswith("@"):
            instagram_url = f"https://www.instagram.com/{target.lstrip('@')}/"
        elif target.startswith("#"):
            tag = target.lstrip("#")
            instagram_url = f"https://www.instagram.com/explore/tags/{tag}/"
        else:
            instagram_url = target  # assume raw URL

        try:
            async with httpx.AsyncClient(timeout=self._config.yutori.timeout) as client:
                response = await client.post(
                    f"{self._config.yutori.base_url}/browse",
                    headers={
                        "Authorization": f"Bearer {self._config.yutori.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "url": instagram_url,
                        "action": "extract_links",
                        "link_pattern": r"/reel/",
                        "max_links": 20,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                links: list[str] = data.get("links", [])
                logger.debug(
                    "Yutori discovered %d reel links for %s", len(links), target
                )
                return links
        except Exception as exc:
            logger.warning(
                "Yutori discovery failed for %s: %s", target, exc
            )
            return []

    # ------------------------------------------------------------------
    # Reka vision analysis
    # ------------------------------------------------------------------

    async def _analyze_video_visuals(self, reel_url: str) -> str:
        """Use Reka's vision model to analyse the visual content of a reel.

        Sends the reel URL to Reka's multimodal endpoint for frame analysis,
        asking it to describe any on-screen text, tools, or demos visible.

        Args:
            reel_url: URL of the reel to analyse visually.

        Returns:
            A text description of the reel's visual content, or empty string
            on failure.
        """
        if not self._config.reka.api_key:
            logger.debug("Reka not configured — skipping visual analysis")
            return ""

        try:
            async with httpx.AsyncClient(timeout=self._config.reka.timeout) as client:
                response = await client.post(
                    f"{self._config.reka.base_url}/chat",
                    headers={
                        "X-Api-Key": self._config.reka.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "reka-flash",
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "video_url",
                                        "video_url": reel_url,
                                    },
                                    {
                                        "type": "text",
                                        "text": (
                                            "Analyse this video and describe: "
                                            "1) Any AI tools, software, or APIs shown or mentioned on screen. "
                                            "2) Any demos or product walkthroughs. "
                                            "3) Any text overlays, captions, or UI elements. "
                                            "Be specific about product names and versions."
                                        ),
                                    },
                                ],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return (
                    data.get("responses", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
        except Exception as exc:
            logger.warning("Reka visual analysis failed for %s: %s", reel_url, exc)
            return ""

    # ------------------------------------------------------------------
    # Audio transcription
    # ------------------------------------------------------------------

    async def _transcribe_audio(self, reel_url: str) -> str:
        """Transcribe the audio track of a reel using Reka or Modulate.

        Attempts Reka's speech endpoint first; falls back to Modulate's
        transcription API if Reka is unavailable.

        Args:
            reel_url: URL of the reel whose audio should be transcribed.

        Returns:
            Transcript text, or empty string on failure.
        """
        # Try Reka multimodal speech first
        transcript = await self._transcribe_via_reka(reel_url)
        if transcript:
            return transcript

        # Fallback: Modulate transcription
        return await self._transcribe_via_modulate(reel_url)

    async def _transcribe_via_reka(self, reel_url: str) -> str:
        """Attempt transcription using Reka's multimodal audio capability.

        Args:
            reel_url: Reel URL to transcribe.

        Returns:
            Transcript string, or empty string on failure.
        """
        if not self._config.reka.api_key:
            return ""

        try:
            async with httpx.AsyncClient(timeout=self._config.reka.timeout) as client:
                response = await client.post(
                    f"{self._config.reka.base_url}/chat",
                    headers={
                        "X-Api-Key": self._config.reka.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "reka-flash",
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "video_url",
                                        "video_url": reel_url,
                                    },
                                    {
                                        "type": "text",
                                        "text": (
                                            "Transcribe the spoken words in this video verbatim. "
                                            "Return ONLY the transcript text, no commentary."
                                        ),
                                    },
                                ],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return (
                    data.get("responses", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
        except Exception as exc:
            logger.debug("Reka audio transcription failed: %s", exc)
            return ""

    async def _transcribe_via_modulate(self, reel_url: str) -> str:
        """Attempt transcription using the Modulate audio API.

        Args:
            reel_url: Reel URL to transcribe.

        Returns:
            Transcript string, or empty string on failure.
        """
        if not self._config.modulate.api_key:
            logger.debug("Modulate not configured — skipping audio transcription")
            return ""

        try:
            async with httpx.AsyncClient(timeout=self._config.modulate.timeout) as client:
                response = await client.post(
                    f"{self._config.modulate.base_url}/transcribe",
                    headers={
                        "Authorization": f"Bearer {self._config.modulate.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "media_url": reel_url,
                        "language": "en",
                        "format": "text",
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return data.get("transcript", "")
        except Exception as exc:
            logger.warning("Modulate transcription failed for %s: %s", reel_url, exc)
            return ""

    # ------------------------------------------------------------------
    # Entity extraction via Fastino
    # ------------------------------------------------------------------

    async def _extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Extract tool and method entities from combined reel text using Fastino.

        Args:
            text: Combined visual description and audio transcript.

        Returns:
            List of :class:`ExtractedEntity` objects.
        """
        if not text.strip():
            return []

        if not self._config.fastino.api_key:
            logger.debug("Fastino not configured — skipping entity extraction")
            return []

        chunk = text[:8000]
        prompt = (
            "You are extracting AI tools, APIs, and techniques from social media content.\n\n"
            "Extract all named AI tools, software products, APIs, libraries, and methods "
            "from the following text. Return ONLY a JSON array, each element having:\n"
            '  "name": string (canonical product/method name),\n'
            '  "entity_type": one of "tool"|"api"|"library"|"method",\n'
            '  "context": the sentence or phrase where it appears,\n'
            '  "confidence": float 0-1\n\n'
            f"TEXT:\n{chunk}\n\nJSON:"
        )

        try:
            async with httpx.AsyncClient(timeout=self._config.fastino.timeout) as client:
                response = await client.post(
                    f"{self._config.fastino.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._config.fastino.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "fastino-extract",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                import json
                raw_json: str = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "[]")
                )
                items: list[dict[str, Any]] = json.loads(raw_json)
                return [ExtractedEntity(**item) for item in items if "name" in item]
        except Exception as exc:
            logger.warning("Fastino entity extraction failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # LinkIntel enrichment
    # ------------------------------------------------------------------

    async def _enrich_via_link_intel(self, tool_names: list[str]) -> None:
        """Feed discovered tool names into LinkIntelEngine for deep research.

        This is called as a fire-and-forget task; errors are logged but do not
        propagate to the caller.

        Args:
            tool_names: Names of tools to research via LinkIntel.
        """
        try:
            from hackforge.engines.link_intel import LinkIntelEngine

            engine = LinkIntelEngine(self._config)
            for name in tool_names:
                try:
                    # Use a synthetic search URL to drive LinkIntel
                    synthetic_url = (
                        f"https://www.google.com/search?q={name.replace(' ', '+')}+API"
                    )
                    await engine.analyze_url(synthetic_url)
                    logger.debug("LinkIntel enrichment complete for %s", name)
                except Exception as exc:
                    logger.warning("LinkIntel enrichment failed for %s: %s", name, exc)
        except Exception as exc:
            logger.warning("Could not import LinkIntelEngine for enrichment: %s", exc)
