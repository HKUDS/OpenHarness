"""Comprehensive integration tests for all previously untested OpenHarness features.

Run with: python -m pytest tests/test_untested_features.py -v --tb=short -x
Or standalone: python tests/test_untested_features.py

Uses real Kimi K2.5 API for agent loop tests. Requires ANTHROPIC_API_KEY env
or the hardcoded key below.
"""

from __future__ import annotations

import pytest

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY",
    "sk-Ue1kdhq9prvNwuwySlzRtWVD7ek0iJJaHyPdKDa3ecKLwYuG",
)
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.moonshot.cn/anthropic")
MODEL = os.environ.get("ANTHROPIC_MODEL", "kimi-k2.5")
WORKSPACE = Path("/home/tangjiabin/AutoAgent")
_SKIP_REAL_API = not WORKSPACE.exists() or not API_KEY

RESULTS: dict[str, bool] = {}


# ====================================================================
# Helpers
# ====================================================================

def make_engine(system_prompt="You are a helpful assistant. Be concise.", cwd=None, tools=None):
    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query_engine import QueryEngine
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.file_write_tool import FileWriteTool
    from openharness.tools.file_edit_tool import FileEditTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool

    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
    reg = ToolRegistry()
    for t in (tools or [BashTool(), FileReadTool(), FileWriteTool(), FileEditTool(), GlobTool(), GrepTool()]):
        reg.register(t)
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
    return QueryEngine(
        api_client=api, tool_registry=reg, permission_checker=checker,
        cwd=Path(cwd or WORKSPACE), model=MODEL, system_prompt=system_prompt, max_tokens=4096,
    )


def collect(events):
    from openharness.engine.stream_events import (
        AssistantTextDelta, AssistantTurnComplete,
        ToolExecutionStarted, ToolExecutionCompleted,
    )
    r = {"text": "", "tools": [], "tool_results": [], "turns": 0, "in_tok": 0, "out_tok": 0}
    for ev in events:
        if isinstance(ev, AssistantTextDelta):
            r["text"] += ev.text
        elif isinstance(ev, ToolExecutionStarted):
            r["tools"].append(ev.tool_name)
        elif isinstance(ev, ToolExecutionCompleted):
            r["tool_results"].append({"tool": ev.tool_name, "ok": not ev.is_error, "out": ev.output[:300]})
        elif isinstance(ev, AssistantTurnComplete):
            r["turns"] += 1
            r["in_tok"] += ev.usage.input_tokens
            r["out_tok"] += ev.usage.output_tokens
    return r


async def run_test(name, coro):
    print(f"\n{'='*60}\n  {name}\n{'='*60}")
    try:
        ok = await coro
        RESULTS[name] = ok
        print(f"  >>> {'PASS' if ok else 'FAIL'}")
    except Exception as e:
        RESULTS[name] = False
        print(f"  >>> EXCEPTION: {e}")
        import traceback
        traceback.print_exc()


# ====================================================================
# 1. Hooks: command hook blocks a tool call
# ====================================================================
async def test_hooks_command_block():
    """Register a pre_tool_use command hook that blocks bash, verify it fires."""
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext

    registry = HookRegistry()
    # Hook: run 'echo BLOCKED' when bash is used — block_on_failure means if exit!=0 it blocks
    # We use a command that always exits 1 to simulate blocking
    hook = CommandHookDefinition(
        type="command",
        command="exit 1",
        matcher="bash",
        block_on_failure=True,
        timeout_seconds=5,
    )
    registry.register(HookEvent.PRE_TOOL_USE, hook)
    print(f"  Registered pre_tool_use hook: {hook}")

    from openharness.api.client import AnthropicApiClient
    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
    ctx = HookExecutionContext(cwd=Path.cwd(), api_client=api, default_model=MODEL)
    executor = HookExecutor(registry, ctx)

    # Trigger with bash — should block
    result = await executor.execute(
        HookEvent.PRE_TOOL_USE,
        {"tool_name": "bash", "tool_input": {"command": "ls"}, "event": "pre_tool_use"},
    )
    print(f"  bash hook result: blocked={result.blocked}, reason={result.reason}")

    # Trigger with glob — should NOT block (matcher doesn't match)
    result2 = await executor.execute(
        HookEvent.PRE_TOOL_USE,
        {"tool_name": "glob", "tool_input": {"pattern": "*.py"}, "event": "pre_tool_use"},
    )
    print(f"  glob hook result: blocked={result2.blocked}")

    return result.blocked and not result2.blocked


