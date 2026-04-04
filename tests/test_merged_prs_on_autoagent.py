"""Real large tasks testing ALL merged PR features on AutoAgent codebase.

Every test runs on /home/tangjiabin/AutoAgent — a 17K LOC unfamiliar Python project.
Uses real Kimi K2.5 API via both Anthropic and OpenAI endpoints.

Run: python tests/test_merged_prs_on_autoagent.py
"""

from __future__ import annotations

import asyncio
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
ANTHROPIC_BASE = "https://api.moonshot.cn/anthropic"
OPENAI_BASE = "https://api.moonshot.cn/v1"
MODEL = "kimi-k2.5"
WORKSPACE = Path("/home/tangjiabin/AutoAgent")

RESULTS: dict[str, tuple[bool, float]] = {}


# ==================================================================
# Helpers
# ==================================================================

def _make_registry(extra_tools=None):
    from openharness.tools.base import ToolRegistry
    from openharness.tools.bash_tool import BashTool
    from openharness.tools.file_read_tool import FileReadTool
    from openharness.tools.file_write_tool import FileWriteTool
    from openharness.tools.file_edit_tool import FileEditTool
    from openharness.tools.glob_tool import GlobTool
    from openharness.tools.grep_tool import GrepTool

    reg = ToolRegistry()
    for t in [BashTool(), FileReadTool(), FileWriteTool(), FileEditTool(), GlobTool(), GrepTool()]:
        reg.register(t)
    for t in (extra_tools or []):
        reg.register(t)
    return reg


def _make_checker():
    from openharness.config.settings import PermissionSettings
    from openharness.permissions.checker import PermissionChecker
    from openharness.permissions.modes import PermissionMode
    return PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))


def make_anthropic_engine(system_prompt, extra_tools=None):
    from openharness.api.client import AnthropicApiClient
    from openharness.engine.query_engine import QueryEngine
    api = AnthropicApiClient(api_key=API_KEY, base_url=ANTHROPIC_BASE)
    return QueryEngine(
        api_client=api, tool_registry=_make_registry(extra_tools),
        permission_checker=_make_checker(), cwd=WORKSPACE, model=MODEL,
        system_prompt=system_prompt, max_tokens=4096,
    )


def make_openai_engine(system_prompt, extra_tools=None):
    from openharness.api.openai_client import OpenAICompatibleClient
    from openharness.engine.query_engine import QueryEngine
    api = OpenAICompatibleClient(api_key=API_KEY, base_url=OPENAI_BASE)
    return QueryEngine(
        api_client=api, tool_registry=_make_registry(extra_tools),
        permission_checker=_make_checker(), cwd=WORKSPACE, model=MODEL,
        system_prompt=system_prompt, max_tokens=4096,
    )


def collect(events):
    from openharness.engine.stream_events import (
        AssistantTextDelta, AssistantTurnComplete,
        ToolExecutionStarted, ToolExecutionCompleted,
    )
    r = {"text": "", "tools": [], "errors": [], "turns": 0, "in_tok": 0, "out_tok": 0}
    for ev in events:
        if isinstance(ev, AssistantTextDelta):
            r["text"] += ev.text
        elif isinstance(ev, ToolExecutionStarted):
            r["tools"].append(ev.tool_name)
            print(f"    [{ev.tool_name}] {str(ev.tool_input)[:70]}")
        elif isinstance(ev, ToolExecutionCompleted):
            if ev.is_error:
                r["errors"].append(ev.output[:100])
        elif isinstance(ev, AssistantTurnComplete):
            r["turns"] += 1
            r["in_tok"] += ev.usage.input_tokens
            r["out_tok"] += ev.usage.output_tokens
    return r


