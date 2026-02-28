"""Link Intelligence Engine — URL-driven tool and vendor discovery.

Takes any URL (Luma hackathon page, landing page, docs site, etc.) and runs a
full discovery pipeline:

  scrape → extract entities → deep-research each → store in Neo4j → compare
  against existing harness tools → return a structured LinkIntelReport.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig
from hackforge.pipeline_bus import PipelineBus
from hackforge.providers.tavily_client import TavilyClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """A tool, vendor, or API discovered from raw text."""

    name: str
    entity_type: str = "tool"  # "tool" | "vendor" | "api" | "library"
    raw_mention: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DiscoveredTool(BaseModel):
    """Enriched description of a discovered tool after deep research."""

    name: str
    vendor: str = ""
    description: str = ""
    api_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    auth_type: str = ""  # "api_key" | "oauth" | "none" | "unknown"
    has_free_tier: bool = False
    pricing_url: str = ""
    docs_url: str = ""


class EntityResearch(BaseModel):
    """Results of deep-researching a single entity."""

    entity: Entity
    tool: DiscoveredTool
    raw_research: str = ""
    sources: list[str] = Field(default_factory=list)
    researched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExistingTool(BaseModel):
    """A tool that already exists in the harness."""

    name: str
    description: str = ""
    config_path: str = ""
    capabilities: list[str] = Field(default_factory=list)


class ToolComparison(BaseModel):
    """Side-by-side comparison between a newly discovered tool and an existing one."""

    new_tool: DiscoveredTool
    existing_tool: ExistingTool
    overlap_score: float = Field(default=0.0, ge=0.0, le=1.0)
    new_capabilities: list[str] = Field(default_factory=list)
    notes: str = ""


class RecommendedAction(BaseModel):
    """A single recommended action for a discovered tool."""

    tool_name: str
    action: str  # "integrate" | "replace" | "skip" | "evaluate"
    reason: str
    priority: int = Field(default=2, ge=1, le=3)  # 1=high, 2=medium, 3=low


class LinkIntelReport(BaseModel):
    """Full report produced by LinkIntelEngine.analyze_url."""

    url: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    page_title: str = ""
    discovered_tools: list[DiscoveredTool] = Field(default_factory=list)
    existing_alternatives: list[ToolComparison] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    raw_entity_count: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class LinkIntelEngine:
    """Takes a URL (Luma hackathon, any webpage) and discovers tools/vendors/APIs.

    Pipeline:
        1. Scrape page content via Tavily search or direct HTTP fetch.
        2. Extract entity names (tools, companies, APIs) via Fastino LLM.
        3. Deep-research each entity via Tavily.
        4. Store knowledge in Neo4j graph.
        5. Compare against existing harness tools.
        6. Return a structured LinkIntelReport.

    Usage::

        config = HackForgeConfig.load()
        engine = LinkIntelEngine(config)
        report = await engine.analyze_url("https://lu.ma/some-hackathon")
        print(report.model_dump_json(indent=2))
    """

    def __init__(self, config: HackForgeConfig, bus: PipelineBus | None = None) -> None:
        self._config = config
        self._tavily = TavilyClient(config.tavily)
        self._http: httpx.AsyncClient | None = None
        self._bus = bus

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_url(self, url: str) -> LinkIntelReport:
        """Full pipeline: scrape → extract → research → graph → compare.

        Args:
            url: Any publicly accessible URL to analyse.

        Returns:
            A :class:`LinkIntelReport` with all discovered tools and actions.
        """
        logger.info("LinkIntelEngine: starting analysis of %s", url)
        report = LinkIntelReport(url=url)

        try:
            # Step 1: scrape
            if self._bus:
                await self._bus.emit_step("link_intel", "scrape", f"Scraping {url}...")
            page_text, page_title = await self._scrape_page(url)
            if page_title:
                report.page_title = page_title
            if not page_text:
                logger.warning("No content retrieved for %s", url)
                report.error = "Could not retrieve page content."
                if self._bus:
                    await self._bus.emit_error("link_intel", "scrape", f"No content from {url}")
                return report
            if self._bus:
                await self._bus.emit_step(
                    "link_intel", "scrape",
                    f"Scraped {len(page_text)} chars" + (f' from "{page_title}"' if page_title else ""),
                )

            # Step 2: extract entities
            if self._bus:
                await self._bus.emit_step("link_intel", "extract", "Extracting entities (Fastino → Reka → keyword)...")
            entities = await self._extract_entities(page_text)
            report.raw_entity_count = len(entities)
            logger.info("Extracted %d entities from %s", len(entities), url)
            if self._bus:
                names = [e.name for e in entities[:10]]
                await self._bus.emit_step(
                    "link_intel", "extract",
                    f"Extracted {len(entities)} entities: {', '.join(names)}",
                    {"entities": [e.name for e in entities]},
                )

            # Step 3: research each entity
            researched: list[EntityResearch] = []
            for i, entity in enumerate(entities):
                try:
                    if self._bus:
                        await self._bus.emit_step(
                            "link_intel", "research",
                            f"Researching {entity.name} ({i+1}/{len(entities)})...",
                        )
                    research = await self._research_entity(entity)
                    researched.append(research)
                except Exception as exc:
                    logger.warning("Failed to research entity %s: %s", entity.name, exc)
                    if self._bus:
                        await self._bus.emit_error(
                            "link_intel", "research", f"Research failed for {entity.name}: {exc}"
                        )

            # Step 4: store in Neo4j (best-effort)
            if self._bus:
                await self._bus.emit_step("link_intel", "graph", f"Storing {len(researched)} tools in Neo4j...")
            try:
                await self._store_in_graph(
                    researched,
                    source_url=url,
                    source_type=self._infer_source_type(url),
                    entity_count=len(entities),
                )
                if self._bus:
                    await self._bus.emit_step("link_intel", "graph", f"Stored {len(researched)} tools in Neo4j")
            except Exception as exc:
                logger.warning("Neo4j storage failed (non-fatal): %s", exc)
                if self._bus:
                    await self._bus.emit_error("link_intel", "graph", f"Neo4j storage failed: {exc}")

            # Step 5: check against existing harness tools
            if self._bus:
                await self._bus.emit_step("link_intel", "compare", "Comparing against existing harness tools...")
            comparisons: list[ToolComparison] = []
            for er in researched:
                existing = await self._check_existing(er.entity)
                if existing:
                    comparison = self._build_comparison(er.tool, existing)
                    comparisons.append(comparison)

            # Step 6: assemble report
            report.discovered_tools = [er.tool for er in researched]
            report.existing_alternatives = comparisons
            report.recommended_actions = self._generate_recommendations(
                researched, comparisons
            )

            if self._bus:
                await self._bus.emit_result(
                    "link_intel", "complete",
                    f"Found {len(report.discovered_tools)} tools, {len(report.recommended_actions)} actions",
                    {"tool_count": len(report.discovered_tools)},
                )

        except Exception as exc:
            logger.exception("Unexpected error analysing %s", url)
            report.error = str(exc)
            if self._bus:
                await self._bus.emit_error("link_intel", "error", f"Pipeline error: {exc}")

        return report

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    async def _scrape_page(self, url: str) -> tuple[str, str]:
        """Retrieve page content via Tavily search, falling back to direct HTTP.

        Tavily's deep-extraction mode returns clean, structured text which is
        superior to raw HTML for downstream LLM processing.  When Tavily
        results are available the page title is extracted from the first
        result's ``title`` field.

        Args:
            url: The URL to scrape.

        Returns:
            A ``(page_text, page_title)`` tuple.  *page_text* is the plain-text
            content of the page (empty string on failure) and *page_title* is
            the best-effort title (empty string if unknown).
        """
        logger.debug("Scraping %s via Tavily", url)
        try:
            async with TavilyClient(self._config.tavily) as client:
                resp = await client.search(
                    query=f"site:{url} OR tools APIs vendors",
                    max_results=5,
                    search_depth="advanced",
                    include_raw_content=True,
                )
                parts: list[str] = []
                page_title = ""
                if resp.answer:
                    parts.append(resp.answer)
                for idx, result in enumerate(resp.results):
                    # Use the first result's title as the page title
                    if idx == 0 and result.title:
                        page_title = result.title
                    if result.raw_content:
                        parts.append(result.raw_content)
                    elif result.content:
                        parts.append(result.content)
                if parts:
                    return "\n\n".join(parts), page_title
        except Exception as exc:
            logger.warning("Tavily scrape failed for %s: %s — falling back to HTTP", url, exc)

        # Fallback: direct HTTP fetch
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "HackForge/0.1"})
                response.raise_for_status()
                return response.text, ""
        except Exception as exc:
            logger.error("Direct HTTP fetch failed for %s: %s", url, exc)
            return "", ""

    async def _extract_entities(self, text: str) -> list[Entity]:
        """Extract tool/vendor/API entities from page text.

        Tries extraction providers in order of preference:
          1. **Fastino** -- fast GLiNER2-based entity extraction.
          2. **Reka** -- ``reka-flash`` model as an LLM fallback.
          3. **Keyword** -- smart regex/dictionary scan as a last resort.

        Args:
            text: Raw page text (potentially large).

        Returns:
            Deduplicated list of :class:`Entity` objects.
        """
        # Truncate to avoid exceeding context limits
        chunk = text[:12_000]

        prompt = (
            "You are an expert at identifying AI tools, APIs, SDKs, SaaS vendors, "
            "and developer libraries mentioned in text.\n\n"
            "Extract ALL tools/vendors/APIs from the following text. "
            "Return ONLY a JSON array of objects, each with:\n"
            '  "name": string (canonical product name),\n'
            '  "entity_type": one of "tool"|"vendor"|"api"|"library",\n'
            '  "raw_mention": exact phrase from text,\n'
            '  "confidence": float 0-1\n\n'
            f"TEXT:\n{chunk}\n\n"
            "JSON:"
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
                        "max_tokens": 2048,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                raw_json: str = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "[]")
                )
                items: list[dict[str, Any]] = json.loads(raw_json)
                entities = [Entity(**item) for item in items if "name" in item]
                # Deduplicate by lowercase name
                seen: set[str] = set()
                unique: list[Entity] = []
                for e in entities:
                    key = e.name.lower()
                    if key not in seen:
                        seen.add(key)
                        unique.append(e)
                return unique

        except Exception as exc:
            logger.warning("Fastino entity extraction failed: %s — trying Reka", exc)
            return await self._reka_entity_extraction(text)

    async def _reka_entity_extraction(self, text: str) -> list[Entity]:
        """Extract entities using Reka AI as an alternative to Fastino.

        Uses the ``reka-flash`` model via the Reka chat completions API.
        Falls back to :meth:`_keyword_entity_fallback` if Reka is also
        unavailable.

        Args:
            text: Raw page text (potentially large).

        Returns:
            Deduplicated list of :class:`Entity` objects.
        """
        chunk = text[:12_000]

        prompt = (
            "You are an expert at identifying AI tools, APIs, SDKs, SaaS vendors, "
            "and developer libraries mentioned in text.\n\n"
            "Extract ALL tools/vendors/APIs from the following text. "
            "Return ONLY a JSON array of objects, each with:\n"
            '  "name": string (canonical product name),\n'
            '  "entity_type": one of "tool"|"vendor"|"api"|"library",\n'
            '  "raw_mention": exact phrase from text,\n'
            '  "confidence": float 0-1\n\n'
            f"TEXT:\n{chunk}\n\n"
            "JSON:"
        )

        try:
            async with httpx.AsyncClient(timeout=self._config.reka.timeout) as client:
                response = await client.post(
                    f"{self._config.reka.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._config.reka.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "reka-flash",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                # Reka uses "responses" array (not "choices"); each item
                # has message.content directly.
                raw_json: str = (
                    data.get("responses", [{}])[0]
                    .get("message", {})
                    .get("content", "[]")
                )
                items: list[dict[str, Any]] = json.loads(raw_json)
                entities = [Entity(**item) for item in items if "name" in item]
                # Deduplicate by lowercase name
                seen: set[str] = set()
                unique: list[Entity] = []
                for e in entities:
                    key = e.name.lower()
                    if key not in seen:
                        seen.add(key)
                        unique.append(e)
                logger.info("Reka entity extraction succeeded: %d entities", len(unique))
                return unique

        except Exception as exc:
            logger.warning("Reka entity extraction failed: %s — using keyword fallback", exc)
            return self._keyword_entity_fallback(text)

    # Known AI/developer tool and vendor names for keyword fallback matching.
    _KNOWN_TOOL_NAMES: list[str] = [
        "Tavily", "Reka", "Fastino", "Neo4j", "Yutori", "Senso", "Modulate",
        "Airbyte", "Render", "AWS", "OpenAI", "Numeric", "LangChain",
        "Anthropic", "Hugging Face", "HuggingFace", "Pinecone", "Weaviate",
        "Cohere", "Replicate", "Mistral", "Groq", "Together AI", "Perplexity",
        "Vercel", "Supabase", "Firebase", "MongoDB", "Redis", "Postgres",
        "Stripe", "Twilio", "SendGrid", "Algolia", "Elastic", "Datadog",
        "Sentry", "LaunchDarkly", "Segment", "Amplitude", "Mixpanel",
        "Cloudflare", "Fly.io", "Railway", "Neon", "PlanetScale", "Turso",
        "Upstash", "Convex", "Clerk", "Auth0", "Okta", "WorkOS",
        "LlamaIndex", "ChromaDB", "Chroma", "Qdrant", "Milvus", "Zilliz",
        "Unstructured", "DocArray", "Haystack", "Marqo", "Vespa",
        "Stability AI", "Midjourney", "ElevenLabs", "Deepgram", "AssemblyAI",
        "Whisper", "DALL-E", "GPT-4", "Claude", "Gemini", "Llama",
        "Streamlit", "Gradio", "Chainlit", "Modal", "Banana", "Baseten",
        "Cerebrium", "RunPod", "Lambda", "Anyscale", "Weights & Biases",
        "MLflow", "DVC", "ClearML", "Neptune", "Comet",
    ]

    # URL-friendly slugs mapped to canonical names for URL-based detection.
    _URL_TOOL_MAP: dict[str, str] = {
        "tavily": "Tavily", "reka": "Reka", "fastino": "Fastino",
        "neo4j": "Neo4j", "yutori": "Yutori", "senso": "Senso",
        "modulate": "Modulate", "airbyte": "Airbyte", "render": "Render",
        "openai": "OpenAI", "langchain": "LangChain", "anthropic": "Anthropic",
        "huggingface": "Hugging Face", "pinecone": "Pinecone",
        "weaviate": "Weaviate", "cohere": "Cohere", "replicate": "Replicate",
        "mistral": "Mistral", "groq": "Groq", "together": "Together AI",
        "perplexity": "Perplexity", "vercel": "Vercel", "supabase": "Supabase",
        "firebase": "Firebase", "mongodb": "MongoDB", "redis": "Redis",
        "stripe": "Stripe", "twilio": "Twilio", "sendgrid": "SendGrid",
        "algolia": "Algolia", "elastic": "Elastic", "datadog": "Datadog",
        "sentry": "Sentry", "segment": "Segment", "cloudflare": "Cloudflare",
        "fly": "Fly.io", "railway": "Railway", "neon": "Neon",
        "planetscale": "PlanetScale", "upstash": "Upstash", "convex": "Convex",
        "clerk": "Clerk", "auth0": "Auth0", "workos": "WorkOS",
        "llamaindex": "LlamaIndex", "chromadb": "ChromaDB", "qdrant": "Qdrant",
        "milvus": "Milvus", "zilliz": "Zilliz", "stability": "Stability AI",
        "elevenlabs": "ElevenLabs", "deepgram": "Deepgram",
        "assemblyai": "AssemblyAI", "streamlit": "Streamlit",
        "gradio": "Gradio", "chainlit": "Chainlit", "modal": "Modal",
        "baseten": "Baseten", "runpod": "RunPod", "anyscale": "Anyscale",
        "wandb": "Weights & Biases", "mlflow": "MLflow",
        "numeric": "Numeric",
    }

    def _keyword_entity_fallback(self, text: str) -> list[Entity]:
        """Smart keyword scan used when LLM-based extraction is unavailable.

        Uses three complementary strategies:
          1. **Known names** -- scans for a curated list of AI/developer tool
             names appearing anywhere in the text.
          2. **Contextual patterns** -- matches phrases like ``"powered by X"``,
             ``"built with X"``, ``"X API"``, ``"X SDK"``, ``"X platform"``,
             ``"sponsored by X"``, and ``"presented by X"``.
          3. **URL matching** -- finds URLs containing known tool domain slugs
             (e.g. ``reka.ai``, ``tavily.com``).

        Args:
            text: Raw page text.

        Returns:
            Best-effort list of :class:`Entity` objects (capped at 30).
        """
        import re

        found: dict[str, Entity] = {}
        text_lower = text.lower()

        # --- Strategy 1: known tool/vendor names ---
        for name in self._KNOWN_TOOL_NAMES:
            # Use word-boundary matching; for multi-word names the boundary is
            # at the start of the first word and end of the last word.
            pattern = rf"\b{re.escape(name)}\b"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                key = name.lower()
                if key not in found:
                    found[key] = Entity(
                        name=name,
                        entity_type="tool",
                        raw_mention=match.group(0),
                        confidence=0.7,
                    )

        # --- Strategy 2: contextual patterns ---
        # Patterns where the tool name follows a keyword: "X API", "X SDK", etc.
        suffix_patterns = [
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+API\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+SDK\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+platform\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+library\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+framework\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+integration\b",
        ]
        for pattern in suffix_patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                key = name.lower()
                if key not in found:
                    found[key] = Entity(
                        name=name,
                        entity_type="tool",
                        raw_mention=match.group(0),
                        confidence=0.5,
                    )

        # Patterns where the tool name follows a preposition:
        # "powered by X", "built with X", "sponsored by X", "presented by X"
        prefix_patterns = [
            r"(?:powered\s+by|built\s+with|built\s+on|sponsored\s+by|presented\s+by|"
            r"backed\s+by|maintained\s+by|developed\s+by|created\s+with|hosted\s+on|"
            r"deployed\s+on|runs\s+on|using)\s+"
            r"([A-Z][a-zA-Z0-9]+(?:\s[A-Z][a-zA-Z0-9]+)?(?:\.\w+)?)",
        ]
        for pattern in prefix_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1).strip()
                key = name.lower()
                if key not in found:
                    found[key] = Entity(
                        name=name,
                        entity_type="vendor",
                        raw_mention=match.group(0),
                        confidence=0.6,
                    )

        # --- Strategy 3: URL-based detection ---
        url_pattern = r"https?://(?:www\.)?([a-zA-Z0-9-]+)\.[a-zA-Z]{2,}"
        for match in re.finditer(url_pattern, text):
            domain_slug = match.group(1).lower()
            if domain_slug in self._URL_TOOL_MAP:
                canonical = self._URL_TOOL_MAP[domain_slug]
                key = canonical.lower()
                if key not in found:
                    found[key] = Entity(
                        name=canonical,
                        entity_type="tool",
                        raw_mention=match.group(0),
                        confidence=0.6,
                    )

        return list(found.values())[:30]  # cap at 30 to avoid noise

    async def _research_entity(self, entity: Entity) -> EntityResearch:
        """Deep-research a single entity using Tavily.

        Searches for the tool's API docs, pricing, features, and auth model.

        Args:
            entity: The entity to research.

        Returns:
            An :class:`EntityResearch` object with an enriched :class:`DiscoveredTool`.
        """
        logger.debug("Researching entity: %s", entity.name)

        query = (
            f"{entity.name} API documentation pricing free tier authentication "
            "capabilities integrations developer"
        )

        sources: list[str] = []
        raw_text = ""
        tool = DiscoveredTool(name=entity.name)

        try:
            async with TavilyClient(self._config.tavily) as client:
                resp = await client.search(query, max_results=8, search_depth="advanced")
                if resp.answer:
                    raw_text = resp.answer
                for result in resp.results:
                    sources.append(result.url)
                    raw_text += f"\n{result.content}"

            # Parse the research into a structured DiscoveredTool via Fastino
            tool = await self._parse_tool_research(entity.name, raw_text)

        except Exception as exc:
            logger.warning("Research failed for %s: %s", entity.name, exc)
            tool = DiscoveredTool(name=entity.name)

        return EntityResearch(
            entity=entity,
            tool=tool,
            raw_research=raw_text[:4000],
            sources=sources,
        )

    async def _parse_tool_research(self, tool_name: str, research_text: str) -> DiscoveredTool:
        """Use Fastino to parse free-form research text into a DiscoveredTool.

        Args:
            tool_name: Name of the tool being researched.
            research_text: Raw text from Tavily search results.

        Returns:
            A populated :class:`DiscoveredTool`, or a minimal stub on failure.
        """
        chunk = research_text[:6000]
        prompt = (
            f"Based on the following research text about '{tool_name}', extract a structured "
            "profile. Return ONLY valid JSON with these exact fields:\n"
            '  "name": string,\n'
            '  "vendor": string (company name),\n'
            '  "description": string (1-2 sentences),\n'
            '  "api_url": string (URL to API/developer docs),\n'
            '  "capabilities": array of strings (key features),\n'
            '  "auth_type": one of "api_key"|"oauth"|"none"|"unknown",\n'
            '  "has_free_tier": boolean,\n'
            '  "pricing_url": string,\n'
            '  "docs_url": string\n\n'
            f"RESEARCH TEXT:\n{chunk}\n\nJSON:"
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
                raw_json: str = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "{}")
                )
                parsed = json.loads(raw_json)
                parsed.setdefault("name", tool_name)
                return DiscoveredTool(**parsed)
        except Exception as exc:
            logger.warning("Could not parse tool research for %s via Fastino: %s", tool_name, exc)
            return DiscoveredTool(name=tool_name)

    async def _check_existing(self, entity: Entity) -> ExistingTool | None:
        """Check whether the entity already exists in the harness tool registry.

        Reads tool-broker.md and any YAML/JSON manifests under the harness
        project root looking for name overlap.

        Args:
            entity: The entity to look up.

        Returns:
            An :class:`ExistingTool` if a match is found, else ``None``.
        """
        import re

        tool_broker_path = self._config.project_root / "tool-broker.md"
        search_name = entity.name.lower()

        if tool_broker_path.exists():
            try:
                content = tool_broker_path.read_text(encoding="utf-8")
                # Look for the tool name in headings or bullet points
                pattern = re.compile(
                    rf"(?:^|\n)\s*[#*-]?\s*(?P<line>[^\n]*{re.escape(search_name)}[^\n]*)",
                    re.IGNORECASE,
                )
                match = pattern.search(content)
                if match:
                    line = match.group("line").strip()
                    return ExistingTool(
                        name=entity.name,
                        description=line,
                        config_path=str(tool_broker_path),
                    )
            except OSError as exc:
                logger.debug("Could not read tool-broker.md: %s", exc)

        # Also scan mcp-servers/ directory for a matching server
        mcp_root = self._config.project_root / "mcp-servers"
        if mcp_root.exists():
            for child in mcp_root.iterdir():
                if search_name in child.name.lower():
                    return ExistingTool(
                        name=entity.name,
                        description=f"Existing MCP server: {child.name}",
                        config_path=str(child),
                    )

        return None

    @staticmethod
    def _infer_source_type(url: str) -> str:
        """Infer the source type from a URL.

        Args:
            url: The URL to classify.

        Returns:
            One of ``"luma"``, ``"youtube"``, ``"instagram"``, or ``"manual"``.
        """
        url_lower = url.lower()
        if "lu.ma" in url_lower or "luma" in url_lower:
            return "luma"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        if "instagram.com" in url_lower:
            return "instagram"
        return "manual"

    async def _store_in_graph(
        self,
        entities: list[EntityResearch],
        *,
        source_url: str = "",
        source_type: str = "manual",
        entity_count: int = 0,
    ) -> None:
        """Store discovered entities and their relationships in Neo4j.

        Creates ``Tool`` nodes, a ``DiscoveryEvent`` node for this run, and
        ``DISCOVERED_FROM`` relationships linking each tool to the event.
        Skips gracefully when Neo4j is not configured.

        Args:
            entities: List of researched entities to persist.
            source_url: The URL that was analysed in this discovery run.
            source_type: One of ``"luma"``, ``"youtube"``, ``"instagram"``,
                         ``"manual"``.
            entity_count: Total number of raw entities extracted before
                          filtering/dedup.
        """
        if not self._config.neo4j_password and not self._config.neo4j_uri:
            logger.debug("Neo4j not configured — skipping graph storage.")
            return

        try:
            from neo4j import AsyncGraphDatabase  # type: ignore[import]
        except ImportError:
            logger.warning("neo4j driver not installed — skipping graph storage.")
            return

        driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_user, self._config.neo4j_password),
        )
        try:
            async with driver.session() as session:
                # --- Upsert Tool nodes ---
                for er in entities:
                    t = er.tool
                    await session.run(
                        """
                        MERGE (tool:Tool {name: $name})
                        SET tool.vendor = $vendor,
                            tool.description = $description,
                            tool.api_url = $api_url,
                            tool.auth_type = $auth_type,
                            tool.has_free_tier = $has_free_tier,
                            tool.updated_at = datetime()
                        """,
                        name=t.name,
                        vendor=t.vendor,
                        description=t.description,
                        api_url=t.api_url,
                        auth_type=t.auth_type,
                        has_free_tier=t.has_free_tier,
                    )
                    logger.debug("Stored %s in Neo4j", t.name)

                # --- Create DiscoveryEvent and link to tools ---
                tool_names = [er.tool.name for er in entities]
                if tool_names and source_url:
                    from hackforge.graph.queries import LOG_DISCOVERY

                    await session.run(
                        LOG_DISCOVERY,
                        url=source_url,
                        source_type=source_type,
                        engine_used="link_intel",
                        entity_count=entity_count,
                        tool_names=tool_names,
                    )
                    logger.info(
                        "Created DiscoveryEvent for %s with %d tools",
                        source_url,
                        len(tool_names),
                    )
        finally:
            await driver.close()

    # ------------------------------------------------------------------
    # Report helpers
    # ------------------------------------------------------------------

    def _build_comparison(
        self, new_tool: DiscoveredTool, existing: ExistingTool
    ) -> ToolComparison:
        """Build a side-by-side comparison between new and existing tools.

        Args:
            new_tool: The newly discovered tool.
            existing: The matching tool already in the harness.

        Returns:
            A :class:`ToolComparison` with overlap score and delta capabilities.
        """
        existing_caps_lower = {c.lower() for c in existing.capabilities}
        new_caps = new_tool.capabilities
        new_only = [c for c in new_caps if c.lower() not in existing_caps_lower]

        overlap = 0.0
        if new_caps and existing.capabilities:
            overlap_count = len(new_caps) - len(new_only)
            overlap = overlap_count / max(len(new_caps), len(existing.capabilities))

        return ToolComparison(
            new_tool=new_tool,
            existing_tool=existing,
            overlap_score=round(overlap, 2),
            new_capabilities=new_only,
            notes=(
                f"New tool adds {len(new_only)} capability(ies) not present in existing tool."
            ),
        )

    def _generate_recommendations(
        self,
        researched: list[EntityResearch],
        comparisons: list[ToolComparison],
    ) -> list[RecommendedAction]:
        """Generate recommended actions for each discovered tool.

        Logic:
        - If a tool has no existing alternative → recommend "integrate".
        - If overlap > 0.8 and no new capabilities → recommend "skip".
        - If overlap > 0.5 but the new tool adds capabilities → recommend "evaluate".
        - If overlap < 0.5 → recommend "integrate".

        Args:
            researched: All researched entities.
            comparisons: Comparisons against existing harness tools.

        Returns:
            List of :class:`RecommendedAction` objects, one per tool.
        """
        comparison_map = {c.new_tool.name: c for c in comparisons}
        actions: list[RecommendedAction] = []

        for er in researched:
            name = er.tool.name
            if name not in comparison_map:
                actions.append(
                    RecommendedAction(
                        tool_name=name,
                        action="integrate",
                        reason="No existing alternative found in harness — integrate as new tool.",
                        priority=1,
                    )
                )
                continue

            comp = comparison_map[name]
            if comp.overlap_score > 0.8 and not comp.new_capabilities:
                actions.append(
                    RecommendedAction(
                        tool_name=name,
                        action="skip",
                        reason=(
                            f"High overlap ({comp.overlap_score:.0%}) with existing tool "
                            f"'{comp.existing_tool.name}' and no new capabilities."
                        ),
                        priority=3,
                    )
                )
            elif comp.overlap_score > 0.5:
                actions.append(
                    RecommendedAction(
                        tool_name=name,
                        action="evaluate",
                        reason=(
                            f"Partial overlap ({comp.overlap_score:.0%}) with "
                            f"'{comp.existing_tool.name}' but adds: "
                            + ", ".join(comp.new_capabilities[:3])
                        ),
                        priority=2,
                    )
                )
            else:
                actions.append(
                    RecommendedAction(
                        tool_name=name,
                        action="integrate",
                        reason=(
                            f"Low overlap ({comp.overlap_score:.0%}) with existing tool — "
                            "sufficiently different to justify integration."
                        ),
                        priority=2,
                    )
                )

        return actions
