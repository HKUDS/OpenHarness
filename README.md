<h1 align="center"><img src="assets/logo.png" alt="OpenHarness" width="64" style="vertical-align: middle;">&nbsp; <code>oh</code> — OpenHarness: Open Agent Harness</h1>

• **O**pen**H**arness (**oh**) is an ultra-lightweight alternative to Claude Code with pure Python implementation

• **OpenHarness** delivers approximately 80% of essential agent functionality

• **OpenHarness** achieves this using just 3% of the lines of code compared to Claude Code

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-5_min-blue?style=for-the-badge" alt="Quick Start"></a>
  <a href="#-harness-architecture"><img src="https://img.shields.io/badge/Harness-Architecture-ff69b4?style=for-the-badge" alt="Architecture"></a>
  <a href="#-features"><img src="https://img.shields.io/badge/Tools-43+-green?style=for-the-badge" alt="Tools"></a>
  <a href="#-test-results"><img src="https://img.shields.io/badge/Tests-114_Passing-brightgreen?style=for-the-badge" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-≥3.11-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React+Ink-TUI-61DAFB?logo=react&logoColor=white" alt="React">
  <img src="https://img.shields.io/badge/pytest-114_pass-brightgreen" alt="Pytest">
  <img src="https://img.shields.io/badge/E2E-6_suites-orange" alt="E2E">
  <img src="https://img.shields.io/badge/output-text_|_json_|_stream--json-blueviolet" alt="Output">
  <a href="https://github.com/HKUDS/.github/blob/main/profile/README.md"><img src="https://img.shields.io/badge/Feishu-Group-E9DBFC?style=flat&logo=feishu&logoColor=white" alt="Feishu"></a>
  <a href="https://github.com/HKUDS/.github/blob/main/profile/README.md"><img src="https://img.shields.io/badge/WeChat-Group-C5EAB4?style=flat&logo=wechat&logoColor=white" alt="WeChat"></a>
</p>

One Command (**oh**) to Launch **OpenHarness** and Unlock All Agent Harnesses. 

Supports CLI agent integration including OpenClaw, nanobot, Cursor, and more.

<p align="center">
  <img src="assets/cli-typing.gif" alt="OpenHarness Terminal Demo" width="800">
</p>

<p align="center">
  <img src="assets/architecture-comic.png" alt="How Agent Harness Works" width="800">
</p>

---

## 🚀 44x Lighter Than Claude Code

<table>
<tr><th></th><th>Claude Code</th><th>OpenHarness</th></tr>
<tr><td><strong>Lines of Code</strong></td><td>512,664</td><td><strong>11,733</strong> (44x lighter)</td></tr>
<tr><td><strong>Files</strong></td><td>1,884</td><td><strong>163</strong></td></tr>
<tr><td><strong>Language</strong></td><td>TypeScript</td><td>Python</td></tr>
<tr><td><strong>Tools</strong></td><td>~44</td><td>43 (98%)</td></tr>
<tr><td><strong>Commands</strong></td><td>~88</td><td>54 (61%)</td></tr>
<tr><td><strong>Skills Compatible</strong></td><td>✅</td><td>✅ anthropics/skills</td></tr>
<tr><td><strong>Plugin Compatible</strong></td><td>✅</td><td>✅ claude-code/plugins</td></tr>
<tr><td><strong>Tests</strong></td><td>—</td><td>114 unit + 6 E2E suites</td></tr>
</table>

**Just 2.3% of the code, 98% of the essential tools**. Leverages Python's power with pure focus on Harness architecture—stripped of enterprise overhead like telemetry, OAuth complexity, and hundreds of React components.

---

## 🤔 What is an Agent Harness?

An **Agent Harness** is the complete infrastructure that wraps around an LLM to make it a functional agent. The model provides intelligence; the harness provides **hands, eyes, memory, and safety boundaries**.

<p align="center">
  <img src="assets/harness-equation.png" alt="Harness = Tools + Knowledge + Observation + Action + Permissions" width="700">
</p>

OpenHarness is an open-source Python implementation designed for **researchers, builders, and the community**:

- **Understand** how production AI agents work under the hood
- **Experiment** with cutting-edge tools, skills, and agent coordination patterns
- **Extend** the harness with custom plugins, providers, and domain knowledge
- **Build** specialized agents on top of proven architecture