# ==================================================================
# Task 1: PR #17 — diagnose skill to debug AutoAgent's test runner
#
# Agent loads diagnose skill, runs AutoAgent's tests, finds failures,
# reads the failing code, identifies root cause.
# Features: skill tool, bash, read, grep, multi-turn
# ==================================================================
async def task_diagnose_autoagent():
    print("=" * 70)
    print("  Task 1: PR#17 — Use diagnose skill to investigate AutoAgent tests")
    print("=" * 70)

    from openharness.tools.skill_tool import SkillTool

    engine = make_anthropic_engine(
        "You are a debugger. Start by loading the 'diagnose' skill to get "
        "a structured debugging procedure. Then follow it to investigate "
        "the AutoAgent codebase for issues. Be concise and report findings.",
        extra_tools=[SkillTool()],
    )

    evs = [ev async for ev in engine.submit_message(
        "I think there might be issues with AutoAgent's import structure. "
        "First, load the 'diagnose' skill. Then investigate: "
        "1. Try to import the main module: python -c 'import autoagent' "
        "2. If it fails, read the traceback and find the root cause "
        "3. If it succeeds, check autoagent/core.py for any bare except clauses "
        "that could swallow errors silently."
    )]
    r = collect(evs)
    print(f"\n  Tools: {r['tools']} ({len(r['tools'])} calls)")
    print(f"  Turns: {r['turns']}, Tokens: {r['in_tok']}+{r['out_tok']}")
    print(f"  Response: {r['text'][:400]}")

    ok = (
        "skill" in r["tools"]
        and "bash" in r["tools"]
        and len(r["text"]) > 200
        and any(kw in r["text"].lower() for kw in ["import", "error", "except", "issue", "found"])
    )
    return ok


# ==================================================================
# Task 2: PR #12 — Research AutoAgent, save to memory with frontmatter,
#          search memory, use it in follow-up analysis
#
# Features: memory frontmatter, memory search, agent loop, multi-turn
# ==================================================================
async def task_memory_research_autoagent():
    print("\n" + "=" * 70)
    print("  Task 2: PR#12 — Research AutoAgent → save to memory → search → use")
    print("=" * 70)

    from openharness.memory.search import find_relevant_memories
    from openharness.memory.scan import scan_memory_files
    import openharness.memory.paths as mp
    import openharness.memory.manager as mm
    import openharness.memory.scan as ms

    with tempfile.TemporaryDirectory() as tmpdir:
        mem_dir = Path(tmpdir) / "memory"
        mem_dir.mkdir(parents=True)
        orig_mp, orig_ms = mp.get_project_memory_dir, ms.get_project_memory_dir
        orig_ep = mm.get_memory_entrypoint
        mp.get_project_memory_dir = lambda cwd: mem_dir
        ms.get_project_memory_dir = lambda cwd: mem_dir
        mm.get_memory_entrypoint = lambda cwd: mem_dir / "MEMORY.md"

        try:
            # Phase 1: Agent researches AutoAgent's architecture
            engine = make_anthropic_engine(
                "You are a researcher. Investigate codebases thoroughly. Be concise.",
            )
            print("  Phase 1: Research AutoAgent architecture...")
            evs1 = [ev async for ev in engine.submit_message(
                "Read autoagent/core.py (first 50 lines) and autoagent/types.py. "
                "Tell me: what is the main class, what pattern does the agent loop use, "
                "and what data types are defined."
            )]
            r1 = collect(evs1)
            print(f"    {r1['turns']} turns, {len(r1['tools'])} tools")

            # Phase 2: Agent researches dependencies
            print("  Phase 2: Research dependencies...")
            evs2 = [ev async for ev in engine.submit_message(
                "Read setup.cfg and tell me what the install_requires are."
            )]
            r2 = collect(evs2)
            print(f"    {r2['turns']} turns, {len(r2['tools'])} tools")

            # Save findings to memory WITH YAML frontmatter
            (mem_dir / "architecture.md").write_text(f"""---
name: autoagent-architecture
description: Core architecture of AutoAgent - MetaChain class with ReAct-style agent loop
type: project
---

{r1['text'][:600]}
""")
            (mem_dir / "dependencies.md").write_text(f"""---
name: autoagent-dependencies
description: Package dependencies from setup.cfg for AutoAgent framework
type: reference
---

{r2['text'][:600]}
""")

            # Phase 3: Verify frontmatter parsing (PR #12 fix)
            scanned = scan_memory_files(tmpdir)
            print(f"\n  Scanned memories: {len(scanned)}")
            for s in scanned:
                print(f"    {s.title}: {s.description[:60]}")
            frontmatter_ok = len(scanned) == 2 and all(s.description != "---" for s in scanned)

            # Phase 4: Search memory by body content (PR #12 improvement)
            r_arch = find_relevant_memories("What class implements the agent loop?", tmpdir)
            r_deps = find_relevant_memories("What packages does AutoAgent need?", tmpdir)
            print(f"  Search 'agent loop': {len(r_arch)} results — {r_arch[0].title if r_arch else 'none'}")
            print(f"  Search 'packages': {len(r_deps)} results — {r_deps[0].title if r_deps else 'none'}")
            search_ok = len(r_arch) > 0 and len(r_deps) > 0

            # Phase 5: New agent uses memory context to answer
            memory_ctx = "\n".join(f"- {s.title}: {s.description}" for s in scanned)
            engine2 = make_anthropic_engine(
                f"You have project memories:\n{memory_ctx}\n\nAnswer using this context.",
            )
            evs3 = [ev async for ev in engine2.submit_message(
                "Based on the project memories: what is the core class in AutoAgent, "
                "what pattern does it use, and what are 3 key dependencies?"
            )]
            r3 = collect(evs3)
            print(f"\n  Memory-informed answer: {r3['text'][:200]}")
            answer_ok = any(kw in r3["text"].lower() for kw in ["metacha", "react", "litellm"])

            ok = frontmatter_ok and search_ok and answer_ok
            return ok
        finally:
            mp.get_project_memory_dir = orig_mp
            ms.get_project_memory_dir = orig_ms
            mm.get_memory_entrypoint = orig_ep


