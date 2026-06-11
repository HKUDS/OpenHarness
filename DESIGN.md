# OpenHarness 架构设计总结

OpenHarness（`oh`）是一个开源的 AI Agent Harness 框架，用纯 Python 实现了 Claude Code 的核心架构。以约 11,700 行代码（Claude Code 的 2.3%）实现了 43 个工具、54 个命令，覆盖 98% 的核心功能。

---

## 1. 整体架构

```
┌──────────────────────────────────────────────────────┐
│                 CLI 入口 (Typer)                      │
│          oh / openharness → cli.py                   │
├──────────┬───────────────────────────────────────────┤
│ 交互模式 │  React TUI (Ink 5)  ←JSON Protocol→  Backend │
│ 打印模式 │  oh -p "..." → 无头 Agent Loop             │
├──────────┴───────────────────────────────────────────┤
│              RuntimeBundle (ui/runtime.py)            │
│  组装: API Client / ToolRegistry / Hooks / Commands  │
├──────────────────────────────────────────────────────┤
│              QueryEngine (engine/)                    │
│  管理对话历史 / Cost 追踪 / 提交查询                    │
├──────────────────────────────────────────────────────┤
│    ┌────────┬────────┬──────────┬───────┬──────┐     │
│    │ Tools  │Perms   │ Hooks    │ MCP   │ API  │     │
│    │ 43 个  │3 级模式 │ 生命周期  │ 外部服务│ 流式  │     │
│    └────────┴────────┴──────────┴───────┴──────┘     │
└──────────────────────────────────────────────────────┘
```

---

## 2. Agent Loop（核心循环）

位于 `engine/query.py` 的 `run_query()` 函数，是整个系统的心脏：

```python
for _ in range(max_turns):           # 默认最多 8 轮
    # 1. 流式调用 LLM
    async for event in api_client.stream_message(request):
        yield TextDelta / MessageComplete

    messages.append(assistant_message)

    # 2. 若无工具调用，结束
    if not message.tool_uses:
        return

    # 3. 执行工具（单个串行，多个 asyncio.gather 并发）
    for tool_call in tool_uses:
        pre_hook → permission_check → validate → execute → post_hook

    # 4. 工具结果回传，进入下一轮
    messages.append(tool_results)
```

**关键设计：**
- 通过 `AsyncIterator[StreamEvent]` 逐事件 yield，支持实时流式输出
- 事件类型：`AssistantTextDelta` / `AssistantTurnComplete` / `ToolExecutionStarted` / `ToolExecutionCompleted`
- 多工具调用时用 `asyncio.gather` 并行执行，提升效率

---

## 3. 子系统设计

### 3.1 工具系统（tools/）

43 个工具，统一基于 `BaseTool` 抽象类：

```python
class BaseTool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]          # Pydantic 输入校验

    async def execute(self, arguments, context) -> ToolResult
    def is_read_only(self, arguments) -> bool
    def to_api_schema(self) -> dict       # 生成 JSON Schema 供 LLM 使用
```

| 分类 | 工具 |
|------|------|
| 文件 I/O | Bash, Read, Write, Edit, Glob, Grep |
| 搜索 | WebFetch, WebSearch, ToolSearch, LSP |
| Agent | Agent, SendMessage, TeamCreate/Delete |
| 任务 | TaskCreate/Get/List/Update/Stop/Output |
| MCP | MCPTool, ListMcpResources, ReadMcpResource |
| 工作流 | EnterPlanMode, ExitPlanMode, Worktree |
| 定时 | CronCreate/List/Delete, RemoteTrigger |
| 元操作 | Skill, Config, Brief, Sleep, AskUser, NotebookEdit |

通过 `ToolRegistry` 统一注册和查找，支持运行时动态扩展（MCP 工具）。

### 3.2 权限系统（permissions/）

三级权限模式 + 细粒度规则：

| 模式 | 行为 | 场景 |
|------|------|------|
| DEFAULT | 写操作/执行需确认 | 日常开发 |
| PLAN | 阻止所有写操作 | 大型重构前审查 |
| FULL_AUTO | 全部允许 | 沙箱环境 |

