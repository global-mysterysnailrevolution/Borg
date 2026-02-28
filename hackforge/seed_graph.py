"""Seed the Neo4j Aura knowledge graph with HackForge schema and initial data.

This script is fully idempotent — it uses MERGE for all nodes and
relationships, so it can be re-run safely at any time.

Usage:
    cd <project_root>
    set -a && source .env && set +a
    export PYTHONPATH="$PWD"
    python hackforge/seed_graph.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import neo4j
from neo4j import AsyncGraphDatabase

from hackforge.graph.schema import SCHEMA_INIT_QUERIES
from hackforge.graph.queries import (
    UPSERT_VENDOR,
    UPSERT_TOOL,
    UPSERT_CAPABILITY,
    CREATE_OFFERS_REL,
    CREATE_PROVIDES_REL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")


def _check_env() -> None:
    missing = []
    if not NEO4J_URI:
        missing.append("NEO4J_URI")
    if not NEO4J_PASSWORD:
        missing.append("NEO4J_PASSWORD")
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

VENDORS: list[dict] = [
    {"name": "Tavily",   "url": "https://tavily.com",       "description": "AI-powered web search API for LLM agents",              "hackathon_sponsor": True},
    {"name": "Reka AI",  "url": "https://reka.ai",          "description": "Multimodal AI — vision, video, audio, and research",    "hackathon_sponsor": True},
    {"name": "Fastino",  "url": "https://fastino.ai",       "description": "Entity extraction (GLiNER2), classification, Pioneer personalization", "hackathon_sponsor": True},
    {"name": "Neo4j",    "url": "https://neo4j.com",        "description": "Graph database for connected data and knowledge graphs", "hackathon_sponsor": True},
    {"name": "Yutori",   "url": "https://yutori.ai",        "description": "Browser automation, scouting, and web research",        "hackathon_sponsor": True},
    {"name": "Senso",    "url": "https://senso.ai",         "description": "Knowledge base and document storage platform",          "hackathon_sponsor": True},
    {"name": "Modulate", "url": "https://modulate.ai",      "description": "Voice/audio moderation with ToxMod",                   "hackathon_sponsor": True},
    {"name": "Airbyte",  "url": "https://airbyte.com",      "description": "Open-source data integration and ELT pipelines",       "hackathon_sponsor": True},
    {"name": "Render",   "url": "https://render.com",       "description": "Cloud deployment platform — workers, cron, static sites", "hackathon_sponsor": True},
    {"name": "AWS",      "url": "https://aws.amazon.com",   "description": "Cloud infrastructure — compute, storage, AI/ML services", "hackathon_sponsor": True},
    {"name": "OpenAI",   "url": "https://openai.com",       "description": "Large language model inference — GPT-4o, o1, embeddings", "hackathon_sponsor": True},
    {"name": "Numeric",  "url": "https://numeric.io",       "description": "AI-powered analytics and financial close automation",   "hackathon_sponsor": True},
]

# Each vendor's key product as a Tool node
TOOLS: list[dict] = [
    {
        "name": "Tavily Search",
        "description": "Real-time AI search API optimised for LLM tool-use",
        "url": "https://api.tavily.com",
        "api_base_url": "https://api.tavily.com",
        "auth_type": "api_key",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["search"],
        "vendor": "Tavily",
    },
    {
        "name": "Reka Flash",
        "description": "Multimodal model — vision, video frames, audio transcription, research agent",
        "url": "https://api.reka.ai",
        "api_base_url": "https://api.reka.ai/v2",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["llm", "vision", "audio"],
        "vendor": "Reka AI",
    },
    {
        "name": "Fastino GLiNER",
        "description": "High-speed entity extraction, classification, and Pioneer personalization engine",
        "url": "https://api.fastino.ai",
        "api_base_url": "https://api.fastino.ai/v1",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["llm", "code_execution"],
        "vendor": "Fastino",
    },
    {
        "name": "Neo4j Aura",
        "description": "Managed graph database service with Cypher query language",
        "url": "https://neo4j.com/cloud/aura/",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["database"],
        "vendor": "Neo4j",
    },
    {
        "name": "Yutori Browser",
        "description": "Headless browser automation and web scouting via MCP",
        "url": "https://yutori.ai",
        "api_base_url": "",
        "auth_type": "api_key",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "uvx yutori-mcp",
        "categories": ["browser", "search"],
        "vendor": "Yutori",
    },
    {
        "name": "Senso KB",
        "description": "Knowledge base with document storage and semantic retrieval",
        "url": "https://api.senso.ai",
        "api_base_url": "https://api.senso.ai/v1",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["storage", "search"],
        "vendor": "Senso",
    },
    {
        "name": "ToxMod",
        "description": "Real-time voice and audio moderation (toxicity, hate speech, profanity)",
        "url": "https://modulate.ai/toxmod",
        "api_base_url": "https://api.modulate.ai/v1",
        "auth_type": "api_key",
        "has_free_tier": False,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["audio"],
        "vendor": "Modulate",
    },
    {
        "name": "Airbyte Cloud",
        "description": "350+ connectors for ELT data pipelines and replication",
        "url": "https://airbyte.com",
        "api_base_url": "http://localhost:8000/api/v1",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["database", "storage"],
        "vendor": "Airbyte",
    },
    {
        "name": "Render Deploy",
        "description": "One-click cloud deployment for services, workers, cron, and static sites",
        "url": "https://render.com",
        "api_base_url": "https://api.render.com/v1",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["storage"],
        "vendor": "Render",
    },
    {
        "name": "AWS Bedrock",
        "description": "Managed foundation model access — Claude, Titan, Llama on AWS infrastructure",
        "url": "https://aws.amazon.com/bedrock/",
        "api_base_url": "",
        "auth_type": "api_key",
        "has_free_tier": False,
        "is_integrated": False,
        "mcp_command": "",
        "categories": ["llm"],
        "vendor": "AWS",
    },
    {
        "name": "OpenAI API",
        "description": "GPT-4o, o1, embeddings, and DALL-E image generation",
        "url": "https://platform.openai.com",
        "api_base_url": "https://api.openai.com/v1",
        "auth_type": "bearer",
        "has_free_tier": False,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["llm"],
        "vendor": "OpenAI",
    },
    {
        "name": "Numeric Analytics",
        "description": "AI-driven analytics, financial close automation, and reporting",
        "url": "https://numeric.io",
        "api_base_url": "",
        "auth_type": "bearer",
        "has_free_tier": True,
        "is_integrated": False,
        "mcp_command": "",
        "categories": ["storage"],
        "vendor": "Numeric",
    },
]

CAPABILITIES: list[dict] = [
    {"name": "web_search",          "description": "Search the live web and return structured results"},
    {"name": "video_analysis",      "description": "Extract information from video frames and audio tracks"},
    {"name": "entity_extraction",   "description": "Identify named entities, tools, and products from text"},
    {"name": "graph_storage",       "description": "Store and query connected data in a property graph"},
    {"name": "browser_control",     "description": "Automate headless browser sessions for scraping and interaction"},
    {"name": "audio_transcription", "description": "Transcribe and moderate audio content"},
    {"name": "mcp_generation",      "description": "Auto-generate MCP server stubs from API documentation"},
    {"name": "data_pipelines",      "description": "Build and run ELT data replication pipelines"},
    {"name": "cloud_deploy",        "description": "Deploy services, workers, and cron jobs to the cloud"},
    {"name": "llm_inference",       "description": "Run large language model inference (chat, completion, embeddings)"},
    {"name": "analytics",           "description": "Generate dashboards, reports, and financial analytics"},
    {"name": "knowledge_base",      "description": "Store, index, and semantically retrieve documents"},
]

# Tool -> list of capability names it provides
TOOL_CAPABILITIES: dict[str, list[str]] = {
    "Tavily Search":      ["web_search"],
    "Reka Flash":         ["video_analysis", "audio_transcription", "llm_inference"],
    "Fastino GLiNER":     ["entity_extraction", "mcp_generation"],
    "Neo4j Aura":         ["graph_storage"],
    "Yutori Browser":     ["browser_control", "web_search"],
    "Senso KB":           ["knowledge_base"],
    "ToxMod":             ["audio_transcription"],
    "Airbyte Cloud":      ["data_pipelines"],
    "Render Deploy":      ["cloud_deploy"],
    "AWS Bedrock":        ["llm_inference", "cloud_deploy"],
    "OpenAI API":         ["llm_inference"],
    "Numeric Analytics":  ["analytics"],
}

# HackForge engine definitions
ENGINES: list[dict] = [
    {
        "name": "LinkIntel",
        "description": "URL to tool discovery pipeline — scrapes pages, extracts vendors, compares with harness",
        "url": "",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["search", "code_execution"],
    },
    {
        "name": "VideoIntel",
        "description": "Video to tool extraction — analyses YouTube and Instagram video for tools and methods",
        "url": "",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["vision", "audio"],
    },
    {
        "name": "ReelScout",
        "description": "Instagram reel monitoring — watches for AI tool announcements and demos",
        "url": "",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["browser", "vision"],
    },
    {
        "name": "AuthForge",
        "description": "Agentic auth navigation — signs up for APIs and acquires keys via browser automation",
        "url": "",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["browser"],
    },
    {
        "name": "ToolForge",
        "description": "MCP server generator — reads API docs and produces a complete MCP server package",
        "url": "",
        "api_base_url": "",
        "auth_type": "none",
        "has_free_tier": True,
        "is_integrated": True,
        "mcp_command": "",
        "categories": ["code_execution"],
    },
]

# Engine -> list of vendor names it uses
ENGINE_USES: dict[str, list[str]] = {
    "LinkIntel":   ["Tavily", "Yutori", "Fastino", "Neo4j"],
    "VideoIntel":  ["Reka AI", "Fastino", "Modulate"],
    "ReelScout":   ["Yutori", "Reka AI", "Fastino"],
    "AuthForge":   ["Yutori", "Tavily"],
    "ToolForge":   ["Tavily", "Fastino"],
}

# Engine -> list of engine names it feeds into
ENGINE_FEEDS_INTO: dict[str, list[str]] = {
    "LinkIntel":   ["ToolForge"],
    "VideoIntel":  ["LinkIntel", "ToolForge"],
    "ReelScout":   ["VideoIntel", "LinkIntel"],
    "AuthForge":   ["ToolForge"],
}

# ---------------------------------------------------------------------------
# USES relationship query (Engine Tool -> Vendor)
# ---------------------------------------------------------------------------

MERGE_USES_REL = """
MATCH (engine:Tool {name: $engine_name}), (v:Vendor {name: $vendor_name})
MERGE (engine)-[r:USES]->(v)
SET r.since = coalesce(r.since, date())
RETURN r
"""

# FEEDS_INTO relationship query (Engine -> Engine)
MERGE_FEEDS_INTO_REL = """
MATCH (src:Tool {name: $source_name}), (tgt:Tool {name: $target_name})
MERGE (src)-[r:FEEDS_INTO]->(tgt)
SET r.since = coalesce(r.since, date())
RETURN r
"""


# ---------------------------------------------------------------------------
# Main seeding coroutine
# ---------------------------------------------------------------------------


async def seed() -> None:
    """Connect to Neo4j Aura and seed the knowledge graph."""
    _check_env()

    log.info("Connecting to Neo4j at %s ...", NEO4J_URI)
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    try:
        # Verify connectivity
        await driver.verify_connectivity()
        log.info("Connected successfully.")

        # ------------------------------------------------------------------
        # 1. Schema constraints and indexes
        # ------------------------------------------------------------------
        log.info("Creating schema constraints and indexes (%d statements) ...", len(SCHEMA_INIT_QUERIES))
        async with driver.session() as session:
            for i, query in enumerate(SCHEMA_INIT_QUERIES, 1):
                try:
                    await session.run(query)
                    log.info("  [%d/%d] OK", i, len(SCHEMA_INIT_QUERIES))
                except Exception as exc:
                    # Some constraints may already exist or syntax may differ
                    # between editions — log and continue
                    log.warning("  [%d/%d] SKIPPED: %s", i, len(SCHEMA_INIT_QUERIES), exc)

        # ------------------------------------------------------------------
        # 2. Vendor nodes
        # ------------------------------------------------------------------
        log.info("Upserting %d Vendor nodes ...", len(VENDORS))
        async with driver.session() as session:
            for v in VENDORS:
                await session.run(UPSERT_VENDOR, **v)
                log.info("  Vendor: %s", v["name"])

        # ------------------------------------------------------------------
        # 3. Tool nodes (vendor products)
        # ------------------------------------------------------------------
        log.info("Upserting %d Tool nodes ...", len(TOOLS))
        async with driver.session() as session:
            for t in TOOLS:
                params = {k: v for k, v in t.items() if k != "vendor"}
                await session.run(UPSERT_TOOL, **params)
                log.info("  Tool: %s", t["name"])

        # ------------------------------------------------------------------
        # 4. OFFERS relationships (Vendor -> Tool)
        # ------------------------------------------------------------------
        log.info("Creating OFFERS relationships ...")
        async with driver.session() as session:
            for t in TOOLS:
                await session.run(
                    CREATE_OFFERS_REL,
                    vendor_name=t["vendor"],
                    tool_name=t["name"],
                )
                log.info("  %s -[OFFERS]-> %s", t["vendor"], t["name"])

        # ------------------------------------------------------------------
        # 5. Capability nodes
        # ------------------------------------------------------------------
        log.info("Upserting %d Capability nodes ...", len(CAPABILITIES))
        async with driver.session() as session:
            for c in CAPABILITIES:
                await session.run(UPSERT_CAPABILITY, **c)
                log.info("  Capability: %s", c["name"])

        # ------------------------------------------------------------------
        # 6. PROVIDES relationships (Tool -> Capability)
        # ------------------------------------------------------------------
        log.info("Creating PROVIDES relationships ...")
        async with driver.session() as session:
            for tool_name, caps in TOOL_CAPABILITIES.items():
                for cap_name in caps:
                    await session.run(
                        CREATE_PROVIDES_REL,
                        tool_name=tool_name,
                        capability_name=cap_name,
                        notes="",
                    )
                    log.info("  %s -[PROVIDES]-> %s", tool_name, cap_name)

        # ------------------------------------------------------------------
        # 7. Engine Tool nodes
        # ------------------------------------------------------------------
        log.info("Upserting %d Engine nodes (as Tool) ...", len(ENGINES))
        async with driver.session() as session:
            for e in ENGINES:
                await session.run(UPSERT_TOOL, **e)
                log.info("  Engine: %s", e["name"])

        # ------------------------------------------------------------------
        # 8. USES relationships (Engine -> Vendor)
        # ------------------------------------------------------------------
        log.info("Creating USES relationships ...")
        async with driver.session() as session:
            for engine_name, vendors in ENGINE_USES.items():
                for vendor_name in vendors:
                    await session.run(
                        MERGE_USES_REL,
                        engine_name=engine_name,
                        vendor_name=vendor_name,
                    )
                    log.info("  %s -[USES]-> %s", engine_name, vendor_name)

        # ------------------------------------------------------------------
        # 9. FEEDS_INTO relationships (Engine -> Engine)
        # ------------------------------------------------------------------
        log.info("Creating FEEDS_INTO relationships ...")
        async with driver.session() as session:
            for source, targets in ENGINE_FEEDS_INTO.items():
                for target in targets:
                    await session.run(
                        MERGE_FEEDS_INTO_REL,
                        source_name=source,
                        target_name=target,
                    )
                    log.info("  %s -[FEEDS_INTO]-> %s", source, target)

        # ------------------------------------------------------------------
        # 10. Verification
        # ------------------------------------------------------------------
        log.info("Verifying graph contents ...")
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n)
                WITH labels(n) AS lbls, count(*) AS cnt
                UNWIND lbls AS label
                RETURN label, sum(cnt) AS node_count
                ORDER BY node_count DESC
                """
            )
            records = await result.data()
            log.info("--- Node counts ---")
            total_nodes = 0
            for r in records:
                log.info("  %-15s %d", r["label"], r["node_count"])
                total_nodes += r["node_count"]
            log.info("  %-15s %d", "TOTAL", total_nodes)

            result = await session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS rel_type, count(r) AS rel_count
                ORDER BY rel_count DESC
                """
            )
            records = await result.data()
            log.info("--- Relationship counts ---")
            total_rels = 0
            for r in records:
                log.info("  %-20s %d", r["rel_type"], r["rel_count"])
                total_rels += r["rel_count"]
            log.info("  %-20s %d", "TOTAL", total_rels)

        log.info("Seed complete. %d nodes, %d relationships.", total_nodes, total_rels)

    except neo4j.exceptions.ServiceUnavailable as exc:
        log.error("Cannot reach Neo4j at %s: %s", NEO4J_URI, exc)
        sys.exit(1)
    except neo4j.exceptions.AuthError as exc:
        log.error("Authentication failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await driver.close()
        log.info("Driver closed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(seed())
