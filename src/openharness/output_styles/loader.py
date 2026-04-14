"""Output style loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openharness.config.paths import get_config_dir


@dataclass(frozen=True)
class OutputStyle:
    """A named output style."""

    name: str
    content: str
    source: str


def get_output_styles_dir() -> Path:
    """Return the custom output styles directory."""
    path = get_config_dir() / "output_styles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_output_styles() -> list[OutputStyle]:
    """Load bundled and custom output styles."""
    styles = [
        OutputStyle(name="default", content="Standard rich console output.", source="builtin"),
        OutputStyle(name="minimal", content="Very terse plain-text output.", source="builtin"),
        OutputStyle(name="codex", content="Codex-like compact transcript and tool output.", source="builtin"),
    ]
    for path in sorted(get_output_styles_dir().glob("*.md")):
        styles.append(
            OutputStyle(
                name=path.stem,
                content=path.read_text(encoding="utf-8"),
                source="user",
            )
        )
    return styles
