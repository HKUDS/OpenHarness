"""SQL 只读安全校验：仅允许单条 SELECT/WITH 语句。"""

from __future__ import annotations

import re

# 去掉 -- 行注释与 /* */ 块注释
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

_FORBIDDEN_KEYWORDS = frozenset(
    ["INSERT", "UPDATE", "DELETE", "REPLACE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "MERGE", "CALL", "EXECUTE", "EXEC", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "ANALYZE", "SET", "RESET", "COPY", "LOAD", "UNLOAD", "LOCK", "UNLOCK", "OPTIMIZE", "HANDLER", "DO"]
)

_ALLOWED_STARTS = ("SELECT", "WITH")


class SQLSafetyError(ValueError):
    """SQL 未通过只读校验。"""


def strip_sql_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def _first_token(sql: str) -> str:
    return sql.strip().split(None, 1)[0].upper() if sql.strip() else ""


def _split_statements(sql: str) -> list[str]:
    """按顶层分号切分（忽略引号内的分号）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in sql:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == ";":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p for p in (part.strip() for part in parts) if p]


def validate_readonly_sql(sql: str) -> str:
    """校验并返回净化后的 SQL；不合法抛 SQLSafetyError（信息供模型改写）。"""
    if not sql or not sql.strip():
        raise SQLSafetyError("SQL 为空")
    cleaned = strip_sql_comments(sql)
    statements = _split_statements(cleaned)
    if len(statements) > 1:
        raise SQLSafetyError("仅允许单条 SQL 语句（检测到多条，请去掉分号后的附加语句）")
    first = _first_token(statements[0])
    if first not in _ALLOWED_STARTS:
        raise SQLSafetyError(f"仅允许只读查询（SELECT/WITH 开头），当前开头: {first or '<空>'}")
    for token in re.findall(r"[A-Za-z_]+", statements[0]):
        if token.upper() in _FORBIDDEN_KEYWORDS:
            raise SQLSafetyError(f"检测到禁用关键字: {token.upper()}，仅允许只读 SELECT 查询")
    return statements[0]
