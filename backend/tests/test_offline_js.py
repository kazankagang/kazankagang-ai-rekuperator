"""Офлайн-движок Android-приложения (frontend/js/offline.js) должен считать так же, как бэкенд."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.app.claims import template_claim
from backend.app.rules import detect
from backend.app.statement import parse_csv

ROOT = Path(__file__).resolve().parents[2]
STATEMENTS = [ROOT / "data" / "demo_statement.csv", ROOT / "backend" / "tests" / "data" / "statement_all_cases.csv"]

RUNNER = """
import { readFileSync } from "node:fs";
import { analyze, templateClaim } from "./frontend/js/offline.js";
const res = analyze(readFileSync(process.argv[1], "utf8"), "x");
const claims = res.cases.map((c) => templateClaim(c, res.transactions.filter((t) => c.evidence.includes(t.id))));
console.log(JSON.stringify({ ...res, claims }));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="нужен Node.js")
@pytest.mark.parametrize("path", STATEMENTS, ids=lambda p: p.name)
def test_js_engine_matches_backend(path):
    out = subprocess.run(["node", "--input-type=module", "-e", RUNNER, str(path)],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    js = json.loads(out)

    txs = parse_csv(path.read_text(encoding="utf-8"))
    cases = detect(txs)
    assert js["transactions"] == [t.model_dump(mode="json") for t in txs]
    assert js["cases"] == [c.model_dump(mode="json") for c in cases]
    by_id = {t.id: t for t in txs}
    assert js["claims"] == [template_claim(c, [by_id[i] for i in c.evidence]) for c in cases]


def test_all_cases_statement_finds_every_scenario():
    cases = detect(parse_csv(STATEMENTS[1].read_text(encoding="utf-8")))
    assert {c.id.split("-")[0] for c in cases} == {"flight", "sub", "dup", "loanins", "cool"}
