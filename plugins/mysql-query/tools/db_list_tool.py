"""db_list 工具：列出数据库目录。"""

from __future__ import annotations

import json

from pydantic import BaseModel

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

from insightagent.db.catalog import DatabaseCatalog


class DBListInput(BaseModel):
    """db_list 无参数。"""


class DBListTool(BaseTool):
    name = "db_list"
    description = "列出所有可查询的数据库目录（id、类型、业务描述）。回答数据问题前先调用它定位目标库。"
    input_model = DBListInput

    def __init__(self, catalog: DatabaseCatalog) -> None:
        self._catalog = catalog

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        entries = self._catalog.entries
        if not entries:
            return ToolResult(is_error=True, output="未配置数据库目录（~/.insightagent/config.yaml 的 databases 段为空），无法执行数据查询。")
        payload = [{"id": e.id, "type": e.type, "description": e.description} for e in entries]
        return ToolResult(output=json.dumps({"databases": payload}, ensure_ascii=False, indent=2))
