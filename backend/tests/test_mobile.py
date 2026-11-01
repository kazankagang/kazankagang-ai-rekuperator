import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app

ROOT = Path(__file__).resolve().parents[2]


def load_build_www():
    spec = importlib.util.spec_from_file_location("build_www", ROOT / "mobile" / "scripts" / "build_www.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_offline_data_has_demo_and_dashboard():
    data = load_build_www().offline_data()
    assert len(data["demo"]["cases"]) == 5
    assert data["dashboard"]["kpis"]


def test_cors_for_android_app():
    res = TestClient(app).get("/api/health", headers={"Origin": "https://localhost"})
    assert res.headers["access-control-allow-origin"] == "*"
