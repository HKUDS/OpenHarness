# QWEN.md - OpenHarness 项目上下文

## 项目概述

**OpenHarness**（`oh`）是一个开源的 Python Agent Harness 框架，为 LLM 提供完整的代理基础设施，包括工具使用、技能、记忆、权限管理和多代理协调。

### 核心特性

- **🧠 Agent Loop**: 流式工具调用循环，支持 API 重试、并行工具执行、Token 计数与成本追踪
- **🔧 43+ 工具**: 文件 I/O、Shell、搜索、Web、MCP 等
- **📚 技能系统**: 按需加载的知识库（.md 文件），兼容 anthropics/skills
- **🔌 插件系统**: 兼容 claude-code 插件，支持命令、钩子、代理和 MCP 服务器
- **🛡️ 权限管理**: 多级权限模式、路径规则、命令拒绝、交互式审批对话框
- **🤝 多代理协调**: 子代理生成、团队注册、任务管理、后台任务生命周期
- **🖥️ 终端 UI**: React/Ink TUI，支持命令选择器、权限对话框、会话恢复

### 项目结构

```
OpenHarness/
├── src/openharness/       # 核心 Python 包
│   ├── engine/            # Agent 循环引擎
│   ├── tools/             # 工具注册与实现
│   ├── skills/            # 技能加载器
│   ├── plugins/           # 插件系统
│   ├── permissions/       # 权限管理
│   ├── hooks/             # 生命周期钩子
│   ├── commands/          # 命令系统
│   ├── mcp/               # MCP 客户端
│   ├── memory/            # 持久记忆
│   ├── tasks/             # 后台任务管理
│   ├── coordinator/       # 多代理协调
│   ├── prompts/           # 系统提示组装
│   ├── config/            # 多层配置
│   ├── ui/                # React TUI 后端
│   ├── api/               # API 客户端
│   ├── auth/              # 认证管理
│   └── ...
├── ohmo/                  # ohmo 个人代理应用
├── frontend/terminal/     # React TUI 前端
├── tests/                 # 测试套件（114+ 测试）
├── scripts/               # 安装和测试脚本
└── docs/                  # 文档
```

## 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python ≥ 3.10, TypeScript (前端) |
| **框架** | Typer (CLI), Pydantic (验证), Anthropic/OpenAI SDK |
| **前端** | React + Ink (终端 UI) |
| **测试** | pytest, pytest-asyncio, pexpect (E2E) |
| **代码质量** | ruff, mypy |
| **包管理** | uv, hatchling |

## 构建与运行

### 安装

```bash
# 克隆并安装
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev

# 可选：安装前端依赖
cd frontend/terminal && npm ci && cd ../..
```

### 运行

```bash
# 交互式模式
uv run oh

# 非交互式（单提示词）
uv run oh -p "解释这个代码库"

# JSON 输出
uv run oh -p "列出所有函数" --output-format json

# 流式 JSON
uv run oh -p "修复 bug" --output-format stream-json
```

### 配置 Provider

```bash
# 交互式配置向导
uv run oh setup

# 查看/切换 provider
uv run oh provider list
uv run oh provider use <profile>
```

### 环境变量

```bash
# Anthropic 兼容 API
export ANTHROPIC_BASE_URL=https://api.moonshot.cn/anthropic
export ANTHROPIC_API_KEY=your_key
export ANTHROPIC_MODEL=kimi-k2.5

# OpenAI 兼容 API
export OPENHARNESS_API_FORMAT=openai
export OPENAI_API_KEY=your_key
```

### ohmo 个人代理

```bash
ohmo init              # 初始化 ~/.ohmo 工作区
ohmo config            # 配置 gateway 和 provider
ohmo                   # 运行个人代理
ohmo gateway run       # 运行 gateway
```

## 测试

```bash
# 运行所有单元测试和集成测试
uv run pytest -q

# 代码检查
uv run ruff check src tests scripts

# 类型检查（可选）
uv run mypy src/openharness

# 前端 TypeScript 检查
cd frontend/terminal && npx tsc --noEmit
```

### E2E 测试

```bash
# Harness 功能 E2E
python scripts/test_harness_features.py

# 真实插件 E2E
python scripts/test_real_skills_plugins.py
```

## 开发约定

### 代码风格

- **行长度**: 100 字符（ruff 配置）
- **类型注解**: 使用严格模式（mypy strict）
- **输入验证**: 使用 Pydantic 模型验证工具输入

### 添加自定义工具

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

### 添加自定义技能

创建 `~/.openharness/skills/my-skill.md`：

```markdown
---
name: my-skill
description: 特定领域的专业指导
---

# My Skill

## 何时使用
当用户询问 [你的领域] 时使用。

## 工作流
1. 第一步
2. 第二步
...
```

### 添加插件

创建 `.openharness/plugins/my-plugin/.claude-plugin/plugin.json`：

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "自定义插件"
}
```

## 关键架构模式

### Agent 循环

```python
while True:
    response = await api.stream(messages, tools)
    if response.stop_reason != "tool_use":
        break  # 完成
    for tool_call in response.tool_uses:
        # 权限检查 → 钩子 → 执行 → 钩子 → 结果
        result = await harness.execute_tool(tool_call)
    messages.append(tool_results)
    # 循环继续
```

### 提供者兼容性

| 工作流 | 支持的提供商 |
|--------|-------------|
| Anthropic-Compatible | Claude 官方, Kimi, GLM, MiniMax |
| OpenAI-Compatible | OpenAI, OpenRouter, DashScope, DeepSeek, Groq, Ollama |
| Claude Subscription | 本地 Claude CLI 凭证 |
| Codex Subscription | 本地 Codex 凭证 |
| GitHub Copilot | GitHub OAuth 设备流 |

## 重要文件

| 文件 | 描述 |
|------|------|
| `README.md` | 主要文档：快速开始、特性、架构 |
| `pyproject.toml` | 项目配置、依赖、脚本 |
| `CHANGELOG.md` | 版本变更历史 |
| `CONTRIBUTING.md` | 贡献指南 |
| `docs/SHOWCASE.md` | 使用示例 |
| `src/openharness/cli.py` | CLI 入口点 |

## 注意事项

- 项目使用 MIT 许可证
- 当前版本：v0.1.2
- 测试覆盖率：114+ 测试通过
- 兼容 anthropics/skills 和 claude-code/plugins
- 支持多语言记忆搜索（包括中文 Han 字符）
