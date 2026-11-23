"""db_schema 工具：查看库的表/列结构。"""

from __future__ import annotations

import json

from pydantic import BaseModel

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

from insightagent.db.catalog import CatalogError, DatabaseCatalog
from insightagent.db.dbengine import QueryEngine


class DBSchemaInput(BaseModel):
    db_id: str
    table: str | None = None


class DBSchemaTool(BaseTool):
    name = "db_schema"
    description = "查看指定数据库的表结构（表名、列名、类型、可空、行数估计）。生成 SQL 前先调用它确认表与字段。"
    input_model = DBSchemaInput

    def __init__(self, catalog: DatabaseCatalog, engine: QueryEngine) -> None:
        self._catalog = catalog
        self._engine = engine

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: DBSchemaInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            self._catalog.get(arguments.db_id)
            tables = await self._engine.get_schema(arguments.db_id, arguments.table)
        except CatalogError as exc:
            return ToolResult(is_error=True, output=str(exc))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(is_error=True, output=f"读取 schema 失败: {exc}")
        if not tables:
            hint = f"（过滤条件 table={arguments.table!r}）" if arguments.table else ""
            return ToolResult(is_error=True, output=f"未找到任何表 {hint}，请确认 db_id 或表名。")
        payload = [
            {"table": t.name, "row_estimate": t.row_estimate, "columns": t.columns}
            for t in tables
        ]
        return ToolResult(output=json.dumps({"db_id": arguments.db_id, "tables": payload}, ensure_ascii=False, indent=2))
