"""Bridge client for Yutori MCP tools.

Yutori runs as an MCP (Model Context Protocol) server, typically launched via
``uvx yutori-mcp``.  This client supports two transport modes:

1. **HTTP mode** — when ``config.base_url`` is set, sends MCP JSON-RPC
   requests directly to the running server over HTTP.
2. **Subprocess mode** — spawns ``uvx yutori-mcp`` as a child process and
   communicates over stdin/stdout using the MCP protocol.

The caller should prefer HTTP mode (more efficient) when a persistent Yutori
server is available, and fall back to subprocess mode for one-shot calls.

Reference: https://github.com/yutori-ai/yutori-mcp
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from hackforge.config import ProviderConfig


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class YutoriError(Exception):
    """Base error for all Yutori client failures."""


class YutoriTransportError(YutoriError):
    """Raised when communication with the Yutori MCP server fails."""


class YutoriToolError(YutoriError):
    """Raised when Yutori returns a tool-execution error."""


class YutoriTimeoutError(YutoriError):
    """Raised when a Yutori operation exceeds the configured timeout."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BrowseResult:
    """Result from a ``browse`` tool call."""

    url: str
    task: str
    content: str
    screenshots: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoutResult:
    """Result from starting a ``scout`` monitoring job."""

    scout_id: str
    target: str
    interval_minutes: int
    status: str = "started"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchResult:
    """Result from a ``research`` tool call."""

    query: str
    summary: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class StopScoutResult:
    """Result from stopping a scout job."""

    scout_id: str
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MCP JSON-RPC helpers
# ---------------------------------------------------------------------------


