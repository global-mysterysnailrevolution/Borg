# HackForge: Autonomous Tool Discovery and Integration
## Sponsor Story — Autonomous Agents Hackathon SF | February 27, 2026

---

> **"Give us a Luma link, and we'll have every sponsor's API configured and ready to use in under 60 seconds."**

---

## What Is HackForge?

HackForge is an autonomous tool discovery and integration engine. Point it at any URL — a Luma hackathon page, a YouTube video, an Instagram reel — and it automatically:

1. Discovers every AI tool mentioned, shown, or demonstrated
2. Researches each tool's API, pricing, and authentication flow
3. Navigates signup pages, obtains API keys, and stores credentials
4. Generates fully functional MCP servers for each tool
5. Integrates everything into a Claude Code harness — with zero human page-by-page setup

HackForge is a tool that integrates tools. We built it using every sponsor's product at this hackathon. The system that discovers and integrates new AI tools is itself built from the very tools it discovers. This is the meta-story of HackForge.

---

## The Pipeline

```
┌─── INPUT ───────────────────────────────────────────────┐
│  Luma Link  │  YouTube Video  │  Instagram Reel  │  URL │
└──────┬──────┴────────┬────────┴─────────┬────────┴──┬───┘
       │               │                  │           │
       ▼               ▼                  ▼           ▼
  [Tavily Search] [Reka Vision+Audio] [Yutori Scout] [Tavily]
       │               │                  │           │
       ▼               ▼                  ▼           ▼
  ┌────────────────────────────────────────────────────────┐
  │            Fastino GLiNER2 Entity Extraction           │
  │     (tools, companies, APIs, methods, relations)       │
  └──────────────────────┬─────────────────────────────────┘
                         │
                         ▼
  ┌────────────────────────────────────────────────────────┐
  │              Neo4j Knowledge Graph                      │
  │    Tools ──PROVIDES──▶ Capabilities                    │
  │    Vendors ──OFFERS──▶ Tools                           │
  │    Tools ──REPLACES──▶ Tools                           │
  └──────────────────────┬─────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         [Compare]  [AuthForge] [ToolForge]
         with       Yutori      Jinja2 +
         existing   browse →    Fastino →
         (Senso     get keys    gen MCP
          search)               servers
              │          │          │
              ▼          ▼          ▼
  ┌────────────────────────────────────────────────────────┐
  │         Integrated Tool Ready to Use                    │
  │   API key stored │ MCP server generated │ Graph updated │
  └────────────────────────────────────────────────────────┘
                         │
                         ▼
         [Render: Deploy monitoring workers]
         [Airbyte: Pipe data between services]
         [Numeric: Track metrics & alert]
```

---

## Sponsor Deep Dives

Each sponsor below plays a non-replaceable role in the HackForge pipeline. We did not use these tools superficially. We built the system around them.

---

### Tavily — The Eyes of HackForge

> *"Every discovery starts with a Tavily search."*

Tavily is the first tool invoked for any new input. When HackForge receives a URL or a company name it has never seen before, Tavily is what makes the unknown knowable.

**Web Search API — LinkIntel and ToolForge Engines**

The Web Search API powers our `LinkIntel` engine, which crawls a hackathon sponsor page and resolves every company name into actionable intelligence: API documentation URLs, pricing tiers, signup pages, open-source alternatives, and community sentiment. When ToolForge is generating an MCP server for a newly discovered tool, it calls Tavily to find the most current API reference — not a cached or stale version, but the live, authoritative source.

This matters because AI tool APIs change fast. A vendor may have shipped a new endpoint last week that completely changes the integration approach. Tavily ensures HackForge always works from fresh data.

**MCP Endpoint — Direct Claude Code Integration**

Beyond the REST API, we connect directly to `mcp.tavily.com`, integrating Tavily as a native MCP tool within the Claude Code session. This means that when the Claude Code harness is reasoning about a newly discovered tool — mid-session — it can issue a Tavily search directly, without round-tripping through our own server layer. The search is ambient, instant, and contextually integrated.

This is the difference between a tool that looks things up for you and a tool that is part of how you think.

---

### Yutori — The Hands and Feet of HackForge

