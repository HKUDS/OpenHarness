"""Theme loading utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openharness.themes.builtin import BUILTIN_THEMES
from openharness.themes.schema import ThemeConfig

logger = logging.getLogger(__name__)


def get_custom_themes_dir() -> Path:
    """Return the user custom themes directory."""
    path = Path.home() / ".openharness" / "themes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_custom_themes() -> dict[str, ThemeConfig]:
    """Load custom themes from ~/.openharness/themes/*.json."""
    themes: dict[str, ThemeConfig] = {}
    for path in sorted(get_custom_themes_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            theme = ThemeConfig.model_validate(data)
            themes[theme.name] = theme
        except Exception as exc:
            logger.debug("Skipping invalid theme file %s: %s", path, exc)
    return themes


def list_themes() -> list[str]:
    """Return names of all available themes (builtin + custom)."""
    names = list(BUILTIN_THEMES.keys())
    for name in load_custom_themes():
        if name not in names:
            names.append(name)
    return names


def load_theme(name: str) -> ThemeConfig:
    """Load a theme by name.

    Looks up custom themes first, then falls back to builtins.
    Raises ``KeyError`` if the theme is not found.
    """
    custom = load_custom_themes()
    if name in custom:
        return custom[name]
    if name in BUILTIN_THEMES:
        return BUILTIN_THEMES[name]
    raise KeyError(f"Unknown theme: {name!r}. Available: {list_themes()}")
