"""Provider/auth capability helpers."""

from __future__ import annotations

from dataclasses import dataclass

from openharness.auth.external import describe_external_binding
from openharness.auth.storage import load_external_binding
from openharness.api.registry import detect_provider_from_registry
from openharness.config.settings import Settings

_AUTH_KIND: dict[str, str] = {
    "anthropic": "api_key",
    "openai_compat": "api_key",
    "copilot": "oauth_device",
    "openai_codex": "external_oauth",
    "anthropic_claude": "external_oauth",
}

_VOICE_REASON: dict[str, str] = {
    "anthropic": (
        "voice mode shell exists, but live voice auth/streaming is not configured in this build"
    ),
    "openai_compat": "voice mode is not wired for OpenAI-compatible providers in this build",
    "copilot": "voice mode is not supported for GitHub Copilot",
    "openai_codex": "voice mode is not supported for Codex subscription auth",
    "anthropic_claude": "voice mode is not supported for Claude subscription auth",
}


@dataclass(frozen=True)
class ProviderInfo:
    """Resolved provider metadata for UI and diagnostics."""

    name: str
    auth_kind: str
    voice_supported: bool
    voice_reason: str


def detect_provider(settings: Settings) -> ProviderInfo:
    """Infer the active provider and rough capability set using the registry."""
    if settings.provider == "openai_codex":
        return ProviderInfo(
            name="openai-codex",
            auth_kind="external_oauth",
            voice_supported=False,
            voice_reason=_VOICE_REASON["openai_codex"],
        )
    if settings.provider == "anthropic_claude":
        return ProviderInfo(
            name="claude-subscription",
            auth_kind="external_oauth",
            voice_supported=False,
            voice_reason=_VOICE_REASON["anthropic_claude"],
        )
    if settings.api_format == "copilot":
        return ProviderInfo(
            name="github_copilot",
            auth_kind="oauth_device",
            voice_supported=False,
            voice_reason=_VOICE_REASON["copilot"],
        )

    spec = detect_provider_from_registry(
        model=settings.model,
        api_key=settings.api_key or None,
        base_url=settings.base_url,
    )

    if spec is not None:
        backend = spec.backend_type
        return ProviderInfo(
            name=spec.name,
            auth_kind=_AUTH_KIND.get(backend, "api_key"),
            voice_supported=False,
            voice_reason=_VOICE_REASON.get(backend, "voice mode is not supported for this provider"),
        )

    # Fallback: use api_format to pick a sensible default
    if settings.api_format == "openai":
        return ProviderInfo(
            name="openai-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason=_VOICE_REASON["openai_compat"],
        )
    return ProviderInfo(
        name="anthropic",
        auth_kind="api_key",
        voice_supported=False,
        voice_reason=_VOICE_REASON["anthropic"],
    )


def auth_status(settings: Settings) -> str:
    """Return a compact auth status string."""
    if settings.api_format == "copilot":
        from openharness.api.copilot_auth import load_copilot_auth

        auth_info = load_copilot_auth()
        if not auth_info:
            return "missing (run 'oh auth copilot-login')"
        if auth_info.enterprise_url:
            return f"configured (enterprise: {auth_info.enterprise_url})"
        return "configured"
    try:
        resolved = settings.resolve_auth()
    except ValueError as exc:
        if settings.provider == "openai_codex":
            return "missing (run 'oh auth codex-login')"
        if settings.provider == "anthropic_claude":
            binding = load_external_binding("anthropic_claude")
            if binding is not None:
                external_state = describe_external_binding(binding)
                if external_state.state != "missing":
                    return external_state.state
            message = str(exc)
            if "third-party" in message:
                return "invalid base_url"
            return "missing (run 'oh auth claude-login')"
        return "missing"
    if resolved.source.startswith("external:"):
        return f"configured ({resolved.source.removeprefix('external:')})"
    return "configured"
