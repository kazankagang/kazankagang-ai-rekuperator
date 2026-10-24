from fastapi.testclient import TestClient

from backend.app import llm
from backend.app.main import app

client = TestClient(app)


def test_demo_and_frontend():
    res = client.get("/api/demo")
    assert res.status_code == 200
    assert len(res.json()["cases"]) == 5
    assert "AI-Рекуператор" in client.get("/").text


def test_upload_bad_file():
    res = client.post("/api/analyze", files={"file": ("x.csv", b"hello\n", "text/csv")})
    assert res.status_code == 422


def test_claim_template_without_key(monkeypatch):
    monkeypatch.setattr(llm, "ai_enabled", lambda: False)
    demo = client.get("/api/demo").json()
    case = demo["cases"][0]
    res = client.post("/api/claim", json={"case": case, "transactions": demo["transactions"]})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "template"
    assert "ПРЕТЕНЗИЯ" in body["text"]


def test_ai_scan_needs_key(monkeypatch):
    monkeypatch.setattr(llm, "ai_enabled", lambda: False)
    res = client.post("/api/ai-scan", json={"transactions": [], "cases": []})
    assert res.status_code == 503


def test_dashboard():
    data = client.get("/api/dashboard").json()
    assert data["kpis"]["returned_thousands"] == 6177
    assert data["kpis"]["commission_thousands"] == 1235
