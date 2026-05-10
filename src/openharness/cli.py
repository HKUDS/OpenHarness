"""CLI entry point using typer."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer

__version__ = "0.1.9"

_PREVIEW_STOPWORDS = {
    "a",
    "an",
    "and",
    "bug",
    "by",
    "fix",
    "for",
    "get",
    "help",
    "in",
    "of",
    "on",
    "or",
    "please",
    "show",
    "test",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _safe_short(text: str, *, limit: int = 140) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _schema_argument_preview(tool_schema: dict[str, object]) -> dict[str, object]:
    input_schema = tool_schema.get("input_schema")
    if not isinstance(input_schema, dict):
        return {"required_args": [], "optional_args": []}
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return {"required_args": [], "optional_args": []}
    required_raw = input_schema.get("required")
    required = (
        sorted(str(name) for name in required_raw if isinstance(name, str))
        if isinstance(required_raw, list)
        else []
    )
    optional = sorted(name for name in properties if name not in required)
    return {"required_args": required, "optional_args": optional}


def _mcp_transport_preview(config: object) -> dict[str, str]:
    if hasattr(config, "type"):
        transport = str(getattr(config, "type") or "unknown")
    elif isinstance(config, dict):
        transport = str(config.get("type") or "unknown")
    else:
        transport = "unknown"

    if transport == "stdio":
        command = getattr(config, "command", None) if not isinstance(config, dict) else config.get("command")
        args = getattr(config, "args", None) if not isinstance(config, dict) else config.get("args")
        rendered_args = " ".join(str(item) for item in args) if isinstance(args, list) and args else ""
        target = " ".join(part for part in (str(command or "").strip(), rendered_args.strip()) if part).strip()
        return {"transport": "stdio", "target": target or "configured"}
    if transport in {"http", "ws"}:
        url = getattr(config, "url", None) if not isinstance(config, dict) else config.get("url")
        return {"transport": transport, "target": str(url or "").strip() or "configured"}
    return {"transport": transport, "target": "configured"}


def _validate_mcp_server(name: str, config: object) -> dict[str, object]:
    preview = _mcp_transport_preview(config)
    issues: list[str] = []
    status = "ok"
    transport = preview["transport"]

    if transport == "stdio":
        command = getattr(config, "command", None) if not isinstance(config, dict) else config.get("command")
        raw_cwd = getattr(config, "cwd", None) if not isinstance(config, dict) else config.get("cwd")
        command_text = str(command or "").strip()
        if not command_text:
            issues.append("missing command")
        elif shutil.which(command_text) is None:
            issues.append(f"command not found in PATH: {command_text}")
        if raw_cwd:
            resolved_cwd = Path(str(raw_cwd)).expanduser()
            if not resolved_cwd.exists():
                issues.append(f"cwd does not exist: {resolved_cwd}")
    elif transport in {"http", "ws"}:
        raw_url = getattr(config, "url", None) if not isinstance(config, dict) else config.get("url")
        parsed = urlparse(str(raw_url or "").strip())
        expected = {"http", "https"} if transport == "http" else {"ws", "wss"}
        if parsed.scheme not in expected or not parsed.netloc:
            issues.append(f"invalid {transport} url: {raw_url}")

    if issues:
        status = "error"
    return {
        "name": name,
        **preview,
        "status": status,
        "issues": issues,
    }


def _dry_run_command_behavior(name: str) -> dict[str, str]:
    read_only = {
        "help",
        "version",
        "status",
        "context",
        "cost",
        "usage",
        "stats",
        "hooks",
        "onboarding",
        "skills",
        "mcp",
        "doctor",
        "diff",
        "branch",
        "privacy-settings",
        "rate-limit-options",
        "release-notes",
        "upgrade",
        "keybindings",
        "files",
    }
    mutating = {
        "clear",
        "compact",
        "resume",
        "session",
        "export",
        "share",
        "copy",
        "tag",
        "rewind",
        "init",
        "bridge",
        "login",
        "logout",
        "feedback",
        "config",
        "plugin",
        "reload-plugins",
        "permissions",
        "plan",
        "fast",
        "effort",
        "passes",
        "turns",
        "continue",
        "provider",
        "model",
        "theme",
        "output-style",
        "vim",
        "voice",
        "commit",
        "issue",
        "pr_comments",
        "agents",
        "subagents",
        "tasks",
        "autopilot",
        "ship",
        "memory",
    }
    if name in read_only:
        return {
            "kind": "read_only",
            "detail": "This slash command mainly inspects current state and should not require a model turn.",
        }
    if name in mutating:
        return {
            "kind": "stateful",
            "detail": "This slash command can mutate local state, queue work, or trigger follow-up execution depending on its arguments.",
        }
    return {
        "kind": "unknown",
        "detail": "This slash command comes from a handler or plugin that dry-run cannot classify precisely.",
    }


def _tokenize_preview_text(text: str) -> list[str]:
    lowered = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9_/-]+", lowered)
    cjk_tokens = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
    seen: set[str] = set()
    ordered: list[str] = []
    for token in [*ascii_tokens, *cjk_tokens]:
        normalized = token.strip("-_/")
        if len(normalized) < 2 and normalized not in cjk_tokens:
            continue
        if normalized in _PREVIEW_STOPWORDS:
            continue
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _score_candidate_match(prompt: str, *fields: str) -> tuple[int, list[str]]:
    prompt_lower = prompt.lower()
    prompt_tokens = _tokenize_preview_text(prompt)
    haystack = " ".join(field.lower() for field in fields if field).strip()
    if not haystack:
        return 0, []

    score = 0
    reasons: list[str] = []
    for token in prompt_tokens:
        if token in haystack:
            score += max(2, min(len(token), 8))
            if len(reasons) < 3:
                reasons.append(token)
    primary_name = fields[0].lower() if fields and fields[0] else ""
    if primary_name and primary_name in prompt_lower:
        score += 10
        if fields[0] not in reasons:
            reasons.insert(0, fields[0])
    return score, reasons[:3]


def _candidate_entry(name: str, description: str, *, score: int, reasons: list[str]) -> dict[str, object]:
    return {
        "name": name,
        "description": description,
        "score": score,
        "reasons": reasons,
    }


def _recommend_preview_candidates(
    prompt: str | None,
    *,
    skills: list[object],
    tool_schemas: list[dict[str, object]],
    command_entries: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    if not prompt:
        return {"skills": [], "tools": [], "commands": []}
    stripped = prompt.strip()
    if not stripped or stripped.startswith("/"):
        return {"skills": [], "tools": [], "commands": []}

    skill_matches: list[dict[str, object]] = []
    for skill in skills:
        score, reasons = _score_candidate_match(
            stripped,
            str(getattr(skill, "name", "")),
            str(getattr(skill, "description", "")),
            str(getattr(skill, "content", ""))[:800],
        )
        if score >= 4:
            skill_matches.append(
                _candidate_entry(
                    str(getattr(skill, "name", "")),
                    str(getattr(skill, "description", "")),
                    score=score,
                    reasons=reasons,
                )
            )

    tool_matches: list[dict[str, object]] = []
    for tool in tool_schemas:
        optional = ", ".join(str(item) for item in tool.get("optional_args") or [])
        required = ", ".join(str(item) for item in tool.get("required_args") or [])
        score, reasons = _score_candidate_match(
            stripped,
            str(tool.get("name") or ""),
            str(tool.get("description") or ""),
            required,
            optional,
        )
        if score >= 4:
            tool_matches.append(
                _candidate_entry(
                    str(tool.get("name") or ""),
                    str(tool.get("description") or ""),
                    score=score,
                    reasons=reasons,
                )
            )

    command_matches: list[dict[str, object]] = []
    for command in command_entries:
        score, reasons = _score_candidate_match(
            stripped,
            str(command.get("name") or ""),
            str(command.get("description") or ""),
            str(command.get("behavior", {}).get("detail") or ""),
        )
        if score >= 8:
            command_matches.append(
                _candidate_entry(
                    str(command.get("name") or ""),
                    str(command.get("description") or ""),
                    score=score,
                    reasons=reasons,
                )
            )

    skill_matches.sort(key=lambda entry: (-int(entry["score"]), str(entry["name"])))
    tool_matches.sort(key=lambda entry: (-int(entry["score"]), str(entry["name"])))
    command_matches.sort(key=lambda entry: (-int(entry["score"]), str(entry["name"])))
    return {
        "skills": skill_matches[:5],
        "tools": tool_matches[:8],
        "commands": command_matches[:5],
    }


def _evaluate_dry_run_readiness(
    *,
    prompt: str | None,
    entrypoint: dict[str, object],
    validation: dict[str, object],
) -> dict[str, object]:
    level = "ready"
    reasons: list[str] = []
    next_actions: list[str] = []

    if entrypoint.get("kind") == "unknown_slash_command":
        level = "blocked"
        reasons.append("The prompt starts with '/' but does not match any registered slash command.")
        next_actions.append("Check the command name and run `oh --dry-run -p \"/help\"` to inspect available slash commands.")

    api_client = validation.get("api_client")
    if isinstance(api_client, dict) and api_client.get("status") == "error":
        if entrypoint.get("kind") == "model_prompt":
            level = "blocked"
            detail = str(api_client.get("detail") or "").strip()
            reasons.append(detail or "Runtime client resolution failed for a prompt that would require a model call.")
            next_actions.append("Fix authentication or provider profile configuration before running this prompt.")
        elif level != "blocked":
            level = "warning"
            reasons.append("Runtime client resolution failed. Interactive commands may still work, but model execution would fail.")
            next_actions.append("If you expect a model call later, fix authentication or provider profile configuration first.")

    mcp_errors = int(validation.get("mcp_errors") or 0)
    if mcp_errors > 0 and level != "blocked":
        level = "warning"
        reasons.append(f"{mcp_errors} configured MCP server(s) have obvious configuration errors.")
        next_actions.append("Fix or disable the broken MCP server configuration before relying on MCP-backed tools.")

    auth_status = str(validation.get("auth_status") or "")
    if auth_status.startswith("missing") and entrypoint.get("kind") in {"interactive_session", "model_prompt"} and level != "blocked":
        level = "warning"
        reasons.append("Authentication is missing, so live model execution would not start successfully.")
        next_actions.append("Run `oh auth login` or configure the active profile credentials before executing.")

    if not prompt and level == "ready":
        reasons.append("No prompt provided; dry-run only validated the session setup path.")
        next_actions.append("Provide `-p/--print` for a single prompt preview, or start `oh` normally to enter an interactive session.")
    elif level == "ready":
        reasons.append("Resolved configuration, prompt assembly, and static discovery checks all look usable.")
        if entrypoint.get("kind") == "slash_command":
            next_actions.append(f"You can run `oh -p \"{prompt}\"` directly.")
        elif entrypoint.get("kind") == "model_prompt":
            next_actions.append("You can run this prompt directly with `oh -p '...'` or open the interactive UI with `oh`.")
        else:
            next_actions.append("You can run OpenHarness normally with the current configuration.")

    deduped_actions: list[str] = []
    seen_actions: set[str] = set()
    for action in next_actions:
        normalized = action.strip()
        if not normalized or normalized in seen_actions:
            continue
        seen_actions.add(normalized)
        deduped_actions.append(normalized)

    return {"level": level, "reasons": reasons, "next_actions": deduped_actions}


def _build_dry_run_preview(
    *,
    prompt: str | None,
    cwd: str,
    model: str | None,
    max_turns: int | None,
    base_url: str | None,
    system_prompt: str | None,
    append_system_prompt: str | None,
    api_key: str | None,
    api_format: str | None,
    permission_mode: str | None,
) -> dict[str, object]:
    from openharness.api.provider import auth_status, detect_provider
    from openharness.commands import create_default_command_registry
    from openharness.config import get_config_file_path, load_settings
    from openharness.mcp.config import load_mcp_server_configs
    from openharness.plugins import load_plugins
    from openharness.prompts.context import build_runtime_system_prompt
    from openharness.skills import load_skill_registry
    from openharness.tools import create_default_tool_registry
    from openharness.ui.runtime import _resolve_api_client_from_settings

    resolved_cwd = str(Path(cwd).expanduser().resolve())
    settings = load_settings().merge_cli_overrides(
        model=model,
        max_turns=max_turns,
        base_url=base_url,
        system_prompt=system_prompt,
        api_key=api_key,
        api_format=api_format,
        permission_mode=permission_mode,
    )
    provider = detect_provider(settings)
    auth = auth_status(settings)
    profile_name, profile = settings.resolve_profile()

    plugins = load_plugins(settings, resolved_cwd)
    plugin_commands = [
        command
        for plugin in plugins
        if plugin.enabled
        for command in plugin.commands
    ]
    command_registry = create_default_command_registry(plugin_commands=plugin_commands)
    command_match = command_registry.lookup(prompt) if prompt else None
    skill_registry = load_skill_registry(resolved_cwd, settings=settings)
    skills = skill_registry.list_skills()
    mcp_servers = load_mcp_server_configs(settings, plugins)
    tool_registry = create_default_tool_registry()
    tool_schemas = []
    for tool_schema in tool_registry.to_api_schema():
        args_preview = _schema_argument_preview(tool_schema)
        tool_schemas.append(
            {
                "name": str(tool_schema.get("name") or ""),
                "description": str(tool_schema.get("description") or ""),
                **args_preview,
            }
        )

    client_validation = {"status": "ok", "detail": ""}
    try:
        with redirect_stderr(StringIO()):
            _resolve_api_client_from_settings(settings)
    except SystemExit:
        client_validation = {"status": "error", "detail": "runtime client could not be resolved with current auth/config"}
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        client_validation = {"status": "error", "detail": str(exc)}

    preview_prompt = prompt.strip() if prompt else None
    prompt_seed = preview_prompt
    if append_system_prompt:
        appended = append_system_prompt.strip()
        if appended:
            existing = settings.system_prompt or ""
            settings = settings.model_copy(update={"system_prompt": f"{existing}\n\n{appended}".strip()})
    system_prompt_text = build_runtime_system_prompt(
        settings,
        cwd=resolved_cwd,
        latest_user_prompt=prompt_seed,
    )

    command_entries = []
    for command in command_registry.list_commands():
        behavior = _dry_run_command_behavior(command.name)
        command_entries.append(
            {
                "name": command.name,
                "description": command.description,
                "remote_invocable": command.remote_invocable,
                "remote_admin_opt_in": command.remote_admin_opt_in,
                "behavior": behavior,
            }
        )

    recommendations = _recommend_preview_candidates(
        preview_prompt,
        skills=skills,
        tool_schemas=tool_schemas,
        command_entries=command_entries,
    )

    if preview_prompt:
        if preview_prompt.startswith("/") and command_match is not None:
            matched_command = command_match[0]
            behavior = _dry_run_command_behavior(matched_command.name)
            entrypoint = {
                "kind": "slash_command",
                "command": matched_command.name,
                "args": command_match[1],
                "description": matched_command.description,
                "remote_invocable": matched_command.remote_invocable,
                "remote_admin_opt_in": matched_command.remote_admin_opt_in,
                "behavior": behavior["kind"],
                "detail": (
                    f"Input resolves to /{matched_command.name}. "
                    f"{behavior['detail']} Dry-run does not execute the command handler."
                ),
            }
        elif preview_prompt.startswith("/") and command_match is None:
            entrypoint = {
                "kind": "unknown_slash_command",
                "detail": "Input starts with / but does not match a registered slash command.",
            }
        else:
            entrypoint = {
                "kind": "model_prompt",
                "detail": (
                    "The first live step would be a model request. "
                    "Exact tool calls and parameters are decided by the model at runtime."
                ),
            }
    else:
        entrypoint = {
            "kind": "interactive_session",
            "detail": "OpenHarness would start and wait for user input. No model or tool call happens until you submit one.",
        }

    preview = {
        "mode": "dry-run",
        "cwd": resolved_cwd,
        "config_path": str(get_config_file_path()),
        "prompt": preview_prompt,
        "prompt_preview": _safe_short(preview_prompt or "", limit=220) if preview_prompt else "",
        "settings": {
            "active_profile": profile_name,
            "profile_label": profile.label,
            "provider": provider.name,
            "api_format": settings.api_format,
            "model": settings.model,
            "base_url": settings.base_url or "",
            "permission_mode": settings.permission.mode.value,
            "max_turns": settings.max_turns,
            "effort": settings.effort,
            "passes": settings.passes,
        },
        "validation": {
            "auth_status": auth,
            "api_client": client_validation,
            "system_prompt_chars": len(system_prompt_text),
            "mcp_validation": "skipped in dry-run (configured only; external servers are not started)",
        },
        "entrypoint": entrypoint,
        "commands": command_entries,
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "source": skill.source,
            }
            for skill in skills
        ],
        "tools": tool_schemas,
        "recommendations": recommendations,
        "plugins": [
            {
                "name": plugin.manifest.name,
                "enabled": plugin.enabled,
                "skills": len(plugin.skills),
                "commands": len(plugin.commands),
                "agents": len(plugin.agents),
                "mcp_servers": len(plugin.mcp_servers),
            }
            for plugin in plugins
        ],
        "mcp_servers": [
            _validate_mcp_server(name, config)
            for name, config in sorted(mcp_servers.items())
        ],
        "system_prompt_preview": _safe_short(system_prompt_text, limit=600),
    }
    mcp_errors = sum(1 for entry in preview["mcp_servers"] if entry.get("status") == "error")
    preview["validation"]["mcp_errors"] = mcp_errors
    preview["readiness"] = _evaluate_dry_run_readiness(
        prompt=preview_prompt,
        entrypoint=preview["entrypoint"],
        validation=preview["validation"],
    )
    return preview


def _format_dry_run_preview(preview: dict[str, object]) -> str:
    settings = preview.get("settings") if isinstance(preview.get("settings"), dict) else {}
    validation = preview.get("validation") if isinstance(preview.get("validation"), dict) else {}
    entrypoint = preview.get("entrypoint") if isinstance(preview.get("entrypoint"), dict) else {}
    readiness = preview.get("readiness") if isinstance(preview.get("readiness"), dict) else {}
    recommendations = preview.get("recommendations") if isinstance(preview.get("recommendations"), dict) else {}
    plugins = preview.get("plugins") if isinstance(preview.get("plugins"), list) else []
    skills = preview.get("skills") if isinstance(preview.get("skills"), list) else []
    commands = preview.get("commands") if isinstance(preview.get("commands"), list) else []
    tools = preview.get("tools") if isinstance(preview.get("tools"), list) else []
    mcp_servers = preview.get("mcp_servers") if isinstance(preview.get("mcp_servers"), list) else []

    lines = [
        "OpenHarness Dry Run",
        "",
        "Readiness",
        f"- level: {readiness.get('level', 'unknown')}",
    ]
    readiness_reasons = readiness.get("reasons")
    if isinstance(readiness_reasons, list):
        for reason in readiness_reasons[:4]:
            lines.append(f"- {reason}")
    readiness_actions = readiness.get("next_actions")
    if isinstance(readiness_actions, list) and readiness_actions:
        lines.append("- next actions:")
        for action in readiness_actions[:4]:
            lines.append(f"  - {action}")
    lines.extend(
        [
        "",
        "Execution",
        f"- cwd: {preview.get('cwd')}",
        f"- prompt: {preview.get('prompt_preview') or '(none)'}",
        f"- entrypoint: {entrypoint.get('kind', 'unknown')}",
        f"- detail: {entrypoint.get('detail', '')}",
        "",
        "Resolved Settings",
        f"- profile: {settings.get('active_profile')} ({settings.get('profile_label')})",
        f"- provider: {settings.get('provider')}",
        f"- api_format: {settings.get('api_format')}",
        f"- model: {settings.get('model')}",
        f"- base_url: {settings.get('base_url') or '(default)'}",
        f"- permission_mode: {settings.get('permission_mode')}",
        f"- max_turns: {settings.get('max_turns')}",
        f"- effort: {settings.get('effort')} / passes={settings.get('passes')}",
        "",
        "Validation",
        f"- auth: {validation.get('auth_status')}",
        f"- api client: {validation.get('api_client', {}).get('status', 'unknown')}",
        f"- system prompt chars: {validation.get('system_prompt_chars')}",
        f"- mcp: {validation.get('mcp_validation')}",
        f"- mcp config errors: {validation.get('mcp_errors', 0)}",
        "",
        "Discovery",
        f"- plugins: {len(plugins)}",
        f"- skills: {len(skills)}",
        f"- slash commands: {len(commands)}",
        f"- built-in tools: {len(tools)}",
        f"- configured mcp servers: {len(mcp_servers)}",
        ]
    )

    if mcp_servers:
        lines.extend(["", "Configured MCP"])
        for entry in mcp_servers[:8]:
            status = entry.get("status") or "unknown"
            suffix = ""
            issues = entry.get("issues")
            if isinstance(issues, list) and issues:
                suffix = f" [{'; '.join(str(item) for item in issues)}]"
            lines.append(
                f"- {entry.get('name')}: {entry.get('transport')} -> {entry.get('target')} ({status}){suffix}"
            )
        if len(mcp_servers) > 8:
            lines.append(f"- ... (+{len(mcp_servers) - 8} more)")

    if tools:
        lines.extend(["", "Available Tools"])
        for entry in tools[:12]:
            required = entry.get("required_args") or []
            optional = entry.get("optional_args") or []
            signature_parts: list[str] = []
            if required:
                signature_parts.append("required: " + ", ".join(required))
            if optional:
                signature_parts.append("optional: " + ", ".join(optional[:4]))
            suffix = f" ({'; '.join(signature_parts)})" if signature_parts else ""
            lines.append(f"- {entry.get('name')}{suffix}")
        if len(tools) > 12:
            lines.append(f"- ... (+{len(tools) - 12} more)")

    if skills:
        lines.extend(["", "Available Skills"])
        for entry in skills[:8]:
            lines.append(f"- {entry.get('name')}: {_safe_short(str(entry.get('description') or ''), limit=100)}")
        if len(skills) > 8:
            lines.append(f"- ... (+{len(skills) - 8} more)")

    recommended_skills = recommendations.get("skills") if isinstance(recommendations.get("skills"), list) else []
    recommended_tools = recommendations.get("tools") if isinstance(recommendations.get("tools"), list) else []
    recommended_commands = recommendations.get("commands") if isinstance(recommendations.get("commands"), list) else []
    if recommended_skills or recommended_tools or recommended_commands:
        lines.extend(["", "Likely Matches"])
        if recommended_skills:
            lines.append("- skills:")
            for entry in recommended_skills[:4]:
                reasons = ", ".join(str(item) for item in entry.get("reasons") or [])
                suffix = f" [{reasons}]" if reasons else ""
                lines.append(f"  - {entry.get('name')} (score={entry.get('score')}){suffix}")
        if recommended_tools:
            lines.append("- tools:")
            for entry in recommended_tools[:6]:
                reasons = ", ".join(str(item) for item in entry.get("reasons") or [])
                suffix = f" [{reasons}]" if reasons else ""
                lines.append(f"  - {entry.get('name')} (score={entry.get('score')}){suffix}")
        if recommended_commands:
            lines.append("- slash commands:")
            for entry in recommended_commands[:4]:
                reasons = ", ".join(str(item) for item in entry.get("reasons") or [])
                suffix = f" [{reasons}]" if reasons else ""
                lines.append(f"  - /{entry.get('name')} (score={entry.get('score')}){suffix}")

    if entrypoint.get("kind") == "slash_command":
        lines.extend(
            [
                "",
                "Slash Command Detail",
                f"- command: /{entrypoint.get('command')}",
                f"- description: {entrypoint.get('description')}",
                f"- behavior: {entrypoint.get('behavior')}",
                f"- remote_invocable: {entrypoint.get('remote_invocable')}",
                f"- remote_admin_opt_in: {entrypoint.get('remote_admin_opt_in')}",
            ]
        )
        args = str(entrypoint.get("args") or "").strip()
        if args:
            lines.append(f"- args: {args}")

    preview_text = str(preview.get("system_prompt_preview") or "").strip()
    if preview_text:
        lines.extend(["", "System Prompt Preview", preview_text])

    return "\n".join(lines)


def _version_callback(value: bool) -> None:
    if value:
        print(f"openharness {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="openharness",
    help=(
        "Oh my Harness! An AI-powered coding assistant.\n\n"
        "Starts an interactive session by default, use -p/--print for non-interactive output."
    ),
    add_completion=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

mcp_app = typer.Typer(name="mcp", help="Manage MCP servers")
plugin_app = typer.Typer(name="plugin", help="Manage plugins")
auth_app = typer.Typer(name="auth", help="Manage authentication")
provider_app = typer.Typer(name="provider", help="Manage provider profiles")
cron_app = typer.Typer(name="cron", help="Manage cron scheduler and jobs")
autopilot_app = typer.Typer(name="autopilot", help="Manage repo autopilot")

app.add_typer(mcp_app)
app.add_typer(plugin_app)
app.add_typer(auth_app)
app.add_typer(provider_app)
app.add_typer(cron_app)
app.add_typer(autopilot_app)


# ---- mcp subcommands ----

@mcp_app.command("list")
def mcp_list() -> None:
    """List configured MCP servers."""
    from openharness.config import load_settings
    from openharness.mcp.config import load_mcp_server_configs
    from openharness.plugins import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    configs = load_mcp_server_configs(settings, plugins)
    if not configs:
        print("No MCP servers configured.")
        return
    for name, cfg in configs.items():
        transport = cfg.get("transport", cfg.get("command", "unknown"))
        print(f"  {name}: {transport}")


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Server name"),
    config_json: str = typer.Argument(..., help="Server config as JSON string"),
) -> None:
    """Add an MCP server configuration."""
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    try:
        cfg = json.loads(config_json)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    if not isinstance(settings.mcp_servers, dict):
        settings.mcp_servers = {}
    settings.mcp_servers[name] = cfg
    save_settings(settings)
    print(f"Added MCP server: {name}")


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove"),
) -> None:
    """Remove an MCP server configuration."""
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    if not isinstance(settings.mcp_servers, dict) or name not in settings.mcp_servers:
        print(f"MCP server not found: {name}", file=sys.stderr)
        raise typer.Exit(1)
    del settings.mcp_servers[name]
    save_settings(settings)
    print(f"Removed MCP server: {name}")


# ---- plugin subcommands ----

@plugin_app.command("list")
def plugin_list() -> None:
    """List installed plugins."""
    from openharness.config import load_settings
    from openharness.plugins import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    if not plugins:
        print("No plugins installed.")
        return
    for plugin in plugins:
        status = "enabled" if plugin.enabled else "disabled"
        print(f"  {plugin.name} [{status}] - {plugin.description or ''}")


@plugin_app.command("install")
def plugin_install(
    source: str = typer.Argument(..., help="Plugin source (path or URL)"),
) -> None:
    """Install a plugin from a source path."""
    from openharness.plugins.installer import install_plugin_from_path

    result = install_plugin_from_path(source)
    print(f"Installed plugin: {result}")


@plugin_app.command("uninstall")
def plugin_uninstall(
    name: str = typer.Argument(..., help="Plugin name to uninstall"),
) -> None:
    """Uninstall a plugin."""
    from openharness.plugins.installer import uninstall_plugin

    try:
        uninstall_plugin(name)
    except ValueError as exc:
        raise typer.BadParameter("invalid plugin name") from exc
    print(f"Uninstalled plugin: {name}")


# ---- cron subcommands ----

@cron_app.command("start")
def cron_start() -> None:
    """Start the cron scheduler daemon."""
    from openharness.services.cron_scheduler import is_scheduler_running, start_daemon

    if is_scheduler_running():
        print("Cron scheduler is already running.")
        return
    pid = start_daemon()
    print(f"Cron scheduler started (pid={pid})")


@cron_app.command("stop")
def cron_stop() -> None:
    """Stop the cron scheduler daemon."""
    from openharness.services.cron_scheduler import stop_scheduler

    if stop_scheduler():
        print("Cron scheduler stopped.")
    else:
        print("Cron scheduler is not running.")


@cron_app.command("status")
def cron_status_cmd() -> None:
    """Show cron scheduler status and job summary."""
    from openharness.services.cron_scheduler import scheduler_status

    status = scheduler_status()
    state = "running" if status["running"] else "stopped"
    print(f"Scheduler: {state}" + (f" (pid={status['pid']})" if status["pid"] else ""))
    print(f"Jobs:      {status['enabled_jobs']} enabled / {status['total_jobs']} total")
    print(f"Log:       {status['log_file']}")


@cron_app.command("list")
def cron_list_cmd() -> None:
    """List all registered cron jobs with schedule and status."""
    from openharness.services.cron import load_cron_jobs

    jobs = load_cron_jobs()
    if not jobs:
        print("No cron jobs configured.")
        return
    for job in jobs:
        enabled = "on " if job.get("enabled", True) else "off"
        last = job.get("last_run", "never")
        if last != "never":
            last = last[:19]  # trim to readable datetime
        last_status = job.get("last_status", "")
        status_indicator = f" [{last_status}]" if last_status else ""
        timezone = f" ({job['timezone']})" if job.get("timezone") else ""
        print(f"  [{enabled}] {job['name']}  {job.get('schedule', '?')}{timezone}")
        print(f"        cmd: {job.get('command') or '(agent_turn)'}")
        payload = job.get("payload")
        if isinstance(payload, dict):
            print(
                f"        payload: {payload.get('kind', 'agent_turn')} -> "
                f"{payload.get('channel', '?')}:{payload.get('to', '?')}"
            )
        notify = job.get("notify")
        if isinstance(notify, dict):
            notify_type = notify.get("type", "?")
            target = notify.get("user_open_id") or notify.get("open_id") or notify.get("chat_id") or "?"
            print(f"        notify: {notify_type} -> {target}")
        print(f"        last: {last}{status_indicator}  next: {job.get('next_run', 'n/a')[:19]}")


@cron_app.command("toggle")
def cron_toggle_cmd(
    name: str = typer.Argument(..., help="Cron job name"),
    enabled: bool = typer.Argument(..., help="true to enable, false to disable"),
) -> None:
    """Enable or disable a cron job."""
    from openharness.services.cron import set_job_enabled

    if not set_job_enabled(name, enabled):
        print(f"Cron job not found: {name}")
        raise typer.Exit(1)
    state = "enabled" if enabled else "disabled"
    print(f"Cron job '{name}' is now {state}")


@cron_app.command("history")
def cron_history_cmd(
    name: str | None = typer.Argument(None, help="Filter by job name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
) -> None:
    """Show cron execution history."""
    from openharness.services.cron_scheduler import load_history

    entries = load_history(limit=limit, job_name=name)
    if not entries:
        print("No execution history.")
        return
    for entry in entries:
        ts = entry.get("started_at", "?")[:19]
        status = entry.get("status", "?")
        rc = entry.get("returncode", "?")
        print(f"  {ts}  {entry.get('name', '?')}  {status} (rc={rc})")
        stderr = entry.get("stderr", "").strip()
        if stderr and status != "success":
            for line in stderr.splitlines()[:3]:
                print(f"    stderr: {line}")


@cron_app.command("logs")
def cron_logs_cmd(
    lines: int = typer.Option(30, "--lines", "-n", help="Number of lines to show"),
) -> None:
    """Show recent cron scheduler log output."""
    from openharness.config.paths import get_logs_dir

    log_path = get_logs_dir() / "cron_scheduler.log"
    if not log_path.exists():
        print("No scheduler log found. Start the scheduler with: oh cron start")
        return
    content = log_path.read_text(encoding="utf-8", errors="replace")
    tail = content.splitlines()[-lines:]
    for line in tail:
        print(line)


# ---- autopilot subcommands ----

@autopilot_app.command("status")
def autopilot_status_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Show repo autopilot queue status."""
    from openharness.autopilot import RepoAutopilotStore

    store = RepoAutopilotStore(cwd)
    counts = store.stats()
    print("Autopilot queue status:")
    for status_name in (
        "queued",
        "accepted",
        "preparing",
        "running",
        "verifying",
        "pr_open",
        "waiting_ci",
        "repairing",
        "completed",
        "merged",
        "failed",
        "rejected",
        "superseded",
    ):
        print(f"  {status_name}: {counts.get(status_name, 0)}")
    next_card = store.pick_next_card()
    if next_card is not None:
        print(f"  next: {next_card.id} {next_card.title} (score={next_card.score})")
    print(f"  registry: {store.registry_path}")
    print(f"  journal: {store.journal_path}")
    print(f"  context: {store.context_path}")


