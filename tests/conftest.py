import os
import asyncio
import tempfile
import pytest
from app import env

# Use mock LLM for all tests
os.environ["APP_ENV"] = "test"
_tmp_ws = tempfile.mkdtemp()
os.environ.setdefault("SHSCODE_WORKSPACE", _tmp_ws)


@pytest.fixture
def tmp_workspace(tmp_path):
    prev = env.getenv("WORKSPACE", "")
    os.environ["SHSCODE_WORKSPACE"] = str(tmp_path)
    yield tmp_path
    if prev:
        os.environ["SHSCODE_WORKSPACE"] = prev
    else:
        os.environ.pop("SHSCODE_WORKSPACE", None)


@pytest.fixture
def tmp_db(tmp_path):
    from app.db.session import SessionDB
    db = SessionDB(db_path=tmp_path / "test.db")
    yield db
    db.close()
