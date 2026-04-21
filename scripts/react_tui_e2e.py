"""Scripted React TUI end-to-end checks using the real CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pexpect

from openharness.config.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]


def _spawn_oh(*, env: dict[str, str] | None = None) -> pexpect.spawn:
    args = ["run", "oh"]
    child = pexpect.spawn(
        "uv",
        args,
        cwd=str(ROOT),
        env=env or os.environ,
        encoding="utf-8",
        timeout=180,
    )
    child.delaybeforesend = 0.1
    if os.environ.get("OPENHARNESS_E2E_DEBUG") == "1":
        child.logfile_read = sys.stdout
    return child


def _submit(child: pexpect.spawn, text: str) -> None:
    for character in text:
        child.send(character)
        time.sleep(0.02)
    time.sleep(0.2)
    child.send("\r")
    time.sleep(0.4)


def _isolated_env(permission_mode: str = "full_auto") -> tuple[tempfile.TemporaryDirectory[str], dict[str, str]]:
    settings = load_settings()
    temp_dir = tempfile.TemporaryDirectory(prefix="openharness-react-tui-")
    config_dir = Path(temp_dir.name) / "config"
    data_dir = Path(temp_dir.name) / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")
    payload["permission"]["mode"] = permission_mode
    (config_dir / "settings.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["OPENHARNESS_CONFIG_DIR"] = str(config_dir)
    env["OPENHARNESS_DATA_DIR"] = str(data_dir)
    env["OPENHARNESS_FRONTEND_RAW_RETURN"] = "1"
    return temp_dir, env


def _run_permission_file_io() -> None:
    path = ROOT / "react_tui_smoke.txt"
    if path.exists():
        path.unlink()
    temp_dir, env = _isolated_env()
    child = _spawn_oh(env=env)
    try:
        print("[react_tui_permission_file_io] waiting for app shell")
        child.expect("OpenHarness")
        child.expect("model: kimi-k2.5")
        _submit(
            child,
            "You are running a React TUI end-to-end test. "
            "Use write_file to create react_tui_smoke.txt with exact content REACT_TUI_OK, "
            "then use read_file to verify it, then reply with exactly FINAL_OK_REACT_TUI.",
        )
        print("[react_tui_permission_file_io] waiting for final marker")
        child.expect(r"(?s)assistant>.*FINAL_OK_REACT_TUI")
    finally:
        child.sendcontrol("c")
        child.close(force=True)
        temp_dir.cleanup()
    assert path.read_text(encoding="utf-8") == "REACT_TUI_OK"
    print("[react_tui_permission_file_io] PASS")


def _run_question_flow() -> None:
    path = ROOT / "react_tui_question.txt"
    if path.exists():
        path.unlink()
    temp_dir, env = _isolated_env()
    child = _spawn_oh(env=env)
    try:
        child.expect("OpenHarness")
        child.expect("model: kimi-k2.5")
        _submit(
            child,
            "You are running a React TUI question flow test. "
            "Use ask_user_question to ask for a color. "
            "After the answer arrives, use write_file to create react_tui_question.txt with that exact answer, "
            "then use read_file to verify it, then reply with exactly FINAL_OK_REACT_TUI_QUESTION.",
        )
        print("[react_tui_question_flow] waiting for question modal")
        child.expect("Question")
        child.expect("color")
        _submit(child, "teal")
        print("[react_tui_question_flow] waiting for final marker")
        child.expect(r"(?s)assistant>.*FINAL_OK_REACT_TUI_QUESTION")
    finally:
        child.sendcontrol("c")
        child.close(force=True)
        temp_dir.cleanup()
    assert path.read_text(encoding="utf-8") == "teal"
    print("[react_tui_question_flow] PASS")


def _run_command_flow() -> None:
    temp_dir, env = _isolated_env()
    env["OPENHARNESS_FRONTEND_SCRIPT"] = json.dumps(
        [
            "/plan",
            "Reply with exactly FINAL_OK_REACT_TUI_COMMANDS.",
        ]
    )
    child = _spawn_oh(env=env)
    try:
        print("[react_tui_command_flow] waiting for app shell")
        child.expect("OpenHarness")
        child.expect("model: kimi-k2.5")
        print("[react_tui_command_flow] waiting for plan mode indicator")
        child.expect("PLAN MODE")
        print("[react_tui_command_flow] waiting for final marker")
        child.expect(r"(?s)assistant>.*FINAL_OK_REACT_TUI_COMMANDS")
    finally:
        child.sendcontrol("c")
        child.close(force=True)
        temp_dir.cleanup()
    print("[react_tui_command_flow] PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scripted React TUI E2E scenarios")
    parser.add_argument(
        "--scenario",
        choices=["all", "permission_file_io", "question_flow", "command_flow"],
        default="all",
    )
    args = parser.parse_args()

    if args.scenario in {"all", "permission_file_io"}:
        _run_permission_file_io()
    if args.scenario in {"all", "command_flow"}:
        _run_command_flow()
    if args.scenario == "question_flow":
        _run_question_flow()


if __name__ == "__main__":
    main()
