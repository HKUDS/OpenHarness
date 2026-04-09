# Provider 配置

## 概述

OpenHarness 支持多种 AI Provider，通过统一的工作流（workflow）概念进行管理。Provider 配置采用 Profile 机制，支持同时配置多个 Provider 并快速切换。

## 工作流类型

| Workflow | 说明 | 适用后端 |
|----------|------|----------|
| Anthropic-Compatible API | Anthropic 风格接口 | Claude、Kimi、GLM、MiniMax 等 |
| Claude Subscription | Claude CLI 订阅 | Claude Code 订阅用户 |
| OpenAI-Compatible API | OpenAI 风格接口 | OpenAI、OpenRouter、DashScope 等 |
| Codex Subscription | Codex CLI 订阅 | Codex 订阅用户 |
| GitHub Copilot | GitHub Copilot OAuth | Copilot 用户 |

## 配置流程

### 引导式配置

```bash
oh setup
```

`oh setup` 会依次引导：
1. 选择 Provider workflow
2. 完成认证（如需要）
3. 选择/输入 Provider preset
4. 确认模型
5. 保存并激活 profile

### 手动配置

```bash
oh provider add <name> [选项]
```

## Anthropic-Compatible API

适合 Claude API 及所有 Anthropic 兼容接口。

### 支持的后端

- **Claude 官方 API** - api.anthropic.com
- **Moonshot/Kimi** - api.moonshot.cn
- **Zhipu/GLM** - lm.jina.ai 等
- **MiniMax** - api.minimax.chat
- **其他兼容接口** - 任何实现 Anthropic API 格式的后端

### 配置示例

```bash
# Claude 官方
oh setup
# 选择 Anthropic-Compatible API → Claude official

# Moonshot/Kimi
oh provider add kimi \
  --label "Moonshot Kimi" \
  --provider anthropic \
  --api-format anthropic \
  --auth-source moonshot_api_key \
  --model moonshot-v1-8k \
  --base-url https://api.moonshot.cn/anthropic
```

### 认证方式

| 认证源 | 说明 |
|--------|------|
| anthropic_api_key | Anthropic API Key |
| moonshot_api_key | Moonshot API Key |
| glm_api_key | Zhipu GLM API Key |
| minimax_api_key | MiniMax API Key |

## Claude Subscription

复用本地 Claude CLI 的订阅凭据。

### 前提条件

已安装 Claude CLI 并完成订阅认证：

```bash
claude auth
```

### 配置

```bash
oh auth claude-login
```

这会自动绑定 `~/.claude/.credentials.json` 中的凭据。

## OpenAI-Compatible API

适合 OpenAI API 及所有 OpenAI 兼容接口。

### 支持的后端

- **OpenAI 官方** - api.openai.com
- **OpenRouter** - openrouter.ai/api
- **DashScope** - dashscope.aliyuncs.com
- **DeepSeek** - api.deepseek.com
- **GitHub Models** - models.inference.github.com
- **SiliconFlow** - api.siliconflow.cn
- **Groq** - api.groq.com
- **Ollama** - localhost:11434（本地）

### 配置示例

```bash
# OpenAI 官方
oh setup
# 选择 OpenAI-Compatible API → OpenAI official

# OpenRouter
oh provider add openrouter \
  --label "OpenRouter" \
  --provider openai \
  --api-format openai \
  --auth-source openai_api_key \
  --model anthropic/claude-3.5-sonnet \
  --base-url https://openrouter.ai/api/v1

# 本地 Ollama
oh provider add ollama \
  --label "Local Ollama" \
  --provider openai \
  --api-format openai \
  --auth-source none \
  --model llama3.2 \
  --base-url http://localhost:11434/v1
```

### 认证方式

| 认证源 | 说明 |
|--------|------|
| openai_api_key | OpenAI API Key |
| dashscope_api_key | DashScope API Key |
| none | 无需认证（本地服务） |

## Codex Subscription

复用本地 Codex CLI 的订阅凭据。

