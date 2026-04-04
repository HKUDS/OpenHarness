"""Real large tasks where hooks/skills/plugins are ACTIVELY used by the model.

Not passive logging — the model encounters hook blocks, invokes the skill tool,
and uses plugin-provided skills through the agent loop.

Run: python tests/test_hooks_skills_plugins_real.py
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

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-Ue1kdhq9prvNwuwySlzRtWVD7ek0iJJaHyPdKDa3ecKLwYuG")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.moonshot.cn/anthropic")
MODEL = os.environ.get("ANTHROPIC_MODEL", "kimi-k2.5")
WORKSPACE = Path("/home/tangjiabin/AutoAgent")

RESULTS: dict[str, tuple[bool, float]] = {}


def collect(events):
    from openharness.engine.stream_events import (
        AssistantTextDelta, AssistantTurnComplete,
        ToolExecutionStarted, ToolExecutionCompleted,
    )
    r = {"text": "", "tools": [], "tool_errors": [], "turns": 0}
    for ev in events:
        if isinstance(ev, AssistantTextDelta):
            r["text"] += ev.text
        elif isinstance(ev, ToolExecutionStarted):
            r["tools"].append(ev.tool_name)
        elif isinstance(ev, ToolExecutionCompleted):
            if ev.is_error:
                r["tool_errors"].append({"tool": ev.tool_name, "err": ev.output[:200]})
        elif isinstance(ev, AssistantTurnComplete):
            r["turns"] += 1
    return r


# ====================================================================
# Task 1: Hook BLOCKS a tool → model adapts and uses alternative
#
# The model tries to use bash, hook blocks it, model sees the error
# and switches to glob/grep instead. This tests that hooks actually
# change model behavior in the loop.
# ====================================================================
@pytest.mark.skipif(not Path("/home/tangjiabin/AutoAgent").exists(), reason="Needs real API + AutoAgent")
async def task_hook_blocks_model_adapts():
    print("=" * 70)
    print("  Task 1: Hook blocks bash → model must adapt to glob/grep")
    print("=" * 70)

    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query_engine import QueryEngine
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext

    api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)

    # Hook: BLOCK all bash usage
    hook_reg = HookRegistry()
    hook_reg.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(
        type="command",
        command="exit 1",  # Always fails → blocks
        matcher="bash",
        block_on_failure=True,
        timeout_seconds=5,
    ))
    hook_exec = HookExecutor(hook_reg, HookExecutionContext(
        cwd=WORKSPACE, api_client=api, default_model=MODEL,
    ))

    reg = ToolRegistry()
    for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool()]:
        reg.register(t)
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

    engine = QueryEngine(
        api_client=api, tool_registry=reg, permission_checker=checker,
        cwd=WORKSPACE, model=MODEL, max_tokens=2048,
        system_prompt=(
            "You are a code explorer. You have bash, read_file, glob, and grep tools. "
            "If a tool fails or is blocked, try a different tool to accomplish the same goal. "
            "Do NOT retry a blocked tool."
        ),
        hook_executor=hook_exec,
    )

    events = []
    async for ev in engine.submit_message(
        "Count how many Python files are in the autoagent/ directory. "
        "Try using bash first. If it's blocked, use glob instead."
    ):
        events.append(ev)

    r = collect(events)
    print(f"  Tools attempted: {r['tools']}")
    print(f"  Tool errors (blocked): {len(r['tool_errors'])}")
    if r["tool_errors"]:
        print(f"    Blocked: {r['tool_errors'][0]}")
    print(f"  Response: {r['text'][:300]}")

    bash_blocked = any(e["tool"] == "bash" for e in r["tool_errors"])
    used_alternative = "glob" in r["tools"] or "grep" in r["tools"]
    has_answer = any(c.isdigit() for c in r["text"])  # found a count

    print(f"\n  bash blocked: {bash_blocked}, used alternative: {used_alternative}, got answer: {has_answer}")
    ok = bash_blocked and used_alternative and has_answer
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


# ====================================================================
# Task 2: Model INVOKES the skill tool to get instructions
#
# Skill tool is registered, model is told to use it, and the skill
# content drives what the model does next. This tests the full
# skill tool → load → return content → model acts on it loop.
# ====================================================================
@pytest.mark.skipif(not Path("/home/tangjiabin/AutoAgent").exists(), reason="Needs real API + AutoAgent")
async def task_model_invokes_skill_tool():
    print("\n" + "=" * 70)
    print("  Task 2: Model invokes skill tool, then follows skill instructions")
    print("=" * 70)

    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query_engine import QueryEngine
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool
    from openharness.tools.skill_tool import SkillTool
    import openharness.skills.loader as sl

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a skill file that gives specific instructions
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        (skills_dir / "code-review.md").write_text("""---
name: code-review
description: Step-by-step code review checklist
---
# Code Review Checklist