@autopilot_app.command("list")
def autopilot_list_cmd(
    status: str | None = typer.Argument(None, help="Optional status filter"),
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """List repo autopilot cards."""
    from openharness.autopilot import RepoAutopilotStore

    store = RepoAutopilotStore(cwd)
    cards = store.list_cards(status=status) if status else store.list_cards()
    if not cards:
        print("No autopilot cards.")
        return
    for card in cards[:20]:
        print(f"{card.id} [{card.status}] score={card.score} {card.title}")
        print(f"  source={card.source_kind} ref={card.source_ref or '-'}")
        if card.body:
            print(f"  {_safe_short(card.body)}")


@autopilot_app.command("add")
def autopilot_add_cmd(
    source: str = typer.Argument("manual_idea", help="Source kind: idea, ohmo, issue, pr, claude"),
    title: str = typer.Argument(..., help="Task title"),
    body: str = typer.Option("", "--body", help="Task body/details"),
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Add one repo autopilot card."""
    from openharness.autopilot import RepoAutopilotStore

    source_map = {
        "idea": "manual_idea",
        "manual": "manual_idea",
        "manual_idea": "manual_idea",
        "ohmo": "ohmo_request",
        "ohmo_request": "ohmo_request",
        "issue": "github_issue",
        "github_issue": "github_issue",
        "pr": "github_pr",
        "github_pr": "github_pr",
        "claude": "claude_code_candidate",
        "claude_code_candidate": "claude_code_candidate",
    }
    source_kind = source_map.get(source.lower())
    if source_kind is None:
        print(f"Unknown source kind: {source}", file=sys.stderr)
        raise typer.Exit(1)
    store = RepoAutopilotStore(cwd)
    card, created = store.enqueue_card(source_kind=source_kind, title=title, body=body)
    state = "Queued" if created else "Refreshed"
    print(f"{state} {card.id} (score={card.score}): {card.title}")


@autopilot_app.command("context")
def autopilot_context_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Print the synthesized active repo context."""
    from openharness.autopilot import RepoAutopilotStore

    store = RepoAutopilotStore(cwd)
    print(store.load_active_context())


@autopilot_app.command("journal")
def autopilot_journal_cmd(
    limit: int = typer.Option(12, "--limit", "-n", help="Number of entries"),
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Print the recent repo autopilot journal."""
    from openharness.autopilot import RepoAutopilotStore

    store = RepoAutopilotStore(cwd)
    entries = store.load_journal(limit=limit)
    if not entries:
        print("Repo journal is empty.")
        return
    for entry in entries:
        print(f"{entry.kind} {entry.task_id or '-'} {entry.summary}")


@autopilot_app.command("scan")
def autopilot_scan_cmd(
    target: str = typer.Argument(..., help="issues, prs, claude-code, or all"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of items"),
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Scan one or more autopilot intake sources."""
    from openharness.autopilot import RepoAutopilotStore

    store = RepoAutopilotStore(cwd)
    if target == "issues":
        print(f"Scanned {len(store.scan_github_issues(limit=limit))} GitHub issues.")
        return
    if target == "prs":
        print(f"Scanned {len(store.scan_github_prs(limit=limit))} GitHub PRs.")
        return
    if target == "claude-code":
        print(f"Scanned {len(store.scan_claude_code_candidates(limit=limit))} claude-code candidates.")
        return
    if target == "all":
        print(json.dumps(store.scan_all_sources(issue_limit=limit, pr_limit=limit), ensure_ascii=False))
        return
    print(f"Unknown scan target: {target}", file=sys.stderr)
    raise typer.Exit(1)


@autopilot_app.command("run-next")
def autopilot_run_next_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
    model: str | None = typer.Option(None, "--model", help="Override execution model"),
    max_turns: int | None = typer.Option(None, "--max-turns", help="Override execution max turns"),
    permission_mode: str | None = typer.Option(None, "--permission-mode", help="Override execution permission mode"),
) -> None:
    """Run the highest-priority queued autopilot card end-to-end."""
    import asyncio
    from openharness.autopilot import RepoAutopilotStore

    try:
        result = asyncio.run(
            RepoAutopilotStore(cwd).run_next(
                model=model,
                max_turns=max_turns,
                permission_mode=permission_mode,
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise typer.Exit(1)
    print(f"{result.card_id} -> {result.status}")
    print(f"run report: {result.run_report_path}")
    print(f"verification report: {result.verification_report_path}")


@autopilot_app.command("tick")
def autopilot_tick_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
    model: str | None = typer.Option(None, "--model", help="Override execution model"),
    max_turns: int | None = typer.Option(None, "--max-turns", help="Override execution max turns"),
    permission_mode: str | None = typer.Option(None, "--permission-mode", help="Override execution permission mode"),
    limit: int = typer.Option(10, "--limit", "-n", help="Scan limit for issues/PRs"),
) -> None:
    """Scan sources and, if idle, run the next queued autopilot task."""
    import asyncio
    from openharness.autopilot import RepoAutopilotStore

    try:
        result = asyncio.run(
            RepoAutopilotStore(cwd).tick(
                model=model,
                max_turns=max_turns,
                permission_mode=permission_mode,
                issue_limit=limit,
                pr_limit=limit,
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise typer.Exit(1)
    if result is None:
        print("Autopilot tick completed with no execution.")
        return
    print(f"{result.card_id} -> {result.status}")
    print(f"run report: {result.run_report_path}")
    print(f"verification report: {result.verification_report_path}")


@autopilot_app.command("install-cron")
def autopilot_install_cron_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
) -> None:
    """Install default cron jobs for repo autopilot scan/tick."""
    from openharness.autopilot import RepoAutopilotStore

    names = RepoAutopilotStore(cwd).install_default_cron()
    print("Installed cron jobs: " + ", ".join(names))


@autopilot_app.command("export-dashboard")
def autopilot_export_dashboard_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Repository root"),
    output: str | None = typer.Option(None, "--output", help="Dashboard output directory"),
) -> None:
    """Export a static autopilot kanban site for GitHub Pages."""
    from openharness.autopilot import RepoAutopilotStore

    path = RepoAutopilotStore(cwd).export_dashboard(output)
    print(f"Exported autopilot dashboard: {path}")


# ---- auth subcommands ----

# Mapping from provider name to human-readable label for interactive prompts.
_PROVIDER_LABELS: dict[str, str] = {
    "anthropic": "Anthropic (Claude API)",
    "anthropic_claude": "Claude subscription (Claude CLI)",
    "openai": "OpenAI / compatible",
    "openai_codex": "OpenAI Codex subscription (Codex CLI)",
    "copilot": "GitHub Copilot",
    "dashscope": "Alibaba DashScope",
    "bedrock": "AWS Bedrock",
    "vertex": "Google Vertex AI",
    "moonshot": "Moonshot (Kimi)",
    "gemini": "Google Gemini",
    "minimax": "MiniMax",
    "modelscope": "ModelScope",
}

_AUTH_SOURCE_LABELS: dict[str, str] = {
    "anthropic_api_key": "Anthropic API key",
    "openai_api_key": "OpenAI API key",
    "codex_subscription": "Codex subscription",
    "claude_subscription": "Claude subscription",
    "copilot_oauth": "GitHub Copilot OAuth",
    "dashscope_api_key": "DashScope API key",
    "bedrock_api_key": "Bedrock credentials",
    "vertex_api_key": "Vertex credentials",
    "moonshot_api_key": "Moonshot API key",
    "gemini_api_key": "Gemini API key",
    "minimax_api_key": "MiniMax API key",
    "modelscope_api_key": "ModelScope API key",
}


def _can_use_questionary() -> bool:
    """Return True when a real interactive terminal is available."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    if sys.stdin is not sys.__stdin__ or sys.stdout is not sys.__stdout__:
        return False
    try:
        import questionary  # noqa: F401
    except ImportError:
        return False
    return True


def _select_with_questionary(
    title: str,
    options: list[tuple[str, str]],
    *,
    default_value: str | None = None,
) -> str:
    import questionary

    choices = [
        questionary.Choice(
            title=label,
            value=value,
            checked=(value == default_value),
        )
        for value, label in options
    ]
    result = questionary.select(title, choices=choices, default=default_value).ask()
    if result is None:
        raise typer.Abort()
    return str(result)


def _text_prompt(message: str, *, default: str = "") -> str:
    """Prompt for text input, preferring questionary in a real TTY."""
    if _can_use_questionary():
        import questionary

        result = questionary.text(message, default=default).ask()
        if result is None:
            raise typer.Abort()
        return str(result)
    return typer.prompt(message, default=default)


def _secret_prompt(message: str) -> str:
    """Prompt for secret text, preferring questionary in a real TTY."""
    if _can_use_questionary():
        import questionary

        result = questionary.password(message).ask()
        if result is None:
            raise typer.Abort()
        return str(result)
    return typer.prompt(message, hide_input=True)


def _confirm_prompt(message: str, *, default: bool = False) -> bool:
    """Prompt for a yes/no confirmation, preferring questionary in a real TTY."""
    if _can_use_questionary():
        import questionary

        result = questionary.confirm(message, default=default).ask()
        if result is None:
            raise typer.Abort()
        return bool(result)
    return bool(typer.confirm(message, default=default))


def _select_from_menu(
    title: str,
    options: list[tuple[str, str]],
    *,
    default_value: str | None = None,
) -> str:
    """Render a simple numbered picker and return the selected value."""
    if _can_use_questionary():
        return _select_with_questionary(title, options, default_value=default_value)
    print(title, flush=True)
    default_index = 1
    for index, (value, label) in enumerate(options, 1):
        marker = " (default)" if value == default_value else ""
        if value == default_value:
            default_index = index
        print(f"  {index}. {label}{marker}", flush=True)
    raw = typer.prompt("Choose", default=str(default_index))
    try:
        selected = options[int(raw) - 1]
    except (ValueError, IndexError):
        raise typer.BadParameter(f"Invalid selection: {raw}") from None
    return selected[0]


def _prompt_model_for_profile(profile) -> str:
    from openharness.config.settings import (
        CLAUDE_MODEL_ALIAS_OPTIONS,
        display_model_setting,
        is_claude_family_provider,
    )

    current = display_model_setting(profile)
    if profile.allowed_models:
        if len(profile.allowed_models) == 1:
            return profile.allowed_models[0]
        options = [(value, value) for value in profile.allowed_models]
        return _select_from_menu("Choose a model setting:", options, default_value=current if current in profile.allowed_models else profile.allowed_models[0])
    if is_claude_family_provider(profile.provider):
        options = [(value, f"{label} - {description}") for value, label, description in CLAUDE_MODEL_ALIAS_OPTIONS]
        options.append(("__custom__", "Custom model ID"))
        selection = _select_from_menu(
            "Choose a model setting:",
            options,
            default_value=current if any(value == current for value, _, _ in CLAUDE_MODEL_ALIAS_OPTIONS) else "__custom__",
        )
        if selection != "__custom__":
            return selection
    return _text_prompt("Model", default=current).strip() or current


def _format_profile_choice_label(info: dict[str, object]) -> str:
    """Render a user-facing workflow label without leaking internal provider ids."""
    label = str(info["label"])
    state = "" if bool(info["configured"]) else f" ({info['auth_state']})"
    return f"{label}{state}"


def _styled_missing_suffix(info: dict[str, object]) -> tuple[str, str] | None:
    """Return a soft red missing-auth suffix for questionary titles."""
    if bool(info["configured"]):
        return None
    return (f" ({info['auth_state']})", "fg:#d3869b")


def _select_setup_workflow(
    statuses: dict[str, dict[str, object]],
    *,
    default_value: str | None = None,
) -> str:
    """Render the top-level `oh setup` workflow picker with richer hints."""
    hints = {
        "claude-api": ("Claude / Kimi / GLM / MiniMax", "fg:#7aa2f7"),
        "openai-compatible": ("OpenAI / OpenRouter", "fg:#9ece6a"),
    }

    if _can_use_questionary():
        import questionary

        choices = []
        for name, info in statuses.items():
            label = str(info["label"])
            hint = hints.get(name)
            missing = _styled_missing_suffix(info)
            if hint is None:
                if missing is None:
                    title = label
                else:
                    suffix, suffix_style = missing
                    title = [("", label), (suffix_style, suffix)]
            else:
                hint_text, hint_style = hint
                if missing is None:
                    title = [
                        ("", f"{label}  "),
                        (hint_style, hint_text),
                    ]
                else:
                    suffix, suffix_style = missing
                    title = [
                        ("", f"{label}  "),
                        (hint_style, hint_text),
                        ("", "  "),
                        (suffix_style, suffix.strip()),
                    ]
            choices.append(questionary.Choice(title=title, value=name, checked=(name == default_value)))

        result = questionary.select("Choose a provider workflow:", choices=choices, default=default_value).ask()
        if result is None:
            raise typer.Abort()
        return str(result)

    options: list[tuple[str, str]] = []
    for name, info in statuses.items():
        label = _format_profile_choice_label(info)
        hint = hints.get(name)
        if hint is not None:
            label = f"{label} ({hint[0]})"
        options.append((name, label))
    return _select_from_menu("Choose a provider workflow:", options, default_value=default_value)


def _default_credential_slot_for_profile(name: str, auth_source: str) -> str | None:
    from openharness.config.settings import auth_source_uses_api_key, builtin_provider_profile_names

    if name in builtin_provider_profile_names():
        return None
    if not auth_source_uses_api_key(auth_source):
        return None
    return name


def _prompt_api_key_for_profile(label: str) -> str:
    key = _secret_prompt(f"Enter API key for {label}").strip()
    if not key:
        raise typer.BadParameter("API key cannot be empty.")
    return key


def _configure_custom_profile_via_setup(manager) -> str:
    from openharness.config.settings import ProviderProfile, default_auth_source_for_provider

    family = _select_from_menu(
        "Choose a compatible API family:",
        [
            ("anthropic", "Anthropic-compatible"),
            ("openai", "OpenAI-compatible"),
        ],
        default_value="anthropic",
    )
    default_name = f"custom-{family}"
    name = _text_prompt("Profile name", default=default_name).strip()
    if not name:
        raise typer.BadParameter("Profile name cannot be empty.")
    label = _text_prompt("Display label", default=name).strip() or name
    base_url = _text_prompt("Base URL", default="").strip()
    if not base_url:
        raise typer.BadParameter("Base URL cannot be empty.")

    auth_source = default_auth_source_for_provider(family, family)
    model = _text_prompt("Default model", default="").strip()
    if not model:
        raise typer.BadParameter("Default model cannot be empty.")

    profile = ProviderProfile(
        label=label,
        provider=family,
        api_format=family,
        auth_source=auth_source,
        default_model=model,
        last_model=model,
        base_url=base_url,
        credential_slot=_default_credential_slot_for_profile(name, auth_source),
        allowed_models=[model],
    )
    manager.upsert_profile(name, profile)
    manager.store_profile_credential(name, "api_key", _prompt_api_key_for_profile(label))
    return name


def _ensure_preset_profile(
    manager,
    *,
    name: str,
    label: str,
    provider: str,
    api_format: str,
    auth_source: str,
    base_url: str | None,
    model: str,
    lock_model: bool,
) -> str:
    from openharness.config.settings import ProviderProfile

    existing = manager.list_profiles().get(name)
    profile = ProviderProfile(
        label=label,
        provider=provider,
        api_format=api_format,
        auth_source=auth_source,
        default_model=model,
        last_model=model,
        base_url=base_url,
        credential_slot=_default_credential_slot_for_profile(name, auth_source),
        allowed_models=[model] if lock_model else (existing.allowed_models if existing else []),
    )
    manager.upsert_profile(name, profile)
    return name


def _specialize_setup_target(manager, target: str) -> str:
    """Expand a top-level family choice into a concrete workflow profile."""
    from openharness.config.settings import default_auth_source_for_provider

    if target == "claude-api":
        choice = _select_from_menu(
            "Choose an Anthropic-compatible provider:",
            [
                ("claude-api", "Claude official"),
                ("kimi-anthropic", "Moonshot Kimi"),
                ("glm-anthropic", "Zhipu GLM"),
                ("minimax-anthropic", "MiniMax"),
            ],
            default_value="claude-api",
        )
        if choice == "claude-api":
            return choice
        defaults = {
            "kimi-anthropic": ("Kimi (Anthropic-compatible)", "https://api.moonshot.cn/anthropic", "kimi-k2.5"),
            "glm-anthropic": ("GLM (Anthropic-compatible)", "", "glm-4.5"),
            "minimax-anthropic": ("MiniMax (Anthropic-compatible)", "", "MiniMax-M2.7"),
        }
        label, suggested_base_url, suggested_model = defaults[choice]
        base_url = _text_prompt("Base URL", default=suggested_base_url).strip()
        if not base_url:
            raise typer.BadParameter("Base URL cannot be empty.")
        model = _text_prompt("Model", default=suggested_model).strip()
        if not model:
            raise typer.BadParameter("Model cannot be empty.")
        return _ensure_preset_profile(
            manager,
            name=choice,
            label=label,
            provider="anthropic",
            api_format="anthropic",
            auth_source=default_auth_source_for_provider("anthropic", "anthropic"),
            base_url=base_url,
            model=model,
            lock_model=True,
        )

    if target == "openai-compatible":
        choice = _select_from_menu(
            "Choose an OpenAI-compatible provider:",
            [
                ("openai-compatible", "OpenAI official"),
                ("openrouter", "OpenRouter"),
            ],
            default_value="openai-compatible",
        )
        if choice == "openai-compatible":
            return choice
        base_url = _text_prompt("Base URL", default="https://openrouter.ai/api/v1").strip()
        if not base_url:
            raise typer.BadParameter("Base URL cannot be empty.")
        model = _text_prompt("Default model", default="").strip()
        if not model:
            raise typer.BadParameter("Default model cannot be empty.")
        return _ensure_preset_profile(
            manager,
            name="openrouter",
            label="OpenRouter",
            provider="openai",
            api_format="openai",
            auth_source=default_auth_source_for_provider("openai", "openai"),
            base_url=base_url,
            model=model,
            lock_model=False,
        )

    return target


def _ensure_profile_auth(manager, profile_name: str) -> None:
    from openharness.auth.flows import ApiKeyFlow
    from openharness.config.settings import auth_source_provider_name, auth_source_uses_api_key

    profile = manager.list_profiles()[profile_name]
    if not auth_source_uses_api_key(profile.auth_source):
        _login_provider(auth_source_provider_name(profile.auth_source))
        return

    flow = ApiKeyFlow(
        provider=profile.provider,
        prompt_text=f"Enter API key for {profile.label}",
    )
    try:
        key = flow.run()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    manager.store_profile_credential(profile_name, "api_key", key)
    print(f"{profile.label} API key saved.", flush=True)


def _maybe_update_profile_auth(manager, profile_name: str) -> bool:
    """Ask whether to replace an already configured profile API key."""
    from openharness.config.settings import auth_source_uses_api_key

    profile = manager.list_profiles()[profile_name]
    if not auth_source_uses_api_key(profile.auth_source):
        return False
    if not _confirm_prompt(f"Update API key for {profile.label}?", default=False):
        return False
    _ensure_profile_auth(manager, profile_name)
    return True


def _maybe_update_default_model_for_provider(provider: str) -> None:
    """Keep the active model in-family after switching auth providers."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    profile_name = {
        "openai_codex": "codex",
        "anthropic_claude": "claude-subscription",
    }.get(provider)
    if profile_name is None:
        return
    profile = manager.list_profiles()[profile_name]
    model = profile.resolved_model.lower()
    target_model = None
    if provider == "openai_codex" and not model.startswith(("gpt-", "o1", "o3", "o4")):
        target_model = "gpt-5.4"
    elif provider == "anthropic_claude" and not model.startswith("claude-"):
        target_model = "sonnet"
    if not target_model:
        return
    manager.update_profile(profile_name, default_model=target_model, last_model=target_model)


def _bind_external_provider(provider: str) -> None:
    """Bind a provider to credentials managed by an external CLI."""
    from openharness.auth.external import default_binding_for_provider, load_external_credential
    from openharness.auth.storage import store_external_binding

    binding = default_binding_for_provider(provider)
    try:
        credential = load_external_credential(
            binding,
            refresh_if_needed=(provider == "anthropic_claude"),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        raise typer.Exit(1)

    profile_label = credential.profile_label or binding.profile_label
    store_external_binding(
        binding.__class__(
            provider=binding.provider,
            source_path=binding.source_path,
            source_kind=binding.source_kind,
            managed_by=binding.managed_by,
            profile_label=profile_label,
        )
    )

    _maybe_update_default_model_for_provider(provider)
    label = _PROVIDER_LABELS.get(provider, provider)
    profile_name = {
        "openai_codex": "codex",
        "anthropic_claude": "claude-subscription",
    }[provider]
    print(f"{label} bound from {credential.source_path}.", flush=True)
    print(f"Use `oh provider use {profile_name}` to activate it.", flush=True)


def _login_provider(provider: str) -> None:
    """Authenticate or bind the given provider."""
    from openharness.auth.flows import ApiKeyFlow
    from openharness.auth.manager import AuthManager
    from openharness.auth.storage import store_credential

    manager = AuthManager()

    if provider == "copilot":
        _run_copilot_login()
        return

    if provider in ("openai_codex", "anthropic_claude"):
        _bind_external_provider(provider)
        return

    if provider in ("anthropic", "openai", "dashscope", "bedrock", "vertex", "moonshot", "gemini", "minimax", "modelscope"):
        label = _PROVIDER_LABELS.get(provider, provider)
        flow = ApiKeyFlow(provider=provider, prompt_text=f"Enter your {label} API key")
        try:
            key = flow.run()
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise typer.Exit(1)
        store_credential(provider, "api_key", key)
        try:
            manager.store_credential(provider, "api_key", key)
        except Exception:
            pass
        print(f"{label} API key saved.", flush=True)
        return

    print(f"Unknown provider: {provider!r}. Known: {', '.join(_PROVIDER_LABELS)}", file=sys.stderr)
    raise typer.Exit(1)


@app.command("setup")
def setup_cmd(
    profile: str | None = typer.Argument(None, help="Provider profile name to configure"),
) -> None:
    """Unified setup flow: choose workflow, authenticate if needed, then set the model."""
    from openharness.auth.manager import AuthManager
    from openharness.config.settings import display_model_setting

    manager = AuthManager()
    statuses = manager.get_profile_statuses()
    if not statuses:
        print("No provider profiles available.", file=sys.stderr)
        raise typer.Exit(1)

    target = profile
    if target is None:
        target = _select_setup_workflow(
            statuses,
            default_value=manager.get_active_profile(),
        )

    target = _specialize_setup_target(manager, target)
    manager = AuthManager()
    statuses = manager.get_profile_statuses()

    if target not in statuses:
        print(f"Unknown provider profile: {target!r}", file=sys.stderr)
        raise typer.Exit(1)

    info = statuses[target]
    if not info["configured"]:
        source_label = _AUTH_SOURCE_LABELS.get(info["auth_source"], info["auth_source"])
        print(f"{info['label']} requires {source_label}.", flush=True)
        _ensure_profile_auth(manager, target)
        manager = AuthManager()
    else:
        if _maybe_update_profile_auth(manager, target):
            manager = AuthManager()

    profile_obj = manager.list_profiles()[target]
    model_setting = _prompt_model_for_profile(profile_obj)
    if model_setting.lower() == "default":
        manager.update_profile(target, last_model="")
    else:
        manager.update_profile(target, last_model=model_setting)
    manager.use_profile(target)

    updated = manager.list_profiles()[target]
    print(
        "Setup complete:\n"
        f"- profile: {target}\n"
        f"- provider: {updated.provider}\n"
        f"- auth_source: {updated.auth_source}\n"
        f"- model: {display_model_setting(updated)}",
        flush=True,
    )


@auth_app.command("login")
def auth_login(
    provider: Optional[str] = typer.Argument(None, help="Provider name (anthropic, openai, copilot, …)"),
) -> None:
    """Interactively authenticate with a provider.

    Run without arguments to choose a provider from a menu.
    Supported providers: anthropic, anthropic_claude, openai, openai_codex, copilot, dashscope, bedrock, vertex, moonshot, minimax, modelscope.
    """
    if provider is None:
        print("Select a provider to authenticate:", flush=True)
        labels = list(_PROVIDER_LABELS.items())
        for i, (name, label) in enumerate(labels, 1):
            print(f"  {i}. {label} [{name}]", flush=True)
        raw = typer.prompt("Enter number or provider name", default="1")
        try:
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(labels):
                provider = labels[idx][0]
            else:
                print("Invalid selection.", file=sys.stderr)
                raise typer.Exit(1)
        except ValueError:
            provider = raw.strip()

    provider = provider.lower()
    _login_provider(provider)


@auth_app.command("status")
def auth_status_cmd() -> None:
    """Show authentication source and provider profile status."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    auth_sources = manager.get_auth_source_statuses()
    profiles = manager.get_profile_statuses()

    print("Auth sources:")
    print(f"{'Source':<24} {'State':<14} {'Origin':<10} Active")
    print("-" * 60)
    for name, info in auth_sources.items():
        label = _AUTH_SOURCE_LABELS.get(name, name)
        active_str = "<-- active" if info["active"] else ""
        print(f"{label:<24} {info['state']:<14} {info['source']:<10} {active_str}")
        if info.get("detail"):
            print(f"  detail: {info['detail']}")

    print()
    print("Provider profiles:")
    print(f"{'Profile':<20} {'Provider':<18} {'Auth source':<22} {'State':<12} Active")
    print("-" * 92)
    for name, info in profiles.items():
        status_str = "ready" if info["configured"] else info.get("auth_state", "missing auth")
        active_str = "<-- active" if info["active"] else ""
        print(f"{name:<20} {info['provider']:<18} {info['auth_source']:<22} {status_str:<12} {active_str}")


@auth_app.command("logout")
def auth_logout(
    provider: Optional[str] = typer.Argument(None, help="Provider to log out (default: active provider)"),
) -> None:
    """Clear stored authentication for a provider."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    if provider is None:
        target = manager.get_active_profile()
        manager.clear_profile_credential(target)
        print(f"Authentication cleared for profile: {target}", flush=True)
        return
    manager.clear_credential(provider)
    print(f"Authentication cleared for provider: {provider}", flush=True)


@auth_app.command("switch")
def auth_switch(
    provider: str = typer.Argument(..., help="Auth source or profile to activate"),
) -> None:
    """Switch the auth source for the active profile, or use a profile by name."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    try:
        manager.switch_provider(provider)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"Switched auth/profile to: {provider}", flush=True)


# ---------------------------------------------------------------------------
# Copilot login helper (kept as a named function for reuse and backward compat)
# ---------------------------------------------------------------------------


def _run_copilot_login() -> None:
    """Run the GitHub Copilot device-code flow and persist the result."""
    from openharness.api.copilot_auth import save_copilot_auth
    from openharness.auth.flows import DeviceCodeFlow

    print("Select GitHub deployment type:", flush=True)
    print("  1. GitHub.com (public)", flush=True)
    print("  2. GitHub Enterprise (data residency / self-hosted)", flush=True)
    choice = typer.prompt("Enter choice", default="1")

    enterprise_url: str | None = None
    github_domain = "github.com"

    if choice.strip() == "2":
        raw_url = typer.prompt("Enter your GitHub Enterprise URL or domain (e.g. company.ghe.com)")
        domain = raw_url.replace("https://", "").replace("http://", "").rstrip("/")
        if not domain:
            print("Error: domain cannot be empty.", file=sys.stderr, flush=True)
            raise typer.Exit(1)
        enterprise_url = domain
        github_domain = domain

    print(flush=True)
    flow = DeviceCodeFlow(github_domain=github_domain, enterprise_url=enterprise_url)
    try:
        token = flow.run()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        raise typer.Exit(1)

    save_copilot_auth(token, enterprise_url=enterprise_url)
    print("GitHub Copilot authenticated successfully.", flush=True)
    if enterprise_url:
        print(f"  Enterprise domain: {enterprise_url}", flush=True)
    print(flush=True)
    print("To use Copilot as the provider, run:", flush=True)
    print("  oh provider use copilot", flush=True)


@auth_app.command("copilot-login")
def auth_copilot_login() -> None:
    """Authenticate with GitHub Copilot via device flow (alias for 'oh auth login copilot')."""
    _run_copilot_login()


@auth_app.command("codex-login")
def auth_codex_login() -> None:
    """Bind OpenHarness to a local Codex CLI subscription session."""
    _bind_external_provider("openai_codex")


@auth_app.command("claude-login")
def auth_claude_login() -> None:
    """Bind OpenHarness to a local Claude CLI subscription session."""
    _bind_external_provider("anthropic_claude")


@auth_app.command("copilot-logout")
def auth_copilot_logout() -> None:
    """Remove stored GitHub Copilot authentication."""
    from openharness.api.copilot_auth import clear_github_token

    clear_github_token()
    print("Copilot authentication cleared.")


# ---- provider subcommands ----


@provider_app.command("list")
def provider_list() -> None:
    """List configured provider profiles."""
    from openharness.auth.manager import AuthManager

    statuses = AuthManager().get_profile_statuses()
    for name, info in statuses.items():
        marker = "*" if info["active"] else " "
        configured = "ready" if info["configured"] else "missing auth"
        base = info["base_url"] or "(default)"
        print(f"{marker} {name}: {info['label']} [{configured}]")
        print(f"    auth={info['auth_source']} model={info['model']} base_url={base}")


@provider_app.command("use")
def provider_use(
    name: str = typer.Argument(..., help="Provider profile name"),
) -> None:
    """Activate a provider profile."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    try:
        manager.use_profile(name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"Activated provider profile: {name}", flush=True)


@provider_app.command("add")
def provider_add(
    name: str = typer.Argument(..., help="Provider profile name"),
    label: str = typer.Option(..., "--label", help="Display label"),
    provider: str = typer.Option(..., "--provider", help="Runtime provider id"),
    api_format: str = typer.Option(..., "--api-format", help="API format"),
    auth_source: str = typer.Option(..., "--auth-source", help="Auth source name"),
    model: str = typer.Option(..., "--model", help="Default model"),
    base_url: str | None = typer.Option(None, "--base-url", help="Optional base URL"),
    credential_slot: str | None = typer.Option(None, "--credential-slot", help="Optional profile-specific credential slot"),
    api_key: str | None = typer.Option(None, "--api-key", help="Set the profile API key"),
    allowed_models: list[str] | None = typer.Option(None, "--allowed-model", help="Allowed model values for this profile"),
    context_window_tokens: int | None = typer.Option(None, "--context-window-tokens", help="Optional context window override for auto-compact"),
    auto_compact_threshold_tokens: int | None = typer.Option(None, "--auto-compact-threshold-tokens", help="Optional explicit auto-compact threshold override"),
) -> None:
    """Create a provider profile."""
    from openharness.auth.manager import AuthManager
    from openharness.config.settings import ProviderProfile

    manager = AuthManager()
    manager.upsert_profile(
        name,
        ProviderProfile(
            label=label,
            provider=provider,
            api_format=api_format,
            auth_source=auth_source,
            default_model=model,
            last_model=model,
            base_url=base_url,
            credential_slot=credential_slot or _default_credential_slot_for_profile(name, auth_source),
            allowed_models=allowed_models or ([model] if credential_slot or _default_credential_slot_for_profile(name, auth_source) else []),
            context_window_tokens=context_window_tokens,
            auto_compact_threshold_tokens=auto_compact_threshold_tokens,
        ),
    )
    if api_key is not None:
        manager = AuthManager()
        manager.store_profile_credential(name, "api_key", api_key)
        print(f"Saved provider profile: {name} (API key set)", flush=True)
    else:
        print(f"Saved provider profile: {name}", flush=True)


@provider_app.command("edit")
def provider_edit(
    name: str = typer.Argument(..., help="Provider profile name"),
    label: str | None = typer.Option(None, "--label", help="Display label"),
    provider: str | None = typer.Option(None, "--provider", help="Runtime provider id"),
    api_format: str | None = typer.Option(None, "--api-format", help="API format"),
    auth_source: str | None = typer.Option(None, "--auth-source", help="Auth source name"),
    model: str | None = typer.Option(None, "--model", help="Default model"),
    base_url: str | None = typer.Option(None, "--base-url", help="Optional base URL"),
    credential_slot: str | None = typer.Option(None, "--credential-slot", help="Optional profile-specific credential slot"),
    api_key: str | None = typer.Option(None, "--api-key", help="Replace the profile API key"),
    allowed_models: list[str] | None = typer.Option(None, "--allowed-model", help="Allowed model values for this profile"),
    context_window_tokens: int | None = typer.Option(None, "--context-window-tokens", help="Optional context window override for auto-compact"),
    auto_compact_threshold_tokens: int | None = typer.Option(None, "--auto-compact-threshold-tokens", help="Optional explicit auto-compact threshold override"),
) -> None:
    """Edit a provider profile."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    try:
        manager.update_profile(
            name,
            label=label,
            provider=provider,
            api_format=api_format,
            auth_source=auth_source,
            default_model=model,
            last_model=model,
            base_url=base_url,
            credential_slot=credential_slot,
            allowed_models=allowed_models,
            context_window_tokens=context_window_tokens,
            auto_compact_threshold_tokens=auto_compact_threshold_tokens,
        )
        if api_key is not None:
            manager = AuthManager()
            manager.store_profile_credential(name, "api_key", api_key)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    if api_key is not None:
        print(f"Updated provider profile: {name} (API key replaced)", flush=True)
    else:
        print(f"Updated provider profile: {name}", flush=True)


@provider_app.command("remove")
def provider_remove(
    name: str = typer.Argument(..., help="Provider profile name"),
) -> None:
    """Remove a provider profile."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    try:
        manager.remove_profile(name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"Removed provider profile: {name}", flush=True)

# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
    # --- Session ---
    continue_session: bool = typer.Option(
        False,
        "--continue",
        "-c",
        help="Continue the most recent conversation in the current directory",
        rich_help_panel="Session",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        "-r",
        help="Resume a conversation by session ID, or open picker",
        rich_help_panel="Session",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Set a display name for this session",
        rich_help_panel="Session",
    ),
    # --- Model & Effort ---
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model alias (e.g. 'sonnet', 'opus') or full model ID",
        rich_help_panel="Model & Effort",
    ),
    effort: str | None = typer.Option(
        None,
        "--effort",
        help="Effort level for the session (low, medium, high, max)",
        rich_help_panel="Model & Effort",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Override verbose mode setting from config",
        rich_help_panel="Model & Effort",
    ),
    max_turns: int | None = typer.Option(
        None,
        "--max-turns",
        help="Maximum number of agentic turns (enforced by default in --print; optional cap for interactive mode)",
        rich_help_panel="Model & Effort",
    ),
    # --- Output ---
    print_mode: str | None = typer.Option(
        None,
        "--print",
        "-p",
        help="Print response and exit. Pass your prompt as the value: -p 'your prompt'",
        rich_help_panel="Output",
    ),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="Output format with --print: text (default), json, or stream-json",
        rich_help_panel="Output",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview resolved runtime config, skills, commands, and tools without executing the model or tools",
        rich_help_panel="Output",
    ),
    # --- Permissions ---
    permission_mode: str | None = typer.Option(
        None,
        "--permission-mode",
        help="Permission mode: default, plan, or full_auto",
        rich_help_panel="Permissions",
    ),
    dangerously_skip_permissions: bool = typer.Option(
        False,
        "--dangerously-skip-permissions",
        help="Bypass all permission checks (only for sandboxed environments)",
        rich_help_panel="Permissions",
    ),
    allowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--allowed-tools",
        help="Comma or space-separated list of tool names to allow",
        rich_help_panel="Permissions",
    ),
    disallowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--disallowed-tools",
        help="Comma or space-separated list of tool names to deny",
        rich_help_panel="Permissions",
    ),
    # --- System & Context ---
    system_prompt: str | None = typer.Option(
        None,
        "--system-prompt",
        "-s",
        help="Override the default system prompt",
        rich_help_panel="System & Context",
    ),
    append_system_prompt: str | None = typer.Option(
        None,
        "--append-system-prompt",
        help="Append text to the default system prompt",
        rich_help_panel="System & Context",
    ),
    settings_file: str | None = typer.Option(
        None,
        "--settings",
        help="Path to a JSON settings file or inline JSON string",
        rich_help_panel="System & Context",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Anthropic-compatible API base URL",
        rich_help_panel="System & Context",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key (overrides config and environment)",
        rich_help_panel="System & Context",
    ),
    bare: bool = typer.Option(
        False,
        "--bare",
        help="Minimal mode: skip hooks, plugins, MCP, and auto-discovery",
        rich_help_panel="System & Context",
    ),
    api_format: str | None = typer.Option(
        None,
        "--api-format",
        help="API format: 'anthropic' (default), 'openai' (DashScope, GitHub Models, etc.), or 'copilot' (GitHub Copilot)",
        rich_help_panel="System & Context",
    ),
    theme: str | None = typer.Option(
        None,
        "--theme",
        help="TUI theme: default, dark, minimal, cyberpunk, solarized, or custom name",
        rich_help_panel="System & Context",
    ),
    # --- Advanced ---
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging",
        rich_help_panel="Advanced",
    ),
    mcp_config: Optional[list[str]] = typer.Option(
        None,
        "--mcp-config",
        help="Load MCP servers from JSON files or strings",
        rich_help_panel="Advanced",
    ),
    cwd: str = typer.Option(
        str(Path.cwd()),
        "--cwd",
        help="Working directory for the session",
        hidden=True,
    ),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Run the structured backend host for the React terminal UI",
        hidden=True,
    ),
    task_worker: bool = typer.Option(
        False,
        "--task-worker",
        help="Run the stdin-driven headless worker loop used for background agent tasks",
        hidden=True,
    ),
) -> None:
    """Start an interactive session or run a single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    import asyncio
    import logging

    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
            stream=sys.stderr,
        )
        logging.getLogger("openharness").setLevel(logging.DEBUG)
    elif os.environ.get("OPENHARNESS_LOG_LEVEL"):
        lvl = getattr(logging, os.environ["OPENHARNESS_LOG_LEVEL"].upper(), logging.WARNING)
        logging.basicConfig(level=lvl, format="%(asctime)s [%(name)s] %(levelname)s %(message)s", stream=sys.stderr)

    if dangerously_skip_permissions:
        permission_mode = "full_auto"

    # Apply --theme override to settings
    if theme:
        from openharness.config.settings import load_settings, save_settings

        settings = load_settings()
        settings.theme = theme
        save_settings(settings)

    from openharness.ui.app import run_print_mode, run_repl, run_task_worker

    if dry_run and (continue_session or resume is not None):
        print("Error: --dry-run does not support --continue/--resume yet.", file=sys.stderr)
        raise typer.Exit(1)

    if dry_run:
        prompt = print_mode.strip() if print_mode is not None else None
        if print_mode is not None and not prompt:
            print("Error: -p/--print requires a prompt value, e.g. -p 'your prompt'", file=sys.stderr)
            raise typer.Exit(1)
        preview = _build_dry_run_preview(
            prompt=prompt,
            cwd=cwd,
            model=model,
            max_turns=max_turns,
            base_url=base_url,
            system_prompt=system_prompt,
            append_system_prompt=append_system_prompt,
            api_key=api_key,
            api_format=api_format,
            permission_mode=permission_mode,
        )
        effective_output_format = output_format or "text"
        if effective_output_format == "text":
            print(_format_dry_run_preview(preview))
        elif effective_output_format == "json":
            print(json.dumps(preview, ensure_ascii=False, indent=2))
        elif effective_output_format == "stream-json":
            print(json.dumps(preview, ensure_ascii=False))
        else:
            print(
                "Error: --dry-run only supports --output-format text, json, or stream-json",
                file=sys.stderr,
            )
            raise typer.Exit(1)
        return

    # Handle --continue and --resume flags
    if continue_session or resume is not None:
        from openharness.services.session_storage import (
            list_session_snapshots,
            load_session_by_id,
            load_session_snapshot,
        )

        session_data = None
        if continue_session:
            session_data = load_session_snapshot(cwd)
            if session_data is None:
                print("No previous session found in this directory.", file=sys.stderr)
                raise typer.Exit(1)
            print(f"Continuing session: {session_data.get('summary', '(untitled)')[:60]}")
        elif resume == "" or resume is None:
            # --resume with no value: show session picker
            sessions = list_session_snapshots(cwd, limit=10)
            if not sessions:
                print("No saved sessions found.", file=sys.stderr)
                raise typer.Exit(1)
            print("Saved sessions:")
            for i, s in enumerate(sessions, 1):
                print(f"  {i}. [{s['session_id']}] {s.get('summary', '?')[:50]} ({s['message_count']} msgs)")
            choice = typer.prompt("Enter session number or ID")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session_data = load_session_by_id(cwd, sessions[idx]["session_id"])
                else:
                    print("Invalid selection.", file=sys.stderr)
                    raise typer.Exit(1)
            except ValueError:
                session_data = load_session_by_id(cwd, choice)
            if session_data is None:
                print(f"Session not found: {choice}", file=sys.stderr)
                raise typer.Exit(1)
        else:
            session_data = load_session_by_id(cwd, resume)
            if session_data is None:
                print(f"Session not found: {resume}", file=sys.stderr)
                raise typer.Exit(1)

        # Pass restored session to the REPL
        asyncio.run(
            run_repl(
                prompt=None,
                cwd=cwd,
                model=session_data.get("model") or model,
                backend_only=backend_only,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
                restore_messages=session_data.get("messages"),
                restore_tool_metadata=session_data.get("tool_metadata"),
                permission_mode=permission_mode,
                api_format=api_format,
            )
        )
        return

    if print_mode is not None:
        prompt = print_mode.strip()
        if not prompt:
            print("Error: -p/--print requires a prompt value, e.g. -p 'your prompt'", file=sys.stderr)
            raise typer.Exit(1)
        asyncio.run(
            run_print_mode(
                prompt=prompt,
                output_format=output_format or "text",
                cwd=cwd,
                model=model,
                base_url=base_url,
                system_prompt=system_prompt,
                append_system_prompt=append_system_prompt,
                api_key=api_key,
                api_format=api_format,
                permission_mode=permission_mode,
                max_turns=max_turns,
            )
        )
        return

    if task_worker:
        asyncio.run(
            run_task_worker(
                cwd=cwd,
                model=model,
                max_turns=max_turns,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
                api_format=api_format,
                permission_mode=permission_mode,
            )
        )
        return

    asyncio.run(
        run_repl(
            prompt=None,
            cwd=cwd,
            model=model,
            max_turns=max_turns,
            backend_only=backend_only,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            api_format=api_format,
            permission_mode=permission_mode,
        )
    )
