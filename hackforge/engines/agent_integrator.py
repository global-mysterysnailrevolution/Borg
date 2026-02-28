"""Agent Integrator — Claude-powered autonomous tool integration.

When a user clicks "Integrate" on a discovered tool, this engine:
  1. Gathers all research data (Tavily sources, Reka summary, capabilities).
  2. Calls Claude API to generate MCP server code, REST client, and config.
  3. Writes generated files to ``mcp-servers/{tool}-mcp/``.
  4. Updates ``.claude/settings.json`` with the new MCP server entry.
  5. Updates ``tool-broker.md`` with a new entry.
  6. Emits progress events to the pipeline bus at every step.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig
from hackforge.pipeline_bus import PipelineBus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class IntegrationResult(BaseModel):
    """Result of an agentic integration run."""

    tool_name: str
    status: str = "pending"  # "pending" | "running" | "success" | "failed" | "skipped"
    files_created: list[str] = Field(default_factory=list)
    output_dir: str = ""
    mcp_command: str = ""
    settings_updated: bool = False
    broker_updated: bool = False
    error: str | None = None
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AgentIntegrator:
    """Uses Claude API to autonomously generate tool integrations.

    Falls back to template-based generation (via ToolForgeEngine) when
    the Anthropic API key is not configured.

    Usage::

        config = HackForgeConfig.load()
        bus = PipelineBus()
        agent = AgentIntegrator(config, bus)
        result = await agent.integrate(
            tool_name="Stripe",
            research_data={"answer": "...", "sources": [...], ...},
        )
    """

    def __init__(self, config: HackForgeConfig, bus: PipelineBus) -> None:
        self._config = config
        self._bus = bus
        self._client: Any = None

    async def _ensure_client(self) -> bool:
        """Try to create an Anthropic client. Returns True if successful."""
        if self._client is not None:
            return True

        api_key = self._config.anthropic.api_key if hasattr(self._config, "anthropic") else ""
        if not api_key:
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not api_key:
            return False

        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            return True
        except ImportError:
            logger.warning("anthropic package not installed — using template fallback")
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def integrate(
        self,
        tool_name: str,
        research_data: dict[str, Any],
    ) -> IntegrationResult:
        """Run the full agentic integration pipeline.

        Args:
            tool_name: Name of the tool to integrate.
            research_data: Research data from Tavily + Reka (answer, sources,
                ai_summary, capabilities, etc.).

        Returns:
            An :class:`IntegrationResult` describing what was created.
        """
        result = IntegrationResult(tool_name=tool_name, status="running")

        await self._bus.emit_agent(
            "start", f"Starting integration of {tool_name}..."
        )

        has_claude = await self._ensure_client()

        if has_claude:
            await self._bus.emit_agent(
                "init", "Claude API connected — using AI-powered integration"
            )
            result = await self._claude_integrate(tool_name, research_data, result)
        else:
            await self._bus.emit_agent(
                "init",
                "No Anthropic API key — using template-based integration",
            )
            result = await self._template_integrate(tool_name, research_data, result)

        return result

    # ------------------------------------------------------------------
    # Claude-powered integration
    # ------------------------------------------------------------------

    async def _claude_integrate(
        self,
        tool_name: str,
        research_data: dict[str, Any],
        result: IntegrationResult,
    ) -> IntegrationResult:
        """Generate integration code using Claude API."""
        slug = self._slugify(tool_name)
        env_var = f"{slug.upper().replace('-', '_')}_API_KEY"

        # Step 1: Assemble context
        await self._bus.emit_agent(
            "research", f"Assembling research context for {tool_name}..."
        )
        context = self._build_context(tool_name, research_data)

        # Step 2: Generate MCP server via Claude
        await self._bus.emit_agent(
            "generating", f"Claude is writing MCP server code for {tool_name}..."
        )

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": self._build_prompt(tool_name, slug, env_var, context),
                    }
                ],
            )

            raw_text = response.content[0].text
            files = self._parse_generated_files(raw_text, tool_name, slug, env_var)

            await self._bus.emit_agent(
                "generated",
                f"Claude generated {len(files)} files for {tool_name}",
                {"file_count": len(files), "files": list(files.keys())},
            )

        except Exception as exc:
            logger.warning("Claude generation failed: %s — using template fallback", exc)
            await self._bus.emit_error(
                "agent", "generating", f"Claude API error: {exc} — falling back to templates"
            )
            return await self._template_integrate(tool_name, research_data, result)

        # Step 3: Write files
        output_dir = self._config.project_root / "mcp-servers" / f"{slug}-mcp"
        output_dir.mkdir(parents=True, exist_ok=True)

        await self._bus.emit_agent(
            "writing", f"Writing {len(files)} files to mcp-servers/{slug}-mcp/"
        )

        for filename, content in files.items():
            (output_dir / filename).write_text(content, encoding="utf-8")
            result.files_created.append(filename)

        result.output_dir = str(output_dir)

        # Step 4: Update harness
        await self._bus.emit_agent(
            "harness", "Updating settings.json and tool-broker.md..."
        )

        try:
            self._update_settings_json(tool_name, slug, env_var, output_dir)
            result.settings_updated = True
            await self._bus.emit_agent(
                "settings", f"Added {tool_name} MCP server to settings.json"
            )
        except Exception as exc:
            logger.warning("settings.json update failed: %s", exc)
            await self._bus.emit_error(
                "agent", "settings", f"settings.json update failed: {exc}"
            )

        try:
            self._update_tool_broker(tool_name, slug, research_data)
            result.broker_updated = True
            await self._bus.emit_agent(
                "broker", f"Added {tool_name} entry to tool-broker.md"
            )
        except Exception as exc:
            logger.warning("tool-broker.md update failed: %s", exc)

        # Step 5: Done
        result.status = "success"
        result.mcp_command = f"cd {output_dir} && uv run python server.py"
        result.completed_at = datetime.now(timezone.utc).isoformat()

        await self._bus.emit_agent(
            "complete",
            f"{tool_name} fully integrated! {len(files)} files written.",
            {
                "output_dir": str(output_dir),
                "files": result.files_created,
                "mcp_command": result.mcp_command,
            },
        )

        return result

    # ------------------------------------------------------------------
    # Template-based fallback (no Claude API key)
    # ------------------------------------------------------------------

    async def _template_integrate(
        self,
        tool_name: str,
        research_data: dict[str, Any],
        result: IntegrationResult,
    ) -> IntegrationResult:
        """Generate integration using the existing ToolForgeEngine templates."""
        await self._bus.emit_agent(
            "template", f"Generating {tool_name} integration from templates..."
        )

        slug = self._slugify(tool_name)
        env_var = f"{slug.upper().replace('-', '_')}_API_KEY"

        # Build minimal files from templates
        base_url = research_data.get("api_url", f"https://api.{slug}.com/v1")
        auth_type = research_data.get("auth_type", "bearer")
        description = research_data.get("ai_summary", "") or research_data.get("answer", "")
        if len(description) > 200:
            description = description[:200] + "..."

        files = self._generate_template_files(
            tool_name, slug, env_var, base_url, auth_type, description
        )

        output_dir = self._config.project_root / "mcp-servers" / f"{slug}-mcp"
        output_dir.mkdir(parents=True, exist_ok=True)

        await self._bus.emit_agent(
            "writing", f"Writing {len(files)} files to mcp-servers/{slug}-mcp/"
        )

        for filename, content in files.items():
            (output_dir / filename).write_text(content, encoding="utf-8")
            result.files_created.append(filename)

        result.output_dir = str(output_dir)

        # Update harness files
        try:
            self._update_settings_json(tool_name, slug, env_var, output_dir)
            result.settings_updated = True
        except Exception as exc:
            logger.warning("settings.json update failed: %s", exc)

        try:
            self._update_tool_broker(tool_name, slug, research_data)
            result.broker_updated = True
        except Exception as exc:
            logger.warning("tool-broker.md update failed: %s", exc)

        result.status = "success"
        result.mcp_command = f"cd {output_dir} && uv run python server.py"
        result.completed_at = datetime.now(timezone.utc).isoformat()

        await self._bus.emit_agent(
            "complete",
            f"{tool_name} integrated via templates. {len(files)} files written.",
            {"output_dir": str(output_dir), "files": result.files_created},
        )

        return result

    # ------------------------------------------------------------------
    # Claude prompt
    # ------------------------------------------------------------------

    def _build_context(self, tool_name: str, research_data: dict[str, Any]) -> str:
        """Assemble research context for the Claude prompt."""
        parts: list[str] = []

        if research_data.get("ai_summary"):
            parts.append(f"AI Summary:\n{research_data['ai_summary']}")
        if research_data.get("answer"):
            parts.append(f"Research Answer:\n{research_data['answer']}")
        if research_data.get("sources"):
            sources = research_data["sources"][:5]
            source_text = "\n".join(
                f"  - {s.get('title', 'N/A')}: {s.get('snippet', '')}"
                for s in sources
            )
            parts.append(f"Sources:\n{source_text}")
        if research_data.get("capabilities"):
            parts.append(f"Capabilities: {', '.join(research_data['capabilities'])}")

        return "\n\n".join(parts) if parts else f"Tool name: {tool_name}"

    def _build_prompt(
        self, tool_name: str, slug: str, env_var: str, context: str
    ) -> str:
        return f"""\
