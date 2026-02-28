"""HackForge API — FastAPI server for demo and visualization."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from hackforge.pipeline_bus import PipelineEvent, pipeline_bus

logger = logging.getLogger(__name__)

app = FastAPI(
    title="The Borg",
    description="Autonomous Tool Discovery & Integration Engine — Resistance is Futile",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeVideoRequest(BaseModel):
    url: str


class ResearchToolRequest(BaseModel):
    name: str
    vendor: str = ""


class IntegrateToolRequest(BaseModel):
    name: str
    method: str = "mcp"  # "mcp" | "rest" | "manual"


class DismissToolRequest(BaseModel):
    name: str
    reason: str = ""


# ---------------------------------------------------------------------------
# Sponsor catalogue  (12 hackathon sponsors)
# ---------------------------------------------------------------------------

SPONSORS: list[dict[str, Any]] = [
    {
        "name": "Tavily",
        "role": "Web Search & Scraping",
        "env_key": "TAVILY_API_KEY",
        "color": "#4CAF50",
        "icon": "search",
        "docs": "https://tavily.com",
    },
    {
        "name": "Reka AI",
        "role": "Vision, Video & Audio Intelligence",
        "env_key": "REKA_API_KEY",
        "color": "#9C27B0",
        "icon": "movie",
        "docs": "https://reka.ai",
    },
    {
        "name": "Fastino",
        "role": "Entity Extraction & Fast Inference",
        "env_key": "FASTINO_API_KEY",
        "color": "#FF9800",
        "icon": "flash_on",
        "docs": "https://fastino.ai",
    },
    {
        "name": "Neo4j",
        "role": "Knowledge Graph",
        "env_key": "NEO4J_URI",
        "color": "#2196F3",
        "icon": "account_tree",
        "docs": "https://neo4j.com",
    },
    {
        "name": "Yutori",
        "role": "Browser Automation & Scouting",
        "env_key": "YUTORI_API_KEY",
        "color": "#00BCD4",
        "icon": "open_in_browser",
        "docs": "https://yutori.ai",
    },
    {
        "name": "Senso",
        "role": "Knowledge Base & Document Storage",
        "env_key": "SENSO_API_KEY",
        "color": "#8BC34A",
        "icon": "storage",
        "docs": "https://senso.ai",
    },
    {
        "name": "Modulate",
        "role": "Voice & Audio Moderation (ToxMod)",
        "env_key": "MODULATE_API_KEY",
        "color": "#F44336",
        "icon": "mic",
        "docs": "https://modulate.ai",
    },
    {
        "name": "Airbyte",
        "role": "Data Integration Pipelines",
        "env_key": "AIRBYTE_API_KEY",
        "color": "#795548",
        "icon": "sync",
        "docs": "https://airbyte.com",
    },
    {
        "name": "Render",
        "role": "Cloud Deployment & Workers",
        "env_key": "RENDER_API_KEY",
        "color": "#607D8B",
        "icon": "cloud_upload",
        "docs": "https://render.com",
    },
    {
        "name": "AWS",
        "role": "Cloud Infrastructure",
        "env_key": "AWS_ACCESS_KEY_ID",
        "color": "#FF9800",
        "icon": "dns",
        "docs": "https://aws.amazon.com",
    },
    {
        "name": "OpenAI",
        "role": "LLM Inference",
        "env_key": "OPENAI_API_KEY",
        "color": "#4CAF50",
        "icon": "psychology",
        "docs": "https://openai.com",
    },
    {
        "name": "Numeric",
        "role": "Analytics",
        "env_key": "NUMERIC_API_KEY",
        "color": "#3F51B5",
        "icon": "bar_chart",
        "docs": "https://numeric.io",
    },
]

# ---------------------------------------------------------------------------
# Demo graph data (used when Neo4j is not connected)
# ---------------------------------------------------------------------------

DEMO_GRAPH: dict[str, Any] = {
    "nodes": [
        # Vendor / sponsor nodes
        {"id": 1,  "label": "Tavily",   "group": "vendor",      "color": "#4CAF50", "size": 28, "title": "Web Search & Scraping"},
        {"id": 2,  "label": "Reka AI",  "group": "vendor",      "color": "#9C27B0", "size": 28, "title": "Vision & Video AI"},
        {"id": 3,  "label": "Fastino",  "group": "vendor",      "color": "#FF9800", "size": 28, "title": "Fast Entity Extraction"},
        {"id": 4,  "label": "Neo4j",    "group": "vendor",      "color": "#2196F3", "size": 28, "title": "Knowledge Graph DB"},
        {"id": 5,  "label": "Yutori",   "group": "vendor",      "color": "#00BCD4", "size": 28, "title": "Browser Automation"},
        {"id": 6,  "label": "Senso",    "group": "vendor",      "color": "#8BC34A", "size": 24, "title": "Knowledge Base"},
        {"id": 7,  "label": "Modulate", "group": "vendor",      "color": "#F44336", "size": 24, "title": "Audio Moderation"},
        {"id": 8,  "label": "Airbyte",  "group": "vendor",      "color": "#795548", "size": 24, "title": "Data Pipelines"},
        # Engine nodes
        {"id": 10, "label": "LinkIntel",   "group": "engine",   "color": "#E91E63", "size": 32, "title": "URL → Tool Discovery"},
        {"id": 11, "label": "VideoIntel",  "group": "engine",   "color": "#E91E63", "size": 32, "title": "Video → Tool Extraction"},
        {"id": 12, "label": "ReelScout",   "group": "engine",   "color": "#E91E63", "size": 28, "title": "Instagram Monitoring"},
        {"id": 13, "label": "AuthForge",   "group": "engine",   "color": "#E91E63", "size": 28, "title": "Agentic Auth"},
        {"id": 14, "label": "ToolForge",   "group": "engine",   "color": "#E91E63", "size": 28, "title": "MCP Server Generator"},
        # Capability nodes
        {"id": 20, "label": "web_search",        "group": "capability", "color": "#37474F", "size": 18, "title": "Web Search"},
        {"id": 21, "label": "video_analysis",    "group": "capability", "color": "#37474F", "size": 18, "title": "Video Analysis"},
        {"id": 22, "label": "entity_extraction", "group": "capability", "color": "#37474F", "size": 18, "title": "Entity Extraction"},
        {"id": 23, "label": "graph_storage",     "group": "capability", "color": "#37474F", "size": 18, "title": "Graph Storage"},
        {"id": 24, "label": "browser_control",   "group": "capability", "color": "#37474F", "size": 18, "title": "Browser Control"},
        {"id": 25, "label": "audio_transcription","group": "capability", "color": "#37474F", "size": 18, "title": "Audio Transcription"},
        {"id": 26, "label": "mcp_generation",    "group": "capability", "color": "#37474F", "size": 18, "title": "MCP Generation"},
        {"id": 27, "label": "url_discovery",     "group": "capability", "color": "#37474F", "size": 18, "title": "URL Discovery"},
    ],
    "edges": [
        # Vendor → Capability
        {"from": 1,  "to": 20, "label": "PROVIDES", "color": "#4CAF50"},
        {"from": 2,  "to": 21, "label": "PROVIDES", "color": "#9C27B0"},
        {"from": 2,  "to": 25, "label": "PROVIDES", "color": "#9C27B0"},
        {"from": 3,  "to": 22, "label": "PROVIDES", "color": "#FF9800"},
        {"from": 4,  "to": 23, "label": "PROVIDES", "color": "#2196F3"},
        {"from": 5,  "to": 24, "label": "PROVIDES", "color": "#00BCD4"},
        {"from": 3,  "to": 26, "label": "PROVIDES", "color": "#FF9800"},
        {"from": 1,  "to": 27, "label": "PROVIDES", "color": "#4CAF50"},
        # Engine → Vendor (USES)
        {"from": 10, "to": 1,  "label": "USES",     "color": "#E91E63"},
        {"from": 10, "to": 3,  "label": "USES",     "color": "#E91E63"},
        {"from": 10, "to": 4,  "label": "USES",     "color": "#E91E63"},
        {"from": 10, "to": 5,  "label": "USES",     "color": "#E91E63"},
        {"from": 11, "to": 2,  "label": "USES",     "color": "#E91E63"},
        {"from": 11, "to": 3,  "label": "USES",     "color": "#E91E63"},
        {"from": 11, "to": 7,  "label": "USES",     "color": "#E91E63"},
        {"from": 12, "to": 5,  "label": "USES",     "color": "#E91E63"},
        {"from": 12, "to": 2,  "label": "USES",     "color": "#E91E63"},
        {"from": 13, "to": 5,  "label": "USES",     "color": "#E91E63"},
        {"from": 13, "to": 1,  "label": "USES",     "color": "#E91E63"},
        {"from": 14, "to": 1,  "label": "USES",     "color": "#E91E63"},
        {"from": 14, "to": 3,  "label": "USES",     "color": "#E91E63"},
        # Engine → Engine (FEEDS_INTO)
        {"from": 10, "to": 14, "label": "FEEDS_INTO", "dashes": True, "color": "#78909C"},
        {"from": 11, "to": 10, "label": "FEEDS_INTO", "dashes": True, "color": "#78909C"},
        {"from": 12, "to": 11, "label": "FEEDS_INTO", "dashes": True, "color": "#78909C"},
        {"from": 13, "to": 14, "label": "FEEDS_INTO", "dashes": True, "color": "#78909C"},
    ],
}

# ---------------------------------------------------------------------------
# HTML demo UI
# ---------------------------------------------------------------------------

DEMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Borg — Autonomous Tool Discovery & Integration</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root {
    --bg:       #0d1117;
    --surface:  #161b22;
    --border:   #30363d;
    --accent:   #e91e63;
    --accent2:  #2196F3;
    --text:     #c9d1d9;
    --muted:    #8b949e;
    --green:    #4CAF50;
    --yellow:   #FF9800;
    --red:      #F44336;
    --radius:   10px;
    --font:     'Segoe UI', system-ui, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font); min-height: 100vh; }

  /* ── Header ─────────────────────────────────────────────── */
  header {
    background: linear-gradient(135deg, #1a0a1e 0%, #0d1117 60%, #0a1628 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex; align-items: center; justify-content: space-between;
    position: relative; z-index: 100;
  }
  .logo { display: flex; align-items: center; gap: 12px; }
  .logo-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: 900; color: #fff;
  }
  .logo-text h1 { font-size: 22px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
  .logo-text p  { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .badge {
    background: linear-gradient(135deg, var(--accent), #c2185b);
    color: #fff; padding: 4px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  /* ── Tabs ────────────────────────────────────────────────── */
  .tabs {
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
    background: var(--surface); padding: 0 32px;
  }
  .tab {
    padding: 14px 22px; cursor: pointer; font-size: 14px; font-weight: 500;
    color: var(--muted); border-bottom: 2px solid transparent;
    transition: all 0.2s; user-select: none;
  }
  .tab:hover  { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* ── Layout ──────────────────────────────────────────────── */
  .container { max-width: 1280px; margin: 0 auto; padding: 28px 32px; }
  .panel { display: none; }
  .panel.active { display: block; }

  /* ── Search bar ──────────────────────────────────────────── */
  .search-wrap {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px; margin-bottom: 28px;
  }
  .search-wrap label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }
  .search-row { display: flex; gap: 10px; }
  .search-row input {
    flex: 1; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 11px 16px; color: var(--text); font-size: 14px;
    outline: none; transition: border-color 0.2s;
  }
  .search-row input:focus { border-color: var(--accent); }
  .search-row input::placeholder { color: var(--muted); }
  .btn {
    background: linear-gradient(135deg, var(--accent), #c2185b);
    color: #fff; border: none; border-radius: 8px; padding: 11px 24px;
    font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
    white-space: nowrap; display: flex; align-items: center; gap: 6px;
  }
  .btn:hover { opacity: 0.88; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-outline {
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer;
    transition: all 0.2s;
  }
  .btn-outline:hover { border-color: var(--text); color: var(--text); }

  /* ── Status pills ────────────────────────────────────────── */
  .status-row { display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }
  .stat-pill {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 18px; display: flex; align-items: center; gap: 8px;
    font-size: 13px;
  }
  .stat-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
  .stat-pill .num { font-size: 18px; font-weight: 700; color: var(--accent); }

  /* ── Result cards ────────────────────────────────────────── */
  .section-title { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 16px; }
  .cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px; transition: border-color 0.2s;
    position: relative; overflow: hidden;
  }
  .card:hover { border-color: #4a5568; }
  .card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: var(--card-accent, var(--accent));
  }
  .card-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 10px; }
  .card-name { font-size: 15px; font-weight: 600; color: #fff; }
  .card-vendor { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .tag {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; font-weight: 500;
    background: rgba(233,30,99,0.15); color: var(--accent); white-space: nowrap;
  }
  .tag.green  { background: rgba(76,175,80,0.15); color: var(--green); }
  .tag.yellow { background: rgba(255,152,0,0.15); color: var(--yellow); }
  .card-desc { font-size: 13px; color: var(--muted); line-height: 1.55; margin-bottom: 12px; }
  .caps { display: flex; flex-wrap: wrap; gap: 6px; }
  .cap { font-size: 11px; padding: 3px 8px; border-radius: 5px; background: rgba(255,255,255,0.05); color: var(--muted); }
  .action-row { display: flex; gap: 8px; margin-top: 12px; align-items: center; }
  .action-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .action-integrate { color: var(--green); }
  .action-evaluate  { color: var(--yellow); }
  .action-skip      { color: var(--muted); }

  /* ── Graph panel ─────────────────────────────────────────── */
  .graph-wrap {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; position: relative;
  }
  .graph-toolbar {
    padding: 12px 20px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 12px;
  }
  .graph-toolbar span { font-size: 13px; color: var(--muted); }
  #graph-container { height: 580px; width: 100%; }
  .legend { display: flex; gap: 20px; padding: 12px 20px; border-top: 1px solid var(--border); flex-wrap: wrap; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }

  /* ── Sponsors panel ──────────────────────────────────────── */
  .sponsors-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .sponsor-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px;
    display: flex; align-items: flex-start; gap: 14px;
    transition: border-color 0.2s;
  }
  .sponsor-card:hover { border-color: #4a5568; }
  .sponsor-icon {
    width: 40px; height: 40px; border-radius: 8px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; color: #fff;
  }
  .sponsor-info { flex: 1; min-width: 0; }
  .sponsor-name { font-size: 14px; font-weight: 600; color: #fff; }
  .sponsor-role { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .sponsor-status { margin-top: 8px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .status-configured { color: var(--green); }
  .status-discovered  { color: var(--yellow); }
  .status-pending     { color: var(--muted); }

  /* ── Detail modal ────────────────────────────────────────── */
  .modal-overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    width: 90%; max-width: 700px; max-height: 80vh; overflow-y: auto; padding: 28px;
    position: relative;
  }
  .modal-close {
    position: absolute; top: 14px; right: 18px; background: none; border: none;
    color: var(--muted); font-size: 22px; cursor: pointer; line-height: 1;
  }
  .modal-close:hover { color: var(--text); }
  .modal h2 { font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 6px; }
  .modal .vendor-line { font-size: 13px; color: var(--muted); margin-bottom: 16px; }
  .modal .section { margin-bottom: 18px; }
  .modal .section h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 8px; }
  .modal .section p { font-size: 14px; color: var(--text); line-height: 1.6; }
  .modal .source-list { list-style: none; padding: 0; }
  .modal .source-list li {
    padding: 8px 12px; background: var(--bg); border-radius: 6px; margin-bottom: 6px; font-size: 13px;
  }
  .modal .source-list li a { color: var(--accent2); text-decoration: none; }
  .modal .source-list li a:hover { text-decoration: underline; }
  .modal .source-snippet { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .modal-actions { display: flex; gap: 10px; margin-top: 20px; border-top: 1px solid var(--border); padding-top: 16px; }
  .btn-integrate { background: linear-gradient(135deg, var(--green), #388E3C); }
  .btn-dismiss { background: transparent; border: 1px solid var(--border); color: var(--muted); }
  .btn-dismiss:hover { border-color: var(--red); color: var(--red); }

  /* ── Card action buttons ────────────────────────────────── */
  .card-actions { display: flex; gap: 6px; margin-top: 12px; }
  .card-btn {
    font-size: 11px; padding: 5px 12px; border-radius: 6px; cursor: pointer;
    font-weight: 600; border: none; transition: all 0.2s;
  }
  .card-btn-research { background: rgba(33,150,243,0.15); color: var(--accent2); }
  .card-btn-research:hover { background: rgba(33,150,243,0.3); }
  .card-btn-integrate { background: rgba(76,175,80,0.15); color: var(--green); }
  .card-btn-integrate:hover { background: rgba(76,175,80,0.3); }
  .card-btn-getkey { background: rgba(255,193,7,0.15); color: #FFD54F; }
  .card-btn-getkey:hover { background: rgba(255,193,7,0.3); }
  .card-btn-dismiss { background: rgba(255,255,255,0.05); color: var(--muted); }
  .card-btn-dismiss:hover { background: rgba(244,67,54,0.15); color: var(--red); }
  .card.integrated { border-color: var(--green); opacity: 0.7; }
  .card.dismissed { border-color: var(--border); opacity: 0.35; }
  .card-status-badge {
    position: absolute; top: 10px; right: 14px; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 8px; border-radius: 4px;
  }
  .badge-integrated { background: rgba(76,175,80,0.2); color: var(--green); }
  .badge-researched { background: rgba(33,150,243,0.2); color: var(--accent2); }
  .badge-dismissed { background: rgba(255,255,255,0.05); color: var(--muted); }

  /* ── Activity feed ───────────────────────────────────────── */
  .activity-item {
    display: flex; align-items: flex-start; gap: 10px; padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }
  .activity-item:last-child { border-bottom: none; }
  .activity-time { color: #4a5568; font-size: 11px; min-width: 70px; flex-shrink: 0; }
  .activity-dot {
    width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0;
  }
  .activity-dot.step     { background: var(--accent2); }
  .activity-dot.result   { background: var(--green); }
  .activity-dot.error    { background: var(--red); }
  .activity-dot.agent    { background: #a855f7; }
  .activity-dot.progress { background: var(--yellow); animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .activity-engine {
    font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    padding: 1px 6px; border-radius: 3px; flex-shrink: 0;
  }
  .engine-link_intel  { background: rgba(233,30,99,0.15); color: var(--accent); }
  .engine-tool_forge  { background: rgba(33,150,243,0.15); color: var(--accent2); }
  .engine-agent       { background: rgba(168,85,247,0.15); color: #a855f7; }
  .engine-video_intel { background: rgba(156,39,176,0.15); color: #9C27B0; }
  .engine-auth_forge  { background: rgba(255,193,7,0.15); color: #FFD54F; }
  .activity-msg { color: var(--text); flex: 1; }
  .activity-msg .highlight { color: #fff; font-weight: 600; }

  /* ── Demo narration ────────────────────────────────────── */
  #demo-narration {
    display: none; position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%);
    background: rgba(0,0,0,0.92); border: 1px solid rgba(168,85,247,0.5);
    border-radius: 12px; padding: 16px 28px; z-index: 2000;
    max-width: 600px; text-align: center; backdrop-filter: blur(12px);
    box-shadow: 0 8px 32px rgba(168,85,247,0.2);
  }
  #demo-narration.show { display: block; animation: fadeUp 0.4s ease; }
  @keyframes fadeUp { from { opacity:0; transform: translateX(-50%) translateY(20px); } to { opacity:1; transform: translateX(-50%) translateY(0); } }
  #demo-narration h3 { font-size: 15px; color: #a855f7; margin-bottom: 4px; font-weight: 700; }
  #demo-narration p { font-size: 13px; color: var(--text); line-height: 1.5; }
  .demo-step-num { color: #a855f7; font-weight: 800; font-size: 18px; margin-right: 6px; }

  /* ── Loading / error ─────────────────────────────────────── */
  .spinner {
    display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .alert {
    background: rgba(244,67,54,0.1); border: 1px solid rgba(244,67,54,0.3);
    border-radius: 8px; padding: 14px 18px; font-size: 13px; color: #ef9a9a; margin-bottom: 20px;
  }
  .empty-state {
    text-align: center; padding: 60px 20px; color: var(--muted);
  }
  .empty-state .big { font-size: 48px; margin-bottom: 12px; }
  .empty-state p { font-size: 14px; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon" style="font-size:18px">&#9609;</div>
    <div class="logo-text">
      <h1>The Borg</h1>
      <p>Autonomous Tool Discovery &amp; Integration — Resistance is Futile</p>
    </div>
  </div>
  <div style="display:flex;gap:10px;align-items:center">
    <button id="demo-btn" onclick="runDemo()" style="background:linear-gradient(135deg,#a855f7,#6d28d9);color:#fff;border:none;border-radius:8px;padding:10px 22px;font-size:14px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:6px;z-index:200;position:relative">
      <span id="demo-label">&#9654; Auto Demo</span>
      <span id="demo-spinner" class="spinner" style="display:none"></span>
    </button>
    <span class="badge">Live</span>
  </div>
</header>

<nav class="tabs">
  <div class="tab active" onclick="showTab('discover')">Discover</div>
  <div class="tab" onclick="showTab('graph')">Graph</div>
  <div class="tab" onclick="showTab('sponsors')">Sponsors</div>
  <div class="tab" onclick="showTab('video')">Video Intel</div>
  <div class="tab" onclick="showTab('activity')">Activity <span id="activity-count" style="background:var(--accent);color:#fff;border-radius:10px;padding:1px 7px;font-size:10px;margin-left:4px;display:none">0</span></div>
</nav>

<!-- ================================================================ DISCOVER -->
<div id="tab-discover" class="panel active">
<div class="container">

  <div class="search-wrap">
    <label>Analyze any Luma hackathon page, landing page, or docs site</label>
    <div class="search-row">
      <input id="url-input" type="url" placeholder="https://lu.ma/sfagents   or   https://any-hackathon-page.com" />
      <button class="btn" id="forge-btn" onclick="runAnalyze()">
        <span id="forge-label">Forge</span>
        <span id="forge-spinner" class="spinner" style="display:none"></span>
      </button>
    </div>
  </div>

  <div id="discover-error" class="alert" style="display:none"></div>

  <div class="status-row" id="status-row" style="display:none">
    <div class="stat-pill">
      <div class="dot"></div>
      <span>Discovered</span>
      <span class="num" id="stat-total">0</span>
      <span>tools</span>
    </div>
    <div class="stat-pill">
      <div class="dot" style="background:var(--yellow)"></div>
      <span>Entities scanned</span>
      <span class="num" id="stat-entities">0</span>
    </div>
    <div class="stat-pill">
      <div class="dot" style="background:var(--accent2)"></div>
      <span>Actions</span>
      <span class="num" id="stat-actions">0</span>
      <span>recommended</span>
    </div>
  </div>

  <div id="results-area">
    <div class="empty-state" id="empty-discover">
      <div class="big">&#9889;</div>
      <p>Enter a URL above and press Forge to discover tools automatically.</p>
    </div>
    <div id="cards-area" style="display:none">
      <div class="section-title" id="cards-title">Discovered Tools</div>
      <div class="cards-grid" id="cards-grid"></div>
    </div>
  </div>

</div>
</div>

<!-- ================================================================ GRAPH -->
<div id="tab-graph" class="panel">
<div class="container">

  <div class="search-wrap" style="margin-bottom:20px">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <span style="font-size:13px;color:var(--muted)">Knowledge graph — tool relationships, capabilities, and integration status</span>
      <button class="btn-outline" onclick="loadGraph()">Refresh</button>
    </div>
  </div>

  <div class="graph-wrap">
    <div class="graph-toolbar">
      <span>vis.js physics simulation &mdash; nodes settle via Barnes-Hut force</span>
      <span id="graph-node-count" style="margin-left:auto;"></span>
    </div>
    <div id="graph-container"></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#E91E63"></div> Engine</div>
      <div class="legend-item"><div class="legend-dot" style="background:#4CAF50"></div> Vendor (configured)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#2196F3"></div> Vendor (Neo4j)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#37474F"></div> Capability</div>
    </div>
  </div>

</div>
</div>

<!-- ================================================================ SPONSORS -->
<div id="tab-sponsors" class="panel">
<div class="container">
  <div class="section-title" style="margin-bottom:20px">12 Hackathon Sponsors</div>
  <div class="sponsors-grid" id="sponsors-grid"></div>
</div>
</div>

<!-- ================================================================ VIDEO INTEL -->
<div id="tab-video" class="panel">
<div class="container">

  <div class="search-wrap">
    <label>Analyze a YouTube video or Instagram reel for AI tool discovery</label>
    <div class="search-row">
      <input id="video-url-input" type="url" placeholder="https://youtube.com/watch?v=...   or   https://instagram.com/reel/..." />
      <button class="btn" id="video-btn" onclick="runVideoAnalyze()">
        <span id="video-label">Analyze</span>
        <span id="video-spinner" class="spinner" style="display:none"></span>
      </button>
    </div>
  </div>

  <div id="video-error" class="alert" style="display:none"></div>

  <div id="video-results">
    <div class="empty-state" id="empty-video">
      <div class="big">&#127909;</div>
      <p>Enter a YouTube or Instagram URL to extract tools via Reka AI + Fastino.</p>
    </div>
    <div id="video-cards-area" style="display:none">
      <div class="section-title" id="video-title-label">Video Analysis</div>
      <div class="cards-grid" id="video-cards-grid"></div>
    </div>
  </div>

</div>
</div>

<!-- ================================================================ ACTIVITY -->
<div id="tab-activity" class="panel">
<div class="container">
  <div class="search-wrap" style="margin-bottom:20px">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <span style="font-size:13px;color:var(--muted)">Live pipeline activity — watch discovery, research, and integration in real time</span>
      <div style="display:flex;gap:8px">
        <button class="btn-outline" onclick="clearActivity()">Clear</button>
        <button class="btn-outline" id="sse-status" style="border-color:var(--green);color:var(--green)">Connected</button>
      </div>
    </div>
  </div>

  <div id="activity-feed" style="
    background: #0a0e14;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    min-height: 500px;
    max-height: 70vh;
    overflow-y: auto;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.7;
  ">
    <div id="activity-empty" style="text-align:center;padding:40px;color:var(--muted)">
      <div style="font-size:32px;margin-bottom:8px">&#9889;</div>
      <p>Waiting for pipeline activity...</p>
      <p style="font-size:11px;margin-top:4px">Analyze a URL or integrate a tool to see events here.</p>
    </div>
  </div>
</div>
</div>

<!-- ================================================================ MODAL -->
<div class="modal-overlay" id="tool-modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h2 id="modal-name"></h2>
    <div class="vendor-line" id="modal-vendor"></div>
    <div class="section" id="modal-summary-section" style="display:none">
      <h3>AI Summary</h3>
      <p id="modal-summary"></p>
    </div>
    <div class="section" id="modal-answer-section" style="display:none">
      <h3>Research Answer</h3>
      <p id="modal-answer"></p>
    </div>
    <div class="section" id="modal-caps-section" style="display:none">
      <h3>Capabilities</h3>
      <div id="modal-caps" class="caps"></div>
    </div>
    <div class="section" id="modal-sources-section" style="display:none">
      <h3>Sources</h3>
      <ul class="source-list" id="modal-sources"></ul>
    </div>
    <div class="section" id="modal-integration-section" style="display:none">
      <h3>Integration Guides</h3>
      <ul class="source-list" id="modal-integration-sources"></ul>
    </div>
    <div class="section" id="modal-history-section" style="display:none">
      <h3>Discovery History</h3>
      <ul class="source-list" id="modal-history"></ul>
    </div>
    <div id="modal-loading" style="text-align:center;padding:20px;display:none">
      <div class="spinner" style="width:24px;height:24px"></div>
      <p style="font-size:13px;color:var(--muted);margin-top:8px">Researching with Tavily + Reka AI...</p>
    </div>
    <div class="modal-actions" id="modal-actions">
      <button class="btn" style="background:rgba(255,193,7,0.15);color:#FFD54F" onclick="getToolKey()">Get API Key</button>
      <button class="btn btn-integrate" onclick="integrateTool()">Integrate into Harness</button>
      <button class="btn btn-dismiss" onclick="dismissTool()">Dismiss</button>
    </div>
  </div>
</div>

<div id="demo-narration"><h3 id="narr-title"></h3><p id="narr-text"></p></div>

<script>
// ── State ─────────────────────────────────────────────────────────────────
let currentTool = null;
const toolStates = {};  // name -> {status: 'researched'|'integrated'|'dismissed', data: {...}}

// ── Tab switching ──────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[onclick="showTab('${name}')"]`).classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'graph')    loadGraph();
  if (name === 'sponsors') loadSponsors();
}

// ── Discover ───────────────────────────────────────────────────────────────
async function runAnalyze() {
  const url = document.getElementById('url-input').value.trim();
  if (!url) { alert('Please enter a URL.'); return; }
  setLoading('forge', true);
  document.getElementById('discover-error').style.display = 'none';
  document.getElementById('status-row').style.display = 'none';
  document.getElementById('cards-area').style.display = 'none';
  document.getElementById('empty-discover').style.display = 'none';
  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    renderDiscoverResults(data);
  } catch(e) {
    showError('discover-error', e.message);
    document.getElementById('empty-discover').style.display = 'block';
  } finally {
    setLoading('forge', false);
  }
}

function renderDiscoverResults(data) {
  const tools = data.discovered_tools || [];
  const actions = data.recommended_actions || [];
  const actionMap = {};
  actions.forEach(a => { actionMap[a.tool_name] = a; });

  document.getElementById('stat-total').textContent = tools.length;
  document.getElementById('stat-entities').textContent = data.raw_entity_count || tools.length;
  document.getElementById('stat-actions').textContent = actions.length;
  document.getElementById('status-row').style.display = 'flex';

  if (tools.length === 0) {
    document.getElementById('cards-area').style.display = 'none';
    document.getElementById('empty-discover').style.display = 'block';
    document.getElementById('empty-discover').querySelector('p').textContent =
      'No tools discovered. Try a different URL.';
    return;
  }

  const colors = ['#4CAF50','#2196F3','#9C27B0','#FF9800','#00BCD4','#E91E63','#8BC34A','#F44336','#795548','#607D8B','#3F51B5','#FF5722'];
  const grid = document.getElementById('cards-grid');
  grid.innerHTML = '';

  tools.forEach((tool, i) => {
    const action = actionMap[tool.name] || {};
    const color = colors[i % colors.length];
    const tag = tool.has_free_tier ? '<span class="tag green">Free tier</span>' : '';
    const caps = (tool.capabilities || []).slice(0,4).map(c => `<span class="cap">${c}</span>`).join('');
    const state = toolStates[tool.name] || {};
    const stateClass = state.status === 'integrated' ? ' integrated' : state.status === 'dismissed' ? ' dismissed' : '';
    const badgeHtml = state.status ? `<span class="card-status-badge badge-${state.status}">${state.status}</span>` : '';
    grid.innerHTML += `
      <div class="card${stateClass}" id="card-${i}" style="--card-accent:${color}">
        ${badgeHtml}
        <div class="card-header" style="cursor:pointer" onclick='openToolModal(${JSON.stringify(tool).replace(/'/g,"&#39;")})'>
          <div>
            <div class="card-name">${esc(tool.name)}</div>
            <div class="card-vendor">${esc(tool.vendor || 'Click to research')}</div>
          </div>
          ${tag}
        </div>
        <div class="card-desc" style="cursor:pointer" onclick='openToolModal(${JSON.stringify(tool).replace(/'/g,"&#39;")})'>${esc(tool.description || 'Click to deep-research this tool with Tavily + Reka AI.')}</div>
        ${caps ? `<div class="caps">${caps}</div>` : ''}
        <div class="card-actions">
          <button class="card-btn card-btn-research" onclick='event.stopPropagation();openToolModal(${JSON.stringify(tool).replace(/'/g,"&#39;")})'>Research</button>
          <button class="card-btn card-btn-getkey" onclick="event.stopPropagation();quickGetKey('${esc(tool.name)}','${esc(tool.api_url || tool.vendor || tool.name)}')">Get Key</button>
          <button class="card-btn card-btn-integrate" onclick="event.stopPropagation();quickIntegrate('${esc(tool.name)}')">Integrate</button>
          <button class="card-btn card-btn-dismiss" onclick="event.stopPropagation();quickDismiss('${esc(tool.name)}',${i})">Dismiss</button>
        </div>
      </div>`;
  });

  document.getElementById('cards-title').textContent =
    `Discovered ${tools.length} Tool${tools.length !== 1 ? 's' : ''}` +
    (data.page_title ? ` from "${data.page_title}"` : '');
  document.getElementById('cards-area').style.display = 'block';
}

// ── Graph ──────────────────────────────────────────────────────────────────
let network = null;

async function loadGraph() {
  document.getElementById('graph-node-count').textContent = 'Loading...';
  try {
    const res = await fetch('/api/graph');
    const data = await res.json();
    renderGraph(data);
  } catch(e) {
    document.getElementById('graph-node-count').textContent = 'Error loading graph';
  }
}

function renderGraph(data) {
  const container = document.getElementById('graph-container');
  const nodes = new vis.DataSet(data.nodes);
  const edges = new vis.DataSet(data.edges);

  const options = {
    physics: {
      enabled: true,
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -8000,
        centralGravity: 0.3,
        springLength: 120,
        springConstant: 0.04,
        damping: 0.09,
        avoidOverlap: 0.2
      },
      stabilization: { iterations: 180, fit: true }
    },
    nodes: {
      shape: 'dot',
      borderWidth: 2,
      borderWidthSelected: 3,
      font: { color: '#c9d1d9', size: 13, face: 'Segoe UI, system-ui, sans-serif' },
      shadow: { enabled: true, color: 'rgba(0,0,0,0.5)', size: 8, x: 2, y: 2 }
    },
    edges: {
      width: 1.5,
      selectionWidth: 3,
      arrows: { to: { enabled: true, scaleFactor: 0.6 } },
      font: { color: '#8b949e', size: 10, align: 'middle', strokeWidth: 0 },
      smooth: { type: 'dynamic' }
    },
    interaction: {
      hover: true,
      tooltipDelay: 150,
      navigationButtons: false,
      keyboard: true,
      zoomView: true
    },
    groups: {
      engine:     { color: { background: '#1a0014', border: '#E91E63' }, shape: 'hexagon' },
      vendor:     { color: { background: '#0d1f0d', border: '#4CAF50' }, shape: 'dot' },
      capability: { color: { background: '#0a1628', border: '#37474F' }, shape: 'diamond' }
    },
    background: { color: '#0d1117' }
  };

  if (network) network.destroy();
  network = new vis.Network(container, { nodes, edges }, options);
  network.on('stabilizationIterationsDone', () => {
    network.setOptions({ physics: { enabled: false } });
  });
  document.getElementById('graph-node-count').textContent =
    `${data.nodes.length} nodes · ${data.edges.length} edges`;
}

// ── Sponsors ───────────────────────────────────────────────────────────────
async function loadSponsors() {
  try {
    const res = await fetch('/api/sponsors');
    const sponsors = await res.json();
    const icons = {
      search:'&#128269;', movie:'&#127909;', flash_on:'&#9889;',
      account_tree:'&#127968;', open_in_browser:'&#127760;', storage:'&#128190;',
      mic:'&#127908;', sync:'&#128257;', cloud_upload:'&#9729;',
      dns:'&#128225;', psychology:'&#129504;', bar_chart:'&#128202;'
    };
    const grid = document.getElementById('sponsors-grid');
    grid.innerHTML = '';
    sponsors.forEach(s => {
      const icon = icons[s.icon] || '&#9733;';
      let statusClass, statusText;
      if (s.status === 'configured') { statusClass = 'status-configured'; statusText = 'Configured'; }
      else if (s.status === 'discovered') { statusClass = 'status-discovered'; statusText = 'Discovered'; }
      else { statusClass = 'status-pending'; statusText = 'Pending'; }
      grid.innerHTML += `
        <div class="sponsor-card">
          <div class="sponsor-icon" style="background:${s.color}20;border:1px solid ${s.color}40">
            <span>${icon}</span>
          </div>
          <div class="sponsor-info">
            <div class="sponsor-name">${esc(s.name)}</div>
            <div class="sponsor-role">${esc(s.role)}</div>
            <div class="sponsor-status ${statusClass}">${statusText}</div>
          </div>
        </div>`;
    });
  } catch(e) {
    console.error('Failed to load sponsors', e);
  }
}

// ── Video Intel ────────────────────────────────────────────────────────────
async function runVideoAnalyze() {
  const url = document.getElementById('video-url-input').value.trim();
  if (!url) { alert('Please enter a video URL.'); return; }
  setLoading('video', true);
  document.getElementById('video-error').style.display = 'none';
  document.getElementById('video-cards-area').style.display = 'none';
  document.getElementById('empty-video').style.display = 'none';
  try {
    const res = await fetch('/api/analyze-video', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    renderVideoResults(data);
  } catch(e) {
    showError('video-error', e.message);
    document.getElementById('empty-video').style.display = 'block';
  } finally {
    setLoading('video', false);
  }
}

function renderVideoResults(data) {
  const tools = data.tools_found || [];
  const methods = data.methods_found || [];
  const grid = document.getElementById('video-cards-grid');
  grid.innerHTML = '';

  const colors = ['#9C27B0','#2196F3','#4CAF50','#FF9800','#E91E63','#00BCD4'];

  tools.forEach((toolName, i) => {
    const color = colors[i % colors.length];
    grid.innerHTML += `
      <div class="card" style="--card-accent:${color}">
        <div class="card-header">
          <div class="card-name">${esc(toolName)}</div>
          <span class="tag">Discovered</span>
        </div>
        <div class="card-desc">Mentioned in video — extracted via Reka AI visual + audio analysis.</div>
      </div>`;
  });

  methods.forEach((m, i) => {
    const color = colors[(i + 3) % colors.length];
    const toolsUsed = (m.tools_used || []).slice(0,3).map(t => `<span class="cap">${esc(t)}</span>`).join('');
    grid.innerHTML += `
      <div class="card" style="--card-accent:${color}">
        <div class="card-header">
          <div class="card-name">${esc(m.name || 'Method')}</div>
          <span class="tag" style="background:rgba(33,150,243,0.15);color:#2196F3">Method</span>
        </div>
        <div class="card-desc">${esc(m.description || '')}</div>
        ${toolsUsed ? `<div class="caps">${toolsUsed}</div>` : ''}
      </div>`;
  });

  if (tools.length === 0 && methods.length === 0) {
    document.getElementById('empty-video').style.display = 'block';
    document.getElementById('empty-video').querySelector('p').textContent =
      data.error ? `Error: ${data.error}` : 'No tools found. Try a public video URL.';
    return;
  }

  document.getElementById('video-title-label').textContent =
    `Found ${tools.length} tool(s) and ${methods.length} method(s)` +
    (data.title ? ` in "${data.title}"` : '');
  document.getElementById('video-cards-area').style.display = 'block';
}

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function setLoading(id, on) {
  document.getElementById(id + '-btn').disabled = on;
  document.getElementById(id + '-label').style.opacity = on ? 0 : 1;
  document.getElementById(id + '-spinner').style.display = on ? 'inline-block' : 'none';
}

function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = 'Error: ' + msg;
  el.style.display = 'block';
}

// ── Tool Modal ─────────────────────────────────────────────────────────────
async function openToolModal(tool) {
  currentTool = tool;
  const modal = document.getElementById('tool-modal');
  document.getElementById('modal-name').textContent = tool.name;
  document.getElementById('modal-vendor').textContent = tool.vendor || 'Vendor unknown — researching...';

  // Reset sections
  ['modal-summary-section','modal-answer-section','modal-caps-section',
   'modal-sources-section','modal-integration-section','modal-history-section'].forEach(
    id => document.getElementById(id).style.display = 'none'
  );
  document.getElementById('modal-loading').style.display = 'block';
  document.getElementById('modal-actions').style.display = 'flex';
  modal.classList.add('open');

  // Show existing caps if any
  if (tool.capabilities && tool.capabilities.length) {
    document.getElementById('modal-caps').innerHTML =
      tool.capabilities.map(c => `<span class="cap">${esc(c)}</span>`).join('');
    document.getElementById('modal-caps-section').style.display = 'block';
  }

  // Check state
  const state = toolStates[tool.name];
  if (state && state.status === 'integrated') {
    document.getElementById('modal-actions').innerHTML =
      '<span style="color:var(--green);font-weight:600">Integrated into harness</span>';
  } else if (state && state.status === 'dismissed') {
    document.getElementById('modal-actions').innerHTML =
      '<span style="color:var(--muted)">Dismissed</span>';
  }

  // Fetch research + tool details in parallel
  try {
    const [researchRes, detailRes] = await Promise.all([
      fetch('/api/research-tool', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name: tool.name, vendor: tool.vendor || ''})
      }),
      fetch(`/api/tool/${encodeURIComponent(tool.name)}`)
    ]);
    const research = await researchRes.json();
    const detail = await detailRes.json();

    document.getElementById('modal-loading').style.display = 'none';

    // AI Summary
    if (research.ai_summary) {
      document.getElementById('modal-summary').textContent = research.ai_summary;
      document.getElementById('modal-summary-section').style.display = 'block';
    }

    // Answer
    if (research.answer) {
      document.getElementById('modal-answer').textContent = research.answer;
      document.getElementById('modal-answer-section').style.display = 'block';
    }

    // Sources
    if (research.sources && research.sources.length) {
      document.getElementById('modal-sources').innerHTML = research.sources.map(s =>
        `<li><a href="${esc(s.url)}" target="_blank">${esc(s.title)}</a><div class="source-snippet">${esc(s.snippet)}</div></li>`
      ).join('');
      document.getElementById('modal-sources-section').style.display = 'block';
    }

    // Integration sources
    if (research.integration_sources && research.integration_sources.length) {
      document.getElementById('modal-integration-sources').innerHTML = research.integration_sources.map(s =>
        `<li><a href="${esc(s.url)}" target="_blank">${esc(s.title)}</a><div class="source-snippet">${esc(s.snippet)}</div></li>`
      ).join('');
      document.getElementById('modal-integration-section').style.display = 'block';
    }

    // Capabilities from Neo4j
    if (detail.capabilities && detail.capabilities.length) {
      document.getElementById('modal-caps').innerHTML =
        detail.capabilities.map(c => `<span class="cap">${esc(c)}</span>`).join('');
      document.getElementById('modal-caps-section').style.display = 'block';
    }

    // Discovery history
    if (detail.discovery_events && detail.discovery_events.length) {
      document.getElementById('modal-history').innerHTML = detail.discovery_events.map(e =>
        `<li>Discovered from <strong>${esc(e.url || 'unknown')}</strong> via ${esc(e.engine_used || 'unknown')} (${esc(e.source_type || '')})</li>`
      ).join('');
      document.getElementById('modal-history-section').style.display = 'block';
    }

    // Update vendor if found
    if (detail.vendor) {
      document.getElementById('modal-vendor').textContent = detail.vendor;
    }

    toolStates[tool.name] = { ...toolStates[tool.name], status: 'researched', data: { ...research, ...detail } };

  } catch(e) {
    document.getElementById('modal-loading').style.display = 'none';
    document.getElementById('modal-answer').textContent = 'Research failed: ' + e.message;
    document.getElementById('modal-answer-section').style.display = 'block';
  }
}

function closeModal() {
  document.getElementById('tool-modal').classList.remove('open');
  currentTool = null;
}

async function integrateTool() {
  if (!currentTool) return;
  const name = currentTool.name;
  document.getElementById('modal-actions').innerHTML =
    '<span style="color:var(--yellow)"><span class="spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:8px"></span>Agent integrating... check Activity tab</span>';
  try {
    const res = await fetch('/api/integrate-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, method: 'mcp'})
    });
    const data = await res.json();
    toolStates[name] = { ...toolStates[name], status: 'integrated' };
    let filesInfo = '';
    if (data.files_created && data.files_created.length) {
      filesInfo = `<br><span style="font-size:12px;color:var(--muted)">${data.files_created.length} files: ${data.files_created.join(', ')}</span>`;
    }
    document.getElementById('modal-actions').innerHTML =
      `<span style="color:var(--green);font-weight:600">Integrated! ${esc(data.message || '')}${filesInfo}</span>`;
    // Update card visually
    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector('.card-name')?.textContent === name) {
        card.classList.add('integrated');
        const badge = card.querySelector('.card-status-badge');
        if (badge) { badge.className = 'card-status-badge badge-integrated'; badge.textContent = 'integrated'; }
        else { card.insertAdjacentHTML('afterbegin', '<span class="card-status-badge badge-integrated">integrated</span>'); }
      }
    });
  } catch(e) {
    document.getElementById('modal-actions').innerHTML =
      `<span style="color:var(--red)">Integration failed: ${esc(e.message)}</span>`;
  }
}

async function dismissTool() {
  if (!currentTool) return;
  const name = currentTool.name;
  try {
    await fetch('/api/dismiss-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, reason: 'User dismissed from UI'})
    });
    toolStates[name] = { ...toolStates[name], status: 'dismissed' };
    closeModal();
    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector('.card-name')?.textContent === name) {
        card.classList.add('dismissed');
      }
    });
  } catch(e) {
    alert('Dismiss failed: ' + e.message);
  }
}

async function quickGetKey(name, vendorUrl) {
  try {
    // Find the button and show loading state
    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector('.card-name')?.textContent === name) {
        const btn = card.querySelector('.card-btn-getkey');
        if (btn) { btn.textContent = 'Acquiring...'; btn.disabled = true; }
      }
    });
    // Switch to Activity tab to watch progress
    switchTab('activity');

    const res = await fetch('/api/auth-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({tool_name: name, vendor_url: vendorUrl})
    });
    const data = await res.json();

    if (data.view_url) {
      window.open(data.view_url, '_blank');
    }

    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector('.card-name')?.textContent === name) {
        const btn = card.querySelector('.card-btn-getkey');
        if (btn) {
          if (data.setup_complete) {
            btn.textContent = 'Key Acquired';
            btn.style.background = 'rgba(76,175,80,0.3)';
            btn.style.color = 'var(--green)';
          } else {
            btn.textContent = 'Get Key';
            btn.disabled = false;
            if (data.manual_steps && data.manual_steps.length > 0) {
              alert('Manual steps needed:\\n' + data.manual_steps.join('\\n'));
            }
          }
        }
      }
    });
  } catch(e) {
    alert('Auth failed: ' + e.message);
    document.querySelectorAll('.card-btn-getkey').forEach(b => { b.textContent = 'Get Key'; b.disabled = false; });
  }
}

async function getToolKey() {
  const name = document.getElementById('modal-title')?.textContent || '';
  const vendorUrl = document.getElementById('modal-url')?.textContent || name;
  const actionsEl = document.getElementById('modal-actions');
  if (actionsEl) {
    actionsEl.innerHTML = '<div class="spinner" style="width:20px;height:20px;display:inline-block"></div> <span style="color:#FFD54F">Yutori acquiring API key...</span>';
  }
  switchTab('activity');
  try {
    const res = await fetch('/api/auth-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({tool_name: name, vendor_url: vendorUrl})
    });
    const data = await res.json();

    if (data.view_url) {
      window.open(data.view_url, '_blank');
    }

    if (data.setup_complete) {
      actionsEl.innerHTML = '<span style="color:var(--green);font-weight:600">API key acquired and stored!</span>';
    } else {
      let msg = 'Could not auto-acquire key.';
      if (data.manual_steps && data.manual_steps.length > 0) {
        msg += ' ' + data.manual_steps[0];
      }
      actionsEl.innerHTML = '<span style="color:#FFD54F">' + esc(msg) + '</span>';
    }
  } catch(e) {
    actionsEl.innerHTML = '<span style="color:var(--red)">Auth failed: ' + esc(e.message) + '</span>';
  }
}

async function quickIntegrate(name) {
  try {
    const res = await fetch('/api/integrate-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, method: 'mcp'})
    });
    const data = await res.json();
    toolStates[name] = { status: 'integrated' };
    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector('.card-name')?.textContent === name) {
        card.classList.add('integrated');
        card.insertAdjacentHTML('afterbegin', '<span class="card-status-badge badge-integrated">integrated</span>');
      }
    });
  } catch(e) { alert('Integration failed: ' + e.message); }
}

async function quickDismiss(name, idx) {
  try {
    await fetch('/api/dismiss-tool', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, reason: 'Quick dismiss from card'})
    });
    toolStates[name] = { status: 'dismissed' };
    const card = document.getElementById('card-' + idx);
    if (card) card.classList.add('dismissed');
  } catch(e) { alert('Dismiss failed: ' + e.message); }
}

// ── Auto Demo ──────────────────────────────────────────────────────────────
let demoRunning = false;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function narrate(title, text) {
  const el = document.getElementById('demo-narration');
  document.getElementById('narr-title').innerHTML = title;
  document.getElementById('narr-text').innerHTML = text;
  el.classList.add('show');
}

function hideNarration() {
  document.getElementById('demo-narration').classList.remove('show');
}

async function typeText(input, text, speed = 45) {
  input.value = '';
  input.focus();
  for (let i = 0; i < text.length; i++) {
    input.value += text[i];
    input.dispatchEvent(new Event('input'));
    await sleep(speed + Math.random() * 30);
  }
}

async function runDemo() {
  if (demoRunning) return;
  demoRunning = true;
  const btn = document.getElementById('demo-btn');
  btn.disabled = true;
  document.getElementById('demo-label').style.opacity = '0.5';
  document.getElementById('demo-label').textContent = 'Running Demo...';

  try {
    // ── Step 1: Intro ──
    narrate(
      "<span class='demo-step-num'>1</span> The Borg \u2014 Tool Discovery",
      "Paste any URL. The Borg autonomously discovers, researches, and integrates every tool mentioned. Analyzing a hackathon page..."
    );
    await sleep(4000);

    // ── Step 2: Type URL ──
    showTab("discover");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>2</span> Scraping a Hackathon Page",
      "Tavily deep-scrapes the page, then Fastino/Reka extract tool entities, and each gets deep-researched."
    );
    const urlInput = document.getElementById("url-input");
    await typeText(urlInput, "https://lu.ma/sfagents");
    await sleep(1500);

    // ── Step 3: Switch to Activity ──
    showTab("activity");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>3</span> Live Pipeline \u2014 Activity Feed",
      "Every step streams here in real time via SSE. Watch the pipeline: scrape \u2192 extract \u2192 research \u2192 graph \u2192 compare."
    );
    clearActivity();
    await sleep(1500);

    // ── Step 4: Fire the analysis ──
    showTab("discover");
    await sleep(300);
    document.getElementById("forge-btn").click();
    await sleep(1000);

    showTab("activity");
    narrate(
      "<span class='demo-step-num'>4</span> Pipeline Running",
      "Tavily is scraping... Fastino/Reka extracting entities... each tool gets deep-researched. Watch the events stream in."
    );

    let waited = 0;
    while (waited < 30000) {
      await sleep(1000);
      waited += 1000;
      if (activityCount > 5) break;
    }
    await sleep(3000);

    // ── Step 5: Show results ──
    showTab("discover");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>5</span> Discovered Tools",
      "Each tool gets a card with research data, capabilities, and an integration recommendation. Click any card to deep-dive."
    );
    await sleep(5000);

    // ── Step 6: Knowledge Graph ──
    showTab("graph");
    await sleep(1000);
    narrate(
      "<span class='demo-step-num'>6</span> Knowledge Graph (Neo4j)",
      "41 nodes, 49 relationships \u2014 tools, vendors, capabilities, and discovery events. All stored in Neo4j Aura with full traceability."
    );
    await sleep(5000);

    // ── Step 7: Sponsors ──
    showTab("sponsors");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>7</span> 12 Sponsor Tools",
      "All 12 hackathon sponsors integrated. Green = configured with live API keys. The Borg uses these tools to integrate more tools."
    );
    await sleep(4000);

    // ── Step 8: Integration ──
    showTab("discover");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>8</span> Agentic Integration",
      "Click Integrate and the AI agent generates a complete MCP server \u2014 server.py, client.py, config \u2014 and wires it into the harness. All autonomous."
    );
    await sleep(5000);

    // ── Step 9: Activity recap ──
    showTab("activity");
    await sleep(500);
    narrate(
      "<span class='demo-step-num'>9</span> Full Observability",
      "Every discovery, research, and integration step is logged and streamed. The graph provides full audit trail. Resistance is futile."
    );
    await sleep(5000);

    // ── Done ──
    hideNarration();
    await sleep(500);
    narrate(
      "Demo Complete",
      "The Borg \u2014 Autonomous Tool Discovery and Integration. Built at the SF Autonomous Agents Hackathon 2025."
    );
    await sleep(4000);
    hideNarration();

  } catch(e) {
    console.error('Demo error:', e);
    hideNarration();
  } finally {
    demoRunning = false;
    btn.disabled = false;
    document.getElementById('demo-label').style.opacity = '1';
    document.getElementById("demo-label").textContent = "\u25B6 Auto Demo";
  }
}

// ── Activity Feed (SSE) ─────────────────────────────────────────────────────
let activityCount = 0;
let evtSource = null;

function connectSSE() {
  evtSource = new EventSource('/api/events');
  const statusEl = document.getElementById('sse-status');

  evtSource.onopen = () => {
    statusEl.textContent = 'Connected';
    statusEl.style.borderColor = 'var(--green)';
    statusEl.style.color = 'var(--green)';
  };

  evtSource.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      appendActivityItem(event);
    } catch(err) {
      console.warn('SSE parse error', err);
    }
  };

  evtSource.onerror = () => {
    statusEl.textContent = 'Reconnecting...';
    statusEl.style.borderColor = 'var(--yellow)';
    statusEl.style.color = 'var(--yellow)';
  };
}

function appendActivityItem(event) {
  const feed = document.getElementById('activity-feed');
  const empty = document.getElementById('activity-empty');
  if (empty) empty.style.display = 'none';

  const time = new Date(event.timestamp).toLocaleTimeString();
  const dotClass = event.event_type || 'step';
  const engineClass = 'engine-' + (event.engine || 'unknown');

  const item = document.createElement('div');
  item.className = 'activity-item';
  item.innerHTML = `
    <span class="activity-time">${esc(time)}</span>
    <span class="activity-dot ${dotClass}"></span>
    <span class="activity-engine ${engineClass}">${esc(event.engine || '?')}</span>
    <span class="activity-msg">${formatActivityMsg(event)}</span>
  `;
  feed.appendChild(item);
  feed.scrollTop = feed.scrollHeight;

  // Update badge count
  activityCount++;
  const badge = document.getElementById('activity-count');
  badge.textContent = activityCount;
  badge.style.display = 'inline';
}

function formatActivityMsg(event) {
  let msg = esc(event.message || '');
  // Highlight tool names and numbers
  msg = msg.replace(/(\d+)/g, '<span class="highlight">$1</span>');
  if (event.step) {
    msg = '<span style="color:var(--muted);font-size:11px">[' + esc(event.step) + ']</span> ' + msg;
  }
  return msg;
}

function clearActivity() {
  const feed = document.getElementById('activity-feed');
  feed.innerHTML = '<div id="activity-empty" style="text-align:center;padding:40px;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">&#9889;</div><p>Cleared. Waiting for new activity...</p></div>';
  activityCount = 0;
  const badge = document.getElementById('activity-count');
  badge.style.display = 'none';
}

// ── Init ───────────────────────────────────────────────────────────────────
connectSSE();
loadSponsors();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the HackForge demo UI."""
    return HTMLResponse(content=DEMO_HTML)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "hackforge"}