评估流程（`PermissionChecker.evaluate`）：
1. 显式拒绝列表 → 2. 显式允许列表 → 3. 路径 Glob 规则 → 4. 命令黑名单 → 5. 模式级检查

返回 `PermissionDecision(allowed, requires_confirmation, reason)`。

### 3.3 Hook 系统（hooks/）

生命周期事件拦截，支持热重载：

- **事件**: `PRE_TOOL_USE` / `POST_TOOL_USE` / `SESSION_START` 等
- **Hook 类型**: Command（Shell 命令）/ HTTP（Webhook）/ Prompt（模型评估）/ Agent（深度评估）
- **拦截能力**: Pre-hook 可返回 `blocked=True` 阻止工具执行
- **热重载**: `HookReloader` 监听配置文件变化，自动重载

### 3.4 API 客户端（api/）

封装 Anthropic SDK，提供流式调用和容错：

- **流式处理**: `stream_message()` yield `ApiTextDeltaEvent` + `ApiMessageCompleteEvent`
- **重试策略**: 指数退避（1s → 2s → 4s），最多 3 次，支持 Retry-After header
- **可重试状态码**: 429 / 500 / 502 / 503 / 529
- **不可重试**: 认证错误（401/403）立即抛出
- **用量追踪**: `UsageSnapshot` 记录 input/output tokens，`CostTracker` 累计会话总量

### 3.5 消息模型（engine/messages.py）

Pydantic 模型，与 Anthropic API 格式对齐：

```
ConversationMessage(role, content: list[ContentBlock])
  ├── TextBlock(text)
  ├── ToolUseBlock(id, name, input)
  └── ToolResultBlock(tool_use_id, content, is_error)
```

### 3.6 配置系统（config/）

多层配置解析，优先级：CLI 参数 > 环境变量 > `~/.openharness/settings.json` > 默认值

关键配置项：
- `api_key` / `model` / `base_url` — 模型连接
- `permission.mode` / `path_rules` / `denied_commands` — 权限
- `hooks` — 生命周期钩子
- `mcp_servers` — MCP 服务器

### 3.7 MCP 集成（mcp/）

Model Context Protocol 客户端，连接外部工具服务器：

- `McpClientManager` 管理多个 MCP 服务器连接
- 自动将 MCP 工具注册到 `ToolRegistry`
- 支持资源读取（`ListMcpResources` / `ReadMcpResource`）

### 3.8 技能系统（skills/）

按需加载的知识文档（Markdown 格式）：

内置技能：`commit` / `debug` / `plan` / `review` / `simplify` / `test`