---

## 📰 What's New

- **2026-04-01** 🎨 **v0.1.0** — Initial **OpenHarness** open-source release featuring complete Harness architecture: 

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **Node.js 18+** (for the React terminal UI)
- An LLM API key

### Install & Run

```bash
# Clone and install
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev

# Example: use Kimi as the backend
export ANTHROPIC_BASE_URL=https://api.moonshot.cn/anthropic
export ANTHROPIC_API_KEY=your_kimi_api_key
export ANTHROPIC_MODEL=kimi-k2.5

# Launch
oh                    # if venv is activated
uv run oh             # without activating venv
```

<p align="center">
  <img src="assets/landing.png" alt="OpenHarness Landing Screen" width="700">
</p>

### Non-Interactive Mode (Pipes & Scripts)

```bash
# Single prompt → stdout
oh -p "Explain this codebase"

# JSON output for programmatic use
oh -p "List all functions in main.py" --output-format json

# Stream JSON events in real-time
oh -p "Fix the bug" --output-format stream-json
```

---

## 🏗️ Harness Architecture

### System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   CLI Entry (cli.py / Typer)                 │
│               oh / openharness → Interactive or Print mode   │
├──────────┬───────────────────────────────────────────────────┤
│ TUI Mode │  React/Ink Frontend ←─JSON Protocol─→ BackendHost│
│ Print    │  oh -p "..." → Headless agent loop → stdout       │
├──────────┴───────────────────────────────────────────────────┤
│              RuntimeBundle (ui/runtime.py)                    │
│   Assembles: ApiClient + ToolRegistry + Hooks + Commands     │
├──────────────────────────────────────────────────────────────┤
│                QueryEngine (engine/)                          │
│       Conversation history + Cost tracking + run_query()     │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────┬────────────┬────────┬───────┬───────┬────────┐ │
│  │ Tools   │ Permissions│ Hooks  │  MCP  │Skills │Plugins │ │
│  │ 43 tools│ 3 modes    │ Pre/   │ Proto │ .md   │ claude │ │
│  │ Pydantic│ Path rules │ Post   │ Client│ files │ compat │ │
│  └─────────┴────────────┴────────┴───────┴───────┴────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Project Structure & File Reference

