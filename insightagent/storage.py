"""命名会话持久化（SQLite）：sessions / messages / turns 三表。

- sessions  会话元信息（插件集、模型、摘要、时间戳）
- messages  引擎完整消息序列（用于恢复运行时上下文）
- turns     每个用户回合的思考/回答/工具事件回放（用于前端历史重现）

旧版 JSON 快照目录（sessions/<sha1[:12]>/snapshot.json）在首次建库时自动迁移。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from insightagent.config import InsightConfig
from openharness.engine.messages import ConversationMessage, sanitize_conversation_messages


def _as_message_objects(messages: list[Any]) -> list[ConversationMessage]:
    """dict（旧 JSON 迁移/回放数据）与模型对象统一转为 ConversationMessage。"""
    out: list[ConversationMessage] = []
    for m in messages:
        if isinstance(m, ConversationMessage):
            out.append(m)
        elif isinstance(m, dict):
            try:
                out.append(ConversationMessage.model_validate(m))
            except Exception:  # noqa: BLE001 - 单条损坏跳过，不阻断整体
                continue
    return out

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  session_id TEXT PRIMARY KEY,
  plugins TEXT NOT NULL DEFAULT '[]',
  model TEXT NOT NULL DEFAULT '',
  system_prompt TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  message_count INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages(
  session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  PRIMARY KEY(session_id, seq)
);
CREATE TABLE IF NOT EXISTS turns(
  session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  thinking TEXT NOT NULL DEFAULT '',
  answer TEXT NOT NULL DEFAULT '',
  usage TEXT,
  error TEXT,
  events TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  PRIMARY KEY(session_id, seq)
);
"""


def _token(session_id: str) -> str:
    return hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:12]


def db_path(cfg: InsightConfig) -> Path:
    return cfg.sessions_dir / "sessions.db"


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


