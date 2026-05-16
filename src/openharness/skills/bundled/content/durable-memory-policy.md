---
name: durable-memory-policy
description: Shared durable-memory write policy for the main model and reviewer.
---

# Durable Memory Writes

Use the memory_write tool for durable context that should survive future sessions.

## Good Candidates

- Stable user preferences or workflow preferences
- Repeated requests for the same tool, backend, format, or workflow across the session when they imply a durable default
- Recurring project constraints, decisions, or conventions
- High-frequency mistakes, gotchas, and fix patterns the agent should avoid repeating
- Safety guardrails, permission boundaries, protected files, and forbidden commands
- Output style, naming, validation, and retry rules that should shape future behavior
- Durable environment facts like hosts, paths, env names, or service endpoints
- Long-lived task context that future turns are likely to need

## Do Not Store

- Secrets, tokens, passwords, or credentials
- Transient logs, stack traces, or one-off debug output
- Short-lived plans that will be obsolete after this session
- Facts already obvious from repository source unless the conversation adds durable context

## Stable Key Patterns

- preference:<topic>
- project:<topic>
- environment:<topic>
- task:<topic>
- pitfall:<topic>
- guardrail:<topic>
- forbidden_command:<topic>
- protected_path:<topic>
- style_rule:<topic>
- naming_rule:<topic>
- validation_rule:<topic>
- retry_rule:<topic>

Reuse stable keys when updating existing memory so entries stay deduplicated.