"""Tests for MCP client error handling on disconnected servers."""

from __future__ import annotations

from pathlib import Path
import asyncio
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock

import pytest

from openharness.mcp.client import McpClientManager, McpServerNotConnectedError
from openharness.mcp.types import McpConnectionStatus, McpStdioServerConfig, McpToolInfo
from openharness.tools.base import ToolExecutionContext
from openharness.tools.mcp_tool import McpToolAdapter
from openharness.tools.read_mcp_resource_tool import ReadMcpResourceTool


# --- McpClientManager.call_tool ---


@pytest.mark.asyncio
async def test_call_tool_raises_when_server_never_connected():
    manager = McpClientManager({})
    with pytest.raises(McpServerNotConnectedError, match="not connected"):
        await manager.call_tool("missing", "some_tool", {})


@pytest.mark.asyncio
async def test_call_tool_raises_when_server_failed_to_connect():
    config = McpStdioServerConfig(command="false", args=[])
    manager = McpClientManager({"bad": config})
    manager._statuses["bad"] = McpConnectionStatus(
        name="bad", state="failed", detail="Connection refused",
    )
    with pytest.raises(McpServerNotConnectedError, match="Connection refused"):
        await manager.call_tool("bad", "tool", {})


@pytest.mark.asyncio
async def test_call_tool_raises_when_session_errors():
    manager = McpClientManager({})
    mock_session = AsyncMock()
    mock_session.call_tool.side_effect = RuntimeError("transport closed")
    manager._sessions["flaky"] = mock_session

    with pytest.raises(McpServerNotConnectedError, match="transport closed"):
        await manager.call_tool("flaky", "tool", {})


@pytest.mark.asyncio
async def test_call_tool_includes_unknown_server_detail_for_unconfigured():
    """When the server name is not even in _statuses, detail says 'unknown server'."""
    manager = McpClientManager({})
    with pytest.raises(McpServerNotConnectedError, match="unknown server"):
        await manager.call_tool("ghost", "tool", {})


# --- McpClientManager.read_resource ---


@pytest.mark.asyncio
async def test_read_resource_raises_when_server_never_connected():
    manager = McpClientManager({})
    with pytest.raises(McpServerNotConnectedError, match="not connected"):
        await manager.read_resource("missing", "res://data")


@pytest.mark.asyncio
async def test_read_resource_raises_when_session_errors():
    manager = McpClientManager({})
    mock_session = AsyncMock()
    mock_session.read_resource.side_effect = OSError("broken pipe")
    manager._sessions["flaky"] = mock_session

    with pytest.raises(McpServerNotConnectedError, match="broken pipe"):
        await manager.read_resource("flaky", "res://data")


@pytest.mark.asyncio
async def test_register_connected_session_tolerates_missing_resources_list():
    manager = McpClientManager({})
    session = AsyncMock()
    session.initialize.return_value = None
    session.list_tools.return_value.tools = []
    session.list_resources.side_effect = RuntimeError("Method not found")
    stack = AsyncExitStack()
    await stack.__aenter__()
    stack.enter_async_context = AsyncMock(return_value=session)

    await manager._register_connected_session(
        name="context7",
        config=McpStdioServerConfig(command="npx", args=[]),
        stack=stack,
        read_stream=object(),
        write_stream=object(),
        auth_configured=False,
    )

    assert manager._statuses["context7"].state == "connected"
    assert manager._statuses["context7"].resources == []


@pytest.mark.asyncio
async def test_close_suppresses_known_runtime_error_from_stdio_cleanup():
    manager = McpClientManager({})
    stack = MagicMock()
    stack.aclose = AsyncMock(side_effect=RuntimeError("Attempted to exit cancel scope in a different task than it was entered in"))
    manager._stacks["context7"] = stack
    manager._sessions["context7"] = AsyncMock()

    await manager.close()

    assert manager._stacks == {}
    assert manager._sessions == {}


@pytest.mark.asyncio
async def test_close_suppresses_cancelled_error_from_stdio_cleanup():
    manager = McpClientManager({})
    stack = MagicMock()
    stack.aclose = AsyncMock(side_effect=asyncio.CancelledError())
    manager._stacks["context7"] = stack
    manager._sessions["context7"] = AsyncMock()

    await manager.close()

    assert manager._stacks == {}
    assert manager._sessions == {}


# --- McpToolAdapter catches error and returns ToolResult(is_error=True) ---


@pytest.mark.asyncio
async def test_mcp_tool_adapter_returns_error_result_on_disconnected_server():
    manager = McpClientManager({})
    tool_info = McpToolInfo(
        server_name="gone",
        name="hello",
        description="test",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )
    adapter = McpToolAdapter(manager, tool_info)
    result = await adapter.execute(
        adapter.input_model.model_validate({"x": "1"}),
        ToolExecutionContext(cwd=Path(".")),
    )
    assert result.is_error is True
    assert "not connected" in result.output


# --- ReadMcpResourceTool catches error and returns ToolResult(is_error=True) ---


@pytest.mark.asyncio
async def test_read_mcp_resource_tool_returns_error_result_on_disconnected_server():
    manager = McpClientManager({})
    tool = ReadMcpResourceTool(manager)
    result = await tool.execute(
        tool.input_model.model_validate({"server": "gone", "uri": "res://x"}),
        ToolExecutionContext(cwd=Path(".")),
    )
    assert result.is_error is True
    assert "not connected" in result.output