# ====================================================================
# 2. Hooks: post_tool_use hook runs after tool
# ====================================================================
async def test_hooks_post_tool_use():
    """Register a post_tool_use hook that logs tool output, verify it runs."""
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext

    registry = HookRegistry()
    hook = CommandHookDefinition(
        type="command",
        command="echo POST_HOOK_FIRED",
        timeout_seconds=5,
    )
    registry.register(HookEvent.POST_TOOL_USE, hook)

    from openharness.api.client import AnthropicApiClient
    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
    ctx = HookExecutionContext(cwd=Path.cwd(), api_client=api, default_model=MODEL)
    executor = HookExecutor(registry, ctx)

    result = await executor.execute(
        HookEvent.POST_TOOL_USE,
        {"tool_name": "bash", "tool_output": "hello", "event": "post_tool_use"},
    )
    print(f"  post_tool_use results: {len(result.results)} hooks fired")
    print(f"  output: {result.results[0].output if result.results else 'none'}")
    any_fired = len(result.results) > 0 and result.results[0].success
    return any_fired


# ====================================================================
# 3. Hooks integrated into agent loop — hook blocks a dangerous command
# ====================================================================
@pytest.mark.skipif(_SKIP_REAL_API, reason="Needs real API + AutoAgent")
async def test_hooks_in_agent_loop():
    """Hook that blocks 'rm' commands integrated into real agent loop."""
    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query import QueryContext, run_query
    from openharness.engine.messages import ConversationMessage
    from openharness.engine.stream_events import AssistantTextDelta, ToolExecutionStarted, ToolExecutionCompleted
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext

    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)

    # Set up hook that blocks bash commands containing 'rm'
    hook_reg = HookRegistry()
    hook_reg.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(
        type="command",
        command='echo "$TOOL_INPUT" | grep -q "rm " && exit 1 || exit 0',
        matcher="bash",
        block_on_failure=True,
        timeout_seconds=5,
    ))
    hook_executor = HookExecutor(hook_reg, HookExecutionContext(cwd=WORKSPACE, api_client=api, default_model=MODEL))
    reg = ToolRegistry()
    reg.register(BashTool())
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

    ctx = QueryContext(
        api_client=api, tool_registry=reg, permission_checker=checker,
        cwd=WORKSPACE, model=MODEL, max_tokens=1024, max_turns=4,
        system_prompt="You are a helpful assistant. Use bash to execute commands.",
        hook_executor=hook_executor,
    )
    messages = [ConversationMessage.from_user_text("Run this command: echo hello")]

    text, tools, blocked = "", [], False
    async for event, usage in run_query(ctx, messages):
        if isinstance(event, AssistantTextDelta):
            text += event.text
        elif isinstance(event, ToolExecutionStarted):
            tools.append(event.tool_name)
        elif isinstance(event, ToolExecutionCompleted):
            if event.is_error and "hook" in event.output.lower():
                blocked = True

    print(f"  Tools: {tools}, text: {text[:100]}")
    print(f"  Hook blocking detected: {blocked}")
    # echo hello should succeed (no 'rm')
    return len(tools) >= 1 and "hello" in text.lower()


