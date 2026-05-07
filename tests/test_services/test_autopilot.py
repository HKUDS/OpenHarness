"""Tests for project repo autopilot state."""

from __future__ import annotations

from pathlib import Path
from types import MethodType, SimpleNamespace

from openharness.autopilot import RepoAutopilotStore, RepoVerificationStep
from openharness.autopilot.service import _DEFAULT_VERIFICATION_POLICY
from openharness.config.paths import (
    get_project_active_repo_context_path,
    get_project_autopilot_policy_path,
    get_project_release_policy_path,
    get_project_verification_policy_path,
)


def test_autopilot_enqueue_creates_layout_and_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    store = RepoAutopilotStore(repo)
    card, created = store.enqueue_card(
        source_kind="manual_idea",
        title="Add repo autopilot queue",
        body="Persist repo-level work items for self-evolution.",
    )

    assert created is True
    assert card.score > 0
    assert get_project_autopilot_policy_path(repo).exists()
    assert get_project_verification_policy_path(repo).exists()
    assert get_project_release_policy_path(repo).exists()
    context = get_project_active_repo_context_path(repo).read_text(encoding="utf-8")
    assert "Current Task Focus" in context
    assert "Add repo autopilot queue" in context


def test_autopilot_pick_next_prefers_highest_score(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    store.enqueue_card(
        source_kind="claude_code_candidate",
        title="Evaluate claude-code agent",
        body="candidate",
    )
    store.enqueue_card(
        source_kind="ohmo_request",
        title="Fix production issue",
        body="urgent bug in channel bridge",
    )

    next_card = store.pick_next_card()

    assert next_card is not None
    assert next_card.source_kind == "ohmo_request"


def test_autopilot_scan_claude_code_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    claude_root = tmp_path / "claude-code"
    (claude_root / "commands").mkdir(parents=True)
    (claude_root / "agents").mkdir(parents=True)
    (claude_root / "commands" / "compact.md").write_text("compact feature", encoding="utf-8")
    (claude_root / "agents" / "reviewer.md").write_text("reviewer feature", encoding="utf-8")

    store = RepoAutopilotStore(repo)
    cards = store.scan_claude_code_candidates(limit=5, root=claude_root)

    assert len(cards) == 2
    titles = {card.title for card in cards}
    assert "Evaluate claude-code command: compact" in titles
    assert "Evaluate claude-code agent: reviewer" in titles


def test_default_verification_policy_uses_repeatable_local_tsc_command() -> None:
    commands = _DEFAULT_VERIFICATION_POLICY["commands"]

    def _command_text(entry: object) -> str:
        if isinstance(entry, dict):
            return str(entry.get("command", ""))
        return str(entry)

    texts = [_command_text(entry) for entry in commands]
    assert any("./node_modules/.bin/tsc --noEmit" in text for text in texts)
    assert any("npm ci --no-audit --no-fund" in text for text in texts)
    # The tsc step relies on `cd ... && ...` and must opt in to shell=true so
    # the metacharacters are allowed through the verification runner.
    tsc_entry = next(
        entry
        for entry in commands
        if isinstance(entry, dict) and "tsc --noEmit" in str(entry.get("command", ""))
    )
    assert tsc_entry["shell"] is True


def test_autopilot_ci_rollup_treats_missing_checks_as_pending(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)

    state, summary, checks = store._ci_rollup({"statusCheckRollup": []})

    assert state == "pending"
    assert "have not appeared yet" in summary
    assert checks == []


def test_autopilot_export_dashboard_writes_static_site(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    store.enqueue_card(
        source_kind="manual_idea",
        title="Build kanban page",
        body="Make the self-evolution direction visible.",
    )
    store.enqueue_card(
        source_kind="github_issue",
        title="GitHub issue #42: Fix dashboard filters",
        body="search should work",
        source_ref="issue:42",
    )

    output_dir = repo / "docs" / "autopilot"
    exported = store.export_dashboard(output_dir)

    assert exported == output_dir.resolve()
    index_path = output_dir / "index.html"
    snapshot_path = output_dir / "snapshot.json"
    assert index_path.exists()
    assert snapshot_path.exists()
    index_text = index_path.read_text(encoding="utf-8")
    snapshot_text = snapshot_path.read_text(encoding="utf-8")
    assert "Autopilot Kanban" in index_text
    assert "snapshot.json" in index_text
    assert "Build kanban page" in snapshot_text
    assert '"status_order"' in snapshot_text


def test_autopilot_run_card_marks_completed_after_verification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="manual_idea",
        title="Implement repo autopilot tick",
        body="run next queued task and verify it",
    )

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        assert "Implement repo autopilot tick" in prompt
        return "Implemented the change and ran targeted checks."

    def fake_run_verification_steps(self, policies, *, cwd=None):
        return [
            RepoVerificationStep(
                command="uv run pytest -q",
                returncode=0,
                status="success",
                stdout="63 passed",
            )
        ]

    store._run_agent_prompt = MethodType(fake_run_agent_prompt, store)
    store._run_verification_steps = MethodType(fake_run_verification_steps, store)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "completed"
    updated = store.get_card(card.id)
    assert updated is not None
    assert updated.status == "completed"
    assert Path(result.run_report_path).exists()
    assert Path(result.verification_report_path).exists()
    run_report = Path(result.run_report_path).read_text(encoding="utf-8")
    assert "## Agent Self-Reported Summary" in run_report
    assert "## Service-Level Ground Truth" in run_report
    assert "- Verification status: passed." in run_report


def test_autopilot_run_card_marks_failed_when_verification_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="manual_idea",
        title="Ship broken change",
        body="this should fail verification",
    )

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        return "Made a risky change."

    def fake_run_verification_steps(self, policies, *, cwd=None):
        return [
            RepoVerificationStep(
                command="uv run pytest -q",
                returncode=1,
                status="failed",
                stderr="1 failed",
            )
        ]

    store._run_agent_prompt = MethodType(fake_run_agent_prompt, store)
    store._run_verification_steps = MethodType(fake_run_verification_steps, store)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "failed"
    updated = store.get_card(card.id)
    assert updated is not None
    assert updated.status == "failed"
    run_report = Path(result.run_report_path).read_text(encoding="utf-8")
    assert "## Agent Self-Reported Summary" in run_report
    assert "## Service-Level Ground Truth" in run_report
    assert "- Verification status: failed." in run_report
    assert "[failed] `uv run pytest -q`" in run_report