```
OpenHarness/
├── pyproject.toml                  # Build config (hatchling), deps, pytest/ruff/mypy settings
├── LICENSE                         # MIT License
├── README.md                       # This file
├── CLAUDE.md                       # AI assistant project context
├── DESIGN.md                       # Architecture design document (Chinese)
│
├── src/openharness/                # ══════ Core Python Package ══════
│   ├── __init__.py                 # Package marker
│   ├── __main__.py                 # `python -m openharness` entry
│   ├── cli.py                      # CLI entry point (Typer): oh [options], sub-commands
│   │
│   ├── engine/                     # ── Agent Loop (core) ──
│   │   ├── query.py                #   run_query(): async tool-call loop (max_turns=8)
│   │   ├── query_engine.py         #   QueryEngine: conversation history + cost tracking
│   │   ├── messages.py             #   ConversationMessage, TextBlock, ToolUseBlock, ToolResultBlock
│   │   ├── stream_events.py        #   StreamEvent types: TextDelta, TurnComplete, ToolStarted/Completed
│   │   └── cost_tracker.py         #   CostTracker: cumulative token usage per session
│   │
│   ├── api/                        # ── Anthropic API Client ──
│   │   ├── client.py               #   AnthropicApiClient: streaming + exponential backoff retry (3x)
│   │   ├── errors.py               #   AuthenticationFailure, RateLimitFailure, RequestFailure
│   │   ├── provider.py             #   ProviderInfo: detect API capabilities
│   │   └── usage.py                #   UsageSnapshot: input/output token counts
│   │
│   ├── tools/                      # ── 43 Tools (all extend BaseTool) ──
│   │   ├── base.py                 #   BaseTool ABC, ToolResult, ToolExecutionContext, ToolRegistry
│   │   ├── bash_tool.py            #   Execute shell commands via subprocess
│   │   ├── file_read_tool.py       #   Read file contents with offset/limit
│   │   ├── file_write_tool.py      #   Create or overwrite files atomically
│   │   ├── file_edit_tool.py       #   Search-and-replace edits within files
│   │   ├── glob_tool.py            #   Find files matching glob patterns
│   │   ├── grep_tool.py            #   Regex search with ripgrep integration
│   │   ├── web_fetch_tool.py       #   Fetch and parse HTML/text from URLs
│   │   ├── web_search_tool.py      #   Web search via search engine API
│   │   ├── agent_tool.py           #   Spawn sub-agent with separate context
│   │   ├── send_message_tool.py    #   Send message to sub-agent or team member
│   │   ├── team_create_tool.py     #   Create multi-agent team
│   │   ├── team_delete_tool.py     #   Delete team
│   │   ├── skill_tool.py           #   Load and apply skill knowledge
│   │   ├── mcp_tool.py             #   Call MCP server tools dynamically
│   │   ├── mcp_auth_tool.py        #   MCP server authentication
│   │   ├── list_mcp_resources_tool.py  # List MCP resources
│   │   ├── read_mcp_resource_tool.py   # Read MCP resource content
│   │   ├── task_create_tool.py     #   Create background shell/agent task
│   │   ├── task_list_tool.py       #   List running tasks
│   │   ├── task_get_tool.py        #   Get task status and output
│   │   ├── task_update_tool.py     #   Update task parameters
│   │   ├── task_stop_tool.py       #   Gracefully stop a task
│   │   ├── task_output_tool.py     #   Stream task output
│   │   ├── cron_create_tool.py     #   Schedule agents on cron
│   │   ├── cron_list_tool.py       #   List cron schedules
│   │   ├── cron_delete_tool.py     #   Delete cron schedule
│   │   ├── enter_plan_mode_tool.py #   Switch to read-only plan mode
│   │   ├── exit_plan_mode_tool.py  #   Exit plan mode
│   │   ├── enter_worktree_tool.py  #   Enter git worktree for isolation
│   │   ├── exit_worktree_tool.py   #   Exit git worktree
│   │   ├── config_tool.py          #   Get/set configuration values
│   │   ├── sleep_tool.py           #   Delay execution for polling scenarios
│   │   ├── ask_user_question_tool.py   # Ask user for input (blocks until response)
│   │   ├── brief_tool.py           #   Summarize conversation context
│   │   ├── tool_search_tool.py     #   Search available tools by name/description
│   │   ├── lsp_tool.py             #   Language Server Protocol integration
│   │   ├── notebook_edit_tool.py   #   Edit Jupyter notebook cells
│   │   ├── remote_trigger_tool.py  #   Trigger remote agent execution
│   │   └── todo_write_tool.py      #   Update task/todo list
│   │
│   ├── permissions/                # ── Permission System ──
│   │   ├── modes.py                #   PermissionMode enum: DEFAULT, PLAN, FULL_AUTO
│   │   └── checker.py              #   PermissionChecker: evaluate tool calls against rules
│   │
│   ├── hooks/                      # ── Lifecycle Hooks ──
│   │   ├── executor.py             #   HookExecutor: run Command/HTTP/Prompt/Agent hooks
│   │   ├── loader.py               #   HookRegistry: load hooks from settings
│   │   ├── events.py               #   HookEvent: PRE_TOOL_USE, POST_TOOL_USE, SESSION_START
│   │   ├── schemas.py              #   HookDefinition pydantic model
│   │   ├── types.py                #   Hook type definitions
│   │   └── hot_reload.py           #   HookReloader: watch settings for hot-reload
│   │
│   ├── config/                     # ── Configuration ──
│   │   ├── settings.py             #   Settings model (Pydantic): model, perms, hooks, MCP
│   │   └── paths.py                #   Config/session/task/memory directory helpers
│   │
│   ├── mcp/                        # ── Model Context Protocol ──
│   │   ├── client.py               #   McpClientManager: connect to MCP servers via stdio
│   │   ├── config.py               #   Load MCP server configs from settings
│   │   └── types.py                #   McpStdioServerConfig, McpToolInfo, McpResourceInfo
│   │
│   ├── skills/                     # ── Skills (on-demand knowledge) ──
│   │   ├── loader.py               #   Load skills from bundled/ and ~/.openharness/skills/
│   │   ├── registry.py             #   SkillRegistry: store loaded skill definitions
│   │   ├── types.py                #   SkillDefinition model (name, description, content)
│   │   └── bundled/content/        #   Built-in skills: commit, debug, plan, review, simplify, test
│   │
│   ├── plugins/                    # ── Plugin System (claude-code compatible) ──
│   │   ├── loader.py               #   Load plugins from ~/.openharness/plugins/
│   │   ├── installer.py            #   Plugin install/uninstall helpers
│   │   ├── schemas.py              #   PluginManifest model
│   │   └── types.py                #   LoadedPlugin dataclass
│   │
│   ├── coordinator/                # ── Multi-Agent Coordination ──
│   │   ├── coordinator_mode.py     #   TeamRegistry: in-memory team/agent membership
│   │   └── agent_definitions.py    #   AgentDefinition: built-in roles (default, worker)
│   │
│   ├── commands/                   # ── 54 Interactive Slash Commands ──
│   │   └── registry.py             #   CommandRegistry: /help, /commit, /plan, /resume, /perms...
│   │
│   ├── prompts/                    # ── System Prompt Assembly ──
│   │   ├── system_prompt.py        #   Build system prompt from base + environment
│   │   ├── environment.py          #   EnvironmentInfo: OS, Python, git, cwd detection
│   │   ├── context.py              #   PromptContext: optional CLAUDE.md injection
│   │   └── claudemd.py             #   Load/parse CLAUDE.md from project root
│   │
│   ├── memory/                     # ── Persistent Cross-Session Memory ──
│   │   ├── manager.py              #   Memory file CRUD operations
│   │   ├── memdir.py               #   MemoryDirectory: persistent storage
│   │   ├── scan.py                 #   Scan markdown memory files
│   │   ├── search.py               #   Heuristic memory search (token matching)
│   │   ├── paths.py                #   Memory directory path helpers
│   │   └── types.py                #   MemoryHeader, MemoryBlock dataclasses
│   │
│   ├── tasks/                      # ── Background Tasks ──
│   │   ├── manager.py              #   BackgroundTaskManager: spawn async tasks
│   │   ├── types.py                #   TaskRecord, TaskStatus, TaskType
│   │   ├── local_shell_task.py     #   ShellTask: background shell commands
│   │   ├── local_agent_task.py     #   AgentTask: background sub-agent processes
│   │   └── stop_task.py            #   Graceful task termination
│   │
│   ├── ui/                         # ── UI Layer ──
│   │   ├── app.py                  #   run_repl(): interactive mode entry point
│   │   ├── runtime.py              #   RuntimeBundle: assemble all components for a session
│   │   ├── backend_host.py         #   JSON-lines backend server for React TUI (stdin/stdout)
│   │   ├── react_launcher.py       #   Launch React terminal UI subprocess
│   │   ├── textual_app.py          #   Fallback Textual TUI (pure Python, no Node.js)
│   │   ├── protocol.py             #   FrontendRequest/Response protocol models
│   │   ├── permission_dialog.py    #   Interactive permission confirmation dialog
│   │   ├── input.py                #   Input handling and line reading
│   │   └── output.py               #   Output formatting and streaming
│   │
│   ├── bridge/                     # ── External Session Management ──
│   │   ├── manager.py              #   BridgeSessionManager: track spawned sessions
│   │   ├── session_runner.py       #   SessionHandle: subprocess lifecycle
│   │   ├── types.py                #   Bridge communication types
│   │   └── work_secret.py          #   Secure session secret handling
│   │
│   ├── services/                   # ── Shared Services ──
│   │   ├── session_storage.py      #   Persist session history to ~/.openharness/sessions/
│   │   ├── token_estimation.py     #   Rough token count heuristic
│   │   ├── cron.py                 #   Local cron job registry for scheduled agents
│   │   ├── compact/                #   Message compaction (context window management)
│   │   ├── lsp/                    #   Language Server Protocol integration
│   │   └── oauth/                  #   OAuth flow helpers for MCP auth
│   │
│   ├── state/                      # ── Application State ──
│   │   ├── app_state.py            #   AppState: model, mode, theme, cwd, auth, vim, voice
│   │   └── store.py                #   AppStateStore: observable state with listener pattern
│   │
│   ├── keybindings/                # ── Keyboard Shortcuts ──
│   │   ├── loader.py               #   Load from ~/.claude/keybindings.json
│   │   ├── parser.py               #   Parse keybinding JSON format
│   │   ├── resolver.py             #   Resolve key combos to actions
│   │   └── default_bindings.py     #   Default keybinding presets
│   │
│   ├── output_styles/              # ── Output Customization ──
│   │   └── loader.py               #   Load custom output styles
│   │
│   ├── vim/                        # ── Vim Mode ──
│   │   └── transitions.py          #   toggle_vim_mode() state helper
│   │
│   ├── voice/                      # ── Voice Input ──
│   │   ├── voice_mode.py           #   VoiceDiagnostics, toggle_voice_mode()
│   │   ├── keyterms.py             #   Voice command keyword mapping
│   │   └── stream_stt.py           #   Speech-to-text streaming integration
│   │
│   └── types/                      # ── Shared Type Definitions ──
│       └── __init__.py
│
├── frontend/terminal/              # ══════ React + Ink TUI (TypeScript) ══════
│   ├── package.json                # Dependencies: React 18, Ink 5, TypeScript 5
│   ├── tsconfig.json               # TypeScript configuration
│   └── src/
│       ├── index.tsx               #   Entry point, renders <App/>
│       ├── App.tsx                  #   Main component: routing, modes, keyboard
│       ├── types.ts                #   TypeScript interfaces (Config, Transcript, Task...)
│       ├── hooks/
│       │   └── useBackendSession.ts    # JSON-lines backend communication hook
│       └── components/
│           ├── Composer.tsx         #   Multi-line prompt input with history
│           ├── CommandPicker.tsx    #   Slash command autocomplete picker
│           ├── ConversationView.tsx #   Render transcript (messages + tool calls)
│           ├── TranscriptPane.tsx   #   Scrollable transcript display
│           ├── ToolCallDisplay.tsx  #   Pretty-print tool invocations and results
│           ├── StatusBar.tsx        #   Top bar: model, cwd, auth status
│           ├── Footer.tsx           #   Bottom bar: keybindings
│           ├── SelectModal.tsx      #   Multi-choice selection modal
│           ├── PromptInput.tsx      #   Single-line input prompt
│           ├── SidePanel.tsx        #   Side panel: tasks, memory, sessions
│           ├── Spinner.tsx          #   Loading spinner animation
│           ├── ModalHost.tsx        #   Portal for modal dialogs
│           └── WelcomeBanner.tsx    #   Welcome/splash screen
│
├── tests/                          # ══════ Test Suite ══════
│   ├── conftest.py                 # Shared pytest fixtures
│   ├── fixtures/
│   │   └── fake_mcp_server.py      #   Mock MCP server for testing
│   ├── test_engine/                #   Agent loop, message formatting, cost tracking
│   ├── test_api/                   #   API client, retry, error translation
│   ├── test_tools/                 #   Individual tool tests (bash, file, web, mcp...)
│   ├── test_permissions/           #   Permission checker, mode evaluation
│   ├── test_hooks/                 #   Hook executor, loader, hot-reload
│   ├── test_commands/              #   Slash command registry and execution
│   ├── test_config/                #   Settings loading, path resolution
│   ├── test_mcp/                   #   MCP client connection
│   ├── test_skills/                #   Skill loader, bundled skills
│   ├── test_plugins/               #   Plugin loader, manifest validation
│   ├── test_memory/                #   Memory search, file management
│   ├── test_tasks/                 #   Background task manager
│   ├── test_coordinator/           #   Team registry
│   ├── test_prompts/               #   System prompt building
│   ├── test_services/              #   Session storage, cron, token estimation
│   ├── test_ui/                    #   Backend protocol, Textual app
│   └── test_bridge/                #   Bridge session management
│
└── scripts/                        # ══════ E2E Test Scripts ══════
    ├── e2e_smoke.py                #   Full smoke test: real API calls, multiple scenarios
    ├── test_harness_features.py    #   Feature tests: retry, skills, parallel, permissions
    ├── test_cli_flags.py           #   CLI argument parsing tests
    ├── test_real_skills_plugins.py #   Real skill/plugin loading tests
    ├── react_tui_e2e.py            #   React TUI end-to-end tests
    ├── test_react_tui_redesign.py  #   React TUI redesign validation
    ├── test_tui_interactions.py    #   Terminal UI interaction tests
    ├── test_headless_rendering.py  #   Headless mode rendering tests
    └── local_system_scenarios.py   #   Local filesystem scenario tests
```

