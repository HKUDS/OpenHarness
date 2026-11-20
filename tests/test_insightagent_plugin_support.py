"""plugin_support 与工具层单测：解析三路径、SQL 安全、限行截断。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext

from insightagent.config import (
    AgentConfig,
    DatabaseEntry,
    EmbeddingConfig,
    InsightConfig,
    MilvusConfig,
    SessionsConfig,
)
from insightagent.plugin_support import (
    PluginResolutionError,
    _load_factory,
    build_deps,
    discover_plugins,
    resolve_plugins,
)

REPO_PLUGINS = Path(__file__).resolve().parents[1] / "plugins"
_CTX = ToolExecutionContext(cwd=Path("."))


def make_config(tmp_path: Path, *, with_db: bool = True, with_milvus: bool = False, max_rows: int = 100) -> InsightConfig:
    db_path = tmp_path / "demo.db"
    if with_db:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, amount REAL)")
        conn.executemany(
            "INSERT INTO orders (customer, amount) VALUES (?, ?)",
            [("alice", 100.0), ("bob", 200.0), ("carol", 300.0)],
        )
        conn.commit()
        conn.close()
    return InsightConfig(
        databases=[DatabaseEntry(id="demo", type="sqlite", dsn=str(db_path))] if with_db else [],
        milvus=MilvusConfig(collection="reports") if with_milvus else None,
        embedding=EmbeddingConfig(base_url="http://localhost:9999/v1", model="test-emb") if with_milvus else None,
        agent=AgentConfig(plugin_root=str(REPO_PLUGINS), max_rows=max_rows),
        sessions=SessionsConfig(dir=str(tmp_path / "sessions")),
    )


class TestResolvePlugins:
    def test_auto_select_ready_plugins(self, tmp_path):
        cfg = make_config(tmp_path)
        loaded, skipped = resolve_plugins(None, cfg)
        assert [p.name for p in loaded] == ["mysql-query"]
        assert {s["plugin"] for s in skipped} == {"report-search"}

    def test_explicit_selection(self, tmp_path):
        cfg = make_config(tmp_path)
        loaded, _ = resolve_plugins(["mysql-query"], cfg)
        assert [p.name for p in loaded] == ["mysql-query"]
        tool_names = {t.name for p in loaded for t in p.tools}
        assert {"db_list", "db_schema", "db_query"} <= tool_names

    def test_unknown_plugin_rejected(self, tmp_path):
        cfg = make_config(tmp_path)
        with pytest.raises(PluginResolutionError):
            resolve_plugins(["no-such-plugin"], cfg)

    def test_not_allowed_plugin_rejected(self, tmp_path):
        cfg = make_config(tmp_path)
        cfg.agent.default_plugins = ["mysql-query"]
        with pytest.raises(PluginResolutionError):
            resolve_plugins(["report-search"], cfg)

    def test_all_plugins_missing_config_skips(self, tmp_path):
        cfg = make_config(tmp_path, with_db=False)
        loaded, skipped = resolve_plugins(None, cfg)
        assert loaded == []
        assert len(skipped) == 2


class TestReportSearchMcp:
    """report-search 插件改为经 MCP「报表检索」服务检索。"""

    def _tool(self, cfg: InsightConfig):
        plugin = next(p for p in discover_plugins(cfg) if p.name == "report-search")
        factory = _load_factory(plugin.root)
        return factory.build_tools(build_deps(cfg))[0]

    def test_ready_when_mcp_server_configured(self, tmp_path, monkeypatch):
        import insightagent.plugin_support as ps

        monkeypatch.setattr(ps, "_configured_mcp_names", lambda: {"报表检索"})
        loaded, skipped = resolve_plugins(["report-search"], make_config(tmp_path))
        assert [p.name for p in loaded] == ["report-search"]
        assert skipped == []

    async def test_calls_mcp_and_normalizes_hits(self, tmp_path):
        tool = self._tool(make_config(tmp_path))
        calls: list[tuple] = []

        class FakeManager:
            async def call_tool(self, server: str, name: str, args: dict) -> str:
                calls.append((server, name, args))
                return json.dumps(
                    {
                        "hits": [
                            {"score": 0.55, "id": "r1", "text": json.dumps({"报表主题": "红虫处理情况"})},
                            {"score": 0.42, "id": "r2", "text": "纯文本摘要"},
                        ]
                    },
                    ensure_ascii=False,
                )

        tool.attach_mcp(FakeManager())
        result = await tool.execute(tool.input_model(query="红虫", top_k=2), _CTX)

        assert result.is_error is False
        assert calls == [
            ("报表检索", "search", {"collection_name": "biz_report_meta", "query_text": "红虫", "top_k": 2})
        ]
        data = json.loads(result.output)
        assert data["source"] == "mcp:报表检索"
        assert data["results"][0] == {"score": 0.55, "报表主题": "红虫处理情况", "id": "r1"}
        assert data["results"][1]["text"] == "纯文本摘要"

    async def test_without_mcp_returns_error(self, tmp_path):
        tool = self._tool(make_config(tmp_path))
        result = await tool.execute(tool.input_model(query="红虫"), _CTX)
        assert result.is_error is True
        assert "MCP" in result.output


class TestSqlSafety:
    def test_select_allowed(self):
        from insightagent.db.sqlsafety import SQLSafetyError, validate_readonly_sql

        assert validate_readonly_sql("SELECT 1").upper().startswith("SELECT")
        assert validate_readonly_sql("with t as (select 1) select * from t").lower().startswith("with")

    def test_write_rejected(self):
        from insightagent.db.sqlsafety import SQLSafetyError, validate_readonly_sql

        for sql in [
            "DELETE FROM orders",
            "DROP TABLE orders",
            "UPDATE orders SET amount = 0",
            "INSERT INTO orders VALUES (1, 'x', 1)",
            "SELECT 1; DROP TABLE orders",
            "-- comment\nDELETE FROM orders",
            "SELECT 1; SELECT 2",
        ]:
            with pytest.raises(SQLSafetyError):
                validate_readonly_sql(sql)


class TestDbTools:
    def _tools(self, cfg: InsightConfig):
        deps = build_deps(cfg)
        loaded, _ = resolve_plugins(["mysql-query"], cfg, deps=deps)
        return {t.name: t for p in loaded for t in p.tools}

    async def test_db_list(self, tmp_path):
        tools = self._tools(make_config(tmp_path))
        result = await tools["db_list"].execute(tools["db_list"].input_model(), _CTX)
        data = json.loads(result.output)
        assert data["databases"][0]["id"] == "demo"

    async def test_db_query_roundtrip_and_truncation(self, tmp_path):
        cfg = make_config(tmp_path, max_rows=2)
        tools = self._tools(cfg)

        args = tools["db_query"].input_model(db_id="demo", sql="SELECT customer, amount FROM orders ORDER BY amount")
        result = await tools["db_query"].execute(args, _CTX)
        data = json.loads(result.output)
        assert result.is_error is False
        assert data["row_count"] == 2
        assert data["truncated"] is True

        args = tools["db_query"].input_model(db_id="demo", sql="DELETE FROM orders")
        result = await tools["db_query"].execute(args, _CTX)
        assert result.is_error is True

    async def test_db_schema(self, tmp_path):
        tools = self._tools(make_config(tmp_path))
        args = tools["db_schema"].input_model(db_id="demo")
        result = await tools["db_schema"].execute(args, _CTX)
        data = json.loads(result.output)
        assert data["tables"][0]["table"] == "orders"
        col_names = {c["name"] for c in data["tables"][0]["columns"]}
        assert {"id", "customer", "amount"} <= col_names
