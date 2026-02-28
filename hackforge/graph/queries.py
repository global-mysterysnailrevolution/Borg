"""Cypher query templates for HackForge knowledge graph operations.

All queries are written as string constants and are parameterised using
Neo4j's ``$param`` syntax.  Pass parameters as a plain Python dict to
``neo4j.AsyncSession.run(QUERY, **params)`` or ``session.run(QUERY, params)``.

Query naming convention
-----------------------
UPSERT_*       — MERGE-based create-or-update for nodes
CREATE_*_REL   — MERGE-based create-or-update for relationships
LOG_*          — Create event/audit nodes for traceability
FIND_*         — Read queries that return matched subgraphs
GET_*          — Read queries that fetch full node/subgraph data
SEARCH_*       — Read queries that perform free-text or property search
DELETE_*       — Delete operations (use with caution)
"""

from __future__ import annotations

# ===========================================================================
# UPSERT QUERIES  (idempotent node writes)
# ===========================================================================

UPSERT_TOOL = """
MERGE (t:Tool {name: $name})
SET t.description    = $description,
    t.url            = $url,
    t.api_base_url   = $api_base_url,
    t.auth_type      = $auth_type,
    t.has_free_tier  = $has_free_tier,
    t.is_integrated  = $is_integrated,
    t.mcp_command    = $mcp_command,
    t.categories     = $categories,
    t.updated_at     = datetime()
RETURN t
"""
"""Upsert a Tool node.

Required params: name, description, url, api_base_url, auth_type,
has_free_tier, is_integrated, mcp_command, categories.
"""

UPSERT_VENDOR = """
MERGE (v:Vendor {name: $name})
SET v.url                = $url,
    v.description        = $description,
    v.hackathon_sponsor  = $hackathon_sponsor,
    v.updated_at         = datetime()
RETURN v
"""
"""Upsert a Vendor node.

Required params: name, url, description, hackathon_sponsor.
"""

UPSERT_CAPABILITY = """
MERGE (c:Capability {name: $name})
SET c.description = $description,
    c.updated_at  = datetime()
RETURN c
"""
"""Upsert a Capability node.

Required params: name, description.
"""

UPSERT_ENDPOINT = """
MERGE (e:APIEndpoint {method: $method, path: $path})
SET e.description   = $description,
    e.requires_auth = $requires_auth,
    e.updated_at    = datetime()
RETURN e
"""
"""Upsert an APIEndpoint node.

Required params: method, path, description, requires_auth.
"""

# ===========================================================================
# RELATIONSHIP CREATION QUERIES
# ===========================================================================

CREATE_OFFERS_REL = """
MATCH (v:Vendor {name: $vendor_name}), (t:Tool {name: $tool_name})
MERGE (v)-[r:OFFERS]->(t)
SET r.since = coalesce(r.since, date())
RETURN r
"""
"""Create or verify a VENDOR -[OFFERS]-> TOOL relationship.

Required params: vendor_name, tool_name.
"""

CREATE_PROVIDES_REL = """
MATCH (t:Tool {name: $tool_name}), (c:Capability {name: $capability_name})
MERGE (t)-[r:PROVIDES]->(c)
SET r.since = coalesce(r.since, date()),
    r.notes = $notes
RETURN r
"""
"""Create or verify a TOOL -[PROVIDES]-> CAPABILITY relationship.

Required params: tool_name, capability_name, notes (may be empty string).
"""

CREATE_REPLACES_REL = """
MATCH (t1:Tool {name: $tool_name}), (t2:Tool {name: $replaced_tool_name})
MERGE (t1)-[r:REPLACES]->(t2)
SET r.reason = $reason,
    r.since  = coalesce(r.since, date())
RETURN r
"""
"""Create or verify a TOOL -[REPLACES]-> TOOL relationship.

Required params: tool_name, replaced_tool_name, reason.
"""

