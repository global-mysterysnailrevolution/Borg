# HackForge + Agent Harness — Claude Code Native

This project combines an AI agent harness with **HackForge**, an autonomous tool
discovery and integration engine. HackForge takes a URL (Luma hackathon page,
YouTube video, Instagram reel) and automatically discovers, researches, sets up,
and integrates every tool mentioned — API keys, MCP servers, and all.

## HackForge Commands

- `/hackforge <url>` — Discover and auto-integrate tools from any URL
- `/analyze-video <url>` — Extract tools/methods from YouTube or Instagram video
- `/scout-reels <handle>` — Monitor Instagram for AI tool announcements
- `/forge-tool <name>` — Auto-generate an MCP server for any tool

## HackForge Engines

| Engine | Purpose | Providers Used |
|--------|---------|----------------|
| **LinkIntel** | URL → tool discovery | Tavily, Yutori, Fastino, Neo4j |
| **VideoIntel** | Video → tool extraction | Reka, Fastino, Modulate |
| **ReelScout** | Instagram monitoring | Yutori, Reka, Fastino |
| **AuthForge** | Agentic auth navigation | Yutori, Tavily |
| **ToolForge** | Auto-generate MCP servers | Tavily, Fastino, Jinja2 |

## HackForge Subagents

- **link-intel** — Scrapes URLs, extracts vendors, compares with harness
- **reel-scout** — Monitors Instagram, analyzes reels with multimodal AI
- **auth-forge** — Navigates signup pages, acquires API keys via browser
- **tool-forge** — Generates MCP servers from API documentation

## Core Harness Commands

- `/prime` — Map repo, load context, create implementation plan
- `/status` — Show harness status (context %, active agents, memory state)
- `/checkpoint` — Manually save session state to ai/memory/
- `/research <topic>` — Deep research via Tavily + Reka
- `/intake` — New project intake questionnaire
- `/diagnose` — Run system diagnostics

## Core Harness Subagents

- **log-monitor** — Monitors dev server logs for errors (runs on haiku)
- **test-companion** — Writes tests in parallel with feature work
- **research-agent** — Deep web research with multi-source synthesis
- **security-reviewer** — Reviews code changes for vulnerabilities
- **supervisor** — Orchestrates multi-agent workflows

## API Integrations (12 Providers)

| Provider | Capability | Auth |
|----------|-----------|------|
| **Tavily** | Web search | API key in body |
| **Reka AI** | Vision, video, audio, research | Bearer token |
| **Fastino** | Entity extraction (GLiNER2), classification, Pioneer personalization | Bearer token |
| **Neo4j** | Knowledge graph (tool relationships) | Bolt driver |
| **Yutori** | Browser automation, scouting, research | MCP via uvx |
| **Senso** | Knowledge base, document storage | Bearer token |
| **Modulate** | Voice/audio moderation (ToxMod) | X-API-Key |
| **Airbyte** | Data integration pipelines | Bearer token |
| **Render** | Cloud deployment (workers, cron) | Bearer token |
| **AWS** | Cloud infrastructure | IAM |
| **OpenAI** | LLM inference | Bearer token |
| **Numeric** | Analytics | Bearer token |

## Project Structure

```
hackforge/                  — Main Python package
  config.py                 — Centralized config loader
  engines/                  — Processing pipelines
    link_intel.py           — URL → tool discovery
    reel_scout.py           — Instagram monitoring
    auth_forge.py           — Agentic auth navigation
    tool_forge.py           — MCP server generation
    video_intel.py          — YouTube/video analysis
  providers/                — API client wrappers (7 clients)
  graph/                    — Neo4j schema + Cypher queries
  templates/                — Jinja2 templates for code generation
  demo.py                   — Live demo script

mcp-servers/
  fastino-mcp/              — Fastino Labs MCP server

.claude/
  agents/                   — 9 subagent definitions
  commands/                 — 11 slash commands
  skills/                   — 9 skills (incl. hackforge-router)
  scripts/                  — 3 hook scripts

ai/                         — Session state (not committed)
  context/                  — Repo maps, context packs
  memory/                   — Working memory, decisions, logs
  research/                 — Archived research outputs
  vendor/                   — Cached API responses
```

## Demo

```bash
# Simulated demo with ASCII visualization
python -m hackforge.demo

# Live mode against a real URL
python -m hackforge.demo --live https://luma.com/sfagents
```

## Rules

- Never commit secrets. The security hook scans all Write/Edit operations.
- Always checkpoint before context exceeds 80%.
- Delegate expensive exploration to subagents to keep main context clean.
- Use the cheapest model tier (haiku) for subagents doing routine work.
- Run `/prime` at the start of every new session to restore context.
- HackForge tools are additive — they never remove existing integrations.