def test_autopilot_tick_scans_then_runs_next(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    store.enqueue_card(source_kind="manual_idea", title="Do queued work", body="body")

    def fake_scan_all_sources(self, *, issue_limit: int = 10, pr_limit: int = 10):
        return {"github_issue": 0, "github_pr": 0, "claude_code_candidate": 0}

    async def fake_run_next(self, *, model=None, max_turns=None, permission_mode=None):
        from openharness.autopilot import RepoRunResult

        return RepoRunResult(
            card_id="ap-test",
            status="completed",
            assistant_summary="done",
            run_report_path=str(self.runs_dir / "ap-test-run.md"),
            verification_report_path=str(self.runs_dir / "ap-test-verification.md"),
            verification_steps=[],
        )

    store.scan_all_sources = MethodType(fake_scan_all_sources, store)
    store.run_next = MethodType(fake_run_next, store)

    import asyncio

    result = asyncio.run(store.tick())

    assert result is not None
    assert result.card_id == "ap-test"


def test_autopilot_install_default_cron_creates_jobs(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    recorded: list[dict[str, str]] = []

    monkeypatch.setattr(
        "openharness.services.cron.upsert_cron_job",
        lambda job: recorded.append(job),
    )

    names = store.install_default_cron()

    assert names == ["autopilot.scan", "autopilot.tick"]
    assert len(recorded) == 2
    assert recorded[0]["name"] == "autopilot.scan"


def test_autopilot_run_card_opens_pr_and_waits_for_ci(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="manual_idea",
        title="Ship autopilot PR flow",
        body="exercise PR/CI orchestration",
    )

    async def fake_create_worktree(self, repo_path, slug, branch=None, agent_id=None):
        return SimpleNamespace(path=worktree)

    async def fake_remove_worktree(self, slug):
        return True

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        assert cwd == worktree
        return "Implemented the requested feature."

    def fake_run_verification_steps(self, policies, *, cwd=None):
        assert cwd == worktree
        return [RepoVerificationStep(command="uv run pytest -q", returncode=0, status="success")]

    async def fake_wait_for_pr_ci(self, pr_number: int, policies):
        return "success", "All reported remote checks passed.", {"url": "https://example/pr/17", "labels": [], "isDraft": False}, []

    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.create_worktree", fake_create_worktree)
    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.remove_worktree", fake_remove_worktree)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._is_git_repo", lambda self, cwd: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_agent_prompt", fake_run_agent_prompt)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_verification_steps", fake_run_verification_steps)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._sync_worktree_to_base", lambda self, cwd, *, base_branch, head_branch, reset: None)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_commit_all", lambda self, cwd, message: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_push_branch", lambda self, cwd, branch: None)
    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._upsert_pull_request",
        lambda self, card, *, head_branch, base_branch, run_report_path, verification_report_path: {
            "number": 17,
            "url": "https://example/pr/17",
        },
    )
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._wait_for_pr_ci", fake_wait_for_pr_ci)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._automerge_eligible", lambda self, pr_snapshot, policies: False)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._comment_on_pr", lambda self, pr_number, comment: None)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "completed"
    assert result.pr_number == 17
    updated = store.get_card(card.id)
    assert updated is not None
    assert updated.metadata["linked_pr_number"] == 17
    assert updated.metadata["human_gate_pending"] is True


