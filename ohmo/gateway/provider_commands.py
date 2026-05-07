"""ohmo gateway-scoped provider and model commands."""

from __future__ import annotations

from pathlib import Path

from openharness.auth.manager import AuthManager
from openharness.config import load_settings

from ohmo.gateway.config import load_gateway_config, save_gateway_config


def handle_gateway_provider_command(args: str, *, workspace: str | Path | None) -> tuple[str, bool]:
    """Handle ``/provider`` against the ohmo gateway config."""
    tokens = args.split()
    statuses = AuthManager(load_settings()).get_profile_statuses()
    config = load_gateway_config(workspace)
    active = config.provider_profile
    if not tokens or tokens[0] == "show":
        info = statuses.get(active)
        if info is None:
            return f"ohmo gateway provider_profile: {active}\nStatus: unknown profile", False
        return (
            f"ohmo gateway provider_profile: {active}\n"
            f"Label: {info['label']}\n"
            f"Configured: {'yes' if info['configured'] else 'no'}\n"
            f"Base URL: {info['base_url'] or '(default)'}\n"
            f"Model: {info['model']}",
            False,
        )
    if tokens[0] == "list":
        lines = ["ohmo gateway provider profiles:"]
        for name, info in statuses.items():
            marker = "*" if name == active else " "
            configured = "ready" if info["configured"] else "missing auth"
            lines.append(f"{marker} {name} [{configured}] {info['label']} -> {info['model']}")
        return "\n".join(lines), False
    target = tokens[1] if tokens[0] == "use" and len(tokens) == 2 else (tokens[0] if len(tokens) == 1 else None)
    if target is None:
        return "Usage: /provider [show|list|PROFILE]", False
    if target not in statuses:
        return f"Unknown provider profile: {target}", False
    if target == active:
        return f"ohmo gateway already uses provider_profile={target}.", False
    save_gateway_config(config.model_copy(update={"provider_profile": target}), workspace)
    info = statuses[target]
    configured = "ready" if info["configured"] else "missing auth"
    return (
        f"ohmo gateway provider_profile set to {target} ({info['label']}, {configured}).\n"
        "Refreshing the current ohmo runtime to apply it.",
        True,
    )


def handle_gateway_model_command(args: str, *, workspace: str | Path | None) -> tuple[str, bool]:
    """Handle ``/model`` against the profile selected by ohmo gateway."""
    settings = load_settings()
    manager = AuthManager(settings)
    config = load_gateway_config(workspace)
    profile_name = config.provider_profile
    profiles = manager.list_profiles()
    profile = profiles.get(profile_name)
    if profile is None:
        return f"ohmo gateway provider_profile is unknown: {profile_name}", False

    tokens = args.split(maxsplit=1)
    if not tokens or tokens[0] == "show":
        return _format_model_status(profile_name, profile), False
    if tokens[0] == "list":
        if profile.allowed_models:
            return (
                f"Switchable models for ohmo gateway profile '{profile_name}':\n"
                + "\n".join(f"- {model}" for model in profile.allowed_models)
            ), False
        return (
            f"Profile '{profile_name}' has no pinned model list. "
            "Any model value is accepted. Use /model add MODEL to pin one."
        ), False
    if tokens[0] == "add" and len(tokens) == 2:
        model_name = tokens[1].strip()
        if not model_name:
            return "Usage: /model add MODEL", False
        manager.update_profile(profile_name, allowed_models=_dedupe([*_seed_models(profile), model_name]))
        return f"Added model '{model_name}' to ohmo gateway profile '{profile_name}'.", False
    if tokens[0] == "add":
        return "Usage: /model add MODEL", False
    if tokens[0] in {"remove", "rm"} and len(tokens) == 2:
        model_name = tokens[1].strip()
        models = [model for model in _dedupe(profile.allowed_models) if model != model_name]
        if len(models) == len(_dedupe(profile.allowed_models)):
            return f"Model '{model_name}' is not pinned for ohmo gateway profile '{profile_name}'.", False
        reset_current = (profile.last_model or "").strip() == model_name
        manager.update_profile(profile_name, allowed_models=models, last_model="" if reset_current else None)
        return f"Removed model '{model_name}' from ohmo gateway profile '{profile_name}'.", True
    if tokens[0] in {"remove", "rm"}:
        return "Usage: /model remove MODEL", False
    if tokens[0] == "clear":
        manager.update_profile(profile_name, allowed_models=[])
        return f"Cleared pinned models for ohmo gateway profile '{profile_name}'.", False
    model_name = tokens[1].strip() if tokens[0] == "set" and len(tokens) == 2 else args.strip()
    if not model_name:
        return "Usage: /model [show|list|add MODEL|remove MODEL|clear|MODEL]", False
    if profile.allowed_models and model_name.lower() != "default" and model_name not in profile.allowed_models:
        allowed = ", ".join(profile.allowed_models)
        return f"Model '{model_name}' is not allowed for ohmo gateway profile '{profile_name}'. Allowed models: {allowed}", False
    if model_name.lower() == "default":
        manager.update_profile(profile_name, last_model="")
        return f"ohmo gateway model reset to default for profile '{profile_name}'. Refreshing runtime to apply it.", True
    manager.update_profile(profile_name, last_model=model_name)
    return f"ohmo gateway model set to {model_name} for profile '{profile_name}'. Refreshing runtime to apply it.", True


def _format_model_status(profile_name, profile) -> str:
    lines = [
        f"ohmo gateway model: {profile.resolved_model}",
        f"Profile: {profile_name}",
    ]
    if profile.allowed_models:
        lines.append("Available models:")
        lines.extend(f"- {model}" for model in profile.allowed_models)
    else:
        lines.append("Available models: unrestricted for this profile")
        lines.append("Use /model add MODEL to pin switchable models.")
    return "\n".join(lines)


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        model = str(value).strip()
        if model and model not in seen:
            result.append(model)
            seen.add(model)
    return result


def _seed_models(profile) -> list[str]:
    return _dedupe([*profile.allowed_models, profile.resolved_model])
