"""Переобучить модели и показать метрики.

Запуск из корня репозитория:
    python -m backend.app.ml.train
"""
import json

from . import model

if __name__ == "__main__":
    bundle = model.train(save=True)
    print(json.dumps(bundle["metrics"], ensure_ascii=False, indent=2))
    print(f"\nМодели сохранены в {model.MODEL_FILE}")
