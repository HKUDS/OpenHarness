"""Tests for automatic durable-memory review helpers."""

from __future__ import annotations

from pathlib import Path

from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.memory.auto_write import (
    MEMORY_POLICY_SKILL_NAME,
    MEMORY_REVIEW_SKILL_NAME,
    build_turn_memory_review_messages,
    build_turn_memory_review_prompt,
)
from openharness.memory.manager import upsert_memory_entry


def test_build_turn_memory_review_prompt_uses_compact_memory_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    for index in range(15):
        upsert_memory_entry(
            project_dir,
            key=f"guardrail:rule_{index}",
            title=f"规则 {index}",
            description=f"用于测试的 durable memory {index}",
            memory_type="guardrail",
            content=f"Guardrail: rule {index}",
        )

    prompt = build_turn_memory_review_prompt(
        [ConversationMessage(role="user", content=[TextBlock(text="Guardrail: never delete migrations/")])],
        project_dir,
        max_messages=1,
    )

    assert "# Current Durable Memories" in prompt
    assert "- Total entries: 15" in prompt
    assert "Persistent memory directory" not in prompt
    assert "Treat MEMORY.md as the default index" not in prompt
    assert "... 3 more entries in MEMORY.md" in prompt


def test_build_turn_memory_review_messages_prepends_bundled_skill(tmp_path: Path):
    review_messages = build_turn_memory_review_messages(
        [ConversationMessage(role="user", content=[TextBlock(text="Guardrail: never force-push main")])],
        tmp_path,
        max_messages=1,
    )

    assert len(review_messages) == 3
    assert "# Durable Memory Writes" in review_messages[0].text
    assert "Use the memory_write tool for durable context" in review_messages[0].text
    assert "# Durable Memory Reviewer" in review_messages[1].text
    assert "If no memory update is needed, reply with exactly NO_MEMORY_UPDATE." in review_messages[1].text
    assert "# Completed Conversation Turn" in review_messages[2].text


def test_build_turn_memory_review_messages_accepts_skill_override(tmp_path: Path):
    skills_root = tmp_path / "skills"
    policy_dir = skills_root / MEMORY_POLICY_SKILL_NAME
    policy_dir.mkdir(parents=True)
    (policy_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {MEMORY_POLICY_SKILL_NAME}\n"
        "description: Custom policy\n"
        "---\n\n"
        "# Custom durable memory policy\n\n"
        "Prefer long-lived team conventions first.\n",
        encoding="utf-8",
    )
    reviewer_dir = skills_root / MEMORY_REVIEW_SKILL_NAME
    reviewer_dir.mkdir(parents=True)
    (reviewer_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {MEMORY_REVIEW_SKILL_NAME}\n"
        "description: Custom reviewer\n"
        "---\n\n"
        "# Custom durable reviewer\n\n"
        "Always check the override instructions first.\n",
        encoding="utf-8",
    )

    review_messages = build_turn_memory_review_messages(
        [ConversationMessage(role="user", content=[TextBlock(text="Remember the SSH host")])],
        tmp_path,
        max_messages=1,
        extra_skill_dirs=[skills_root],
    )

    assert len(review_messages) == 3
    assert review_messages[0].text == "# Custom durable memory policy\n\nPrefer long-lived team conventions first."
    assert "# Custom durable reviewer" in review_messages[1].text
    assert "override instructions" in review_messages[1].text