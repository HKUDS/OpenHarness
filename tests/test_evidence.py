"""Tests for the evidence layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from openharness.evidence import EvidenceCollector, EvidenceStore, EvidenceArchiver
from openharness.evidence.types import RunEvidence, TaskEvidence


def test_evidence_store():
    """Test basic evidence storage and retrieval."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = EvidenceStore(Path(temp_dir))

        # Create and store evidence
        evidence = RunEvidence(
            type="run_start",
            run_id="test-run-123",
            agent_id="test-agent",
            session_id="test-session",
            cwd="/tmp",
            command_line="test command",
        )
        store.store_evidence(evidence)

        # Retrieve evidence
        records = list(store.get_evidence("test-run-123"))
        assert len(records) == 1
        assert records[0].run_id == "test-run-123"
        assert records[0].type == "run_start"


def test_evidence_collector():
    """Test evidence collection."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = EvidenceStore(Path(temp_dir))
        collector = EvidenceCollector("test-run-456", store)

        # Record run start
        collector.record_run_start(
            session_id="test-session",
            cwd="/tmp",
            command_line="test command",
        )

        # Record task
        collector.record_task_start(
            TaskEvidence(
                task_id="task-123",
                task_type="local_agent",
                description="Test task",
                status="running",
                cwd="/tmp",
                output_file=Path("/tmp/task.log"),
                command="echo hello",
            )
        )

        # Check evidence was stored
        records = list(store.get_evidence("test-run-456"))
        assert len(records) == 2

        run_records = [r for r in records if r.type == "run_start"]
        task_records = [r for r in records if r.type == "task_start"]

        assert len(run_records) == 1
        assert len(task_records) == 1
        assert task_records[0].task_id == "task-123"


def test_evidence_archiver():
    """Test evidence archiving."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        store = EvidenceStore(temp_path)
        archiver = EvidenceArchiver(store)

        # Create some evidence
        evidence = RunEvidence(
            type="run_start",
            run_id="archive-test-run",
            agent_id="test-agent",
        )
        store.store_evidence(evidence)

        # Export to JSON
        json_path = archiver.export_run_to_json("archive-test-run")
        assert json_path.exists()

        # Create archive
        archive_path = archiver.create_run_archive("archive-test-run")
        assert archive_path.exists()

        # Create report
        report_path = archiver.create_run_report("archive-test-run")
        assert report_path.exists()
        assert "Run Evidence Report" in report_path.read_text()


def test_run_summary():
    """Test run summary generation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = EvidenceStore(Path(temp_dir))

        # Create multiple evidence records
        records = [
            RunEvidence(type="run_start", run_id="summary-test", agent_id="agent1"),
            TaskEvidence(type="task_start", run_id="summary-test", agent_id="agent1", task_id="task1"),
            TaskEvidence(type="task_end", run_id="summary-test", agent_id="agent1", task_id="task1"),
            RunEvidence(type="run_end", run_id="summary-test", agent_id="agent1"),
        ]

        for record in records:
            store.store_evidence(record)

        summary = store.get_run_summary("summary-test")
        assert summary["run_id"] == "summary-test"
        assert summary["total_records"] == 4
        assert summary["evidence_counts"]["run_start"] == 1
        assert summary["evidence_counts"]["run_end"] == 1
        assert summary["evidence_counts"]["task_start"] == 1
        assert summary["evidence_counts"]["task_end"] == 1