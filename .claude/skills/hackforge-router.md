---
name: hackforge-router
description: >
  Routes HackForge tasks to the appropriate engine and subagent.
  Use when the user mentions tool discovery, vendor integration,
  video analysis, Instagram monitoring, or hackathon setup.
---

# HackForge Router

Routes incoming requests to the correct HackForge engine based on input type.

## Routing Rules

| Input Pattern | Engine | Subagent | Command |
|--------------|--------|----------|---------|
| Luma URL (lu.ma/*, luma.com/*) | LinkIntel | link-intel | /hackforge |
| Any webpage URL | LinkIntel | link-intel | /hackforge |
| YouTube URL (youtube.com/*, youtu.be/*) | VideoIntel | reel-scout | /analyze-video |
| Instagram reel URL | VideoIntel + ReelScout | reel-scout | /analyze-video |
| Instagram handle (@...) | ReelScout | reel-scout | /scout-reels |
| Hashtag (#...) | ReelScout | reel-scout | /scout-reels |
| Tool name (no URL) | ToolForge | tool-forge | /forge-tool |
| "set up" / "auth" / "key" | AuthForge | auth-forge | (internal) |
| "compare" / "versus" / "vs" | LinkIntel | link-intel | (internal) |

## Orchestration Patterns

### Pattern: Hackathon Quick Start
Input: Luma hackathon URL
1. LinkIntel → discover all sponsor tools
2. For each tool: AuthForge → acquire API keys
3. For each tool: ToolForge → generate MCP server
4. Neo4j → visualize the tool graph
5. Report → present unified dashboard

### Pattern: Video → Integration
Input: YouTube or Instagram URL
1. VideoIntel → analyze video content
2. Extract tools and Luma links
3. For each Luma link: trigger Hackathon Quick Start
4. For each tool: trigger ToolForge
5. Report → what was learned and integrated

### Pattern: Continuous Discovery
Input: Instagram handle or hashtag
1. ReelScout → start monitoring
2. On each new reel: VideoIntel → analyze
3. On each new tool: LinkIntel → research
4. Present discoveries for user approval
5. On approval: AuthForge + ToolForge → integrate

## Model Routing

Use the cheapest capable model for each task:
- **haiku**: Log monitoring, simple scraping, status checks
- **sonnet**: Entity extraction, code generation, API research
- **opus**: Complex orchestration, multi-step planning, ambiguous inputs

## Context Compilation

Before spawning subagents, use contextforge to compile:
- Only the relevant provider clients
- Current Neo4j graph state (if available)
- Previously discovered tools (avoid re-researching)
- User preferences from ai/memory/DECISIONS.md
