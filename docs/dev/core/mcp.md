# MCP 客户端

OpenHarness 内置 MCP（Model Context Protocol）客户端，支持连接 stdio 和 HTTP 两种传输方式的 MCP 服务器，并将服务器提供的工具和资源暴露给 Agent。

## 架构总览

```mermaid
flowchart TB
    McpClientManager --> McpStdioServerConfig
    McpClientManager --> McpHttpServerConfig
    McpClientManager --> ClientSession
    McpClientManager --> list_tools
    McpClientManager --> list_resources
    McpClientManager --> call_tool
    McpClientManager --> read_resource
    McpStdioServerConfig --> StdioServerParameters
    McpHttpServerConfig --> streamable_http_client
```

## 核心类型

### McpClientManager

```python
# src/openharness/mcp/client.py
class McpClientManager:
    """管理 MCP 连接和工具/资源暴露"""

    def __init__(self, server_configs: dict[str, object]) -> None:
        self._server_configs = server_configs
        self._statuses: dict[str, McpConnectionStatus] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._stacks: dict[str, AsyncExitStack] = {}

    async def connect_all(self) -> None:
        """连接所有配置的 MCP 服务器"""

    async def close(self) -> None:
        """关闭所有 MCP 会话"""

    def list_tools(self) -> list[McpToolInfo]:
        """列出所有已连接服务器的 MCP 工具"""

    def list_resources(self) -> list[McpResourceInfo]:
        """列出所有已连接服务器的 MCP 资源"""

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具"""

    async def read_resource(self, server_name: str, uri: str) -> str:
        """读取 MCP 资源"""
```

### 服务器配置类型

```python
# src/openharness/mcp/types.py

class McpStdioServerConfig(BaseModel):
    """Stdio 传输配置"""
    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None

class McpHttpServerConfig(BaseModel):
    """HTTP 传输配置"""
    type: Literal["http"] = "http"
    url: str
    headers: dict[str, str] = {}
```

### 连接状态

```python
@dataclass
class McpConnectionStatus:
    name: str
    state: str                    # "pending" | "connected" | "failed"
    transport: str
    auth_configured: bool
    detail: str | None = None
    tools: list[McpToolInfo] = []
    resources: list[McpResourceInfo] = []
```

## 连接流程

### Stdio 连接

```python
async def _connect_stdio(self, name: str, config: McpStdioServerConfig) -> None:
    stack = AsyncExitStack()
    read_stream, write_stream = await stack.enter_async_context(
        stdio_client(
            StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
                cwd=config.cwd,
            )
        )
    )
    await self._register_connected_session(
        name=name,
        config=config,
        stack=stack,
        read_stream=read_stream,
        write_stream=write_stream,
        auth_configured=bool(config.env),
    )
```

### HTTP 连接

```python
async def _connect_http(self, name: str, config: McpHttpServerConfig) -> None:
    stack = AsyncExitStack()
    http_client = await stack.enter_async_context(
        httpx.AsyncClient(headers=config.headers or None)
    )
    read_stream, write_stream, _get_session_id = await stack.enter_async_context(
        streamable_http_client(config.url, http_client=http_client)
    )
    await self._register_connected_session(
        name=name,
        config=config,
        stack=stack,
        read_stream=read_stream,
        write_stream=write_stream,
        auth_configured=bool(config.headers),
    )
```

### 会话注册

```python
async def _register_connected_session(
    self,
    *,
    name: str,
    config: object,
    stack: AsyncExitStack,
    read_stream: Any,
    write_stream: Any,
    auth_configured: bool,
) -> None:
    session = await stack.enter_async_context(
        ClientSession(read_stream, write_stream)
    )
    await session.initialize()

    # 获取工具列表
    tool_result = await session.list_tools()
    # 获取资源列表
    resource_result = await session.list_resources()

    # 存储会话
    self._sessions[name] = session
    self._stacks[name] = stack
    self._statuses[name] = McpConnectionStatus(
        name=name,
        state="connected",
        transport=config.type,
        auth_configured=auth_configured,
        tools=[...],  # McpToolInfo 列表
        resources=[...],  # McpResourceInfo 列表
    )
```

## MCP 工具适配

