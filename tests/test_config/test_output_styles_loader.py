from __future__ import annotations

from openharness.output_styles.loader import load_output_styles


def test_builtin_output_styles_include_codex(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))

    styles = load_output_styles()
    builtin_names = {style.name for style in styles if style.source == "builtin"}

    assert {"default", "minimal", "codex"}.issubset(builtin_names)


def test_custom_output_style_is_loaded(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    style_dir = config_dir / "output_styles"
    style_dir.mkdir(parents=True)
    (style_dir / "focus.md").write_text("Use focused output", encoding="utf-8")
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(config_dir))

    styles = load_output_styles()
    custom = {style.name: style for style in styles if style.source == "user"}

    assert "focus" in custom
    assert custom["focus"].content == "Use focused output"
