# 命令系统

OpenHarness 提供 54+ 内置斜杠命令（slash commands），用于控制会话、管理任务、查询状态等。

## 架构总览

```mermaid
flowchart LR
    CommandRegistry --> SlashCommand
    SlashCommand --> name
    SlashCommand --> description
    SlashCommand --> handler
    handler --> CommandHandler
    CommandHandler --> CommandContext
    CommandResult --> message
    CommandResult --> should_exit
    CommandResult --> refresh_runtime
```

## 核心类型

### SlashCommand

```python
@dataclass
class SlashCommand:
    name: str                           # 命令名称
    description: str                    # 命令描述
    handler: CommandHandler             # 处理函数
```

### CommandHandler

```python
CommandHandler = Callable[[str, CommandContext], Awaitable[CommandResult]]
```

处理函数接收：
- `args: str` — 命令参数
- `context: CommandContext` — 执行上下文

### CommandResult

命令执行结果：

```python
@dataclass
class CommandResult:
    message: str | None = None          # 返回消息
    should_exit: bool = False           # 是否退出
    clear_screen: bool = False          # 是否清屏
    replay_messages: list | None = None # TUI 重放消息
    continue_pending: bool = False      # 继续待处理工具循环
    continue_turns: int | None = None   # 继续的轮次
    refresh_runtime: bool = False        # 刷新运行时
    submit_prompt: str | None = None    # 提交提示
    submit_model: str | None = None     # 提交使用的模型
```

### CommandContext

```python
@dataclass
class CommandContext:
    engine: QueryEngine                 # 查询引擎
    hooks_summary: str = ""             # 钩子摘要
    mcp_summary: str = ""               # MCP 摘要
    plugin_summary: str = ""            # 插件摘要
    cwd: str = "."                      # 当前目录
    tool_registry: ToolRegistry | None = None
    app_state: AppStateStore | None = None
    session_backend: SessionBackend = DEFAULT_SESSION_BACKEND
    session_id: str | None = None
    extra_skill_dirs: Iterable[str | Path] | None = None
    extra_plugin_roots: Iterable[str | Path] | None = None
```

## 命令注册表

`CommandRegistry`（位于 `src/openharness/commands/registry.py`）管理所有命令：

```python
class CommandRegistry:
    def register(self, command: SlashCommand) -> None:
        """注册命令"""

    def lookup(self, raw_input: str) -> tuple[SlashCommand, str] | None:
        """解析并查找命令，返回 (command, args)"""

    def help_text(self) -> str:
        """生成帮助文本"""

    def list_commands(self) -> list[SlashCommand]:
        """列出所有命令"""
```

命令解析：
```text
/command arg1 arg2
     │      │
     │      └── args
     └── name
```

## 内置命令

### 会话管理

| 命令 | 说明 | 示例 |
|-----|------|-----|
| `/help` | 显示帮助 | `/help` |
| `/exit` | 退出 | `/exit` |
| `/clear` | 清空对话历史 | `/clear` |
| `/version` | 显示版本 | `/version` |
| `/resume` | 恢复会话 | `/resume <session_id>` |
| `/session` | 会话管理 | `/session show\|ls\|path\|tag\|clear` |
| `/export` | 导出为 Markdown | `/export` |
| `/share` | 创建共享快照 | `/share` |
| `/rewind` | 回退对话轮次 | `/rewind [N]` |
| `/tag` | 标记当前会话 | `/tag <name>` |

### 状态和信息

| 命令 | 说明 |
|-----|------|
| `/status` | 显示会话状态 |
| `/stats` | 显示统计信息 |
| `/context` | 显示当前系统提示 |
| `/summary` | 总结对话历史 |
| `/usage` | 显示 Token 使用量 |
| `/cost` | 显示估算成本 |
| `/doctor` | 环境诊断 |

### 工具和插件

| 命令 | 说明 |
|-----|------|
| `/skills` | 查看技能 |
| `/hooks` | 查看钩子配置 |
| `/plugins` | 插件管理 |
| `/reload-plugins` | 重新加载插件 |
| `/mcp` | MCP 管理 |

### 记忆和文件

| 命令 | 说明 |
|-----|------|
| `/memory` | 记忆管理 |
| `/files` | 列出文件 |
| `/init` | 初始化项目 |

### Git 操作

| 命令 | 说明 |
|-----|------|
| `/diff` | 显示 Git 差异 |
| `/branch` | Git 分支信息 |
| `/commit` | Git 提交 |

### 配置管理