CREATE_COMPETES_WITH_REL = """
MATCH (t1:Tool {name: $tool_name_a}), (t2:Tool {name: $tool_name_b})
MERGE (t1)-[r:COMPETES_WITH]->(t2)
SET r.notes = $notes,
    r.since  = coalesce(r.since, date())
RETURN r
"""
"""Create or verify a TOOL -[COMPETES_WITH]-> TOOL relationship.

Required params: tool_name_a, tool_name_b, notes.
"""

CREATE_INTEGRATES_WITH_REL = """
MATCH (t1:Tool {name: $tool_name}), (t2:Tool {name: $partner_tool_name})
MERGE (t1)-[r:INTEGRATES_WITH]->(t2)
SET r.integration_type = $integration_type,
    r.since             = coalesce(r.since, date())
RETURN r
"""
"""Create or verify a TOOL -[INTEGRATES_WITH]-> TOOL relationship.

Required params: tool_name, partner_tool_name, integration_type.
"""

CREATE_HAS_ENDPOINT_REL = """
MATCH (t:Tool {name: $tool_name})
MATCH (e:APIEndpoint {method: $method, path: $path})
MERGE (t)-[r:HAS_ENDPOINT]->(e)
RETURN r
"""
"""Link a Tool to one of its APIEndpoint nodes.

Required params: tool_name, method, path.
"""

CREATE_REQUIRES_REL = """
MATCH (t:Tool {name: $tool_name}), (dep:Tool {name: $dependency_name})
MERGE (t)-[r:REQUIRES]->(dep)
SET r.reason = $reason
RETURN r
"""
"""Create or verify a TOOL -[REQUIRES]-> TOOL dependency edge.

Required params: tool_name, dependency_name, reason.
"""

CREATE_DISCOVERED_FROM_REL = """
MATCH (t:Tool {name: $tool_name})
MERGE (src:Source {url: $source_url})
MERGE (t)-[r:DISCOVERED_FROM]->(src)
SET r.discovered_at = coalesce(r.discovered_at, datetime())
RETURN r
"""
"""Record the URL from which a tool was discovered.

Required params: tool_name, source_url.
"""

# ===========================================================================
# DISCOVERY / INTEGRATION / AUDIT QUERIES
# ===========================================================================

LOG_DISCOVERY = """
CREATE (d:DiscoveryEvent {
    url:          $url,
    timestamp:    datetime(),
    source_type:  $source_type,
    engine_used:  $engine_used,
    entity_count: $entity_count
})
WITH d
UNWIND $tool_names AS tool_name
MATCH (t:Tool {name: tool_name})
MERGE (t)-[:DISCOVERED_FROM]->(d)
RETURN d, collect(t.name) AS linked_tools
"""
"""Create a DiscoveryEvent node and link it to all tools found in this run.

Required params: url, source_type, engine_used, entity_count, tool_names (list[str]).
Returns: the DiscoveryEvent node and the list of linked tool names.
"""

LOG_INTEGRATION = """
MATCH (t:Tool {name: $tool_name})
CREATE (i:IntegrationEvent {
    timestamp:        datetime(),
    method:           $method,
    status:           $status,
    api_key_obtained: $api_key_obtained
})
MERGE (t)-[:INTEGRATED_VIA]->(i)
RETURN t, i
"""
"""Create an IntegrationEvent for a specific tool.

Required params: tool_name, method, status, api_key_obtained.
Returns: the Tool and IntegrationEvent nodes.
"""

CREATE_AUDIT_LOG = """
CREATE (a:AuditLog {
    timestamp: datetime(),
    action:    $action,
    actor:     $actor,
    details:   $details
})
WITH a
OPTIONAL MATCH (d:DiscoveryEvent)
  WHERE id(d) = $event_id AND $event_label = 'DiscoveryEvent'
OPTIONAL MATCH (i:IntegrationEvent)
  WHERE id(i) = $event_id AND $event_label = 'IntegrationEvent'
WITH a, coalesce(d, i) AS source_event
WHERE source_event IS NOT NULL
MERGE (source_event)-[:LOGGED]->(a)
RETURN a, source_event
"""
"""Create an AuditLog entry, optionally linked to a DiscoveryEvent or IntegrationEvent.

Required params: action, actor, details, event_id (int, Neo4j internal id or -1),
                 event_label ('DiscoveryEvent' | 'IntegrationEvent' | '').
Returns: the AuditLog node and its linked source event (if any).
"""

