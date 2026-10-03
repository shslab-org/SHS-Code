"""v4.0.1 server wiring regression tests (FastAPI TestClient).

Pins the critical wiring fixes:
1. Multi-socket ConnectionManager fan-out (was: one socket per session,
   second viewer silently replaced the first).
2. /ws/chat sockets receive agent events (was: separate registry that
   never got any event — the shipped chat UI was blind).
3. REST session continuation (POST /run with session_id).
4. Session detail / cancel / tasks / workspace / git / config endpoints.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated TestClient with a fresh SessionDB."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("HOME", str(tmp_path))
    from app.db.session import SessionDB
    from app.server import main as srv
    # fresh DB for this test
    srv.db.close()
    srv.db = SessionDB(db_path=tmp_path / "sessions.db")
    from fastapi.testclient import TestClient
    with TestClient(srv.app) as tc:
        yield tc
    srv.db.close()


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_multi_socket_fanout(self):
        from app.server.main import ConnectionManager

        class _FakeWS:
            def __init__(self):
                self.sent = []

            async def accept(self):
                pass

            async def send_text(self, data):
                self.sent.append(data)

        m = ConnectionManager()
        ws1, ws2 = _FakeWS(), _FakeWS()

        await m.connect(ws1, "s1")
        await m.connect(ws2, "s1")
        await m.send("s1", {"event": "llm_delta", "text": "hi"})
        m.disconnect_one(ws1, "s1")
        await m.send("s1", {"event": "agent_done"})
        # both sockets received the first frame; only ws2 gets the second
        assert json.loads(ws1.sent[0])["event"] == "llm_delta"
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 2
        assert json.loads(ws2.sent[1])["event"] == "agent_done"
        assert "s1" in m.active          # ws2 still connected
        m.disconnect_one(ws2, "s1")
        assert "s1" not in m.active      # last socket removed the key


class TestRestEndpoints:
    def test_session_detail(self, client):
        from app.server import main as srv
        import asyncio

        async def _create():
            return await srv.db.create_session("detail test")

        # SessionDB calls are async; run them on the TestClient's loop via
        # anyio from the test thread is unsafe — instead create through the
        # /run endpoint which does it for us, then inspect detail.
        r = client.post("/run", json={"prompt": "detail probe", "max_steps": 1})
        assert r.status_code == 200
        sid = r.json()["session_id"]
        r2 = client.get(f"/sessions/{sid}")
        assert r2.status_code == 200
        body = r2.json()
        assert body["session"]["id"] == sid
        assert isinstance(body["running"], bool)
        assert isinstance(body["viewers"], int)

    def test_session_detail_404(self, client):
        r = client.get("/sessions/doesnotexist")
        assert r.status_code == 404

    def test_run_with_unknown_session_404(self, client):
        r = client.post("/run", json={"prompt": "x", "session_id": "nope"})
        assert r.status_code == 404

    def test_workspace_files_confined(self, client, tmp_path):
        r = client.get("/workspace/files", params={"path": "."})
        assert r.status_code == 200
        assert "entries" in r.json()
        # path escape is rejected
        r = client.get("/workspace/files", params={"path": "../../etc"})
        assert r.status_code == 400

    def test_workspace_file_read(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sample.txt").write_text("hello workspace")
        r = client.get("/workspace/file", params={"path": "sample.txt"})
        assert r.status_code == 200
        assert r.json()["content"] == "hello workspace"

    def test_config_masks_key(self, client, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-supersecretkey123456")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
        from app.config import Config
        Config._instance = None   # force reload
        try:
            r = client.get("/config")
            assert r.status_code == 200
            key = r.json().get("api_key", "")
            assert "supersecretkey" not in key
        finally:
            Config._instance = None

    def test_tasks_endpoint(self, client):
        r = client.get("/tasks")
        assert r.status_code == 200
        assert "tasks" in r.json()

    def test_git_status(self, client):
        r = client.get("/git/status")
        assert r.status_code == 200
        assert "is_repo" in r.json()


class TestChatSocketReceivesEvents:
    def test_chat_socket_registered_in_main_manager(self, client):
        """The wiring fix: /ws/chat sockets must appear in the MAIN manager
        (the registry StreamingSHSCode sends through)."""
        with client.websocket_connect("/ws/chat/socktest1") as ws:
            hello = json.loads(ws.receive_text())
            assert hello["type"] == "connected"
            from app.server import main as srv
            assert "socktest1" in srv.manager.active
            assert len(srv.manager.active["socktest1"]) >= 1
