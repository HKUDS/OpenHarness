"""Tests for openharness.config.settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.auth.storage import store_credential
from openharness.config.settings import (
    ProviderProfile,
    Settings,
    display_model_setting,
    load_settings,
    normalize_anthropic_model_name,
    save_settings,
    strip_ansi_escape_sequences,
    _apply_env_overrides,
)


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.api_key == ""
        assert s.model == "claude-sonnet-4-6"
        assert s.max_tokens == 16384
        assert s.timeout == 30.0
        assert s.max_turns == 200
        assert s.fast_mode is False
        assert s.permission.mode == "default"
        assert s.sandbox.enabled is False
        assert s.sandbox.filesystem.allow_write == ["."]

    def test_resolve_api_key_from_instance(self):
        s = Settings(api_key="sk-test-123")
        assert s.resolve_api_key() == "sk-test-123"

    def test_resolve_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings()
        assert s.resolve_api_key() == "sk-env-456"

    def test_resolve_api_key_instance_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings(api_key="sk-instance-789")
        assert s.resolve_api_key() == "sk-instance-789"

    def test_resolve_api_key_missing_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        s = Settings()
        with pytest.raises(ValueError, match="No API key found"):
            s.resolve_api_key()

    def test_merge_cli_overrides(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="claude-opus-4-20250514", verbose=True, api_key=None)
        assert updated.model == "claude-opus-4-20250514"
        assert updated.verbose is True
        # api_key=None should not override the default
        assert updated.api_key == ""

    def test_merge_cli_overrides_returns_new_instance(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="claude-opus-4-20250514")
        assert s.model != updated.model
        assert s is not updated

    def test_resolve_auth_prefers_env_over_flat_api_key_for_openai(self, monkeypatch):
        """When api_format=openai, resolve_auth() should use OPENAI_API_KEY
        from the environment rather than the flat api_key field which may
        contain an Anthropic key from settings.json."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-correct")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        s = Settings(api_key="sk-ant-wrong-provider", api_format="openai")
        s = s.sync_active_profile_from_flat_fields()
        auth = s.resolve_auth()
        assert auth.value == "sk-openai-correct"
        assert "OPENAI" in auth.source

    def test_resolve_auth_falls_back_to_flat_api_key(self, monkeypatch):
        """When no provider-specific env var is set, resolve_auth() should
        still fall back to the flat api_key field."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        s = Settings(api_key="sk-fallback-key")
        s = s.sync_active_profile_from_flat_fields()
        auth = s.resolve_auth()
        assert auth.value == "sk-fallback-key"

    def test_env_overrides_picks_up_openai_base_url(self, tmp_path: Path, monkeypatch):
        """_apply_env_overrides should pick up OPENAI_BASE_URL for relay
        providers that use OpenAI-compatible format."""
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv("OPENHARNESS_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_BASE_URL", "https://relay.example.com/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-relay-key")
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        s = load_settings(path)
        assert s.base_url == "https://relay.example.com/v1"

    def test_env_overrides_pick_up_compact_threshold_settings(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONTEXT_WINDOW_TOKENS", "123456")
        monkeypatch.setenv("OPENHARNESS_AUTO_COMPACT_THRESHOLD_TOKENS", "120000")
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        s = load_settings(path)
        assert s.context_window_tokens == 123456
        assert s.auto_compact_threshold_tokens == 120000

    def test_anthropic_base_url_takes_precedence_over_openai(self, tmp_path: Path, monkeypatch):
        """ANTHROPIC_BASE_URL should take precedence over OPENAI_BASE_URL."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic-relay.example.com")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://openai-relay.example.com/v1")
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        s = load_settings(path)
        assert s.base_url == "https://anthropic-relay.example.com"


