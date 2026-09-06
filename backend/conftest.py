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


@pytest.fixture()
def deterministic_feature_llm(monkeypatch):
    """旧 B-Rep 夹具的确定性 LLM 替身；测试永不访问 tu-zi 网络。"""
    from cncflow_core.geometry import service
    from cncflow_core.geometry.plugins import (
        run_face,
        run_slot,
        run_step,
        run_surface,
        run_thread,
    )
    from cncflow_core.ingestion import step_parser

    def recognize(path, image_urls=None):
        try:
            parsed = step_parser.parse_step(path, include_mesh=False)
        except TypeError:
            # Some unit doubles intentionally expose the historical path-only signature.
            parsed = step_parser.parse_step(path)
        features = [
            feature
            for feature in parsed.get("features") or []
            if feature.get("type") != "outer_cylinder"
        ]
        features.extend(run_slot(path))
        features.extend(run_face(path))
        features.extend(run_thread(path))
        features.extend(run_step(path))
        features.extend(run_surface(path))
        return {
            "provider": "tu-zi",
            "model": "deterministic-test-double",
            "input_mode": "mock",
            "features": features,
            "warnings": [],
        }

    monkeypatch.setattr(service, "recognize_step_features", recognize)
