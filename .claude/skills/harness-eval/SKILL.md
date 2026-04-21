---
name: harness-eval
description: This skill should be used when the user asks to "test the harness", "run integration tests", "validate features with real API", "test with real model calls", "run agent loop tests", "verify end-to-end", or needs to verify OpenHarness features on a real codebase with actual LLM calls.
version: 0.2.0
---

# Harness Eval — End-to-End Feature Validation

Validate OpenHarness features by running real agent loops against an unfamiliar codebase with actual LLM API calls. Every test exercises the full stack: API client → model → tool calls → execution → result.

## Core Principles

1. **Test on an unfamiliar project** — never test on OpenHarness itself (the agent modifies its own code). Clone a real project as the workspace.
2. **Use real API calls** — no mocks. Configure a real LLM endpoint.
3. **Multi-turn conversations** — always test 2+ turns where the model needs prior context.
4. **Combine features** — test hooks+skills+agent loop together, not in isolation.
5. **Verify tool execution** — inspect tool call lists and output files, not just model text.

## Workflow

### 1. Prepare Workspace

Clone an unfamiliar project (do not use OpenHarness):

```bash
git clone https://github.com/HKUDS/AutoAgent /tmp/eval-workspace
```

### 2. Configure Environment

```bash
export ANTHROPIC_API_KEY=sk-xxx
export ANTHROPIC_BASE_URL=https://api.moonshot.cn/anthropic  # or any provider
export ANTHROPIC_MODEL=kimi-k2.5
```

For long-running real evals, do not artificially lower `max_turns`. Use the product default (`200`) unless the user explicitly wants a tighter bound.

### 3. Prepare Real Sandbox Runtime When Relevant

If the task is validating sandbox behavior, install and verify the actual runtime before running agent loops:

```bash
npm install -g @anthropic-ai/sandbox-runtime
sudo apt-get update
sudo apt-get install -y bubblewrap ripgrep
which srt
which bwrap
which rg
srt --version
```

Then run a minimal smoke check through OpenHarness, not just raw `srt`, so you verify the real adapter path:

```python
from pathlib import Path
from openharness.config.settings import Settings, SandboxSettings, save_settings
from openharness.tools.bash_tool import BashTool

cfg = Path("/tmp/openharness-sandbox-settings.json")
save_settings(Settings(sandbox=SandboxSettings(enabled=True, fail_if_unavailable=True)), cfg)
# Point config loader at this file, then run BashTool on a tiny command such as `pwd`.
```

If sandbox dependencies are missing, treat that as an environment/setup failure, not a feature regression.

### 4. Design Tests

Each test follows this pattern:

```python
engine = make_engine(system_prompt="...", cwd=UNFAMILIAR_PROJECT)
evs1 = [ev async for ev in engine.submit_message("Read X, analyze Y")]
r1 = collect(evs1)  # text, tools, turns, tokens
evs2 = [ev async for ev in engine.submit_message("Based on what you found...")]
r2 = collect(evs2)
assert "grep" in r1["tools"]  # verify tools ran
```

For detailed code templates and the `make_engine`/`collect` helpers, consult `references/test-patterns.md`.

### 5. Prefer Long-Horizon, Real Agent Loops

For meaningful end-to-end validation, prefer unfamiliar-repo tasks that force multiple turns, context reuse, and mixed tool usage.

Recommended pattern:

- Use a real external workspace such as `AutoAgent`
- Use real provider credentials and the actual target model
- Keep `max_turns=200`
- Use per-prompt timeouts large enough for real exploration, such as `240-600s`
- Require at least 2 turns per scenario
- Verify both text quality and tool traces
- Keep polling long-running sessions until they finish; do not abandon a run after the first long pause

Recommended long-horizon scenarios:

- `architecture_multiturn`
  - Turn 1: map architecture, shell/subprocess surfaces, and test entrypoints
  - Turn 2: identify top risks and propose refactors
  - Turn 3: condense into onboarding or remediation actions
  - Success: `bash`, `glob`, `grep`, `read_file` all appear; no timeout; no `MaxTurnsExceeded`

- `hook_block_and_recover`
  - Force the model to try `bash`
  - Block it with a real pre-tool hook
  - Verify the model adapts with `glob`/`grep`/`read_file`