> *"Yutori browses the web, monitors the pulse of AI, and handles the tedious signup flows so humans don't have to."*

If Tavily is the eyes, Yutori is everything physical — the browsing, the monitoring, the form-filling. HackForge automates authentication flows that would otherwise require a human to open a browser and click through a dozen pages. Yutori makes this fully autonomous.

**Scouting — Continuous AI Ecosystem Monitoring**

Yutori's scouting capability runs 24/7 on Render (see below), monitoring Instagram profiles, GitHub repositories, and LinkedIn company pages for new tool announcements. We configure scouting with criteria-based alerting: if a post mentions "API," "SDK," "open source," or "launch," it triggers the HackForge ingestion pipeline. The interval is configurable — during the hackathon, we run it on 15-minute cycles.

This is how HackForge stays current. The AI tool landscape evolves daily. Scouting means HackForge knows about new tools before most developers do.

**Browsing — The AuthForge Engine**

Yutori's agentic browsing capability is the backbone of our `AuthForge` engine. Given a vendor's signup URL, Yutori navigates the page, fills registration forms with pre-configured credentials, handles OAuth redirect flows, waits for confirmation emails, and extracts the API key from the post-signup dashboard. This flow — which typically takes a human 5-10 minutes per vendor — runs autonomously in under 60 seconds.

AuthForge would not exist without agentic browsing. There is no API for "give me an API key." You have to click through the web. Yutori clicks through the web.

**Research — Deep Async Synthesis**

For complex vendors with multi-page documentation, Yutori's research mode runs 5-10 minute deep async tasks — visiting multiple documentation pages, cross-referencing changelogs, and synthesizing findings into structured summaries that feed directly into the Neo4j knowledge graph and Senso knowledge base.

---

### Reka AI — The Multimodal Cortex

> *"Reka sees videos, hears speech, and reasons about what tools are being demonstrated."*

Many of the most important AI tool announcements don't happen in blog posts — they happen in demo videos, conference talks, and social media reels. Reka gives HackForge the ability to extract structured intelligence from video and audio content, not just text.

**Vision (reka-core) — Visual Tool Identification**

When HackForge receives a YouTube video or Instagram reel URL, Reka's vision model analyzes frames for identifiable signals: product logos in the corner of a screen recording, terminal output showing package imports (`import anthropic`, `from openai import`), IDE extensions visible in the toolbar, and UI elements distinctive to specific developer tools.

A creator might never say the name of the tool they're using. Reka reads the screen and tells us anyway.

**Audio/Speech — Spoken Tool Names**

Creators often mention tools conversationally — "I'm using this with Cursor and it works great with their API" — without on-screen text to match. Reka's audio processing extracts speech transcripts from video content, passing them to Fastino's entity extraction pipeline. Tool names spoken aloud are captured as reliably as those written in captions or shown on screen.

**Research and Reasoning — Tool Comparison**

Reka's deep reasoning capability handles the comparative analysis layer of HackForge: given two tools that appear to serve the same purpose, which is more mature? Which has better rate limits for the use case at hand? Which has a more permissive license? Reka synthesizes API documentation and community signals into a structured trade-off analysis that populates the Neo4j comparison edges.

---

### Neo4j — The Memory and Map

> *"Neo4j knows how every tool relates to every other tool."*

HackForge doesn't just discover tools in isolation — it understands the ecosystem. Neo4j is how that understanding persists and compounds over time. Every tool, vendor, capability, and API endpoint becomes a node. Every relationship between them becomes an edge.

**Knowledge Graph — The Tool Ecosystem Model**

The HackForge knowledge graph uses the following schema:

```cypher
(:Tool)-[:PROVIDES]->(:Capability)
(:Vendor)-[:OFFERS]->(:Tool)
(:Tool)-[:INTEGRATES_WITH]->(:Tool)
(:Tool)-[:REPLACES]->(:Tool)
(:Tool)-[:COMPETES_WITH]->(:Tool)
(:Tool)-[:REQUIRES_AUTH]->(:AuthMethod)
(:Tool)-[:HAS_ENDPOINT]->(:APIEndpoint)
```

