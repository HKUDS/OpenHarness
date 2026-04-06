"""Evidence storage and retrieval system."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator

from openharness.evidence.types import EvidenceRecord


class EvidenceStore:
    """Structured storage for run-level evidence."""

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            # Lazy import to avoid dependency issues during testing
            try:
                from openharness.config.paths import get_data_dir
                self.base_dir = get_data_dir() / "evidence"
            except ImportError:
                # Fallback for testing without full environment
                self.base_dir = Path.home() / ".openharness" / "evidence"
        else:
            self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_run_dir(self, run_id: str) -> Path:
        """Get the directory for a specific run."""
        return self.base_dir / run_id

    def _get_evidence_file(self, run_id: str, evidence_type: str) -> Path:
        """Get the file path for evidence of a specific type."""
        run_dir = self._get_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / f"{evidence_type}.jsonl"

    def store_evidence(self, evidence: EvidenceRecord) -> None:
        """Store an evidence record."""
        if not evidence.timestamp:
            evidence.timestamp = time.time()

        file_path = self._get_evidence_file(evidence.run_id, evidence.type)
        record_data = {
            "id": evidence.id,
            "timestamp": evidence.timestamp,
            "type": evidence.type,
            "run_id": evidence.run_id,
            "agent_id": evidence.agent_id,
            "metadata": evidence.metadata,
            **{
                k: v for k, v in evidence.__dict__.items()
                if k not in {"id", "timestamp", "type", "run_id", "agent_id", "metadata"}
                and v is not None and v != "" and v != [] and v != {}
            }
        }

        with open(file_path, "a", encoding="utf-8") as f:
            json.dump(record_data, f, ensure_ascii=False)
            f.write("\n")

    def get_evidence(
        self,
        run_id: str,
        evidence_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> Iterator[EvidenceRecord]:
        """Retrieve evidence records for a run."""
        if evidence_type:
            files = [self._get_evidence_file(run_id, evidence_type)]
        else:
            run_dir = self._get_run_dir(run_id)
            if not run_dir.exists():
                return
            files = list(run_dir.glob("*.jsonl"))

        for file_path in files:
            if not file_path.exists():
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        if start_time and data["timestamp"] < start_time:
                            continue
                        if end_time and data["timestamp"] > end_time:
                            continue

                        # Create the appropriate evidence record type
                        evidence = EvidenceRecord(
                            id=data["id"],
                            timestamp=data["timestamp"],
                            type=data["type"],
                            run_id=data["run_id"],
                            agent_id=data.get("agent_id", ""),
                            metadata=data.get("metadata", {}),
                        )

                        # Add type-specific fields
                        for k, v in data.items():
                            if k not in {"id", "timestamp", "type", "run_id", "agent_id", "metadata"}:
                                setattr(evidence, k, v)

                        yield evidence
                    except (json.JSONDecodeError, KeyError):
                        continue

    def list_runs(self) -> list[str]:
        """List all run IDs that have evidence."""
        if not self.base_dir.exists():
            return []

        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def get_run_summary(self, run_id: str) -> dict[str, Any]:
        """Get a summary of evidence for a run."""
        summary = {
            "run_id": run_id,
            "evidence_counts": {},
            "time_range": {"start": None, "end": None},
            "total_records": 0,
        }

        for evidence in self.get_evidence(run_id):
            summary["total_records"] += 1

            # Count by type
            summary["evidence_counts"][evidence.type] = (
                summary["evidence_counts"].get(evidence.type, 0) + 1
            )

            # Track time range
            if summary["time_range"]["start"] is None or evidence.timestamp < summary["time_range"]["start"]:
                summary["time_range"]["start"] = evidence.timestamp
            if summary["time_range"]["end"] is None or evidence.timestamp > summary["time_range"]["end"]:
                summary["time_range"]["end"] = evidence.timestamp

        return summary

    def archive_run(self, run_id: str, archive_path: Path) -> None:
        """Archive all evidence for a run to a compressed file."""
        import tarfile

        run_dir = self._get_run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"No evidence found for run {run_id}")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(run_dir, arcname=run_id)

    def cleanup_old_runs(self, max_age_days: int) -> int:
        """Remove evidence for runs older than the specified age."""
        import shutil

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        removed_count = 0

        for run_dir in self.base_dir.iterdir():
            if not run_dir.is_dir():
                continue

            # Check if any evidence file is older than cutoff
            should_remove = True
            for evidence_file in run_dir.glob("*.jsonl"):
                if evidence_file.stat().st_mtime > cutoff_time:
                    should_remove = False
                    break

            if should_remove:
                shutil.rmtree(run_dir)
                removed_count += 1

        return removed_count