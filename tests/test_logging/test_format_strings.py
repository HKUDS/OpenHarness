from __future__ import annotations

import ast
from pathlib import Path


LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
SCAN_ROOTS = ("src/openharness", "ohmo", "scripts")


def _iter_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_root in SCAN_ROOTS:
        root = repo_root / relative_root
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _find_brace_style_logging_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOGGER_METHODS:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            continue
        if "{}" not in first_arg.value:
            continue
        findings.append(f"{path}:{node.lineno}:{first_arg.value}")
    return findings


def test_logging_format_strings_use_percent_style_placeholders() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []
    for path in _iter_python_files(repo_root):
        violations.extend(_find_brace_style_logging_calls(path))

    assert not violations, (
        "stdlib logging calls must use %%s-style placeholders instead of {}:\n"
        + "\n".join(violations)
    )
