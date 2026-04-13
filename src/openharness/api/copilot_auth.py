"""GitHub Copilot OAuth device-flow authentication.

Flow:
1. Device code request  → user visits URL and enters code
2. Poll for OAuth token → get GitHub access token
3. Use token directly   → ``Authorization: Bearer <token>`` to Copilot API

Supports two deployment types:
- **github.com** — public GitHub, API at ``https://api.githubcopilot.com``
- **enterprise**  — GitHub Enterprise (data-residency / self-hosted),
  API at ``https://copilot-api.<domain>``

The GitHub OAuth token (and optional enterprise URL) are persisted to
``~/.openharness/copilot_auth.json``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from openharness.config.paths import get_config_dir
from openharness.utils.fs import atomic_write_text

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OAuth client ID registered by OpenCode for Copilot integrations.
COPILOT_CLIENT_ID = "Ov23li8tweQw6odWQebz"

COPILOT_DEFAULT_API_BASE = "https://api.githubcopilot.com"

# Safety margin added to each poll interval to avoid server-side rate limits.
_POLL_SAFETY_MARGIN = 3.0  # seconds

_AUTH_FILE_NAME = "copilot_auth.json"


def copilot_api_base(enterprise_url: str | None = None) -> str:
    """Return the Copilot API base URL.

    For public GitHub this is ``https://api.githubcopilot.com``.
    For enterprise it is ``https://copilot-api.<domain>``.
    """
    if enterprise_url:
        domain = enterprise_url.replace("https://", "").replace("http://", "").rstrip("/")
        return f"https://copilot-api.{domain}"
    return COPILOT_DEFAULT_API_BASE


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceCodeResponse:
    """Parsed response from the GitHub device-code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


@dataclass
class CopilotAuthInfo:
    """Persisted + runtime auth state for Copilot."""

    github_token: str
    enterprise_url: str | None = None

    @property
    def api_base(self) -> str:
        return copilot_api_base(self.enterprise_url)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _auth_file_path() -> Path:
    return get_config_dir() / _AUTH_FILE_NAME


def save_copilot_auth(token: str, *, enterprise_url: str | None = None) -> None:
    """Persist the GitHub OAuth token (and optional enterprise URL) to disk."""
    path = _auth_file_path()
    payload: dict[str, Any] = {"github_token": token}
    if enterprise_url:
        payload["enterprise_url"] = enterprise_url
    atomic_write_text(
        path,
        json.dumps(payload, indent=2) + "\n",
        mode=0o600,
    )
    log.info("Copilot auth saved to %s", path)


def load_copilot_auth() -> CopilotAuthInfo | None:
    """Load the persisted Copilot auth, or return None."""
    path = _auth_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        token = data.get("github_token")
        if not token:
            return None
        return CopilotAuthInfo(
            github_token=token,
            enterprise_url=data.get("enterprise_url"),
        )
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        log.warning("Failed to read Copilot auth file: %s", exc)
        return None


# Keep backward-compatible aliases used by CLI and tests.
save_github_token = save_copilot_auth


def load_github_token() -> str | None:
    """Load just the persisted GitHub OAuth token, or return None."""
    info = load_copilot_auth()
    return info.github_token if info else None


def clear_github_token() -> None:
    """Remove persisted Copilot auth."""
    path = _auth_file_path()
    if path.exists():
        path.unlink()
        log.info("Copilot auth cleared.")


# ---------------------------------------------------------------------------
# OAuth device flow (synchronous – called from CLI)
# ---------------------------------------------------------------------------


def request_device_code(
    *,
    client_id: str = COPILOT_CLIENT_ID,
    github_domain: str = "github.com",
) -> DeviceCodeResponse:
    """Start the OAuth device flow and return the device/user codes."""
    url = f"https://{github_domain}/login/device/code"
    resp = httpx.post(
        url,
        json={"client_id": client_id, "scope": "read:user"},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return DeviceCodeResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        interval=data.get("interval", 5),
        expires_in=data.get("expires_in", 900),
    )


def poll_for_access_token(
    device_code: str,
    interval: int,
    *,
    client_id: str = COPILOT_CLIENT_ID,
    github_domain: str = "github.com",
    timeout: float = 900,
    progress_callback: Any | None = None,
) -> str:
    """Poll GitHub until the user authorises, returning the OAuth access token.

    *progress_callback*, if provided, is called with ``(poll_number, elapsed_seconds)``
    before each poll so callers can show progress feedback.

    Raises ``RuntimeError`` on expiry or unexpected error.
    """
    url = f"https://{github_domain}/login/oauth/access_token"
    poll_interval = float(interval)
    deadline = time.monotonic() + timeout
    start = time.monotonic()
    poll_count = 0

    while time.monotonic() < deadline:
        time.sleep(poll_interval + _POLL_SAFETY_MARGIN)
        poll_count += 1
        if progress_callback is not None:
            progress_callback(poll_count, time.monotonic() - start)
        resp = httpx.post(
            url,
            json={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        if "access_token" in data:
            return data["access_token"]

        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            server_interval = data.get("interval")
            if isinstance(server_interval, (int, float)) and server_interval > 0:
                poll_interval = float(server_interval)
            else:
                poll_interval += 5.0
            continue
        # Any other error is terminal.
        desc = data.get("error_description", error)
        raise RuntimeError(f"OAuth device flow failed: {desc}")

    raise RuntimeError("OAuth device flow timed out waiting for user authorisation.")