When HackForge discovers a new tool, it doesn't just add a row to a database — it finds every existing node the new tool connects to, creates edges with typed relationships, and updates capability coverage scores for the entire graph. The graph becomes smarter with every discovery.

**Graph Queries — Redundancy Detection and Path Finding**

Cypher queries power three critical HackForge capabilities:

- **Redundancy detection**: "Do we already have a tool that provides semantic search?" — a graph traversal through `(:Tool)-[:PROVIDES]->(:Capability {name: 'semantic_search'})` finds the answer instantly.
- **Integration path finding**: "What's the shortest path between this new data source and our Neo4j sink?" — a shortest-path query across `INTEGRATES_WITH` edges maps the connection.
- **Competitive landscape**: "What tools compete with this vendor's product?" — traversing `COMPETES_WITH` edges gives a complete picture before we decide whether integration is worth pursuing.

**Visualization — The Demo Graph**

Neo4j Browser and Bloom render the live tool graph for our demo presentation. The visualization shows how the 12 hackathon sponsors connect through shared capabilities — which vendors compete, which integrate, which form natural pipelines. Watching the graph populate in real time as HackForge processes the Luma page is the most compelling moment of the demo.

---

### Modulate — The Audio Dimension

> *"When a creator mentions a tool by name in a reel, Modulate catches it."*

Visual OCR and Reka's vision model handle what's on screen. Modulate handles what's in the audio — the dimension that most analysis pipelines ignore entirely.

**ToxMod Voice Analysis — Audio Content Classification**

HackForge uses Modulate's ToxMod pipeline for quality and content classification of audio extracted from Instagram reels and YouTube videos. Before investing Reka compute and Fastino NLP cycles on a piece of content, we need to know: is this audio clear enough to yield reliable transcripts? Is this content relevant — a genuine tool demo or tutorial — versus promotional noise? ToxMod's analysis provides the signal quality and content classification scores that determine whether downstream processing is warranted.

**Transcript Support — Audio-to-Text for Spoken Tool Names**

Modulate's audio-to-text pipeline handles cases where visual OCR alone isn't sufficient — fast-paced screen recordings, voice-over demos without captions, and content where the creator speaks tool names but never displays them in text. The transcripts produced by Modulate feed directly into Fastino's GLiNER2 entity extraction, completing the audio-to-knowledge pipeline.

---

### Senso — The Institutional Memory

> *"Senso remembers every tool we've ever researched and instantly retrieves relevant docs."*

HackForge processes hundreds of tools. Without persistent, searchable memory, the system would re-research the same tools repeatedly, wasting compute and time. Senso is the knowledge base that makes each discovery permanently useful.

**Knowledge Ingestion — Persistent Tool Documentation**

Every piece of tool intelligence HackForge produces — API documentation, pricing notes, authentication flow details, Yutori research summaries — is ingested into Senso. The ingestion is structured: we tag each document with the tool name, vendor, capability categories, and discovery timestamp. Senso's knowledge base becomes the authoritative source of truth for everything HackForge has ever learned.

**Semantic Search — Answering "Does This Already Exist?"**

Before HackForge invests effort in researching a newly discovered tool, it queries Senso: "Do we already have documentation for a tool that does this?" The semantic search — not keyword matching, but meaning-based retrieval — finds relevant existing knowledge even when the tool names differ. This prevents redundant research and surfaces prior knowledge that accelerates new integrations.

**Content Evaluation — Documentation Quality Assessment**

Not all API documentation is complete or accurate. Senso's evaluation layer assesses whether ingested tool docs cover the endpoints and authentication methods HackForge needs, flagging gaps that trigger a Yutori research task to fill them.

---

### Fastino Labs — The NLP Backbone

> *"Fastino reads text the way a human would, extracting structure from chaos at 99x the speed."*

Every piece of text that passes through HackForge — search results, video transcripts, API documentation, research summaries — goes through Fastino's NLP pipeline. Fastino is what transforms unstructured content into the structured knowledge that Neo4j, Senso, and ToolForge can act on.

**GLiNER2 Entity Extraction — The 205M-Parameter Backbone**

GLiNER2 is the workhorse of HackForge's ingestion pipeline. Given any text — a product blog post, a GitHub README, a Yutori research summary — GLiNER2 extracts the entities that matter: tool names, company names, API endpoints, authentication methods, SDK frameworks, and pricing tiers. At 205M parameters, it runs fast enough to process content in real time without bottlenecking the pipeline.

