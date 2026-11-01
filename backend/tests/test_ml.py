import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ml import model, service
from backend.app.ml.synth import generate_statement
from backend.app.rules import detect
from backend.app.statement import parse_csv

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo_statement.csv"
client = TestClient(app)


@pytest.fixture(scope="module")
def demo_txs():
    return parse_csv(DEMO.read_text(encoding="utf-8"))


def test_models_beat_baseline():
    m = model.get()["metrics"]
    assert m["scanner"]["precision"] > 0.9 and m["scanner"]["recall"] > 0.9
    assert m["scorer"]["auc"] > m["scorer"]["auc_expert"]
    assert m["scorer"]["brier"] < m["scorer"]["brier_expert"]


def test_scanner_finds_what_rules_miss(demo_txs):
    ml_cases = service.find_cases(demo_txs, detect(demo_txs))
    kinds = {c.id.split("-")[1]: c for c in ml_cases}
    assert set(kinds) == {"imposed", "dup"}  # «Юрист 24» к кредиту и дубль на маркетплейсе на следующий день
    assert kinds["imposed"].amount == 4990
    assert kinds["dup"].amount == 2450 and len(kinds["dup"].evidence) == 2
    assert all(c.ml and c.confidence >= service.SCAN_THRESHOLD for c in ml_cases)


def test_scanner_quiet_on_plain_statement():
    csv = ("дата;описание;сумма;категория;детали\n"
           "2026-10-01;Зарплата;-90000;Поступления;\n"
           "2026-10-02;Супермаркет «Утро»;2100;Продукты;\n"
           "2026-10-03;Метро, проезд;63;Транспорт;\n"
           "2026-10-03;Метро, проезд;63;Транспорт;\n"
           "2026-10-05;Музыкальный сервис «Звук»;199;Подписки;автоплатёж\n")
    txs = parse_csv(csv)
    assert service.find_cases(txs, detect(txs)) == []


def test_scanner_on_fresh_synthetic_statements():
    rng = random.Random(2026)
    hits = total = 0
    for _ in range(30):
        txs, labels = generate_statement(rng)
        for t, (kind, p) in zip(txs, model.scan(model.get(), txs)):
            if labels[t.id] != "none":
                total += 1
                hits += kind == labels[t.id] and p >= service.SCAN_THRESHOLD
    assert hits / total > 0.9


def test_score_reacts_to_merchant_and_age(demo_txs):
    [dup] = [c for c in detect(demo_txs) if c.id.startswith("dup-")]
    fresh = service.score_cases([dup], demo_txs)[0]
    unknown = service.score_cases([dup.model_copy(update={"sub": "Неизвестный магазин"})],
                                  [t.model_copy(update={"desc": "Неизвестный магазин"}) for t in demo_txs])[0]
    assert fresh.expert_chance == 95 and fresh.chance_source == "ml"
    assert fresh.chance > unknown.chance  # «Вольт» возвращает деньги в 91% дел
    assert fresh.factors and all(f.impact for f in fresh.factors)


def test_ml_endpoints():
    info = client.get("/api/ml/info").json()
    assert {"scanner", "scorer"} <= set(info["metrics"])
    demo = client.get("/api/demo").json()
    res = client.post("/api/ml/score", json={"cases": demo["cases"][:1], "transactions": demo["transactions"]})
    assert res.status_code == 200
    assert 1 <= res.json()["cases"][0]["chance"] <= 99
