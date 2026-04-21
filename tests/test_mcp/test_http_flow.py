"""HTTP MCP integration tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import openharness.mcp.client as client_module
from openharness.mcp.client import McpClientManager
from openharness.mcp.types import McpHttpServerConfig
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_http_mcp_manager_connects_and_executes_in_process_server(monkeypatch):
    server = FastMCP(
        "demo-http",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @server.tool()
    def hello(name: str) -> str:
        return f"http-hello:{name}"

    @server.resource("demo://readme")
    def readme() -> str:
        return "http fixture resource contents"

    app = server.streamable_http_app()
    transport = httpx.ASGITransport(app=app)
    original_async_client = client_module.httpx.AsyncClient
    seen_headers: list[dict[str, str] | None] = []

    def _async_client_factory(*args, **kwargs):
        seen_headers.append(kwargs.get("headers"))
        return original_async_client(
            *args,
            transport=transport,
            base_url="http://testserver",
            **kwargs,
        )

    monkeypatch.setattr(client_module.httpx, "AsyncClient", _async_client_factory)

    manager = McpClientManager(
        {
            "http-fixture": McpHttpServerConfig(
                url="http://testserver/mcp",
                headers={"Authorization": "Bearer token-smoke"},
            )
        }
    )

    async with app.router.lifespan_context(app):
        await manager.connect_all()
        try:
            statuses = manager.list_statuses()
            assert len(statuses) == 1
            assert statuses[0].state == "connected"
            assert statuses[0].transport == "http"
            assert statuses[0].auth_configured is True
            assert statuses[0].tools[0].name == "hello"
            assert statuses[0].resources[0].uri == "demo://readme"
            assert seen_headers[0] == {"Authorization": "Bearer token-smoke"}

            registry = create_default_tool_registry(manager)
            hello_tool = registry.get("mcp__http-fixture__hello")
            assert hello_tool is not None
            hello_result = await hello_tool.execute(
                hello_tool.input_model.model_validate({"name": "world"}),
                ToolExecutionContext(cwd=Path(".")),
            )
            assert hello_result.output == "http-hello:world"

            resource_tool = registry.get("read_mcp_resource")
            assert resource_tool is not None
            resource_result = await resource_tool.execute(
                resource_tool.input_model.model_validate(
                    {"server": "http-fixture", "uri": "demo://readme"}
                ),
                ToolExecutionContext(cwd=Path(".")),
            )
            assert "http fixture resource contents" in resource_result.output
        finally:
            await manager.close()
