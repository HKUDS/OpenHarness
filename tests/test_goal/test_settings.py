"""GoalSettings configuration tests."""

from __future__ import annotations

from openharness.config.settings import GoalSettings


class TestGoalSettingsFromEnv:
    def test_defaults_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_GOAL_VERIFIER_MODEL", raising=False)
        monkeypatch.delenv("OPENHARNESS_GOAL_MAX_TURNS", raising=False)
        monkeypatch.delenv("OPENHARNESS_GOAL_MAX_TOKENS", raising=False)
        cfg = GoalSettings.from_env()
        assert cfg.verifier_model == ""
        assert cfg.max_turns == 100
        assert cfg.max_tokens is None

    def test_reads_all_environment_variables(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_GOAL_VERIFIER_MODEL", "gpt-5-mini")
        monkeypatch.setenv("OPENHARNESS_GOAL_MAX_TURNS", "42")
        monkeypatch.setenv("OPENHARNESS_GOAL_MAX_TOKENS", "5000")
        cfg = GoalSettings.from_env()
        assert cfg.verifier_model == "gpt-5-mini"
        assert cfg.max_turns == 42
        assert cfg.max_tokens == 5000

    def test_ignores_non_numeric_limits(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_GOAL_MAX_TURNS", "lots")
        monkeypatch.setenv("OPENHARNESS_GOAL_MAX_TOKENS", "many")
        cfg = GoalSettings.from_env()
        assert cfg.max_turns == 100
        assert cfg.max_tokens is None


class TestGoalSettingsDefaults:
    def test_settings_model_exposes_goal_section(self):
        from openharness.config.settings import Settings

        settings = Settings()
        assert settings.goal.verifier_model == ""
        assert settings.goal.max_turns == 100
        assert settings.goal.max_tokens is None

    def test_settings_parses_goal_from_config_file(self, tmp_path, monkeypatch):
        from openharness.config.settings import Settings

        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path))
        (tmp_path / "settings.json").write_text(
            '{"goal": {"verifier_model": "gpt-5-nano", "max_turns": 7}}',
            encoding="utf-8",
        )
        settings = Settings.model_validate_json((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert settings.goal.verifier_model == "gpt-5-nano"
        assert settings.goal.max_turns == 7