---
description: "Auto-generate an MCP server for a tool. Usage: /forge-tool <tool_name> [api_docs_url]"
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, Glob, Grep
---

Run the HackForge Tool Forge pipeline to generate a complete MCP server for $ARGUMENTS.

## Instructions

1. Parse tool name and optional API docs URL from $ARGUMENTS
2. If no docs URL provided, use Tavily to find the official API documentation
3. Spawn **tool-forge** subagent to:
   - Fetch and parse the API documentation
   - Extract all endpoints, auth methods, parameters
   - Generate a complete MCP server package in `mcp-servers/{tool}-mcp/`
   - Generate a REST client in `hackforge/providers/{tool}_client.py`
4. Test the generated code: `python -c "import ast; ast.parse(open('server.py').read())"`
5. Update the harness tool-broker.md with new routing
6. Present the user with:
   - List of generated MCP tools
   - Installation command (`uvx mcp-servers/{tool}-mcp`)
   - Claude Desktop config snippet
