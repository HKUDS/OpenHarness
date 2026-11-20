"""多用户管理：用户表（SQLite）、token 鉴权、每用户数据目录与独立 openharness home。

目录布局（base = 系统 cfg.sessions_dir）：
- <base>/users.db                          用户表 + token 表
- <base>/users/<user_id>/sessions/         该用户全部会话数据（sessions.db + files/）
- <base>/users/<user_id>/home/             该用户独立 openharness home
    ├── settings.json                      用户模型 profiles / active_profile / mcp_servers
    ├── credentials.json                   用户自己的 API Key（文件后端）
    ├── skills/                            用户自定义技能
    └── plugins/                           用户自定义插件
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from insightagent.config import InsightConfig

TOKEN_TTL_SECONDS = 7 * 24 * 3600
_PBKDF2_ITERATIONS = 120_000
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-\u4e00-\u9fff]{2,32}$")

_ENV_LOCK = asyncio.Lock()


class UserError(ValueError):
    """用户操作非法（用户名/密码规则、重复注册、旧密码错误等）。"""


# ── 目录布局 ──────────────────────────────────────────────────────────────


def users_root(cfg: InsightConfig) -> Path:
    return cfg.sessions_dir / "users"


def users_db_path(cfg: InsightConfig) -> Path:
    return users_root(cfg) / "users.db"


def user_dir(cfg: InsightConfig, user_id: str) -> Path:
    return users_root(cfg) / _safe_uid(user_id)


def user_sessions_dir(cfg: InsightConfig, user_id: str) -> Path:
    return user_dir(cfg, user_id) / "sessions"


def user_home_dir(cfg: InsightConfig, user_id: str) -> Path:
    return user_dir(cfg, user_id) / "home"


def user_skills_dir(cfg: InsightConfig, user_id: str) -> Path:
    return user_home_dir(cfg, user_id) / "skills"


def user_plugins_dir(cfg: InsightConfig, user_id: str) -> Path:
    return user_home_dir(cfg, user_id) / "plugins"


def user_settings_path(cfg: InsightConfig, user_id: str) -> Path:
    return user_home_dir(cfg, user_id) / "settings.json"


def user_credentials_path(cfg: InsightConfig, user_id: str) -> Path:
    return user_home_dir(cfg, user_id) / "credentials.json"


def _safe_uid(user_id: str) -> str:
    return re.sub(r"[^\w\-]", "_", user_id)[:64] or "anonymous"


# ── openharness home 环境切换（多用户隔离的核心） ────────────────────────


_UNSET = object()
_SYSTEM_HOME: Any = _UNSET


def set_system_home(home: Path | None) -> None:
    """服务启动时固化系统 home（此后 env 切换不影响 system_home() 语义）。"""
    global _SYSTEM_HOME
    _SYSTEM_HOME = Path(home).expanduser().resolve() if home else None


def system_home() -> Path | None:
    """系统级 openharness home：启动时固化值，否则取当前 env（默认 ~/.openharness）。"""
    if _SYSTEM_HOME is not _UNSET:
        return _SYSTEM_HOME  # type: ignore[return-value]
    env = os.environ.get("OPENHARNESS_CONFIG_DIR")
    return Path(env).expanduser().resolve() if env else None


def _set_env_home(home: Path | None) -> str | None:
    """home=None 表示切回系统 home（而非清空 env）。禁止嵌套切换（全局锁不可重入）。"""
    target = home if home is not None else system_home()
    prev = os.environ.get("OPENHARNESS_CONFIG_DIR")
    if target is None:
        os.environ.pop("OPENHARNESS_CONFIG_DIR", None)
    else:
        os.environ["OPENHARNESS_CONFIG_DIR"] = str(target)
    return prev


def _restore_env_home(prev: str | None) -> None:
    if prev is None:
        os.environ.pop("OPENHARNESS_CONFIG_DIR", None)
    else:
        os.environ["OPENHARNESS_CONFIG_DIR"] = prev


@asynccontextmanager
async def openharness_home(home: Path | None) -> Iterator[None]:
    """异步安全地切换 OPENHARNESS_CONFIG_DIR（全局锁串行化，防止跨用户并发串号）。

    home=None 表示切回系统默认（~/.openharness）。系统 home 由服务启动时写入 env。
    """
    async with _ENV_LOCK:
        prev = _set_env_home(home)
        try:
            yield
        finally:
            _restore_env_home(prev)


@contextmanager
def openharness_home_sync(home: Path | None) -> Iterator[None]:
    """同步版：仅限单线程事件循环内的纯同步代码段使用（期间不得 await）。"""
    prev = _set_env_home(home)
    try:
        yield
    finally:
        _restore_env_home(prev)


def disable_keyring_for_multuser() -> None:
    """多用户服务强制凭据走文件后端（各用户 home 独立），避免系统 keyring 全局串号。"""
    try:
        from openharness.auth import storage as auth_storage

        auth_storage._keyring_checked = True
        auth_storage._keyring_usable = False
    except Exception:  # noqa: BLE001
        pass


# ── 用户表 ────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens(
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
"""


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    )
    return digest.hex()


