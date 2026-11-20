"""report-search 插件工具工厂：由 insightagent.plugin_support 动态加载。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).parent
_MANIFEST = _TOOLS_DIR.parent / "plugin.json"


def _load(name: str):
    mod_name = f"_insightagent_reportsearch_{name}"
    if mod_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(mod_name, _TOOLS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    return sys.modules[mod_name]


def _mcp_settings() -> dict:
    """插件清单里的 mcp 段：检索服务名、工具名、collection。"""
    try:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return manifest.get("mcp") or {}


def build_tools(deps):
    """返回 report-search 插件工具实例（检索后端为 MCP 报表检索服务）。"""
    mcp = _mcp_settings()
    cls = _load("report_search_tool").ReportSearchTool
    return [
        cls(
            deps.config,
            server=str(mcp.get("server") or "报表检索"),
            tool=str(mcp.get("tool") or "search"),
            collection=str(mcp.get("collection") or ""),
        )
    ]
