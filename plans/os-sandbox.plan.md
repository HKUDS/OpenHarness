<plan id="oh-os-sandbox" title="OS-level sandboxing mapped to OH permission modes">

<status>DESIGN PLAN — NON-SHIPPING. This file is a plan, not the feature. No
runtime behavior changes until tasks T1–T6 land (each separately reviewed +
verified). Committing this file alone changes nothing.</status>

<context>
OH gates tool calls through `PermissionChecker.evaluate()` (permissions/checker.py:75)
in three modes — `default` / `plan` / `full_auto` (permissions/modes.py) — called from
the ONE tool-execution chokepoint `engine/query.py::_execute_tool_call()` (~887–981),
just before `tool.execute()` (~970).

What already exists:
- <item>`SandboxSettings` (config/settings.py:104–114): `enabled` (default False), `backend`
  ("srt"|"docker"), `network` (allow/deny domains), `filesystem` (allow_read/deny_read/
  allow_write/deny_write; default allow_write=["."]), docker limits.</item>
- <item>An optional **`srt`** (sandbox-runtime npm CLI) integration that wraps the BASH
  SUBPROCESS only: `utils/shell.py::create_shell_subprocess()` → `wrap_command_for_sandbox()`
  (sandbox/adapter.py:105) prepends `srt --settings <json> -c <cmd>`, which on macOS uses
  `sandbox-exec` and on Linux `bwrap`. Disabled by default; requires the npm CLI present.</item>
- <item>`platforms.py::detect_platform()` + `get_platform_capabilities()` already report
  `supports_sandbox_runtime` / `supports_docker_sandbox` per OS.</item>

The two gaps that matter:
- <gap id="G1">**File-write/edit tools ignore the path policy.** `tools/file_write_tool.py:59` and
  `file_edit_tool.py:67` call `path.write_text(...)` IN-PROCESS and only run Docker path
  validation — they never consult `SandboxSettings.filesystem.allow_write/deny_write`, nor the
  permission checker's path intent. A `full_auto` (or even `default` after one approval) agent can
  write anywhere the user can.</gap>
- <gap id="G2">**No OS sandbox by default, and none at all for in-process tools.** The only OS
  isolation is opt-in `srt` around bash. File reads/writes, grep, etc. run unsandboxed in the OH
  process.</gap>
</context>

<key-design-decision id="why-two-layers">
A full syscall sandbox (Apple Seatbelt / Linux Landlock+seccomp) of OH is **fundamentally partial**
because most tools run IN-PROCESS:
- <item>`sandbox-exec` (Seatbelt) wraps a process **at spawn** — it cannot retroactively confine an
  already-running Python interpreter, so it can only sandbox the bash SUBPROCESS, not in-process
  `write_text`.</item>
- <item>Landlock CAN self-restrict the current process, but it is **irreversible per-thread and
  monotonic** — applying it would also confine OH's own legitimate I/O (session storage under
  `~/.openharness`, config, logs) for the rest of the run. You cannot "enter then exit" a Landlock
  ruleset around a single tool call.</item>

Therefore the enforceable, robust design is **two layers**, not one:
1. <layer id="L1">**Policy at the tool boundary (in-process).** Enforce `allow_write`/`deny_write`/
   `deny_read` + the always-blocked sensitive paths in the file tools themselves, derived from the
   permission mode. This closes G1 and is the real guarantee for in-process side effects.</layer>
2. <layer id="L2">**OS sandbox where it is actually enforceable (the bash subprocess).** Apply a
   native Seatbelt profile (macOS) / Landlock+seccomp via `bwrap` or a small launcher (Linux) to the
   bash child, mapped to the mode — without depending on the external `srt` npm CLI. Keep `srt` as an
   optional backend; add a native backend so the default install is sandboxed out of the box.</layer>

This is the honest version of "Codex-style read-only / workspace-write / danger-full-access": Codex
gets full syscall confinement because its agent process IS the sandbox boundary; OH's agent is
in-process, so L1 carries the in-process guarantee and L2 confines the one real subprocess.
</key-design-decision>

<goal>
Make `plan` / `default` / `full_auto` enforce a real, consistent filesystem+network policy across
BOTH in-process file tools and the bash subprocess, on by default, with no external runtime
dependency — mapped to read-only / workspace-write / full-access tiers.
</goal>

