"""Async-compatible Neo4j client for HackForge knowledge graph operations.

Uses the official ``neo4j`` Python driver (which is sync-only) but wraps
blocking calls in ``asyncio.to_thread`` so it can be used from async code
without blocking the event loop.

The graph schema revolves around ``Tool`` and ``Vendor`` nodes connected by
typed relationships such as PROVIDES, OFFERS, REPLACES, REQUIRES,
INTEGRATES_WITH, and COMPETES_WITH.

Reference: https://neo4j.com/docs/python-manual/current/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
    from neo4j.exceptions import AuthError, ServiceUnavailable, Neo4jError
    _NEO4J_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NEO4J_AVAILABLE = False
    AsyncGraphDatabase = None  # type: ignore[assignment]
    AsyncDriver = None  # type: ignore[assignment]

    class AuthError(Exception): ...  # type: ignore[no-redef]
    class ServiceUnavailable(Exception): ...  # type: ignore[no-redef]
    class Neo4jError(Exception): ...  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class Neo4jClientError(Exception):
    """Base error for all Neo4j client failures."""


class Neo4jConnectionError(Neo4jClientError):
    """Raised when a connection to Neo4j cannot be established."""


class Neo4jQueryError(Neo4jClientError):
    """Raised when a Cypher query fails."""


class Neo4jAuthenticationError(Neo4jClientError):
    """Raised when Neo4j rejects the supplied credentials."""


# ---------------------------------------------------------------------------
# Relationship types (enumerated for safety)
# ---------------------------------------------------------------------------

VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "PROVIDES",
        "OFFERS",
        "REPLACES",
        "REQUIRES",
        "INTEGRATES_WITH",
        "COMPETES_WITH",
    }
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ToolNode:
    """A ``Tool`` node as stored in the knowledge graph."""

    name: str
    description: str = ""
    url: str = ""
    capabilities: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class VendorNode:
    """A ``Vendor`` node as stored in the knowledge graph."""

    name: str
    url: str = ""
    tools: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphQueryResult:
    """Raw result rows from a Cypher query."""

    records: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class Neo4jClient:
    """Async-compatible Neo4j knowledge-graph client.

    Wraps the native ``neo4j`` async driver.  All graph-write operations use
    ``MERGE`` semantics so they are idempotent (safe to call multiple times).

    Usage::

        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="secret",
        )
        await client.connect()
        await client.add_tool(
            name="LangChain",
            description="LLM orchestration framework",
            url="https://langchain.com",
            capabilities=["chain", "agent", "retrieval"],
        )
        await client.close()
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        if not _NEO4J_AVAILABLE:
            raise ImportError(
                "The 'neo4j' package is required.  Install it with: pip install neo4j"
            )
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver: Any = None  # AsyncDriver when connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open a connection to Neo4j and verify connectivity.

        Raises:
            Neo4jConnectionError: If the server is unreachable.
            Neo4jAuthenticationError: If the credentials are rejected.
        """
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            await self._driver.verify_connectivity()
        except AuthError as exc:
            raise Neo4jAuthenticationError(
                f"Neo4j authentication failed for user '{self._user}': {exc}"
            ) from exc
        except ServiceUnavailable as exc:
            raise Neo4jConnectionError(
                f"Cannot connect to Neo4j at '{self._uri}': {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the driver and release all connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> Neo4jClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_connected(self) -> None:
        if self._driver is None:
            raise Neo4jConnectionError(
                "Not connected.  Call await client.connect() first."
            )

    async def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
    ) -> GraphQueryResult:
        """Execute an arbitrary Cypher query and return all result rows.

        Args:
            cypher: The Cypher query string.
            params: Optional dict of query parameters (use ``$name`` syntax).

        Returns:
            A :class:`GraphQueryResult` containing one dict per result row.

        Raises:
            Neo4jQueryError: If the Cypher statement fails.
            Neo4jConnectionError: If the client is not connected.
        """
        self._assert_connected()
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(cypher, parameters=params or {})
                records = [dict(record) async for record in result]
                summary = await result.consume()
                return GraphQueryResult(
                    records=records,
                    summary={
                        "counters": dict(summary.counters) if summary.counters else {},
                        "query_type": summary.query_type,
                    },
                )
        except Neo4jError as exc:
            raise Neo4jQueryError(f"Cypher query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Graph-write operations
    # ------------------------------------------------------------------

    async def add_tool(
        self,
        name: str,
        description: str,
        url: str,
        capabilities: list[str] | None = None,
        extra_properties: dict[str, Any] | None = None,
    ) -> GraphQueryResult:
        """Upsert a ``Tool`` node in the knowledge graph.

        Uses ``MERGE`` on the ``name`` property so duplicate calls are safe.

        Args:
            name: Canonical tool name (used as the merge key).
            description: Short human-readable description.
            url: Primary URL (homepage or documentation).
            capabilities: List of capability tags (e.g. ``["search", "embed"]``).
            extra_properties: Any additional key-value properties to store.

        Returns:
            The :class:`GraphQueryResult` from the write transaction.
        """
        props: dict[str, Any] = {
            "description": description,
            "url": url,
            "capabilities": capabilities or [],
            **(extra_properties or {}),
        }
        cypher = (
            "MERGE (t:Tool {name: $name}) "
            "SET t += $props "
            "RETURN t"
        )
        return await self.query(cypher, {"name": name, "props": props})

    async def add_vendor(
        self,
        name: str,
        url: str,
        tools: list[str] | None = None,
        extra_properties: dict[str, Any] | None = None,
    ) -> GraphQueryResult:
        """Upsert a ``Vendor`` node and link it to its tools via PROVIDES.

        Args:
            name: Canonical vendor name (merge key).
            url: Vendor website URL.
            tools: Names of tools the vendor provides.  Each tool node is
                created with ``MERGE`` if it does not already exist.
            extra_properties: Additional properties to store on the vendor node.

        Returns:
            The :class:`GraphQueryResult` from the final write.
        """
        vendor_props: dict[str, Any] = {"url": url, **(extra_properties or {})}
        result = await self.query(
            "MERGE (v:Vendor {name: $name}) SET v += $props RETURN v",
            {"name": name, "props": vendor_props},
        )
        for tool_name in tools or []:
            await self.query(
                (
                    "MERGE (v:Vendor {name: $vendor}) "
                    "MERGE (t:Tool {name: $tool}) "
                    "MERGE (v)-[:PROVIDES]->(t)"
                ),
                {"vendor": name, "tool": tool_name},
            )
        return result

    async def add_relationship(
        self,
        from_name: str,
        rel_type: str,
        to_name: str,
        properties: dict[str, Any] | None = None,
    ) -> GraphQueryResult:
        """Create or update a typed relationship between two nodes.

        Nodes are looked up by name regardless of label (``Tool`` or ``Vendor``).

        Args:
            from_name: Name of the source node.
            rel_type: Relationship type — must be one of ``PROVIDES``,
                ``OFFERS``, ``REPLACES``, ``REQUIRES``, ``INTEGRATES_WITH``,
                or ``COMPETES_WITH``.
            to_name: Name of the target node.
            properties: Optional properties to set on the relationship.

        Raises:
            ValueError: If *rel_type* is not a recognised relationship type.

        Returns:
            The :class:`GraphQueryResult` from the write transaction.
        """
        if rel_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Unknown relationship type '{rel_type}'. "
                f"Valid types: {sorted(VALID_RELATIONSHIP_TYPES)}"
            )
        # Node labels are not enforced here — MERGE on name across all labels.
        cypher = (
            f"MATCH (a {{name: $from_name}}) "
            f"MATCH (b {{name: $to_name}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props "
            f"RETURN a, r, b"
        )
        return await self.query(
            cypher,
            {
                "from_name": from_name,
                "to_name": to_name,
                "props": properties or {},
            },
        )

    # ------------------------------------------------------------------
    # Graph-read operations
    # ------------------------------------------------------------------

    async def find_similar_tools(self, name: str, limit: int = 10) -> GraphQueryResult:
        """Find tools that share capabilities, vendor, or relationships with *name*.

        The query uses a multi-hop traversal to discover tools that:
        - Are provided by the same vendor.
        - Share ``INTEGRATES_WITH`` edges.
        - Are marked as ``COMPETES_WITH`` the target tool.

        Args:
            name: Canonical name of the reference tool.
            limit: Maximum number of similar tools to return.

        Returns:
            A :class:`GraphQueryResult` where each record contains
            ``similar_tool`` (name) and ``relationship`` (how it is related).
        """
        cypher = """
            MATCH (t:Tool {name: $name})
            OPTIONAL MATCH (t)<-[:PROVIDES]-(v:Vendor)-[:PROVIDES]->(similar:Tool)
            WHERE similar.name <> $name
            WITH similar, 'same_vendor' AS relationship
            UNION
            MATCH (t:Tool {name: $name})-[r:INTEGRATES_WITH|COMPETES_WITH|REPLACES]-(similar:Tool)
            WHERE similar.name <> $name
            WITH similar, type(r) AS relationship
            RETURN DISTINCT similar.name AS similar_tool, relationship
            LIMIT $limit
        """
        return await self.query(cypher, {"name": name, "limit": limit})

    async def get_tool_graph(self, name: str, depth: int = 2) -> GraphQueryResult:
        """Return all nodes and relationships reachable from *name* within *depth* hops.

        Args:
            name: Canonical name of the starting ``Tool`` or ``Vendor`` node.
            depth: Maximum traversal depth.

        Returns:
            A :class:`GraphQueryResult` where each record contains
            ``node`` (name + labels) and ``relationship`` (type, if any).
        """
        cypher = f"""
            MATCH path = (start {{name: $name}})-[*0..{depth}]-(connected)
            WITH connected, relationships(path) AS rels
            UNWIND CASE WHEN size(rels) = 0 THEN [null] ELSE rels END AS rel
            RETURN DISTINCT
                connected.name AS node,
                labels(connected) AS labels,
                type(rel) AS relationship
        """
        return await self.query(cypher, {"name": name})
