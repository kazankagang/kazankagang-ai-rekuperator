"""Собирает веб-часть Android-приложения в mobile/www.

Копирует frontend/ и кладёт рядом data/offline.json: демо-выписку, дашборд и
претензии по шаблону, чтобы приложение работало без сервера.

Запуск из корня репозитория или из mobile/:
    python mobile/scripts/build_www.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app import dashboard  # noqa: E402
from backend.app.claims import template_claim  # noqa: E402
from backend.app.main import demo  # noqa: E402

WWW = ROOT / "mobile" / "www"


def offline_data() -> dict:
    result = demo()
    txs = {t.id: t for t in result.transactions}
    claims = {
        c.id: {
            "text": template_claim(c, [txs[i] for i in c.evidence if i in txs]),
            "source": "template",
            "note": "Офлайн-режим: претензия собрана по шаблону.",
        }
        for c in result.cases
    }
    return {
        "demo": result.model_dump(mode="json"),
        "dashboard": dashboard.build(),
        "claims": claims,
    }


def main() -> None:
    if WWW.exists():
        shutil.rmtree(WWW)
    shutil.copytree(ROOT / "frontend", WWW)
    (WWW / "data").mkdir(exist_ok=True)
    (WWW / "data" / "offline.json").write_text(
        json.dumps(offline_data(), ensure_ascii=False), encoding="utf-8")
    print(f"Готово: {WWW}")


if __name__ == "__main__":
    main()