CREATE_AUDIT_LOG_SIMPLE = """
CREATE (a:AuditLog {
    timestamp: datetime(),
    action:    $action,
    actor:     $actor,
    details:   $details
})
RETURN a
"""
"""Create a standalone AuditLog entry with no linked event.

Required params: action, actor, details.
Returns: the AuditLog node.
"""

# ===========================================================================
# READ QUERIES
# ===========================================================================

FIND_SIMILAR_TOOLS = """
MATCH (t:Tool {name: $tool_name})-[:PROVIDES]->(c:Capability)
WITH t, collect(c.name) AS target_caps
MATCH (other:Tool)-[:PROVIDES]->(c2:Capability)
WHERE other.name <> t.name
  AND c2.name IN target_caps
WITH other,
     count(c2)                    AS shared_caps,
     size(target_caps)            AS total_caps,
     toFloat(count(c2)) / size(target_caps) AS overlap_ratio
WHERE shared_caps >= $min_shared
RETURN other.name          AS tool,
       other.description   AS description,
       shared_caps,
       overlap_ratio
ORDER BY overlap_ratio DESC, shared_caps DESC
LIMIT $limit
"""
"""Find tools that share the most capability overlap with a given tool.

Required params: tool_name, min_shared (int), limit (int).
Returns: tool, description, shared_caps, overlap_ratio.
"""

FIND_ALTERNATIVES = """
MATCH (c:Capability {name: $capability_name})<-[:PROVIDES]-(t:Tool)
WHERE t.is_integrated = $prefer_integrated OR $prefer_integrated IS NULL
RETURN t.name          AS tool,
       t.description   AS description,
       t.has_free_tier AS free_tier,
       t.auth_type     AS auth_type,
       t.mcp_command   AS mcp_command,
       t.is_integrated AS integrated
ORDER BY t.is_integrated DESC, t.has_free_tier DESC
LIMIT $limit
"""
"""Find all tools that provide a given capability.

Required params: capability_name, prefer_integrated (bool or null), limit (int).
Returns columns: tool, description, free_tier, auth_type, mcp_command, integrated.
"""

GET_TOOL_SUBGRAPH = """
MATCH path = (t:Tool {name: $tool_name})-[*1..2]-(related)
RETURN path
LIMIT $max_paths
"""
"""Return all nodes and relationships within 2 hops of the named tool.

Required params: tool_name, max_paths (int, suggest 200).
Returns: Neo4j Path objects.
"""

GET_UNINTEGRATED_TOOLS = """
MATCH (t:Tool)
WHERE t.is_integrated = false
OPTIONAL MATCH (v:Vendor)-[:OFFERS]->(t)
OPTIONAL MATCH (t)-[:PROVIDES]->(c:Capability)
RETURN t.name          AS tool,
       t.description   AS description,
       t.url           AS url,
       t.auth_type     AS auth_type,
       t.has_free_tier AS free_tier,
       t.mcp_command   AS mcp_command,
       collect(DISTINCT v.name) AS vendors,
       collect(DISTINCT c.name) AS capabilities
ORDER BY size(collect(DISTINCT c.name)) DESC, t.name
"""
"""Return all discovered tools not yet integrated into the harness.

No required params.
Returns: tool, description, url, auth_type, free_tier, mcp_command, vendors, capabilities.
"""

GET_VENDOR_TOOLS = """
MATCH (v:Vendor {name: $vendor_name})-[:OFFERS]->(t:Tool)
OPTIONAL MATCH (t)-[:PROVIDES]->(c:Capability)
RETURN t.name          AS tool,
       t.description   AS description,
       t.url           AS url,
       t.has_free_tier AS free_tier,
       t.is_integrated AS integrated,
       t.mcp_command   AS mcp_command,
       collect(DISTINCT c.name) AS capabilities
ORDER BY t.is_integrated DESC, t.name
"""
"""Return all tools offered by a specific vendor.

Required params: vendor_name.
Returns: tool, description, url, free_tier, integrated, mcp_command, capabilities.
"""

