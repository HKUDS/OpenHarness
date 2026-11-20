"""server 层单测：鉴权、用户隔离、插件解析 400、SSE 流、会话 CRUD、用户级配置（不触真实 LLM）。"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from insightagent import storage, users
from insightagent.config import (
    AgentConfig,
    DatabaseEntry,
    InsightConfig,
    SessionsConfig,
)
from insightagent.server import create_app

REPO_PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


def make_config(tmp_path: Path, *, with_db: bool = True) -> InsightConfig:
    db_path = tmp_path / "demo.db"
    if with_db:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, amount REAL)")
        conn.execute("INSERT INTO orders (customer, amount) VALUES ('alice', 100.0)")
        conn.commit()
        conn.close()
    return InsightConfig(
        databases=[DatabaseEntry(id="demo", type="sqlite", dsn=str(db_path))] if with_db else [],
        agent=AgentConfig(plugin_root=str(REPO_PLUGINS)),
        sessions=SessionsConfig(dir=str(tmp_path / "sessions")),
    )


class FakePool:
    """替身池：不触真实 build_runtime/LLM；命名会话回合后落盘快照。"""

    def __init__(self, cfg: InsightConfig) -> None:
        self.cfg = cfg
        self.deps = None  # deps=None 时 resolve_plugins 自行构建
        self.submitted: list[str] = []

    async def stream_chat(
        self,
        *,
        message: str,
        session_id: str | None,
        loaded: list,
        profile: str | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        self.submitted.append((session_id, message))
        if session_id is not None:
            self.precheck(session_id, loaded, mcp_servers=mcp_servers, skills=skills)
        yield {"type": "assistant_delta", "text": "共 1 行"}
        yield {"type": "turn_complete", "text": "共 1 行", "usage": None}
        if session_id is not None:
            storage.save_snapshot(
                self.cfg,
                session_id=session_id,
                plugins=[p.name for p in loaded],
                model="fake-model",
                system_prompt="fake-prompt",
                messages=[],
                usage=None,
            )

    async def try_acquire_slot(self) -> bool:
        return True

    def release_slot(self) -> None:
        return None

    def precheck(
        self,
        session_id: str | None,
        loaded: list,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        return None

    async def close_all(self) -> None:
        return None

    def plugin_state(self) -> dict:
        return {"sessions": 0, "session_ids": []}

    async def _drop_named(self, session_id: str) -> bool:
        return False


def register_and_inject(tc: TestClient, username: str, password: str = "secret1") -> dict:
    """注册用户并注入 FakePool（按 uid 预填 user_cfgs/user_pools，绕开真实运行时）。"""
    resp = tc.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    uid = resp.json()["user"]["user_id"]
    cfg: InsightConfig = tc.app.state.base_cfg
    cloned = copy.deepcopy(cfg)
    cloned.sessions.dir = str(users.user_sessions_dir(cfg, uid))
    tc.app.state.user_cfgs[uid] = cloned
    tc.app.state.user_pools[uid] = FakePool(cloned)
    return {"token": token, "uid": uid, "username": username}


@pytest.fixture()
def client(tmp_path):
    cfg = make_config(tmp_path)
    app = create_app(cfg)
    with TestClient(app) as tc:
        acct = register_and_inject(tc, "alice")
        tc.headers.update({"Authorization": f"Bearer {acct['token']}"})
        yield tc


class TestAuth:
    def test_health_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_requires_login(self, tmp_path):
        app = create_app(make_config(tmp_path))
        with TestClient(app) as tc:
            assert tc.get("/api/sessions").status_code == 401
            assert tc.get("/api/capabilities").status_code == 401
            assert tc.post("/api/chat", json={"message": "hi"}).status_code == 401

    def test_register_login_logout(self, client):
        # 重复注册
        assert client.post("/api/auth/register", json={"username": "alice", "password": "x" * 8}).status_code == 400
        # 密码过短
        assert client.post("/api/auth/register", json={"username": "bob", "password": "123"}).status_code == 400
        # 登录错误
        assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong!"}).status_code == 400
        # 正常登录（第二端）
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
        assert resp.status_code == 200
        token2 = resp.json()["token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
        assert me.json()["user"]["username"] == "alice"
        # 登出后 token 失效
        assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token2}"}).status_code == 200
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"}).status_code == 401

    def test_change_password_revokes_tokens(self, client):
        resp = client.post("/api/auth/password", json={"old_password": "bad", "new_password": "newpass1"})
        assert resp.status_code == 400
        resp = client.post("/api/auth/password", json={"old_password": "secret1", "new_password": "newpass1"})
        assert resp.status_code == 200
        # 旧 token 已被吊销
        assert client.get("/api/auth/me").status_code == 401
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "newpass1"})
        assert resp.status_code == 200


class TestUserIsolation:
    def test_sessions_isolated(self, client):
        client.post("/api/chat", json={"message": "多少订单", "session_id": "s-alice"})
        bob = register_and_inject(client, "bob")
        bob_headers = {"Authorization": f"Bearer {bob['token']}"}
        # bob 看不到 alice 的会话
        listing = client.get("/api/sessions", headers=bob_headers).json()["sessions"]
        assert listing == []
        assert client.get("/api/sessions/s-alice/transcript", headers=bob_headers).status_code == 404
        assert client.get("/api/sessions/s-alice/history", headers=bob_headers).status_code == 404
        assert client.delete("/api/sessions/s-alice", headers=bob_headers).status_code == 404
        # alice 自己可见
        mine = client.get("/api/sessions").json()["sessions"]
        assert [s["session_id"] for s in mine] == ["s-alice"]


class TestUserSettings:
    def test_profile_crud_and_active(self, client):
        resp = client.put(
            "/api/user/profiles",
            json={
                "name": "my-qwen",
                "label": "我的千问",
                "api_format": "openai",
                "base_url": "https://example.com/v1",
                "default_model": "qwen-max",
                "api_key": "sk-test-123",
            },
        )
        assert resp.status_code == 200
        data = client.get("/api/user/settings").json()
        mine = [p for p in data["profiles"]["items"] if p["name"] == "my-qwen"]
        assert mine and mine[0]["scope"] == "user" and mine[0]["model"] == "qwen-max"

        resp = client.put("/api/user/active-profile", json={"profile": "my-qwen"})
        assert resp.status_code == 200
        assert client.get("/api/user/settings").json()["active_profile"] == "my-qwen"
        # 未注册 profile 拒绝
        assert client.put("/api/user/active-profile", json={"profile": "ghost"}).status_code == 400

        # 删除
        assert client.delete("/api/user/profiles/my-qwen").status_code == 200
        assert client.delete("/api/user/profiles/my-qwen").status_code == 404

    def test_mcp_crud(self, client):
        assert client.put("/api/user/mcp", json={"name": "天气", "url": "ftp://x"}).status_code == 400
        resp = client.put("/api/user/mcp", json={"name": "天气", "url": "http://127.0.0.1:9999/mcp"})
        assert resp.status_code == 200
        servers = client.get("/api/user/mcp").json()["mcp_servers"]
        assert [s["name"] for s in servers] == ["天气"]
        assert client.delete("/api/user/mcp/天气").status_code == 200
        assert client.get("/api/user/mcp").json()["mcp_servers"] == []

    def test_home_reset(self, client):
        client.put("/api/user/profiles", json={"name": "tmp", "api_format": "openai"})
        assert client.post("/api/user/home/reset").status_code == 200
        assert client.get("/api/user/mcp").json()["mcp_servers"] == []


class TestChat:
    def test_unknown_plugin_400(self, client):
        resp = client.post("/api/chat", json={"message": "hi", "plugins": ["nope"]})
        assert resp.status_code == 400

    def test_no_plugins_still_chats(self, tmp_path):
        """允许一个插件都不选：无插件时仍可纯对话（能力缺失仅作为 skipped 提示）。"""
        cfg = make_config(tmp_path, with_db=False)
        app = create_app(cfg)
        with TestClient(app) as tc:
            acct = register_and_inject(tc, "solo")
            tc.headers.update({"Authorization": f"Bearer {acct['token']}"})
            resp = tc.post("/api/chat", json={"message": "hi", "plugins": []})
            assert resp.status_code == 200
            events = [
                json.loads(line[6:])
                for line in resp.text.splitlines()
                if line.startswith("data: ") and line != "data: [DONE]"
            ]
            assert "assistant_delta" in [e["type"] for e in events]
            assert events[-1]["type"] == "turn_complete"

    def test_sse_stream(self, client):
        resp = client.post("/api/chat", json={"message": "多少订单"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        types = [e["type"] for e in events]
        assert "assistant_delta" in types
        assert types[-1] == "turn_complete"
        assert resp.text.strip().endswith("data: [DONE]")

    def test_non_stream(self, client):
        resp = client.post("/api/chat", json={"message": "多少订单", "stream": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["report"] == "共 1 行"
        assert body["events"]

    def test_named_session_snapshot_written(self, client):
        resp = client.post("/api/chat", json={"message": "多少订单", "session_id": "s1"})
        assert resp.status_code == 200
        sessions = client.get("/api/sessions").json()["sessions"]
        assert any(s["session_id"] == "s1" for s in sessions)


class TestSessionsApi:
    def test_history_404(self, client):
        assert client.get("/api/sessions/none/history").status_code == 404

    def test_delete_404(self, client):
        assert client.delete("/api/sessions/none").status_code == 404

    def test_history_roundtrip(self, client):
        client.post("/api/chat", json={"message": "多少订单", "session_id": "s2"})
        resp = client.get("/api/sessions/s2/history")
        assert resp.status_code == 200
        assert resp.json()["model"] == "fake-model"
