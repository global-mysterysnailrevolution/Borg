---
description: "Discover and auto-integrate tools from any URL. Usage: /hackforge <url>"
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, Glob, Grep
---

Run the HackForge Link Intelligence pipeline on $ARGUMENTS.

## Instructions

1. Spawn the **link-intel** subagent to analyze the provided URL
2. The agent will:
   - Scrape the page for vendor/tool/API mentions
   - Deep-research each discovered entity
   - Compare against existing harness tools
   - Present recommendations (INTEGRATE / REPLACE / SKIP / ASK_USER)
3. For each tool recommended for integration:
   - Ask the user: integrate this tool? (yes/no/compare)
   - If yes, spawn **auth-forge** to set up credentials
   - Then spawn **tool-forge** to generate the MCP server
4. Save the full report to `ai/research/hackforge-[domain]-[date].md`
5. Update the Neo4j knowledge graph with all discoveries

If the URL is a Luma hackathon page, pay special attention to:
- Sponsors and partners (they provide API credits)
- Prize categories (tools required to compete)
- Resource links (documentation, quickstarts)

Present results as a structured table with recommended actions.
