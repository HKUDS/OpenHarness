# /goal: Goal-Driven Autonomy

`/goal` lets OpenHarness work toward a **completion condition** over many turns
without you prompting each step. After every turn, a lightweight **verifier
model** judges whether the goal is satisfied; if not, its verdict is fed back
as the next step and the loop continues — until the goal is done or a budget
is exhausted.

The design follows Claude Code's execution loop (built into the REPL, small
fast model verifies after each turn) and borrows Codex's persistence (goal
state survives restarts, resume with `/goal resume`).

## Usage

Start `oh` and set a goal:

```text
/goal <completion condition>
```

Examples:

```text
/goal Fix the login bug and make `uv run pytest tests/test_auth` pass
/goal Add rate limiting to the API and document it in README.md
```

Manage the running goal:

| Command | Effect |
|---|---|
| `/goal status` | Show the condition, verifier model, turns/tokens used, budget, and last verdict |
| `/goal pause` | Pause after the current turn (status `paused`) |
| `/goal resume` | Resume a paused or failed goal; also used after restarting `oh` |
| `/goal clear` | Delete the goal state and start fresh |

Flags at creation time:

```text
/goal --verifier-model gpt-5-mini --max-turns 50 <completion condition>
```

## Configuring the Verifier Model

Priority order (highest first):

1. **Command flag** — per-goal, wins over everything else:

   ```text
   /goal --verifier-model gpt-5-mini <completion condition>
   ```

2. **Environment variable**:

   ```powershell
   $env:OPENHARNESS_GOAL_VERIFIER_MODEL = "gpt-5-mini"
   ```

3. **Settings file** — `~/.openharness/settings.json`:

   ```json
   {
     "goal": {
       "verifier_model": "gpt-5-mini",
       "max_turns": 100,
       "max_tokens": null
     }
   }
   ```

4. **Fallback** — when nothing is configured, the verifier uses the active
   conversation model. This works but costs a full main-model call per
   judgement, so configuring a small model is recommended.

A small, cheap model is ideal (`gpt-5-mini`, `sonnet`, etc.). The verifier
only needs to read the goal, recent conversation, and answer with a JSON
verdict.

Budget limits can also come from the environment:
`OPENHARNESS_GOAL_MAX_TURNS` and `OPENHARNESS_GOAL_MAX_TOKENS`.

## Budget and Safety Nets

- **Turn budget** (`max_turns`, default 100): total goal-loop iterations.
  Note this counts *outer* goal turns, not individual LLM calls — each outer
  turn is itself a full inner agent loop.
- **Token budget** (`max_tokens`): stops once conversation usage reaches the
  limit. Unset by default.
- **Verifier failure cutoff**: if the verifier output is unparseable or the
  call fails 3 times in a row, the goal fails instead of spinning forever.
  A hung verifier call is also capped at 60 seconds and counted as a
  failure, so the UI never stays stuck on "Running agent loop...".
- When a budget is exhausted the goal status becomes `failed`; you can then
  readjust and `/goal resume`.

## Persistence and Recovery

Goal state (condition, budgets, turns run, last verdict) is stored per
project under `~/.openharness/data/goals/` and written after every turn.
When `oh` starts and finds an unfinished active goal it prints:

```text
[goal] 检测到未完成的目标…（已跑 N 轮），输入 /goal resume 继续
```

`/goal` is interactive-only (`remote_invocable=False`); it is not exposed on
remote channels (Feishu/Telegram/etc.).

## /goal vs. the Agent's Inner Loop

OpenHarness already has an **inner agentic loop** on every message: the model
requests tools, tools execute, results are fed back, and this repeats until
the model stops requesting tools (or `max_turns` hits). `/goal` adds a second
layer on top:

| | Inner loop (always on) | Outer `/goal` loop (opt-in) |
|---|---|---|
| Drives | LLM ↔ tool calls within one submission | Whole working sessions |
| Ends when | model stops requesting tools / `max_turns` | verifier says done / budget exhausted |
| Unit of work | one tool-use round-trip | one complete turn (an entire inner loop) |
| Who decides next | the main model | the verifier model + its `next_step_hint` |
| Persisted across restarts | via session snapshot | yes, with resume support |

In short: without `/goal`, each of your messages launches one inner loop and
stops. With `/goal`, the outer loop keeps launching inner loops and asks a
judge whether the announced finish line has actually been crossed.

## When to Use /goal

Good fits:

- Long tasks with an **objective, checkable acceptance criterion** (tests
  pass, files exist, CI green, a report is produced).
- Work that needs many iterations you don't want to hand-hold: bug-fix loops,
  refactors with a test suite, batch migrations, multi-file features,
  "research X and write the findings to a file".
- Sessions you expect to interrupt and resume later.

Poor fits:

- Exploratory work without a clear finish condition ("look around the repo
  and see what's wrong").
- Tasks needing frequent human judgement or step-by-step approval.
- Risky irreversible operations — the permission mode still applies inside
  the loop, but the whole point of `/goal` is lengthier autonomy.
- Small one-shot tasks where a normal prompt is cheaper and faster.

### Writing good completion conditions

State deliverables and evidence, not effort:

- ✔ "Make `uv run pytest tests/ -q` pass and update CHANGELOG.md"
- ✔ "Generate `docs/architecture.md` describing the module layout"
- ✘ "Improve the codebase"
- ✘ "Fix things until it feels right"