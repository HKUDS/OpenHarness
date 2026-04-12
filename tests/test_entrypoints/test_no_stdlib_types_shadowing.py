from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_openharness_package_layout_does_not_shadow_stdlib_types(monkeypatch):
    shadow_path = str((Path(__file__).resolve().parents[2] / "src" / "openharness"))
    monkeypatch.syspath_prepend(shadow_path)
    sys.modules.pop("types", None)

    module = importlib.import_module("types")

    assert getattr(module, "__file__", "").endswith("types.py")
    assert "site-packages" not in getattr(module, "__file__", "")
