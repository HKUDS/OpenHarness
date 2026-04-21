"""Theme configuration schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ColorsConfig(BaseModel):
    """Color configuration for a theme."""

    primary: str = "#5875d4"
    secondary: str = "#4a9eff"
    accent: str = "#61afef"
    error: str = "#e06c75"
    muted: str = "#5c6370"
    background: str = "#282c34"
    foreground: str = "#abb2bf"


class BorderConfig(BaseModel):
    """Border style configuration."""

    style: Literal["rounded", "single", "double", "none"] = "rounded"
    char: str | None = None


class IconConfig(BaseModel):
    """Icon/glyph configuration."""

    spinner: str = "⠋"
    tool: str = "⚙"
    error: str = "✖"
    success: str = "✔"
    agent: str = "◆"


class LayoutConfig(BaseModel):
    """Layout configuration."""

    compact: bool = False
    show_tokens: bool = True
    show_time: bool = True


class ThemeConfig(BaseModel):
    """Full theme configuration."""

    name: str
    colors: ColorsConfig = ColorsConfig()
    borders: BorderConfig = BorderConfig()
    icons: IconConfig = IconConfig()
    layout: LayoutConfig = LayoutConfig()