<non-goals>
- <item>Full seccomp syscall filtering of the entire OH interpreter (breaks OH's own I/O; see
  why-two-layers). Landlock/seccomp apply to the bash child only.</item>
- <item>Network egress filtering for in-process HTTP (the LLM/API calls OH itself makes). L2 network
  policy applies to bash-spawned processes; in-process domain control is a separate, later effort.</item>
- <item>Windows OS sandboxing (no Seatbelt/Landlock equivalent wired). Windows keeps L1 path policy
  only; document the gap.</item>
- <item>Removing the existing `srt`/docker backends. They remain selectable; we ADD a native backend
  and the L1 enforcement.</item>
</non-goals>

<decisions>
<decision id="D1" status="resolved">
  <q>Where does the in-process filesystem guarantee live?</q>
  <a>In the file tools (L1), enforced via a shared `permissions` path-policy helper, NOT via OS
  syscalls. The file tools already receive the resolved path; they must check it against the
  mode-derived allow/deny set before `write_text`. This is the only point that can confine in-process
  writes.</a>
</decision>
<decision id="D2" status="resolved">
  <q>Native OS sandbox vs the existing `srt` dependency for bash?</q>
  <a>Add a NATIVE backend (`backend="native"`, becomes default): macOS emits a generated
  `sandbox-exec` profile; Linux uses `bwrap` if present else a Landlock+seccomp launcher. Keep
  `srt`/`docker` as opt-in backends. Native default means the protection ships without an npm install.</a>
</decision>
<decision id="D3" status="resolved">
  <q>Mode → policy mapping.</q>
  <a>`plan` → read-only (no writes anywhere; L1 already blocks mutating tools, L2 read-only profile is
  defense-in-depth). `default` → workspace-write (writes restricted to cwd + `allow_write`, minus
  `deny_write` and sensitive paths; per-call confirmation unchanged). `full_auto` → full-access
  (no path restriction beyond the always-blocked sensitive paths — see D5).</a>
</decision>
<decision id="D4" status="resolved">
  <q>Does `full_auto` keep the hardcoded sensitive-path denylist (.ssh, .aws/credentials, .gnupg…)?</q>
  <a>RESOLVED (user-confirmed): yes — even full-access blocks the sensitive-path set (checker.py:18–37)
  in BOTH layers, so "dangerously skip permissions" still can't exfiltrate SSH/cloud creds by default.
  A separate explicit opt-in would be required to disable even that. Implemented in L1 (path_policy).</a>
</decision>
<decision id="D5" status="resolved">
  <q>Fail-open or fail-closed when the OS sandbox is unavailable (no bwrap, Landlock unsupported
  kernel, etc.)?</q>
  <a>RESOLVED (user-confirmed): L1 (in-process path policy) ALWAYS applies (pure Python, always
  available). L2 (bash OS sandbox) honors `SandboxSettings.fail_if_unavailable`: default fail-OPEN with
  a one-time warning (bash runs unsandboxed but L1 still constrains file tools), opt-in fail-CLOSED.</a>
</decision>
<decision id="D6" status="resolved">
  <q>How aggressive is the default-on posture?</q>
  <a>RESOLVED (user-confirmed): L1 (file-tool path enforcement) is ON by default — the bigger real
  security win and low-surprise. L2 (OS bash sandbox) stays OPT-IN so it can't surprise users whose
  bash relies on broad filesystem access.</a>
</decision>
</decisions>

<architecture>
<module id="path-policy">New `openharness/permissions/path_policy.py`: `resolve_write_policy(mode, sandbox_settings, cwd)
→ PathPolicy` with `is_write_allowed(path)` / `is_read_allowed(path)`, folding in the sensitive-path
denylist + `allow_write`/`deny_write` + workspace root. Pure, unit-testable, platform-independent.</module>
<wire id="L1-file-tools">file_write_tool.py / file_edit_tool.py call `path_policy.is_write_allowed()`
before `write_text`; on deny return the existing tool-error shape (no write). Same for any future
mutating file tool.</wire>
<module id="os-sandbox">New `openharness/sandbox/os_sandbox.py`: `build_native_bash_wrapper(argv, cwd, mode, sandbox_settings)
→ wrapped_argv` (+ temp profile cleanup). macOS: write a `sandbox-exec -p <profile>` profile string for
the tier; Linux: `bwrap` arg set, or a Landlock+seccomp pre-exec launcher. Selected by `platforms.py`.</module>
<wire id="L2-bash">utils/shell.py::create_shell_subprocess routes to the native wrapper when
`backend=="native"` (new default), keeping the existing `srt`/`docker` branches.</wire>
</architecture>