SEARCH_BY_CAPABILITY = """
MATCH (c:Capability)
WHERE c.name CONTAINS $keyword OR c.description CONTAINS $keyword
MATCH (t:Tool)-[:PROVIDES]->(c)
OPTIONAL MATCH (v:Vendor)-[:OFFERS]->(t)
RETURN c.name          AS capability,
       t.name          AS tool,
       t.description   AS description,
       t.has_free_tier AS free_tier,
       t.is_integrated AS integrated,
       t.auth_type     AS auth_type,
       v.name          AS vendor
ORDER BY t.is_integrated DESC, t.has_free_tier DESC, t.name
"""
"""Search for tools by a partial capability keyword.

Required params: keyword (case-sensitive substring).
Returns: capability, tool, description, free_tier, integrated, auth_type, vendor.
"""

SEARCH_TOOLS_FULLTEXT = """
CALL db.index.fulltext.queryNodes('tool_fulltext', $query)
YIELD node AS t, score
OPTIONAL MATCH (v:Vendor)-[:OFFERS]->(t)
OPTIONAL MATCH (t)-[:PROVIDES]->(c:Capability)
RETURN t.name          AS tool,
       t.description   AS description,
       t.url           AS url,
       score,
       collect(DISTINCT v.name) AS vendors,
       collect(DISTINCT c.name) AS capabilities
ORDER BY score DESC
LIMIT $limit
"""
"""Full-text search across tool name and description fields.

Required params: query (Lucene query string), limit (int).
Returns: tool, description, url, score, vendors, capabilities.
"""

GET_HACKATHON_SPONSOR_TOOLS = """
MATCH (v:Vendor {hackathon_sponsor: true})-[:OFFERS]->(t:Tool)
OPTIONAL MATCH (t)-[:PROVIDES]->(c:Capability)
RETURN v.name          AS sponsor,
       t.name          AS tool,
       t.description   AS description,
       t.has_free_tier AS free_tier,
       t.is_integrated AS integrated,
       t.mcp_command   AS mcp_command,
       collect(DISTINCT c.name) AS capabilities
ORDER BY v.name, t.name
"""
"""Return all tools offered by hackathon sponsors.

No required params.
Returns: sponsor, tool, description, free_tier, integrated, mcp_command, capabilities.
"""

GET_MCP_READY_TOOLS = """
MATCH (t:Tool)
WHERE t.mcp_command <> ''
OPTIONAL MATCH (v:Vendor)-[:OFFERS]->(t)
OPTIONAL MATCH (t)-[:PROVIDES]->(c:Capability)
RETURN t.name          AS tool,
       t.mcp_command   AS mcp_command,
       t.description   AS description,
       t.is_integrated AS integrated,
       collect(DISTINCT v.name) AS vendors,
       collect(DISTINCT c.name) AS capabilities
ORDER BY t.is_integrated DESC, t.name
"""
"""Return all tools that have a known MCP uvx command.

No required params.
Returns: tool, mcp_command, description, integrated, vendors, capabilities.
"""

FULL_TOOL_REPORT = """
MATCH (t:Tool {name: $tool_name})
OPTIONAL MATCH (v:Vendor)-[:OFFERS]->(t)
OPTIONAL MATCH (t)-[:PROVIDES]->(cap:Capability)
OPTIONAL MATCH (t)-[:HAS_ENDPOINT]->(ep:APIEndpoint)
OPTIONAL MATCH (t)-[:REPLACES]->(replaced:Tool)
OPTIONAL MATCH (t)-[:COMPETES_WITH]->(competitor:Tool)
OPTIONAL MATCH (t)-[:INTEGRATES_WITH]->(partner:Tool)
OPTIONAL MATCH (t)-[:DISCOVERED_FROM]->(src:Source)
RETURN t                                     AS tool,
       collect(DISTINCT v.name)              AS vendors,
       collect(DISTINCT cap.name)            AS capabilities,
       collect(DISTINCT {method: ep.method, path: ep.path,
                         description: ep.description}) AS endpoints,
       collect(DISTINCT replaced.name)       AS replaces,
       collect(DISTINCT competitor.name)     AS competes_with,
       collect(DISTINCT partner.name)        AS integrates_with,
       collect(DISTINCT src.url)             AS discovered_from
"""
"""Comprehensive single-tool report joining all related nodes.

Required params: tool_name.
Returns: full tool node + all relationship collections.
"""

