"""Regression: secrets + MCP API-key auth (§6)."""
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_secrets_client(tmp_path, monkeypatch):
    import app.secrets.router as router_mod
    from app.secrets.store import FileSecretsStore
    # isolate store per test
    monkeypatch.setattr(router_mod, "_store", FileSecretsStore(base_dir=str(tmp_path / "secrets")))
    app = FastAPI()
    app.include_router(router_mod.router)
    return TestClient(app)


def test_secrets_open_when_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SHSCODE_API_KEY", raising=False)
    monkeypatch.delenv("MANUSCLAW_API_KEY", raising=False)
    c = _make_secrets_client(tmp_path, monkeypatch)
    r = c.get("/secrets")
    assert r.status_code == 200, r.text


def test_secrets_401_without_key_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("SHSCODE_API_KEY", "s3cr3t")
    c = _make_secrets_client(tmp_path, monkeypatch)
    assert c.get("/secrets").status_code == 401
    assert c.get("/secrets", headers={"X-API-Key": "wrong"}).status_code == 401
    r = c.get("/secrets", headers={"X-API-Key": "s3cr3t"})
    assert r.status_code == 200, r.text


def test_secrets_crud_guarded(tmp_path, monkeypatch):
    monkeypatch.setenv("SHSCODE_API_KEY", "k123")
    c = _make_secrets_client(tmp_path, monkeypatch)
    H = {"X-API-Key": "k123"}
    # create without key -> 401
    r = c.post("/secrets", json={"name": "a", "value": "v"})
    assert r.status_code == 401
    # create with key -> 201
    r = c.post("/secrets", json={"name": "a", "value": "v"}, headers=H)
    assert r.status_code == 201, r.text
    # get/delete with wrong key -> 401
    assert c.get("/secrets/a", headers={"X-API-Key": "bad"}).status_code == 401
    assert c.delete("/secrets/a", headers={"X-API-Key": "bad"}).status_code == 401
    # delete with valid key
    assert c.delete("/secrets/a", headers=H).status_code == 200


def test_mcp_auth_matrix(monkeypatch):
    from app.mcp.server import build_mcp_server
    monkeypatch.delenv("SHSCODE_API_KEY", raising=False)
    monkeypatch.delenv("MANUSCLAW_API_KEY", raising=False)
    c = TestClient(build_mcp_server())
    assert c.get("/tools/list").status_code == 200
    monkeypatch.setenv("SHSCODE_API_KEY", "mcp123")
    c2 = TestClient(build_mcp_server())
    assert c2.get("/tools/list").status_code == 401
    assert c2.get("/tools/list", headers={"X-API-Key": "bad"}).status_code == 401
    assert c2.get("/tools/list", headers={"X-API-Key": "mcp123"}).status_code == 200
    # tools/call also guarded
    assert c2.post("/tools/call", json={"name": "nope", "arguments": {}}).status_code == 401


def test_main_app_mounts_secrets():
    from app.server.main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/secrets" in paths
    assert "/secrets/{name}" in paths
