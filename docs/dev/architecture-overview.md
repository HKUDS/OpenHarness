# 架构总览

本文档介绍 OpenHarness 的整体架构设计。

## 项目简介

OpenHarness 是一个开源的 Python Agent Harness —— 围绕 LLM 构建功能性编码 Agent 的基础设施。它兼容 Claude Code 规范，提供工具使用、技能、记忆和多 Agent 协调能力。

**核心理念**: 模型是 Agent，代码是 Harness。

## 系统架构

```mermaid
flowchart TB
    subgraph Client["客户端层"]
        CLI[CLI: oh]
        TUI[React TUI]
    end

    subgraph Core["核心引擎"]
        QueryEngine[QueryEngine]
        run_query[run_query]
    end

    subgraph Tools["工具层"]
        Registry[ToolRegistry]
        Permission[PermissionChecker]
        Hooks[HookExecutor]
    end

    subgraph Subsystems["子系统"]
        Skills[Skills]
        Plugins[Plugins]
        MCP[MCP Client]
        Memory[Memory]
        Tasks[Tasks]
        Coordinator[Coordinator]
        Commands[Commands]
    end

    subgraph API["API 层"]
        AnthropicClient[Anthropic Client]
        OpenAIClient[OpenAI Client]
        CustomClient[Custom Client]
    end

    subgraph Config["配置层"]
        Settings[Settings]
        Profiles[Provider Profiles]
        EnvVars[环境变量]
    end

    CLI --> QueryEngine
    TUI --> QueryEngine

    QueryEngine --> run_query
    run_query --> Registry
    run_query --> Permission
    run_query --> Hooks

    Registry --> Skills
    Registry --> Plugins
    Registry --> MCP
    Registry --> Tasks
    Registry --> Commands

    run_query --> Coordinator
    run_query --> Memory

    QueryEngine --> AnthropicClient
    QueryEngine --> OpenAIClient
    QueryEngine --> CustomClient

    QueryEngine --> Settings
    Settings --> Profiles
    Settings --> EnvVars
```

## 核心模块

### 1. Engine（引擎）

**职责**: Agent 循环的核心实现

```
src/openharness/engine/
├── query_engine.py    # QueryEngine 主类
├── query.py           # run_query 循环实现
├── messages.py        # 消息类型定义
├── stream_events.py   # 流式事件类型
└── cost_tracker.py    # 使用量追踪
```

**核心流程**:
1. 接收用户消息
2. 调用 API 获取响应
3. 如有工具调用，执行权限检查
4. 执行工具
5. 触发钩子
6. 将结果添加到对话历史
7. 循环直到模型完成

### 2. Tools（工具）

**职责**: 提供 Agent 可调用的工具

```
src/openharness/tools/
├── base.py           # BaseTool 基类（含 ToolRegistry 工具注册表）
├── __init__.py       # 工具初始化
├── bash_tool.py      # Bash 执行
├── file_*.py        # 文件操作（edit/read/write/glob/grep）
├── web_*.py         # Web 操作（fetch/search）
├── task_*.py        # 任务管理（create/get/list/update/stop/output）
├── mcp_tool.py      # MCP 包装
└── ... (40+ 工具)
```

### 3. Skills（技能）

**职责**: 按需加载的知识模块

```
src/openharness/skills/
├── loader.py        # 技能加载器
├── registry.py       # 技能注册表
├── types.py         # 类型定义
└── bundled/         # 内置技能
```

### 4. Plugins（插件）

**职责**: 扩展系统功能

```
src/openharness/plugins/
├── loader.py        # 插件加载器
├── schemas.py       # 插件清单 Schema
└── types.py         # 类型定义
```

### 5. Permissions（权限）

**职责**: 工具执行安全控制

```
src/openharness/permissions/
├── checker.py       # 权限检查器
└── modes.py        # 权限模式
```

### 6. Hooks（钩子）

**职责**: 生命周期事件处理

```
src/openharness/hooks/
├── executor.py      # 钩子执行器
├── loader.py        # 钩子加载器
├── events.py        # 事件类型
├── schemas.py       # 钩子 Schema
└── types.py         # 结果类型
```

### 7. Commands（命令）

**职责**: Slash commands 实现

```
src/openharness/commands/
├── __init__.py       # 命令初始化
└── registry.py       # 命令注册表（含所有 slash command 定义）
```

### 8. MCP（Model Context Protocol）

**职责**: MCP 客户端集成

```
src/openharness/mcp/
├── client.py        # MCP 客户端管理器
├── config.py        # 配置处理
└── types.py         # 类型定义
```

### 9. Memory（记忆）