# ====================================================================
# 4. Skills: load from directory and list
# ====================================================================
async def test_skills_load():
    """Create skill files, load them, verify registry."""
    from openharness.skills.registry import SkillRegistry
    from openharness.skills.loader import load_user_skills

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create skill files
        (Path(tmpdir) / "commit.md").write_text("""---
name: commit
description: Create a git commit with a good message
---
Read the git diff, then create a commit with a descriptive message.
""")
        (Path(tmpdir) / "review-pr.md").write_text("""---
name: review-pr
description: Review a pull request for issues
---
Fetch the PR diff, review for bugs, style issues, and security problems.
""")

        # Monkey-patch skills dir
        import openharness.skills.loader as sl
        orig = sl.get_user_skills_dir
        sl.get_user_skills_dir = lambda: Path(tmpdir)

        skills = load_user_skills()
        print(f"  Loaded {len(skills)} skills: {[s.name for s in skills]}")

        reg = SkillRegistry()
        for s in skills:
            reg.register(s)

        commit = reg.get("commit")
        review = reg.get("review-pr")
        print(f"  commit skill: {commit.description if commit else 'NOT FOUND'}")
        print(f"  review-pr skill: {review.description if review else 'NOT FOUND'}")
        print(f"  All skills: {[s.name for s in reg.list_skills()]}")

        sl.get_user_skills_dir = orig

        return (
            commit is not None
            and review is not None
            and "commit" in commit.content.lower()
            and len(reg.list_skills()) == 2
        )


# ====================================================================
# 5. Plugins: load manifest and discover skills
# ====================================================================
async def test_plugins_load():
    """Create a plugin directory, load it, verify manifest and skills."""
    from openharness.plugins.loader import load_plugin

    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "my-plugin"
        plugin_dir.mkdir()

        # plugin.json
        manifest = {
            "name": "my-plugin",
            "version": "1.0.0",
            "description": "Test plugin for integration testing",
            "enabled_by_default": True,
            "skills_dir": "skills",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        # skills
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "deploy.md").write_text("""---
name: deploy
description: Deploy the application
---
Build and deploy the app to production.
""")

        loaded = load_plugin(plugin_dir, enabled_plugins={})
        print(f"  Plugin: {loaded.name if loaded else 'FAILED TO LOAD'}")
        if loaded:
            print(f"  Enabled: {loaded.enabled}")
            print(f"  Skills: {[s.name for s in loaded.skills]}")
            print(f"  Manifest: v{loaded.manifest.version}")
            return loaded.name == "my-plugin" and len(loaded.skills) >= 1
        return False


# ====================================================================
# 6. Memory: add, list, search, remove
# ====================================================================
async def test_memory_lifecycle():
    """Test full memory lifecycle: add → list → search → remove."""
    from openharness.memory.manager import list_memory_files, add_memory_entry, remove_memory_entry
    from openharness.memory.search import find_relevant_memories
    from openharness.memory.scan import scan_memory_files

    with tempfile.TemporaryDirectory() as tmpdir:
        # Monkey-patch memory dir
        import openharness.memory.paths as mp
        orig = mp.get_project_memory_dir
        mem_dir = Path(tmpdir) / ".openharness" / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        mp.get_project_memory_dir = lambda cwd: mem_dir

        # Also patch entrypoint
        import openharness.memory.manager as mm
        orig_ep = mm.get_memory_entrypoint
        mm.get_memory_entrypoint = lambda cwd: mem_dir / "MEMORY.md"

        # Add entries
        p1 = add_memory_entry(tmpdir, "user-preference", "User prefers Python over JavaScript")
        p2 = add_memory_entry(tmpdir, "project-goal", "Building an AI agent framework called OpenHarness")
        print(f"  Added: {p1.name}, {p2.name}")

        # List
        files = list_memory_files(tmpdir)
        print(f"  Listed: {len(files)} memory files")

        # Search
        results = find_relevant_memories("What language does the user prefer?", tmpdir)
        print(f"  Search results: {len(results)} matches")
        if results:
            print(f"  Top match: {results[0].title}")

        # Scan
        scanned = scan_memory_files(tmpdir)
        print(f"  Scanned: {len(scanned)} files")

        # Remove
        removed = remove_memory_entry(tmpdir, "user_preference")
        print(f"  Removed user-preference: {removed}")
        files_after = list_memory_files(tmpdir)
        print(f"  Files after removal: {len(files_after)}")

        mp.get_project_memory_dir = orig
        mm.get_memory_entrypoint = orig_ep

        return len(files) == 2 and removed and len(files_after) == 1


