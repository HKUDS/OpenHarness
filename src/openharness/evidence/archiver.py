"""Evidence archiving and management utilities."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from openharness.evidence.store import EvidenceStore


class EvidenceArchiver:
    """Utilities for archiving and managing evidence collections."""

    def __init__(self, store: EvidenceStore | None = None) -> None:
        self.store = store or EvidenceStore()

    def create_run_archive(
        self,
        run_id: str,
        archive_path: Path | None = None,
        include_metadata: bool = True,
    ) -> Path:
        """Create a compressed archive of all evidence for a run."""
        if archive_path is None:
            timestamp = int(time.time())
            archive_path = self.store.base_dir / f"{run_id}_{timestamp}.tar.gz"

        self.store.archive_run(run_id, archive_path)
        return archive_path

    def export_run_to_json(
        self,
        run_id: str,
        output_path: Path | None = None,
        pretty: bool = True,
    ) -> Path:
        """Export all evidence for a run to a single JSON file."""
        if output_path is None:
            output_path = self.store.base_dir / f"{run_id}_export.json"

        evidence_list = list(self.store.get_evidence(run_id))
        evidence_data = [evidence.__dict__ for evidence in evidence_list]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "run_id": run_id,
                    "export_timestamp": time.time(),
                    "evidence_count": len(evidence_data),
                    "evidence": evidence_data,
                },
                f,
                indent=2 if pretty else None,
                ensure_ascii=False,
            )

        return output_path

    def import_run_from_json(self, json_path: Path, new_run_id: str | None = None) -> str:
        """Import evidence from a JSON export file."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        run_id = new_run_id or data["run_id"] or str(uuid4())

        # Import each evidence record
        for evidence_dict in data["evidence"]:
            # Create a generic EvidenceRecord from the dict
            from openharness.evidence.types import EvidenceRecord

            evidence = EvidenceRecord()
            for key, value in evidence_dict.items():
                if hasattr(evidence, key):
                    setattr(evidence, key, value)

            # Override run_id if specified
            if new_run_id:
                evidence.run_id = new_run_id

            self.store.store_evidence(evidence)

        return run_id

    def create_run_report(
        self,
        run_id: str,
        report_path: Path | None = None,
        include_details: bool = True,
    ) -> Path:
        """Create a human-readable report of a run's evidence."""
        if report_path is None:
            report_path = self.store.base_dir / f"{run_id}_report.md"

        summary = self.store.get_run_summary(run_id)
        evidence_list = list(self.store.get_evidence(run_id))

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Run Evidence Report: {run_id}\n\n")

            f.write("## Summary\n\n")
            f.write(f"- **Total Records**: {summary['total_records']}\n")
            if summary['time_range']['start'] and summary['time_range']['end']:
                duration = summary['time_range']['end'] - summary['time_range']['start']
                f.write(f"- **Duration**: {duration:.2f} seconds\n")
                f.write(f"- **Time Range**: {time.ctime(summary['time_range']['start'])} - {time.ctime(summary['time_range']['end'])}\n")

            f.write("\n## Evidence Counts\n\n")
            for evidence_type, count in summary['evidence_counts'].items():
                f.write(f"- **{evidence_type}**: {count}\n")

            if include_details:
                f.write("\n## Detailed Evidence\n\n")

                # Group by type
                by_type = {}
                for evidence in evidence_list:
                    by_type.setdefault(evidence.type, []).append(evidence)

                for evidence_type, records in by_type.items():
                    f.write(f"### {evidence_type.title()}\n\n")

                    for record in sorted(records, key=lambda r: r.timestamp):
                        f.write(f"**{time.ctime(record.timestamp)}**\n\n")

                        # Show relevant fields based on type
                        if hasattr(record, 'description') and record.description:
                            f.write(f"- Description: {record.description}\n")
                        if hasattr(record, 'status') and record.status:
                            f.write(f"- Status: {record.status}\n")
                        if hasattr(record, 'error_message') and record.error_message:
                            f.write(f"- Error: {record.error_message}\n")
                        if hasattr(record, 'content') and record.content:
                            content_preview = record.content[:200] + "..." if len(record.content) > 200 else record.content
                            f.write(f"- Content: {content_preview}\n")

                        f.write("\n")

        return report_path

    def cleanup_archives(self, max_age_days: int = 30) -> dict[str, int]:
        """Clean up old evidence archives and runs."""
        results = {
            "removed_runs": self.store.cleanup_old_runs(max_age_days),
            "removed_archives": 0,
        }

        # Also clean up archive files
        archive_pattern = self.store.base_dir / "*.tar.gz"
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        for archive_file in self.store.base_dir.glob("*.tar.gz"):
            if archive_file.stat().st_mtime < cutoff_time:
                archive_file.unlink()
                results["removed_archives"] += 1

        return results

    def list_archives(self) -> list[dict[str, Any]]:
        """List all available evidence archives."""
        archives = []

        for archive_file in self.store.base_dir.glob("*.tar.gz"):
            stat = archive_file.stat()
            archives.append({
                "path": archive_file,
                "name": archive_file.name,
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
            })

        return sorted(archives, key=lambda x: x["created"], reverse=True)