When performing a code review, follow these exact steps:

1. First, use grep to search for `TODO` and `FIXME` comments in the codebase
2. Then, count the total number of TODO/FIXME items found
3. Report the findings in this format:
   - Total TODOs: <count>
   - Total FIXMEs: <count>
   - Files affected: <list>
""")

        # Monkey-patch skills dir so SkillTool can find our skill
        orig_dir = sl.get_user_skills_dir
        sl.get_user_skills_dir = lambda: skills_dir

        api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
        reg = ToolRegistry()
        for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool(), SkillTool()]:
            reg.register(t)
        checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

        engine = QueryEngine(
            api_client=api, tool_registry=reg, permission_checker=checker,
            cwd=WORKSPACE, model=MODEL, max_tokens=2048,
            system_prompt=(
                "You are a code reviewer. You have a 'skill' tool that provides review checklists. "
                "ALWAYS start by invoking the skill tool with the relevant skill name to get instructions, "
                "then follow those instructions exactly. Available skill: 'code-review'."
            ),
        )

        events = []
        async for ev in engine.submit_message(
            "Review the autoagent/ codebase. First, invoke the 'code-review' skill to get your checklist, "
            "then follow its instructions step by step."
        ):
            events.append(ev)

        r = collect(events)
        sl.get_user_skills_dir = orig_dir

        print(f"  Tools used: {r['tools']}")
        print(f"  Turns: {r['turns']}")
        print(f"  Response: {r['text'][:400]}")

        skill_invoked = "skill" in r["tools"]
        followed_instructions = "grep" in r["tools"]  # skill says to grep for TODO/FIXME
        has_report = any(kw in r["text"].lower() for kw in ["todo", "fixme"])

        print(f"\n  skill tool invoked: {skill_invoked}")
        print(f"  followed instructions (used grep): {followed_instructions}")
        print(f"  report has TODO/FIXME: {has_report}")
        ok = skill_invoked and followed_instructions and has_report
        print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        return ok


# ====================================================================
# Task 3: Plugin-provided skill used in agent loop
#
# A plugin is loaded with a custom skill. The model uses the skill
# tool to access the plugin's skill content, then acts on it.
# ====================================================================
@pytest.mark.skipif(not Path("/home/tangjiabin/AutoAgent").exists(), reason="Needs real API + AutoAgent")
async def task_plugin_skill_in_agent_loop():
    print("\n" + "=" * 70)
    print("  Task 3: Plugin-provided skill used through skill tool in agent loop")
    print("=" * 70)

    from openharness.api.client import AnthropicApiClient
    from openharness.config.settings import PermissionSettings
    from openharness.engine.query_engine import QueryEngine
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool
    from openharness.tools.skill_tool import SkillTool
    import openharness.skills.loader as sl

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a plugin with a skill
        plugin_dir = Path(tmpdir) / "plugins" / "security-scanner"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "security-scanner",
            "version": "1.0.0",
            "description": "Security scanning plugin",
            "skills_dir": "skills",
        }))
        plugin_skills = plugin_dir / "skills"
        plugin_skills.mkdir()
        (plugin_skills / "scan-secrets.md").write_text("""---
