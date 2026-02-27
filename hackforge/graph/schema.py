"""Neo4j knowledge graph schema for tool/vendor/capability tracking.

This module defines the Pydantic node models, relationship type registry,
and the Cypher DDL statements used to initialise constraints and indexes
in the HackForge Neo4j instance.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Node models
# ---------------------------------------------------------------------------


class ToolNode(BaseModel):
    """Represents a discovered or integrated tool/service in the graph."""

    name: str
    description: str = ""
    url: str = ""
    api_base_url: str = ""
    auth_type: str = ""  # "api_key" | "oauth2" | "bearer" | "none"
    has_free_tier: bool = False
    is_integrated: bool = False  # True when already wired into the harness
    mcp_command: str = ""  # e.g. "uvx mcp-server-brave-search"
    categories: list[str] = Field(default_factory=list)
    # e.g. ["search", "browser", "llm", "database", "vector_db", "audio",
    #        "vision", "code_execution", "storage", "messaging"]

    @field_validator("auth_type")
    @classmethod
    def _valid_auth_type(cls, v: str) -> str:
        allowed = {"api_key", "oauth2", "bearer", "none", ""}
        if v not in allowed:
            raise ValueError(f"auth_type must be one of {allowed}, got {v!r}")
        return v

    def to_cypher_params(self) -> dict[str, Any]:
        """Return a flat dict suitable for use as Cypher query parameters."""
        return self.model_dump()


class VendorNode(BaseModel):
    """Represents a company or organisation that offers tools."""

    name: str
    url: str = ""
    description: str = ""
    hackathon_sponsor: bool = False

    def to_cypher_params(self) -> dict[str, Any]:
        return self.model_dump()


class CapabilityNode(BaseModel):
    """An abstract capability that one or more tools can provide.

    Examples: ``"web_search"``, ``"browser_automation"``,
    ``"video_analysis"``, ``"text_to_speech"``, ``"vector_similarity_search"``.
    """

    name: str  # snake_case canonical identifier
    description: str = ""

    def to_cypher_params(self) -> dict[str, Any]:
        return self.model_dump()


class APIEndpointNode(BaseModel):
    """A specific REST endpoint exposed by a tool."""

    method: str  # GET | POST | PUT | PATCH | DELETE
    path: str  # e.g. "/v1/search"
    description: str = ""
    requires_auth: bool = True

    @field_validator("method")
    @classmethod
    def _upper_method(cls, v: str) -> str:
        return v.upper()

    def to_cypher_params(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Relationship type registry
# ---------------------------------------------------------------------------


RELATIONSHIPS: dict[str, str] = {
    # Core supply-chain relationships
    "OFFERS": "Vendor → Tool: the vendor offers/publishes this tool",
    "PROVIDES": "Tool → Capability: the tool exposes this capability",
    # Competitive / substitution graph
    "REPLACES": "Tool → Tool: this tool can fully replace another",
    "COMPETES_WITH": "Tool → Tool: tools target the same use-case but differ",
    # Dependency / integration graph
    "REQUIRES": "Tool → Tool|Capability: a hard runtime dependency",
    "INTEGRATES_WITH": "Tool → Tool: optional/optional complementary integration",
    # Technical structure
    "HAS_ENDPOINT": "Tool → APIEndpoint: the tool exposes this REST endpoint",
    # Provenance
    "DISCOVERED_FROM": "Tool → URL source: where the tool was first found",
}

# Typed tuple for static analysis / documentation generation
RELATIONSHIP_TYPES = tuple(RELATIONSHIPS.keys())


# ---------------------------------------------------------------------------
# Schema initialisation DDL
# ---------------------------------------------------------------------------

SCHEMA_INIT_QUERIES: list[str] = [
    # --- Uniqueness constraints ---
    "CREATE CONSTRAINT tool_name IF NOT EXISTS "
    "FOR (t:Tool) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT vendor_name IF NOT EXISTS "
    "FOR (v:Vendor) REQUIRE v.name IS UNIQUE",
    "CREATE CONSTRAINT capability_name IF NOT EXISTS "
    "FOR (c:Capability) REQUIRE c.name IS UNIQUE",
    # Composite uniqueness for endpoints (method + path must be unique per tool)
    # Enforced via application logic; a full-text search index covers lookup.
    # --- Property indexes ---
    "CREATE INDEX tool_category IF NOT EXISTS "
    "FOR (t:Tool) ON (t.categories)",
    "CREATE INDEX tool_integrated IF NOT EXISTS "
    "FOR (t:Tool) ON (t.is_integrated)",
    "CREATE INDEX tool_auth_type IF NOT EXISTS "
    "FOR (t:Tool) ON (t.auth_type)",
    "CREATE INDEX tool_free_tier IF NOT EXISTS "
    "FOR (t:Tool) ON (t.has_free_tier)",
    "CREATE INDEX vendor_sponsor IF NOT EXISTS "
    "FOR (v:Vendor) ON (v.hackathon_sponsor)",
    # --- Full-text search indexes ---
    "CREATE FULLTEXT INDEX tool_fulltext IF NOT EXISTS "
    "FOR (t:Tool) ON EACH [t.name, t.description]",
    "CREATE FULLTEXT INDEX capability_fulltext IF NOT EXISTS "
    "FOR (c:Capability) ON EACH [c.name, c.description]",
]


# ---------------------------------------------------------------------------
# Schema metadata helpers
# ---------------------------------------------------------------------------


def node_label_for(model: type[BaseModel]) -> str:
    """Return the Neo4j node label string for a given Pydantic model class.

    >>> node_label_for(ToolNode)
    'Tool'
    """
    name = model.__name__
    if name.endswith("Node"):
        return name[:-4]  # strip trailing "Node"
    return name


NODE_LABELS: dict[str, type[BaseModel]] = {
    node_label_for(ToolNode): ToolNode,
    node_label_for(VendorNode): VendorNode,
    node_label_for(CapabilityNode): CapabilityNode,
    node_label_for(APIEndpointNode): APIEndpointNode,
}
