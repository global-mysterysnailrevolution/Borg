"""MCP server exposing Fastino Labs TLM API as callable tools."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import mcp
import mcp.server.stdio
import mcp.types as types

from fastino_mcp.client import (
    FastinoAPIError,
    FastinoAuthError,
    FastinoClient,
    FastinoRateLimitError,
)
from fastino_mcp.tools import (
    AnalyzeContentInput,
    ClassifyTextInput,
    DetectPiiInput,
    ExtractEntitiesInput,
    ExtractStructuredInput,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("fastino_mcp.server")

# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------

server = mcp.Server("fastino-mcp")

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[types.Tool] = [
    types.Tool(
        name="fastino_extract_entities",
        description=(
            "Extracts named entities from text using Fastino's GLiNER-based NER model. "
            "Detects entities such as tools, companies, APIs, and frameworks by default. "
            "Returns a list of {entity, type, confidence} objects."
        ),
        inputSchema={
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The raw text from which to extract named entities.",
                },
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["TOOL", "COMPANY", "API", "FRAMEWORK"],
                    "description": (
                        "Entity type labels the GLiNER model should detect. "
                        "Common values: TOOL, COMPANY, API, FRAMEWORK, PERSON, LOCATION, DATE."
                    ),
                },
            },
        },
    ),
    types.Tool(
        name="fastino_detect_pii",
        description=(
            "Scans text for personally-identifiable information (PII) such as email addresses, "
            "phone numbers, social security numbers, and credit card numbers. "
            "Returns a list of {text, category, start, end} objects with character offsets."
        ),
        inputSchema={
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to scan for personally-identifiable information.",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of PII category filters, "
                        "e.g. ['EMAIL', 'PHONE', 'SSN', 'CREDIT_CARD']. "
                        "When omitted, all supported categories are detected."
                    ),
                },
            },
        },
    ),
    types.Tool(
        name="fastino_classify_text",
        description=(
            "Performs zero-shot text classification against a user-supplied list of candidate labels. "
            "Supports both single-label (returns best match) and multi-label modes. "
            "Returns {label, confidence} or a list of {label, confidence} for multi_label."
        ),
        inputSchema={
            "type": "object",
            "required": ["text", "labels"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to classify.",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Candidate classification labels (at least one required).",
                    "minItems": 1,
                },
                "multi_label": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, multiple labels may be returned. "
                        "When false, only the single best-matching label is returned."
                    ),
                },
            },
        },
    ),
    types.Tool(
        name="fastino_extract_structured",
        description=(
            "Extracts structured JSON data from unstructured text using a user-supplied JSON Schema. "
            "The model attempts to populate a JSON object that conforms to the provided schema. "
            "Returns the extracted data as a JSON object."
        ),
        inputSchema={
            "type": "object",
            "required": ["text", "schema"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Source text from which to extract structured data.",
                },
                "schema": {
                    "type": "object",
                    "description": (
                        "A JSON Schema object describing the structure to extract. "
                        "The API will return JSON conforming to this schema."
                    ),
                },
            },
        },
    ),
    types.Tool(
        name="fastino_analyze_content",
        description=(
            "Performs open-ended content analysis using a Fastino language model. "
            "Provide the content to analyze along with an instruction or question prompt. "
            "Returns {analysis: str, model: str}."
        ),
        inputSchema={
            "type": "object",
            "required": ["text", "prompt"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The content to analyze.",
                },
                "prompt": {
                    "type": "string",
                    "description": "An instruction or question describing what analysis to perform.",
                },
                "model": {
                    "type": "string",
                    "default": "fastino-flash",
                    "description": (
                        "Fastino model variant to use. "
                        "Options: 'fastino-flash' (fast, lower cost), 'fastino-pro' (higher quality)."
                    ),
                },
            },
        },
    ),
]

# ---------------------------------------------------------------------------
# MCP handler: list_tools
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all available Fastino tools."""
    return _TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# MCP handler: call_tool
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """Dispatch tool calls to the appropriate Fastino API endpoint."""
    logger.info("Tool invoked: %s", name)

    api_key = os.environ.get("FASTINO_API_KEY", "")
    if not api_key:
        return _error_response(
            "FASTINO_API_KEY environment variable is not set. "
            "Obtain an API key from https://fastino.ai and restart the MCP server."
        )

    try:
        client = FastinoClient(api_key=api_key)
        async with client:
            if name == "fastino_extract_entities":
                return await _run_extract_entities(client, arguments)
            elif name == "fastino_detect_pii":
                return await _run_detect_pii(client, arguments)
            elif name == "fastino_classify_text":
                return await _run_classify_text(client, arguments)
            elif name == "fastino_extract_structured":
                return await _run_extract_structured(client, arguments)
            elif name == "fastino_analyze_content":
                return await _run_analyze_content(client, arguments)
            else:
                return _error_response(f"Unknown tool: {name!r}")

    except FastinoAuthError as exc:
        logger.error("Authentication error: %s", exc)
        return _error_response(f"Authentication error: {exc}")
    except FastinoRateLimitError as exc:
        logger.warning("Rate limit error: %s", exc)
        return _error_response(
            f"Rate limit exceeded after retries: {exc}. "
            "Wait a moment before retrying or reduce request frequency."
        )
    except FastinoAPIError as exc:
        logger.error("Fastino API error (status=%s): %s", exc.status_code, exc)
        return _error_response(f"Fastino API error: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in tool %r: %s", name, exc)
        return _error_response(f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Per-tool dispatch helpers
# ---------------------------------------------------------------------------


async def _run_extract_entities(
    client: FastinoClient,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        params = ExtractEntitiesInput(**arguments)
    except Exception as exc:
        return _error_response(f"Invalid arguments for fastino_extract_entities: {exc}")

    raw = await client.extract(text=params.text, entity_types=params.entity_types)

    # Normalise: API may return {"entities": [...]} or a bare list
    entities = raw.get("entities", raw) if isinstance(raw, dict) else raw
    if not isinstance(entities, list):
        entities = []

    result: list[dict[str, Any]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "entity": item.get("entity", item.get("text", "")),
                "type": item.get("type", item.get("label", "")),
                "confidence": round(float(item.get("confidence", item.get("score", 0.0))), 4),
            }
        )

    return _json_response({"entities": result})


async def _run_detect_pii(
    client: FastinoClient,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        params = DetectPiiInput(**arguments)
    except Exception as exc:
        return _error_response(f"Invalid arguments for fastino_detect_pii: {exc}")

    raw = await client.detect_pii(text=params.text, categories=params.categories)

    pii_items = raw.get("pii_found", raw.get("results", raw)) if isinstance(raw, dict) else raw
    if not isinstance(pii_items, list):
        pii_items = []

    result: list[dict[str, Any]] = []
    for item in pii_items:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "text": item.get("text", item.get("value", "")),
                "category": item.get("category", item.get("type", "")),
                "start": int(item.get("start", 0)),
                "end": int(item.get("end", 0)),
            }
        )

    payload: dict[str, Any] = {"pii_found": result}
    redacted = raw.get("redacted_text") if isinstance(raw, dict) else None
    if redacted is not None:
        payload["redacted_text"] = redacted

    return _json_response(payload)