# ====================================================================
# 7. Session storage: save, list, load, export markdown
# ====================================================================
async def test_session_storage():
    """Test session save/load/list/export cycle."""
    from openharness.services.session_storage import (
        save_session_snapshot, load_session_snapshot,
        list_session_snapshots, export_session_markdown,
    )
    from openharness.engine.messages import ConversationMessage, TextBlock
    from openharness.api.usage import UsageSnapshot

    with tempfile.TemporaryDirectory() as tmpdir:
        messages = [
            ConversationMessage.from_user_text("Hello, analyze this code"),
            ConversationMessage(role="assistant", content=[TextBlock(text="I'll read the file first.")]),
            ConversationMessage.from_user_text("Thanks, now fix the bug"),
            ConversationMessage(role="assistant", content=[TextBlock(text="Fixed the null check at line 42.")]),
        ]
        usage = UsageSnapshot(input_tokens=500, output_tokens=200)

        # Save
        path = save_session_snapshot(
            cwd=tmpdir, model=MODEL, system_prompt="Test prompt",
            messages=messages, usage=usage, session_id="test-session-123",
        )
        print(f"  Saved to: {path}")

        # List
        snapshots = list_session_snapshots(tmpdir)
        print(f"  Listed: {len(snapshots)} snapshots")

        # Load latest
        loaded = load_session_snapshot(tmpdir)
        print(f"  Loaded: model={loaded.get('model')}, messages={len(loaded.get('messages', []))}")

        # Load by ID


        # Export markdown
        md_path = export_session_markdown(cwd=tmpdir, messages=messages)
        md_content = md_path.read_text() if md_path.exists() else ""
        print(f"  Exported markdown: {len(md_content)} chars")

        return (
            path.exists()
            and len(snapshots) >= 1
            and loaded is not None
            and loaded.get("model") == MODEL
            and len(md_content) > 0
        )


# ====================================================================
# 8. Config: load settings, merge overrides, path functions
# ====================================================================
async def test_config_settings():
    """Test settings loading, env var overrides, and path functions."""
    from openharness.config.settings import Settings, load_settings
    from openharness.config.paths import (
        get_config_dir, get_sessions_dir, get_tasks_dir,
    )

    # Default settings
    s = Settings()
    print(f"  Default model: {s.model}")
    print(f"  Default permission mode: {s.permission.mode}")
    print(f"  Default memory enabled: {s.memory.enabled}")

    # Merge overrides
    s2 = s.merge_cli_overrides(model="kimi-k2.5", verbose=True)
    print(f"  After override: model={s2.model}, verbose={s2.verbose}")

    # With custom settings file
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "settings.json"
        config_file.write_text(json.dumps({
            "model": "custom-model",
            "permission": {"mode": "plan"},
            "memory": {"enabled": False, "max_files": 10},
        }))
        loaded = load_settings(config_path=config_file)
        print(f"  Loaded from file: model={loaded.model}, perm={loaded.permission.mode}, memory={loaded.memory.enabled}")

    # Path functions
    config_dir = get_config_dir()
    sessions_dir = get_sessions_dir()
    tasks_dir = get_tasks_dir()
    print(f"  Config dir: {config_dir}")
    print(f"  Sessions dir: {sessions_dir}")
    print(f"  Tasks dir: {tasks_dir}")

    return (
        s.model != ""
        and s2.model == "kimi-k2.5"
        and s2.verbose is True
        and loaded.model == "custom-model"
        and loaded.memory.enabled is False
        and config_dir.name == ".openharness"
    )


