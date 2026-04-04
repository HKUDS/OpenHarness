"""Tests for openharness.config.settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.config.settings import Settings, load_settings, save_settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.api_key == ""
        assert s.model == "claude-sonnet-4-20250514"
        assert s.max_tokens == 16384
        assert s.fast_mode is False
        assert s.permission.mode == "default"

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
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
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


class TestLoadSaveSettings:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        s = load_settings(path)
        assert s == Settings()

    def test_load_existing_file(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "claude-opus-4-20250514", "verbose": True, "fast_mode": True}))
        s = load_settings(path)
        assert s.model == "claude-opus-4-20250514"
        assert s.verbose is True
        assert s.fast_mode is True
        assert s.api_key == ""  # default preserved

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        original = Settings(api_key="sk-roundtrip", model="claude-opus-4-20250514", verbose=True)
        save_settings(original, path)
        loaded = load_settings(path)
        assert loaded.api_key == original.api_key
        assert loaded.model == original.model
        assert loaded.verbose == original.verbose

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
        monkeypatch.delenv("OPENHARNESS_API_FORMAT", raising=False)
        monkeypatch.delenv("OPENHARNESS_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-override")

        s = load_settings(path)

        assert s.model == "from-env-model"
        assert s.base_url == "https://env.example/anthropic"
        assert s.api_key == "sk-env-override"

    def test_load_supports_legacy_provider_field(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"provider": "openai"}))
        monkeypatch.delenv("OPENHARNESS_API_FORMAT", raising=False)
        monkeypatch.delenv("OPENHARNESS_PROVIDER", raising=False)
        s = load_settings(path)
        assert s.api_format == "openai"

    def test_resolve_api_key_openai_format(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-123")
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        s = Settings(api_format="openai")
        assert s.resolve_api_key() == "sk-openai-123"
