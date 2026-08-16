from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send
import hmac
import os

MCP_API_TOKEN = os.environ.get("MCP_API_TOKEN")
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

mcp = FastMCP(
    "my-mcp-server",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(RENDER_EXTERNAL_HOSTNAME),
        allowed_hosts=[RENDER_EXTERNAL_HOSTNAME] if RENDER_EXTERNAL_HOSTNAME else [],
    ),
)


# Add tools below. The docstring is surfaced to LLMs as the tool description.
# Type hints define the JSON schema for parameters.
@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"


# custom_route bypasses auth — use only for public endpoints
@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


# Simple bearer token auth. For multi-user or production setups,
# consider upgrading to the MCP SDK's built-in OAuth 2.1 support.
class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["path"] == "/health":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        # constant-time comparison to prevent timing side-channel attacks
        if hmac.compare_digest(auth, f"Bearer {MCP_API_TOKEN}"):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32001, "message": "Unauthorized"},
                "id": None,
            },
            status_code=401,
        )
        await response(scope, receive, send)


def create_app():
    app = mcp.streamable_http_app()
    # When no token is set (local dev), auth is disabled entirely
    if MCP_API_TOKEN:
        app.add_middleware(BearerAuthMiddleware)
    return app


if __name__ == "__main__":
    import uvicorn

    if not MCP_API_TOKEN:
        print(
            "WARNING: MCP_API_TOKEN is not set."
            " The server is running without authentication."
        )

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)