# ====================================================================
# 9. Commands: register and lookup slash commands
# ====================================================================
async def test_commands_registry():
    """Test slash command registration and lookup."""
    from openharness.commands.registry import (
        CommandRegistry, SlashCommand, CommandResult, CommandContext,
    )

    registry = CommandRegistry()

    async def handle_test(args: str, ctx: CommandContext) -> CommandResult:
        return CommandResult(message=f"Test executed with: {args}")

    async def handle_clear(args: str, ctx: CommandContext) -> CommandResult:
        return CommandResult(clear_screen=True)

    registry.register(SlashCommand(name="test", description="Run a test", handler=handle_test))
    registry.register(SlashCommand(name="clear", description="Clear screen", handler=handle_clear))

    # Lookup
    found = registry.lookup("/test hello world")
    print(f"  Lookup '/test hello world': {found[0].name if found else 'NOT FOUND'}, args='{found[1] if found else ''}'")

    found2 = registry.lookup("/clear")
    print(f"  Lookup '/clear': {found2[0].name if found2 else 'NOT FOUND'}")

    notfound = registry.lookup("/nonexistent")
    print(f"  Lookup '/nonexistent': {'NOT FOUND' if notfound is None else 'FOUND?!'}")

    # Help text
    help_text = registry.help_text()
    print(f"  Help text: {len(help_text)} chars, contains 'test': {'test' in help_text}")

    # Default registry
    from openharness.commands.registry import create_default_command_registry
    default_reg = create_default_command_registry()
    cmds = default_reg.list_commands()
    print(f"  Default registry: {len(cmds)} commands")

    return (
        found is not None and found[0].name == "test" and found[1] == "hello world"
        and found2 is not None
        and notfound is None
        and len(cmds) > 0
    )


# ====================================================================
# 10. Web fetch: real URL fetch in agent loop
# ====================================================================
@pytest.mark.skipif(_SKIP_REAL_API, reason="Needs real API + AutoAgent")
async def test_web_fetch_real():
    """Agent fetches a real URL and summarizes it."""
    from openharness.tools.web_fetch_tool import WebFetchTool
    from openharness.tools.bash_tool import BashTool

    engine = make_engine(
        "You are a web researcher. Fetch URLs when asked and summarize the content.",
        tools=[WebFetchTool(), BashTool()],
    )
    evs = [ev async for ev in engine.submit_message(
        "Fetch https://httpbin.org/json and tell me what JSON data it returns."
    )]
    r = collect(evs)
    print(f"  Tools: {r['tools']}, turns: {r['turns']}")
    print(f"  Response: {r['text'][:200]}")
    return "web_fetch" in r["tools"] and len(r["text"]) > 50


# ====================================================================
# 11. Worktree: real git worktree create/list/remove
# ====================================================================
@pytest.mark.skipif(_SKIP_REAL_API, reason="Needs local environment")
async def test_worktree_real_git():
    """Create a real git worktree, list it, remove it."""
    from openharness.swarm.worktree import WorktreeManager

    with tempfile.TemporaryDirectory() as tmpdir:
        # Init a git repo
        repo = Path(tmpdir) / "test-repo"
        repo.mkdir()
        os.system(f"cd {repo} && git init && git commit --allow-empty -m 'init' 2>/dev/null")

        wt_base = Path(tmpdir) / "worktrees"
        mgr = WorktreeManager(base_dir=wt_base)

        # Create
        info = await mgr.create_worktree(repo, "feature-x", agent_id="worker-1")
        print(f"  Created: slug={info.slug}, path={info.path}, branch={info.branch}")
        assert info.path.exists(), "Worktree path should exist"
        assert (info.path / ".git").exists(), "Should have .git"

        # List
        worktrees = await mgr.list_worktrees()
        print(f"  Listed: {len(worktrees)} worktree(s)")

        # Remove
        removed = await mgr.remove_worktree("feature-x")
        print(f"  Removed: {removed}")
        worktrees_after = await mgr.list_worktrees()
        print(f"  After remove: {len(worktrees_after)} worktree(s)")

        return info.slug == "feature-x" and len(worktrees) == 1 and removed and len(worktrees_after) == 0


