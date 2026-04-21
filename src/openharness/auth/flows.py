"""Authentication flows for various provider types.

Each flow is a self-contained class with a single ``run()`` method that
performs the interactive authentication and returns the obtained credential.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any

log = logging.getLogger(__name__)


class AuthFlow(ABC):
    """Abstract base for all auth flows."""

    @abstractmethod
    def run(self) -> str:
        """Execute the flow and return the obtained credential value."""


# ---------------------------------------------------------------------------
# ApiKeyFlow — directly prompt for and store an API key
# ---------------------------------------------------------------------------


class ApiKeyFlow(AuthFlow):
    """Prompt the user for an API key and persist it via :mod:`openharness.auth.storage`."""

    def __init__(self, provider: str, prompt_text: str | None = None) -> None:
        self.provider = provider
        self.prompt_text = prompt_text or f"Enter your {provider} API key"

    def run(self) -> str:
        import getpass

        key = getpass.getpass(f"{self.prompt_text}: ").strip()
        if not key:
            raise ValueError("API key cannot be empty.")
        return key


# ---------------------------------------------------------------------------
# DeviceCodeFlow — GitHub OAuth device-code flow (refactored from copilot_auth)
# ---------------------------------------------------------------------------


class DeviceCodeFlow(AuthFlow):
    """GitHub OAuth device-code flow.

    This is a refactored version of the logic previously inlined in
    ``cli.py`` (``auth_copilot_login``).  It can be used for any GitHub
    OAuth app that supports the device-code grant.
    """

    def __init__(
        self,
        client_id: str | None = None,
        github_domain: str = "github.com",
        enterprise_url: str | None = None,
        *,
        progress_callback: Any | None = None,
    ) -> None:
        from openharness.api.copilot_auth import COPILOT_CLIENT_ID

        self.client_id = client_id or COPILOT_CLIENT_ID
        self.enterprise_url = enterprise_url
        self.github_domain = github_domain if not enterprise_url else enterprise_url
        self.progress_callback = progress_callback

    @staticmethod
    def _try_open_browser(url: str) -> bool:
        """Attempt to open *url* in the default browser; return True if likely succeeded."""
        try:
            plat = platform.system()
            if plat == "Darwin":
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            if plat == "Windows":
                subprocess.Popen(
                    ["start", "", url],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            # Linux / WSL
            proc = subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=2)
                return proc.returncode == 0
            except subprocess.TimeoutExpired:
                return True
        except Exception:
            return False

    def run(self) -> str:
        from openharness.api.copilot_auth import poll_for_access_token, request_device_code

        print("Starting GitHub device flow...", flush=True)
        dc = request_device_code(client_id=self.client_id, github_domain=self.github_domain)

        print(flush=True)
        print(f"  Open: {dc.verification_uri}", flush=True)
        print(f"  Code: {dc.user_code}", flush=True)
        print(flush=True)

        opened = self._try_open_browser(dc.verification_uri)
        if opened:
            print("(Browser opened — enter the code shown above.)", flush=True)
        else:
            print("Open the URL above in your browser and enter the code.", flush=True)
        print(flush=True)

        if self.progress_callback is None:

            def _default_progress(poll_num: int, elapsed: float) -> None:
                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                print(f"\r  Polling... ({mins}m {secs:02d}s elapsed)", end="", flush=True)

            self.progress_callback = _default_progress

        print("Waiting for authorisation...", flush=True)
        try:
            token = poll_for_access_token(
                dc.device_code,
                dc.interval,
                client_id=self.client_id,
                github_domain=self.github_domain,
                progress_callback=self.progress_callback,
            )
        except RuntimeError as exc:
            print(flush=True)
            print(f"Error: {exc}", file=sys.stderr, flush=True)
            raise

        print(flush=True)
        return token


# ---------------------------------------------------------------------------
# BrowserFlow — open a URL and wait for the user to complete auth
# ---------------------------------------------------------------------------


class BrowserFlow(AuthFlow):
    """Open a browser URL and wait for the user to complete authentication.

    After the user completes the browser flow they are expected to paste
    back a token/code — this simple implementation prompts for that value.
    """

    def __init__(self, auth_url: str, prompt_text: str = "Paste the token from your browser") -> None:
        self.auth_url = auth_url
        self.prompt_text = prompt_text

    def run(self) -> str:
        import getpass

        print(f"Opening browser for authentication: {self.auth_url}", flush=True)
        opened = DeviceCodeFlow._try_open_browser(self.auth_url)
        if not opened:
            print(f"Could not open browser automatically. Visit: {self.auth_url}", flush=True)

        token = getpass.getpass(f"{self.prompt_text}: ").strip()
        if not token:
            raise ValueError("No token provided.")
        return token