def test_autopilot_run_card_repairs_after_local_verification_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="manual_idea",
        title="Repair failing verification",
        body="first verification fails, second passes",
    )

    verification_calls = {"count": 0}

    async def fake_create_worktree(self, repo_path, slug, branch=None, agent_id=None):
        return SimpleNamespace(path=worktree)

    async def fake_remove_worktree(self, slug):
        return True

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        return f"attempt for {cwd}"

    def fake_run_verification_steps(self, policies, *, cwd=None):
        verification_calls["count"] += 1
        if verification_calls["count"] == 1:
            return [RepoVerificationStep(command="uv run pytest -q", returncode=1, status="failed", stderr="1 failed")]
        return [RepoVerificationStep(command="uv run pytest -q", returncode=0, status="success")]

    async def fake_wait_for_pr_ci(self, pr_number: int, policies):
        return "success", "All reported remote checks passed.", {"url": "https://example/pr/23", "labels": ["autopilot:merge"], "isDraft": False}, []

    merged = {"called": False}

    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.create_worktree", fake_create_worktree)
    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.remove_worktree", fake_remove_worktree)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._is_git_repo", lambda self, cwd: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_agent_prompt", fake_run_agent_prompt)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_verification_steps", fake_run_verification_steps)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._sync_worktree_to_base", lambda self, cwd, *, base_branch, head_branch, reset: None)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_commit_all", lambda self, cwd, message: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_push_branch", lambda self, cwd, branch: None)
    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._upsert_pull_request",
        lambda self, card, *, head_branch, base_branch, run_report_path, verification_report_path: {
            "number": 23,
            "url": "https://example/pr/23",
        },
    )
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._wait_for_pr_ci", fake_wait_for_pr_ci)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._automerge_eligible", lambda self, pr_snapshot, policies: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._merge_pull_request", lambda self, pr_number: merged.__setitem__("called", True))
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._comment_on_pr", lambda self, pr_number, comment: None)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "merged"
    assert result.attempt_count == 2
    assert merged["called"] is True
    assert verification_calls["count"] == 2


def test_autopilot_run_card_reuses_existing_branch_progress(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="manual_idea",
        title="Reuse existing branch commit",
        body="agent may commit directly before the service tries to commit",
    )

    async def fake_create_worktree(self, repo_path, slug, branch=None, agent_id=None):
        return SimpleNamespace(path=worktree)

    async def fake_remove_worktree(self, slug):
        return True

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        return "A direct git commit already exists on the branch."

    def fake_run_verification_steps(self, policies, *, cwd=None):
        return [RepoVerificationStep(command="uv run pytest -q", returncode=0, status="success")]

    async def fake_wait_for_pr_ci(self, pr_number: int, policies):
        return "success", "All reported remote checks passed.", {"url": "https://example/pr/29", "labels": [], "isDraft": False}, []

    pushed = {"called": False}

    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.create_worktree", fake_create_worktree)
    monkeypatch.setattr("openharness.autopilot.service.WorktreeManager.remove_worktree", fake_remove_worktree)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._is_git_repo", lambda self, cwd: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_agent_prompt", fake_run_agent_prompt)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._run_verification_steps", fake_run_verification_steps)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._sync_worktree_to_base", lambda self, cwd, *, base_branch, head_branch, reset: None)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_commit_all", lambda self, cwd, message: False)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._git_branch_has_progress", lambda self, cwd, *, base_branch: True)
    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._git_push_branch",
        lambda self, cwd, branch: pushed.__setitem__("called", True),
    )
    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._upsert_pull_request",
        lambda self, card, *, head_branch, base_branch, run_report_path, verification_report_path: {
            "number": 29,
            "url": "https://example/pr/29",
        },
    )
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._wait_for_pr_ci", fake_wait_for_pr_ci)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._automerge_eligible", lambda self, pr_snapshot, policies: False)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._comment_on_pr", lambda self, pr_number, comment: None)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "completed"
    assert result.pr_number == 29
    assert pushed["called"] is True
    updated = store.get_card(card.id)
    assert updated is not None
    assert updated.metadata["human_gate_pending"] is True