# ==================================================================
# Task 3: PR #14 — OpenAI client does full code review of AutoAgent
#
# Multi-turn via OpenAI endpoint: glob → read → grep → read → synthesize
# Features: OpenAI client, tool calling, reasoning_content, multi-turn
# ==================================================================
async def task_openai_code_review():
    print("\n" + "=" * 70)
    print("  Task 3: PR#14 — OpenAI client full code review on AutoAgent")
    print("=" * 70)

    engine = make_openai_engine(
        "You are a senior code reviewer. Review code for bugs, security issues, "
        "and code quality. Use tools to read files. Be thorough but concise.",
    )

    # Turn 1: Find files to review
    print("  Turn 1: Find key files...")
    evs1 = [ev async for ev in engine.submit_message(
        "List the Python files in autoagent/ (top level only) using glob pattern 'autoagent/*.py'"
    )]
    r1 = collect(evs1)
    print(f"    {r1['text'][:150]}")

    # Turn 2: Review core.py for security issues
    print("  Turn 2: Security review of core.py...")
    evs2 = [ev async for ev in engine.submit_message(
        "Search autoagent/core.py for potential security issues: "
        "grep for 'eval(', 'exec(', 'subprocess', 'shell=True', 'os.system'"
    )]
    r2 = collect(evs2)
    print(f"    {r2['text'][:200]}")

    # Turn 3: Review error handling
    print("  Turn 3: Error handling review...")
    evs3 = [ev async for ev in engine.submit_message(
        "Search autoagent/ for bare 'except:' or 'except Exception' with 'pass' "
        "that could swallow errors. Use grep."
    )]
    r3 = collect(evs3)
    print(f"    {r3['text'][:200]}")

    # Turn 4: Read a specific suspicious file
    print("  Turn 4: Deep read of docker_env.py...")
    evs4 = [ev async for ev in engine.submit_message(
        "Read autoagent/environment/docker_env.py and check for any hardcoded "
        "credentials, unsafe subprocess usage, or missing error handling."
    )]
    r4 = collect(evs4)
    print(f"    {r4['text'][:200]}")

    # Turn 5: Synthesize review
    print("  Turn 5: Synthesize review report...")
    evs5 = [ev async for ev in engine.submit_message(
        "Write a 5-point code review summary based on everything you found. "
        "Include file paths and severity levels."
    )]
    r5 = collect(evs5)
    print(f"    Report: {r5['text'][:400]}")

    total_tools = sum(len(r["tools"]) for r in [r1, r2, r3, r4, r5])
    total_tokens = sum(r["in_tok"] + r["out_tok"] for r in [r1, r2, r3, r4, r5])
    print(f"\n  Total: 5 turns, {total_tools} tool calls, {total_tokens} tokens")

    ok = (
        total_tools >= 4
        and len(r5["text"]) > 200
        and any(kw in (r2["text"] + r4["text"]).lower() for kw in ["subprocess", "shell", "security", "eval"])
    )
    return ok