@app.get("/api/events")
async def events() -> StreamingResponse:
    """SSE endpoint — streams pipeline events in real time."""
    queue = pipeline_bus.subscribe()

    async def stream():
        try:
            # Send recent history first
            for event in pipeline_bus.history[-20:]:
                yield f"data: {event.to_json()}\n\n"
            # Then stream live events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {event.to_json()}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            pipeline_bus.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/status")
async def status() -> dict[str, Any]:
    """Return harness status — configured providers, key counts, etc."""
    from hackforge.config import HackForgeConfig

    try:
        cfg = HackForgeConfig.load()
    except Exception:
        cfg = None

    configured: list[str] = []
    missing: list[str] = []

    checks = {
        "tavily":   lambda c: bool(c.tavily.api_key),
        "reka":     lambda c: bool(c.reka.api_key),
        "fastino":  lambda c: bool(c.fastino.api_key),
        "neo4j":    lambda c: bool(c.neo4j_uri and c.neo4j_password),
        "yutori":   lambda c: bool(c.yutori.api_key),
        "senso":    lambda c: bool(c.senso.api_key),
        "modulate": lambda c: bool(c.modulate.api_key),
    }

    for name, check in checks.items():
        try:
            (configured if (cfg and check(cfg)) else missing).append(name)
        except Exception:
            missing.append(name)

    return {
        "configured_providers": configured,
        "missing_providers": missing,
        "provider_count": len(configured),
        "total_providers": 12,
        "neo4j_uri": (cfg.neo4j_uri if cfg else "") or "not configured",
        "version": "0.1.0",
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    """Run LinkIntel engine against a URL and return discovered tools."""
    if not req.url.strip():
        raise HTTPException(status_code=422, detail="url must not be empty")

    try:
        from hackforge.config import HackForgeConfig
        from hackforge.engines.link_intel import LinkIntelEngine

        cfg = HackForgeConfig.load()
        engine = LinkIntelEngine(cfg, bus=pipeline_bus)
        report = await engine.analyze_url(req.url)
        return report.model_dump(mode="json")
    except Exception as exc:
        logger.exception("analyze_url failed for %s", req.url)
        # Return a graceful degraded response rather than a 500
        return {
            "url": req.url,
            "page_title": "",
            "discovered_tools": [],
            "existing_alternatives": [],
            "recommended_actions": [],
            "raw_entity_count": 0,
            "error": str(exc),
        }


@app.post("/api/analyze-video")
async def analyze_video(req: AnalyzeVideoRequest) -> dict[str, Any]:
    """Run VideoIntel engine against a YouTube/Instagram URL."""
    if not req.url.strip():
        raise HTTPException(status_code=422, detail="url must not be empty")

    try:
        from hackforge.config import HackForgeConfig
        from hackforge.engines.video_intel import VideoIntelEngine

        cfg = HackForgeConfig.load()
        engine = VideoIntelEngine(cfg)
        analysis = await engine.analyze_video(req.url)
        return analysis.model_dump(mode="json")
    except Exception as exc:
        logger.exception("analyze_video failed for %s", req.url)
        return {
            "url": req.url,
            "title": "",
            "platform": "",
            "tools_found": [],
            "methods_found": [],
            "urls_mentioned": [],
            "luma_links": [],
            "error": str(exc),
        }


@app.get("/api/graph")
async def graph() -> dict[str, Any]:
    """Return Neo4j graph data (or demo data) in vis.js format."""
    try:
        from hackforge.config import HackForgeConfig

        cfg = HackForgeConfig.load()
        if cfg.neo4j_password and cfg.neo4j_uri:
            return await _fetch_neo4j_graph(cfg)
    except Exception as exc:
        logger.warning("Neo4j graph fetch failed, returning demo data: %s", exc)

    return DEMO_GRAPH


async def _fetch_neo4j_graph(cfg: Any) -> dict[str, Any]:
    """Query Neo4j and convert to vis.js node/edge format."""
    try:
        from neo4j import AsyncGraphDatabase  # type: ignore[import]
    except ImportError:
        return DEMO_GRAPH

    driver = AsyncGraphDatabase.driver(
        cfg.neo4j_uri,
        auth=(cfg.neo4j_user, cfg.neo4j_password),
    )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: dict[str, int] = {}
    counter = 1

    def get_id(name: str) -> int:
        nonlocal counter
        if name not in node_ids:
            node_ids[name] = counter
            counter += 1
        return node_ids[name]

    color_map = {
        "Tool":       "#4CAF50",
        "Vendor":     "#2196F3",
        "Capability": "#37474F",
        "Source":     "#FF9800",
    }

    try:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (a)-[r]->(b) RETURN a, r, b, labels(a) AS la, labels(b) AS lb LIMIT 200"
            )
            async for record in result:
                a = record["a"]
                b = record["b"]
                r = record["r"]
                la = record["la"]
                lb = record["lb"]

                a_name = a.get("name", str(a.id))
                b_name = b.get("name", str(b.id))
                a_id = get_id(a_name)
                b_id = get_id(b_name)
                a_label = la[0] if la else "Node"
                b_label = lb[0] if lb else "Node"

                if not any(n["id"] == a_id for n in nodes):
                    nodes.append({
                        "id": a_id,
                        "label": a_name,
                        "group": a_label.lower(),
                        "color": color_map.get(a_label, "#607D8B"),
                        "size": 22,
                        "title": a.get("description", a_name),
                    })
                if not any(n["id"] == b_id for n in nodes):
                    nodes.append({
                        "id": b_id,
                        "label": b_name,
                        "group": b_label.lower(),
                        "color": color_map.get(b_label, "#607D8B"),
                        "size": 18,
                        "title": b.get("description", b_name),
                    })
                edges.append({
                    "from": a_id,
                    "to": b_id,
                    "label": type(r).__name__,
                })
    finally:
        await driver.close()

    return {"nodes": nodes, "edges": edges} if nodes else DEMO_GRAPH


