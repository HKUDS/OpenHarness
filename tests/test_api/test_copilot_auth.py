"""Tests for GitHub Copilot authentication and token management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from openharness.api.copilot_auth import (
    COPILOT_DEFAULT_API_BASE,
    CopilotAuthInfo,
    DeviceCodeResponse,
    clear_github_token,
    copilot_api_base,
    load_copilot_auth,
    load_github_token,
    poll_for_access_token,
    request_device_code,
    save_copilot_auth,
)


# ---------------------------------------------------------------------------
# Fake HTTP helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeHttpResponse:
    """Minimal stand-in for an ``httpx.Response``."""

    status_code: int = 200
    _json: dict[str, Any] | None = None

    def json(self) -> dict[str, Any]:
        assert self._json is not None
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# CopilotAuthInfo / copilot_api_base tests
# ---------------------------------------------------------------------------


class TestCopilotAuthInfo:
    """Test CopilotAuthInfo dataclass and api_base property."""

    def test_api_base_public(self):
        info = CopilotAuthInfo(github_token="ghu_abc")
        assert info.api_base == COPILOT_DEFAULT_API_BASE

    def test_api_base_enterprise(self):
        info = CopilotAuthInfo(github_token="ghu_abc", enterprise_url="company.ghe.com")
        assert info.api_base == "https://copilot-api.company.ghe.com"

    def test_enterprise_url_defaults_to_none(self):
        info = CopilotAuthInfo(github_token="ghu_abc")
        assert info.enterprise_url is None


class TestCopilotApiBase:
    """Test copilot_api_base() helper."""

    def test_public_github(self):
        assert copilot_api_base() == COPILOT_DEFAULT_API_BASE

    def test_none_enterprise(self):
        assert copilot_api_base(None) == COPILOT_DEFAULT_API_BASE

    def test_enterprise_domain(self):
        assert copilot_api_base("company.ghe.com") == "https://copilot-api.company.ghe.com"

    def test_enterprise_with_https_prefix(self):
        assert copilot_api_base("https://company.ghe.com") == "https://copilot-api.company.ghe.com"

    def test_enterprise_with_trailing_slash(self):
        assert copilot_api_base("company.ghe.com/") == "https://copilot-api.company.ghe.com"


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestTokenPersistence:
    """Round-trip save / load / clear of the Copilot auth file."""

    def test_save_and_load_round_trip(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_abc123")
        info = load_copilot_auth()
        assert info is not None
        assert info.github_token == "gho_abc123"
        assert info.enterprise_url is None

    def test_save_and_load_with_enterprise_url(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_ent_token", enterprise_url="company.ghe.com")
        info = load_copilot_auth()
        assert info is not None
        assert info.github_token == "gho_ent_token"
        assert info.enterprise_url == "company.ghe.com"

    def test_load_returns_none_when_file_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        assert load_copilot_auth() is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path, monkeypatch):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir(parents=True)
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(cfg_dir))
        (cfg_dir / "copilot_auth.json").write_text("NOT VALID JSON{{{", encoding="utf-8")
        assert load_copilot_auth() is None

    def test_clear_removes_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_xyz")
        clear_github_token()
        assert load_copilot_auth() is None

    def test_clear_noop_when_no_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        # Should not raise
        clear_github_token()

    def test_backward_compat_load_github_token(self, tmp_path: Path, monkeypatch):
        """load_github_token() should return just the token string."""
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_compat")
        assert load_github_token() == "gho_compat"

    def test_backward_compat_load_github_token_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        assert load_github_token() is None


# ---------------------------------------------------------------------------
# request_device_code tests
# ---------------------------------------------------------------------------


class TestRequestDeviceCode:
    """Verify device-code request delegates to httpx.post correctly."""

    def test_request_device_code_happy_path(self, monkeypatch):
        def fake_post(*args: Any, **kwargs: Any) -> FakeHttpResponse:
            return FakeHttpResponse(
                _json={
                    "device_code": "dc_123",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 5,
                    "expires_in": 900,
                }
            )

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        result = request_device_code()

        assert isinstance(result, DeviceCodeResponse)
        assert result.device_code == "dc_123"
        assert result.user_code == "ABCD-1234"
        assert result.verification_uri == "https://github.com/login/device"
        assert result.interval == 5
        assert result.expires_in == 900

    def test_request_device_code_enterprise(self, monkeypatch):
        """Enterprise domain should use the enterprise device-code URL."""
        captured_urls: list[str] = []

        def fake_post(url: str, **kwargs: Any) -> FakeHttpResponse:
            captured_urls.append(url)
            return FakeHttpResponse(
                _json={
                    "device_code": "dc_ent",
                    "user_code": "ENT-1234",
                    "verification_uri": "https://company.ghe.com/login/device",
                    "interval": 5,
                    "expires_in": 900,
                }
            )

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        result = request_device_code(github_domain="company.ghe.com")

        assert result.device_code == "dc_ent"
        assert captured_urls[0] == "https://company.ghe.com/login/device/code"


# ---------------------------------------------------------------------------
# poll_for_access_token tests
# ---------------------------------------------------------------------------


class TestPollForAccessToken:
    """Verify the OAuth device-flow polling loop."""

    def test_returns_token_after_pending(self, monkeypatch):
        """First call returns pending, second returns access_token."""
        call_count = 0

        def fake_post(*args: Any, **kwargs: Any) -> FakeHttpResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeHttpResponse(_json={"error": "authorization_pending"})
            return FakeHttpResponse(_json={"access_token": "gho_good_token"})

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        monkeypatch.setattr("openharness.api.copilot_auth.time.sleep", lambda _: None)

        token = poll_for_access_token("dc_test", interval=0, timeout=60)
        assert token == "gho_good_token"
        assert call_count == 2

    def test_slow_down_increases_interval(self, monkeypatch):
        """A ``slow_down`` response should adopt the server-provided interval."""
        recorded_sleeps: list[float] = []
        call_count = 0

        def fake_post(*args: Any, **kwargs: Any) -> FakeHttpResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeHttpResponse(_json={"error": "slow_down", "interval": 10})
            return FakeHttpResponse(_json={"access_token": "gho_token"})

        def fake_sleep(seconds: float) -> None:
            recorded_sleeps.append(seconds)

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        monkeypatch.setattr("openharness.api.copilot_auth.time.sleep", fake_sleep)

        token = poll_for_access_token("dc_sd", interval=5, timeout=120)
        assert token == "gho_token"
        # After slow_down with interval=10, the next sleep should use 10 + safety margin
        # First sleep uses original interval (5 + 3.0 = 8.0)
        # Second sleep uses the new interval from slow_down (10 + 3.0 = 13.0)
        assert recorded_sleeps[1] == pytest.approx(13.0)

    def test_timeout_raises_runtime_error(self, monkeypatch):
        """Polling beyond the deadline should raise RuntimeError."""
        # Make monotonic() return values past the deadline immediately
        monotonic_calls = iter([0.0, 0.0, 999.0])

        def fake_monotonic() -> float:
            return next(monotonic_calls)

        def fake_post(*args: Any, **kwargs: Any) -> FakeHttpResponse:
            return FakeHttpResponse(_json={"error": "authorization_pending"})

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        monkeypatch.setattr("openharness.api.copilot_auth.time.sleep", lambda _: None)
        monkeypatch.setattr("openharness.api.copilot_auth.time.monotonic", fake_monotonic)

        with pytest.raises(RuntimeError, match="timed out"):
            poll_for_access_token("dc_timeout", interval=0, timeout=10)

    def test_terminal_error_raises(self, monkeypatch):
        """A non-retryable error should raise RuntimeError."""

        def fake_post(*args: Any, **kwargs: Any) -> FakeHttpResponse:
            return FakeHttpResponse(
                _json={"error": "access_denied", "error_description": "User denied"}
            )

        monkeypatch.setattr("openharness.api.copilot_auth.httpx.post", fake_post)
        monkeypatch.setattr("openharness.api.copilot_auth.time.sleep", lambda _: None)

        with pytest.raises(RuntimeError, match="User denied"):
            poll_for_access_token("dc_denied", interval=0, timeout=60)