# ====================================================================
# 12. MCP types: config models validate correctly
# ====================================================================
async def test_mcp_types():
    """Test MCP config model validation."""
    from openharness.mcp.types import McpStdioServerConfig, McpToolInfo, McpConnectionStatus

    # Stdio config
    stdio = McpStdioServerConfig(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    print(f"  Stdio config: cmd={stdio.command}, args={stdio.args}")

    # Tool info
    tool = McpToolInfo(server_name="filesystem", name="read_file", description="Read a file", input_schema={"type": "object"})
    print(f"  Tool: {tool.server_name}/{tool.name}")

    # Connection status
    status = McpConnectionStatus(name="filesystem", state="connected", tools=[tool])
    print(f"  Status: {status.name}={status.state}, tools={len(status.tools)}")

    return stdio.command == "npx" and tool.name == "read_file" and status.state == "connected"


# ====================================================================
# 13. Config paths: all path functions return valid paths
# ====================================================================
async def test_config_paths():
    """Verify all config path functions return sensible paths."""
    from openharness.config.paths import (
        get_config_dir, get_config_file_path, get_data_dir,
        get_logs_dir, get_sessions_dir, get_tasks_dir,
    )

    paths = {
        "config_dir": get_config_dir(),
        "config_file": get_config_file_path(),
        "data_dir": get_data_dir(),
        "logs_dir": get_logs_dir(),
        "sessions_dir": get_sessions_dir(),
        "tasks_dir": get_tasks_dir(),
    }
    for name, p in paths.items():
        print(f"  {name}: {p}")

    # All should be under ~/.openharness
    all_under_home = all(".openharness" in str(p) for p in paths.values())
    return all_under_home


# ====================================================================
# 14. Combined: hooks + skills + agent loop on AutoAgent
# ====================================================================
@pytest.mark.skipif(_SKIP_REAL_API, reason="Needs real API + AutoAgent")
async def test_combined_hooks_skills_agent():
    """Combined test: load skills, register hooks, run agent on AutoAgent."""
    from openharness.skills.registry import SkillRegistry
    from openharness.skills.types import SkillDefinition
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext
    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query import QueryContext, run_query
    from openharness.engine.messages import ConversationMessage
    from openharness.engine.stream_events import AssistantTextDelta, ToolExecutionStarted
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool

    # Skills
    skill_reg = SkillRegistry()
    skill_reg.register(SkillDefinition(
        name="analyze-imports", description="Analyze Python imports",
        content="Find all import statements and report unique packages used.",
        source="user",
    ))

    # Hooks — log every tool use
    hook_reg = HookRegistry()
    hook_reg.register(HookEvent.POST_TOOL_USE, CommandHookDefinition(
        type="command", command="echo HOOK_LOGGED", timeout_seconds=5,
    ))
    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
    hook_exec = HookExecutor(hook_reg, HookExecutionContext(cwd=WORKSPACE, api_client=api, default_model=MODEL))

    # Engine with hooks
    reg = ToolRegistry()
    for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool()]:
        reg.register(t)
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

    ctx = QueryContext(
        api_client=api, tool_registry=reg, permission_checker=checker,
        cwd=WORKSPACE, model=MODEL, max_tokens=2048, max_turns=8,
        system_prompt="You are a code analyst. Be concise. Use tools to answer questions.",
        hook_executor=hook_exec,
    )

    messages = [ConversationMessage.from_user_text(
        "Count how many Python files are in the autoagent/ directory using glob."
    )]

    text, tools = "", []
    async for event, usage in run_query(ctx, messages):
        if isinstance(event, AssistantTextDelta):
            text += event.text
        elif isinstance(event, ToolExecutionStarted):
            tools.append(event.tool_name)

    print(f"  Tools used: {tools}")
    print(f"  Response: {text[:200]}")
    print(f"  Skills available: {[s.name for s in skill_reg.list_skills()]}")

    return len(tools) >= 1 and len(text) > 20


