"""Dongtian memory integration (optional).

This module reads a local Dongtian "palace" SQLite database and pulls a few
relevant snippets for prompt injection. It intentionally uses only SQLite FTS5
queries (no embedding API calls) so it works offline and doesn't add latency
from external services.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DongtianSearchHit:
    """One search hit from the Dongtian palace database."""

    id: int
    wing: str
    room: str
    source: str
    source_ts: str
    content: str
    score: float | None = None


def search_dongtian_fts(
    query: str,
    *,
    db_path: str = "~/.dongtian/palace.db",
    wing: str | None = None,
    room: str | None = None,
    limit: int = 5,
    timeout_seconds: float = 0.2,
) -> list[DongtianSearchHit]:
    """Search a Dongtian palace DB via FTS5 (keyword-only).

    Returns an empty list when the DB is missing, locked, or the schema isn't
    compatible with Dongtian.
    """
    resolved = Path(db_path).expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        # Nonexistent paths can fail resolve(); keep the expanded path.
        pass

    # Avoid accidental creation of a new DB file: open read-only.
    uri = resolved.as_uri() + "?mode=ro"

    limit = int(limit)
    if limit <= 0:
        return []
    if limit > 20:
        limit = 20

    query = (query or "").strip()
    if not query:
        return []

    # Try the raw query first; if FTS syntax breaks, fall back to token OR query.
    candidates = [query]
    token_query = _tokenize_to_fts_query(query)
    if token_query and token_query != query:
        candidates.append(token_query)

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(
            uri,
            uri=True,
            timeout=timeout_seconds,
        )
        conn.row_factory = sqlite3.Row
        for q in candidates:
            hits = _search_once(conn, q, wing=wing, room=room, limit=limit)
            if hits:
                return hits
        return []
    except (sqlite3.OperationalError, sqlite3.DatabaseError, ValueError):
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _search_once(
    conn: sqlite3.Connection,
    query: str,
    *,
    wing: str | None,
    room: str | None,
    limit: int,
) -> list[DongtianSearchHit]:
    clauses = ["drawers_fts MATCH ?"]
    params: list[object] = [query]
    if wing:
        clauses.append("w.name = ?")
        params.append(wing)
    if room:
        clauses.append("r.name = ?")
        params.append(room)
    params.append(limit)

    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT d.id, d.content, d.source, d.source_ts, w.name AS wing, r.name AS room,
               bm25(drawers_fts) AS score
        FROM drawers_fts
        JOIN drawers d ON d.id = drawers_fts.rowid
        JOIN rooms r ON r.id = d.room_id
        JOIN wings w ON w.id = r.wing_id
        WHERE {where}
        ORDER BY score
        LIMIT ?
        """,
        params,
    ).fetchall()

    hits: list[DongtianSearchHit] = []
    for row in rows:
        hits.append(
            DongtianSearchHit(
                id=int(row["id"]),
                content=str(row["content"] or ""),
                source=str(row["source"] or ""),
                source_ts=str(row["source_ts"] or ""),
                wing=str(row["wing"] or ""),
                room=str(row["room"] or ""),
                score=float(row["score"]) if row["score"] is not None else None,
            )
        )
    return hits


def _tokenize_to_fts_query(text: str) -> str:
    """Convert *text* to a conservative FTS query that avoids syntax errors."""
    tokens: list[str] = []

    # ASCII word tokens.
    for tok in re.findall(r"[A-Za-z0-9_]+", text.lower()):
        if len(tok) >= 3:
            tokens.append(tok)

    # Han ideographs: each character is meaningful; include a few.
    tokens.extend(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for tok in tokens:
        if tok in seen:
            continue
        seen.add(tok)
        uniq.append(tok)
        if len(uniq) >= 20:
            break

    return " OR ".join(uniq)
