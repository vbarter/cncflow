"""pytest 共享 fixture：内存/临时 SQLite + 种子数据 + Flask test client。"""
import pytest

from cncflow_core.common.db import get_conn
from data.seed_tools import seed


@pytest.fixture(scope="session")
def seeded_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "cncflow_test.db"
    conn = get_conn(path)
    seed(conn)
    conn.close()
    return str(path)


@pytest.fixture()
def seeded_conn(seeded_db_path):
    conn = get_conn(seeded_db_path)
    yield conn
    conn.close()


@pytest.fixture()
def client(seeded_db_path):
    from app import create_app

    app = create_app(db_path=seeded_db_path)
    app.testing = True
    return app.test_client()
