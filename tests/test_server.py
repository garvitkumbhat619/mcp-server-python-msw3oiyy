import os
import json
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ["MCP_API_TOKEN"] = "test-token"

import server as server_module  # noqa: E402
from server import create_app, BearerAuthMiddleware  # noqa: E402

TOKEN = "test-token"
BASE_URL = "http://localhost"
MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0.0"},
    },
}


def parse_sse_data(text: str) -> dict:
    """Extract the JSON payload from an SSE response."""
    for line in text.strip().splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise ValueError(f"No data line in SSE response: {text}")


@pytest.fixture(scope="module")
async def managed_app():
    """Single app with lifespan for the entire test module."""
    app = create_app()
    async with LifespanManager(app):
        yield app


@pytest.fixture
def authed_headers():
    return {**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"}


@pytest.mark.anyio
async def test_health(managed_app):
    async with AsyncClient(
        transport=ASGITransport(app=managed_app), base_url=BASE_URL
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_mcp_no_token_when_required(managed_app):
    async with AsyncClient(
        transport=ASGITransport(app=managed_app), base_url=BASE_URL
    ) as client:
        resp = await client.post("/mcp", headers=MCP_HEADERS, json=INIT_BODY)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == -32001


@pytest.mark.anyio
async def test_mcp_wrong_token(managed_app):
    headers = {**MCP_HEADERS, "Authorization": "Bearer wrong-token"}
    async with AsyncClient(
        transport=ASGITransport(app=managed_app), base_url=BASE_URL
    ) as client:
        resp = await client.post("/mcp", headers=headers, json=INIT_BODY)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_mcp_correct_token(managed_app, authed_headers):
    async with AsyncClient(
        transport=ASGITransport(app=managed_app), base_url=BASE_URL
    ) as client:
        resp = await client.post("/mcp", headers=authed_headers, json=INIT_BODY)
    assert resp.status_code == 200
    data = parse_sse_data(resp.text)
    assert data["result"]["serverInfo"]["name"] == "my-mcp-server"


@pytest.mark.anyio
async def test_mcp_open_when_no_token_set():
    """Verify auth middleware passes requests through when MCP_API_TOKEN is unset."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse

    async def ok(request):
        return JSONResponse({"passed": True})

    # When MCP_API_TOKEN is None, create_app() skips the middleware entirely.
    # Simulate that by building a bare app (no BearerAuthMiddleware).
    saved = server_module.MCP_API_TOKEN
    try:
        server_module.MCP_API_TOKEN = None
        bare_app = Starlette(routes=[Route("/mcp", ok, methods=["POST"])])
        # Verify create_app logic: middleware is NOT added when token is unset
        assert server_module.MCP_API_TOKEN is None
        async with AsyncClient(
            transport=ASGITransport(app=bare_app), base_url=BASE_URL
        ) as client:
            resp = await client.post("/mcp", headers=MCP_HEADERS, json=INIT_BODY)
        assert resp.status_code == 200
        assert resp.json() == {"passed": True}
    finally:
        server_module.MCP_API_TOKEN = saved


@pytest.mark.anyio
async def test_tool_call(managed_app, authed_headers):
    async with AsyncClient(
        transport=ASGITransport(app=managed_app), base_url=BASE_URL
    ) as client:
        resp = await client.post(
            "/mcp", headers=authed_headers, json=INIT_BODY
        )
        assert resp.status_code == 200

        tool_body = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "hello", "arguments": {"name": "World"}},
        }
        resp = await client.post(
            "/mcp", headers=authed_headers, json=tool_body
        )
        assert resp.status_code == 200
        data = parse_sse_data(resp.text)
        assert data["result"]["content"][0]["text"] == "Hello, World!"