# ==================================================================
# Task 4: PR #16 — Multi-turn research → save session → resume → continue
#
# Agent does 3 turns of AutoAgent research, session is saved, loaded
# into a new engine, and the conversation continues with full context.
# Features: session save/load, message restore, multi-turn memory
# ==================================================================
async def task_session_resume_autoagent():
    print("\n" + "=" * 70)
    print("  Task 4: PR#16 — Research AutoAgent → save → resume → continue")
    print("=" * 70)

    from openharness.services.session_storage import (
        save_session_snapshot, load_session_snapshot,
    )
    from openharness.engine.messages import ConversationMessage

    with tempfile.TemporaryDirectory() as session_dir:
        # Phase 1: Original 3-turn research session
        engine1 = make_anthropic_engine(
            "You are a code analyst. Remember all findings across turns.",
        )

        print("  Phase 1: Original session (3 turns)...")
        evs1 = [ev async for ev in engine1.submit_message(
            "Read autoagent/registry.py and tell me what the Registry class does."
        )]
        r1 = collect(evs1)
        print(f"    Turn 1: {r1['text'][:100]}")

        evs2 = [ev async for ev in engine1.submit_message(
            "Now read autoagent/types.py and list the data classes defined there."
        )]
        r2 = collect(evs2)
        print(f"    Turn 2: {r2['text'][:100]}")

        evs3 = [ev async for ev in engine1.submit_message(
            "How does the Registry class relate to the types in types.py? "
            "Are any of the data classes registered in the registry?"
        )]
        r3 = collect(evs3)
        print(f"    Turn 3: {r3['text'][:100]}")

        # Save session with cost tracking (PR #16)
        usage_before = engine1.total_usage
        print(f"\n  Session cost: in={usage_before.input_tokens}, out={usage_before.output_tokens}")

        session_path = save_session_snapshot(
            cwd=session_dir, model=MODEL,
            system_prompt="code analyst",
            messages=engine1.messages,
            usage=usage_before,
            session_id="autoagent-research-001",
        )
        print(f"  Saved: {session_path.exists()}, {len(engine1.messages)} messages")

        # Phase 2: Resume in new engine
        loaded = load_session_snapshot(session_dir)
        assert loaded is not None
        print(f"  Loaded: {len(loaded['messages'])} messages, model={loaded['model']}")

        engine2 = make_anthropic_engine(
            "You are a code analyst. Continue the previous analysis.",
        )
        engine2.load_messages([
            ConversationMessage.model_validate(m) for m in loaded["messages"]
        ])

        # Phase 3: Continue with context — agent should remember Registry + types
        print("\n  Phase 3: Resumed conversation...")
        evs4 = [ev async for ev in engine2.submit_message(
            "Based on your earlier analysis of registry.py and types.py, "
            "what would be the most important refactoring to improve "
            "the relationship between these two modules?"
        )]
        r4 = collect(evs4)
        print(f"    Resumed: {r4['text'][:300]}")

        remembers = any(kw in r4["text"].lower() for kw in [
            "registry", "type", "agent", "tool", "register", "class",
        ])
        print(f"\n  Remembers context: {remembers}")
        return remembers and session_path.exists()


