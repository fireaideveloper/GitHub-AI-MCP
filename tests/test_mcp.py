import httpx
import pytest

from github_ai_mcp.security.auth_mcp import LocalAuth
from github_ai_mcp.server import build_server


async def test_sdk_tools_and_schemas(factory):
    service, _, _ = factory(mode="READ_ONLY")
    server = build_server(service)
    tools = await server.list_tools()
    assert len(tools) == 26
    assert all(t.output_schema and t.input_schema for t in tools)
    assert not any("approve" in t.name or "config" in t.name for t in tools)
    result = await server.call_tool("github_mcp.health_check", {})
    assert result.structured_content["data"]["sdk"] == "2.3.0"
    denied = await server.call_tool("github_mcp.create_job", {"repository": "test/repo", "idempotency_key": "blocked"})
    assert denied.structured_content["error_code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("host,origin,auth,status", [
    ("127.0.0.1:8766", "", "", 401),
    ("evil.example", "", "Bearer fixture", 403),
    ("127.0.0.1:8766", "https://evil.example", "Bearer fixture", 403),
    ("127.0.0.1:8766", "", "Bearer fixture", 200)])
async def test_http_auth_host_origin(host, origin, auth, status):
    from starlette.responses import JSONResponse
    async def app(scope, receive, send):
        await JSONResponse({"ok": True})(scope, receive, send)
    middleware = LocalAuth(app, "fixture", 8766)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=middleware), base_url="http://127.0.0.1:8766") as client:
        response = await client.post("/mcp", headers={"host": host, "origin": origin, "authorization": auth})
        assert response.status_code == status


async def test_real_http_sdk_initialize_and_list(factory):
    service, _, _ = factory(mode="READ_ONLY")
    server = build_server(service)
    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")
    middleware = LocalAuth(app, "fixture", 8766)
    headers = {"Authorization": "Bearer fixture", "Accept": "application/json, text/event-stream"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=middleware),
                                     base_url="http://127.0.0.1:8766", headers=headers) as client:
            initialize = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                           "clientInfo": {"name": "offline-test", "version": "1.0"}}})
            assert initialize.status_code == 200, initialize.text
            assert "serverInfo" in initialize.json()["result"]
            tools = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            assert tools.status_code == 200, tools.text
            assert len(tools.json()["result"]["tools"]) == 26
