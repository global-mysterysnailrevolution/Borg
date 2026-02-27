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

    def __init__(self, config: HackForgeConfig) -> None:
        self._config = config
        self._tavily = TavilyClient(config.tavily)
        self._http: httpx.AsyncClient | None = None

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
            page_text = await self._scrape_page(url)
            if not page_text:
                logger.warning("No content retrieved for %s", url)
                report.error = "Could not retrieve page content."
                return report

            # Step 2: extract entities
            entities = await self._extract_entities(page_text)
            report.raw_entity_count = len(entities)
            logger.info("Extracted %d entities from %s", len(entities), url)

            # Step 3: research each entity
            researched: list[EntityResearch] = []
            for entity in entities:
                try:
                    research = await self._research_entity(entity)
                    researched.append(research)
                except Exception as exc:
                    logger.warning("Failed to research entity %s: %s", entity.name, exc)

            # Step 4: store in Neo4j (best-effort)
            try:
                await self._store_in_graph(researched)
            except Exception as exc:
                logger.warning("Neo4j storage failed (non-fatal): %s", exc)

            # Step 5: check against existing harness tools
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

        except Exception as exc:
            logger.exception("Unexpected error analysing %s", url)
            report.error = str(exc)

        return report

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    async def _scrape_page(self, url: str) -> str:
        """Retrieve page content via Tavily search, falling back to direct HTTP.

        Tavily's deep-extraction mode returns clean, structured text which is
        superior to raw HTML for downstream LLM processing.

        Args:
            url: The URL to scrape.

        Returns:
            Plain-text content of the page, or an empty string on failure.
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
                if resp.answer:
                    parts.append(resp.answer)
                for result in resp.results:
                    if result.raw_content:
                        parts.append(result.raw_content)
                    elif result.content:
                        parts.append(result.content)
                if parts:
                    return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("Tavily scrape failed for %s: %s — falling back to HTTP", url, exc)

        # Fallback: direct HTTP fetch
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "HackForge/0.1"})
                response.raise_for_status()
                return response.text
        except Exception as exc:
            logger.error("Direct HTTP fetch failed for %s: %s", url, exc)
            return ""

    async def _extract_entities(self, text: str) -> list[Entity]:
        """Extract tool/vendor/API entities from page text using Fastino.

        Sends the text to Fastino's fast-inference endpoint and parses the
        structured JSON response.  Falls back to keyword-based extraction when
        the API is unavailable.

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
            logger.warning("Fastino entity extraction failed: %s — using keyword fallback", exc)
            return self._keyword_entity_fallback(text)

    def _keyword_entity_fallback(self, text: str) -> list[Entity]:
        """Simple keyword scan used when Fastino is unavailable.

        Looks for common tool/API indicators like capitalized product names
        followed by 'API', 'SDK', or 'platform'.

        Args:
            text: Raw page text.

        Returns:
            Best-effort list of :class:`Entity` objects.
        """
        import re

        patterns = [
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+API\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+SDK\b",
            r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s[A-Z][a-zA-Z0-9]+)?)\s+platform\b",
        ]
        found: dict[str, Entity] = {}
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                if name.lower() not in found:
                    found[name.lower()] = Entity(
                        name=name,
                        entity_type="tool",
                        raw_mention=match.group(0),
                        confidence=0.5,
                    )
        return list(found.values())[:20]  # cap at 20 to avoid noise

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

    async def _store_in_graph(self, entities: list[EntityResearch]) -> None:
        """Store discovered entities and their relationships in Neo4j.

        Creates ``Tool`` nodes and ``DISCOVERED_FROM`` relationships.
        Skips gracefully when Neo4j is not configured.

        Args:
            entities: List of researched entities to persist.
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