兼容 [anthropics/skills](https://github.com/anthropics/skills)，用户可将 `.md` 文件放入 `~/.openharness/skills/` 扩展。

### 3.9 插件系统（plugins/）

兼容 Claude Code 插件格式：
- 插件类型：Command / Hook / Agent / MCP Server
- 管理命令：`oh plugin list/install/uninstall`
- 运行时发现和加载

### 3.10 多 Agent 协调（coordinator/）

支持子 Agent 派生和团队协作：
- `Agent` 工具可启动子 Agent（独立上下文窗口）
- `SendMessage` 向子 Agent 发送消息
- `TeamCreate/Delete` 管理 Agent 团队

### 3.11 提示词构建（prompts/）

动态组装系统提示词：
- 基础系统提示词 + 环境信息（OS、Shell、Git、CWD）
- CLAUDE.md 项目级知识注入
- 技能文档按需拼接

---

## 4. 前端架构（frontend/terminal/）

React 18 + Ink 5 构建的终端 TUI，通过 JSON 协议与 Python 后端通信：

```
Python Backend (BackendHost)
    ↕ JSON Protocol (stdin/stdout)
React Frontend (App.tsx)
    ├── Composer        # 输入框
    ├── TranscriptPane  # 对话记录
    ├── ToolCallDisplay # 工具调用展示
    ├── StatusBar       # 状态栏
    ├── CommandPicker   # 命令选择器
    ├── SelectModal     # 权限确认弹窗
    └── WelcomeBanner   # 欢迎页
```

备用方案：Textual TUI（纯 Python，无需 Node.js）。

---

## 5. 数据流全景

```
用户输入
  ↓
CLI (typer) 解析参数
  ↓
build_runtime() → RuntimeBundle
  ├─ 加载 Settings
  ├─ 创建 AnthropicApiClient
  ├─ 注册 43 个 Tool + MCP 工具
  ├─ 加载 Plugins / Hooks / Skills
  └─ 创建 QueryEngine
  ↓
QueryEngine.submit_message(prompt)
  ↓
run_query() 循环:
  │
  ├─ api_client.stream_message()
  │   ├─ TextDelta → 实时流式输出
  │   └─ MessageComplete → 完整响应
  │
  ├─ 检查 tool_uses
  │   └─ 无 → 结束循环，返回结果
  │
  ├─ 执行工具链:
  │   ├─ Pre-Hook (可拦截)
  │   ├─ PermissionChecker.evaluate()
  │   │   └─ requires_confirmation → 弹窗确认
  │   ├─ Pydantic 输入校验
  │   ├─ tool.execute()
  │   └─ Post-Hook
  │
  └─ tool_results → messages → 下一轮循环
  ↓
输出（text / json / stream-json）
```

---

## 6. 关键设计模式

| 模式 | 应用 |
|------|------|
| **Agent Loop** | 核心递归工具调用循环 |
| **Async Iterator** | 流式事件 yield，支持实时 UI 更新 |
| **Pydantic 校验** | 所有工具输入强类型验证 |
| **权限组合** | 模式 + 规则 + Hook 多层安全检查 |
| **依赖注入** | API Client / Tools / Permissions / Hooks 均可替换 |
| **Hook 拦截** | Pre/Post 生命周期事件，可阻止或观察操作 |
| **懒加载** | Skills / MCP Server / Plugins 按需初始化 |
| **协议隔离** | Python 后端与 React 前端通过 JSON 协议通信 |
| **指数退避** | API 调用失败自动重试，带 Jitter |

---

## 7. 目录结构

```
src/openharness/
├── cli.py              # CLI 入口 (typer)
├── engine/             # Agent Loop 核心
│   ├── query.py        #   run_query() 主循环
│   ├── query_engine.py #   QueryEngine 会话管理
│   ├── messages.py     #   消息模型
│   ├── stream_events.py#   流式事件定义
│   └── cost_tracker.py #   用量追踪
├── api/                # API 客户端
│   ├── client.py       #   Anthropic SDK 封装 + 重试
│   ├── errors.py       #   错误类型
│   └── usage.py        #   Token 用量
├── tools/              # 43 个工具
│   ├── base.py         #   BaseTool 抽象类
│   └── *.py            #   各工具实现
├── permissions/        # 权限系统
├── hooks/              # 生命周期钩子
├── config/             # 配置管理
├── mcp/                # MCP 集成
├── skills/             # 技能系统
├── plugins/            # 插件系统
├── coordinator/        # 多 Agent 协调
├── commands/           # 54 个交互命令
├── prompts/            # 系统提示词构建
├── memory/             # 持久化记忆
├── tasks/              # 后台任务
├── ui/                 # UI 层 (Backend + Protocol)
└── services/           # 公共服务 (session, cron, LSP, compact)

frontend/terminal/      # React TUI (TypeScript)
tests/                  # 114 单元测试 + 6 E2E 套件
```

---

## 8. 技术栈

| 层 | 技术 |
|----|------|
| CLI | Python 3.10+, Typer |
| 数据校验 | Pydantic 2.0+ |
| HTTP | httpx, websockets |
| AI SDK | anthropic >= 0.40.0 |
| MCP | mcp >= 1.0.0 |
| 终端 UI | Rich, Textual (备用) |
| 前端 TUI | React 18, Ink 5, TypeScript |
| 测试 | pytest, pytest-asyncio, pexpect |
| 代码质量 | ruff, mypy |
