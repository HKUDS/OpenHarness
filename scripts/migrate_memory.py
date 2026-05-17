"""Run the OpenHarness memory schema migration from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openharness.memory.migrate import main


if __name__ == "__main__":
    raise SystemExit(main())
