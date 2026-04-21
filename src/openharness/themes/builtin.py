"""Built-in theme definitions."""

from __future__ import annotations

from openharness.themes.schema import (
    BorderConfig,
    ColorsConfig,
    IconConfig,
    LayoutConfig,
    ThemeConfig,
)

BUILTIN_THEMES: dict[str, ThemeConfig] = {
    "default": ThemeConfig(
        name="default",
        colors=ColorsConfig(
            primary="#5875d4",
            secondary="#4a9eff",
            accent="#61afef",
            error="#e06c75",
            muted="#5c6370",
            background="#282c34",
            foreground="#abb2bf",
        ),
        borders=BorderConfig(style="rounded"),
        icons=IconConfig(spinner="⠋", tool="⚙", error="✖", success="✔", agent="◆"),
        layout=LayoutConfig(compact=False, show_tokens=True, show_time=True),
    ),
    "dark": ThemeConfig(
        name="dark",
        colors=ColorsConfig(
            primary="#bb9af7",
            secondary="#7aa2f7",
            accent="#9ece6a",
            error="#f7768e",
            muted="#414868",
            background="#1a1b26",
            foreground="#c0caf5",
        ),
        borders=BorderConfig(style="single"),
        icons=IconConfig(spinner="·", tool="*", error="!", success="+", agent=">"),
        layout=LayoutConfig(compact=False, show_tokens=True, show_time=True),
    ),
    "minimal": ThemeConfig(
        name="minimal",
        colors=ColorsConfig(
            primary="#ffffff",
            secondary="#cccccc",
            accent="#999999",
            error="#ff0000",
            muted="#666666",
            background="#000000",
            foreground="#ffffff",
        ),
        borders=BorderConfig(style="none"),
        icons=IconConfig(spinner="-", tool=":", error="E", success=".", agent="#"),
        layout=LayoutConfig(compact=True, show_tokens=False, show_time=False),
    ),
    "cyberpunk": ThemeConfig(
        name="cyberpunk",
        colors=ColorsConfig(
            primary="#00ff41",
            secondary="#bf00ff",
            accent="#00ffff",
            error="#ff0054",
            muted="#1a1a2e",
            background="#0d0d0d",
            foreground="#00ff41",
        ),
        borders=BorderConfig(style="double"),
        icons=IconConfig(spinner="◈", tool="◉", error="◌", success="◍", agent="◎"),
        layout=LayoutConfig(compact=False, show_tokens=True, show_time=True),
    ),
    "solarized": ThemeConfig(
        name="solarized",
        colors=ColorsConfig(
            primary="#268bd2",
            secondary="#2aa198",
            accent="#b58900",
            error="#dc322f",
            muted="#93a1a1",
            background="#002b36",
            foreground="#839496",
        ),
        borders=BorderConfig(style="rounded"),
        icons=IconConfig(spinner="⠋", tool="⚙", error="✖", success="✔", agent="◆"),
        layout=LayoutConfig(compact=False, show_tokens=True, show_time=True),
    ),
}