@contextmanager
def _open_db(cfg: InsightConfig) -> Iterator[sqlite3.Connection]:
    path = users_db_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _usable_system_profiles(sys_settings: Path) -> dict[str, Any]:
    """系统内置可下发的 profile：default_model 非空的项（其余视为未配置，不提供给用户）。"""
    profiles = _read_json_file(sys_settings).get("profiles")
    if not isinstance(profiles, dict):
        return {}
    return {
        name: p
        for name, p in profiles.items()
        if isinstance(p, dict) and str(p.get("default_model") or "").strip()
    }


def _write_seed_settings(sys_settings: Path, dst: Path) -> None:
    """以系统配置为模板生成用户配置：只保留可用的内置 profile，模型设置由用户在自有文件中维护。"""
    raw = _read_json_file(sys_settings)
    usable = _usable_system_profiles(sys_settings)
    raw["profiles"] = usable
    if raw.get("active_profile") not in usable:
        raw["active_profile"] = next(iter(usable), "")
    dst.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_usable_system_profiles(settings_dst: Path, sys_settings: Path) -> None:
    """补齐用户配置中缺失的系统内置 profile；已有条目（含用户改写）一律不动。"""
    usable = _usable_system_profiles(sys_settings)
    if not usable:
        return
    raw = _read_json_file(settings_dst)
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    added = False
    for name, p in usable.items():
        if name not in profiles:
            profiles[name] = p
            added = True
    if not added:
        return
    raw["profiles"] = profiles
    if not raw.get("active_profile"):
        raw["active_profile"] = next(iter(usable), "")
    settings_dst.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_user_home(cfg: InsightConfig, user_id: str) -> Path:
    """注册时初始化用户 home：settings.json 仅含可用内置模型模板，credentials 复制系统版。"""
    home = user_home_dir(cfg, user_id)
    (home / "skills").mkdir(parents=True, exist_ok=True)
    (home / "plugins").mkdir(parents=True, exist_ok=True)
    settings_dst = user_settings_path(cfg, user_id)
    creds_dst = user_credentials_path(cfg, user_id)
    sys_home = system_home()
    if sys_home is not None:
        sys_settings = sys_home / "settings.json"
        if not settings_dst.exists() and sys_settings.is_file():
            _write_seed_settings(sys_settings, settings_dst)
        sys_creds = sys_home / "credentials.json"
        if not creds_dst.exists() and sys_creds.is_file():
            shutil.copyfile(sys_creds, creds_dst)
    if not settings_dst.exists():
        settings_dst.write_text("{}", encoding="utf-8")
    return home


def ensure_user_home(cfg: InsightConfig, user_id: str) -> None:
    """惰性修复用户 home：补齐缺失/空的 settings.json、缺失的 credentials 与新增的内置模型。

    覆盖两类历史数据：注册时系统 home 尚未准备好，或播种逻辑上线前创建的用户。
    """
    home = user_home_dir(cfg, user_id)
    (home / "skills").mkdir(parents=True, exist_ok=True)
    (home / "plugins").mkdir(parents=True, exist_ok=True)
    sys_home = system_home()
    if sys_home is None:
        return
    settings_dst = user_settings_path(cfg, user_id)
    sys_settings = sys_home / "settings.json"
    blank = not settings_dst.exists()
    if not blank and settings_dst.stat().st_size <= 16:
        blank = settings_dst.read_text(encoding="utf-8-sig").strip() in ("", "{}", "null")
    if blank and sys_settings.is_file():
        _write_seed_settings(sys_settings, settings_dst)
    elif sys_settings.is_file():
        _sync_usable_system_profiles(settings_dst, sys_settings)
    creds_dst = user_credentials_path(cfg, user_id)
    sys_creds = sys_home / "credentials.json"
    if not creds_dst.exists() and sys_creds.is_file():
        shutil.copyfile(sys_creds, creds_dst)


