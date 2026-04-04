# diagnose

Diagnose why an agent run failed, regressed, or produced unexpected output — using structured evidence instead of intuition.

## When to use

Use when the user asks:
- "Why did this run fail?"
- "What changed between this run and the last one?"
- "The output looks wrong — what happened?"
- "Why is this run worse than before?"

## Workflow

1. **Locate the run artifacts** — check `artifacts/runs/<run_id>/` or the latest run directory for:
   - `manifest.json` — run metadata, task type, input hash, timestamps
   - `execution_trace.jsonl` — the full tool-call chain, one event per line
   - `verification_report.json` — what was verified and whether it passed
   - `failure_signature.json` — which stage failed and why (if present)
2. **Read the failure signature first** — if it exists, it already localizes the failure to a specific stage (routing, execution, verification, or governance)
3. **Trace the execution chain** — walk `execution_trace.jsonl` forward to find where output diverged from expectation
4. **Compare with a passing run** — if a previous run succeeded, diff the two manifests and traces to identify what changed
5. **Identify the failure layer**:
   - **Routing**: wrong task type or profile selected
   - **Execution**: tool call error, permission block, or unexpected result
   - **Verification**: output produced but did not match expected artifact
   - **Governance**: run was halted by a safety or boundary check
6. **Report with evidence** — cite specific file paths, line numbers in the trace, or field values from the manifest; never summarize without pointing to the source

## Rules

- Evidence before intuition: always read the trace before forming a hypothesis
- Localize before explaining: identify which stage failed before describing why
- Compare, don't guess: if a previous run succeeded, diff it — don't speculate about what changed
- If no artifacts exist, say so clearly and ask the user to re-run with archive mode enabled