GET_CAPABILITY_GRAPH = """
MATCH (c:Capability)<-[:PROVIDES]-(t:Tool)
WITH c, collect({name: t.name, integrated: t.is_integrated,
                 free: t.has_free_tier}) AS tools
RETURN c.name        AS capability,
       c.description AS description,
       size(tools)   AS tool_count,
       tools
ORDER BY tool_count DESC
"""
"""Return all capabilities with the list of tools that provide them.

No required params.
Returns: capability, description, tool_count, tools (list of maps).
"""

GET_INTEGRATION_COVERAGE = """
MATCH (t:Tool)
WITH count(t) AS total
MATCH (t2:Tool {is_integrated: true})
WITH total, count(t2) AS integrated
RETURN total,
       integrated,
       total - integrated       AS unintegrated,
       round(100.0 * integrated / total, 1) AS coverage_pct
"""
"""Return a summary of how many tools are integrated vs still pending.

No required params.
Returns: total, integrated, unintegrated, coverage_pct.
"""

GET_TOOL_HISTORY = """
MATCH (t:Tool {name: $tool_name})
OPTIONAL MATCH (t)-[:DISCOVERED_FROM]->(d:DiscoveryEvent)
OPTIONAL MATCH (t)-[:INTEGRATED_VIA]->(i:IntegrationEvent)
OPTIONAL MATCH (d)-[:LOGGED]->(da:AuditLog)
OPTIONAL MATCH (i)-[:LOGGED]->(ia:AuditLog)
RETURN t.name                                      AS tool,
       collect(DISTINCT {
           type: 'discovery',
           url: d.url,
           timestamp: d.timestamp,
           source_type: d.source_type,
           engine_used: d.engine_used,
           entity_count: d.entity_count
       })                                           AS discoveries,
       collect(DISTINCT {
           type: 'integration',
           timestamp: i.timestamp,
           method: i.method,
           status: i.status,
           api_key_obtained: i.api_key_obtained
       })                                           AS integrations,
       collect(DISTINCT {
           timestamp: da.timestamp,
           action: da.action,
           actor: da.actor,
           details: da.details
       }) + collect(DISTINCT {
           timestamp: ia.timestamp,
           action: ia.action,
           actor: ia.actor,
           details: ia.details
       })                                           AS audit_entries
ORDER BY t.name
"""
"""Get the full discovery + integration timeline for a tool.

Required params: tool_name.
Returns: tool name, list of discovery events, integration events, and audit entries.
"""

GET_RECENT_DISCOVERIES = """
MATCH (d:DiscoveryEvent)
OPTIONAL MATCH (t:Tool)-[:DISCOVERED_FROM]->(d)
WITH d, collect(t.name) AS tools
ORDER BY d.timestamp DESC
LIMIT $limit
RETURN d.url          AS url,
       d.timestamp    AS timestamp,
       d.source_type  AS source_type,
       d.engine_used  AS engine_used,
       d.entity_count AS entity_count,
       tools
"""
"""Get the last N discovery events with their linked tools.

Required params: limit (int).
Returns: url, timestamp, source_type, engine_used, entity_count, tools (list of names).
"""

GET_AUDIT_TRAIL = """
MATCH (a:AuditLog)
WHERE a.timestamp >= datetime($start_time)
  AND a.timestamp <= datetime($end_time)
OPTIONAL MATCH (source)-[:LOGGED]->(a)
RETURN a.timestamp AS timestamp,
       a.action    AS action,
       a.actor     AS actor,
       a.details   AS details,
       labels(source)[0] AS source_type,
       CASE
           WHEN source:DiscoveryEvent THEN source.url
           WHEN source:IntegrationEvent THEN source.method
           ELSE null
       END AS source_ref
ORDER BY a.timestamp DESC
"""
"""Get the full audit trail for a time period.

Required params: start_time (ISO-8601 string), end_time (ISO-8601 string).
Returns: timestamp, action, actor, details, source_type, source_ref.
"""

