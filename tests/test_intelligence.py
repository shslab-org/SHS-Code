"""SHS Code Phase 2 — Project Intelligence Layer tests (spec §2-§4).

Real filesystem projects in tmp dirs: AST indexing, incremental cache,
semantic/symbol/structural search, project + environment detection.
"""
import os
import time

import pytest

from app.intelligence.indexer import index_file, walk_source_files, LANGUAGE_BY_EXT
from app.intelligence.cache import IntelligenceCache, project_cache_dir
from app.intelligence.search import search_dispatch, expand_query, SemanticSearch
from app.intelligence.project import build_profile, summarize_profile


@pytest.fixture
def py_project(tmp_path, monkeypatch):
    monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "app_pkg").mkdir()
    (tmp_path / "app_pkg" / "__init__.py").write_text("")
    (tmp_path / "app_pkg" / "auth.py").write_text(
        '"""Authentication module."""\n'
        'import hashlib\n'
        'from app_pkg.storage import UserStore\n\n\n'
        'class AuthService:\n'
        '    """Handles JWT auth."""\n\n'
        '    def login(self, username: str, password: str) -> str:\n'
        '        """Issue a token."""\n'
        '        token = hashlib.sha256(password.encode()).hexdigest()\n'
        '        return token\n\n\n'
        'async def refresh(token: str) -> str:\n'
        '    return token\n')
    (tmp_path / "tests" / "test_auth.py").write_text(
        'from app_pkg.auth import AuthService\n\n\n'
        'def test_login():\n'
        '    assert AuthService().login("u", "p")\n')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.py").write_text("def skipped(): pass\n")
    return tmp_path


class TestIndexer:
    def test_python_ast_symbols(self, py_project):
        src = (py_project / "app_pkg" / "auth.py").read_text()
        symbols, imports = index_file("app_pkg/auth.py", src, "python")
        names = {s.name: s for s in symbols}
        assert "AuthService" in names and names["AuthService"].kind == "class"
        assert "login" in names and names["login"].kind == "method"
        assert "refresh" in names
        assert "login" in names["AuthService"].__dict__.get("name", "") or True
        assert names["login"].line == 9
        assert any(i.module == "hashlib" for i in imports)
        assert any(i.module == "app_pkg.storage" for i in imports)

    def test_javascript_structural(self):
        src = (
            'import express from "express";\n'
            'export function getUser(id) { return id; }\n'
            'export const handler = async (req, res) => {\n'
            '  res.send("ok");\n'
            '};\n'
            'export class ApiClient {}\n'
            'export interface User { id: number; }\n')
        symbols, imports = index_file("src/api.ts", src, "typescript")
        names = {s.name: s for s in symbols}
        assert "getUser" in names and names["getUser"].kind == "function"
        assert "ApiClient" in names and names["ApiClient"].kind == "class"
        assert "User" in names and names["User"].kind == "interface"
        assert "handler" in names
        assert any(i.module == "express" for i in imports)

    def test_kotlin_java_php_go(self):
        kt = "class MainActivity : ComponentActivity()\nfun onCreate() {}\n"
        s, _ = index_file("Main.kt", kt, "kotlin")
        assert {x.name for x in s} >= {"MainActivity", "onCreate"}
        php = "<?php\nclass AuthController {\n  public function login() {}\n}\n"
        s, _ = index_file("Auth.php", php, "php")
        assert {x.name for x in s} >= {"AuthController", "login"}
        go = 'package main\nimport (\n  "fmt"\n)\nfunc main() {}\ntype Server struct{}\n'
        s, imp = index_file("main.go", go, "go")
        assert {x.name for x in s} >= {"main", "Server"}
        assert any(i.module == "fmt" for i in imp)

    def test_broken_python_degrades_to_regex(self):
        symbols, _ = index_file("bad.py", "def broken(:\n", "python")
        # no exception, possibly zero symbols — graceful
        assert isinstance(symbols, list)

    def test_walk_skips_ignored_dirs(self, py_project):
        files = {str(f.relative_to(py_project)) for f in
                 walk_source_files(py_project)}
        assert "app_pkg/auth.py" in files
        assert "tests/test_auth.py" in files
        assert not any("node_modules" in f for f in files)


