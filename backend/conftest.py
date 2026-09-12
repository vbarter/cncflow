"""pytest 共享 fixture：内存/临时 SQLite + 种子数据 + Flask test client。"""
import pytest

from cncflow_core.common.db import get_conn
from data.seed_tools import seed


def pytest_configure(config):
    config.addinivalue_line("markers", "llm_features: 走 tu-zi LLM 特征主路径（需 mock）")


@pytest.fixture(autouse=True)
def _geometry_parser_for_pin_tests(monkeypatch, request):
    """现网插件/报价钉测默认走几何回退；标 llm_features 的测才打 LLM 主路径。"""
    monkeypatch.setenv("CNCFLOW_PLAN_LLM_ENABLED", "0")
    if request.node.get_closest_marker("llm_features"):
        monkeypatch.setenv("CNCFLOW_FEATURE_PARSER", "llm")
        return
    monkeypatch.setenv("CNCFLOW_FEATURE_PARSER", "geometry")


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