**职责**: 持久化记忆和上下文压缩

```
src/openharness/memory/
├── memdir.py        # 记忆目录
├── manager.py       # 记忆管理器
└── types.py         # 类型定义
```

### 10. Tasks（任务）

**职责**: 后台任务管理

```
src/openharness/tasks/
├── manager.py       # 任务管理器
├── types.py         # 任务类型
├── local_shell_task.py
└── local_agent_task.py
```

### 11. Coordinator（协调）

**职责**: 多 Agent 协调

```
src/openharness/coordinator/
├── coordinator_mode.py  # 协调者模式
└── agent_definitions.py # Agent 定义
```

### 12. Prompts（提示词）

**职责**: 系统提示词构建

```
src/openharness/prompts/
├── system_prompt.py     # 基础提示词
├── environment.py        # 环境信息
├── context.py            # 上下文组装
└── claudemd.py          # CLAUDE.md 处理
```

### 13. Config（配置）

**职责**: 配置管理

```
src/openharness/config/
├── settings.py      # 设置模型和加载
├── paths.py         # 路径管理
└── schema.py       # Schema 定义
```

## 数据流

### Agent 执行流程

```
用户输入
    ↓
RuntimeBundle 初始化
    ↓
QueryEngine.submit_message()
    ↓
run_query() 循环
    ├─→ auto_compact_if_needed()  [上下文压缩]
    ├─→ api_client.stream_message()  [API 调用]
    │       ↓
    │   AssistantTextDelta  [流式文本]
    │       ↓
    │   AssistantTurnComplete  [完成]
    │
    ├─→ 工具执行 (如有 tool_use)
    │       ├─→ hook_executor.execute(PRE_TOOL_USE)
    │       ├─→ permission_checker.evaluate()
    │       ├─→ tool.execute()
    │       └─→ hook_executor.execute(POST_TOOL_USE)
    │
    └─→ 消息追加，循环继续
    ↓
返回结果
```

### 工具执行流程

```
工具调用请求
    ↓
ToolRegistry.get(tool_name)
    ↓
权限检查 (PermissionChecker)
    ├─→ 敏感路径检查
    ├─→ 工具允许/拒绝列表
    ├─→ 路径规则
    └─→ 命令规则
    ↓
钩子执行 (PreToolUse)
    ↓
BaseTool.execute()
    ↓
钩子执行 (PostToolUse)
    ↓
返回 ToolResult
```

## 关键设计

### 1. 流式优先

所有 API 调用和工具执行都支持流式返回，提供实时反馈。

### 2. 异步架构

广泛使用 `async/await`，支持高效的并发执行。

### 3. 扩展性

- **工具**: 继承 BaseTool
- **技能**: Markdown 文件格式
- **插件**: 完整扩展系统
- **钩子**: 多种钩子类型

### 4. 安全性

- 多层权限检查
- 敏感路径保护
- 沙箱集成
- 审计追踪

### 5. 可配置性

- 多层配置系统
- 提供者抽象
- 环境变量支持

## 与 Claude Code 的兼容性

OpenHarness 兼容 Claude Code 的：

- **工具格式**: 相同 schema
- **技能格式**: `~/.openharness/skills/` 和 `SKILL.md`
- **插件格式**: `.claude-plugin/plugin.json`
- **命令格式**: Markdown 命令文件
- **CLAUDE.md**: 自动发现和注入

## 扩展点

### 添加新工具

```python
class MyTool(BaseTool):
    name = "my_tool"
    input_model = MyToolInput

    async def execute(self, args, ctx):
        return ToolResult(output="...")

registry.register(MyTool())
```

### 添加新技能

在 `~/.openharness/skills/my-skill/SKILL.md` 创建 Markdown 文件。

### 添加新插件

创建 `.openharness/plugins/my-plugin/plugin.json` 和相应组件。

## 部署架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLI/oh    │     │   React UI  │     │   脚本/API  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ↓
                   ┌───────────────┐
                   │  QueryEngine  │
                   └───────┬───────┘
                           ↓
       ┌───────────────────┼───────────────────┐
       ↓                   ↓                   ↓
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Tools     │     │   Skills    │     │   Plugins   │
└─────────────┘     └─────────────┘     └─────────────┘
                           ↓
                   ┌───────────────┐
                   │  API Client   │
                   │  (Anthropic,  │
                   │   OpenAI, ...) │
                   └───────────────┘
```

## 进一步阅读

- [Agent 循环引擎](./core/agent-loop.md)
- [工具系统](./core/tools.md)
- [权限系统](./core/permissions.md)
- [钩子系统](./core/hooks.md)
- [插件系统](./core/plugins.md)
