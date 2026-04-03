"""Scripted React TUI end-to-end checks using the real CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import pexpect

from openharness.config.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend" / "terminal"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _spawn_oh(prompt: str | None = None, *, env: dict[str, str] | None = None) -> pexpect.spawn:
    args = ["run", "oh"]
    if prompt is not None:
        args.append(prompt)
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


def _spawn_frontend(config: dict[str, object], *, env: dict[str, str] | None = None) -> pexpect.spawn:
    frontend_env = (env or os.environ).copy()
    frontend_env["OPENHARNESS_FRONTEND_CONFIG"] = json.dumps(config)
    child = pexpect.spawn(
        "npm",
        ["exec", "--", "tsx", "src/index.tsx"],
        cwd=str(FRONTEND_DIR),
        env=frontend_env,
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


def _normalize_terminal_text(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text).replace("\r", "")


def _wait_for_text(child: pexpect.spawn, text: str, *, timeout: float = 20.0) -> str:
    deadline = time.time() + timeout
    chunks: list[str] = []
    while time.time() < deadline:
        try:
            chunks.append(child.read_nonblocking(size=4096, timeout=1))
        except pexpect.TIMEOUT:
            continue
        except pexpect.EOF:
            break
        normalized = _normalize_terminal_text("".join(chunks))
        if text in normalized:
            return normalized
    normalized = _normalize_terminal_text("".join(chunks))
    raise AssertionError(f"Timed out waiting for {text!r}. Output tail:\n{normalized[-2000:]}")


def _drain_output(child: pexpect.spawn, *, timeout: float = 2.0) -> str:
    deadline = time.time() + timeout
    chunks: list[str] = []
    while time.time() < deadline:
        try:
            chunks.append(child.read_nonblocking(size=4096, timeout=0.5))
        except (pexpect.TIMEOUT, pexpect.EOF):
            break
    return _normalize_terminal_text("".join(chunks))


def _isolated_env(
    permission_mode: str = "full_auto",
    *,
    raw_return: bool = True,
) -> tuple[tempfile.TemporaryDirectory[str], dict[str, str]]:
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
    if raw_return:
        env["OPENHARNESS_FRONTEND_RAW_RETURN"] = "1"
    else:
        env.pop("OPENHARNESS_FRONTEND_RAW_RETURN", None)
    return temp_dir, env


def _run_no_duplicate_submit() -> None:
    temp_dir = tempfile.TemporaryDirectory(prefix="openharness-react-tui-submit-")
    temp_root = Path(temp_dir.name)
    count_path = temp_root / "submit_count.txt"
    backend_script = temp_root / "stub_backend.py"
    backend_script.write_text(
        """
import json
import sys
from pathlib import Path

PREFIX = "OHJSON:"
COUNT_PATH = Path(sys.argv[1])
submit_count = 0


def emit(event):
    sys.stdout.write(PREFIX + json.dumps(event) + "\\n")
    sys.stdout.flush()


emit(
    {
        "type": "ready",
        "state": {
            "model": "stub-model",
            "cwd": str(Path.cwd()),
            "permission_mode": "Default",
        },
        "tasks": [],
        "commands": [],
        "mcp_servers": [],
        "bridge_sessions": [],
    }
)

for raw in sys.stdin:
    request = json.loads(raw)
    request_type = request.get("type")
    if request_type == "submit_line":
        submit_count += 1
        COUNT_PATH.write_text(str(submit_count), encoding="utf-8")
        emit({"type": "transcript_item", "item": {"role": "user", "text": request.get("line", "")}})
        emit({"type": "assistant_complete", "message": "ACK", "item": {"role": "assistant", "text": "ACK"}})
        emit({"type": "line_complete"})
    elif request_type == "shutdown":
        emit({"type": "shutdown"})
        break
""".strip()
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("OPENHARNESS_FRONTEND_RAW_RETURN", None)
    child = _spawn_frontend(
        {
            "backend_command": [sys.executable, str(backend_script), str(count_path)],
            "initial_prompt": None,
        },
        env=env,
    )
    try:
        print("[react_tui_no_duplicate_submit] waiting for input prompt")
        _wait_for_text(child, "stub-model", timeout=30)
        time.sleep(1)
        child.send("hi")
        time.sleep(0.1)
        child.send("\r")
        output = _wait_for_text(child, "ACK", timeout=20)
        output += _drain_output(child, timeout=2)
    finally:
        child.sendcontrol("c")
        try:
            child.expect(pexpect.EOF, timeout=5)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
        child.close(force=True)

    deadline = time.time() + 5
    while not count_path.exists() and time.time() < deadline:
        time.sleep(0.1)

    submit_count = int(count_path.read_text(encoding="utf-8").strip())
    temp_dir.cleanup()

    matches = output.count("ACK")
    assert submit_count == 1, f"Expected one submit_line request, found {submit_count}. Output tail:\n{output[-2000:]}"
    assert matches >= 1, f"Expected assistant acknowledgement in output. Output tail:\n{output[-2000:]}"
    print("[react_tui_no_duplicate_submit] PASS")


def _run_permission_file_io() -> None:
    path = ROOT / "react_tui_smoke.txt"
    if path.exists():
        path.unlink()
    temp_dir, env = _isolated_env()
    child = _spawn_oh(
        "You are running a React TUI end-to-end test. "
        "Use write_file to create react_tui_smoke.txt with exact content REACT_TUI_OK, "
        "then use read_file to verify it, then reply with exactly FINAL_OK_REACT_TUI.",
        env=env,
    )
    try:
        print("[react_tui_permission_file_io] waiting for app shell")
        child.expect("OpenHarness React TUI")
        child.expect("model=kimi-k2.5")
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
    child = _spawn_oh(
        "You are running a React TUI question flow test. "
        "Use ask_user_question to ask for a color. "
        "After the answer arrives, use write_file to create react_tui_question.txt with that exact answer, "
        "then use read_file to verify it, then reply with exactly FINAL_OK_REACT_TUI_QUESTION.",
        env=env,
    )
    try:
        child.expect("OpenHarness React TUI")
        child.expect("model=kimi-k2.5")
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
            "/permissions set full_auto",
            "/effort high",
            "/passes 3",
            "/status",
            "Reply with exactly FINAL_OK_REACT_TUI_COMMANDS.",
        ]
    )
    child = _spawn_oh(env=env)
    try:
        print("[react_tui_command_flow] waiting for app shell")
        child.expect("OpenHarness React TUI")
        child.expect("model=kimi-k2.5")
        child.expect("Permission mode set to full_auto")
        print("[react_tui_command_flow] waiting for effort confirmation")
        child.expect("Reasoning effort set to high.")
        print("[react_tui_command_flow] waiting for passes confirmation")
        child.expect("Pass count set to 3.")
        print("[react_tui_command_flow] waiting for status output")
        child.expect("Effort: high")
        child.expect("Passes: 3")
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
        choices=["all", "permission_file_io", "question_flow", "command_flow", "no_duplicate_submit"],
        default="all",
    )
    args = parser.parse_args()

    if args.scenario in {"all", "no_duplicate_submit"}:
        _run_no_duplicate_submit()
    if args.scenario in {"all", "permission_file_io"}:
        _run_permission_file_io()
    if args.scenario in {"all", "command_flow"}:
        _run_command_flow()
    if args.scenario == "question_flow":
        _run_question_flow()


if __name__ == "__main__":
    main()