def test_autopilot_existing_pr_card_can_auto_merge(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    card, _ = store.enqueue_card(
        source_kind="github_pr",
        title="GitHub PR #88: Existing autopilot PR",
        body="already open",
        source_ref="pr:88",
    )

    async def fake_wait_for_pr_ci(self, pr_number: int, policies):
        assert pr_number == 88
        return "success", "All reported remote checks passed.", {"url": "https://example/pr/88", "labels": ["autopilot:merge"], "isDraft": False}, []

    merged = {"called": False}

    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._wait_for_pr_ci", fake_wait_for_pr_ci)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._automerge_eligible", lambda self, pr_snapshot, policies: True)
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._merge_pull_request", lambda self, pr_number: merged.__setitem__("called", True))
    monkeypatch.setattr("openharness.autopilot.service.RepoAutopilotStore._comment_on_pr", lambda self, pr_number, comment: None)

    import asyncio

    result = asyncio.run(store.run_card(card.id))

    assert result.status == "merged"
    assert result.pr_number == 88
    assert merged["called"] is True


def test_wait_for_pr_ci_allows_repos_with_no_remote_checks_after_grace(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)

    times = iter([1000.0, 1000.0, 1006.0, 1006.0])
    monkeypatch.setattr("openharness.autopilot.service.time.time", lambda: next(times))
    monkeypatch.setattr(
        "openharness.autopilot.service.asyncio.sleep",
        lambda _seconds: __import__("asyncio").sleep(0),
    )
    monkeypatch.setattr(
        store,
        "_pr_status_snapshot",
        lambda pr_number: {"url": "https://example/pr/31", "statusCheckRollup": []},
    )

    import asyncio

    state, summary, snapshot, checks = asyncio.run(
        store._wait_for_pr_ci(
            31,
            {"autopilot": {"github": {"ci_poll_interval_seconds": 1, "ci_timeout_seconds": 30, "no_checks_grace_seconds": 5}}},
        )
    )

    assert state == "success"
    assert "grace period" in summary
    assert snapshot["url"] == "https://example/pr/31"
    assert checks == []


def test_wait_for_pr_ci_waits_for_check_settle_window(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)

    current_time = {"value": 1000.0}
    monkeypatch.setattr("openharness.autopilot.service.time.time", lambda: current_time["value"])
    snapshots = [
        {
            "url": "https://example/pr/33",
            "statusCheckRollup": [
                {"name": "GitGuardian Security Checks", "status": "COMPLETED", "conclusion": "SUCCESS"}
            ],
        },
        {
            "url": "https://example/pr/33",
            "statusCheckRollup": [
                {"name": "GitGuardian Security Checks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "Python tests (3.10)", "status": "IN_PROGRESS", "conclusion": ""},
            ],
        },
        {
            "url": "https://example/pr/33",
            "statusCheckRollup": [
                {"name": "GitGuardian Security Checks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "Python tests (3.10)", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
        },
    ]
    snapshot_index = {"value": 0}
    sleep_calls: list[int] = []

    async def fake_sleep(seconds: int) -> None:
        sleep_calls.append(seconds)
        current_time["value"] += seconds

    monkeypatch.setattr("openharness.autopilot.service.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        store,
        "_pr_status_snapshot",
        lambda pr_number: snapshots[min(snapshot_index.setdefault("value", 0), len(snapshots) - 1)],
    )
    original_snapshot = store._pr_status_snapshot

    def advancing_snapshot(pr_number: int):
        value = snapshot_index["value"]
        snapshot_index["value"] = value + 1
        return original_snapshot(pr_number)

    monkeypatch.setattr(store, "_pr_status_snapshot", advancing_snapshot)

    import asyncio

    state, summary, snapshot, checks = asyncio.run(
        store._wait_for_pr_ci(
            33,
            {
                "autopilot": {
                    "github": {
                        "ci_poll_interval_seconds": 5,
                        "ci_timeout_seconds": 60,
                        "no_checks_grace_seconds": 5,
                        "checks_settle_seconds": 10,
                    }
                }
            },
        )
    )

    assert state == "success"
    assert summary == "All reported remote checks passed."
    assert snapshot["url"] == "https://example/pr/33"
    assert len(checks) == 2
    assert sleep_calls == [5, 5]


def test_merge_pull_request_does_not_request_branch_deletion(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepoAutopilotStore(repo)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        store,
        "_run_gh",
        lambda args, *, cwd=None, check=False: captured.update({"args": args, "cwd": cwd, "check": check}),
    )

    store._merge_pull_request(41)

    assert captured["args"] == ["pr", "merge", "41", "--squash"]
    assert captured["check"] is True