| 命令 | 说明 |
|-----|------|
| `/config` | 显示/修改配置 |
| `/permissions` | 权限模式管理 |
| `/plan` | 切换 Plan 模式 |
| `/model` | 模型管理 |
| `/provider` | Provider 管理 |
| `/theme` | 主题管理 |
| `/fast` | 快速模式 |
| `/effort` | 推理努力度 |
| `/passes` | 推理遍数 |
| `/turns` | 最大轮次 |

### 任务管理

| 命令 | 说明 |
|-----|------|
| `/tasks` | 任务管理 |
| `/agents` | Agent 管理 |
| `/bridge` | Bridge 会话管理 |

### 工具快捷

| 命令 | 说明 |
|-----|------|
| `/copy` | 复制到剪贴板 |
| `/login` | 登录/显示认证状态 |
| `/logout` | 清除认证 |
| `/feedback` | 保存反馈 |
| `/onboarding` | 快速入门 |

## 命令处理流程

```text
用户输入: /command arg1 arg2
                │
                ▼
    CommandRegistry.lookup()
                │
                ▼
    解析命令名称和参数
                │
                ▼
    调用 handler(args, context)
                │
                ▼
    返回 CommandResult
                │
        ┌───────┼───────┐
        │       │       │
    message   exit    refresh
```

## 自定义命令

### 1. 定义命令处理器

```python
async def my_command_handler(args: str, context: CommandContext) -> CommandResult:
    # 处理命令逻辑
    return CommandResult(
        message="操作完成",
        refresh_runtime=True
    )
```

### 2. 注册命令

```python
registry = create_default_command_registry()
registry.register(SlashCommand(
    name="my-cmd",
    description="我的自定义命令",
    handler=my_command_handler
))
```

### 3. 插件贡献命令

插件通过 `PluginCommandDefinition` 贡献命令：

```python
# 插件 commands/my-cmd.md
---
name: my-cmd
description: 我的插件命令
argument-hint: <参数>
model: sonnet
---

这里是命令的内容...
```

## 特殊命令处理

### 继续工具循环

```python
# /continue 命令
return CommandResult(
    continue_pending=True,
    continue_turns=None  # 或指定轮次
)
```

### 提交提示给模型

```python
# 插件命令
return CommandResult(
    submit_prompt="用户提供的提示",
    submit_model="sonnet"  # 可选
)
```

### 刷新运行时

```python
# 修改设置后刷新
return CommandResult(
    message="设置已更新",
    refresh_runtime=True
)
```

## 命令执行上下文

`CommandContext` 提供对各种子系统的访问：

```python
async def my_command(args: str, context: CommandContext) -> CommandResult:
    # 访问 QueryEngine
    messages = context.engine.messages

    # 访问工具注册表
    tools = context.tool_registry.list_tools()

    # 访问任务管理器
    tasks = get_task_manager().list_tasks()

    # 访问记忆系统
    memory_files = list_memory_files(context.cwd)

    # 保存快照
    context.session_backend.save_snapshot(...)

    return CommandResult(message="完成")
```

## 插件命令

插件命令通过 `_render_plugin_command_prompt()` 处理：

```python
def _render_plugin_command_prompt(
    command: PluginCommandDefinition,
    args: str,
    session_id: str | None = None
) -> str:
    prompt = command.content
    # 替换参数占位符
    prompt = prompt.replace("$ARGUMENTS", args)
    # 添加会话信息
    if session_id:
        prompt = prompt.replace("${CLAUDE_SESSION_ID}", session_id)
    return prompt
```

## 扩展点

### 1. 命令别名

```python
# 在注册表中添加别名
registry.register(SlashCommand(
    name="alias",
    description="...",
    handler=original_command.handler
))
```

### 2. 动态命令

```python
def create_dynamic_command(name: str, handler: Callable) -> SlashCommand:
    return SlashCommand(name=name, description="Dynamic command", handler=handler)
```

### 3. 命令拦截

```python
class LoggingCommandRegistry(CommandRegistry):
    async def lookup(self, raw_input: str):
        log(f"Command invoked: {raw_input}")
        return await super().lookup(raw_input)
```

## 与其他模块的关系

- **Engine** — `/continue` 命令触发 `continue_pending`
- **Memory** — `/memory` 命令操作记忆文件
- **Tasks** — `/tasks` 命令管理后台任务
- **Plugins** — 插件贡献命令定义
- **Config** — `/config` 命令修改设置

## 关键文件

| 文件 | 职责 |
|-----|------|
| `commands/registry.py` | CommandRegistry 和内置命令 |
| `tools/base.py` | CommandContext 中使用的类型 |
