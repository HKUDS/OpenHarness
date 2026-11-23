# InsightAgent

InsightAgent 是构建在 **OpenHarness Agent 内核**之上的多用户 Web 数据智能体：

- 注册 / 登录 / 修改密码，账号与 Token 存在 SQLite
- 每个用户的数据完全隔离（会话、文件、模型配置、能力配置按用户 id 分目录）
- 用户可自行配置模型服务（OpenAI 兼容 / Anthropic 等），Key 只落在自己的 home
- 能力分两层：**系统内置**（所有用户可用）与**用户自定义**（同名覆盖内置），覆盖插件、Skill 与 MCP
- 流式对话（SSE）、中断生成、附件、产出文件下载
- 一份前端双端自适应：≥900px 为桌面控制台，窄屏自动切移动端布局

---

## 与 OpenHarness 的关系

```
openharness-ai（本仓库）
├── src/openharness/   Agent 内核：运行时、工具、模型认证、配置解析、插件/Skill/MCP、会话存储
├── insightagent/      Web 应用层（本项目）
└── ohmo/              内置插件/能力包
```

- `openharness` 提供 agent 运行时与全部底层能力，本身是**单用户 CLI 形态**，不感知账号体系
- `insightagent` 只做应用层封装，不修改内核：
  - 用 `OPENHARNESS_CONFIG_DIR` 把进程级「全局 home」临时切到某个用户的 home，再由全局锁串行化，从而让单用户内核安全地服务多用户
  - 禁用系统 keyring（多用户下不可用），凭证统一存各用户 home 的 `credentials.json`
  - 在 FastAPI 上暴露 `/api/auth`、`/api/chat`、`/api/sessions`、`/api/capabilities`、`/api/user/*`
  - 托管 Vue3 构建产物，前后端同源，无需单独部署
- 依赖方向是单向的：`insightagent → openharness`。命令行入口仍是 `insightagent`，底层 `oh` / `openharness` 命令不受影响

---

## 快速开始

前置：Python ≥ 3.10、Node.js ≥ 18（仅构建前端时需要）。

```powershell
# 1. 安装 Python 依赖
cd e:\工作文档\OpenHarness
uv sync                       # 或：python -m venv .venv 后 pip install -e .

# 2. 构建前端（仓库已包含 dist 时可跳过）
cd insightagent\frontend
npm install
npm run build

# 3. 启动服务
cd e:\工作文档\OpenHarness
.\.venv\Scripts\python.exe -m insightagent serve --config .openharness-home\config.yaml
```

浏览器打开 <http://127.0.0.1:8760/> ，首个访问者请先注册账号。

常用参数：

```powershell
# 覆盖监听地址/端口
.\.venv\Scripts\python.exe -m insightagent serve --port 9000 --host 0.0.0.0

# 自检：数据库 / Milvus / embedding / LLM profile / 能力插件
.\.venv\Scripts\python.exe -m insightagent check --config .openharness-home\config.yaml

# 命令行单次提问（不经 Web）
.\.venv\Scripts\python.exe -m insightagent ask "统计近 7 天订单量" --config .openharness-home\config.yaml
```

不传 `--config` 时读取默认配置 `~/.insightagent/config.yaml`，数据也落在 `~/.insightagent/`。

### 前端开发模式

```powershell
# 终端 A：后端（vite 代理目标为 8000）
.\.venv\Scripts\python.exe -m insightagent serve --config .openharness-home\config.yaml --port 8000

# 终端 B：前端热更新
cd insightagent\frontend
npm run dev        # http://127.0.0.1:5173
```

只改前端时无需重启后端，`npm run build` 后刷新页面即可。

---

## 项目结构

```
insightagent/
├── cli.py              # 命令行入口：serve / check / ask / plugins
├── server.py           # FastAPI 应用：鉴权中间件、SSE 对话、会话/能力/用户 API、托管前端
├── users.py            # 用户库（SQLite）：注册、登录、Token、改密、用户目录播种与修复
├── capabilities.py     # 能力聚合：系统 + 用户双层（插件 / Skill / MCP / 模型 profiles）
├── plugin_support.py   # 能力条目的安装、启用与元数据读取
├── session_pool.py     # 按用户构建并缓存 agent 运行时（切换 OPENHARNESS_CONFIG_DIR）
├── session_files.py    # 会话附件与产出文件的存取
├── config.py           # 配置模型与加载（server / sessions / databases / milvus / embedding）
├── storage.py          # 会话持久化（sessions.db）
├── retrieve/           # 数据检索（SQL / 向量）
├── db/                 # 数据库连接与方言
├── prompts.py          # 系统提示词
└── frontend/           # Vue3 + Vite 前端
    ├── src/App.vue             # 视口分流：桌面控制台 / 移动端
    ├── src/desktop/            # 桌面端：DesktopShell、DesktopChat、CapabilityCenter
    ├── src/views/              # 移动端页面：登录、会话、聊天、能力、我的
    ├── src/chat/               # 共用会话逻辑：流式请求、会话 store、Markdown 渲染、能力选择
    ├── src/components/         # 通用组件：TabBar、Icon、Sheet
    └── src/styles.css          # 全站唯一样式源（微信读书视觉语言 token）
```

---

## 数据目录

系统侧（配置文件同目录，本仓库示例为 `.openharness-home/`）：

```
.openharness-home/
├── config.yaml         # 服务、数据源、Milvus、embedding 配置
├── settings.json       # 系统内置模型 profiles、MCP、能力开关
├── credentials.json    # 系统凭证（槽位：openai / anthropic / profile:<name> …）
└── sessions/
    ├── sessions.db     # 命令行/历史会话
    └── users/          # 多用户数据根目录
```

用户侧：

```
sessions/users/
├── users.db                    # 账号表 users + 登录 Token 表 tokens
└── <user_id>/
    ├── home/                   # 该用户的 openharness home
    │   ├── settings.json       # 模型 profiles / MCP（首次注册从系统 home 播种）
    │   ├── credentials.json    # 该用户自己的 API Key
    │   ├── skills/             # 用户自定义 Skill
    │   └── plugins/            # 用户自定义插件
    └── sessions/               # 该用户全部会话（sessions.db + files/）
```

首次注册会把系统 `settings.json` / `credentials.json` 复制到用户 home；对缺失或为空的老用户目录，登录后会自动补齐。

---

## 模型配置

两种方式：

1. **页面操作**：登录后进入「我的 → 模型服务」，新增/编辑 profile 并填入 API Key，保存后模型对该用户立即可用
2. **直接改文件**：编辑用户 home 的 `settings.json` 的 `profiles` 与 `active_profile`，Key 写入 `credentials.json`

凭证槽位规则：profile 显式声明 `credential_slot` 时用 `profile:<slot>`，否则按 `auth_source` 映射为 `openai` / `anthropic` 等。接口不回传明文 Key，只返回 `has_api_key`。

---

## 测试

```powershell
cd e:\工作文档\OpenHarness
.\.venv\Scripts\python.exe -m pytest tests\test_insightagent_server.py -q
```
