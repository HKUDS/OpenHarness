"""Integration with external CLI-managed subscription credentials."""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openharness.auth.storage import ExternalAuthBinding
from openharness.utils.fs import atomic_write_text

CODEX_PROVIDER = "openai_codex"
CLAUDE_PROVIDER = "anthropic_claude"
CLAUDE_CODE_VERSION_FALLBACK = "2.1.92"
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_TOKEN_ENDPOINTS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
CLAUDE_COMMON_BETAS = (
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
)
CLAUDE_AI_OAUTH_SCOPES = (
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
)
CLAUDE_OAUTH_ONLY_BETAS = (
    "claude-code-20250219",
    "oauth-2025-04-20",
)
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"
_KEYCHAIN_BINDING_PREFIX = "keychain:"

_claude_code_version_cache: str | None = None
_claude_code_session_id: str | None = None


@dataclass(frozen=True)
class ExternalAuthCredential:
    """Normalized external credential used at runtime."""

    provider: str
    value: str
    auth_kind: str
    source_path: Path
    managed_by: str
    profile_label: str = ""
    refresh_token: str = ""
    expires_at_ms: int | None = None


@dataclass(frozen=True)
class ExternalAuthState:
    """Human-readable state for an external auth source."""

    configured: bool
    state: str
    source: str
    detail: str = ""


def default_binding_for_provider(provider: str) -> ExternalAuthBinding:
    """Return the default external auth source for *provider*."""
    if provider == CODEX_PROVIDER:
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        return ExternalAuthBinding(
            provider=provider,
            source_path=str(codex_home / "auth.json"),
            source_kind="codex_auth_json",
            managed_by="codex-cli",
            profile_label="Codex CLI",
        )
    if provider == CLAUDE_PROVIDER:
        configured_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
        if configured_dir:
            return ExternalAuthBinding(
                provider=provider,
                source_path=str(Path(configured_dir).expanduser() / ".credentials.json"),
                source_kind="claude_credentials_json",
                managed_by="claude-cli",
                profile_label="Claude CLI",
            )
        if platform.system() == "Darwin":
            return ExternalAuthBinding(
                provider=provider,
                source_path=f"{_KEYCHAIN_BINDING_PREFIX}{CLAUDE_KEYCHAIN_SERVICE}",
                source_kind="claude_credentials_keychain",
                managed_by="claude-cli",
                profile_label="Claude CLI",
            )
        claude_home = Path(os.environ.get("CLAUDE_HOME", "~/.claude")).expanduser()
        return ExternalAuthBinding(
            provider=provider,
            source_path=str(claude_home / ".credentials.json"),
            source_kind="claude_credentials_json",
            managed_by="claude-cli",
            profile_label="Claude CLI",
        )
    raise ValueError(f"Unsupported external auth provider: {provider}")


def load_external_credential(
    binding: ExternalAuthBinding,
    *,
    refresh_if_needed: bool = False,
) -> ExternalAuthCredential:
    """Read a runtime credential from an external auth binding."""
    if binding.provider == CODEX_PROVIDER:
        source_path = Path(binding.source_path).expanduser()
        if not source_path.exists():
            raise ValueError(f"External auth source not found: {source_path}")
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in external auth source: {source_path}") from exc
        return _load_codex_credential(payload, source_path, binding)
    if binding.provider == CLAUDE_PROVIDER:
        payload, source_path, keychain_service, keychain_account = _load_claude_payload(binding)
        return _load_claude_credential(
            payload,
            source_path,
            binding,
            refresh_if_needed=refresh_if_needed,
            keychain_service=keychain_service,
            keychain_account=keychain_account,
        )
    raise ValueError(f"Unsupported external auth provider: {binding.provider}")