name: scan-secrets
description: Scan for hardcoded secrets and credentials
---
# Secret Scanning Procedure

To scan for hardcoded secrets:

1. Use grep to search for these patterns:
   - `password` or `passwd` (case insensitive)
   - `secret` or `api_key` or `token` in assignment context
   - Any string that looks like `sk-` or `ghp_` (API key prefixes)
2. For each match, report: file path, line number, and the suspicious pattern
3. Classify severity: HIGH (actual key/password), MEDIUM (variable name), LOW (comment/doc)
""")

        # Load plugin and make its skills available
        from openharness.plugins.loader import load_plugin
        plugin = load_plugin(plugin_dir, enabled_plugins={})
        print(f"  Plugin loaded: {plugin.name}, skills: {[s.name for s in plugin.skills]}")

        # Monkey-patch skills loading to include plugin skill
        orig_dir = sl.get_user_skills_dir
        sl.get_user_skills_dir = lambda: plugin_skills  # Plugin skills as user skills

        api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)
        reg = ToolRegistry()
        for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool(), SkillTool()]:
            reg.register(t)
        checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

        engine = QueryEngine(
            api_client=api, tool_registry=reg, permission_checker=checker,
            cwd=WORKSPACE, model=MODEL, max_tokens=2048,
            system_prompt=(
                "You are a security analyst. You have a 'skill' tool that provides scanning procedures. "
                "Start by loading the 'scan-secrets' skill, then follow its procedure to scan the autoagent/ codebase. "
                "Report ALL findings."
            ),
        )

        events = []
        async for ev in engine.submit_message(
            "Scan the autoagent/ codebase for hardcoded secrets. "
            "Use the 'scan-secrets' skill first to get the scanning procedure, then execute it."
        ):
            events.append(ev)

        r = collect(events)
        sl.get_user_skills_dir = orig_dir

        print(f"  Tools used: {r['tools']}")
        print(f"  Turns: {r['turns']}")
        print(f"  Response: {r['text'][:400]}")

        skill_invoked = "skill" in r["tools"]
        did_grep = "grep" in r["tools"]
        has_findings = any(kw in r["text"].lower() for kw in ["password", "secret", "token", "api_key", "key"])

        print(f"\n  skill invoked: {skill_invoked}, did grep: {did_grep}, has findings: {has_findings}")
        ok = skill_invoked and did_grep and has_findings
        print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        return ok


# ====================================================================
# Task 4: Hook modifies tool behavior + skill drives multi-step workflow
#
# Combined: pre_tool_use hook logs + gates file writes (blocks write to
# certain paths), skill provides a refactoring checklist, model follows
# it, encounters hook block on protected path, adapts.
# ====================================================================
@pytest.mark.skipif(not Path("/home/tangjiabin/AutoAgent").exists(), reason="Needs real API + AutoAgent")
async def task_hook_gates_writes_skill_guides():
    print("\n" + "=" * 70)
    print("  Task 4: Hook gates file writes + skill guides refactoring workflow")
    print("=" * 70)

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
    from openharness.tools.skill_tool import SkillTool
    from openharness.hooks.events import HookEvent
    from openharness.hooks.loader import HookRegistry
    from openharness.hooks.schemas import CommandHookDefinition
    from openharness.hooks.executor import HookExecutor, HookExecutionContext
    import openharness.skills.loader as sl

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create skill
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        (skills_dir / "refactor-guide.md").write_text("""---
name: refactor-guide
description: Guide for safe refactoring
---
# Safe Refactoring Steps