<resolved-questions audience="user">
<q id="Q1" answer="yes">D4: sensitive-path denylist stays enforced even under `full_auto`.</q>
<q id="Q2" answer="fail-open+warn">D5: bash OS-sandbox unavailable → fail-open with a one-time warning (L1 still applies); opt-in fail-closed.</q>
<q id="Q3" answer="L1-on, L2-opt-in">D6: L1 file-tool path enforcement is on by default; the OS bash sandbox stays opt-in.</q>
</resolved-questions>

<tasks>
<task id="T1" depends="none">
  <title>path_policy module + unit tests</title>
  <what>Add `permissions/path_policy.py` (resolve_write_policy / is_write_allowed / is_read_allowed)
  folding sensitive-path denylist + allow_write/deny_write + cwd workspace root, per mode.</what>
  <files>src/openharness/permissions/path_policy.py, tests/test_permissions/test_path_policy.py</files>
  <verification>Unit: plan→all writes denied; default→cwd allowed, ~/.ssh denied, deny_write honored;
  full_auto→cwd+outside allowed but sensitive paths still denied (D4). Symlink-escape of cwd denied.</verification>
</task>
<task id="T2" depends="T1">
  <title>L1: enforce path policy in file-write/edit tools (closes G1)</title>
  <what>file_write_tool/file_edit_tool consult path_policy before write_text; deny → tool error, no
  write. Thread the active mode + SandboxSettings into the tools.</what>
  <files>src/openharness/tools/file_write_tool.py, file_edit_tool.py, (tool ctx plumbing)</files>
  <verification>A write outside policy returns an error and leaves the FS unchanged (assert file absent);
  an in-policy write succeeds. Regression: existing file-tool tests still pass.</verification>
</task>
<task id="T3" depends="none">
  <title>Native bash sandbox wrapper (macOS Seatbelt)</title>
  <what>os_sandbox.build_native_bash_wrapper for macOS: generate a sandbox-exec profile per tier
  (read-only / workspace-write / full-access).</what>
  <files>src/openharness/sandbox/os_sandbox.py, tests/test_sandbox/test_os_sandbox.py</files>
  <verification>On macOS: plan-tier wrapped bash cannot write a temp file (nonzero); workspace-write can
  write under cwd but not ~/; full-access writes both. Skipped on non-macOS.</verification>
</task>
<task id="T4" depends="T3">
  <title>Native bash sandbox (Linux bwrap / Landlock+seccomp)</title>
  <what>Linux arm of build_native_bash_wrapper: bwrap arg set if present, else Landlock+seccomp
  pre-exec launcher; same three tiers.</what>
  <files>src/openharness/sandbox/os_sandbox.py, tests/test_sandbox/test_os_sandbox.py</files>
  <verification>On Linux: same write-confinement assertions per tier; graceful fallback path covered.</verification>
</task>
<task id="T5" depends="T3,T4">
  <title>Wire native backend into shell + default flip</title>
  <what>create_shell_subprocess routes backend=="native" to the wrapper; map permission mode → tier;
  honor fail_if_unavailable (D5). Make native the default backend per D2/Q3 (pending user answer).</what>
  <files>src/openharness/utils/shell.py, src/openharness/sandbox/adapter.py, config/settings.py (default)</files>
  <verification>Integration: a `default`-mode bash session writing outside cwd is blocked by L2 on
  macOS+Linux; unavailable-sandbox path fails open with a single warning (or closed if configured).</verification>
</task>
<task id="T6" depends="T2,T5">
  <title>Docs + mode/tier mapping reference</title>
  <what>Document the two-layer model, the Windows L1-only gap, and the D4/D5 defaults in OH docs.</what>
  <files>docs/ (sandbox reference)</files>
  <verification>Doc lists each mode→tier→both-layer behavior + platform support matrix.</verification>
</task>
</tasks>

<verification-summary>
Feature ships only when T1–T5 are implemented + verified. T1+T2 (L1 path enforcement) deliver the
biggest real security gain independent of OS support and should land first; T3–T5 (L2 OS sandbox)
add subprocess confinement and the default flip.
</verification-summary>

</plan>
