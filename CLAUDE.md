# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

OpenHarness（`oh`）是一个开源 Python Agent Harness 框架，为 LLM 代理提供工具、技能、记忆、权限管理和多代理协调功能。是 Claude Code 的开源实现。

## 常用命令

```bash
# 安装（需要 uv）
uv sync --extra dev

# 运行 CLI
uv run oh

# 单次提示（非交互式）
uv run oh -p "你的提示词"

# JSON 输出
uv run oh -p "..." --output-format json

# 设置向导
uv run oh setup

# 代码检查
uv run ruff check src tests scripts
uv run mypy src/openharness  # 可选，非必须

# 运行所有测试
uv run pytest -q

# 运行单个测试文件
uv run pytest tests/test_engine/test_query_engine.py -v

# 运行单个测试
uv run pytest tests/test_engine/test_query_engine.py::test_name -v

# 前端（React TUI）
cd frontend/terminal && npm ci && npx tsc --noEmit
```

## 架构

### 核心循环（`src/openharness/engine/`）

Agent 循环是 harness 的核心：
1. QueryEngine 从 LLM API 流式获取响应
2. 对于每个 `tool_use` 停止原因，通过 ToolRegistry 执行工具
3. 工具执行流程：权限检查 → PreToolUse 钩子 → 执行 → PostToolUse 钩子 → 结果
4. 将工具结果追加到消息中，循环继续

### 工具系统（`src/openharness/tools/`）

43+ 工具，继承自 `BaseTool`：
- 文件 I/O：Read, Write, Edit, Glob, Grep
- Shell：Bash
- 搜索：WebFetch, WebSearch, ToolSearch, LSP
- 代理：Agent, SendMessage, TeamCreate/Delete
- 任务：TaskCreate/Get/List/Update/Stop/Output
- MCP：MCPTool, ListMcpResources, ReadMcpResource
- 模式：EnterPlanMode, ExitPlanMode, Worktree 工具
- 调度：CronCreate/List/Delete, RemoteTrigger

每个工具使用 Pydantic 做输入验证，在 `tools/registry.py` 中注册。

### API 层（`src/openharness/api/`）

支持多后端的 Provider 无感知 API 客户端：
- `client.py` - Anthropic 兼容 API 调用
- `openai_client.py` - OpenAI 兼容 API 调用
- `codex_client.py` - Codex 订阅桥接
- `copilot_client.py` - GitHub Copilot OAuth 流程
- `registry.py` - Provider 配置管理

### 多代理 Swarm（`src/openharness/swarm/`）

子代理生成和团队协作：
- `team_lifecycle.py` - 团队创建、成员管理
- `mailbox.py` - 代理间消息传递
- `in_process.py` - 进程内代理执行
- `worktree.py` - 每个代理的 Git worktree 隔离

### 记忆系统（`src/openharness/memory/`）

跨会话持久化记忆：
- `memory.py` - 核心记忆接口
- `*.py` - 各种记忆后端（基于文件）
- 支持中文 Han 字符搜索

### React TUI 前端（`frontend/terminal/`）

基于 React/Ink 的终端 UI：
- 后端协议在 `src/openharness/ui/`
- 前端在 `frontend/terminal/src/`
- 使用 Ink + React 构建，绑定到 CLI

### ohmo 个人代理（`ohmo/`）

构建在 OpenHarness 之上的个人代理应用：
- `cli.py` - ohmo CLI 入口
- `gateway/` - 渠道集成的 Gateway 服务
- `workspace.py` - 工作区管理（`~/.ohmo/`）
- 支持 Telegram、Slack、Discord、飞书渠道

### 技能系统（`src/openharness/skills/`, `src/openharness/skills/bundled/`）

从 `.md` 文件按需加载知识：
- 兼容 `anthropics/skills` 格式
- 内置技能：commit, debug, diagnose, plan, review, simplify, test
- 用户技能放在 `~/.openharness/skills/`

### 插件系统（`src/openharness/plugins/`）

兼容 Claude Code 插件的插件生态：
- 命令、钩子、代理、MCP 服务器
- `.claude-plugin/plugin.json` 清单格式

### 权限（`src/openharness/permissions/`）

多级权限模式：
- `default` - 写入/执行前询问
- `auto` - 允许所有操作
- `plan` - 阻止所有写入

`settings.json` 中的路径级规则和命令拒绝。

## Provider 兼容性

| 工作流 | 支持的后端 |
|--------|-----------|
| Anthropic 兼容 API | Claude 官方, Kimi, GLM, MiniMax |
| OpenAI 兼容 API | OpenAI, OpenRouter, DashScope, DeepSeek, Groq, Ollama |
| Claude 订阅 | 本地 `~/.claude/.credentials.json` |
| Codex 订阅 | 本地 `~/.codex/auth.json` |
| GitHub Copilot | GitHub OAuth 设备流 |

## 关键入口点

| 文件 | 用途 |
|------|------|
| `src/openharness/cli.py` | 主 `oh` CLI 入口，使用 Typer |
| `ohmo/cli.py` | `ohmo` 个人代理 CLI |
| `src/openharness/engine/query_engine.py` | 核心 Agent 循环实现 |
| `src/openharness/tools/registry.py` | 工具注册和执行 |
| `src/openharness/config/` | 多层配置系统 |

## 添加自定义工具

```python
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

class MyToolInput(BaseModel):
    query: str = Field(description="搜索查询")

class MyTool(BaseTool):
    name = "my_tool"
    description = "执行有用的操作"
    input_model = MyToolInput

    async def execute(self, arguments: MyToolInput, context: ToolExecutionContext) -> ToolResult:
        return ToolResult(output=f"结果: {arguments.query}")
```

## 代码规范

- 行长度：100 字符（ruff）
- Python：3.10+，严格类型注解（mypy）
- 输入验证使用 Pydantic 模型
- 所有工具使用 async/await
