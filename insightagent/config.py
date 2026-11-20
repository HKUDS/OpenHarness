"""统一配置加载：~/.insightagent/config.yaml（DATAAGENT/INSIGHTAGENT_CONFIG 环境变量可覆盖）。

支持从仓库根 `.env` 读取 MYSQL_* 变量自动注册 MySQL 数据源（真实环境变量优先于 .env）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".insightagent"
DEFAULT_PORT = 8760
SUPPORTED_DB_TYPES = ("mysql", "postgres", "sqlite")
MYSQL_ENV_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")


class ConfigError(ValueError):
    """配置文件结构或取值非法。"""


@dataclass
class DatabaseEntry:
    id: str
    type: str
    dsn: str
    description: str = ""


@dataclass
class MilvusConfig:
    uri: str = "http://localhost:19530"
    collection: str = ""
    token: str = ""
    db_name: str = "default"
    vector_field: str = "vector"
    output_fields: list[str] = field(default_factory=lambda: ["report_name", "report_url", "metrics", "description"])
    top_k: int = 3
    metric_type: str = "COSINE"


@dataclass
class EmbeddingConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    max_sessions: int = 50
    max_concurrent: int = 8


@dataclass
class AgentConfig:
    profile: str | None = None
    model: str | None = None
    max_turns: int = 12
    plugin_root: str = "./plugins"
    default_plugins: list[str] = field(default_factory=lambda: ["mysql-query", "report-search"])
    max_rows: int = 100
    query_timeout_seconds: int = 30
    sql_retry_limit: int = 3
    search_retry_limit: int = 2


@dataclass
class SessionsConfig:
    dir: str = "~/.insightagent/sessions"


@dataclass
class InsightConfig:
    databases: list[DatabaseEntry] = field(default_factory=list)
    milvus: MilvusConfig | None = None
    embedding: EmbeddingConfig | None = None
    server: ServerConfig = field(default_factory=ServerConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    sessions: SessionsConfig = field(default_factory=SessionsConfig)
    config_path: Path | None = None

    @property
    def sessions_dir(self) -> Path:
        return Path(os.path.expanduser(self.sessions.dir)).resolve()

    def plugin_root_path(self, cwd: str | Path | None = None) -> Path:
        root = Path(self.agent.plugin_root).expanduser()
        if not root.is_absolute():
            base = Path(cwd) if cwd else Path.cwd()
            root = (base / root).resolve()
        return root


def config_file_path() -> Path:
    env = os.environ.get("INSIGHTAGENT_CONFIG") or os.environ.get("DATAAGENT_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (DEFAULT_CONFIG_DIR / "config.yaml").expanduser().resolve()


def _parse_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE，忽略注释与空行，不去除引号内的 #。"""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _mysql_entry_from_env(env: dict[str, str]) -> DatabaseEntry | None:
    """由 MYSQL_* 变量构建 MySQL 数据源；host/user/password/database 齐全才生效。"""
    host = env.get("MYSQL_HOST", "").strip()
    user = env.get("MYSQL_USER", "").strip()
    password = env.get("MYSQL_PASSWORD", "")
    database = env.get("MYSQL_DATABASE", "").strip()
    if not (host and user and database):
        return None
    port = int(env.get("MYSQL_PORT", "3306").strip() or "3306")
    db_id = "mysql-main"
    description = env.get("MYSQL_DESCRIPTION", "").strip() or f"MySQL 主数据源（{host}:{port}/{database}，来自 .env）"
    # 密码可含 @ : / 等特殊字符，必须 URL 编码（catalog 侧 urlparse + unquote 解码）
    from urllib.parse import quote

    return DatabaseEntry(
        id=db_id,
        type="mysql",
        dsn=f"mysql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{database}",
        description=description,
    )


def _merge_mysql_env(databases: list[DatabaseEntry], cfg_path: Path | None) -> list[DatabaseEntry]:
    """合并 .env 中的 MYSQL_* 配置；真实环境变量优先于 .env 文件值。"""
    dotenv_candidates = []
    if cfg_path is not None:
        dotenv_candidates.append(cfg_path.parent / ".env")
    dotenv_candidates.append(Path.cwd() / ".env")
    file_env: dict[str, str] = {}
    for candidate in dotenv_candidates:
        if candidate.is_file():
            file_env.update(_parse_dotenv(candidate))
            break
    merged = {**file_env, **{k: v for k, v in os.environ.items() if k in MYSQL_ENV_KEYS or k == "MYSQL_DESCRIPTION"}}
    if not any(key in merged for key in MYSQL_ENV_KEYS):
        return databases
    entry = _mysql_entry_from_env(merged)
    if entry is None:
        return databases
    return [d for d in databases if d.id != entry.id] + [entry]


def load_config(path: str | Path | None = None) -> InsightConfig:
    """加载配置；文件不存在时返回全默认配置（两个能力域均未配置）。"""
    cfg_path = Path(path).expanduser().resolve() if path else config_file_path()
    if not cfg_path.exists():
        # 无配置文件时仍合并 .env 中的 MYSQL_*（CWD/.env 候选）
        return InsightConfig(databases=_merge_mysql_env([], cfg_path), config_path=cfg_path)
    try:
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件不是合法 YAML: {cfg_path}: {exc}") from exc

    databases: list[DatabaseEntry] = []
    for i, item in enumerate(raw.get("databases") or []):
        if not isinstance(item, dict):
            raise ConfigError(f"databases[{i}] 应为映射")
        db_type = str(item.get("type", "")).lower()
        if db_type not in SUPPORTED_DB_TYPES:
            raise ConfigError(f"databases[{i}].type 必须是 {'/'.join(SUPPORTED_DB_TYPES)}，收到: {db_type!r}")
        db_id = str(item.get("id", "")).strip()
        if not db_id:
            raise ConfigError(f"databases[{i}].id 不能为空")
        if any(d.id == db_id for d in databases):
            raise ConfigError(f"databases[{i}].id 重复: {db_id}")
        databases.append(
            DatabaseEntry(
                id=db_id,
                type=db_type,
                dsn=str(item.get("dsn", "")),
                description=str(item.get("description", "")),
            )
        )

    milvus_raw = raw.get("milvus")
    milvus = MilvusConfig(**{k: v for k, v in milvus_raw.items() if k in MilvusConfig.__dataclass_fields__}) if isinstance(milvus_raw, dict) else None

    emb_raw = raw.get("embedding")
    embedding = EmbeddingConfig(**{k: v for k, v in emb_raw.items() if k in EmbeddingConfig.__dataclass_fields__}) if isinstance(emb_raw, dict) else None

    server_raw = raw.get("server") or {}
    server = ServerConfig(**{k: v for k, v in server_raw.items() if k in ServerConfig.__dataclass_fields__})

    agent_raw = raw.get("agent") or {}
    agent = AgentConfig(**{k: v for k, v in agent_raw.items() if k in AgentConfig.__dataclass_fields__})

    sessions_raw = raw.get("sessions") or {}
    sessions = SessionsConfig(**{k: v for k, v in sessions_raw.items() if k in SessionsConfig.__dataclass_fields__})

    return InsightConfig(
        databases=_merge_mysql_env(databases, cfg_path),
        milvus=milvus,
        embedding=embedding,
        server=server,
        agent=agent,
        sessions=sessions,
        config_path=cfg_path,
    )