The entity extraction step is where raw text becomes actionable data. Every downstream system — Neo4j, Senso, ToolForge — depends on what GLiNER2 finds.

**Text Classification — Routing Content to the Right Pipeline**

Not all content is the same. A tweet announcing a product launch should route to the full discovery pipeline. A tutorial comparing two tools should route to the comparison engine. A changelog entry should route to the documentation updater. Fastino's text classification layer makes this routing decision automatically, ensuring each piece of content is handled by the right engine.

**Structured Data Extraction — API Specs from Prose**

API documentation is written for humans, not machines. Fastino extracts structured API specs from unstructured prose: endpoint paths, HTTP methods, required parameters, response schemas, authentication requirements, and rate limits. This structured output feeds directly into ToolForge, which uses it to generate accurate MCP server configurations.

**Relation Extraction — Mapping the Tool Ecosystem**

Fastino extracts relationship signals directly from text: "X integrates with Y," "X replaces Z," "X is built on top of Y." These extracted relations become edges in the Neo4j knowledge graph, populating the ecosystem map without requiring manual curation.

**Pioneer Personalization — Session Memory**

Fastino's Pioneer capability maintains user preference state across sessions: which tool categories the user cares about, which vendors they've already integrated, their preferred authentication methods, and their stored credentials. HackForge uses Pioneer to avoid surfacing tools the user has already dismissed and to prioritize discoveries in their preferred categories.

---

### Airbyte — The Plumbing

> *"Airbyte ensures data flows automatically between every service without manual ETL."*

HackForge connects many services. Without reliable, automated data pipelines between them, the system would require constant manual intervention to move data from one stage to the next. Airbyte is the connective tissue that keeps data flowing.

**Data Connectors — Cross-Service Data Movement**

Airbyte connectors handle three critical data flows in HackForge:

1. **Instagram → Analysis Pipeline**: Raw posts and reel content from Yutori's scouting output flow through Airbyte into the Reka and Modulate processing stages.
2. **Research Outputs → Neo4j**: Yutori research summaries and Fastino extraction results flow through Airbyte into the Neo4j knowledge graph, triggering node and edge creation.
3. **Tool Metadata → Senso**: Structured tool documentation and API specs flow through Airbyte into the Senso knowledge base for persistent storage and retrieval.

Each connector is configured once and runs automatically. No manual ETL. No scripts to maintain. Data just flows.

**REST API — Programmatic Connector Setup**

HackForge uses Airbyte's REST API to configure new connectors programmatically as new tools are discovered. When HackForge integrates a tool that produces data as output, it automatically provisions an Airbyte connector to route that data to the appropriate downstream service. The plumbing configures itself.

---

### Render — The Infrastructure

> *"Render keeps HackForge running in the cloud, always watching, always ready."*

HackForge is not a one-shot script. It is a continuously running system — always monitoring, always processing, always ready to integrate the next tool. Render provides the deployment infrastructure that makes this possible.

**Background Workers — 24/7 Monitoring Services**

The Yutori scouting jobs that continuously monitor Instagram, GitHub, and LinkedIn run as Render background workers. They have no inbound HTTP interface — they simply run, wake up on configured intervals, perform their scouting tasks, and push results into the pipeline. Render manages their lifecycle, restarts them on failure, and surfaces health metrics.

**Cron Jobs — Scheduled Maintenance Tasks**

HackForge requires periodic maintenance that runs on schedule: stale API key rotation (checking whether discovered keys are still valid), tool graph updates (re-running Tavily searches for tools whose documentation may have changed), and Senso knowledge base health checks. These run as Render cron jobs — simple, reliable, observable.

**Web Services — The Demo API**

The HackForge API — the HTTP interface used by the demo UI to submit URLs, check discovery status, and retrieve integration results — runs as a Render web service. It scales automatically and provides the public endpoint that the demo frontend calls.

---

### AWS — The Scale Guarantee

> *"When HackForge discovers 100 tools simultaneously, AWS handles the burst."*