1. Read the target file completely
2. Identify the function to refactor
3. Write the refactored version to a NEW file (e.g., refactored_<original>.py)
4. Run python -c "import ast; ast.parse(open('<new_file>').read())" to verify syntax
5. Report what changed and why
""")

        # Create a file to refactor
        work_dir = Path(tmpdir) / "work"
        work_dir.mkdir()
        (work_dir / "utils.py").write_text('''def process(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result

def process_v2(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
''')
        # Protected file that hook will block writes to
        (work_dir / "config.py").write_text('SECRET = "do-not-touch"\n')

        orig_dir = sl.get_user_skills_dir
        sl.get_user_skills_dir = lambda: skills_dir

        api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)

        # Hook: block writes to config.py
        hook_reg = HookRegistry()
        hook_reg.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(
            type="command",
            command='echo "$TOOL_INPUT" | grep -q "config.py" && exit 1 || exit 0',
            matcher="write_file",
            block_on_failure=True,
            timeout_seconds=5,
        ))
        hook_reg.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(
            type="command",
            command='echo "$TOOL_INPUT" | grep -q "config.py" && exit 1 || exit 0',
            matcher="edit_file",
            block_on_failure=True,
            timeout_seconds=5,
        ))
        hook_exec = HookExecutor(hook_reg, HookExecutionContext(
            cwd=work_dir, api_client=api, default_model=MODEL,
        ))

        reg = ToolRegistry()
        for t in [BashTool(), FileReadTool(), FileWriteTool(), FileEditTool(),
                  GlobTool(), GrepTool(), SkillTool()]:
            reg.register(t)
        checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))

        engine = QueryEngine(
            api_client=api, tool_registry=reg, permission_checker=checker,
            cwd=work_dir, model=MODEL, max_tokens=2048,
            system_prompt=(
                "You are a developer. Use the 'skill' tool to load refactoring instructions. "
                "Follow them precisely. If a write is blocked by a hook, skip that file and explain why."
            ),
            hook_executor=hook_exec,
        )

        events = []
        async for ev in engine.submit_message(
            "First load the 'refactor-guide' skill. Then refactor utils.py — "
            "the two functions are identical, merge them into one. "
            "Follow the skill's steps. Write the result to refactored_utils.py. "
            "Then verify the syntax."
        ):
            events.append(ev)

        r = collect(events)
        sl.get_user_skills_dir = orig_dir

        print(f"  Tools used: {r['tools']}")
        print(f"  Tool errors: {len(r['tool_errors'])}")
        print(f"  Response: {r['text'][:300]}")

        skill_invoked = "skill" in r["tools"]
        did_read = "read_file" in r["tools"]
        did_write = "write_file" in r["tools"]

        # Check refactored file exists
        refactored = work_dir / "refactored_utils.py"
        file_created = refactored.exists()
        if file_created:
            content = refactored.read_text()
            print(f"  Refactored file: {len(content)} chars")
            # Should have merged the two identical functions
            print(f"  Functions found: {content.count('def process')}")
        else:
            print("  Refactored file: NOT CREATED")

        # Config should be untouched
        config_safe = (work_dir / "config.py").read_text() == 'SECRET = "do-not-touch"\n'

        print(f"\n  skill: {skill_invoked}, read: {did_read}, write: {did_write}")
        print(f"  file created: {file_created}, config safe: {config_safe}")
        ok = skill_invoked and did_read and file_created and config_safe
        print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        return ok


# ====================================================================
# Task 5: Swarm teammates each use skills for different tasks
#
# 2 in-process teammates, each loads a different skill and follows it.
# Tests: skill tool in teammate context + concurrent skill access.
# ====================================================================
@pytest.mark.skipif(not Path("/home/tangjiabin/AutoAgent").exists(), reason="Needs real API + AutoAgent")
async def task_swarm_teammates_use_skills():
    print("\n" + "=" * 70)
    print("  Task 5: 2 concurrent teammates each invoke different skills")
    print("=" * 70)

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
    from openharness.tools.skill_tool import SkillTool
    from openharness.tools.file_write_tool import FileWriteTool
    import openharness.skills.loader as sl

    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        (skills_dir / "count-classes.md").write_text("""---
name: count-classes
description: Count classes in Python files
---
Use grep to search for 'class ' definitions. Count them. Write result to /tmp/class_count.txt.
""")
        (skills_dir / "find-imports.md").write_text("""---
