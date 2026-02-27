"""Video Intelligence Engine — Analyze YouTube videos and reels for AI tool discovery.

Takes a YouTube URL, extracts visual + audio content via Reka AI, runs entity
extraction via Fastino, and feeds discoveries into the LinkIntel pipeline.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class VideoSegment(BaseModel):
    """A time-segmented chunk of analysis."""
    timestamp_start: str = ""
    timestamp_end: str = ""
    visual_description: str = ""
    transcript_chunk: str = ""
    entities_mentioned: list[str] = Field(default_factory=list)


class DiscoveredMethod(BaseModel):
    """A technique or method demonstrated in the video."""
    name: str
    description: str = ""
    tools_used: list[str] = Field(default_factory=list)
    code_shown: bool = False
    url_mentioned: str = ""


class VideoAnalysis(BaseModel):
    """Complete analysis of a video."""
    url: str
    title: str = ""
    platform: str = ""  # "youtube", "instagram", "tiktok"
    duration: str = ""
    transcript: str = ""
    visual_summary: str = ""
    segments: list[VideoSegment] = Field(default_factory=list)
    tools_found: list[str] = Field(default_factory=list)
    methods_found: list[DiscoveredMethod] = Field(default_factory=list)
    urls_mentioned: list[str] = Field(default_factory=list)
    luma_links: list[str] = Field(default_factory=list)
    entities: list[dict] = Field(default_factory=list)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: str = ""


class VideoIntelReport(BaseModel):
    """Report across multiple videos."""
    videos_analyzed: list[VideoAnalysis] = Field(default_factory=list)
    all_tools: list[str] = Field(default_factory=list)
    all_methods: list[DiscoveredMethod] = Field(default_factory=list)
    all_luma_links: list[str] = Field(default_factory=list)
    integration_candidates: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class VideoIntelEngine:
    """Analyzes YouTube/Instagram/TikTok videos for AI tool discoveries."""

    def __init__(self, config: HackForgeConfig):
        self.config = config
        self._reka = None
        self._fastino = None
        self._tavily = None
        self._modulate = None

    async def _ensure_providers(self):
        if self._reka is None:
            from hackforge.providers.reka_client import RekaClient
            self._reka = RekaClient(self.config.reka)
        if self._fastino is None:
            from hackforge.providers.fastino_client import FastinoClient
            self._fastino = FastinoClient(self.config.fastino)
        if self._tavily is None:
            from hackforge.providers.tavily_client import TavilyClient
            self._tavily = TavilyClient(self.config.tavily)

    async def analyze_video(self, url: str) -> VideoAnalysis:
        """Full pipeline: fetch video → Reka vision + audio → Fastino extract → discover."""
        await self._ensure_providers()
        analysis = VideoAnalysis(url=url, platform=self._detect_platform(url))

        try:
            # Step 1: Get video metadata via Tavily
            metadata = await self._fetch_metadata(url)
            analysis.title = metadata.get("title", "")
            analysis.duration = metadata.get("duration", "")

            # Step 2: Visual analysis via Reka Core (best for video)
            visual = await self._analyze_visual(url)
            analysis.visual_summary = visual

            # Step 3: Audio transcript via Reka
            transcript = await self._extract_transcript(url)
            analysis.transcript = transcript

            # Step 4: Combine all text and extract entities via Fastino
            combined_text = f"{analysis.title}\n{visual}\n{transcript}"
            entities = await self._extract_entities(combined_text)
            analysis.entities = entities
            analysis.tools_found = [
                e["entity"]
                for e in entities
                if e.get("type") in ("TOOL", "API", "FRAMEWORK", "COMPANY")
            ]

            # Step 5: Extract methods/techniques demonstrated
            methods = await self._extract_methods(combined_text)
            analysis.methods_found = methods

            # Step 6: Find any URLs mentioned (especially Luma links)
            urls = self._extract_urls(combined_text)
            analysis.urls_mentioned = urls
            analysis.luma_links = [
                u for u in urls if "lu.ma" in u or "luma.com" in u
            ]

        except Exception as e:
            logger.exception("Video analysis failed for %s", url)
            analysis.error = str(e)

        return analysis

    async def analyze_youtube(self, url: str) -> VideoAnalysis:
        """Convenience wrapper for YouTube URLs."""
        return await self.analyze_video(url)

    async def batch_analyze(self, urls: list[str]) -> VideoIntelReport:
        """Analyze multiple videos and compile a unified report."""
        import asyncio

        analyses = await asyncio.gather(
            *[self.analyze_video(url) for url in urls],
            return_exceptions=True,
        )

        report = VideoIntelReport()
        all_tools = set()
        all_methods = []

        for result in analyses:
            if isinstance(result, Exception):
                report.videos_analyzed.append(
                    VideoAnalysis(url="unknown", error=str(result))
                )
                continue
            report.videos_analyzed.append(result)
            all_tools.update(result.tools_found)
            all_methods.extend(result.methods_found)
            report.all_luma_links.extend(result.luma_links)

        report.all_tools = sorted(all_tools)
        report.all_methods = all_methods
        report.integration_candidates = report.all_tools
        return report

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _detect_platform(self, url: str) -> str:
        if "youtube.com" in url or "youtu.be" in url:
            return "youtube"
        if "instagram.com" in url:
            return "instagram"
        if "tiktok.com" in url:
            return "tiktok"
        return "unknown"

    async def _fetch_metadata(self, url: str) -> dict:
        """Get video title and metadata via Tavily search."""
        try:
            results = await self._tavily.search(f"{url} video", max_results=3)
            if results.results:
                return {
                    "title": results.results[0].title,
                    "description": results.results[0].content,
                }
        except Exception:
            logger.warning("Could not fetch metadata for %s", url)
        return {}

    async def _analyze_visual(self, url: str) -> str:
        """Use Reka Core to analyze video content visually."""
        prompt = (
            "Analyze this video thoroughly. Describe:\n"
            "1. What tools, software, or platforms are shown on screen\n"
            "2. Any code editors, terminals, dashboards, or UIs visible\n"
            "3. Any logos, brand names, or product names shown\n"
            "4. Any URLs, QR codes, or links displayed\n"
            "5. What techniques or methods are being demonstrated\n"
            "6. Any text overlays or captions\n"
            "Be specific about tool names and versions."
        )
        try:
            result = await self._reka.analyze_video(url, prompt, model="reka-core")
            return result
        except Exception as e:
            logger.warning("Visual analysis failed: %s", e)
            # Fallback: try as image (for thumbnails/screenshots)
            try:
                return await self._reka.analyze_image(url, prompt)
            except Exception:
                return ""

    async def _extract_transcript(self, url: str) -> str:
        """Extract speech from video via Reka audio analysis."""
        prompt = (
            "Transcribe all speech in this video verbatim. Include speaker "
            "changes if multiple speakers. Pay special attention to: tool names, "
            "API names, company names, URLs spoken aloud, and technical terms."
        )
        try:
            result = await self._reka.analyze_video(url, prompt, model="reka-core")
            return result
        except Exception as e:
            logger.warning("Transcript extraction failed: %s", e)
            return ""

    async def _extract_entities(self, text: str) -> list[dict]:
        """Use Fastino to extract tool/company/API entities."""
        if not text.strip():
            return []
        try:
            result = await self._fastino.extract_entities(
                text,
                entity_types=[
                    "TOOL", "API", "FRAMEWORK", "COMPANY", "LIBRARY",
                    "PLATFORM", "MODEL", "LANGUAGE", "URL",
                ],
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning("Entity extraction failed: %s", e)
            # Regex fallback for common AI tool patterns
            return self._regex_entity_fallback(text)

    async def _extract_methods(self, text: str) -> list[DiscoveredMethod]:
        """Use Fastino to identify techniques/methods demonstrated."""
        if not text.strip():
            return []
        try:
            result = await self._fastino.analyze(
                text,
                prompt=(
                    "Identify all AI/ML techniques, methods, and workflows "
                    "described in this text. For each, provide: name, description, "
                    "and what tools are used. Return as JSON array."
                ),
            )
            if isinstance(result, list):
                return [DiscoveredMethod(**m) for m in result if isinstance(m, dict)]
        except Exception:
            pass
        return []

    def _extract_urls(self, text: str) -> list[str]:
        """Extract URLs from text."""
        pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,;:!?]'
        return list(set(re.findall(pattern, text)))

    def _regex_entity_fallback(self, text: str) -> list[dict]:
        """Fallback entity extraction using regex patterns."""
        known_tools = [
            "OpenAI", "Claude", "Anthropic", "Tavily", "Yutori", "Reka",
            "Neo4j", "Modulate", "Senso", "Airbyte", "Render", "Fastino",
            "LangChain", "LlamaIndex", "Hugging Face", "Vercel", "Supabase",
            "Pinecone", "Weaviate", "ChromaDB", "GPT-4", "GPT-4o", "Gemini",
            "Mistral", "Llama", "Cursor", "Copilot", "Replit", "MCP",
            "FastAPI", "Streamlit", "Gradio", "Docker", "Kubernetes",
        ]
        found = []
        text_lower = text.lower()
        for tool in known_tools:
            if tool.lower() in text_lower:
                found.append({"entity": tool, "type": "TOOL", "confidence": 0.8})
        return found