FIND_TOOLS_WITHOUT_CAPABILITY = """
MATCH (t:Tool)
WHERE NOT (t)-[:PROVIDES]->(:Capability)
RETURN t.name        AS tool,
       t.description AS description,
       t.url         AS url
ORDER BY t.name
"""
"""Return tools that have no PROVIDES relationships (data gaps).

No required params.
Returns: tool, description, url.
"""

DELETE_TOOL = """
MATCH (t:Tool {name: $tool_name})
DETACH DELETE t
"""
"""Hard-delete a Tool node and all its relationships.

Required params: tool_name.
WARNING: irreversible — use only during graph cleanup.
"""

# ===========================================================================
# Query registry — useful for tooling / introspection
# ===========================================================================

QUERY_REGISTRY: dict[str, str] = {
    "UPSERT_TOOL": UPSERT_TOOL,
    "UPSERT_VENDOR": UPSERT_VENDOR,
    "UPSERT_CAPABILITY": UPSERT_CAPABILITY,
    "UPSERT_ENDPOINT": UPSERT_ENDPOINT,
    "CREATE_OFFERS_REL": CREATE_OFFERS_REL,
    "CREATE_PROVIDES_REL": CREATE_PROVIDES_REL,
    "CREATE_REPLACES_REL": CREATE_REPLACES_REL,
    "CREATE_COMPETES_WITH_REL": CREATE_COMPETES_WITH_REL,
    "CREATE_INTEGRATES_WITH_REL": CREATE_INTEGRATES_WITH_REL,
    "CREATE_HAS_ENDPOINT_REL": CREATE_HAS_ENDPOINT_REL,
    "CREATE_REQUIRES_REL": CREATE_REQUIRES_REL,
    "CREATE_DISCOVERED_FROM_REL": CREATE_DISCOVERED_FROM_REL,
    "LOG_DISCOVERY": LOG_DISCOVERY,
    "LOG_INTEGRATION": LOG_INTEGRATION,
    "CREATE_AUDIT_LOG": CREATE_AUDIT_LOG,
    "CREATE_AUDIT_LOG_SIMPLE": CREATE_AUDIT_LOG_SIMPLE,
    "FIND_SIMILAR_TOOLS": FIND_SIMILAR_TOOLS,
    "FIND_ALTERNATIVES": FIND_ALTERNATIVES,
    "GET_TOOL_SUBGRAPH": GET_TOOL_SUBGRAPH,
    "GET_UNINTEGRATED_TOOLS": GET_UNINTEGRATED_TOOLS,
    "GET_VENDOR_TOOLS": GET_VENDOR_TOOLS,
    "SEARCH_BY_CAPABILITY": SEARCH_BY_CAPABILITY,
    "SEARCH_TOOLS_FULLTEXT": SEARCH_TOOLS_FULLTEXT,
    "GET_HACKATHON_SPONSOR_TOOLS": GET_HACKATHON_SPONSOR_TOOLS,
    "GET_MCP_READY_TOOLS": GET_MCP_READY_TOOLS,
    "FULL_TOOL_REPORT": FULL_TOOL_REPORT,
    "GET_CAPABILITY_GRAPH": GET_CAPABILITY_GRAPH,
    "GET_INTEGRATION_COVERAGE": GET_INTEGRATION_COVERAGE,
    "GET_TOOL_HISTORY": GET_TOOL_HISTORY,
    "GET_RECENT_DISCOVERIES": GET_RECENT_DISCOVERIES,
    "GET_AUDIT_TRAIL": GET_AUDIT_TRAIL,
    "FIND_TOOLS_WITHOUT_CAPABILITY": FIND_TOOLS_WITHOUT_CAPABILITY,
    "DELETE_TOOL": DELETE_TOOL,
}