def _build_tool_call_payload(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build an MCP JSON-RPC ``tools/call`` request payload."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def _extract_tool_result(response: dict[str, Any]) -> Any:
    """Extract the ``result`` payload from an MCP JSON-RPC response.

    Raises:
        YutoriToolError: If the response contains a JSON-RPC ``error`` field.
    """
    if "error" in response:
        err = response["error"]
        raise YutoriToolError(
            f"Yutori tool error [{err.get('code', 'unknown')}]: {err.get('message', str(err))}"
        )
    result = response.get("result", {})
    # MCP returns content as a list of content blocks; extract text if present.
    content_blocks = result.get("content", [])
    if content_blocks and isinstance(content_blocks, list):
        texts = [
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ]
        if texts:
            try:
                # Many Yutori tools return JSON inside the text block.
                return json.loads(texts[0])
            except (json.JSONDecodeError, ValueError):
                return {"text": "\n".join(texts)}
    return result


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class YutoriClient:
    """Bridge client for Yutori MCP tools.

    Automatically selects the transport based on ``config.base_url``:

    - If ``config.base_url`` is non-empty → HTTP transport (preferred).
    - Otherwise → subprocess transport (``uvx yutori-mcp``).

    Usage (HTTP mode)::

        cfg = ProviderConfig(base_url="http://localhost:3000", timeout=120)
        async with YutoriClient(cfg) as client:
            result = await client.browse("https://example.com", "Find the pricing page")
            print(result.content)

    Usage (subprocess mode)::

        cfg = ProviderConfig(timeout=120)
        async with YutoriClient(cfg) as client:
            result = await client.research("Open-source LLM frameworks 2024")
            print(result.summary)
    """

    # Subprocess command used when no HTTP URL is configured.
    _MCP_COMMAND: list[str] = ["uvx", "yutori-mcp"]

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._use_http = bool(config.base_url)
        self._http_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> YutoriClient:
        if self._use_http:
            await self._ensure_http_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ensure_http_client(self) -> None:
        if self._http_client is None:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._config.api_key:
                headers["Authorization"] = f"Bearer {self._config.api_key}"
            self._http_client = httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=self._config.timeout,
                headers=headers,
            )

    async def close(self) -> None:
        """Cleanly close any open HTTP connection pool."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Transport dispatch
    # ------------------------------------------------------------------

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Invoke a Yutori MCP tool and return its parsed result.

        Dispatches to the HTTP or subprocess transport based on config.
        """
        payload = _build_tool_call_payload(tool_name, arguments)
        if self._use_http:
            return await self._http_call(payload)
        return await self._subprocess_call(payload)

    async def _http_call(self, payload: dict[str, Any]) -> Any:
        """Send an MCP request over HTTP and return the parsed result."""
        await self._ensure_http_client()
        assert self._http_client is not None

        try:
            response = await self._http_client.post("/", json=payload)
        except httpx.TimeoutException as exc:
            raise YutoriTimeoutError(f"Yutori HTTP request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise YutoriTransportError(f"Yutori HTTP transport error: {exc}") from exc

        if response.status_code >= 400:
            raise YutoriTransportError(
                f"Yutori server returned HTTP {response.status_code}: {response.text}"
            )

        return _extract_tool_result(response.json())

    async def _subprocess_call(self, payload: dict[str, Any]) -> Any:
        """Spawn a Yutori MCP subprocess, send one request, and return the result."""
        stdin_data = (json.dumps(payload) + "\n").encode()
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._MCP_COMMAND,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise YutoriTransportError(
                "Yutori subprocess not found.  Ensure 'uvx' is installed and "
                "'yutori-mcp' is available: pip install uv && uvx yutori-mcp"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=self._config.timeout,
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise YutoriTimeoutError(
                f"Yutori subprocess timed out after {self._config.timeout}s"
            ) from exc

        if proc.returncode != 0:
            raise YutoriTransportError(
                f"Yutori subprocess exited with code {proc.returncode}: "
                f"{stderr.decode(errors='replace')}"
            )

        raw_output = stdout.decode(errors="replace").strip()
        if not raw_output:
            raise YutoriTransportError("Yutori subprocess produced no output.")

        # The MCP server may emit multiple newline-delimited JSON objects;
        # use the last one as the authoritative response.
        last_line = raw_output.splitlines()[-1]
        try:
            response_json: dict[str, Any] = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise YutoriTransportError(
                f"Could not parse Yutori subprocess output as JSON: {exc}\n"
                f"Raw output: {last_line[:500]}"
            ) from exc

        return _extract_tool_result(response_json)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def browse(self, url: str, task: str) -> BrowseResult:
        """Instruct Yutori to browse *url* and complete *task*.

        Yutori will open the URL in a headless browser, navigate as needed
        to complete the task, and return the extracted content.

        Args:
            url: The URL to open.
            task: Natural-language description of what to do or extract
                (e.g. ``"Find the pricing page and extract plan details"``).

        Returns:
            A :class:`BrowseResult` with the extracted ``content`` and any
            available ``screenshots`` (as base64 strings or URLs).
        """
        result = await self._call_tool("browse", {"url": url, "task": task})
        if not isinstance(result, dict):
            result = {"content": str(result)}
        return BrowseResult(
            url=url,
            task=task,
            content=result.get("content", result.get("text", str(result))),
            screenshots=result.get("screenshots", []),
            metadata=result.get("metadata", {}),
            raw=result,
        )

    async def scout(
        self,
        target: str,
        interval_minutes: int = 60,
        criteria: str | list[str] | None = None,
    ) -> ScoutResult:
        """Start a persistent monitoring job on *target*.

        Yutori will periodically visit *target* and notify when *criteria*
        are met.

        Args:
            target: URL or search query to monitor.
            interval_minutes: How often Yutori checks (default 60 min).
            criteria: Trigger conditions expressed as a string or list of
                strings (e.g. ``"price drops below $100"``).

        Returns:
            A :class:`ScoutResult` with the assigned ``scout_id`` which can
            later be passed to :meth:`stop_scout`.
        """
        arguments: dict[str, Any] = {
            "target": target,
            "interval_minutes": interval_minutes,
        }
        if criteria is not None:
            arguments["criteria"] = (
                criteria if isinstance(criteria, list) else [criteria]
            )
        result = await self._call_tool("scout", arguments)
        if not isinstance(result, dict):
            result = {"scout_id": str(result)}
        return ScoutResult(
            scout_id=result.get("scout_id", result.get("id", "")),
            target=target,
            interval_minutes=interval_minutes,
            status=result.get("status", "started"),
            raw=result,
        )

    async def research(self, query: str) -> ResearchResult:
        """Run a deep research task using Yutori's research tool.

        Yutori browses multiple sources and synthesises a comprehensive
        answer to *query*.

        Args:
            query: The research question or topic.

        Returns:
            A :class:`ResearchResult` with a ``summary`` and list of
            ``sources`` consulted.
        """
        result = await self._call_tool("research", {"query": query})
        if not isinstance(result, dict):
            result = {"summary": str(result)}
        return ResearchResult(
            query=query,
            summary=result.get("summary", result.get("content", result.get("text", str(result)))),
            sources=result.get("sources", result.get("references", [])),
            raw=result,
        )

    async def stop_scout(self, scout_id: str) -> StopScoutResult:
        """Stop a running scout monitoring job.

        Args:
            scout_id: The ID returned by a previous :meth:`scout` call.

        Returns:
            A :class:`StopScoutResult` confirming the job has been stopped.
        """
        result = await self._call_tool("stop_scout", {"scout_id": scout_id})
        if not isinstance(result, dict):
            result = {"status": str(result)}
        return StopScoutResult(
            scout_id=scout_id,
            status=result.get("status", "stopped"),
            raw=result,
        )
