"""Tests for session-end personalization persistence."""

from __future__ import annotations

import logging
from pathlib import Path

from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.memory import scan_memory_files
from openharness.personalization import rules as personalization_rules
from openharness.personalization.session_hook import update_rules_from_session


def test_update_rules_from_session_syncs_memory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rules_dir = tmp_path / "local_rules"
    monkeypatch.setattr(personalization_rules, "_RULES_DIR", rules_dir)
    monkeypatch.setattr(personalization_rules, "_RULES_FILE", rules_dir / "rules.md")
    monkeypatch.setattr(personalization_rules, "_FACTS_FILE", rules_dir / "facts.json")

    count = update_rules_from_session(
        [
            ConversationMessage(
                role="user",
                content=[TextBlock(text="ssh dev@10.0.0.8 && conda activate dev312")],
            )
        ],
        str(repo),
    )

    assert count >= 1
    headers = scan_memory_files(repo)
    assert headers
    assert any(header.memory_key.startswith("ssh_host:") or header.memory_key.startswith("conda_env:") for header in headers)


def test_update_rules_from_session_syncs_guardrails_and_style_rules(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rules_dir = tmp_path / "local_rules"
    monkeypatch.setattr(personalization_rules, "_RULES_DIR", rules_dir)
    monkeypatch.setattr(personalization_rules, "_RULES_FILE", rules_dir / "rules.md")
    monkeypatch.setattr(personalization_rules, "_FACTS_FILE", rules_dir / "facts.json")

    count = update_rules_from_session(
        [
            ConversationMessage(
                role="user",
                content=[
                    TextBlock(
                        text=(
                            "Guardrail: never delete migrations/\n"
                            "Protected path: migrations/\n"
                            "Output style: concise bullets only\n"
                            "Retry strategy: retry flaky network requests once"
                        )
                    )
                ],
            )
        ],
        str(repo),
    )

    assert count >= 1
    headers = scan_memory_files(repo)
    assert any(header.memory_key.startswith("guardrail:") for header in headers)
    assert any(header.memory_key.startswith("protected_path:") for header in headers)
    assert any(header.memory_key.startswith("style_rule:") or header.memory_key.startswith("retry_rule:") for header in headers)
    header_by_key = {header.memory_key: header for header in headers}
    assert header_by_key["guardrail:never delete migrations/"].memory_type == "guardrail"
    assert header_by_key["protected_path:migrations/"].memory_type == "protected_path"
    assert header_by_key["style_rule:concise bullets only"].memory_type == "style_rule"
    assert header_by_key["retry_rule:retry flaky network requests once"].memory_type == "retry_rule"


def test_update_rules_from_session_supports_chinese_rule_labels(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rules_dir = tmp_path / "local_rules"
    monkeypatch.setattr(personalization_rules, "_RULES_DIR", rules_dir)
    monkeypatch.setattr(personalization_rules, "_RULES_FILE", rules_dir / "rules.md")
    monkeypatch.setattr(personalization_rules, "_FACTS_FILE", rules_dir / "facts.json")

    count = update_rules_from_session(
        [
            ConversationMessage(
                role="user",
                content=[
                    TextBlock(
                        text=(
                            "高频易错点：改完接口字段后要同步更新测试和文档\n"
                            "安全红线：不要直接改生产配置\n"
                            "输出风格：默认用中文回复\n"
                            "重试策略：网络恢复后只重试一次"
                        )
                    )
                ],
            )
        ],
        str(repo),
    )

    assert count >= 1
    headers = scan_memory_files(repo)
    assert any(header.memory_type == "pitfall" for header in headers)
    assert any(header.memory_type == "guardrail" for header in headers)
    assert any(header.memory_type == "style_rule" for header in headers)
    assert any(header.memory_type == "retry_rule" for header in headers)


def test_update_rules_from_session_logs_memory_sync_failures(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rules_dir = tmp_path / "local_rules"
    monkeypatch.setattr(personalization_rules, "_RULES_DIR", rules_dir)
    monkeypatch.setattr(personalization_rules, "_RULES_FILE", rules_dir / "rules.md")
    monkeypatch.setattr(personalization_rules, "_FACTS_FILE", rules_dir / "facts.json")

    def _boom(*args, **kwargs):
        raise RuntimeError("sync failed")

    monkeypatch.setattr("openharness.personalization.session_hook.sync_fact_memories", _boom)

    with caplog.at_level(logging.ERROR):
        count = update_rules_from_session(
            [
                ConversationMessage(
                    role="user",
                    content=[TextBlock(text="Guardrail: never delete migrations/")],
                )
            ],
            str(repo),
        )

    assert count >= 1
    assert "Failed to sync extracted session facts into durable memory" in caplog.text