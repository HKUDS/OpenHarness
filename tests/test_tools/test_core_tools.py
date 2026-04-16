"""Tests for built-in tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from openharness.tools.bash_tool import BashTool, BashToolInput
from openharness.tools.base import ToolExecutionContext
from openharness.tools.brief_tool import BriefTool, BriefToolInput
from openharness.tools.cron_create_tool import CronCreateTool, CronCreateToolInput
from openharness.tools.cron_delete_tool import CronDeleteTool, CronDeleteToolInput
from openharness.tools.cron_list_tool import CronListTool, CronListToolInput
from openharness.tools.config_tool import ConfigTool, ConfigToolInput
from openharness.tools.enter_worktree_tool import EnterWorktreeTool, EnterWorktreeToolInput
from openharness.tools.exit_worktree_tool import ExitWorktreeTool, ExitWorktreeToolInput
from openharness.tools.file_edit_tool import FileEditTool, FileEditToolInput
from openharness.tools.file_read_tool import FileReadTool, FileReadToolInput
from openharness.tools.file_write_tool import FileWriteTool, FileWriteToolInput
from openharness.tools.glob_tool import GlobTool, GlobToolInput
from openharness.tools.grep_tool import GrepTool, GrepToolInput
from openharness.tools.lsp_tool import LspTool, LspToolInput
from openharness.tools.notebook_edit_tool import NotebookEditTool, NotebookEditToolInput
from openharness.tools.remote_trigger_tool import RemoteTriggerTool, RemoteTriggerToolInput
from openharness.tools.skill_tool import SkillTool, SkillToolInput
from openharness.tools.todo_write_tool import TodoWriteTool, TodoWriteToolInput
from openharness.tools.tool_search_tool import ToolSearchTool, ToolSearchToolInput
from openharness.tools import create_default_tool_registry


@pytest.mark.asyncio
async def test_file_write_read_and_edit(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)

    write_result = await FileWriteTool().execute(
        FileWriteToolInput(path="notes.txt", content="one\ntwo\nthree\n"),
        context,
    )
    assert write_result.is_error is False
    assert (tmp_path / "notes.txt").exists()

    read_result = await FileReadTool().execute(
        FileReadToolInput(path="notes.txt", offset=1, limit=2),
        context,
    )
    assert "2\ttwo" in read_result.output
    assert "3\tthree" in read_result.output

    edit_result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="two", new_str="TWO"),
        context,
    )
    assert edit_result.is_error is False
    assert "TWO" in (tmp_path / "notes.txt").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_glob_and_grep(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")

    glob_result = await GlobTool().execute(GlobToolInput(pattern="*.py"), context)
    assert glob_result.output.splitlines() == ["a.py", "b.py"]

    grep_result = await GrepTool().execute(
        GrepToolInput(pattern=r"def\s+beta", file_glob="*.py"),
        context,
    )
    assert "b.py:1:def beta():" in grep_result.output

    file_root_result = await GrepTool().execute(
        GrepToolInput(pattern=r"def\s+alpha", root="a.py"),
        context,
    )
    assert "a.py:1:def alpha():" in file_root_result.output


@pytest.mark.asyncio
async def test_bash_tool_runs_command(tmp_path: Path):
    result = await BashTool().execute(
        BashToolInput(command="printf 'hello'"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert result.is_error is False
    assert result.output == "hello"


@pytest.mark.asyncio
async def test_tool_search_and_brief_tools(tmp_path: Path):
    registry = create_default_tool_registry()
    context = ToolExecutionContext(cwd=tmp_path, metadata={"tool_registry": registry})

    search_result = await ToolSearchTool().execute(
        ToolSearchToolInput(query="file"),
        context,
    )
    assert "read_file" in search_result.output

    brief_result = await BriefTool().execute(
        BriefToolInput(text="abcdefghijklmnopqrstuvwxyz", max_chars=20),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert brief_result.output == "abcdefghijklmnopqrst..."


@pytest.mark.asyncio
async def test_skill_todo_and_config_tools(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True)
    pytest_dir = skills_dir / "pytest"
    pytest_dir.mkdir()
    (pytest_dir / "SKILL.md").write_text("# Pytest\nHelpful pytest notes.\n", encoding="utf-8")

    skill_result = await SkillTool().execute(
        SkillToolInput(name="Pytest"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert "Helpful pytest notes." in skill_result.output

    todo_result = await TodoWriteTool().execute(
        TodoWriteToolInput(item="wire commands"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert todo_result.is_error is False
    assert "wire commands" in (tmp_path / "TODO.md").read_text(encoding="utf-8")

    config_result = await ConfigTool().execute(
        ConfigToolInput(action="set", key="theme", value="solarized"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert config_result.output == "Updated theme"


@pytest.mark.asyncio
async def test_todo_write_upsert(tmp_path: Path):
    tool = TodoWriteTool()
    ctx = ToolExecutionContext(cwd=tmp_path)

    await tool.execute(TodoWriteToolInput(item="task A"), ctx)
    await tool.execute(TodoWriteToolInput(item="task B"), ctx)

    # Marking done should update in-place, not append a duplicate
    result = await tool.execute(TodoWriteToolInput(item="task A", checked=True), ctx)
    assert result.is_error is False

    content = (tmp_path / "TODO.md").read_text(encoding="utf-8")
    assert content.count("task A") == 1
    assert "- [x] task A" in content
    assert "- [ ] task A" not in content
    assert "- [ ] task B" in content

    # Calling again with same state is a no-op
    noop = await tool.execute(TodoWriteToolInput(item="task A", checked=True), ctx)
    assert "No change" in noop.output
    assert (tmp_path / "TODO.md").read_text(encoding="utf-8").count("task A") == 1


@pytest.mark.asyncio
async def test_notebook_edit_tool(tmp_path: Path):
    result = await NotebookEditTool().execute(
        NotebookEditToolInput(path="demo.ipynb", cell_index=0, new_source="print('nb ok')\n"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert result.is_error is False
    assert "demo.ipynb" in result.output
    assert "nb ok" in (tmp_path / "demo.ipynb").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_lsp_tool(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "utils.py").write_text(
        'def greet(name):\n    """Return a greeting."""\n    return f"hi {name}"\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "app.py").write_text(
        "from pkg.utils import greet\n\nprint(greet('world'))\n",
        encoding="utf-8",
    )
    context = ToolExecutionContext(cwd=tmp_path)

    document_symbols = await LspTool().execute(
        LspToolInput(operation="document_symbol", file_path="pkg/utils.py"),
        context,
    )
    assert "function greet" in document_symbols.output

    definition = await LspTool().execute(
        LspToolInput(operation="go_to_definition", file_path="pkg/app.py", symbol="greet"),
        context,
    )
    assert "pkg/utils.py:1:1" in definition.output

    references = await LspTool().execute(
        LspToolInput(operation="find_references", file_path="pkg/app.py", symbol="greet"),
        context,
    )
    assert "pkg/app.py:1:from pkg.utils import greet" in references.output

    hover = await LspTool().execute(
        LspToolInput(operation="hover", file_path="pkg/app.py", symbol="greet"),
        context,
    )
    assert "Return a greeting." in hover.output


@pytest.mark.asyncio
async def test_worktree_tools(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "openharness@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "OpenHarness Tests"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "demo.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    enter_result = await EnterWorktreeTool().execute(
        EnterWorktreeToolInput(branch="feature/demo"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert enter_result.is_error is False
    worktree_path = Path(enter_result.output.split("Path: ", 1)[1].strip())
    assert worktree_path.exists()

    exit_result = await ExitWorktreeTool().execute(
        ExitWorktreeToolInput(path=str(worktree_path)),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert exit_result.is_error is False
    assert not worktree_path.exists()


@pytest.mark.asyncio
async def test_cron_and_remote_trigger_tools(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await CronCreateTool().execute(
        CronCreateToolInput(name="nightly", schedule="0 0 * * *", command="printf 'CRON_OK'"),
        context,
    )
    assert create_result.is_error is False

    list_result = await CronListTool().execute(CronListToolInput(), context)
    assert "nightly" in list_result.output

    trigger_result = await RemoteTriggerTool().execute(
        RemoteTriggerToolInput(name="nightly"),
        context,
    )
    assert trigger_result.is_error is False
    assert "CRON_OK" in trigger_result.output

    delete_result = await CronDeleteTool().execute(
        CronDeleteToolInput(name="nightly"),
        context,
    )
    assert delete_result.is_error is False
