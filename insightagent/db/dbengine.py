"""统一查询执行层：DB-API + 线程池 + 超时 + 限行 + JSON 安全类型转换。"""

from __future__ import annotations

import asyncio
import datetime as _dt
import decimal
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from insightagent.db.catalog import CatalogError, DatabaseCatalog

logger = logging.getLogger("insightagent.dbengine")


@dataclass
class QueryOutcome:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


@dataclass
class SchemaTable:
    name: str
    columns: list[dict[str, str]] = field(default_factory=list)
    row_estimate: int | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return str(value)
    return value


def _row_to_json_safe(row: tuple) -> list[Any]:
    return [_json_safe(v) for v in row]


def _run_select(conn, sql: str, max_rows: int) -> tuple[list[str], list[list[Any]], bool, int]:
    started = time.perf_counter()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        columns = [str(desc[0]) for desc in (cursor.description or [])]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return columns, [_row_to_json_safe(r) for r in rows], truncated, int((time.perf_counter() - started) * 1000)
    finally:
        cursor.close()


def _sqlite_schema(conn) -> list[SchemaTable]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [r[0] for r in cursor.fetchall()]
        result: list[SchemaTable] = []
        for t in tables:
            cursor.execute(f'SELECT count(*) FROM "{t}"')
            count = int(cursor.fetchone()[0])
            cursor.execute(f'PRAGMA table_info("{t}")')
            cols = [{"name": r[1], "type": r[2] or "", "nullable": "no" if r[3] else "yes"} for r in cursor.fetchall()]
            result.append(SchemaTable(name=t, columns=cols, row_estimate=count))
        return result
    finally:
        cursor.close()


def _ansi_schema(conn, db_type: str) -> list[SchemaTable]:
    cursor = conn.cursor()
    try:
        if db_type == "mysql":
            cursor.execute(
                "SELECT table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_schema = DATABASE() "
                "ORDER BY table_name, ordinal_position"
            )
            rows = cursor.fetchall()
            tables: dict[str, SchemaTable] = {}
            for table_name, column_name, data_type, is_nullable in rows:
                t = tables.setdefault(str(table_name), SchemaTable(name=str(table_name)))
                t.columns.append({"name": str(column_name), "type": str(data_type), "nullable": str(is_nullable)})
            return list(tables.values())
        cursor.execute(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = current_schema() "
            "ORDER BY table_name, ordinal_position"
        )
        rows = cursor.fetchall()
        tables = {}
        for table_name, column_name, data_type, is_nullable in rows:
            t = tables.setdefault(str(table_name), SchemaTable(name=str(table_name)))
            t.columns.append({"name": str(column_name), "type": str(data_type), "nullable": str(is_nullable)})
        return list(tables.values())
    finally:
        cursor.close()


class QueryEngine:
    def __init__(self, catalog: DatabaseCatalog, max_rows: int = 100, timeout_seconds: int = 30) -> None:
        self._catalog = catalog
        self._max_rows = max_rows
        self._timeout = timeout_seconds

    async def execute_query(self, db_id: str, sql: str) -> QueryOutcome:
        logger.info("sql execute: db=%s sql=%r", db_id, " ".join(sql.split())[:160])

        def _do() -> QueryOutcome:
            conn = self._catalog.connect(db_id)
            try:
                columns, rows, truncated, elapsed = _run_select(conn, sql, self._max_rows)
                return QueryOutcome(columns=columns, rows=rows, row_count=len(rows), truncated=truncated, elapsed_ms=elapsed)
            finally:
                conn.close()

        try:
            outcome = await asyncio.wait_for(asyncio.to_thread(_do), timeout=self._timeout)
        except TimeoutError as exc:
            logger.warning("sql timeout: db=%s limit=%ss", db_id, self._timeout)
            raise CatalogError(f"查询超时（>{self._timeout}s），请缩小扫描范围或增加过滤条件") from exc
        except CatalogError:
            raise
        except Exception as exc:  # noqa: BLE001 - 数据库错误回传给模型改写
            logger.warning("sql failed: db=%s err=%s: %s", db_id, type(exc).__name__, str(exc)[:160])
            return QueryOutcome(columns=[], rows=[], row_count=0, truncated=False, elapsed_ms=0, error=f"{type(exc).__name__}: {exc}")
        logger.info("sql done: db=%s rows=%d truncated=%s elapsed_ms=%d", db_id, outcome.row_count, outcome.truncated, outcome.elapsed_ms)
        return outcome

    async def get_schema(self, db_id: str, table: str | None = None) -> list[SchemaTable]:
        entry = self._catalog.get(db_id)

        def _do() -> list[SchemaTable]:
            conn = self._catalog.connect(db_id)
            try:
                tables = _sqlite_schema(conn) if entry.type == "sqlite" else _ansi_schema(conn, entry.type)
                if table:
                    tables = [t for t in tables if t.name == table]
                return tables
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def ping(self, db_id: str) -> None:
        """连通性自检（check 命令用）。"""
        self._catalog.get(db_id)  # 校验数据源存在

        def _do() -> None:
            conn = self._catalog.connect(db_id)
            try:
                conn.cursor().execute("SELECT 1")
            finally:
                conn.close()

        await asyncio.to_thread(_do)