MCP 服务器提供的工具通过 `McpToolAdapter` 适配为 OpenHarness 工具：

```python
# tools/mcp_tool.py
class McpToolAdapter(BaseTool):
    """将 MCP 工具适配为 OpenHarness 工具"""

    def __init__(self, mcp_manager: McpClientManager, tool_info: McpToolInfo):
        self._manager = mcp_manager
        self._tool_info = tool_info
        self.name = f"mcp_{tool_info.server_name}_{tool_info.name}"
        self.description = tool_info.description

    async def execute(self, arguments, context):
        result = await self._manager.call_tool(
            self._tool_info.server_name,
            self._tool_info.name,
            arguments.model_dump()
        )
        return ToolResult(output=result)
```

命名格式：`mcp_{server_name}_{tool_name}`

## MCP 资源读取

MCP 资源通过专用工具访问：

```python
# tools/mcp_resource_tool.py
class ReadMcpResourceTool(BaseTool):
    async def execute(self, arguments, context):
        # arguments.server_name, arguments.uri
        result = await mcp_manager.read_resource(
            arguments.server_name,
            arguments.uri
        )
        return ToolResult(output=result)
```

## 配置格式

### settings.json

```json
{
  "mcp_servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    },
    "github": {
      "type": "http",
      "url": "https://mcp.example.com/github",
      "headers": {
        "Authorization": "Bearer ${GITHUB_TOKEN}"
      }
    }
  }
}
```

### .mcp.json（插件格式）

```json
{
  "mcpServers": {
    "my-server": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "my_mcp_server"]
    }
  }
}
```

### 环境变量认证

```bash
# /mcp 命令设置认证
/mcp auth server_name TOKEN
/mcp auth server_name bearer VALUE
/mcp auth server_name header KEY VALUE
/mcp auth server_name env ENV_VAR_NAME
```

## 工具和资源列表

### 列出所有 MCP 工具

```bash
# 通过 /mcp 命令查看
/mcp
```

### 列出所有资源

```bash
# 工具: /tools | 资源: ReadMcpResource
```

## MCP 工具使用示例

假设连接了 filesystem MCP 服务器：

```text
Available tools:
- mcp_filesystem_read_file   # 读取文件
- mcp_filesystem_write_file  # 写入文件
- mcp_filesystem_list_directory  # 列出目录
```

## 重连管理

```python
async def reconnect_all(self) -> None:
    """重新连接所有服务器"""
    await self.close()
    self._statuses = {...}
    await self.connect_all()
```

## 错误处理

```python
class McpServerNotConnectedError(Exception):
    """MCP 服务器未连接时抛出"""
    pass

# call_tool 时
session = self._sessions.get(server_name)
if session is None:
    raise McpServerNotConnectedError(
        f"MCP server '{server_name}' is not connected"
    )
```

## 扩展点

### 1. 自定义 MCP 工具前缀

```python
class CustomMcpToolAdapter(McpToolAdapter):
    @property
    def name(self) -> str:
        # 自定义命名格式
        return f"custom_{self._tool_info.server_name}_{self._tool_info.name}"
```

### 2. MCP 工具过滤

```python
class FilteringMcpClientManager(McpClientManager):
    def list_tools(self) -> list[McpToolInfo]:
        tools = super().list_tools()
        # 过滤敏感工具
        return [t for t in tools if not t.name.startswith("dangerous_")]
```

### 3. 工具结果后处理

```python
class PostProcessingMcpToolAdapter(McpToolAdapter):
    async def execute(self, arguments, context):
        result = await super().execute(arguments, context)
        # 后处理结果
        return ToolResult(
            output=post_process(result.output),
            is_error=result.is_error
        )
```

## 与其他模块的关系

- **Tools** — MCP 工具通过 `McpToolAdapter` 注册
- **Plugins** — 插件通过 `.mcp.json` 贡献 MCP 服务器
- **Config** — 从 `settings.mcp_servers` 读取配置

## 关键文件

| 文件 | 职责 |
|-----|------|
| `mcp/client.py` | McpClientManager 核心实现 |
| `mcp/types.py` | MCP 类型定义 |
| `mcp/config.py` | MCP 配置加载 |
| `tools/mcp_tool.py` | MCP 工具适配器 |
