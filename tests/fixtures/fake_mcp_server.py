"""Small stdio MCP server used by integration tests."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

server = MCPServer("fixture-demo")


@server.tool()
def hello(name: str) -> str:
    return f"fixture-hello:{name}"


@server.resource("fixture://readme", name="Fixture Readme")
def readme() -> str:
    return "fixture resource contents"


if __name__ == "__main__":
    server.run("stdio")