Most of HackForge runs comfortably on Render. But when the system encounters a large input — a hackathon page with 50 sponsors, a popular YouTube video mentioning 30 tools — the workload spikes. AWS provides the burst capacity that absorbs these spikes without degrading performance.

**Cloud Infrastructure — Overflow Capacity**

AWS serves as the overflow layer for HackForge workloads that exceed Render's capacity or require services Render doesn't offer. The architecture is designed so that Render handles steady-state operation and AWS absorbs burst load, providing scale guarantees without paying for idle capacity.

**Lambda — Serverless Webhook Handlers**

Webhook events — Yutori alerting on a new Instagram post, Airbyte notifying on a successful sync, Numeric alerting on a metric threshold — are handled by AWS Lambda functions. Each webhook handler is a lightweight, stateless function that routes the event to the appropriate HackForge engine. Lambda's cold start latency is acceptable for event-driven workloads, and its pricing model aligns with HackForge's bursty traffic patterns.

---

### Numeric — The Scorekeeper

> *"Numeric measures how well HackForge is performing and alerts us when something needs attention."*

An autonomous system without observability is a system you can't trust. Numeric is how HackForge knows whether it's working — and how operators know when to intervene.

**Analytics Dashboard — Integration Metrics**

Numeric tracks the metrics that define HackForge's effectiveness:

- Tools discovered per input URL
- Authentication success rate (how often AuthForge successfully obtains API keys)
- MCP server generation success rate
- Mean time from URL submission to fully integrated tool
- API response time percentiles for each vendor integration

These metrics are visible in the Numeric dashboard during the demo, showing real performance data from the hackathon run itself.

**Alerting — Operational Intelligence**

Numeric alerts notify operators when HackForge needs human attention: an API key has expired and needs rotation, a vendor has changed their authentication flow and AuthForge is failing, a new competitor to an integrated tool has been detected by the scouting service. The alerting layer turns an autonomous system into a supervised one — humans stay informed without having to watch dashboards constantly.

---

### OpenAI — The Second Opinion

> *"When HackForge needs a second opinion on tool comparison, GPT-4 weighs in."*

HackForge uses Claude as its primary reasoning engine. But complex tool comparison decisions benefit from independent validation — a second model's perspective that isn't anchored to the first model's conclusions.

**GPT-4 — Fallback and Validation**

GPT-4 serves as HackForge's fallback LLM for complex reasoning tasks — particularly cases where Reka's analysis or the primary Claude reasoning produces low-confidence outputs. When HackForge is deciding whether two tools are genuinely equivalent (and therefore one is redundant), it submits the analysis to GPT-4 for independent assessment. Disagreement between models flags the comparison for human review. Agreement increases confidence in the automated decision.

**Embeddings — Semantic Similarity Matching**

OpenAI embeddings power the semantic similarity layer used when comparing tools across the Neo4j graph. When a newly discovered tool needs to find its closest existing neighbors in the capability space, embedding similarity provides the initial ranking. This is faster than running a full Reka reasoning pass on every candidate pair, and it filters the candidate set to the most relevant comparisons before deeper analysis begins.

---

## The Meta Story

HackForge is a demonstration of a thesis: the future of developer tooling is autonomous, composable, and self-improving.

Every sponsor at this hackathon builds something that matters. But tools don't integrate themselves. APIs don't discover themselves. Auth flows don't navigate themselves. Today, every developer who wants to use a new tool goes through the same tedious process: find the docs, sign up for the API, read the authentication section, write the integration code, test it, debug it, repeat.

HackForge eliminates that process entirely.

We built HackForge using every sponsor's product. The same system that integrates your tools was itself built from those tools. That's not a coincidence — it's the point. When tools are composable and discoverable, the right system can integrate them autonomously. HackForge is what that system looks like.

**Give us a Luma link.** We'll have every sponsor's API configured and ready to use in under 60 seconds.

**Give us a YouTube video.** We'll extract every tool mentioned — spoken, shown, or implied — and build MCP servers for each one.

**Give us an Instagram reel.** We'll monitor the AI space 24/7, automatically integrating new tools as they're announced.

This is the future. It's running right now.

---

*HackForge — Autonomous Agents Hackathon SF — February 27, 2026*