def register(cfg: InsightConfig, username: str, password: str, display_name: str = "") -> dict[str, Any]:
    """注册新用户：写入用户表并初始化其独立数据目录与 home。"""
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise UserError("用户名需 2-32 位字母/数字/下划线/连字符/中文")
    if len(password or "") < 6:
        raise UserError("密码至少 6 位")
    salt = secrets.token_hex(16)
    now = time.time()
    user_id = f"u_{secrets.token_hex(6)}"
    with _open_db(cfg) as conn:
        dup = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if dup is not None:
            raise UserError(f"用户名已存在: {username}")
        conn.execute(
            "INSERT INTO users(user_id,username,display_name,password_hash,salt,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (user_id, username, display_name.strip() or username, _hash_password(password, salt), salt, now, now),
        )
    _seed_user_home(cfg, user_id)
    user_sessions_dir(cfg, user_id).mkdir(parents=True, exist_ok=True)
    return get_user(cfg, user_id)  # type: ignore[return-value]


def get_user(cfg: InsightConfig, user_id: str) -> dict[str, Any] | None:
    with _open_db(cfg) as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    return _row_to_user(row) if row is not None else None


def find_user_by_name(cfg: InsightConfig, username: str) -> dict[str, Any] | None:
    with _open_db(cfg) as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return _row_to_user(row) if row is not None else None


def login(cfg: InsightConfig, username: str, password: str) -> tuple[dict[str, Any], str]:
    """校验用户名密码，签发新 token（同一用户旧 token 保留，多端可用）。"""
    with _open_db(cfg) as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
        if row is None:
            raise UserError("用户名或密码错误")
        if _hash_password(password or "", row["salt"]) != row["password_hash"]:
            raise UserError("用户名或密码错误")
        token = secrets.token_urlsafe(32)
        now = time.time()
        conn.execute(
            "DELETE FROM tokens WHERE expires_at < ?",
            (now,),
        )
        conn.execute(
            "INSERT INTO tokens(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
            (token, row["user_id"], now, now + TOKEN_TTL_SECONDS),
        )
    return _row_to_user(row), token


def logout(cfg: InsightConfig, token: str) -> bool:
    with _open_db(cfg) as conn:
        cur = conn.execute("DELETE FROM tokens WHERE token=?", (token,))
    return cur.rowcount > 0


def authenticate(cfg: InsightConfig, token: str) -> dict[str, Any] | None:
    """token → 用户；过期/未知返回 None。"""
    if not token:
        return None
    with _open_db(cfg) as conn:
        row = conn.execute(
            """SELECT u.* FROM tokens t JOIN users u ON u.user_id=t.user_id
               WHERE t.token=? AND t.expires_at >= ?""",
            (token, time.time()),
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def change_password(cfg: InsightConfig, user_id: str, old_password: str, new_password: str) -> None:
    if len(new_password or "") < 6:
        raise UserError("新密码至少 6 位")
    with _open_db(cfg) as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise UserError("用户不存在")
        if _hash_password(old_password or "", row["salt"]) != row["password_hash"]:
            raise UserError("原密码错误")
        salt = secrets.token_hex(16)
        conn.execute(
            "UPDATE users SET password_hash=?, salt=?, updated_at=? WHERE user_id=?",
            (_hash_password(new_password, salt), salt, time.time(), user_id),
        )
        # 改密后吊销该用户全部 token（各端重新登录）
        conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


def update_profile(cfg: InsightConfig, user_id: str, display_name: str) -> dict[str, Any]:
    with _open_db(cfg) as conn:
        conn.execute(
            "UPDATE users SET display_name=?, updated_at=? WHERE user_id=?",
            ((display_name or "").strip()[:64], time.time(), user_id),
        )
    user = get_user(cfg, user_id)
    assert user is not None
    return user


# ── 用户级 settings.json 读写（模型 profiles / MCP 配置） ─────────────────


def load_user_settings(cfg: InsightConfig, user_id: str) -> dict[str, Any]:
    path = user_settings_path(cfg, user_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_settings(cfg: InsightConfig, user_id: str, data: dict[str, Any]) -> None:
    path = user_settings_path(cfg, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def reset_user_home(cfg: InsightConfig, user_id: str) -> None:
    """重置用户 home 为系统默认（settings/credentials 重新播种）。"""
    home = user_home_dir(cfg, user_id)
    for name in ("settings.json", "credentials.json"):
        target = home / name
        if target.exists():
            target.unlink()
    _seed_user_home(cfg, user_id)


def list_users(cfg: InsightConfig) -> list[dict[str, Any]]:
    with _open_db(cfg) as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    return [_row_to_user(r) for r in rows]
