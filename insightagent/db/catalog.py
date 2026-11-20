"""多数据库目录：按配置惰性建立 DB-API 连接（mysql/postgres/sqlite）。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from insightagent.config import DatabaseEntry, InsightConfig

logger = logging.getLogger("insightagent.catalog")


class CatalogError(RuntimeError):
    """数据库目录操作失败（未知库/驱动缺失/连接失败）。"""


def _mysql_conn(dsn: str):
    import pymysql  # 惰性导入

    parsed = urlparse(dsn)
    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/").lstrip("/") or None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
        connect_timeout=10,
    )


def _postgres_conn(dsn: str):
    import psycopg  # 惰性导入

    return psycopg.connect(dsn.removeprefix("postgres://").replace("postgres+psycopg://", "postgresql://", 1) if dsn.startswith("postgres://") else dsn, connect_timeout=10)


def _sqlite_conn(dsn: str):
    path = dsn
    for prefix in ("sqlite:///", "sqlite://", "sqlite:"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    path = unquote(path)
    if not path or path == ":memory:":
        return sqlite3.connect(":memory:")
    resolved = Path(path.strip("/\\")) if not Path(path).is_absolute() else Path(path)
    if not Path(path).is_absolute() and not resolved.exists():
        # Windows 下去掉误判的前导分隔符再解析相对路径
        alt = Path(path.replace("\\", "/").lstrip("/"))
        resolved = alt if alt.exists() else resolved
    return sqlite3.connect(str(resolved), timeout=10)


_DRIVERS = {"mysql": _mysql_conn, "postgres": _postgres_conn, "sqlite": _sqlite_conn}


class DatabaseCatalog:
    """持有 databases 配置，按 db_id 建立一次性连接。"""

    def __init__(self, config: InsightConfig) -> None:
        self._entries: dict[str, DatabaseEntry] = {entry.id: entry for entry in config.databases}
        self._config = config

    @property
    def entries(self) -> list[DatabaseEntry]:
        return list(self._entries.values())

    def get(self, db_id: str) -> DatabaseEntry:
        try:
            return self._entries[db_id]
        except KeyError as exc:
            raise CatalogError(f"未知数据库: {db_id!r}，可用: {sorted(self._entries)}") from exc

    def connect(self, db_id: str):
        entry = self.get(db_id)
        factory = _DRIVERS[entry.type]
        try:
            conn = factory(entry.dsn)
        except ImportError as exc:
            raise CatalogError(
                f"数据库 {db_id!r} 类型 {entry.type} 缺少驱动，请安装: uv sync --extra db"
            ) from exc
        except Exception as exc:
            logger.warning("db connect failed: %s (%s)", db_id, exc)
            raise CatalogError(f"连接数据库 {db_id!r} 失败: {exc}") from exc
        logger.debug("db connected: %s type=%s", db_id, entry.type)
        return conn
