"""mysql-query 插件工具工厂：由 insightagent.plugin_support 动态加载。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).parent


def _load(name: str):
    mod_name = f"_insightagent_mysqlquery_{name}"
    if mod_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(mod_name, _TOOLS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    return sys.modules[mod_name]


def build_tools(deps):
    """返回 mysql-query 插件的三个工具实例。"""
    db_list_cls = _load("db_list_tool").DBListTool
    db_schema_cls = _load("db_schema_tool").DBSchemaTool
    db_query_cls = _load("db_query_tool").DBQueryTool
    return [
        db_list_cls(deps.catalog),
        db_schema_cls(deps.catalog, deps.query_engine),
        db_query_cls(deps.catalog, deps.query_engine),
    ]