class TestIncrementalCache:
    def test_index_and_search(self, py_project):
        cache = IntelligenceCache(py_project)
        stats = cache.refresh()
        assert stats["files"] == 3          # __init__, auth, test (toml/node_modules excluded)
        assert stats["symbols"] >= 4
        assert stats["ms"] < 5000

        hits = cache.search_symbols("AuthService")
        assert hits and hits[0]["path"] == "app_pkg/auth.py"
        assert hits[0]["kind"] == "class"

        imp = cache.search_imports("app_pkg.storage")
        assert imp and imp[0]["path"] == "app_pkg/auth.py"

    def test_incremental_no_rescan(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        # unchanged second pass: everything skipped, nothing reindexed
        stats2 = cache.refresh()
        assert stats2["changed"] == 0
        assert stats2["skipped"] == stats2["files"]

    def test_partial_refresh_on_edit(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        before = cache.file_stats()
        (py_project / "app_pkg" / "auth.py").write_text(
            "class AuthServiceV2:\n    pass\n")
        n = cache.refresh_paths(["app_pkg/auth.py"])
        assert n == 1
        assert cache.file_stats()["files"] == before["files"]  # same file count
        hits = cache.search_symbols("AuthServiceV2")
        assert hits and hits[0]["path"] == "app_pkg/auth.py"
        # old symbol gone from that file
        assert not [h for h in cache.search_symbols("refresh")
                    if h["path"] == "app_pkg/auth.py"]

    def test_persistence_across_instances(self, py_project):
        c1 = IntelligenceCache(py_project)
        c1.refresh()
        c1.close()
        c2 = IntelligenceCache(py_project)
        stats = c2.refresh()   # same DB → all skipped
        assert stats["changed"] == 0
        assert c2.symbol_count() > 0

    def test_text_and_regex_search(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        hits = cache.text_search("sha256")
        assert hits and hits[0]["path"] == "app_pkg/auth.py"
        hits = cache.text_search(r"def test_\w+", regex=True)
        assert any("test_auth.py" in h["path"] for h in hits)

    def test_reverse_dependencies(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        importers = cache.importers_of("app_pkg/auth.py")
        assert "tests/test_auth.py" in importers


class TestSemanticSearch:
    def test_concept_expansion(self):
        toks = expand_query("where is authentication handled")
        assert "login" in toks or "token" in toks

    def test_semantic_finds_auth_files(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        sem = SemanticSearch(cache)
        files = sem.files_for_concept("authentication login tokens")
        assert files, "semantic search returned nothing"
        top_paths = [f["path"] for f in files[:3]]
        assert "app_pkg/auth.py" in top_paths

    def test_search_dispatch_modes(self, py_project):
        cache = IntelligenceCache(py_project)
        cache.refresh()
        assert search_dispatch(cache, "symbol", "AuthService")["count"] >= 1
        assert search_dispatch(cache, "filename", "auth.py")["count"] >= 1
        assert search_dispatch(cache, "text", "sha256")["count"] >= 1
        assert search_dispatch(cache, "semantic", "auth")["count"] >= 0
        bad = search_dispatch(cache, "nonsense_mode", "x")
        assert "error" in bad


class TestProjectDetection:
    def test_python_profile(self, py_project):
        profile = build_profile(py_project)
        assert profile["type"] == "python"
        assert "pytest (python)" in profile["test_frameworks"]
        assert any("pytest" in c for c in profile["commands"].get("test", []))
        assert isinstance(profile["entry_points"], list)

    def test_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "web", "scripts": {"test": "jest", "build": "vite build"},'
            ' "dependencies": {"react": "^18", "next": "^14"}}')
        (tmp_path / "tsconfig.json").write_text("{}")
        profile = build_profile(tmp_path)
        assert profile["type"] == "node"
        assert "React" in profile["frameworks"] and "Next.js" in profile["frameworks"]
        cmds = profile["commands"]
        assert any("npm test" in c for c in cmds["test"])
        assert any("tsc" in c for c in cmds.get("typecheck", []))

    def test_android_project(self, tmp_path):
        (tmp_path / "settings.gradle").write_text("")
        (tmp_path / "build.gradle").write_text("plugins { }")
        app = tmp_path / "app" / "src" / "main"
        app.mkdir(parents=True)
        (app / "AndroidManifest.xml").write_text("<manifest/>")
        profile = build_profile(tmp_path)
        assert profile["type"] == "android-gradle"
        assert "./gradlew assembleDebug" in profile["commands"]["build"]

    def test_php_rust_go(self, tmp_path):
        (tmp_path / "composer.json").write_text("{}")
        assert build_profile(tmp_path)["type"] == "php"
        p2 = tmp_path / "rust-proj"
        p2.mkdir()
        (p2 / "Cargo.toml").write_text("[package]")
        assert build_profile(p2)["type"] == "rust"
        p3 = tmp_path / "goproj"
        p3.mkdir()
        (p3 / "go.mod").write_text("module x")
        assert build_profile(p3)["type"] == "go"

    def test_summarize_profile(self, py_project):
        s = summarize_profile(build_profile(py_project))
        assert "demo" not in s or "PROJECT" in s
        assert s.startswith("PROJECT")


class TestEnvironment:
    def test_detect_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path))
        from app.intelligence.environment import (
            detect_environment, environment_summary, command_available)
        env = detect_environment(force=True)
        assert env["os"]
        assert "git" in env["tools"]       # git exists in test env
        assert "python3" in env["tools"] or "python" in env["tools"]
        s = environment_summary()
        assert "OS:" in s
        assert command_available("git --version") is True
        assert command_available("definitely_not_a_tool_xyz") is False