# ==================================================================
# Task 5: PR #16 — Cron scheduler manages AutoAgent maintenance jobs
#
# Create real cron jobs for AutoAgent maintenance tasks, validate
# schedules, run the full CRUD lifecycle.
# Features: cron CRUD, expression validation, next_run, toggle
# ==================================================================
async def task_cron_autoagent_maintenance():
    print("\n" + "=" * 70)
    print("  Task 5: PR#16 — Cron scheduler for AutoAgent maintenance")
    print("=" * 70)

    from openharness.services.cron import (
        load_cron_jobs, upsert_cron_job, delete_cron_job,
        get_cron_job, set_job_enabled,
        mark_job_run, next_run_time,
    )
    import openharness.services.cron as cron_mod

    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "cron_jobs.json"
        orig = cron_mod.get_cron_registry_path
        cron_mod.get_cron_registry_path = lambda: registry_path

        try:
            # Create maintenance jobs for AutoAgent
            jobs_data = [
                {"name": "lint-autoagent", "schedule": "0 */6 * * *",
                 "command": "cd /home/tangjiabin/AutoAgent && ruff check autoagent/"},
                {"name": "test-autoagent", "schedule": "0 2 * * *",
                 "command": "cd /home/tangjiabin/AutoAgent && python -m pytest tests/ -q"},
                {"name": "count-todos", "schedule": "0 9 * * 1",
                 "command": "cd /home/tangjiabin/AutoAgent && grep -r TODO autoagent/ | wc -l"},
                {"name": "disk-cleanup", "schedule": "0 3 * * 0",
                 "command": "find /tmp -name '*.pyc' -mtime +7 -delete"},
            ]
            for job in jobs_data:
                upsert_cron_job(job)

            jobs = load_cron_jobs()
            print(f"  Created {len(jobs)} maintenance jobs:")
            for j in jobs:
                nrt = next_run_time(j["schedule"])
                print(f"    {j['name']}: {j['schedule']} → next: {str(nrt)[:19]}")

            # Disable disk-cleanup (weekend only, not critical)
            set_job_enabled("disk-cleanup", False)
            dc = get_cron_job("disk-cleanup")
            print(f"\n  disk-cleanup disabled: {dc.get('enabled') is False}")

            # Simulate running lint job
            mark_job_run("lint-autoagent", success=True)
            lint = get_cron_job("lint-autoagent")
            print(f"  lint-autoagent after run: last_status={lint.get('last_status')}")

            # Simulate test failure
            mark_job_run("test-autoagent", success=False)
            test_job = get_cron_job("test-autoagent")
            print(f"  test-autoagent after fail: last_status={test_job.get('last_status')}")

            # Now use agent to actually run the lint command
            engine = make_anthropic_engine("Execute commands. Report results concisely.")
            print("\n  Running lint-autoagent command via agent...")
            evs = [ev async for ev in engine.submit_message(
                f"Run this command and report the result: {jobs_data[0]['command']}"
            )]
            r = collect(evs)
            print(f"    Agent result: {r['text'][:200]}")

            # Delete one job
            delete_cron_job("count-todos")
            remaining = load_cron_jobs()
            print(f"\n  After deleting count-todos: {len(remaining)} jobs remain")

            ok = (
                len(jobs) == 4
                and dc.get("enabled") is False
                and lint.get("last_status") == "success"
                and test_job.get("last_status") == "failure"
                and len(remaining) == 3
                and len(r["tools"]) >= 1
            )
            return ok
        finally:
            cron_mod.get_cron_registry_path = orig