class TestLoadSaveSettings:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENHARNESS_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("OPENHARNESS_MODEL", raising=False)
        path = tmp_path / "nonexistent.json"
        s = load_settings(path)
        assert s == Settings().materialize_active_profile()

    def test_load_existing_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("OPENHARNESS_MODEL", raising=False)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "claude-opus-4-20250514", "verbose": True, "fast_mode": True}))
        s = load_settings(path)
        assert s.model == "claude-opus-4-20250514"
        assert s.verbose is True
        assert s.fast_mode is True
        assert s.api_key == ""  # default preserved

    def test_save_and_load_roundtrip(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("OPENHARNESS_MODEL", raising=False)
        path = tmp_path / "settings.json"
        original = Settings(api_key="sk-roundtrip", model="claude-opus-4-20250514", verbose=True)
        save_settings(original, path)
        loaded = load_settings(path)
        assert loaded.api_key == original.api_key
        assert loaded.model == original.model
        assert loaded.verbose == original.verbose

    def test_load_migrates_flat_provider_settings_to_profile(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "api_format": "anthropic",
                    "provider": "anthropic",
                    "model": "kimi-k2.5",
                    "base_url": "https://api.moonshot.cn/anthropic",
                }
            ),
            encoding="utf-8",
        )

        loaded = load_settings(path)
        profile_name, profile = loaded.resolve_profile()

        assert profile_name == "anthropic"
        assert profile.base_url == "https://api.moonshot.cn/anthropic"
        assert profile.resolved_model == "kimi-k2.5"
        assert loaded.base_url == "https://api.moonshot.cn/anthropic"
        assert loaded.model == "kimi-k2.5"

    def test_materialize_active_profile_uses_profile_model(self):
        settings = Settings(
            active_profile="codex",
            profiles={
                "codex": ProviderProfile(
                    label="Codex Subscription",
                    provider="openai_codex",
                    api_format="openai",
                    auth_source="codex_subscription",
                    default_model="gpt-5.4",
                    last_model="gpt-5",
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.provider == "openai_codex"
        assert materialized.api_format == "openai"
        assert materialized.model == "gpt-5"

    def test_materialize_active_profile_projects_compact_threshold_settings(self):
        settings = Settings(
            active_profile="openai-compatible",
            profiles={
                "openai-compatible": ProviderProfile(
                    label="OpenAI-Compatible API",
                    provider="openai",
                    api_format="openai",
                    auth_source="openai_api_key",
                    default_model="gpt-5.4",
                    context_window_tokens=100000,
                    auto_compact_threshold_tokens=90000,
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.context_window_tokens == 100000
        assert materialized.auto_compact_threshold_tokens == 90000

    def test_merge_cli_active_profile_does_not_inherit_flat_provider_fields(self):
        settings = Settings(
            active_profile="moonshot",
            provider="moonshot",
            api_format="openai",
            base_url="https://api.moonshot.cn/v1",
            model="kimi-k2.5",
            profiles={
                "moonshot": ProviderProfile(
                    label="Moonshot",
                    provider="moonshot",
                    api_format="openai",
                    auth_source="moonshot_api_key",
                    default_model="kimi-k2.5",
                    last_model="kimi-k2.5",
                    base_url="https://api.moonshot.cn/v1",
                ),
                "codex": ProviderProfile(
                    label="Codex Subscription",
                    provider="openai_codex",
                    api_format="openai",
                    auth_source="codex_subscription",
                    default_model="gpt-5.4",
                    last_model="gpt-5.4",
                ),
            },
        )

        updated = settings.merge_cli_overrides(active_profile="codex")
        profile_name, profile = updated.resolve_profile()

        assert profile_name == "codex"
        assert updated.provider == "openai_codex"
        assert updated.base_url is None
        assert updated.model == "gpt-5.4"
        assert profile.provider == "openai_codex"
        assert profile.auth_source == "codex_subscription"

    def test_merge_cli_active_profile_keeps_profile_compact_threshold_settings(self):
        settings = Settings(
            active_profile="moonshot",
            context_window_tokens=64000,
            auto_compact_threshold_tokens=60000,
            profiles={
                "moonshot": ProviderProfile(
                    label="Moonshot",
                    provider="moonshot",
                    api_format="openai",
                    auth_source="moonshot_api_key",
                    default_model="kimi-k2.5",
                    last_model="kimi-k2.5",
                    base_url="https://api.moonshot.cn/v1",
                    context_window_tokens=64000,
                    auto_compact_threshold_tokens=60000,
                ),
                "openai-compatible": ProviderProfile(
                    label="OpenAI-Compatible API",
                    provider="openai",
                    api_format="openai",
                    auth_source="openai_api_key",
                    default_model="gpt-5.4",
                    last_model="gpt-5.4",
                    base_url="https://relay.example.com/v1",
                    context_window_tokens=200000,
                    auto_compact_threshold_tokens=180000,
                ),
            },
        )

        updated = settings.merge_cli_overrides(active_profile="openai-compatible")

        assert updated.base_url == "https://relay.example.com/v1"
        assert updated.context_window_tokens == 200000
        assert updated.auto_compact_threshold_tokens == 180000

    def test_claude_profile_materializes_alias_to_concrete_model(self):
        settings = Settings(
            active_profile="claude-subscription",
            profiles={
                "claude-subscription": ProviderProfile(
                    label="Claude Subscription",
                    provider="anthropic_claude",
                    api_format="anthropic",
                    auth_source="claude_subscription",
                    default_model="sonnet",
                    last_model="opus",
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.model == "claude-opus-4-6"

    def test_claude_profile_normalizes_prefixed_model_name(self):
        settings = Settings(
            active_profile="claude-subscription",
            profiles={
                "claude-subscription": ProviderProfile(
                    label="Claude Subscription",
                    provider="anthropic_claude",
                    api_format="anthropic",
                    auth_source="claude_subscription",
                    default_model="claude-sonnet-4-6",
                    last_model="anthropic/claude-sonnet-4-20250514",
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.model == "claude-sonnet-4-20250514"

    def test_claude_profile_normalizes_dotted_model_name(self):
        settings = Settings(
            active_profile="claude-api",
            profiles={
                "claude-api": ProviderProfile(
                    label="Claude API",
                    provider="anthropic",
                    api_format="anthropic",
                    auth_source="anthropic_api_key",
                    default_model="claude-sonnet-4-6",
                    last_model="claude-opus-4.6",
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.model == "claude-opus-4-6"

    def test_display_model_setting_uses_default_alias(self):
        profile = ProviderProfile(
            label="Claude API",
            provider="anthropic",
            api_format="anthropic",
            auth_source="anthropic_api_key",
            default_model="claude-sonnet-4-6",
            last_model=None,
        )

        assert display_model_setting(profile) == "default"

    def test_opusplan_resolves_by_permission_mode(self):
        settings = Settings(
            permission={"mode": "plan"},
            active_profile="claude-api",
            profiles={
                "claude-api": ProviderProfile(
                    label="Claude API",
                    provider="anthropic",
                    api_format="anthropic",
                    auth_source="anthropic_api_key",
                    default_model="claude-sonnet-4-6",
                    last_model="opusplan",
                )
            },
        )

        materialized = settings.materialize_active_profile()

        assert materialized.model == "claude-opus-4-6"

    def test_resolve_auth_prefers_profile_scoped_credential_for_custom_compatible_profile(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global-env")
        store_credential("profile:kimi-anthropic", "api_key", "sk-profile-specific", use_keyring=False)
        settings = Settings(
            active_profile="kimi-anthropic",
            profiles={
                "kimi-anthropic": ProviderProfile(
                    label="Kimi Anthropic",
                    provider="anthropic",
                    api_format="anthropic",
                    auth_source="anthropic_api_key",
                    default_model="kimi-k2.5",
                    base_url="https://api.moonshot.cn/anthropic",
                    credential_slot="kimi-anthropic",
                )
            },
        )

        resolved = settings.resolve_auth()

        assert resolved.value == "sk-profile-specific"
        assert resolved.source == "file:profile:kimi-anthropic"


def test_normalize_anthropic_model_name_matches_hermes_behavior():
    assert normalize_anthropic_model_name("anthropic/claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"
    assert normalize_anthropic_model_name("claude-opus-4.6") == "claude-opus-4-6"

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "settings.json"
        save_settings(Settings(), path)
        assert path.exists()

    def test_load_with_permission_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "permission": {
                        "mode": "full_auto",
                        "allowed_tools": ["Bash", "Read"],
                    }
                }
            )
        )
        s = load_settings(path)
        assert s.permission.mode == "full_auto"
        assert s.permission.allowed_tools == ["Bash", "Read"]

    def test_load_applies_env_overrides(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "from-file", "base_url": "https://file.example"}))
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example/anthropic")
        monkeypatch.setenv("OPENHARNESS_TIMEOUT", "42.5")
        monkeypatch.setenv("OPENHARNESS_MAX_TURNS", "42")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-override")
        monkeypatch.setenv("OPENHARNESS_SANDBOX_ENABLED", "true")
        monkeypatch.setenv("OPENHARNESS_SANDBOX_FAIL_IF_UNAVAILABLE", "1")

        s = load_settings(path)

        assert s.model == "from-env-model"
        assert s.base_url == "https://env.example/anthropic"
        assert s.timeout == 42.5
        assert s.max_turns == 42
        assert s.api_key == "sk-env-override"
        assert s.sandbox.enabled is True
        assert s.sandbox.fail_if_unavailable is True

    def test_load_with_sandbox_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "sandbox": {
                        "enabled": True,
                        "enabled_platforms": ["linux", "wsl"],
                        "network": {"allowed_domains": ["github.com"]},
                        "filesystem": {"allow_write": [".", "/tmp"], "deny_write": [".env"]},
                    }
                }
            )
        )

        s = load_settings(path)

        assert s.sandbox.enabled is True
        assert s.sandbox.enabled_platforms == ["linux", "wsl"]
        assert s.sandbox.network.allowed_domains == ["github.com"]
        assert s.sandbox.filesystem.allow_write == [".", "/tmp"]
        assert s.sandbox.filesystem.deny_write == [".env"]


class TestAnsiEscapeSequences:
    """Tests for ANSI escape sequence handling in settings."""

    def test_strip_ansi_escape_sequences(self):
        """Test that ANSI escape sequences are properly stripped."""
        # Normal model name should pass through unchanged
        assert strip_ansi_escape_sequences("claude-opus-4-6") == "claude-opus-4-6"
        # Bold formatting should be stripped
        assert strip_ansi_escape_sequences("\x1b[1mclaude-opus-4-6\x1b[0m") == "claude-opus-4-6"
        # Green + bold formatting should be stripped
        assert strip_ansi_escape_sequences("\x1b[32m\x1b[1mclaude-opus-4-6\x1b[0m") == "claude-opus-4-6"
        # Only bold prefix
        assert strip_ansi_escape_sequences("\x1b[1mclaude-opus-4-6") == "claude-opus-4-6"
        # Only reset suffix
        assert strip_ansi_escape_sequences("claude-opus-4-6\x1b[0m") == "claude-opus-4-6"
        # Empty string should return empty string
        assert strip_ansi_escape_sequences("") == ""
        # None should return None
        assert strip_ansi_escape_sequences(None) is None

    def test_env_override_strips_ansi_from_model(self, monkeypatch):
        """Test that ANSI escape sequences are stripped from ANTHROPIC_MODEL env var."""
        monkeypatch.setenv("ANTHROPIC_MODEL", "\x1b[1mclaude-opus-4-6\x1b[0m")
        s = Settings()
        updated = _apply_env_overrides(s)
        assert updated.model == "claude-opus-4-6"

    def test_env_override_strips_ansi_from_openharness_model(self, monkeypatch):
        """Test that ANSI escape sequences are stripped from OPENHARNESS_MODEL env var."""
        monkeypatch.setenv("OPENHARNESS_MODEL", "\x1b[32mclaude-sonnet-4-6\x1b[0m")
        s = Settings()
        updated = _apply_env_overrides(s)
        assert updated.model == "claude-sonnet-4-6"

    def test_merge_cli_overrides_strips_ansi_from_model(self):
        """Test that ANSI escape sequences are stripped from CLI model override."""
        s = Settings()
        updated = s.merge_cli_overrides(model="\x1b[1mclaude-opus-4-6\x1b[0m")
        assert updated.model == "claude-opus-4-6"