You are generating a complete MCP (Model Context Protocol) server for '{tool_name}'.

Based on the research below, generate the following files. Output each file
in a fenced code block with the filename as the info string.

Files to generate:
1. `server.py` — FastMCP server with tools for each API endpoint
2. `client.py` — Async httpx REST client
3. `pyproject.toml` — Package config with dependencies
4. `README.md` — Quick-start docs

Conventions:
- Use `mcp.server.fastmcp.FastMCP` for the MCP server
- Use `httpx.AsyncClient` for the REST client
- API key env var: `{env_var}`
- Package name: `{slug}-mcp`
- Include error handling and type hints
- The client should handle auth headers automatically
- Each significant API action should be a separate MCP tool

Research context:
{context}

Generate all 4 files now. Use ```filename.ext as the fence info string."""

    def _parse_generated_files(
        self, text: str, tool_name: str, slug: str, env_var: str
    ) -> dict[str, str]:
        """Parse Claude's response into filename→content pairs."""
        files: dict[str, str] = {}
        # Match ```filename.ext ... ``` blocks
        pattern = re.compile(
            r"```(\S+\.(?:py|toml|md))\s*\n(.*?)```",
            re.DOTALL,
        )
        for match in pattern.finditer(text):
            filename = match.group(1)
            content = match.group(2)
            files[filename] = content

        # If parsing failed, fall back to template generation
        if not files:
            logger.warning("Could not parse Claude output — using template fallback")
            base_url = f"https://api.{slug}.com/v1"
            files = self._generate_template_files(
                tool_name, slug, env_var, base_url, "bearer", ""
            )

        return files

    # ------------------------------------------------------------------
    # Template file generation (fallback)
    # ------------------------------------------------------------------

    def _generate_template_files(
        self,
        tool_name: str,
        slug: str,
        env_var: str,
        base_url: str,
        auth_type: str,
        description: str,
    ) -> dict[str, str]:
        """Generate MCP server files from inline templates."""
        class_name = self._to_class_name(tool_name)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        auth_header_value = (
            'f"Bearer {self._api_key}"'
            if auth_type in ("bearer", "oauth")
            else 'f"{self._api_key}"'
        )

        server_py = f'''\
"""MCP Server for {tool_name}.

Auto-generated by HackForge AgentIntegrator on {now}.
"""
from __future__ import annotations

import os
from mcp.server.fastmcp import FastMCP
from client import {class_name}Client

mcp = FastMCP(
    name="{tool_name} MCP",
    version="0.1.0",
    description="{description[:100] or tool_name + ' API integration'}",
)

_client: {class_name}Client | None = None


@mcp.startup()
async def _startup() -> None:
    global _client
    api_key = os.environ.get("{env_var}", "")
    if not api_key:
        raise RuntimeError("{env_var} not set")
    _client = {class_name}Client(api_key=api_key)


@mcp.shutdown()
async def _shutdown() -> None:
    if _client:
        await _client.close()


@mcp.tool()
async def ping() -> dict:
    """Health check — verify the API key works."""
    assert _client is not None
    return await _client.request("GET", "/")


@mcp.tool()
async def search(query: str) -> dict:
    """Search or query the {tool_name} API."""
    assert _client is not None
    return await _client.request("POST", "/search", {{"query": query}})


if __name__ == "__main__":
    mcp.run()
'''

        client_py = f'''\
"""Async REST client for {tool_name}.

Auto-generated by HackForge AgentIntegrator on {now}.
"""
from __future__ import annotations

from typing import Any
import httpx


class {class_name}Client:
    BASE_URL = "{base_url}"

    def __init__(self, api_key: str, base_url: str = "", timeout: int = 30) -> None:
        self._api_key = api_key
        self._base_url = base_url or self.BASE_URL
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    async def _ensure(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={{
                    "Authorization": {auth_header_value},
                    "Content-Type": "application/json",
                }},
            )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await self._ensure()
        assert self._http is not None
        params = params or {{}}
        if method.upper() in ("GET", "DELETE"):
            resp = await self._http.request(method, path, params=params)
        else:
            resp = await self._http.request(method, path, json=params)
        resp.raise_for_status()
        return resp.json()
'''

        pyproject_toml = f'''\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{slug}-mcp"
version = "0.1.0"
description = "MCP server for {tool_name} — auto-generated by HackForge"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0",
    "httpx>=0.27",
    "pydantic>=2.0",
]

[project.scripts]
serve = "server:main"
'''

        readme_md = f'''\
# {tool_name} MCP Server

> Auto-generated by HackForge AgentIntegrator on {now}.

{description or f"MCP server for the {tool_name} API."}

## Quick Start

```bash
export {env_var}=your-key-here
uv pip install -e .
uv run python server.py
```

## Add to Claude Code

```json
{{
  "mcpServers": {{
    "{slug}": {{
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "mcp-servers/{slug}-mcp",
      "env": {{
        "{env_var}": "${{{env_var}}}"
      }}
    }}
  }}
}}
```
'''

        return {
            "server.py": server_py,
            "client.py": client_py,
            "pyproject.toml": pyproject_toml,
            "README.md": readme_md,
        }

    # ------------------------------------------------------------------
    # Harness update helpers
    # ------------------------------------------------------------------

    def _update_settings_json(
        self, tool_name: str, slug: str, env_var: str, output_dir: Path
    ) -> None:
        """Add the new MCP server to .claude/settings.json."""
        settings_path = self._config.project_root / ".claude" / "settings.json"
        if not settings_path.exists():
            return

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        mcp_servers = settings.setdefault("mcpServers", {})

        if slug not in mcp_servers:
            mcp_servers[slug] = {
                "command": "uv",
                "args": ["run", "python", "server.py"],
                "cwd": str(output_dir),
                "env": {env_var: f"${{{env_var}}}"},
            }
            settings_path.write_text(
                json.dumps(settings, indent=2) + "\n", encoding="utf-8"
            )
            logger.info("Added %s to settings.json mcpServers", slug)

    def _update_tool_broker(
        self, tool_name: str, slug: str, research_data: dict[str, Any]
    ) -> None:
        """Append entry to tool-broker.md."""
        broker_path = self._config.project_root / "tool-broker.md"
        if not broker_path.exists():
            broker_path.write_text(
                "# Harness Tool Broker\n\n"
                "Auto-managed by HackForge. Each entry is an integrated MCP tool.\n\n",
                encoding="utf-8",
            )

        existing = broker_path.read_text(encoding="utf-8")
        if f"## {tool_name}" in existing:
            return

        description = research_data.get("ai_summary", "") or research_data.get("answer", "")
        if len(description) > 150:
            description = description[:150] + "..."

        entry = (
            f"\n## {tool_name}\n\n"
            f"- **MCP server**: `mcp-servers/{slug}-mcp/`\n"
            f"- **Description**: {description or 'Auto-integrated by HackForge'}\n"
            f"- **Added**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"- **Method**: agentic (Claude API)\n"
        )

        with broker_path.open("a", encoding="utf-8") as f:
            f.write(entry)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    @staticmethod
    def _to_class_name(name: str) -> str:
        return "".join(
            word.capitalize() for word in re.split(r"[\s_\-]+", name) if word
        )
