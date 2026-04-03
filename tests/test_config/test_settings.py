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
        assert s.vertex_project is None
        assert s.vertex_location is None

    def test_vertex_fields(self):
        s = Settings(vertex_project="my-project", vertex_location="us-central1")
        assert s.vertex_project == "my-project"
        assert s.vertex_location == "us-central1"

    def test_resolve_api_key_from_instance(self):
        s = Settings(api_key="sk-test-123")
        assert s.resolve_api_key() == "sk-test-123"

    def test_resolve_api_key_anthropic_from_env(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings()
        assert s.resolve_api_key() == "sk-env-456"

    def test_resolve_api_key_instance_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings(api_key="sk-instance-789")
        assert s.resolve_api_key() == "sk-instance-789"

    def test_resolve_api_key_missing_anthropic_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        s = Settings()
        with pytest.raises(ValueError, match="No API key found"):
            s.resolve_api_key()

    def test_resolve_api_key_gemini_from_gemini_key(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gm-key-abc")
        s = Settings(model="gemini-2.0-flash")
        assert s.resolve_api_key() == "gm-key-abc"

    def test_resolve_api_key_gemini_from_vertex_key(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("VERTEX_AI_API_KEY", "vx-key-xyz")
        s = Settings(model="gemini-2.5-pro")
        assert s.resolve_api_key() == "vx-key-xyz"

    def test_resolve_api_key_gemini_prefers_gemini_key_over_vertex(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gm-first")
        monkeypatch.setenv("VERTEX_AI_API_KEY", "vx-second")
        s = Settings(model="gemini-2.0-flash")
        assert s.resolve_api_key() == "gm-first"

    def test_resolve_api_key_gemini_missing_raises(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("VERTEX_AI_API_KEY", raising=False)
        s = Settings(model="gemini-2.0-flash")
        with pytest.raises(ValueError, match="No API key found for Gemini model"):
            s.resolve_api_key()

    def test_resolve_api_key_instance_takes_precedence_over_gemini_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gm-env")
        s = Settings(model="gemini-2.0-flash", api_key="sk-explicit")
        assert s.resolve_api_key() == "sk-explicit"

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
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example/anthropic")
        # ANTHROPIC_API_KEY is not loaded into api_key — use OPENHARNESS_API_KEY for that
        monkeypatch.setenv("OPENHARNESS_API_KEY", "sk-env-override")

        s = load_settings(path)

        assert s.model == "from-env-model"
        assert s.base_url == "https://env.example/anthropic"
        assert s.api_key == "sk-env-override"

    def test_load_anthropic_api_key_env_not_loaded_into_api_key_field(
        self, tmp_path: Path, monkeypatch
    ):
        """ANTHROPIC_API_KEY must not clobber the api_key field.

        It is resolved lazily by resolve_api_key() so that provider-specific
        key routing remains correct when switching between Anthropic and Gemini.
        """
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic-env")
        monkeypatch.delenv("OPENHARNESS_API_KEY", raising=False)

        s = load_settings(path)

        # api_key field stays empty — resolved dynamically by resolve_api_key()
        assert s.api_key == ""
        # But resolve_api_key() still finds it
        assert s.resolve_api_key() == "sk-anthropic-env"

    def test_load_applies_vertex_env_overrides(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        monkeypatch.setenv("VERTEX_PROJECT", "my-gcp-project")
        monkeypatch.setenv("VERTEX_LOCATION", "europe-west4")

        s = load_settings(path)

        assert s.vertex_project == "my-gcp-project"
        assert s.vertex_location == "europe-west4"

    def test_load_applies_google_cloud_env_overrides(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gcp-proj")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        monkeypatch.delenv("VERTEX_PROJECT", raising=False)
        monkeypatch.delenv("VERTEX_LOCATION", raising=False)

        s = load_settings(path)

        assert s.vertex_project == "gcp-proj"
        assert s.vertex_location == "us-central1"

    def test_vertex_project_env_takes_precedence_over_google_cloud(
        self, tmp_path: Path, monkeypatch
    ):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({}))
        monkeypatch.setenv("VERTEX_PROJECT", "vertex-wins")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gcp-loses")

        s = load_settings(path)

        assert s.vertex_project == "vertex-wins"
