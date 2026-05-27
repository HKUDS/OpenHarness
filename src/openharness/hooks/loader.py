"""Load hooks from settings."""

from __future__ import annotations

from collections import defaultdict
from openharness.hooks.events import HookEvent
from openharness.hooks.schemas import HookDefinition


class HookRegistry:
    """Store hooks grouped by event."""

    def __init__(self) -> None:
        self._hooks: dict[HookEvent, list[HookDefinition]] = defaultdict(list)

    def register(self, event: HookEvent, hook: HookDefinition) -> None:
        """Register one hook."""
        self._hooks[event].append(hook)

    def get(self, event: HookEvent) -> list[HookDefinition]:
        """Return hooks registered for an event, ordered by priority.

        Hooks with a higher ``priority`` run first. ``sorted`` is stable, so
        hooks sharing the same priority keep their registration order.
        """
        hooks = self._hooks.get(event, [])
        return sorted(hooks, key=lambda hook: -getattr(hook, "priority", 0))

    def summary(self) -> str:
        """Return a human-readable hook summary."""
        lines: list[str] = []
        for event in HookEvent:
            hooks = self.get(event)
            if not hooks:
                continue
            lines.append(f"{event.value}:")
            for hook in hooks:
                matcher = getattr(hook, "matcher", None)
                detail = getattr(hook, "command", None) or getattr(hook, "prompt", None) or getattr(hook, "url", None) or ""
                suffix = f" matcher={matcher}" if matcher else ""
                priority = getattr(hook, "priority", 0)
                if priority:
                    suffix += f" priority={priority}"
                lines.append(f"  - {hook.type}{suffix}: {detail}")
        return "\n".join(lines)


def load_hook_registry(settings, plugins=None) -> HookRegistry:
    """Load hooks from the current settings object."""
    registry = HookRegistry()
    for raw_event, hooks in settings.hooks.items():
        try:
            event = HookEvent(raw_event)
        except ValueError:
            continue
        for hook in hooks:
            registry.register(event, hook)
    for plugin in plugins or []:
        if not plugin.enabled:
            continue
        for raw_event, hooks in plugin.hooks.items():
            try:
                event = HookEvent(raw_event)
            except ValueError:
                continue
            for hook in hooks:
                registry.register(event, hook)
    return registry
