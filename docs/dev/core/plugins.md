# 插件系统

OpenHarness 插件系统提供扩展机制，允许通过插件添加自定义命令、Hook、Agent 和 MCP 服务器。插件格式与 [claude-code/plugins](https://github.com/anthropics/claude-code/tree/main/plugins) 兼容。

## 架构总览

```mermaid
flowchart TB
    PluginManifest --> name
    PluginManifest --> version
    PluginManifest --> description
    PluginManifest --> skills_dir
    PluginManifest --> commands
    PluginManifest --> agents
    PluginManifest --> hooks_file
    PluginManifest --> mcp_file
    LoadedPlugin --> manifest
    LoadedPlugin --> skills
    LoadedPlugin --> commands
    LoadedPlugin --> agents
    LoadedPlugin --> hooks
    LoadedPlugin --> mcp_servers
```

## 核心类型

### PluginManifest

```python
# src/openharness/plugins/schemas.py
class PluginManifest(BaseModel):
    name: str
    version: str
    description: str
    enabled_by_default: bool = True
    skills_dir: str = "skills"
    commands: list[str] | dict[str, Any] = Field(default_factory=list)
    agents: list[str] | dict[str, Any] = Field(default_factory=list)
    hooks_file: str = "hooks/hooks.json"
    mcp_file: str = ".mcp.json"
```

### LoadedPlugin

```python
# src/openharness/plugins/types.py
@dataclass(frozen=True)
class LoadedPlugin:
    manifest: PluginManifest
    path: Path
    enabled: bool
    skills: list[SkillDefinition] = field(default_factory=list)
    commands: list[PluginCommandDefinition] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    hooks: dict[str, list] = field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
```

### PluginCommandDefinition

```python
@dataclass(frozen=True)
class PluginCommandDefinition:
    name: str
    description: str
    content: str
    path: str | None = None
    source: str = "plugin"
    base_dir: str | None = None
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    effort: str | int | None = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    is_skill: bool = False
    display_name: str | None = None
```

## 插件发现与加载

### 发现路径

插件从以下位置发现：

```text
# 用户插件目录
~/.openharness/plugins/

# 项目插件目录
<cwd>/.openharness/plugins/

# 额外指定的根目录
extra_plugin_roots
```

### 加载流程

```python
def load_plugins(settings, cwd, extra_roots=None):
    plugins = []
    for path in discover_plugin_paths(cwd, extra_roots=extra_roots):
        plugin = load_plugin(path, settings.enabled_plugins)
        if plugin is not None:
            plugins.append(plugin)
    return plugins
```

### 插件目录结构

标准插件结构：

```text
my-plugin/
  plugin.json                    ← 插件清单
  skills/
    SKILL.md                      ← 插件技能
  commands/
    help.md                       ← 命令文件
  agents/
    my-agent.md                   ← Agent 定义
  hooks/
    hooks.json                    ← Hook 配置
  .mcp.json                       ← MCP 服务器配置
```

或使用 Claude Code 兼容格式：

```text
my-plugin/
  .claude-plugin/
    plugin.json
  skills/
    SKILL.md
  ...
```

## plugin.json 格式

```json
{
  "name": "commit-commands",
  "version": "1.0.0",
  "description": "Git commit, push, and PR workflows",
  "enabled_by_default": true,
  "skills_dir": "skills",
  "commands": ["commands"],
  "agents": ["agents"],
  "hooks_file": "hooks/hooks.json",
  "mcp_file": ".mcp.json"
}
```

### commands 字段

支持两种格式：

```json
// 格式 1: 字符串列表（目录路径）
"commands": ["commands"]

// 格式 2: 字典（命令名 -> 元数据）
"commands": {
  "commit": {
    "source": "commands/commit.md",
    "description": "Create a git commit",
    "model": "sonnet"
  }
}
```

## 生命周期

### 1. 发现阶段

```
discover_plugin_paths() → [Path, ...]
```

### 2. 加载阶段

```
load_plugin(path, enabled_plugins) → LoadedPlugin | None
```

### 3. 注册阶段

加载后的插件贡献被合并到：

- `SkillRegistry` — 技能
- `CommandRegistry` — 命令
- `AgentRegistry` — Agent
- `HookRegistry` — Hook
- `MCPConfig` — MCP 服务器

### 4. 启用/禁用

```python
# 启用插件
settings.enabled_plugins["my-plugin"] = True
save_settings(settings)

# 禁用插件
settings.enabled_plugins["my-plugin"] = False
save_settings(settings)
```

## 插件贡献

### 贡献命令

命令文件格式（Markdown）：

```markdown
---
name: commit
description: Create a clean git commit
argument-hint: <commit message>
when_to_use: When you need to commit changes
model: sonnet
---

# Commit Command

Use this command to create well-structured git commits.

## Steps
1. Review staged changes
2. Write commit message
3. Execute git commit
```

命令注册后可通过 `/plugin-name:commit` 调用。

### 贡献 Agent

Agent 定义格式（Markdown + YAML frontmatter）：

```markdown
---
name: code-review
description: Specialized code review agent
tools:
  - Read
  - Grep
  - Glob
model: haiku
permissionMode: dontAsk
background: true
---

# Code Review Agent

You are a code review specialist...
```

### 贡献 Hook

`hooks/hooks.json` 格式：

```json
{
  "pre_tool_use": [
    {
      "type": "command",
      "command": "echo 'About to use ${tool_name}'",
      "matcher": "Write"
    }
  ],
  "post_tool_use": [
    {
      "type": "prompt",
      "prompt": "Was this {tool_name} call safe?",
      "block_on_failure": true
    }
  ]
}
```

### 贡献 MCP 服务器

`.mcp.json` 格式：

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    }
  }
}
```

## 管理命令

```bash
# 列出插件
oh plugin list

# 启用插件
oh plugin enable <name>

# 禁用插件
oh plugin disable <name>

# 安装插件
oh plugin install <path>

# 卸载插件
oh plugin uninstall <name>

# 重新加载插件
/reload-plugins
```

## 扩展点

### 1. 自定义插件加载

扩展 `load_plugin()` 处理新的贡献类型：

```python
def load_plugin(path: Path, enabled_plugins: dict[str, bool]) -> LoadedPlugin | None:
    # 添加新的加载逻辑
    ...
```

### 2. 插件发现

扩展 `discover_plugin_paths()` 添加新的发现路径：

```python
def discover_plugin_paths(cwd, extra_roots=None):
    roots = [get_user_plugins_dir(), get_project_plugins_dir(cwd)]
    if extra_roots:
        roots.extend(extra_roots)
    # 添加自定义根目录
    ...
```

## 与其他模块的关系

- **Skills** — 插件技能通过 `load_plugin_skills()` 加载
- **Commands** — 插件命令通过 `load_plugin_commands()` 加载
- **Agents** — 插件 Agent 通过 `load_plugin_agents()` 加载
- **Hooks** — 插件 Hook 通过 `load_plugin_hooks()` 加载
- **MCP** — 插件 MCP 服务器通过 `load_plugin_mcp()` 加载

## 关键文件

| 文件 | 职责 |
|-----|------|
| `plugins/loader.py` | 插件发现和加载 |
| `plugins/types.py` | LoadedPlugin, PluginCommandDefinition |
| `plugins/schemas.py` | PluginManifest Pydantic 模型 |
| `plugins/installer.py` | 插件安装/卸载 |