### 前提条件

已安装 Codex CLI 并完成订阅：

```bash
codex auth
```

### 配置

```bash
oh auth codex-login
```

## GitHub Copilot

使用 GitHub OAuth 进行认证。

### 配置

```bash
oh auth copilot-login
```

支持：
- **github.com** - 公共 Copilot
- **GitHub Enterprise** - 自托管版本

#### GitHub Enterprise 配置

```bash
# 选择 2. GitHub Enterprise
# 输入 Enterprise URL
oh auth copilot-login
```

### 支持的功能

| 功能 | 状态 |
|------|------|
| 代码补全 | 完整 |
| 对话 | 完整 |
| 工具调用 | 完整 |

## Provider Profile 管理

### 列出 Profile

```bash
oh provider list
```

输出示例：
```text
* claude-api: Claude API [ready]
    auth=anthropic_api_key model=claude-sonnet-4-20250514 base_url=(default)
  kimi: Moonshot Kimi [ready]
    auth=moonshot_api_key model=moonshot-v1-8k base_url=https://api.moonshot.cn/anthropic
  openrouter: OpenRouter [ready]
    auth=openai_api_key model=anthropic/claude-3.5-sonnet base_url=https://openrouter.ai/api/v1
```

### 切换 Profile

```bash
oh provider use claude-api
oh provider use kimi
```

### 编辑 Profile

```bash
oh provider edit <name> [选项]
```

示例：
```bash
oh provider edit kimi --model moonshot-v1-32k
```

### 删除 Profile

```bash
oh provider remove <name>
```

## 认证管理

### 查看认证状态

```bash
oh auth status
```

输出：
```text
Auth sources:
Anthropic API key         configured   local      <-- active
OpenAI API key            configured   local
GitHub Copilot OAuth      configured   local

Provider profiles:
claude-api                anthropic    anthropic_api_key    ready     <-- active
openrouter                openai       openai_api_key       ready
copilot                   copilot      copilot_oauth        ready
```

### 清除认证

```bash
# 清除当前 profile 的认证
oh auth logout

# 清除指定 provider
oh auth logout anthropic
```

## 环境变量覆盖

可以通过环境变量临时覆盖配置：

| 变量 | 说明 |
|------|------|
| ANTHROPIC_API_KEY | Anthropic API Key |
| OPENAI_API_KEY | OpenAI API Key |
| OPENHARNESS_MODEL | 默认模型 |
| OPENHARNESS_BASE_URL | API Base URL |
| OPENHARNESS_API_FORMAT | API 格式（anthropic/openai/copilot） |

示例：
```bash
ANTHROPIC_API_KEY=sk-xxx oh -p "Hello"
```

## 配置文件

Provider 配置存储在 `~/.openharness/settings.json`：

```json
{
  "provider": "claude-api",
  "model": "claude-sonnet-4-20250514",
  "api_format": "anthropic",
  "base_url": null,
  "profiles": {
    "claude-api": {
      "label": "Claude API",
      "provider": "anthropic",
      "api_format": "anthropic",
      "auth_source": "anthropic_api_key",
      "default_model": "claude-sonnet-4-20250514",
      "last_model": "claude-sonnet-4-20250514"
    }
  }
}
```

## 常见问题

### Q: API 调用失败？

1. 检查认证状态：`oh auth status`
2. 确认 API Key 有效
3. 检查 Base URL 配置
4. 查看错误日志：`oh -d -p "test"`

### Q: 如何使用本地模型？

配置 Ollama 或其他本地服务：

```bash
oh provider add ollama \
  --label "Local" \
  --provider openai \
  --api-format openai \
  --auth-source none \
  --model llama3.2 \
  --base-url http://localhost:11434/v1
```

### Q: 切换 Provider 后模型不变？

使用 `--model` 参数指定模型，或在 profile 中设置 `last_model`。

### Q: 一个项目只能用一个 Provider？

不，可以同时配置多个 Provider，通过 `oh provider use` 切换。