### The Agent Loop

The heart of the harness — a **user-driven request-response loop** with an inner autonomous tool-call cycle:

```
┌─────────────────── Outer Loop (User-Driven) ───────────────────┐
│                                                                 │
│  User types prompt                                              │
│    └→ QueryEngine.submit_message(prompt)                        │
│         └→ run_query(context, messages)                         │
│                                                                 │
│  ┌──────────── Inner Loop (LLM-Driven, max 8 turns) ────────┐  │
│  │                                                            │  │
│  │  1. api_client.stream_message()                            │  │
│  │     ├→ yield TextDelta (real-time streaming)               │  │
│  │     └→ yield MessageComplete                               │  │
│  │                                                            │  │
│  │  2. If no tool_uses → break (return to user)               │  │
│  │                                                            │  │
│  │  3. Execute tools:                                         │  │
│  │     Pre-Hook → Permission Check → Pydantic Validate        │  │
│  │       → tool.execute() → Post-Hook                         │  │
│  │     (single: sequential / multiple: asyncio.gather)        │  │
│  │                                                            │  │
│  │  4. Append ToolResultBlocks → next turn                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ← Wait for next user input                                    │
└─────────────────────────────────────────────────────────────────┘
```

The model decides **what** to do. The harness handles **how** — safely, efficiently, with full observability.