- `sandbox_multiturn`
  - Enable real sandbox settings with `fail_if_unavailable=true`
  - First prompt must start with exactly one shell command such as `pwd && ls -la`
  - Second prompt must explicitly reuse the prior shell findings
  - Success: `bash` executes via sandbox, non-shell tools continue the task, and the agent recovers from incidental repo errors

When a scenario fails, classify it before changing code:

- `MaxTurnsExceeded`: likely eval harness misconfiguration if `max_turns` was manually lowered
- `timeout`: task is too broad or per-prompt timeout is too small
- sandbox unavailable: environment missing `srt`, `bwrap`, or `rg`
- tool error with task still completed: feature may still be healthy; inspect recovery behavior

### 6. Run Tests

```bash
python tests/test_merged_prs_on_autoagent.py   # PR feature tests
python tests/test_real_large_tasks.py           # large multi-step tasks
python tests/test_hooks_skills_plugins_real.py  # hooks/skills/plugins
python -m pytest tests/ -q -k "not autoagent"  # unit tests (no API)
```

For ad hoc long-horizon validation, it is acceptable to run a temporary Python driver script as long as it:

- uses real OpenHarness engine/tool objects
- targets an unfamiliar repository
- prints per-scenario JSON summaries
- records tools, errors, turns, and token usage
- stays attached until completion

### 7. Interpret Results

| Result | Meaning | Action |
|--------|---------|--------|
| PASS with tool calls | Feature works end-to-end | Done |
| PASS without tool calls | Model answered from knowledge | Rewrite prompt to force tool use |
| FAIL with exception | Code bug | Read traceback |
| FAIL with wrong output | Model behavior issue | Check system prompt and tool schemas |
| Timeout | Task too complex | Increase `max_turns` or simplify prompt |

For long-running real evals, refine the timeout guidance:

- First check whether `max_turns` was manually set too low
- If `max_turns=200` and the run still fails, the next suspect is wall-clock timeout, not turn count
- Distinguish environment failures from product failures
  - Example: missing dependency in the unfamiliar target repo is not automatically an OpenHarness regression
  - Example: missing `srt`/`bwrap`/`rg` is an eval environment issue

## Feature Coverage Checklist

- [ ] Engine: multi-turn memory, tool chaining, parallel tools, error recovery, auto-compaction
- [ ] Swarm: InProcessBackend lifecycle, concurrent teammates, coordinator+notifications
- [ ] Hooks: pre_tool_use blocking → model adapts, post_tool_use firing
- [ ] Skills: skill tool invocation → model follows instructions
- [ ] Plugins: plugin-provided skill loaded and used in agent loop
- [ ] Memory: YAML frontmatter parsing, body content search, context injection
- [ ] Session: save → load → resume with context preserved
- [ ] Providers: Anthropic client, OpenAI client (with reasoning_content), multi-turn
- [ ] Cost: token accumulation across turns

## Common Pitfalls

- Testing on OpenHarness itself — agent modifies its own running code
- Using mocks — misses serialization and API compatibility bugs
- Single-turn only — misses context accumulation and compaction bugs
- Artificially lowering `max_turns` during real evals — can create false failures that do not reflect product defaults
- Not checking tool call list — model may claim tool use without calling it
- Hardcoding paths — use `WORKSPACE` variable, skip in CI with `pytest.mark.skipif`
- Declaring sandbox “tested” after only checking raw `srt` — verify the OpenHarness adapter path too
- Abandoning long tasks too early — some real tasks pause for minutes before the next event arrives

## Additional Resources

### Reference Files

- **`references/test-patterns.md`** — Complete code templates for `make_engine`, `collect`, and each feature category
- **`references/feature-matrix.md`** — Detailed test cases for every OpenHarness module

### Existing Test Files

Working test suites in the repo:
- `tests/test_merged_prs_on_autoagent.py` — PR feature validation
- `tests/test_real_large_tasks.py` — Large multi-step tasks
- `tests/test_hooks_skills_plugins_real.py` — Hooks/skills/plugins in agent loops
- `tests/test_untested_features.py` — Module-level integration tests
