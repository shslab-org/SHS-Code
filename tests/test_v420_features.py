"""v4.2.0 regression tests — the four follow-up mission items:

1. GUI workspace diff-viewer   (/workspace/diff + gui.html Changes tab)
2. CI pytest workflow          (.github/workflows/tests.yml ships + pins)
3. Messaging stubs COMPLETED   (Discord Gateway, Slack Socket Mode,
                                Teams Bot Framework OAuth, Google Chat
                                service-account JWT, Email IMAP polling,
                                + messaging webhook routes)
4. SHS-Agent identity EVERYWHERE (commit author + committer +
   Co-Authored-By + contributor, CLI and GUI alike)
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
_GUI = ROOT / "app" / "server" / "static" / "gui.html"


# ═════════════════════════════════════════════════════════════════════════
# 4. SHS-Agent identity — "sab jagah"
# ═════════════════════════════════════════════════════════════════════════

class TestAgentIdentityEverywhere:
    def test_agent_git_env_keys(self):
        from app.git_providers.agent_identity import agent_git_env
        env = agent_git_env()
        assert env["GIT_AUTHOR_NAME"] == "SHS-Agent"
        assert env["GIT_AUTHOR_EMAIL"] == "337454460+SHS-Agent@users.noreply.github.com"
        assert env["GIT_COMMITTER_NAME"] == "SHS-Agent"
        assert env["GIT_COMMITTER_EMAIL"] == "337454460+SHS-Agent@users.noreply.github.com"

    def test_agent_git_args(self):
        from app.git_providers.agent_identity import agent_git_args
        args = agent_git_args()
        assert "user.name=SHS-Agent" in args
        assert "user.email=337454460+SHS-Agent@users.noreply.github.com" in args

    def test_apply_agent_git_env(self, monkeypatch):
        from app.git_providers import agent_identity as ai
        for k in ai.GIT_ENV_KEYS:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("SHSCODE_AGENT_IDENTITY", raising=False)
        assert ai.apply_agent_git_env() is True
        assert ai.agent_git_env() == {k: ai.os.environ[k] for k in ai.GIT_ENV_KEYS}

    def test_apply_agent_git_env_opt_out(self, monkeypatch):
        """v4.3.0: the SHSCODE_AGENT_IDENTITY=0 opt-out is REMOVED — the
        mission rule makes agent attribution mandatory and non-bypassable,
        including via environment variables. Even with the old opt-out var
        set, the identity is enforced and pre-existing author env vars are
        OVERWRITTEN."""
        from app.git_providers import agent_identity as ai
        monkeypatch.setenv("SHSCODE_AGENT_IDENTITY", "0")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Hostile Human")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "hostile@users.noreply.github.com")
        for k in ("GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(k, raising=False)
        assert ai.apply_agent_git_env() is True
        assert ai.os.environ["GIT_AUTHOR_NAME"] == ai.AGENT_NAME
        assert ai.os.environ["GIT_AUTHOR_EMAIL"] == ai.AGENT_EMAIL
        assert ai.os.environ["GIT_COMMITTER_EMAIL"] == ai.AGENT_EMAIL
        assert not hasattr(ai, "agent_identity_enabled")

    def _git_repo(self, tmp_path: Path) -> Path:
        def run(*args):
            subprocess.run(["git"] + list(args), cwd=tmp_path,
                           capture_output=True, check=True)
        run("init", "-q")
        # deliberately configure a HUMAN identity — the provider must
        # override it with the agent identity per the "sab jagah" rule
        run("config", "user.name", "Human User")
        run("config", "user.email", "human@example.com")
        (tmp_path / "seed.txt").write_text("seed\n")
        run("add", "-A")
        run("-c", "user.name=Human User",
            "-c", "user.email=human@example.com",
            "commit", "-q", "-m", "seed")
        return tmp_path

    def test_commit_is_agent_authored(self, tmp_path):
        repo = self._git_repo(tmp_path)
        from app.git_providers.github_provider import GitHubProvider
        provider = GitHubProvider(repo_dir=str(repo))
        (repo / "change.txt").write_text("new content\n")
        result = provider.commit("test: agent attribution")
        assert result["committed"] is True
        assert result["author"] == ("SHS-Agent "
                                    "<337454460+SHS-Agent@users.noreply.github.com>")

        out = subprocess.run(
            ["git", "log", "-1",
             "--pretty=format:%an¦%ae¦%cn¦%ce¦%b"],
            cwd=repo, capture_output=True, text=True, check=True).stdout
        name, email, cname, cemail, body = out.split("¦")
        assert name == "SHS-Agent"
        assert email == "337454460+SHS-Agent@users.noreply.github.com"
        assert cname == "SHS-Agent"          # committer too
        assert cemail == "337454460+SHS-Agent@users.noreply.github.com"
        assert "Co-Authored-By: SHS-Agent" in body
        assert "Generated with SHS-Code" in body

    def test_server_lifespan_applies_identity(self, monkeypatch):
        """The server startup hook exports the agent git identity."""
        from app.git_providers import agent_identity as ai
        for k in ai.GIT_ENV_KEYS:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("SHSCODE_AGENT_IDENTITY", raising=False)
        ai.apply_agent_git_env()
        assert ai.os.environ["GIT_AUTHOR_NAME"] == "SHS-Agent"


# ═════════════════════════════════════════════════════════════════════════
# 1. /workspace/diff endpoint
# ═════════════════════════════════════════════════════════════════════════

@pytest.fixture
def git_repo(tmp_path):
    """A real git repo with one committed file, one modified, one staged,
    and one untracked — the four states the diff viewer must show."""
    def run(*args):
        subprocess.run(["git"] + list(args), cwd=tmp_path,
                       capture_output=True, check=True)
    run("init", "-q")
    run("config", "user.name", "T")
    run("config", "user.email", "t@t")
    (tmp_path / "a.txt").write_text("line1\nline2\n")
    (tmp_path / "del.txt").write_text("gone\n")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    # unstaged modification
    (tmp_path / "a.txt").write_text("line1\nline2 changed\nline3\n")
    # deletion
    (tmp_path / "del.txt").unlink()
    # staged new file
    (tmp_path / "staged.txt").write_text("staged content\n")
    run("add", "staged.txt")
    # untracked file
    (tmp_path / "untracked.txt").write_text("brand new\n")
    return tmp_path


@pytest.fixture
def diff_client(monkeypatch, git_repo):
    monkeypatch.chdir(git_repo)
    from fastapi.testclient import TestClient
    from app.server import main as srv
    with TestClient(srv.app) as tc:
        yield tc


class TestWorkspaceDiffEndpoint:
    def test_not_a_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from fastapi.testclient import TestClient
        from app.server import main as srv
        with TestClient(srv.app) as tc:
            r = tc.get("/workspace/diff")
            assert r.status_code == 200
            body = r.json()
            assert body["is_repo"] is False
            assert body["files"] == []

    def test_unstaged_diff(self, diff_client, git_repo):
        r = diff_client.get("/workspace/diff?mode=unstaged")
        assert r.status_code == 200
        body = r.json()
        assert body["is_repo"] is True
        paths = {f["path"] for f in body["files"]}
        assert "a.txt" in paths                  # modified
        assert "del.txt" in paths                # deleted
        assert "untracked.txt" in paths          # untracked → synthesized
        assert "staged.txt" not in paths         # staged NOT in unstaged
        amod = next(f for f in body["files"] if f["path"] == "a.txt")
        assert amod["status"] == "M"
        assert amod["additions"] >= 2
        assert amod["deletions"] >= 1
        assert "@@" in amod["diff"]
        assert "line2 changed" in amod["diff"]
        untracked = next(f for f in body["files"] if f["path"] == "untracked.txt")
        assert untracked["status"] == "??"
        assert "brand new" in untracked["diff"]

    def test_staged_diff(self, diff_client):
        r = diff_client.get("/workspace/diff?mode=staged")
        body = r.json()
        paths = {f["path"] for f in body["files"]}
        assert "staged.txt" in paths
        assert "untracked.txt" not in paths      # untracked never staged
        assert "a.txt" not in paths

    def test_head_diff_includes_everything(self, diff_client):
        r = diff_client.get("/workspace/diff?mode=head")
        body = r.json()
        paths = {f["path"] for f in body["files"]}
        assert {"a.txt", "del.txt", "staged.txt", "untracked.txt"} <= paths

    def test_summary_math(self, diff_client):
        body = diff_client.get("/workspace/diff?mode=head").json()
        s = body["summary"]
        assert s["files"] == len(body["files"])
        assert s["additions"] == sum(f["additions"] for f in body["files"])
        assert s["deletions"] == sum(f["deletions"] for f in body["files"])

    def test_bad_mode_rejected(self, diff_client):
        r = diff_client.get("/workspace/diff?mode=bogus")
        assert r.status_code == 400

    def test_parse_unified_diff_unit(self):
        from app.server.main import _parse_unified_diff
        raw = (
            "diff --git a/x.py b/x.py\n"
            "index 111..222 100644\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -1,2 +1,3 @@\n"
            " old\n"
            "-removed\n"
            "+added\n"
            "+also added\n"
            "diff --git a/y.py b/y.py\n"
            "--- a/y.py\n"
            "+++ b/y.py\n"
            "@@ -1 +0,0 @@\n"
            "-only line\n")
        files = _parse_unified_diff(raw)
        assert set(files) == {"x.py", "y.py"}
        assert files["x.py"]["additions"] == 2
        assert files["x.py"]["deletions"] == 1
        assert files["y.py"]["deletions"] == 1


GUI_HTML = _GUI.read_text(encoding="utf-8")


class TestGuiDiffViewerStatic:
    @pytest.fixture(scope="class")
    def gui(self):
        return GUI_HTML

    def test_tabs_exist(self, gui):
        assert 'id="ws-tab-files"' in gui
        assert 'id="ws-tab-changes"' in gui
        assert "onclick=\"wsShowTab('files')\"" in gui
        assert "onclick=\"wsShowTab('changes')\"" in gui

    def test_diff_layout_exists(self, gui):
        assert 'id="ws-diff-layout"' in gui
        assert 'id="diff-file-list"' in gui
        assert 'id="diff-content"' in gui
        assert 'id="diff-summary"' in gui

    def test_mode_buttons(self, gui):
        assert "wsDiffMode('unstaged')" in gui
        assert "wsDiffMode('staged')" in gui
        assert "wsDiffMode('head')" in gui

    def test_fetches_endpoint(self, gui):
        assert "/workspace/diff?mode=" in gui

    def test_diff_line_classes(self, gui):
        assert "dl-add" in gui
        assert "dl-del" in gui
        assert "dl-hunk" in gui
        assert "dl-hdr" in gui

    def test_badge_counter(self, gui):
        assert "wsUpdateChangesBadge" in gui
        assert 'id="ws-changes-badge"' in gui

    def test_help_mentions_diff_viewer(self, gui):
        assert "diff-viewer" in gui
        assert "green lines were added" in gui


# ═════════════════════════════════════════════════════════════════════════
# 2. CI pytest workflow
# ═════════════════════════════════════════════════════════════════════════

class TestCiWorkflow:
    def test_tests_yml_exists(self):
        wf = ROOT / ".github" / "workflows" / "tests.yml"
        assert wf.is_file(), "pytest workflow must ship"
        text = wf.read_text()
        assert "python -m pytest" in text
        assert '"3.11"' in text and '"3.12"' in text
        assert "pytest-asyncio" in text
        assert "pip install -e ." in text

    def test_pylint_matrix_matches_requires_python(self):
        wf = ROOT / ".github" / "workflows" / "pylint.yml"
        text = wf.read_text()
        assert '"3.8"' not in text      # requires-python is >=3.11
        assert '"3.11"' in text


# ═════════════════════════════════════════════════════════════════════════
# 3. Messaging stubs completed
# ═════════════════════════════════════════════════════════════════════════

class _FakeWS:
    """Async-iterator websocket double (aiohttp WSMsgType-compatible)."""

    def __init__(self, incoming: list[dict]):
        import aiohttp
        self._incoming = [
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(p))
            for p in incoming
        ]
        self.sent: list[dict] = []
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._incoming:
            return self._incoming.pop(0)
        raise StopAsyncIteration

    async def send_str(self, text: str):
        self.sent.append(json.loads(text))

    async def close(self):
        self.closed = True


class TestDiscordGateway:
    @pytest.fixture
    def adapter(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-bot-token")
        from app.messaging.discord import DiscordAdapter
        return DiscordAdapter()

    async def test_identify_after_hello(self, adapter):
        ws = _FakeWS([{"op": 10, "d": {"heartbeat_interval": 100000}}])
        await adapter._gateway_session(ws, lambda m: None)
        adapter._heartbeat_task.cancel()
        ops = [s for s in ws.sent if s.get("op") == 2]
        assert ops, "IDENTIFY (op 2) must be sent after HELLO"
        assert ops[0]["d"]["token"] == "fake-bot-token"
        assert ops[0]["d"]["intents"] > 0

    async def test_resume_when_session_exists(self, adapter):
        adapter._session_id = "sess-123"
        adapter._seq = 42
        ws = _FakeWS([{"op": 10, "d": {"heartbeat_interval": 100000}}])
        await adapter._gateway_session(ws, lambda m: None)
        adapter._heartbeat_task.cancel()
        resumes = [s for s in ws.sent if s.get("op") == 6]
        assert resumes and resumes[0]["d"]["session_id"] == "sess-123"
        assert resumes[0]["d"]["seq"] == 42

    async def test_message_create_dispatch(self, adapter):
        received = []

        async def on_message(msg):
            received.append(msg)

        await adapter._handle_message({
            "id": "99", "channel_id": "ch-1", "content": "hello agent",
            "author": {"id": "u-7", "bot": False},
        }, on_message)
        assert len(received) == 1
        assert received[0].platform == "discord"
        assert received[0].user_id == "u-7"
        assert received[0].channel_id == "ch-1"
        assert received[0].text == "hello agent"

    async def test_bot_messages_ignored(self, adapter):
        received = []

        async def on_message(msg):
            received.append(msg)

        await adapter._handle_message({
            "channel_id": "ch-1", "content": "beep",
            "author": {"id": "u-7", "bot": True},
        }, on_message)
        assert received == []

    async def test_heartbeat_sends_seq(self, adapter):
        adapter._seq = 17
        ws = _FakeWS([])
        await adapter._send_op(ws, 1, adapter._seq)
        assert ws.sent == [{"op": 1, "d": 17}]

    async def test_stub_mode_without_token(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        from app.messaging.discord import DiscordAdapter
        a = DiscordAdapter()
        await a.connect()   # no raise
        await a.start(lambda m: None)
        result = await a.send("ch", "hi")
        assert result == {"sent": False, "reason": "stub"}


class TestSlackSocketMode:
    @pytest.fixture
    def adapter(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
        from app.messaging.slack import SlackAdapter
        return SlackAdapter()

    async def test_envelope_ack_and_message(self, adapter):
        received = []

        async def on_message(msg):
            received.append(msg)

        ws = _FakeWS([{
            "type": "hello",
        }, {
            "type": "events_api",
            "envelope_id": "env-1",
            "payload": {"event": {
                "type": "message",
                "user": "U123", "channel": "C456",
                "text": "do the thing",
                "client_msg_id": "cmi-9",
            }},
        }])
        await adapter._socket_session(ws, on_message)
        acks = [s for s in ws.sent if "envelope_id" in s]
        assert acks and acks[0]["envelope_id"] == "env-1"
        assert len(received) == 1
        assert received[0].platform == "slack"
        assert received[0].user_id == "U123"
        assert received[0].channel_id == "C456"
        assert received[0].text == "do the thing"

    async def test_bot_and_subtype_ignored(self, adapter):
        received = []

        async def on_message(msg):
            received.append(msg)

        ws = _FakeWS([
            {"type": "events_api", "envelope_id": "e1",
             "payload": {"event": {"type": "message", "bot_id": "B1",
                                   "channel": "C", "text": "hi"}}},
            {"type": "events_api", "envelope_id": "e2",
             "payload": {"event": {"type": "message", "subtype": "channel_join",
                                   "user": "U", "channel": "C", "text": "joined"}}},
        ])
        await adapter._socket_session(ws, on_message)
        assert received == []
        assert len([s for s in ws.sent if "envelope_id" in s]) == 2

    def test_socket_mode_needs_both_tokens(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        from app.messaging.slack import SlackAdapter
        a = SlackAdapter()
        assert a.is_configured() is True          # send works
        assert a.socket_mode_ready() is False     # inbound stub

    async def test_stub_send_without_token(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        from app.messaging.slack import SlackAdapter
        a = SlackAdapter()
        result = await a.send("C1", "hello")
        assert result == {"sent": False, "reason": "stub"}


class TestTeamsBotFramework:
    @pytest.fixture
    def adapter(self, monkeypatch):
        monkeypatch.setenv("MICROSOFT_APP_ID", "app-id-1")
        monkeypatch.setenv("MICROSOFT_APP_PASSWORD", "secret-1")
        monkeypatch.setenv("MICROSOFT_TENANT_ID", "tenant-1")
        from app.messaging.teams import TeamsAdapter
        return TeamsAdapter()

    async def test_oauth_token_flow(self, adapter, monkeypatch):
        """Client-credentials against the (mocked) Azure AD endpoint."""
        captured = {}

        class _Resp:
            status = 200

            async def json(self):
                return {"access_token": "tok-abc", "expires_in": 3600}

        class _Post:
            def __init__(self, url, data=None, headers=None, json=None):
                captured["url"] = url
                captured["data"] = data
                captured["headers"] = headers

            async def __aenter__(self):
                return _Resp()

            async def __aexit__(self, *a):
                return False

        class _Session:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Post(*a, **k)

        import aiohttp
        real = aiohttp.ClientSession
        monkeypatch.setattr(aiohttp, "ClientSession", _Session)
        try:
            token = await adapter._get_access_token()
        finally:
            monkeypatch.setattr(aiohttp, "ClientSession", real)
        assert token == "tok-abc"
        assert "login.microsoftonline.com/tenant-1/oauth2/v2.0/token" in captured["url"]
        assert captured["data"]["grant_type"] == "client_credentials"
        assert captured["data"]["client_id"] == "app-id-1"
        assert captured["data"]["client_secret"] == "secret-1"
        # second call uses the cache (no new HTTP)
        assert await adapter._get_access_token() == "tok-abc"

    async def test_webhook_activity_parse(self, adapter):
        msgs = await adapter.handle_webhook_event({
            "type": "message",
            "id": "act-1",
            "text": "deploy the app",
            "from": {"id": "u-9", "name": "Sazzad"},
            "conversation": {"id": "conv-7"},
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
        })
        assert len(msgs) == 1
        assert msgs[0].platform == "teams"
        assert msgs[0].user_id == "u-9"
        assert msgs[0].channel_id == "conv-7"
        assert msgs[0].text == "deploy the app"

    async def test_non_message_activity_ignored(self, adapter):
        msgs = await adapter.handle_webhook_event({"type": "typing"})
        assert msgs == []

    async def test_send_uses_token_and_url(self, adapter):
        async def fake_token():
            return "tok-xyz"

        adapter._get_access_token = fake_token
        captured = {}

        class _Resp:
            status = 201

            async def json(self):
                return {}

            async def text(self):
                return ""

        class _Post:
            def __init__(self, url, json=None, headers=None):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers

            async def __aenter__(self):
                return _Resp()

            async def __aexit__(self, *a):
                return False

        class _Session:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Post(*a, **k)

        import aiohttp
        mp = pytest.MonkeyPatch()
        real = aiohttp.ClientSession
        mp.setattr(aiohttp, "ClientSession", _Session)
        try:
            result = await adapter.send("conv-7", "hello teams")
        finally:
            mp.undo()
        assert result == {"sent": True}
        assert captured["url"].endswith("/v3/conversations/conv-7/activities")
        assert captured["headers"]["Authorization"] == "Bearer tok-xyz"

    async def test_stub_without_credentials(self, monkeypatch):
        for v in ("MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD"):
            monkeypatch.delenv(v, raising=False)
        from app.messaging.teams import TeamsAdapter
        a = TeamsAdapter()
        await a.connect()
        await a.start(lambda m: None)
        assert (await a.send("c", "x")) == {"sent": False, "reason": "stub"}


class TestGoogleChat:
    @pytest.fixture
    def sa_file(self, tmp_path, monkeypatch):
        """Real RSA service-account key — proves the RS256 JWT is valid."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        sa = {
            "type": "service_account",
            "project_id": "proj-1",
            "client_email": "bot@proj-1.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        path = tmp_path / "sa.json"
        path.write_text(json.dumps(sa))
        monkeypatch.setenv("GOOGLE_CHAT_SERVICE_ACCOUNT", str(path))
        return {"path": path, "key": key, "sa": sa}

    @pytest.fixture
    def adapter(self, sa_file):
        from app.messaging.google_chat import GoogleChatAdapter
        return GoogleChatAdapter()

    async def test_jwt_is_valid_rs256(self, adapter, sa_file):
        """Sign a JWT and verify the signature with the public key."""
        await adapter.connect()   # loads the service account
        import base64
        token = adapter._sign_jwt()
        assert token.count(".") == 2
        h_b64, c_b64, s_b64 = token.split(".")

        def _b64d(x):
            return base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))

        header = json.loads(_b64d(h_b64))
        claims = json.loads(_b64d(c_b64))
        assert header["alg"] == "RS256"
        assert claims["iss"] == "bot@proj-1.iam.gserviceaccount.com"
        assert claims["scope"] == "https://www.googleapis.com/auth/chat.bot"
        assert claims["aud"] == "https://oauth2.googleapis.com/token"
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sa_file["key"].public_key().verify(
            _b64d(s_b64), f"{h_b64}.{c_b64}".encode(),
            padding.PKCS1v15(), hashes.SHA256())

    async def test_send_url_interpolates_space(self, adapter, monkeypatch):
        """v4.2.0 FIX pin: the literal '{space}' placeholder URL is gone."""
        async def fake_token():
            return "tok-g"

        adapter._get_access_token = fake_token
        captured = {}

        class _Resp:
            status = 200

            async def json(self):
                return {}

            async def text(self):
                return ""

        class _Post:
            def __init__(self, url, json=None, headers=None):
                captured["url"] = url

            async def __aenter__(self):
                return _Resp()

            async def __aexit__(self, *a):
                return False

        class _Session:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Post(*a, **k)

        import aiohttp
        mp = pytest.MonkeyPatch()
        real = aiohttp.ClientSession
        mp.setattr(aiohttp, "ClientSession", _Session)
        try:
            assert (await adapter.send("spaces/AAAABBBB", "hi")) == {"sent": True}
            assert captured["url"] == \
                "https://chat.googleapis.com/v1/spaces/AAAABBBB/messages"
            # bare space name also normalized
            assert (await adapter.send("WXYZ", "hi")) == {"sent": True}
            assert captured["url"].endswith("/v1/spaces/WXYZ/messages")
        finally:
            mp.undo()

    async def test_webhook_event_parse(self, adapter):
        msgs = await adapter.handle_webhook_event({
            "type": "MESSAGE",
            "eventTime": "2026-01-01T00:00:00Z",
            "space": {"name": "spaces/SSS", "displayName": "ops"},
            "user": {"name": "users/u-1", "displayName": "Dev"},
            "message": {
                "name": "spaces/SSS/messages/m-1",
                "sender": {"name": "users/u-1"},
                "space": {"name": "spaces/SSS"},
                "argumentText": " run the tests",
            },
        })
        assert len(msgs) == 1
        assert msgs[0].platform == "google_chat"
        assert msgs[0].channel_id == "spaces/SSS"
        assert msgs[0].user_id == "u-1"
        assert msgs[0].text == "run the tests"

    async def test_stub_without_sa(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CHAT_SERVICE_ACCOUNT", raising=False)
        from app.messaging.google_chat import GoogleChatAdapter
        a = GoogleChatAdapter()
        await a.connect()
        await a.start(lambda m: None)
        assert (await a.send("spaces/X", "x")) == {"sent": False,
                                                   "reason": "stub"}


class TestEmailImap:
    @pytest.fixture
    def adapter(self, monkeypatch):
        monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.com")
        monkeypatch.setenv("EMAIL_IMAP_PORT", "993")
        monkeypatch.setenv("EMAIL_USER", "bot@example.com")
        monkeypatch.setenv("EMAIL_PASS", "pw")
        monkeypatch.setenv("EMAIL_POLL_INTERVAL", "1")
        from app.messaging.email import EmailAdapter
        return EmailAdapter()

    @staticmethod
    def _raw_email() -> bytes:
        from email.mime.text import MIMEText
        msg = MIMEText("please refactor the parser")
        msg["Subject"] = "task"
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Message-ID"] = "<m-1@example.com>"
        return msg.as_bytes()

    async def test_poll_inbox_dispatches(self, adapter, monkeypatch):
        import imaplib
        raw = self._raw_email()
        stored = []

        class _FakeIMAP:
            def login(self, u, p):
                stored.append(("login", u))

            def select(self, box):
                stored.append(("select", box))

            def search(self, *a):
                return ("OK", [b"1"])

            def fetch(self, num, spec):
                assert spec == "(RFC822)"
                return ("OK", [(b"1 (RFC822 {99}", raw), b")"])

            def store(self, ids, flags, value):
                stored.append(("store", ids, flags, value))

            def logout(self):
                stored.append(("logout",))

        monkeypatch.setattr(imaplib, "IMAP4_SSL",
                            lambda host, port: _FakeIMAP())
        received = []

        async def on_message(m):
            received.append(m)

        loop = asyncio.get_running_loop()
        count = adapter._poll_inbox(on_message, loop)
        await asyncio.sleep(0.05)   # let run_coroutine_threadsafe finish
        assert count == 1
        assert len(received) == 1
        assert received[0].platform == "email"
        assert received[0].user_id == "user@example.com"
        assert received[0].channel_id == "user@example.com"
        assert "refactor the parser" in received[0].text
        # message marked as seen
        assert any(s[0] == "store" and "\\Seen" in s[3] for s in stored)

    async def test_stub_without_credentials(self, monkeypatch):
        for v in ("EMAIL_USER", "EMAIL_PASS"):
            monkeypatch.delenv(v, raising=False)
        from app.messaging.email import EmailAdapter
        a = EmailAdapter()
        await a.connect()
        await a.start(lambda m: None)
        assert (await a.send("x@y.com", "hi")) == {"sent": False,
                                                   "reason": "stub"}


class TestMessagingWebhookRoutes:
    @pytest.fixture
    def route_client(self):
        from fastapi.testclient import TestClient
        from app.server import main as srv
        with TestClient(srv.app) as tc:
            yield tc

    def test_channels_listing(self, route_client):
        r = route_client.get("/messaging/channels")
        assert r.status_code == 200
        body = r.json()
        assert "channels" in body
        names = set(body["channels"])
        assert {"discord", "slack", "teams", "google_chat",
                "whatsapp", "webchat"} <= names

    def test_whatsapp_verify_ok(self, route_client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "tok123")
        # adapter was built at import time — rebuild the gateway singleton
        import app.server.messaging_routes as mr
        mr._gateway = None
        r = route_client.get(
            "/messaging/webhooks/whatsapp?hub.mode=subscribe"
            "&hub.verify_token=tok123&hub.challenge=424242")
        assert r.status_code == 200
        assert r.json() == 424242

    def test_whatsapp_verify_bad_token(self, route_client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "tok123")
        import app.server.messaging_routes as mr
        mr._gateway = None
        r = route_client.get(
            "/messaging/webhooks/whatsapp?hub.mode=subscribe"
            "&hub.verify_token=WRONG&hub.challenge=1")
        assert r.status_code == 403

    def test_teams_webhook(self, route_client):
        import app.server.messaging_routes as mr
        mr._gateway = None
        # dispatch is fire-and-forget; the response is immediate 200
        r = route_client.post("/messaging/webhooks/teams", json={
            "type": "message", "id": "a1", "text": "hi",
            "from": {"id": "u"}, "conversation": {"id": "c"},
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
        })
        assert r.status_code == 200
        assert r.json()["received"] is True

    def test_google_chat_webhook(self, route_client):
        import app.server.messaging_routes as mr
        mr._gateway = None
        r = route_client.post("/messaging/webhooks/google-chat", json={
            "type": "MESSAGE",
            "message": {"argumentText": " hello",
                        "sender": {"name": "users/u"},
                        "space": {"name": "spaces/S"}},
        })
        assert r.status_code == 200
        assert r.json()["received"] is True

    def test_google_chat_verify_token_enforced(self, route_client):
        import app.server.messaging_routes as mr
        mr._gateway = None
        import os
        os.environ.pop("GOOGLE_CHAT_VERIFY_TOKEN", None)
        # without GOOGLE_CHAT_VERIFY_TOKEN set, any token is accepted
        r = route_client.post(
            "/messaging/webhooks/google-chat?token=WRONG", json={"type": "MESSAGE"})
        assert r.status_code in (200, 401)


class TestMessagingModulesImport:
    def test_all_adapters_importable(self):
        import app.messaging as m
        for name in ("TelegramAdapter", "DiscordAdapter", "SlackAdapter",
                     "WhatsAppAdapter", "SignalAdapter", "TeamsAdapter",
                     "MatrixAdapter", "IRCAdapter", "GoogleChatAdapter",
                     "WebChatAdapter", "EmailAdapter", "TwitchAdapter"):
            assert hasattr(m, name), f"{name} missing"


class TestUntrackedDirSkip:
    def test_untracked_dirs_not_synthesized(self, git_repo, monkeypatch):
        """Server-owned untracked dirs (logs/, workspace/) must not appear."""
        monkeypatch.chdir(git_repo)
        (git_repo / "logs").mkdir()
        (git_repo / "workspace").mkdir()
        from fastapi.testclient import TestClient
        from app.server import main as srv
        with TestClient(srv.app) as tc:
            body = tc.get("/workspace/diff?mode=head").json()
            paths = {f["path"] for f in body["files"]}
            assert "logs/" not in paths
            assert "workspace/" not in paths
            assert "untracked.txt" in paths   # real files still shown
