# Test Patterns — Code Templates for Harness Eval

## Engine Setup Helpers

```python
import asyncio, sys, os
from pathlib import Path
sys.path.insert(0, "src")

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "your-key")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.moonshot.cn/anthropic")
OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
MODEL = os.environ.get("ANTHROPIC_MODEL", "kimi-k2.5")
WORKSPACE = Path("/tmp/eval-workspace")  # unfamiliar project


def make_anthropic_engine(system_prompt, cwd=None, extra_tools=None):
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
    for t in [BashTool(), FileReadTool(), FileWriteTool(), FileEditTool(), GlobTool(), GrepTool()]:
        reg.register(t)
    for t in (extra_tools or []):
        reg.register(t)
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
    return QueryEngine(
        api_client=api, tool_registry=reg, permission_checker=checker,
        cwd=Path(cwd or WORKSPACE), model=MODEL, system_prompt=system_prompt, max_tokens=4096,
    )


def make_openai_engine(system_prompt, cwd=None, extra_tools=None):
    from openharness.api.openai_client import OpenAICompatibleClient
    # Same structure as above, but with:
    api = OpenAICompatibleClient(api_key=API_KEY, base_url=OPENAI_BASE)
    # ... rest identical


def collect(events):
    from openharness.engine.stream_events import (
        AssistantTextDelta, AssistantTurnComplete,
        ToolExecutionStarted, ToolExecutionCompleted,
    )
    r = {"text": "", "tools": [], "turns": 0, "in_tok": 0, "out_tok": 0}
    for ev in events:
        if isinstance(ev, AssistantTextDelta):
            r["text"] += ev.text
        elif isinstance(ev, ToolExecutionStarted):
            r["tools"].append(ev.tool_name)
        elif isinstance(ev, AssistantTurnComplete):
            r["turns"] += 1
            r["in_tok"] += ev.usage.input_tokens
            r["out_tok"] += ev.usage.output_tokens
    return r
```

## Multi-Turn Memory Test

```python
async def test_multi_turn_memory():
    engine = make_anthropic_engine("Remember what the user tells you.")
    [ev async for ev in engine.submit_message("My favorite number is 42.")]
    [ev async for ev in engine.submit_message("What is 2+2?")]
    evs = [ev async for ev in engine.submit_message("What is my favorite number?")]
    r = collect(evs)
    assert "42" in r["text"]
```

## Hook Blocks Tool → Model Adapts

```python
async def test_hook_blocks():
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext

    hook_reg = HookRegistry()
    hook_reg.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(
        type="command", command="exit 1",
        matcher="bash", block_on_failure=True, timeout_seconds=5,
    ))
    # ... create engine with hook_executor, model tries bash, gets blocked, adapts to glob
```

## Skill Tool Invocation

```python
async def test_skill_invocation():
    from openharness.tools.skill_tool import SkillTool
    engine = make_anthropic_engine(
        "Use the 'skill' tool to load instructions before working.",
        extra_tools=[SkillTool()],
    )
    evs = [ev async for ev in engine.submit_message(
        "Load the 'diagnose' skill, then investigate the codebase."
    )]
    r = collect(evs)
    assert "skill" in r["tools"]
```

## InProcess Concurrent Teammates

```python
async def test_concurrent_teammates():
    from openharness.swarm.in_process import start_in_process_teammate, TeammateAbortController
    from openharness.swarm.types import TeammateSpawnConfig
    from openharness.engine.query import QueryContext

    async def run_one(name, prompt):
        ctx = QueryContext(api_client=api, tool_registry=reg, ...)
        config = TeammateSpawnConfig(name=name, team="test", prompt=prompt, ...)
        abort = TeammateAbortController()
        await start_in_process_teammate(config=config, agent_id=f"{name}@test", abort_controller=abort, query_context=ctx)

    await asyncio.gather(
        asyncio.wait_for(run_one("worker-a", "Count .py files"), timeout=30),
        asyncio.wait_for(run_one("worker-b", "Find main class"), timeout=30),
    )
```

## Session Save → Resume

```python
async def test_session_resume():
    from openharness.services.session_storage import save_session_snapshot, load_session_snapshot
    from openharness.engine.messages import ConversationMessage

    engine1 = make_anthropic_engine("Remember context.")
    [ev async for ev in engine1.submit_message("Project uses FastAPI + React.")]
    save_session_snapshot(cwd=tmpdir, model=MODEL, system_prompt="...", messages=engine1.messages, usage=engine1.total_usage)

    loaded = load_session_snapshot(tmpdir)
    engine2 = make_anthropic_engine("Continue analysis.")
    engine2.load_messages([ConversationMessage.model_validate(m) for m in loaded["messages"]])
    evs = [ev async for ev in engine2.submit_message("What tech stack did I mention?")]
    assert "fastapi" in collect(evs)["text"].lower()
```