async def _run_classify_text(
    client: FastinoClient,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        params = ClassifyTextInput(**arguments)
    except Exception as exc:
        return _error_response(f"Invalid arguments for fastino_classify_text: {exc}")

    raw = await client.classify(
        text=params.text,
        labels=params.labels,
        multi_label=params.multi_label,
    )

    # Normalise various response shapes
    if isinstance(raw, dict):
        if "results" in raw:
            scores = raw["results"]
        elif "label" in raw:
            # Single-label shorthand: {"label": "...", "confidence": 0.9}
            scores = [{"label": raw["label"], "confidence": raw.get("confidence", 0.0)}]
        elif "labels" in raw and "scores" in raw:
            # Paired lists format
            scores = [
                {"label": lbl, "confidence": sc}
                for lbl, sc in zip(raw["labels"], raw["scores"])
            ]
        else:
            scores = []
    elif isinstance(raw, list):
        scores = raw
    else:
        scores = []

    normalised = [
        {
            "label": item.get("label", ""),
            "confidence": round(float(item.get("confidence", item.get("score", 0.0))), 4),
        }
        for item in scores
        if isinstance(item, dict)
    ]
    normalised.sort(key=lambda x: x["confidence"], reverse=True)

    if params.multi_label:
        return _json_response({"results": normalised, "multi_label": True})

    top = normalised[0] if normalised else {"label": "", "confidence": 0.0}
    return _json_response({"label": top["label"], "confidence": top["confidence"], "multi_label": False})


async def _run_extract_structured(
    client: FastinoClient,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        params = ExtractStructuredInput(**arguments)
    except Exception as exc:
        return _error_response(f"Invalid arguments for fastino_extract_structured: {exc}")

    raw = await client.extract_structured(text=params.text, schema=params.schema)

    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(data, dict):
        data = raw if isinstance(raw, dict) else {}

    return _json_response({"data": data})


async def _run_analyze_content(
    client: FastinoClient,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        params = AnalyzeContentInput(**arguments)
    except Exception as exc:
        return _error_response(f"Invalid arguments for fastino_analyze_content: {exc}")

    raw = await client.analyze(text=params.text, prompt=params.prompt, model=params.model)

    analysis = raw.get("analysis", raw.get("result", raw.get("text", "")))
    model_used = raw.get("model", params.model)

    return _json_response({"analysis": str(analysis), "model": str(model_used)})


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _json_response(data: Any) -> list[types.TextContent]:
    """Serialise *data* as a pretty-printed JSON TextContent block."""
    import json

    return [
        types.TextContent(
            type="text",
            text=json.dumps(data, indent=2, ensure_ascii=False),
        )
    ]


def _error_response(message: str) -> list[types.TextContent]:
    """Return a structured error response that is safe for the MCP client to consume."""
    import json

    return [
        types.TextContent(
            type="text",
            text=json.dumps({"error": message}, indent=2),
        )
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Fastino MCP server using the stdio transport."""
    import asyncio

    api_key = os.environ.get("FASTINO_API_KEY", "")
    if not api_key:
        logger.error(
            "FASTINO_API_KEY is not set. "
            "The server will start but every tool call will return an error. "
            "Export FASTINO_API_KEY before starting this server."
        )
    else:
        logger.info("Fastino MCP server starting (API key configured).")

    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
