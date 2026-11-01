"""Собирает веб-часть Android-приложения в mobile/www.

Копирует frontend/ и кладёт рядом data/offline.json: демо-выписку и дашборд,
чтобы приложение работало без сервера. Свою выписку и претензии без сервера
собирает frontend/js/offline.js.

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
from backend.app.main import demo  # noqa: E402

WWW = ROOT / "mobile" / "www"


def offline_data() -> dict:
    return {
        "demo": demo().model_dump(mode="json"),
        "dashboard": dashboard.build(),
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