---

## ✨ Features

### 🔧 Tools (43+)

| Category | Tools | Description |
|----------|-------|-------------|
| **File I/O** | Bash, Read, Write, Edit, Glob, Grep | Core file operations with permission checks |
| **Search** | WebFetch, WebSearch, ToolSearch, LSP | Web and code search capabilities |
| **Notebook** | NotebookEdit | Jupyter notebook cell editing |
| **Agent** | Agent, SendMessage, TeamCreate/Delete | Subagent spawning and coordination |
| **Task** | TaskCreate/Get/List/Update/Stop/Output | Background task management |
| **MCP** | MCPTool, ListMcpResources, ReadMcpResource | Model Context Protocol integration |
| **Mode** | EnterPlanMode, ExitPlanMode, Worktree | Workflow mode switching |
| **Schedule** | CronCreate/List/Delete, RemoteTrigger | Scheduled and remote execution |
| **Meta** | Skill, Config, Brief, Sleep, AskUser | Knowledge loading, configuration, interaction |

Every tool has:
- **Pydantic input validation** — structured, type-safe inputs
- **Self-describing JSON Schema** — models understand tools automatically
- **Permission integration** — checked before every execution
- **Hook support** — PreToolUse/PostToolUse lifecycle events

### 📚 Skills System

Skills are **on-demand knowledge** — loaded only when the model needs them:

```
Available Skills:
- commit: Create clean, well-structured git commits
- review: Review code for bugs, security issues, and quality
- debug: Diagnose and fix bugs systematically
- plan: Design an implementation plan before coding
- test: Write and run tests for code
- simplify: Refactor code to be simpler and more maintainable
- pdf: PDF processing with pypdf (from anthropics/skills)
- xlsx: Excel operations (from anthropics/skills)
- ... 40+ more
```

**Compatible with [anthropics/skills](https://github.com/anthropics/skills)** — just copy `.md` files to `~/.openharness/skills/`.

### 🔌 Plugin System

**Compatible with [claude-code plugins](https://github.com/anthropics/claude-code/tree/main/plugins)**. Tested with 12 official plugins:

| Plugin | Type | What it does |
|--------|------|-------------|
| `commit-commands` | Commands | Git commit, push, PR workflows |
| `security-guidance` | Hooks | Security warnings on file edits |
| `hookify` | Commands + Agents | Create custom behavior hooks |
| `feature-dev` | Commands | Feature development workflow |
| `code-review` | Agents | Multi-agent PR review |
| `pr-review-toolkit` | Agents | Specialized PR review agents |

```bash
# Manage plugins
oh plugin list
oh plugin install <source>
oh plugin enable <name>
```

### 🛡️ Permissions

Multi-level safety with fine-grained control:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Default** | Ask before write/execute | Daily development |
| **Auto** | Allow everything | Sandboxed environments |
| **Plan Mode** | Block all writes | Large refactors, review first |

**Path-level rules** in `settings.json`:
```json
{
  "permission": {
    "mode": "default",
    "path_rules": [{"pattern": "/etc/*", "allow": false}],
    "denied_commands": ["rm -rf /", "DROP TABLE *"]
  }
}
```

### 🖥️ Terminal UI

React/Ink TUI with full interactive experience:

- **Command picker**: Type `/` → arrow keys to select → Enter
- **Permission dialog**: Interactive y/n with tool details
- **Mode switcher**: `/permissions` → select from list
- **Session resume**: `/resume` → pick from history
- **Animated spinner**: Real-time feedback during tool execution
- **Keyboard shortcuts**: Shown at the bottom, context-aware

### 📡 CLI

```
oh [OPTIONS] COMMAND [ARGS]

Session:     -c/--continue, -r/--resume, -n/--name
Model:       -m/--model, --effort, --max-turns
Output:      -p/--print, --output-format text|json|stream-json
Permissions: --permission-mode, --dangerously-skip-permissions
Context:     -s/--system-prompt, --append-system-prompt, --settings
Advanced:    -d/--debug, --mcp-config, --bare

Subcommands: oh mcp | oh plugin | oh auth
```

---

## 📊 Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| Unit + Integration | 114 | ✅ All passing |
| CLI Flags E2E | 6 | ✅ Real model calls |
| Harness Features E2E | 9 | ✅ Retry, skills, parallel, permissions |
| React TUI E2E | 3 | ✅ Welcome, conversation, status |
| TUI Interactions E2E | 4 | ✅ Commands, permissions, shortcuts |
| Real Skills + Plugins | 12 | ✅ anthropics/skills + claude-code/plugins |

```bash
# Run all tests
uv run pytest -q                           # 114 unit/integration
python scripts/test_harness_features.py     # Harness E2E
python scripts/test_real_skills_plugins.py  # Real plugins E2E
```

---

## 🔧 Extending OpenHarness

### Add a Custom Tool

```python
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

class MyToolInput(BaseModel):
    query: str = Field(description="Search query")

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    input_model = MyToolInput

    async def execute(self, arguments: MyToolInput, context: ToolExecutionContext) -> ToolResult:
        return ToolResult(output=f"Result for: {arguments.query}")
```

### Add a Custom Skill

Create `~/.openharness/skills/my-skill.md`:

```markdown
---
name: my-skill
description: Expert guidance for my specific domain
---

# My Skill

## When to use
Use when the user asks about [your domain].

## Workflow
1. Step one
2. Step two
...
```

### Add a Plugin

Create `.openharness/plugins/my-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin"
}
```

Add commands in `commands/*.md`, hooks in `hooks/hooks.json`, agents in `agents/*.md`.

---

## 🤝 Contributing

OpenHarness is a **community-driven research project**. We welcome contributions in:

| Area | Examples |
|------|---------|
| **Tools** | New tool implementations for specific domains |
| **Skills** | Domain knowledge `.md` files (finance, science, DevOps...) |
| **Plugins** | Workflow plugins with commands, hooks, agents |
| **Providers** | Support for more LLM backends (OpenAI, Ollama, etc.) |
| **Multi-Agent** | Coordination protocols, team patterns |
| **Testing** | E2E scenarios, edge cases, benchmarks |
| **Documentation** | Architecture guides, tutorials, translations |

```bash
# Development setup
git clone https://github.com/HKUDS/OpenHarness.git
cd openharness
uv sync --extra dev
uv run pytest -q  # Verify everything works
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <img src="assets/logo.png" alt="OpenHarness" width="48">
  <br>
  <strong>Oh my Harness!</strong>
  <br>
  <em>The model is the agent. The code is the harness.</em>
</p>

<p align="center">
  <em> Thanks for visiting ✨ OpenHarness!</em><br><br>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=HKUDS.OpenHarness&style=for-the-badge&color=00d4ff" alt="Views">
</p>
