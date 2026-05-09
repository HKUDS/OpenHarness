"""Runtime hook result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HookResult:
    """Result from a single hook execution."""

    hook_type: str
    success: bool
    output: str = ""
    blocked: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AggregatedHookResult:
    """Aggregated result for a hook event."""

    results: list[HookResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Return whether any hook blocked continuation."""
        return any(result.blocked for result in self.results)

    @property
    def reason(self) -> str:
        """Return the first blocking reason, if any."""
        for result in self.results:
            if result.blocked:
                return result.reason or result.output
        return ""

    @property
    def additional_context(self) -> str:
        """Return context fragments emitted by hooks.

        Hooks may expose context either as explicit metadata
        (``additional_context`` or Claude-style ``additionalContext``) or as a
        JSON object in stdout with the same fields. Plain command stdout is not
        treated as context so existing notification hooks do not accidentally
        affect model input.
        """
        fragments: list[str] = []
        for result in self.results:
            value = _extract_additional_context(result)
            if value:
                fragments.append(value)
        return "\n\n".join(fragments)


def _extract_additional_context(result: HookResult) -> str:
    for key in ("additional_context", "additionalContext"):
        value = result.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    hook_output = result.metadata.get("hookSpecificOutput")
    if isinstance(hook_output, dict):
        value = hook_output.get("additionalContext") or hook_output.get("additional_context")
        if isinstance(value, str) and value.strip():
            return value.strip()

    import json

    try:
        parsed = json.loads(result.output)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    for key in ("additional_context", "additionalContext"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    hook_output = parsed.get("hookSpecificOutput")
    if isinstance(hook_output, dict):
        value = hook_output.get("additionalContext") or hook_output.get("additional_context")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