def _load_codex_credential(
    payload: dict[str, Any],
    source_path: Path,
    binding: ExternalAuthBinding,
) -> ExternalAuthCredential:
    tokens = payload.get("tokens")
    access_token = ""
    refresh_token = ""
    if isinstance(tokens, dict):
        access_token = str(tokens.get("access_token", "") or "")
        refresh_token = str(tokens.get("refresh_token", "") or "")
    if not access_token:
        access_token = str(payload.get("OPENAI_API_KEY", "") or "")
    if not access_token:
        raise ValueError("Codex auth source does not contain an access token.")

    email = _decode_json_web_token_claim(access_token, ["https://api.openai.com/profile", "email"])
    expires_at_ms = _decode_jwt_expiry(access_token)
    return ExternalAuthCredential(
        provider=CODEX_PROVIDER,
        value=access_token,
        auth_kind="api_key",
        source_path=source_path,
        managed_by=binding.managed_by,
        profile_label=email or binding.profile_label,
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
    )


def _load_claude_credential(
    payload: dict[str, Any],
    source_path: Path,
    binding: ExternalAuthBinding,
    *,
    refresh_if_needed: bool,
    keychain_service: str | None = None,
    keychain_account: str | None = None,
) -> ExternalAuthCredential:
    claude_oauth = payload.get("claudeAiOauth")
    if not isinstance(claude_oauth, dict):
        raise ValueError("Claude auth source does not contain claudeAiOauth.")

    access_token = str(claude_oauth.get("accessToken", "") or "")
    refresh_token = str(claude_oauth.get("refreshToken", "") or "")
    expires_at_raw = claude_oauth.get("expiresAt")
    if not access_token:
        raise ValueError("Claude auth source does not contain an access token.")

    expires_at_ms = _coerce_int(expires_at_raw)
    credential = ExternalAuthCredential(
        provider=CLAUDE_PROVIDER,
        value=access_token,
        auth_kind="auth_token",
        source_path=source_path,
        managed_by=binding.managed_by,
        profile_label=keychain_account or binding.profile_label,
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
    )
    if refresh_if_needed and is_credential_expired(credential):
        if not refresh_token:
            raise ValueError(
                f"Claude credentials at {source_path} are expired and cannot be refreshed."
            )
        refreshed = refresh_claude_oauth_credential(refresh_token)
        if binding.source_kind == "claude_credentials_keychain":
            _write_claude_credentials_to_keychain(
                service=keychain_service or CLAUDE_KEYCHAIN_SERVICE,
                account=keychain_account or os.environ.get("USER", ""),
                payload=payload,
                access_token=str(refreshed["access_token"]),
                refresh_token=str(refreshed["refresh_token"]),
                expires_at_ms=int(refreshed["expires_at_ms"]),
            )
        else:
            write_claude_credentials(
                source_path,
                access_token=str(refreshed["access_token"]),
                refresh_token=str(refreshed["refresh_token"]),
                expires_at_ms=int(refreshed["expires_at_ms"]),
            )
        credential = ExternalAuthCredential(
            provider=CLAUDE_PROVIDER,
            value=str(refreshed["access_token"]),
            auth_kind="auth_token",
            source_path=source_path,
            managed_by=binding.managed_by,
            profile_label=keychain_account or binding.profile_label,
            refresh_token=str(refreshed["refresh_token"]),
            expires_at_ms=int(refreshed["expires_at_ms"]),
        )
    return credential


def _load_claude_payload(
    binding: ExternalAuthBinding,
) -> tuple[dict[str, Any], Path, str | None, str | None]:
    if binding.source_kind == "claude_credentials_keychain":
        return _read_claude_credentials_from_keychain(binding)

    source_path = Path(binding.source_path).expanduser()
    if not source_path.exists():
        raise ValueError(f"External auth source not found: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in external auth source: {source_path}") from exc
    return payload, source_path, None, None


