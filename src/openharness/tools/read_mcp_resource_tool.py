"""Tool to read MCP resources."""

from __future__ import annotations

from pydantic import BaseModel, Field

from openharness.mcp.client import McpClientManager, McpServerNotConnectedError
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ReadMcpResourceToolInput(BaseModel):
    """Arguments for reading an MCP resource."""

    server: str = Field(description="MCP server name")
    uri: str = Field(description="Resource URI")


class ReadMcpResourceTool(BaseTool):
    """Read one resource from an MCP server."""

    name = "read_mcp_resource"
    description = "Read an MCP resource by server and URI."
    input_model = ReadMcpResourceToolInput

    def __init__(self, manager: McpClientManager) -> None:
        self._manager = manager

    def is_read_only(self, arguments: ReadMcpResourceToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: ReadMcpResourceToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            output = await self._manager.read_resource(arguments.server, arguments.uri)
        except McpServerNotConnectedError as exc:
            return ToolResult(output=str(exc), is_error=True)
        return ToolResult(output=output)
