"""Prompt builder for memory consolidation dreams."""

from __future__ import annotations

from datetime import date
from pathlib import Path

MAX_ENTRYPOINT_LINES = 200
ENTRYPOINT_NAME = "MEMORY.md"


def build_consolidation_prompt(
    memory_root: str | Path,
    session_dir: str | Path,
    extra: str = "",
    *,
    preview: bool = False,
) -> str:
    """Build the dream prompt used by manual and automatic memory consolidation."""

    memory_root = Path(memory_root)
    session_dir = Path(session_dir)
    extra_section = f"\n\n## Additional context\n\n{extra.strip()}" if extra.strip() else ""
    write_mode = "PREVIEW MODE: do not write files; propose a concise patch plan only." if preview else "APPLY MODE: update memory files directly when changes are clearly warranted."
    return f"""# Dream: Memory Consolidation

You are performing a dream — a reflective pass over OpenHarness/ohmo memory files. Synthesize recent signal into durable, well-organized memories so future sessions can orient quickly.

Current date: {date.today().isoformat()}
Memory directory: `{memory_root}`
Session snapshots: `{session_dir}` (JSON files can be large; inspect narrowly, do not dump everything)
Mode: {write_mode}

---

## Non-negotiable memory policy

### Evidence discipline

- Do not infer user mistakes, motives, personality traits, or habits from incidental logs/config.
- Only record facts directly supported by user statements, repeated behavior, or explicit artifacts.
- Prefer neutral safety policies over accusations.
- If a secret appears in context, do not copy it. Record only a generic safety reminder if useful.
- Never preserve API keys, tokens, app secrets, verification tokens, credential-bearing URLs, or bearer strings.

### Classify every fact before writing

Use these categories:

1. **Stable Preference** — user-stated or repeatedly demonstrated durable preference.
2. **Durable Project Context** — repo paths, canonical repos, project boundaries, validation commands.
3. **Recent Snapshot** — active branches, current commits, temporary worktrees, recent test counts. Must include `Last observed: YYYY-MM-DD` and a reminder to verify current state.
4. **Sensitive/Private Context** — revenue, personal identity, private repos, business metrics. Must include `Privacy: personal/private; do not share externally or in group chats unless explicitly asked.`
5. **Operational Reminder** — short safety or workflow reminders.

### Staleness and scope

- Short-lived facts must be marked as snapshots, not permanent truths.
- Prefer updating existing files over creating new ones.
- Create at most 2 new markdown files in one dream.
- If a topic is transient, prefer `recent_work.md` or an existing status file over a new topic file.
- Do not move personal/business context into project memory; keep sensitive personal context in personal memory only.
- Every top-level memory file must include schema-v1 frontmatter with:
  `schema_version`, `id`, `name`, `description`, `type`, `category`, `importance`, `source`,
  `signature`, `created_at`, `updated_at`, `ttl_days`, `disabled`, and `supersedes`.

---

## Phase 1 — Orient

- List the memory directory to see what already exists.
- Read `{ENTRYPOINT_NAME}` if present; it is the memory index.
- Skim existing topic files so you update or merge instead of creating duplicates.

## Phase 2 — Gather recent signal

Look for information worth persisting. Sources in rough priority order:

1. Existing memory files that may need updates or contradiction fixes.
2. Recent session snapshots (`session-*.json`) when you need concrete context.
3. Focused grep/search terms based on recent work; avoid exhaustive transcript reading.

Skip idle chats, failed retry noise, implementation details that only matter for the current turn, and facts that cannot be supported.

## Phase 3 — Consolidate

For each durable thing worth remembering, write or update concise top-level markdown files in the memory directory.

Focus on:
- Merging new signal into existing topic files rather than creating near-duplicates.
- Converting relative dates ("yesterday", "last week") to absolute dates.
- Correcting or deleting contradicted facts at the source.
- Keeping memories useful for future sessions, not as raw transcripts.
- Adding `Last observed` for snapshots and `Privacy` for sensitive/private context.

## Phase 4 — Prune and index

Update `{ENTRYPOINT_NAME}` so it stays under {MAX_ENTRYPOINT_LINES} lines and remains an index, not a content dump.

- Each entry should be one concise line: `- [Title](file.md): one-line hook`.
- Remove pointers to memories that are stale, wrong, or superseded.
- For stale, wrong, or superseded memory files, set `disabled: true`; do not delete files.
- Treat usage-based stale candidates as review candidates, not automatic deletion instructions.
- Add pointers to newly important memories.
- Resolve contradictions if multiple files disagree.

## Required final response

Return a structured summary:

```md
## Dream Summary
Changed:
- file.md: what changed

Confidence:
- High: directly supported facts
- Medium: recent snapshots that should be verified before use
- Low: uncertain/stale candidates not written as facts

Privacy:
- Any private/sensitive context touched and how it is marked

Stale candidates:
- Items that may need review later
```

If nothing changed, say so and explain why.{extra_section}"""
