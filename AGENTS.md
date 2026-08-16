# MCP Server (Python) — Agent Guide

This is a remote MCP server built with the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) and deployed on [Render](https://render.com). It uses Streamable HTTP transport and runs stateless — no session management.

## Project layout

- `server.py` — the entire server: MCP tools, health check, and ASGI app
- `requirements.txt` — Python dependencies
- `render.yaml` — Render Blueprint for deployment

## Authentication

The server uses bearer token auth controlled by the `MCP_API_TOKEN` environment variable. When set, all requests to `/mcp` must include `Authorization: Bearer <token>`. The `/health` endpoint is always unauthenticated.

When `MCP_API_TOKEN` is not set, auth is disabled entirely — this is the default for local development. Do not remove the auth middleware from `server.py`.

## Adding a tool

Add tools to `server.py` by decorating a function with `@mcp.tool()`. Insert new tools **after the existing tool definitions and before the `@mcp.custom_route` health check**.

### Pattern

```python
@mcp.tool()
def your_tool_name(param: str, count: int = 10) -> str:
    """One-line description of what this tool does (shown to LLMs)."""
    # implementation
    return "result"
```

### Rules

- **snake_case** for tool function names
- Always include a **docstring** — MCP clients surface it to LLMs as the tool description
- Use **type hints** for all parameters and the return type — the SDK generates the JSON schema from them
- Parameters with defaults become optional in the schema
- Return a string. For structured data, return `json.dumps(...)`.

### Examples

Simple tool with required parameters:

```python
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b
```

Tool with optional parameters:

```python
@mcp.tool()
def search_docs(query: str, max_results: int = 5) -> str:
    """Search the documentation for a query string."""
    results = do_search(query, limit=max_results)
    return json.dumps(results)
```

Async tool that calls an external API:

```python
@mcp.tool()
async def fetch_weather(city: str, units: str = "celsius") -> str:
    """Get the current weather for a city."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://wttr.in/{city}?format=j1")
        return resp.text
```

## Adding dependencies

Add new packages to `requirements.txt`, one per line:

```
httpx
```

On Render, the build command (`pip install -r requirements.txt`) installs them automatically.

## Deployment

Push to the GitHub repo connected to your Render Blueprint. Render builds and deploys automatically (unless `autoDeploy` is set to `false` in `render.yaml`, in which case trigger a deploy from the Render Dashboard).

## Tests

Tests live in `tests/test_server.py` and use pytest with httpx's async test client. Run them with `pytest`.

When adding a new tool, add a corresponding test case that calls the tool via MCP and checks the response. Follow the pattern in `test_tool_call` — send a `tools/call` JSON-RPC request and assert on the result content.

## Key files not to remove

- `render.yaml` — required for Render Blueprint deploys
- The `health` function and `/health` route in `server.py` — used by Render's health checks

## References

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP specification](https://spec.modelcontextprotocol.io/)
- [Render Blueprints](https://render.com/docs/infrastructure-as-code)
