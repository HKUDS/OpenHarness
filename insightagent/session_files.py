"""会话文件：按会话隔离的上传/产出目录，及 read/write 两个会话文件工具。

目录布局：<sessions.dir>/files/<session_id>/{uploads,outputs}
- uploads：用户随对话上传的附件；
- outputs：智能体通过 write_session_file 产出的文件（可经 /artifacts 下载）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from insightagent.config import InsightConfig
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_UNSAFE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_READ_CHARS = 40000


def safe_name(name: str) -> str:
    """清洗文件名：去路径分隔、替换非法字符，限长。"""
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    name = _UNSAFE.sub("_", name).strip("._") or "file"
    return name[:120]


def safe_relpath(name: str) -> str:
    """清洗相对路径：逐段 safe_name，保留目录层级（无 .. / 绝对路径）。"""
    parts = [safe_name(p) for p in (name or "").replace("\\", "/").split("/") if p.strip()]
    return "/".join(parts[:8])


def resolve_under(root: Path, name: str) -> Path:
    """把相对路径解析到 root 之下，保证不越出 root。"""
    rel = safe_relpath(name)
    if not rel:
        return root / "file"
    path = (root / rel).resolve()
    root_resolved = root.resolve()
    if root_resolved == path or root_resolved in path.parents:
        return path
    return root / rel.split("/")[-1]  # 兜底：退化到最后一段（仍限 root 内）


def _root(cfg: InsightConfig, session_id: str) -> Path:
    return cfg.sessions_dir / "files" / safe_name(session_id)


def uploads_dir(cfg: InsightConfig, session_id: str) -> Path:
    return _root(cfg, session_id) / "uploads"


def outputs_dir(cfg: InsightConfig, session_id: str) -> Path:
    return _root(cfg, session_id) / "outputs"


def list_dir(root: Path) -> list[dict[str, Any]]:
    """递归列出目录内文件（相对路径名/大小/修改时间），按时间倒序。"""
    if not root.is_dir():
        return []
    items = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        st = p.stat()
        items.append({"name": p.relative_to(root).as_posix(), "size": st.st_size, "modified_at": st.st_mtime})
    items.sort(key=lambda x: -x["modified_at"])
    return items


class _ReadInput(BaseModel):
    path: str


class ReadSessionFileTool(BaseTool):
    """读取当前会话的文件（先查 uploads 再查 outputs），文本截断返回。"""

    name = "read_session_file"
    description = (
        "读取当前会话目录中的文件内容（用户上传的附件或此前产出的文件）。"
        "path 为文件名；先在 uploads 再在 outputs 中查找；超长文本自动截断。"
    )
    input_model = _ReadInput

    def __init__(self, cfg: InsightConfig, session_id: str) -> None:
        self._cfg = cfg
        self._sid = session_id

    async def execute(self, arguments: _ReadInput, context: ToolExecutionContext) -> ToolResult:
        del context
        fname = safe_name(arguments.path)
        for root in (uploads_dir(self._cfg, self._sid), outputs_dir(self._cfg, self._sid)):
            path = root / fname
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > MAX_READ_CHARS:
                    text = text[:MAX_READ_CHARS] + f"\n…（已截断，原文件共 {len(text)} 字符）"
                return ToolResult(output=text or "（空文件）")
        return ToolResult(output=f"文件不存在: {fname}（当前会话 uploads/outputs 中均未找到）", is_error=True)


class _WriteInput(BaseModel):
    filename: str
    content: str


class WriteSessionFileTool(BaseTool):
    """把文本写入当前会话 outputs 目录，返回服务端保存路径。"""

    name = "write_session_file"
    description = (
        "把文本内容保存为当前会话的产出文件（服务端 outputs 目录），返回保存路径；"
        "适合保存报告、分析结果、CSV 数据等产物，用户可在界面的「产出」面板下载。"
    )
    input_model = _WriteInput

    def __init__(self, cfg: InsightConfig, session_id: str) -> None:
        self._cfg = cfg
        self._sid = session_id

    async def execute(self, arguments: _WriteInput, context: ToolExecutionContext) -> ToolResult:
        del context
        fname = safe_name(arguments.filename)
        root = outputs_dir(self._cfg, self._sid)
        root.mkdir(parents=True, exist_ok=True)
        path = root / fname
        path.write_text(arguments.content, encoding="utf-8")
        return ToolResult(output=f"已保存: {path}（{len(arguments.content)} 字符）")