def _read_claude_credentials_from_keychain(
    binding: ExternalAuthBinding,
) -> tuple[dict[str, Any], Path, str, str | None]:
    service = binding.source_path.removeprefix(_KEYCHAIN_BINDING_PREFIX).strip() or CLAUDE_KEYCHAIN_SERVICE
    try:
        raw_payload = subprocess.check_output(
            ["security", "find-generic-password", "-w", "-s", service],
            text=True,
        )
        metadata = subprocess.check_output(
            ["security", "find-generic-password", "-s", service],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Claude Keychain credential not found for service: {service}") from exc

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in Claude Keychain secret for service: {service}") from exc

    keychain_path = _extract_keychain_path(metadata) or (Path.home() / "Library/Keychains/login.keychain-db")
    account = _extract_keychain_attr(metadata, "acct")
    return payload, keychain_path, service, account


def _extract_keychain_path(metadata: str) -> Path | None:
    match = re.search(r'^keychain:\s+"([^"]+)"$', metadata, re.MULTILINE)
    if not match:
        return None
    return Path(match.group(1))


def _extract_keychain_attr(metadata: str, attr_name: str) -> str | None:
    match = re.search(rf'"{re.escape(attr_name)}"<blob>="([^"]*)"', metadata)
    if not match:
        return None
    return match.group(1)


def describe_external_binding(binding: ExternalAuthBinding) -> ExternalAuthState:
    """Return a human-readable state for an external auth binding."""
    source_path = Path(binding.source_path).expanduser()
    if binding.source_kind != "claude_credentials_keychain" and not source_path.exists():
        return ExternalAuthState(
            configured=False,
            state="missing",
            source="missing",
            detail=f"external auth source not found: {source_path}",
        )
    try:
        credential = load_external_credential(binding, refresh_if_needed=False)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            return ExternalAuthState(
                configured=False,
                state="missing",
                source="missing",
                detail=detail,
            )
        return ExternalAuthState(
            configured=False,
            state="invalid",
            source="external",
            detail=detail,
        )
    resolved_source = credential.source_path
    if binding.provider == CLAUDE_PROVIDER and is_credential_expired(credential):
        if credential.refresh_token:
            return ExternalAuthState(
                configured=True,
                state="refreshable",
                source="external",
                detail=f"expired token can be refreshed from {resolved_source}",
            )
        return ExternalAuthState(
            configured=False,
            state="expired",
            source="external",
            detail=f"expired token at {resolved_source}",
        )
    return ExternalAuthState(
        configured=True,
        state="configured",
        source="external",
        detail=str(resolved_source),
    )


def is_credential_expired(credential: ExternalAuthCredential, *, now_ms: int | None = None) -> bool:
    """Return True when the external credential is definitely expired."""
    if credential.expires_at_ms is None:
        return False
    if now_ms is None:
        import time

        now_ms = int(time.time() * 1000)
    return credential.expires_at_ms <= now_ms


def get_claude_code_version() -> str:
    """Return the locally installed Claude Code version or a fallback."""
    global _claude_code_version_cache
    if _claude_code_version_cache is not None:
        return _claude_code_version_cache
    for command in ("claude", "claude-code"):
        try:
            result = subprocess.run(
                [command, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            continue
        version = (result.stdout or "").strip().split(" ", 1)[0]
        if result.returncode == 0 and version and version[0].isdigit():
            _claude_code_version_cache = version
            return version
    _claude_code_version_cache = CLAUDE_CODE_VERSION_FALLBACK
    return _claude_code_version_cache


def get_claude_code_session_id() -> str:
    """Return a stable Claude Code-style session identifier for this process."""
    global _claude_code_session_id
    if _claude_code_session_id is None:
        _claude_code_session_id = str(uuid.uuid4())
    return _claude_code_session_id


def claude_oauth_betas() -> list[str]:
    """Return Claude OAuth betas as a list for SDK beta endpoints."""
    return list(CLAUDE_COMMON_BETAS + CLAUDE_OAUTH_ONLY_BETAS)


def claude_attribution_header() -> str:
    """Return the Claude Code billing attribution prefix used in system prompts."""
    version = get_claude_code_version()
    return (
        "x-anthropic-billing-header: "
        f"cc_version={version}; cc_entrypoint=cli;"
    )


def claude_oauth_headers() -> dict[str, str]:
    """Return Claude Code-style headers for subscription OAuth traffic."""
    all_betas = ",".join(claude_oauth_betas())
    return {
        "anthropic-beta": all_betas,
        "user-agent": f"claude-cli/{get_claude_code_version()} (external, cli)",
        "x-app": "cli",
        "X-Claude-Code-Session-Id": get_claude_code_session_id(),
    }


def refresh_claude_oauth_credential(
    refresh_token: str,
    *,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Refresh a Claude OAuth token without mutating local files."""
    if not refresh_token:
        raise ValueError("refresh_token is required")

    requested_scopes = list(scopes or CLAUDE_AI_OAUTH_SCOPES)
    payload = json.dumps(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "scope": " ".join(requested_scopes),
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"claude-cli/{get_claude_code_version()} (external, cli)",
    }
    last_error: Exception | None = None
    for endpoint in CLAUDE_OAUTH_TOKEN_ENDPOINTS:
        request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""
            if "invalid_grant" in body:
                last_error = ValueError(
                    "Claude OAuth refresh token is invalid or expired. "
                    "Run `claude auth login` to refresh the official Claude CLI "
                    "credentials, then run `oh auth claude-login` again."
                )
                continue
            detail = f"{exc.code} {exc.reason}"
            if body:
                detail = f"{detail}: {body}"
            last_error = ValueError(f"Claude OAuth refresh failed at {endpoint}: {detail}")
            continue
        except Exception as exc:
            last_error = exc
            continue
        access_token = str(result.get("access_token", "") or "")
        if not access_token:
            raise ValueError("Claude OAuth refresh response missing access_token")
        next_refresh = str(result.get("refresh_token", refresh_token) or refresh_token)
        expires_in = int(result.get("expires_in", 3600) or 3600)
        return {
            "access_token": access_token,
            "refresh_token": next_refresh,
            "expires_at_ms": int(time.time() * 1000) + expires_in * 1000,
            "scopes": result.get("scope"),
        }
    if last_error is not None:
        raise ValueError(f"Claude OAuth refresh failed: {last_error}") from last_error
    raise ValueError("Claude OAuth refresh failed")


def write_claude_credentials(
    source_path: Path,
    *,
    access_token: str,
    refresh_token: str,
    expires_at_ms: int,
) -> None:
    """Write refreshed Claude credentials back to the upstream credentials file."""
    existing: dict[str, Any] = {}
    if source_path.exists():
        try:
            existing = json.loads(source_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing["claudeAiOauth"] = _merge_claude_oauth_payload(
        existing.get("claudeAiOauth"),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
    )
    atomic_write_text(
        source_path,
        json.dumps(existing, indent=2) + "\n",
        mode=0o600,
    )


def _write_claude_credentials_to_keychain(
    *,
    service: str,
    account: str,
    payload: dict[str, Any],
    access_token: str,
    refresh_token: str,
    expires_at_ms: int,
) -> None:
    next_payload = dict(payload)
    next_payload["claudeAiOauth"] = _merge_claude_oauth_payload(
        payload.get("claudeAiOauth"),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
    )
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-s",
            service,
            "-a",
            account,
            "-w",
            json.dumps(next_payload, separators=(",", ":")),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _merge_claude_oauth_payload(
    previous: Any,
    *,
    access_token: str,
    refresh_token: str,
    expires_at_ms: int,
) -> dict[str, Any]:
    next_oauth: dict[str, Any] = {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresAt": expires_at_ms,
    }
    if isinstance(previous, dict):
        for key in ("scopes", "rateLimitTier", "subscriptionType"):
            if key in previous:
                next_oauth[key] = previous[key]
    return next_oauth


def is_third_party_anthropic_endpoint(base_url: str | None) -> bool:
    """Return True for non-Anthropic endpoints using Anthropic-compatible APIs."""
    if not base_url:
        return False
    normalized = base_url.rstrip("/").lower()
    return "anthropic.com" not in normalized and "claude.com" not in normalized


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.isdigit():
            return int(trimmed)
    return None


def _decode_jwt_expiry(token: str) -> int | None:
    exp = _decode_json_web_token_claim(token, ["exp"])
    if exp is None:
        return None
    if isinstance(exp, int):
        return exp * 1000
    if isinstance(exp, float):
        return int(exp * 1000)
    if isinstance(exp, str) and exp.strip().isdigit():
        return int(exp.strip()) * 1000
    return None


def _decode_json_web_token_claim(token: str, path: list[str]) -> Any | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        encoded = parts[1]
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        return None

    current: Any = payload
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current
