"""db_query 工具：只读 SQL 执行。"""

from __future__ import annotations

import json

from pydantic import BaseModel

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

from insightagent.db.catalog import CatalogError, DatabaseCatalog
from insightagent.db.dbengine import QueryEngine
from insightagent.db.sqlsafety import SQLSafetyError, validate_readonly_sql


class DBQueryInput(BaseModel):
    db_id: str
    sql: str


class DBQueryTool(BaseTool):
    name = "db_query"
    description = (
        "对指定数据库执行只读 SELECT/WITH 查询，返回限行结果集。"
        "仅允许单条只读语句；执行报错时会返回错误详情，请据此修正 SQL 后重试。"
    )
    input_model = DBQueryInput

    def __init__(self, catalog: DatabaseCatalog, engine: QueryEngine) -> None:
        self._catalog = catalog
        self._engine = engine

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: DBQueryInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            sql = validate_readonly_sql(arguments.sql)
        except SQLSafetyError as exc:
            return ToolResult(is_error=True, output=f"SQL 校验失败: {exc}")
        try:
            self._catalog.get(arguments.db_id)
        except CatalogError as exc:
            return ToolResult(is_error=True, output=str(exc))
        outcome = await self._engine.execute_query(arguments.db_id, sql)
        payload = outcome.to_payload()
        if outcome.error:
            payload["hint"] = "查询执行失败，请根据 error 修正 SQL（表名/列名/方言）后重试。"
            return ToolResult(is_error=True, output=json.dumps(payload, ensure_ascii=False))
        if outcome.truncated:
            payload["hint"] = f"结果超过行数上限被截断，如需完整统计请改写为聚合查询。"
        return ToolResult(output=json.dumps(payload, ensure_ascii=False))
