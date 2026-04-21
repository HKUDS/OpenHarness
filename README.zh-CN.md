# <img src="assets/logo.png" alt="OpenHarness" width="40" style="vertical-align: middle;"> `oh` — OpenHarness 中文说明

<p align="center">
  <a href="README.md"><strong>English</strong></a> ·
  <a href="README.zh-CN.md"><strong>简体中文</strong></a>
</p>

**OpenHarness** 是一个面向开源社区的 Agent Harness。它提供轻量、可扩展、可检查的 Agent 基础设施，包括：

- Agent loop
- tools / skills / plugins
- memory / session resume
- permissions / hooks
- multi-agent coordination
- provider workflows
- React TUI
- `ohmo` personal-agent app

---

## 最新更新

### 2026-04-06 · v0.1.2

- 新增统一配置入口 `oh setup`
- provider 配置从“auth -> provider -> model”收敛成 workflow 视角
- Anthropic/OpenAI 兼容接口支持 profile 级凭据，不再强制共用一把全局 key
- 新增 `ohmo` personal-agent app
- `ohmo` 使用 `~/.ohmo` 作为 home workspace，支持 gateway、bootstrap prompts 和交互式 channel 配置

---

## 快速开始

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash
```

常用安装参数：

- `--from-source`：从源码安装，适合贡献者
- `--with-channels`：一并安装 IM channel 依赖

例如：

```bash
curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash -s -- --from-source --with-channels
```

### 本地运行

```bash
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev
uv run oh
```

---

## 配置模型与 Provider

现在最推荐的入口是：

```bash
oh setup
```

`oh setup` 会按下面的顺序引导：

1. 选择一个 workflow
2. 如果需要，完成认证
3. 选择具体后端 preset
4. 确认模型
5. 保存并激活 profile

当前内置 workflow 包括：

- `Anthropic-Compatible API`
- `Claude Subscription`
- `OpenAI-Compatible API`
- `Codex Subscription`
- `GitHub Copilot`

### Anthropic-Compatible API

适合这类后端：

- Claude 官方 API
- Moonshot / Kimi
- Zhipu / GLM
- MiniMax
- 其他 Anthropic-compatible endpoint

### OpenAI-Compatible API

适合这类后端：

- OpenAI 官方 API
- OpenRouter
- DashScope
- DeepSeek
- GitHub Models
- SiliconFlow
- Google Gemini
- Groq
- Ollama
- 其他 OpenAI-compatible endpoint

### 常用命令

```bash
# 统一配置入口
oh setup

# 查看已有 workflow/profile
oh provider list

# 切换当前 workflow
oh provider use codex

# 查看认证状态
oh auth status
```

### 高级：添加自定义兼容接口

如果内置 preset 不够，可以直接新增 profile：

```bash
oh provider add my-endpoint \
  --label "My Endpoint" \
  --provider anthropic \
  --api-format anthropic \
  --auth-source anthropic_api_key \
  --model my-model \
  --base-url https://example.com/anthropic
```

这一版开始，兼容接口可以按 profile 绑定凭据。  
也就是说，`Kimi`、`GLM`、`MiniMax` 这类 Anthropic-compatible 后端，不需要再共用一把全局 `anthropic` key。

---

## 交互模式与 TUI

运行：

```bash
oh
```

你会得到 React/Ink TUI，支持：

- `/` 命令选择器
- 交互式权限确认
- `/model` 模型切换
- `/permissions` 权限模式切换
- `/resume` 会话恢复
- `/provider` workflow 选择

非交互模式也支持：

```bash
oh -p "Explain this repository"
oh -p "List all functions in main.py" --output-format json
oh -p "Fix the bug" --output-format stream-json
```

---

## Provider 兼容性概览

OpenHarness 现在把 provider 视为 **workflow + profile**，而不是只暴露底层协议名。

| Workflow | 说明 |
|----------|------|
| `Anthropic-Compatible API` | Anthropic 风格接口，适合 Claude/Kimi/GLM/MiniMax 等 |
| `Claude Subscription` | 复用本地 `~/.claude/.credentials.json` |
| `OpenAI-Compatible API` | OpenAI 风格接口，适合 OpenAI/OpenRouter/各种兼容网关 |
| `Codex Subscription` | 复用本地 `~/.codex/auth.json` |
| `GitHub Copilot` | GitHub Copilot OAuth workflow |

日常推荐用法：

```bash
oh setup
oh provider list
oh provider use <profile>
```

---

## `ohmo` Personal Agent

`ohmo` 是基于 OpenHarness 的 personal-agent app，不是 core 的一个 mode。

### 初始化

```bash
ohmo init
```

这会创建：

- `~/.ohmo/soul.md`
- `~/.ohmo/identity.md`
- `~/.ohmo/user.md`
- `~/.ohmo/BOOTSTRAP.md`
- `~/.ohmo/memory/`
- `~/.ohmo/gateway.json`

其中：

- `soul.md`：长期人格与行为原则
- `identity.md`：`ohmo` 自己是谁
- `user.md`：用户画像、偏好、关系信息
- `BOOTSTRAP.md`：首轮 landing / onboarding ritual
- `memory/`：personal memory
- `gateway.json`：gateway 的 profile 和 channel 配置

### 配置

```bash
ohmo config
```

`ohmo config` 会用和 `oh setup` 一致的 workflow 语言来配置 gateway，例如：

- `Anthropic-Compatible API`
- `Claude Subscription`
- `OpenAI-Compatible API`
- `Codex Subscription`
- `GitHub Copilot`

目前 `ohmo init` / `ohmo config` 已支持引导式配置这些 channel：

- Telegram
- Slack
- Discord
- Feishu

如果 gateway 已经在运行，配置完成后也可以直接选择是否重启。

### 运行

```bash
# 运行 personal agent
ohmo

# 前台运行 gateway
ohmo gateway run

# 查看 gateway 状态
ohmo gateway status

# 重启 gateway
ohmo gateway restart
```

---

## OpenHarness 的核心能力

### Agent Loop

- streaming tool-call cycle
- tool execution / observation / loop
- retry + exponential backoff
- token counting 与成本跟踪

### Tools / Skills / Plugins

- 43+ tools
- Markdown skills 按需加载
- 插件生态
- 兼容 `anthropics/skills`
- 兼容 Claude-style plugins

### Memory / Session

- `CLAUDE.md` 自动发现与注入
- `MEMORY.md` 持久记忆
- session resume
- auto-compact

### Governance

- 多级 permission mode
- path rules
- denied commands
- hooks
- interactive approval

### Multi-Agent

- subagent spawning
- team registry
- task lifecycle
- background task execution

---

## 常见命令

### `oh`

```bash
oh setup
oh provider list
oh provider use codex
oh auth status
oh -p "Explain this codebase"
oh
```

### `ohmo`

```bash
ohmo init
ohmo config
ohmo
ohmo gateway run
ohmo gateway status
ohmo gateway restart
```

---

## 测试

```bash
uv run pytest -q
python scripts/test_harness_features.py
python scripts/test_real_skills_plugins.py
```

---

## 贡献

欢迎贡献：

- tools
- skills
- plugins
- providers
- multi-agent coordination
- tests
- 文档与中文翻译

开发环境：

```bash
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev
uv run pytest -q
```

更多信息：

- [贡献指南](CONTRIBUTING.md)
- [更新日志](CHANGELOG.md)
- [Showcase](docs/SHOWCASE.md)

---

## License

MIT，见 [LICENSE](LICENSE)。
