from __future__ import annotations

import json
import os
import time
from pathlib import Path

from openharness.config.settings import Settings
from openharness.services.autodream.backup import create_memory_backup, diff_memory_dirs, restore_memory_backup
from openharness.services.autodream.lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from openharness.services.autodream.prompt import build_consolidation_prompt
from openharness.services.autodream.service import execute_auto_dream, start_dream_now
from openharness.services.session_storage import get_project_session_dir


def test_consolidation_lock_acquire_and_rollback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    cwd = tmp_path / "repo"
    cwd.mkdir()

    assert read_last_consolidated_at(cwd) == 0
    prior = try_acquire_consolidation_lock(cwd)
    assert prior == 0
    assert read_last_consolidated_at(cwd) > 0
    assert try_acquire_consolidation_lock(cwd) is None

    rollback_consolidation_lock(cwd, prior)
    assert read_last_consolidated_at(cwd) == 0


def test_consolidation_lock_supports_memory_dir_override(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    memory_dir = tmp_path / "ohmo" / "memory"
    cwd.mkdir()

    prior = try_acquire_consolidation_lock(cwd, memory_dir=memory_dir)
    assert prior == 0
    assert (memory_dir / ".consolidate-lock").exists()
    assert read_last_consolidated_at(cwd, memory_dir=memory_dir) > 0

    rollback_consolidation_lock(cwd, prior, memory_dir=memory_dir)
    assert read_last_consolidated_at(cwd, memory_dir=memory_dir) == 0


def test_list_sessions_touched_since_excludes_current(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    cwd = tmp_path / "repo"
    cwd.mkdir()
    session_dir = get_project_session_dir(cwd)
    old = session_dir / "session-old.json"
    old.write_text(json.dumps({"session_id": "old"}), encoding="utf-8")
    new = session_dir / "session-new.json"
    new.write_text(json.dumps({"session_id": "new"}), encoding="utf-8")
    current = session_dir / "session-current.json"
    current.write_text(json.dumps({"session_id": "current"}), encoding="utf-8")
    cutoff = time.time() - 10
    os.utime(old, (cutoff - 20, cutoff - 20))

    assert list_sessions_touched_since(cwd, cutoff, current_session_id="current") == ["new"]


def test_list_sessions_touched_since_supports_session_dir_override(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    session_dir = tmp_path / "ohmo" / "sessions"
    cwd.mkdir()
    session_dir.mkdir(parents=True)
    (session_dir / "session-ohmo.json").write_text(json.dumps({"session_id": "ohmo"}), encoding="utf-8")

    assert list_sessions_touched_since(cwd, 0, session_dir=session_dir) == ["ohmo"]


def test_consolidation_prompt_contains_expected_sections(tmp_path: Path) -> None:
    prompt = build_consolidation_prompt(tmp_path / "memory", tmp_path / "sessions", "extra")
    assert "# Dream: Memory Consolidation" in prompt
    assert "Phase 1" in prompt
    assert "Phase 4" in prompt
    assert "MEMORY.md" in prompt
    assert "Never preserve API keys" in prompt
    assert "Evidence discipline" in prompt
    assert "Last observed" in prompt
    assert "Privacy: personal/private" in prompt
    assert "extra" in prompt


def test_consolidation_prompt_preview_mode(tmp_path: Path) -> None:
    prompt = build_consolidation_prompt(tmp_path / "memory", tmp_path / "sessions", preview=True)
    assert "PREVIEW MODE" in prompt
    assert "do not write files" in prompt


def test_memory_backup_diff_and_restore(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    backup = create_memory_backup(memory_dir, backup_root=tmp_path / "backups")
    (memory_dir / "new.md").write_text("new\n", encoding="utf-8")
    (memory_dir / "MEMORY.md").write_text("# Memory\n- changed\n", encoding="utf-8")

    diff = diff_memory_dirs(backup, memory_dir)
    assert diff["added"] == ["new.md"]
    assert diff["changed"] == ["MEMORY.md"]

    restore_memory_backup(backup, memory_dir)
    assert not (memory_dir / "new.md").exists()
    assert (memory_dir / "MEMORY.md").read_text(encoding="utf-8") == "# Memory\n"


async def test_execute_auto_dream_skips_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    cwd = tmp_path / "repo"
    cwd.mkdir()
    settings = Settings()
    settings.memory.auto_dream_enabled = False

    assert await execute_auto_dream(cwd=cwd, settings=settings, model="test") is None


async def test_start_dream_now_uses_overrides(tmp_path: Path, monkeypatch) -> None:
    cwd = tmp_path / "repo"
    memory_dir = tmp_path / ".ohmo" / "memory"
    session_dir = tmp_path / ".ohmo" / "sessions"
    cwd.mkdir()
    memory_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True)
    (session_dir / "session-one.json").write_text(json.dumps({"session_id": "one"}), encoding="utf-8")
    (memory_dir / "old.md").write_text(
        "---\n"
        "schema_version: 1\n"
        "id: \"mem-old\"\n"
        "name: \"old\"\n"
        "description: \"old note\"\n"
        "type: \"project\"\n"
        "category: \"knowledge\"\n"
        "importance: 0\n"
        "source: \"test\"\n"
        "signature: \"sig-old\"\n"
        "created_at: \"2020-01-01T00:00:00Z\"\n"
        "updated_at: \"2020-01-01T00:00:00Z\"\n"
        "ttl_days: null\n"
        "disabled: false\n"
        "supersedes: []\n"
        "---\n\n"
        "Old content.\n",
        encoding="utf-8",
    )

    captured = {}

    class _Manager:
        def register_completion_listener(self, listener):
            return None

        async def create_shell_task(self, **kwargs):
            from openharness.tasks.types import TaskRecord

            captured.update(kwargs)
            return TaskRecord(
                id="dtest",
                type="dream",
                status="running",
                description=kwargs["description"],
                cwd=str(kwargs["cwd"]),
                output_file=tmp_path / "dream.log",
                argv=kwargs["argv"],
                env=kwargs["env"],
            )

    monkeypatch.setattr("openharness.services.autodream.service.get_task_manager", lambda: _Manager())
    settings = Settings()
    task = await start_dream_now(
        cwd=cwd,
        settings=settings,
        force=True,
        memory_dir=memory_dir,
        session_dir=session_dir,
        app_label="ohmo personal memory",
        runner_module="ohmo",
    )

    assert task is not None
    assert task.metadata["memory_dir"] == str(memory_dir.resolve())
    assert task.metadata["session_dir"] == str(session_dir.resolve())
    assert task.metadata["app_label"] == "ohmo personal memory"
    assert task.metadata["backup_dir"]
    assert captured["argv"][:3][-1] == "ohmo"
    assert "--workspace" in captured["argv"]
    assert "--dangerously-skip-permissions" not in captured["argv"]
    assert "Usage-based stale candidates:" in task.prompt
    assert "old.md" in task.prompt