# ==================================================================
# Task 6: ALL PRs combined — Full development workflow on AutoAgent
#
# Complete workflow: OpenAI research → save to memory → diagnose with
# skill → schedule cron job → save session → resume and synthesize
#
# Features: ALL PRs working together in one coherent workflow
# ==================================================================
async def task_full_dev_workflow():
    print("\n" + "=" * 70)
    print("  Task 6: ALL PRs — Full development workflow on AutoAgent")
    print("=" * 70)

    from openharness.tools.skill_tool import SkillTool
    from openharness.memory.scan import scan_memory_files
    from openharness.memory.search import find_relevant_memories
    from openharness.services.session_storage import save_session_snapshot, load_session_snapshot
    from openharness.services.cron import upsert_cron_job, load_cron_jobs, validate_cron_expression
    from openharness.engine.messages import ConversationMessage
    import openharness.memory.paths as mp
    import openharness.memory.manager as mm
    import openharness.memory.scan as ms
    import openharness.services.cron as cron_mod

    with tempfile.TemporaryDirectory() as tmpdir:
        mem_dir = Path(tmpdir) / "memory"
        mem_dir.mkdir(parents=True)
        orig_mp, orig_ms = mp.get_project_memory_dir, ms.get_project_memory_dir
        orig_ep = mm.get_memory_entrypoint
        mp.get_project_memory_dir = lambda cwd: mem_dir
        ms.get_project_memory_dir = lambda cwd: mem_dir
        mm.get_memory_entrypoint = lambda cwd: mem_dir / "MEMORY.md"
        cron_path = Path(tmpdir) / "cron.json"
        orig_cron = cron_mod.get_cron_registry_path
        cron_mod.get_cron_registry_path = lambda: cron_path

        try:
            # Step 1: OpenAI client researches AutoAgent (PR #14)
            print("  Step 1: [PR#14] OpenAI client researches AutoAgent...")
            engine1 = make_openai_engine(
                "You are a researcher. Use tools. Be concise.",
                extra_tools=[SkillTool()],
            )
            evs1 = [ev async for ev in engine1.submit_message(
                "Read autoagent/core.py (first 30 lines) and autoagent/registry.py (first 30 lines). "
                "Tell me the main classes and their purpose."
            )]
            r1 = collect(evs1)
            print(f"    Tools: {r1['tools']}, text: {r1['text'][:150]}")

            # Step 2: Save research to memory with frontmatter (PR #12)
            print("  Step 2: [PR#12] Save findings to memory...")
            (mem_dir / "autoagent_analysis.md").write_text(f"""---
name: autoagent-core
description: MetaChain class in core.py is the main agent engine with ReAct loop
type: project
---

{r1['text'][:500]}
""")
            scanned = scan_memory_files(tmpdir)
            search_results = find_relevant_memories("main agent class", tmpdir)
            print(f"    Memories: {len(scanned)}, search: {len(search_results)} hits")

            # Step 3: Use diagnose skill on AutoAgent (PR #17)
            print("  Step 3: [PR#17] Load diagnose skill and investigate...")
            evs3 = [ev async for ev in engine1.submit_message(
                "Load the 'diagnose' skill. Then check if autoagent/ has any "
                "circular import issues by running: python -c 'import autoagent.core'"
            )]
            r3 = collect(evs3)
            print(f"    Tools: {r3['tools']}, text: {r3['text'][:150]}")

            # Step 4: Track costs (PR #16)
            print("  Step 4: [PR#16] Cost tracking...")
            usage = engine1.total_usage
            print(f"    Total cost: in={usage.input_tokens}, out={usage.output_tokens}")

            # Step 5: Save session (PR #16)
            print("  Step 5: [PR#16] Save session...")
            sp = save_session_snapshot(
                cwd=tmpdir, model=MODEL, system_prompt="researcher",
                messages=engine1.messages, usage=usage,
                session_id="full-workflow-001",
            )
            print(f"    Saved: {sp.exists()}, {len(engine1.messages)} messages")

            # Step 6: Create cron job for ongoing monitoring (PR #16)
            print("  Step 6: [PR#16] Create maintenance cron job...")
            assert validate_cron_expression("0 */4 * * *")
            upsert_cron_job({
                "name": "autoagent-lint",
                "schedule": "0 */4 * * *",
                "command": "cd /home/tangjiabin/AutoAgent && ruff check autoagent/",
            })
            cron_jobs = load_cron_jobs()
            print(f"    Cron jobs: {[j['name'] for j in cron_jobs]}")

            # Step 7: Resume session in Anthropic client and continue (PR #16 + #14)
            print("  Step 7: [PR#16] Resume session with Anthropic client...")
            loaded = load_session_snapshot(tmpdir)
            engine2 = make_anthropic_engine(
                "You are a researcher continuing a previous analysis. Be concise.",
            )
            engine2.load_messages([
                ConversationMessage.model_validate(m) for m in loaded["messages"]
            ])

            evs7 = [ev async for ev in engine2.submit_message(
                "Based on your earlier research, what is the single most important "
                "improvement you would recommend for AutoAgent's codebase?"
            )]
            r7 = collect(evs7)
            print(f"    Continued: {r7['text'][:250]}")

            # Verify all features worked
            ok = (
                len(r1["tools"]) >= 1       # PR#14: OpenAI tools worked
                and len(scanned) >= 1       # PR#12: memory saved + scanned
                and len(search_results) > 0 # PR#12: search works
                and "skill" in r3["tools"]  # PR#17: skill loaded
                and sp.exists()             # PR#16: session saved
                and len(cron_jobs) >= 1     # PR#16: cron created
                and len(r7["text"]) > 50    # PR#16: resume worked
            )
            print(f"\n  All features: OpenAI={len(r1['tools'])>=1}, "
                  f"memory={len(scanned)>=1}, skill={'skill' in r3['tools']}, "
                  f"session={sp.exists()}, cron={len(cron_jobs)>=1}, "
                  f"resume={len(r7['text'])>50}")
            return ok
        finally:
            mp.get_project_memory_dir = orig_mp
            ms.get_project_memory_dir = orig_ms
            mm.get_memory_entrypoint = orig_ep
            cron_mod.get_cron_registry_path = orig_cron


