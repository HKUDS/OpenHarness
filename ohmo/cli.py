"""CLI entry point for the ohmo personal-agent app."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import typer

from openharness.auth.manager import AuthManager
from openharness.config import load_settings

from ohmo.gateway.config import load_gateway_config, save_gateway_config
from ohmo.gateway.models import GatewayConfig
from ohmo.gateway.service import (
    OhmoGatewayService,
    gateway_status,
    start_gateway_process,
    stop_gateway_process,
)
from ohmo.memory import add_memory_entry, list_memory_files, remove_memory_entry
from ohmo.runtime import launch_ohmo_react_tui, run_ohmo_backend, run_ohmo_print_mode
from ohmo.session_storage import OhmoSessionBackend
from ohmo.workspace import (
    get_gateway_config_path,
    get_workspace_root,
    get_soul_path,
    get_state_path,
    get_user_path,
    initialize_workspace,
    workspace_health,
)


app = typer.Typer(
    name="ohmo",
    help="ohmo: a personal-agent app built on top of OpenHarness.",
    invoke_without_command=True,
    add_completion=False,
)
memory_app = typer.Typer(name="memory", help="Manage .ohmo memory")
soul_app = typer.Typer(name="soul", help="Inspect or edit soul.md")
user_app = typer.Typer(name="user", help="Inspect or edit user.md")
gateway_app = typer.Typer(name="gateway", help="Run the ohmo gateway")

app.add_typer(memory_app)
app.add_typer(soul_app)
app.add_typer(user_app)
app.add_typer(gateway_app)

_INTERACTIVE_CHANNELS = ("telegram", "slack", "discord", "feishu")
_WORKSPACE_HELP = "Path to the ohmo workspace (defaults to ~/.ohmo)"


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


def _confirm_prompt(message: str, *, default: bool = False) -> bool:
    """Ask for confirmation, preferring questionary in a real TTY."""
    if _can_use_questionary():
        import questionary

        result = questionary.confirm(message, default=default).ask()
        if result is None:
            raise typer.Abort()
        return bool(result)
    return typer.confirm(message, default=default)


def _text_prompt(message: str, *, default: str = "") -> str:
    """Prompt for text input, preferring questionary in a real TTY."""
    if _can_use_questionary():
        import questionary

        result = questionary.text(message, default=default).ask()
        if result is None:
            raise typer.Abort()
        return str(result)
    return typer.prompt(message, default=default)


def _select_from_menu(
    title: str,
    options: list[tuple[str, str]],
    *,
    default_value: str | None = None,
) -> str:
    """Render a simple numbered picker and return the selected value."""
    if _can_use_questionary():
        return _select_with_questionary(title, options, default_value=default_value)
    print(title)
    default_index = 1
    for index, (value, label) in enumerate(options, 1):
        marker = " (default)" if value == default_value else ""
        if value == default_value:
            default_index = index
        print(f"  {index}. {label}{marker}")
    raw = typer.prompt("Choose", default=str(default_index))
    try:
        selected = options[int(raw) - 1]
    except (ValueError, IndexError):
        raise typer.BadParameter(f"Invalid selection: {raw}") from None
    return selected[0]


def _format_provider_profile_label(info: dict[str, object]) -> str:
    label = str(info["label"])
    if bool(info["configured"]):
        return label
    return f"{label} (missing)"


def _prompt_provider_profile(workspace: str | Path) -> str:
    settings = load_settings()
    statuses = AuthManager(settings).get_profile_statuses()
    default_value = load_gateway_config(workspace).provider_profile
    hints = {
        "claude-api": ("Claude / Kimi / GLM / MiniMax", "fg:#7aa2f7"),
        "openai-compatible": ("OpenAI / OpenRouter", "fg:#9ece6a"),
    }

    if _can_use_questionary():
        import questionary

        choices = []
        for name, info in statuses.items():
            label = str(info["label"])
            missing = "" if bool(info["configured"]) else " (missing)"
            hint = hints.get(name)
            if hint is None:
                title = label if not missing else [("", label), ("fg:#d3869b", missing)]
            else:
                hint_text, hint_style = hint
                title = [
                    ("", f"{label}  "),
                    (hint_style, hint_text),
                ]
                if missing:
                    title.extend([("", "  "), ("fg:#d3869b", missing.strip())])
            choices.append(questionary.Choice(title=title, value=name, checked=(name == default_value)))
        result = questionary.select("Choose provider profile for ohmo:", choices=choices, default=default_value).ask()
        if result is None:
            raise typer.Abort()
        return str(result)

    options = []
    for name, info in statuses.items():
        label = _format_provider_profile_label(info)
        hint = hints.get(name)
        if hint is not None:
            label = f"{label} ({hint[0]})"
        options.append((name, label))
    return _select_from_menu(
        "Choose provider profile for ohmo:",
        options,
        default_value=default_value,
    )


def _prompt_channels(existing: GatewayConfig) -> tuple[list[str], dict[str, dict]]:
    enabled: list[str] = []
    configs: dict[str, dict] = {}
    print("Configure channels for ohmo gateway:")
    for channel in _INTERACTIVE_CHANNELS:
        current = channel in existing.enabled_channels
        prior = dict(existing.channel_configs.get(channel, {}))
        if current:
            enabled.append(channel)
            if not _confirm_prompt(f"Reconfigure {channel}?", default=False):
                configs[channel] = prior
                continue
        elif not _confirm_prompt(f"Enable {channel}?", default=False):
            continue
        else:
            enabled.append(channel)
        allow_from_raw = _text_prompt(
            f"{channel} allow_from (comma separated, '*' for everyone)",
            default=",".join(prior.get("allow_from", ["*"])) or "*",
        )
        allow_from = [item.strip() for item in allow_from_raw.split(",") if item.strip()] or ["*"]
        config: dict[str, object] = {"allow_from": allow_from}
        if channel == "telegram":
            config["token"] = _text_prompt(
                "Telegram bot token",
                default=str(prior.get("token", "")),
            )
            config["reply_to_message"] = _confirm_prompt(
                "Reply to the original Telegram message?",
                default=bool(prior.get("reply_to_message", True)),
            )
        elif channel == "slack":
            config["bot_token"] = _text_prompt(
                "Slack bot token",
                default=str(prior.get("bot_token", "")),
            )
            config["app_token"] = _text_prompt(
                "Slack app token",
                default=str(prior.get("app_token", "")),
            )
            config["mode"] = "socket"
            config["reply_in_thread"] = _confirm_prompt(
                "Reply in thread?",
                default=bool(prior.get("reply_in_thread", True)),
            )
            config["group_policy"] = _select_from_menu(
                "Slack group policy:",
                [
                    ("mention", "Mention only"),
                    ("open", "Always reply in channels"),
                    ("allowlist", "Only allow configured channels"),
                ],
                default_value=str(prior.get("group_policy", "mention")),
            )
        elif channel == "discord":
            config["token"] = _text_prompt(
                "Discord bot token",
                default=str(prior.get("token", "")),
            )
            config["gateway_url"] = _text_prompt(
                "Discord gateway URL",
                default=str(prior.get("gateway_url", "wss://gateway.discord.gg/?v=10&encoding=json")),
            )
            config["intents"] = int(
                _text_prompt(
                    "Discord intents bitmask",
                    default=str(prior.get("intents", 513)),
                )
            )
            config["group_policy"] = _select_from_menu(
                "Discord group policy:",
                [
                    ("mention", "Mention only"),
                    ("open", "Always reply in channels"),
                ],
                default_value=str(prior.get("group_policy", "mention")),
            )
        elif channel == "feishu":
            config["app_id"] = _text_prompt(
                "Feishu app id",
                default=str(prior.get("app_id", "")),
            )
            config["app_secret"] = _text_prompt(
                "Feishu app secret",
                default=str(prior.get("app_secret", "")),
            )
            config["encrypt_key"] = _text_prompt(
                "Feishu encrypt key",
                default=str(prior.get("encrypt_key", "")),
            )
            config["verification_token"] = _text_prompt(
                "Feishu verification token",
                default=str(prior.get("verification_token", "")),
            )
            config["react_emoji"] = _text_prompt(
                "Feishu reaction emoji",
                default=str(prior.get("react_emoji", "OK")),
            )
        configs[channel] = config
    return enabled, configs


def _run_gateway_config_wizard(workspace: str | Path) -> GatewayConfig:
    """Interactive flow for provider/channel setup."""
    existing = load_gateway_config(workspace)
    provider_profile = _prompt_provider_profile(workspace)
    enabled_channels, channel_configs = _prompt_channels(existing)
    send_progress = _confirm_prompt(
        "Send progress updates to channels?",
        default=existing.send_progress,
    )
    send_tool_hints = _confirm_prompt(
        "Send tool hints to channels?",
        default=existing.send_tool_hints,
    )
    config = existing.model_copy(
        update={
            "provider_profile": provider_profile,
            "enabled_channels": enabled_channels,
            "channel_configs": channel_configs,
            "send_progress": send_progress,
            "send_tool_hints": send_tool_hints,
        }
    )
    save_gateway_config(config, workspace)
    return config


def _print_gateway_config_summary(config: GatewayConfig) -> None:
    if config.enabled_channels:
        print(
            "Configured channels: "
            + ", ".join(config.enabled_channels)
            + f" | provider_profile={config.provider_profile}"
        )
    else:
        print(f"Configured provider_profile={config.provider_profile}; no channels enabled yet.")


def _maybe_restart_gateway(*, cwd: str | Path, workspace: str | Path) -> None:
    state = gateway_status(cwd, workspace)
    if not state.running:
        return
    if not _confirm_prompt("Gateway is running. Restart now to apply changes?", default=True):
        print("Configuration saved. Restart later with `ohmo gateway restart`.")
        return
    stop_gateway_process(cwd, workspace)
    pid = start_gateway_process(cwd, workspace)
    print(f"ohmo gateway restarted (pid={pid})")


def _configure_gateway_logging(workspace: str | Path | None = None) -> None:
    """Configure foreground gateway logging."""
    config = load_gateway_config(workspace)
    level_name = str(config.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        force=True,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    print_mode: str | None = typer.Option(None, "--print", "-p", help="Run a single prompt and exit"),
    model: str | None = typer.Option(None, "--model", help="Model override for this session"),
    profile: str | None = typer.Option(None, "--profile", help="Provider profile to use"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
    max_turns: int | None = typer.Option(None, "--max-turns", help="Override max turns"),
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Working directory"),
    backend_only: bool = typer.Option(False, "--backend-only", hidden=True),
    resume: str | None = typer.Option(None, "--resume", help="Resume an ohmo session by id"),
    continue_session: bool = typer.Option(False, "--continue", help="Continue the latest ohmo session"),
) -> None:
    """Launch the ohmo app or invoke a subcommand."""
    if ctx.invoked_subcommand is not None:
        return

    cwd_path = str(Path(cwd).resolve())
    workspace_root = initialize_workspace(workspace)
    backend = OhmoSessionBackend(workspace_root)
    restore_messages = None
    restore_tool_metadata = None
    if continue_session:
        latest = backend.load_latest(cwd_path)
        if latest is None:
            print("No previous ohmo session found in this directory.", file=sys.stderr)
            raise typer.Exit(1)
        restore_messages = latest.get("messages")
        restore_tool_metadata = latest.get("tool_metadata")
    elif resume:
        snapshot = backend.load_by_id(cwd_path, resume)
        if snapshot is None:
            print(f"ohmo session not found: {resume}", file=sys.stderr)
            raise typer.Exit(1)
        restore_messages = snapshot.get("messages")
        restore_tool_metadata = snapshot.get("tool_metadata")

    if backend_only:
        raise SystemExit(
            asyncio.run(
                run_ohmo_backend(
                    cwd=cwd_path,
                    workspace=workspace_root,
                    model=model,
                    max_turns=max_turns,
                    provider_profile=profile,
                    restore_messages=restore_messages,
                    restore_tool_metadata=restore_tool_metadata,
                )
            )
        )

    if print_mode is not None:
        raise SystemExit(
            asyncio.run(
                run_ohmo_print_mode(
                    prompt=print_mode,
                    cwd=cwd_path,
                    workspace=workspace_root,
                    model=model,
                    max_turns=max_turns,
                    provider_profile=profile,
                )
            )
        )

    raise SystemExit(
        asyncio.run(
            launch_ohmo_react_tui(
                cwd=cwd_path,
                workspace=workspace_root,
                model=model,
                max_turns=max_turns,
                provider_profile=profile,
            )
        )
    )


@app.command("init")
def init_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory (reserved for future project overrides)"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Run the provider/channel setup wizard when attached to a terminal",
    ),
) -> None:
    """Initialize the .ohmo workspace."""
    root_path = get_workspace_root(workspace)
    already_exists = root_path.exists()
    root = initialize_workspace(root_path)
    print(f"Initialized ohmo workspace at {root}")
    if already_exists:
        print("ohmo workspace already exists.")
        if not interactive:
            print("Use `ohmo config` to update provider and channel settings.")
            return
        if not _confirm_prompt("Open configuration now?", default=True):
            print("Use `ohmo config` when you want to change provider or channel settings.")
            return
    if interactive:
        config = _run_gateway_config_wizard(root)
        _print_gateway_config_summary(config)
        print(f"Saved gateway config to {get_gateway_config_path(root)}")


@app.command("config")
def config_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    """Configure provider profile and gateway channels."""
    cwd_path = str(Path(cwd).resolve())
    workspace_root = initialize_workspace(workspace)
    config = _run_gateway_config_wizard(workspace_root)
    _print_gateway_config_summary(config)
    print(f"Saved gateway config to {get_gateway_config_path(workspace_root)}")
    _maybe_restart_gateway(cwd=cwd_path, workspace=workspace_root)


@app.command("doctor")
def doctor_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    """Check .ohmo workspace and provider readiness."""
    cwd_path = str(Path(cwd).resolve())
    workspace_root = initialize_workspace(workspace)
    health = workspace_health(workspace_root)
    settings = load_settings()
    statuses = AuthManager(settings).get_profile_statuses()
    lines = ["ohmo doctor:"]
    for name, ok in health.items():
        lines.append(f"- {name}: {'ok' if ok else 'missing'}")
    lines.append(f"- project_cwd: {cwd_path}")
    lines.append(f"- workspace_root: {workspace_root}")
    lines.append(f"- workspace_state: {get_state_path(workspace_root)}")
    lines.append(f"- gateway_config: {get_gateway_config_path(workspace_root)}")
    lines.append("- available_profiles:")
    for name, info in statuses.items():
        lines.append(
            f"  - {name}: {info['label']} ({'configured' if info['configured'] else 'missing auth'})"
        )
    print("\n".join(lines))


@memory_app.command("list")
def memory_list_cmd(workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP)) -> None:
    for path in list_memory_files(workspace):
        print(path.name)


@memory_app.command("add")
def memory_add_cmd(
    title: str = typer.Argument(...),
    content: str = typer.Argument(...),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    path = add_memory_entry(workspace, title, content)
    print(f"Added memory entry {path.name}")


@memory_app.command("remove")
def memory_remove_cmd(
    name: str = typer.Argument(...),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    if remove_memory_entry(workspace, name):
        print(f"Removed memory entry {name}")
        return
    print(f"Memory entry not found: {name}", file=sys.stderr)
    raise typer.Exit(1)


def _show_or_edit(path: Path, set_text: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if set_text is not None:
        path.write_text(set_text.strip() + "\n", encoding="utf-8")
        print(f"Updated {path}")
        return
    if not path.exists():
        print(f"{path} does not exist yet.", file=sys.stderr)
        raise typer.Exit(1)
    print(path.read_text(encoding="utf-8"))


@soul_app.command("show")
def soul_show_cmd(workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP)) -> None:
    _show_or_edit(get_soul_path(workspace), None)


@soul_app.command("edit")
def soul_edit_cmd(
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
    set_text: str | None = typer.Option(None, "--set", help="Replace soul.md with this text"),
) -> None:
    _show_or_edit(get_soul_path(workspace), set_text)


@user_app.command("show")
def user_show_cmd(workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP)) -> None:
    _show_or_edit(get_user_path(workspace), None)


@user_app.command("edit")
def user_edit_cmd(
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
    set_text: str | None = typer.Option(None, "--set", help="Replace user.md with this text"),
) -> None:
    _show_or_edit(get_user_path(workspace), set_text)


@gateway_app.command("run")
def gateway_run_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    """Run the ohmo gateway in the foreground."""
    _configure_gateway_logging(workspace)
    service = OhmoGatewayService(cwd, workspace)
    raise SystemExit(asyncio.run(service.run_foreground()))


@gateway_app.command("start")
def gateway_start_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    pid = start_gateway_process(cwd, workspace)
    print(f"ohmo gateway started (pid={pid})")


@gateway_app.command("stop")
def gateway_stop_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    if stop_gateway_process(cwd, workspace):
        print("ohmo gateway stopped.")
        return
    print("ohmo gateway is not running.")


@gateway_app.command("restart")
def gateway_restart_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    stop_gateway_process(cwd, workspace)
    pid = start_gateway_process(cwd, workspace)
    print(f"ohmo gateway restarted (pid={pid})")


@gateway_app.command("status")
def gateway_status_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    state = gateway_status(cwd, workspace)
    print(state.model_dump_json(indent=2))