@app.get("/api/sponsors")
async def sponsors() -> list[dict[str, Any]]:
    """Return the 12 hackathon sponsors with their configuration status."""
    result = []
    for s in SPONSORS:
        env_val = os.environ.get(s["env_key"], "")
        if env_val:
            status = "configured"
        elif s["name"] in ("Tavily", "Reka AI", "Fastino", "Neo4j", "Yutori"):
            # Core engines — mark as discovered if not yet keyed
            status = "discovered"
        else:
            status = "pending"
        result.append({**s, "status": status})
    return result


@app.post("/api/research-tool")
async def research_tool(req: ResearchToolRequest) -> dict[str, Any]:
    """Deep-research a discovered tool using Tavily and return enriched info."""
    from hackforge.config import HackForgeConfig
    from hackforge.providers.tavily_client import TavilyClient

    cfg = HackForgeConfig.load()
    results: dict[str, Any] = {"name": req.name, "vendor": req.vendor}

    try:
        async with TavilyClient(cfg.tavily) as client:
            # Search for API docs and capabilities
            resp = await client.search(
                f"{req.name} API documentation pricing features free tier developer",
                max_results=8,
                search_depth="advanced",
            )
            results["answer"] = resp.answer or ""
            results["sources"] = [
                {"title": r.title, "url": r.url, "snippet": r.content[:200]}
                for r in resp.results[:8]
            ]

            # Search for integration guides
            resp2 = await client.search(
                f"{req.name} MCP server integration SDK quickstart",
                max_results=5,
                search_depth="basic",
            )
            results["integration_sources"] = [
                {"title": r.title, "url": r.url, "snippet": r.content[:200]}
                for r in resp2.results[:5]
            ]

        # Try enriching with Reka
        if cfg.reka.api_key:
            try:
                import httpx

                combined_text = results.get("answer", "") + " ".join(
                    s["snippet"] for s in results.get("sources", [])
                )
                async with httpx.AsyncClient(timeout=30) as http:
                    reka_resp = await http.post(
                        f"{cfg.reka.base_url}/chat",
                        headers={
                            "Authorization": f"Bearer {cfg.reka.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "reka-flash",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        f"Based on this research about '{req.name}', provide a structured summary:\n"
                                        f"1. What it does (1 sentence)\n"
                                        f"2. Key capabilities (bullet list)\n"
                                        f"3. Auth type (api_key / oauth / none)\n"
                                        f"4. Has free tier? (yes/no)\n"
                                        f"5. How to integrate (MCP server possible? REST API?)\n\n"
                                        f"Research:\n{combined_text[:3000]}"
                                    ),
                                }
                            ],
                        },
                    )
                    if reka_resp.status_code == 200:
                        reka_data = reka_resp.json()
                        results["ai_summary"] = (
                            reka_data.get("responses", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
            except Exception as exc:
                logger.warning("Reka enrichment failed: %s", exc)

        results["status"] = "researched"

    except Exception as exc:
        logger.exception("research_tool failed for %s", req.name)
        results["error"] = str(exc)
        results["status"] = "failed"

    return results


@app.post("/api/auth-tool")
async def auth_tool(body: dict[str, Any]) -> dict[str, Any]:
    """Trigger AuthForge to acquire an API key for a tool via Yutori browser agent."""
    from hackforge.config import HackForgeConfig
    from hackforge.engines.auth_forge import AuthForgeEngine

    tool_name = body.get("tool_name", "")
    vendor_url = body.get("vendor_url", "")

    if not tool_name:
        return {"error": "tool_name is required"}

    cfg = HackForgeConfig.load()

    await pipeline_bus.emit_step(
        "auth_forge", "start",
        f"AuthForge: acquiring API key for {tool_name}...",
    )

    engine = AuthForgeEngine(cfg, bus=pipeline_bus)
    result = await engine.setup_tool(tool_name, vendor_url or tool_name)

    return {
        "tool_name": result.tool_name,
        "setup_complete": result.setup_complete,
        "api_key_preview": result.api_key[:12] + "..." if result.api_key else "",
        "auth_type": result.auth_type,
        "view_url": result.view_url,
        "dashboard_url": result.dashboard_url,
        "manual_steps": result.manual_steps,
        "error": result.error,
    }


@app.post("/api/integrate-tool")
async def integrate_tool(req: IntegrateToolRequest) -> dict[str, Any]:
    """Run agentic integration — generates MCP server, updates harness, streams events."""
    from hackforge.config import HackForgeConfig
    from hackforge.engines.agent_integrator import AgentIntegrator

    cfg = HackForgeConfig.load()

    # Gather cached research data (from toolStates on the client side)
    research_data: dict[str, Any] = {"name": req.name}

    # Try to get tool info from Neo4j
    if cfg.neo4j_password and cfg.neo4j_uri:
        try:
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(
                cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
            )
            try:
                async with driver.session() as session:
                    r = await session.run(
                        "MATCH (t:Tool {name: $name}) RETURN t", name=req.name
                    )
                    rec = await r.single()
                    if rec:
                        research_data.update(dict(rec["t"]))

                    # Mark as integrated in graph
                    await session.run(
                        """
                        MERGE (t:Tool {name: $name})
                        SET t.integrated = true,
                            t.integration_method = $method,
                            t.integrated_at = datetime()
                        """,
                        name=req.name,
                        method=req.method,
                    )
                    await session.run(
                        """
                        MATCH (t:Tool {name: $name})
                        CREATE (ie:IntegrationEvent {
                            timestamp: datetime(),
                            method: $method,
                            status: 'success',
                            api_key_obtained: false
                        })
                        CREATE (t)-[:INTEGRATED_VIA]->(ie)
                        """,
                        name=req.name,
                        method=req.method,
                    )
            finally:
                await driver.close()
        except Exception as exc:
            logger.warning("Neo4j lookup/store failed: %s", exc)

    # Run the agentic integrator (generates MCP server, updates harness)
    agent = AgentIntegrator(cfg, pipeline_bus)
    integration_result = await agent.integrate(req.name, research_data)

    return {
        "name": req.name,
        "method": req.method,
        "status": integration_result.status,
        "message": f"{req.name} integrated via {req.method}",
        "files_created": integration_result.files_created,
        "output_dir": integration_result.output_dir,
        "mcp_command": integration_result.mcp_command,
        "settings_updated": integration_result.settings_updated,
        "error": integration_result.error,
    }


@app.post("/api/dismiss-tool")
async def dismiss_tool(req: DismissToolRequest) -> dict[str, Any]:
    """Dismiss a discovered tool — mark it as skipped in the graph."""
    from hackforge.config import HackForgeConfig

    cfg = HackForgeConfig.load()

    if cfg.neo4j_password and cfg.neo4j_uri:
        try:
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(
                cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
            )
            try:
                async with driver.session() as session:
                    await session.run(
                        """
                        MERGE (t:Tool {name: $name})
                        SET t.dismissed = true,
                            t.dismiss_reason = $reason,
                            t.dismissed_at = datetime()
                        """,
                        name=req.name,
                        reason=req.reason,
                    )
            finally:
                await driver.close()
        except Exception as exc:
            logger.warning("Neo4j dismiss failed: %s", exc)

    return {"name": req.name, "status": "dismissed", "reason": req.reason}


@app.get("/api/tool/{name}")
async def get_tool(name: str) -> dict[str, Any]:
    """Get full details for a tool from Neo4j."""
    from hackforge.config import HackForgeConfig

    cfg = HackForgeConfig.load()
    tool_data: dict[str, Any] = {"name": name}

    def _serialize(obj: Any) -> Any:
        """Convert neo4j types to JSON-safe values."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "to_native"):
            return str(obj.to_native())
        return obj

    if cfg.neo4j_password and cfg.neo4j_uri:
        try:
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(
                cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
            )
            try:
                async with driver.session() as session:
                    # Get tool properties
                    r = await session.run(
                        "MATCH (t:Tool {name: $name}) RETURN t", name=name
                    )
                    record = await r.single()
                    if record:
                        props = dict(record["t"])
                        tool_data.update({k: _serialize(v) for k, v in props.items()})

                    # Get vendor
                    r = await session.run(
                        "MATCH (v:Vendor)-[:OFFERS]->(t:Tool {name: $name}) RETURN v.name AS vendor",
                        name=name,
                    )
                    rec = await r.single()
                    if rec:
                        tool_data["vendor"] = rec["vendor"]

                    # Get capabilities
                    r = await session.run(
                        "MATCH (t:Tool {name: $name})-[:PROVIDES]->(c:Capability) RETURN c.name AS cap",
                        name=name,
                    )
                    caps = [rec["cap"] async for rec in r]
                    tool_data["capabilities"] = caps

                    # Get discovery events
                    r = await session.run(
                        """
                        MATCH (t:Tool {name: $name})-[:DISCOVERED_FROM]->(de:DiscoveryEvent)
                        RETURN de ORDER BY de.timestamp DESC LIMIT 5
                        """,
                        name=name,
                    )
                    events = []
                    async for rec in r:
                        de = dict(rec["de"])
                        # Convert neo4j datetime to string
                        for k, v in de.items():
                            if hasattr(v, "isoformat"):
                                de[k] = v.isoformat()
                        events.append(de)
                    tool_data["discovery_events"] = events

            finally:
                await driver.close()
        except Exception as exc:
            logger.warning("Neo4j tool lookup failed: %s", exc)
            tool_data["error"] = str(exc)

    return tool_data