# ==================================================================
# Main
# ==================================================================
async def main():
    tests = [
        ("1. PR#17: diagnose skill on AutoAgent", task_diagnose_autoagent()),
        ("2. PR#12: memory research on AutoAgent", task_memory_research_autoagent()),
        ("3. PR#14: OpenAI client code review on AutoAgent", task_openai_code_review()),
        ("4. PR#16: session save+resume on AutoAgent", task_session_resume_autoagent()),
        ("5. PR#16: cron scheduler for AutoAgent maintenance", task_cron_autoagent_maintenance()),
        ("6. ALL PRs: full dev workflow on AutoAgent", task_full_dev_workflow()),
    ]

    for name, coro in tests:
        t0 = time.time()
        try:
            ok = await coro
            elapsed = time.time() - t0
            RESULTS[name] = (ok, elapsed)
            print(f"\n  >>> {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s)")
        except Exception as e:
            RESULTS[name] = (False, time.time() - t0)
            print(f"\n  >>> EXCEPTION ({time.time()-t0:.1f}s): {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*70}")
    print("  FINAL — Merged PR Features on AutoAgent (Real Large Tasks)")
    print(f"{'='*70}")
    passed = sum(1 for ok, _ in RESULTS.values() if ok)
    for name, (ok, elapsed) in RESULTS.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  [{elapsed:.1f}s]")
    print(f"\n  {passed}/{len(RESULTS)} passed")


if __name__ == "__main__":
    asyncio.run(main())
