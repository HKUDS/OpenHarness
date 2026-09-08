"""Persistent storage for goal state.

Goals survive process restarts: each project gets its own JSON file under
``~/.openharness/data/goals/`` sharded by a hash of the project path, same
scheme as session snapshots.
"""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from openharness.config.paths import get_data_dir
from openharness.utils.fs import atomic_write_text

from openharness.goal.types import GoalDefinition


def _get_goal_file(cwd: str | Path) -> Path:
    """Return the per-project goal state file path."""
    path = Path(cwd).resolve()
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    goals_dir = get_data_dir() / "goals" / f"{path.name}-{digest}"
    goals_dir.mkdir(parents=True, exist_ok=True)
    return goals_dir / "goal.json"


class GoalStore:
    """JSON-backed store for one active goal per project."""

    def __init__(self, cwd: str | Path) -> None:
        self._file = _get_goal_file(cwd)

    @property
    def file_path(self) -> Path:
        """Return the backing JSON file path."""
        return self._file

    def save(self, goal: GoalDefinition) -> None:
        """Persist the goal definition atomically."""
        goal.touch()
        atomic_write_text(self._file, goal.model_dump_json(indent=2))

    def load(self) -> GoalDefinition | None:
        """Load the persisted goal, or None when absent or corrupt."""
        if not self._file.exists():
            return None
        try:
            return GoalDefinition.model_validate_json(self._file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def clear(self) -> None:
        """Delete the persisted goal state."""
        if self._file.exists():
            self._file.unlink()