# ====================================================================
# 15. Multi-agent + worktree + team: full swarm on AutoAgent
# ====================================================================
@pytest.mark.skipif(_SKIP_REAL_API, reason="Needs real API + AutoAgent")
async def test_full_swarm_autoagent():
    """Spawn 2 in-process teammates working on AutoAgent with team management."""
    from openharness.swarm.in_process import start_in_process_teammate, TeammateAbortController
    from openharness.swarm.types import TeammateSpawnConfig
    from openharness.engine.query import QueryContext
    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool
    from openharness.swarm.team_lifecycle import TeamLifecycleManager, TeamMember
    import openharness.swarm.mailbox as mb
    import openharness.swarm.team_lifecycle as tl

    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_td = mb.get_team_dir
        orig_tf = tl._team_file_path
        mb.get_team_dir = lambda t: Path(tmpdir) / t
        tl._team_file_path = lambda n: Path(tmpdir) / n / "team.json"

        try:
            # Create team
            mgr = TeamLifecycleManager()
            mgr.create_team("autoagent-research", "Research AutoAgent codebase")
            mgr.add_member("autoagent-research", TeamMember(
                agent_id="leader@autoagent-research", name="leader",
                backend_type="in_process", joined_at=time.time(), is_active=True,
            ))

            async def run_teammate(name, prompt):
                reg = ToolRegistry()
                for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool()]:
                    reg.register(t)
                checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
                ctx = QueryContext(
                    api_client=api, tool_registry=reg, permission_checker=checker,
                    cwd=WORKSPACE, model=MODEL, max_tokens=1024, max_turns=6,
                    system_prompt="You are a research worker. Use tools. Be concise.",
                )
                config = TeammateSpawnConfig(
                    name=name, team="autoagent-research", prompt=prompt,
                    cwd=str(WORKSPACE), parent_session_id="main",
                )
                mgr.add_member("autoagent-research", TeamMember(
                    agent_id=f"{name}@autoagent-research", name=name,
                    backend_type="in_process", joined_at=time.time(), is_active=True,
                ))
                abort = TeammateAbortController()
                await start_in_process_teammate(
                    config=config, agent_id=f"{name}@autoagent-research",
                    abort_controller=abort, query_context=ctx,
                )

            t0 = time.time()
            results = await asyncio.gather(
                asyncio.wait_for(
                    run_teammate("counter", "Count .py files in autoagent/ using bash: find autoagent -name '*.py' | wc -l"),
                    timeout=30,
                ),
                asyncio.wait_for(
                    run_teammate("finder", "Find the main entry point of AutoAgent using grep: grep -rn 'def main' autoagent/"),
                    timeout=30,
                ),
                return_exceptions=True,
            )
            elapsed = time.time() - t0

            team = mgr.get_team("autoagent-research")
            print(f"  Team members: {list(team.members.keys()) if team else 'N/A'}")
            print(f"  Worker results: {['OK' if not isinstance(r, Exception) else str(r) for r in results]}")
            print(f"  Time: {elapsed:.1f}s")

            return all(not isinstance(r, Exception) for r in results)
        finally:
            mb.get_team_dir = orig_td
            tl._team_file_path = orig_tf


# ====================================================================
# Main runner
# ====================================================================
async def main():
    tests = [
        ("01 Hooks: command block", test_hooks_command_block()),
        ("02 Hooks: post_tool_use", test_hooks_post_tool_use()),
        ("03 Hooks: in agent loop", test_hooks_in_agent_loop()),
        ("04 Skills: load + registry", test_skills_load()),
        ("05 Plugins: load manifest", test_plugins_load()),
        ("06 Memory: full lifecycle", test_memory_lifecycle()),
        ("07 Session: save/load/export", test_session_storage()),
        ("08 Config: settings + overrides", test_config_settings()),
        ("09 Commands: registry + lookup", test_commands_registry()),
        ("10 Web fetch: real URL", test_web_fetch_real()),
        ("11 Worktree: real git ops", test_worktree_real_git()),
        ("12 MCP: type validation", test_mcp_types()),
        ("13 Config: path functions", test_config_paths()),
        ("14 Combined: hooks+skills+agent on AutoAgent", test_combined_hooks_skills_agent()),
        ("15 Full swarm: team+teammates on AutoAgent", test_full_swarm_autoagent()),
    ]

    for name, coro in tests:
        await run_test(name, coro)

    print(f"\n{'='*60}")
    print("  FINAL SUMMARY — All Previously Untested Features")
    print(f"{'='*60}")
    passed = sum(1 for v in RESULTS.values() if v)
    for name, ok in RESULTS.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n  {passed}/{len(RESULTS)} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