name: find-imports
description: Find all import statements
---
Use grep to search for '^import ' and '^from .* import'. Count unique packages. Write result to /tmp/import_count.txt.
""")

        orig_dir = sl.get_user_skills_dir
        sl.get_user_skills_dir = lambda: skills_dir

        api = AnthropicApiClient(api_key=API_KEY, base_url=BASE_URL)

        async def run_teammate(name, prompt):
            reg = ToolRegistry()
            for t in [BashTool(), FileReadTool(), GlobTool(), GrepTool(), SkillTool(), FileWriteTool()]:
                reg.register(t)
            ctx = QueryContext(
                api_client=api, tool_registry=reg,
                permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
                cwd=WORKSPACE, model=MODEL, max_tokens=1024, max_turns=20,
                system_prompt="You are a worker. First invoke the skill tool to get instructions, then follow them.",
            )
            config = TeammateSpawnConfig(
                name=name, team="skill-team", prompt=prompt,
                cwd=str(WORKSPACE), parent_session_id="main",
            )
            abort = TeammateAbortController()
            await start_in_process_teammate(
                config=config, agent_id=f"{name}@skill-team",
                abort_controller=abort, query_context=ctx,
            )

        # Clean up any previous results
        for f in ["/tmp/class_count.txt", "/tmp/import_count.txt"]:
            Path(f).unlink(missing_ok=True)

        t0 = time.time()
        results = await asyncio.gather(
            asyncio.wait_for(run_teammate(
                "class-counter",
                "Load the 'count-classes' skill, then follow its instructions on the autoagent/ codebase."
            ), timeout=120),
            asyncio.wait_for(run_teammate(
                "import-finder",
                "Load the 'find-imports' skill, then follow its instructions on the autoagent/ codebase."
            ), timeout=120),
            return_exceptions=True,
        )
        elapsed = time.time() - t0
        sl.get_user_skills_dir = orig_dir

        worker_ok = all(not isinstance(r, Exception) for r in results)
        print(f"  Workers: {['OK' if not isinstance(r, Exception) else str(r)[:50] for r in results]}")
        print(f"  Time: {elapsed:.1f}s")

        # Check output files
        class_file = Path("/tmp/class_count.txt")
        import_file = Path("/tmp/import_count.txt")
        class_ok = class_file.exists() and len(class_file.read_text().strip()) > 0
        import_ok = import_file.exists() and len(import_file.read_text().strip()) > 0

        if class_ok:
            print(f"  class_count.txt: {class_file.read_text().strip()[:100]}")
        else:
            print(f"  class_count.txt: {'EXISTS but empty' if class_file.exists() else 'MISSING'}")
        if import_ok:
            print(f"  import_count.txt: {import_file.read_text().strip()[:100]}")
        else:
            print(f"  import_count.txt: {'EXISTS but empty' if import_file.exists() else 'MISSING'}")

        ok = worker_ok and (class_ok or import_ok)  # At least one output file
        print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        return ok


# ====================================================================
# Main
# ====================================================================
async def main():
    tasks = [
        ("1. Hook blocks bash → model adapts", task_hook_blocks_model_adapts()),
        ("2. Model invokes skill tool → follows instructions", task_model_invokes_skill_tool()),
        ("3. Plugin skill → scan-secrets in agent loop", task_plugin_skill_in_agent_loop()),
        ("4. Hook gates writes + skill guides refactoring", task_hook_gates_writes_skill_guides()),
        ("5. Swarm teammates each use different skills", task_swarm_teammates_use_skills()),
    ]

    for name, coro in tasks:
        t0 = time.time()
        try:
            ok = await coro
            RESULTS[name] = (ok, time.time() - t0)
        except Exception as e:
            RESULTS[name] = (False, time.time() - t0)
            print(f"\n  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*70}")
    print("  FINAL RESULTS — Hooks/Skills/Plugins in Real Agent Loops")
    print(f"{'='*70}")
    passed = sum(1 for ok, _ in RESULTS.values() if ok)
    for name, (ok, elapsed) in RESULTS.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  [{elapsed:.1f}s]")
    print(f"\n  {passed}/{len(RESULTS)} tasks passed")


if __name__ == "__main__":
    asyncio.run(main())
