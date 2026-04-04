"""Provider/auth capability helpers."""

from __future__ import annotations

from dataclasses import dataclass

from openharness.config.settings import Settings


@dataclass(frozen=True)
class ProviderInfo:
    """Resolved provider metadata for UI and diagnostics."""

    name: str
    auth_kind: str
    voice_supported: bool
    voice_reason: str


def detect_provider(settings: Settings) -> ProviderInfo:
    """Infer the active provider and rough capability set."""
    base_url = (settings.base_url or "").lower()
    model = settings.model.lower()
    if "moonshot" in base_url or model.startswith("kimi"):
        return ProviderInfo(
            name="moonshot-anthropic-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason="voice mode requires a Claude.ai-style authenticated voice backend",
        )
    if "dashscope" in base_url or model.startswith("qwen"):
        return ProviderInfo(
            name="dashscope-openai-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason="voice mode is not supported for DashScope providers",
        )
    if "models.inference.ai.azure.com" in base_url or "github" in base_url:
        return ProviderInfo(
            name="github-models-openai-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason="voice mode is not supported for GitHub Models",
        )
    if "bedrock" in base_url:
        return ProviderInfo(
            name="bedrock-compatible",
            auth_kind="aws",
            voice_supported=False,
            voice_reason="voice mode is not wired for Bedrock in this build",
        )
    if "vertex" in base_url or "aiplatform" in base_url:
        return ProviderInfo(
            name="vertex-compatible",
            auth_kind="gcp",
            voice_supported=False,
            voice_reason="voice mode is not wired for Vertex in this build",
        )
    if base_url:
        return ProviderInfo(
            name="anthropic-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason="voice mode currently requires a dedicated Claude.ai-style provider",
        )
    return ProviderInfo(
        name="anthropic",
        auth_kind="api_key",
        voice_supported=False,
        voice_reason="voice mode shell exists, but live voice auth/streaming is not configured in this build",
    )


def auth_status(settings: Settings) -> str:
    """Return a compact auth status string."""
    if settings.api_key:
        return "configured"
    return "missing"