@contextmanager
def _open(cfg: InsightConfig) -> Iterator[sqlite3.Connection]:
    path = db_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        if fresh:
            _migrate_json_sessions(cfg, conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _write_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    plugins: list[str],
    model: str,
    system_prompt: str,
    messages: list[Any],
    summary: str,
    now: float,
    created_at: float | None = None,
) -> None:
    if created_at is None:
        row = conn.execute("SELECT created_at FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        created_at = row["created_at"] if row else now
    conn.execute(
        """INSERT INTO sessions(session_id,plugins,model,system_prompt,summary,message_count,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(session_id) DO UPDATE SET
             plugins=excluded.plugins, model=excluded.model, system_prompt=excluded.system_prompt,
             summary=excluded.summary, message_count=excluded.message_count, updated_at=excluded.updated_at""",
        (session_id, _json(plugins), model, system_prompt, summary, len(messages), created_at, now),
    )
    conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    conn.executemany(
        "INSERT INTO messages(session_id,seq,role,content) VALUES(?,?,?,?)",
        [
            (session_id, seq, str(m.get("role") or ""), _json(m))
            for seq, m in enumerate(messages)
        ],
    )


def _migrate_json_sessions(cfg: InsightConfig, conn: sqlite3.Connection) -> None:
    """一次性导入旧版 JSON 快照目录，成功后目录改名为 <token>-migrated。"""
    root = cfg.sessions_dir
    if not root.exists():
        return
    for sdir in root.iterdir():
        if not sdir.is_dir() or sdir.name.endswith("-migrated"):
            continue
        snap = sdir / "snapshot.json"
        if not snap.exists():
            continue
        try:
            payload = json.loads(snap.read_text(encoding="utf-8"))
            _write_session(
                conn,
                session_id=str(payload.get("session_id") or sdir.name),
                plugins=[str(p) for p in payload.get("plugins") or []],
                model=str(payload.get("model") or ""),
                system_prompt=str(payload.get("system_prompt") or ""),
                messages=list(payload.get("messages") or []),
                summary=str(payload.get("summary") or ""),
                now=float(payload.get("updated_at") or time.time()),
                created_at=float(payload.get("created_at") or time.time()),
            )
        except Exception:  # noqa: BLE001 - 单个损坏快照不阻断整体迁移
            continue
        try:
            sdir.rename(sdir.with_name(sdir.name + "-migrated"))
        except OSError:
            pass


def save_snapshot(
    cfg: InsightConfig,
    *,
    session_id: str,
    plugins: list[str],
    model: str,
    system_prompt: str,
    messages: Any,
    usage: Any = None,  # 兼容旧签名；用量已按回合记入 turns
    turn: dict[str, Any] | None = None,
) -> Path:
    """写入/更新命名会话；turn 非空时追加一条回合回放记录。"""
    msgs = sanitize_conversation_messages(_as_message_objects(list(messages)))
    summary = next((m.text.strip()[:80] for m in msgs if m.role == "user" and m.text.strip()), "")
    now = time.time()
    with _open(cfg) as conn:
        _write_session(
            conn,
            session_id=session_id,
            plugins=list(plugins),
            model=model,
            system_prompt=system_prompt,
            messages=[m.model_dump(mode="json") for m in msgs],
            summary=summary,
            now=now,
        )
        if turn is not None:
            seq_row = conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS n FROM turns WHERE session_id=?", (session_id,)
            ).fetchone()
            conn.execute(
                """INSERT INTO turns(session_id,seq,message,thinking,answer,usage,error,events,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    seq_row["n"],
                    str(turn.get("message") or ""),
                    str(turn.get("thinking") or ""),
                    str(turn.get("answer") or ""),
                    _json(turn.get("usage")) if turn.get("usage") is not None else None,
                    turn.get("error"),
                    _json(turn.get("events") or []),
                    now,
                ),
            )
    return db_path(cfg)


def load_snapshot(cfg: InsightConfig, session_id: str) -> dict[str, Any] | None:
    """读取会话快照（恢复运行时上下文用，含完整消息序列）。"""
    with _open(cfg) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            return None
        msgs = [
            json.loads(r["content"])
            for r in conn.execute(
                "SELECT content FROM messages WHERE session_id=? ORDER BY seq", (session_id,)
            )
        ]
        return {
            "app": "insightagent",
            "session_id": row["session_id"],
            "plugins": json.loads(row["plugins"]),
            "model": row["model"],
            "system_prompt": row["system_prompt"],
            "messages": msgs,
            "usage": None,
            "summary": row["summary"],
            "message_count": row["message_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def load_transcript(cfg: InsightConfig, session_id: str) -> dict[str, Any] | None:
    """读取会话回放数据：逐回合的用户输入/思考/回答/工具事件/用量。"""
    with _open(cfg) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            return None
        turns = []
        for r in conn.execute(
            "SELECT * FROM turns WHERE session_id=? ORDER BY seq", (session_id,)
        ):
            turns.append(
                {
                    "message": r["message"],
                    "thinking": r["thinking"],
                    "answer": r["answer"],
                    "usage": json.loads(r["usage"]) if r["usage"] else None,
                    "error": r["error"],
                    "events": json.loads(r["events"]),
                    "created_at": r["created_at"],
                }
            )
        return {
            "session_id": row["session_id"],
            "plugins": json.loads(row["plugins"]),
            "model": row["model"],
            "summary": row["summary"],
            "turns": turns,
        }


def list_sessions(cfg: InsightConfig, limit: int = 50) -> list[dict[str, Any]]:
    """按 updated_at 倒序列出命名会话元信息。"""
    with _open(cfg) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            "session_id": r["session_id"],
            "plugins": json.loads(r["plugins"]),
            "model": r["model"],
            "summary": r["summary"],
            "message_count": r["message_count"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def delete_session(cfg: InsightConfig, session_id: str) -> bool:
    """删除会话（三表级联清理）；不存在时返回 False。"""
    with _open(cfg) as conn:
        cur = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
    return cur.rowcount > 0
