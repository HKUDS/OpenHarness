"""Regression guard: the React TUI exit handler must write a trailing newline.

When the TUI process exits, Ink leaves the cursor at the end of the last
rendered line.  Without a newline the shell prompt appears concatenated with
the TUI output, which is visually broken.  This test reads the TypeScript
entry-point source and asserts that the exit-cleanup write includes '\\n'
alongside the cursor-show escape sequence.
"""

from __future__ import annotations

import re
from pathlib import Path


def _frontend_index() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "frontend" / "terminal" / "src" / "index.tsx"


def test_tui_exit_handler_writes_newline() -> None:
    """restoreTerminal must emit \\x1B[?25h\\n so the shell prompt starts on a new line.

    Regression for: TUI exit leaves shell prompt concatenated with last TUI line.
    """
    source = _frontend_index().read_text(encoding="utf-8")

    # Locate the cleanup function body and verify it includes a trailing \\n.
    # The expected write is: process.stdout.write('\\x1B[?25h\\n')
    pattern = re.compile(
        r"process\.stdout\.write\(['\"].*\\x1B\[\?25h\\n.*['\"]\)",
        re.MULTILINE,
    )
    assert pattern.search(source), (
        "The TUI exit handler must call process.stdout.write with a trailing '\\n' "
        "so the shell prompt starts on a fresh line after the TUI exits. "
        f"Check {_frontend_index()} and ensure the cursor-restore write ends with \\n."
    )


def test_tui_exit_handler_registered_for_all_signals() -> None:
    """restoreTerminal must be attached to 'exit', SIGINT, and SIGTERM."""
    source = _frontend_index().read_text(encoding="utf-8")

    for signal in ("exit", "SIGINT", "SIGTERM"):
        assert f"process.on('{signal}'" in source, (
            f"The TUI exit cleanup must be registered for '{signal}'. "
            f"Check {_frontend_index()}."
        )
