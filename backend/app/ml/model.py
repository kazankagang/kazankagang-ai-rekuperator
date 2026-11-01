"""Обучение, сохранение и загрузка ML-моделей.

Две модели:
- сканер операций: по каждой операции выписки предсказывает, есть ли в ней повод для возврата
  и какой (TF-IDF по тексту операции + признаки контекста выписки, логистическая регрессия);
- скоринг: вероятность, что по найденному случаю деньги вернут (логистическая регрессия
  по типу дела, мерчанту, сумме, давности и источнику).

Обучение на синтетических данных занимает несколько секунд. Модели сохраняются в
backend/app/ml/artifacts/ и переобучаются сами, если файла нет или сменилась версия.
"""
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .features import CASE_COLUMNS, TX_NUMERIC, statement_features, tx_text
from .synth import TX_CLASSES, generate_cases, generate_statement

DATA_VERSION = 1  # поменять при изменении генератора или признаков, чтобы модели переобучились
SEED = 42
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
MODEL_FILE = ARTIFACTS / "models.joblib"

EXPERT_CHANCE = {"flight": 0.85, "sub": 0.60, "dup": 0.95, "loanins": 0.85, "cool": 0.92, "imposed": 0.70, "other": 0.50}


# --- сканер операций ---------------------------------------------------------

def _tx_matrix(bundle: dict, texts: list[str], numeric: list[dict], fit: bool = False):
    num = np.array([[r[c] for c in TX_NUMERIC] for r in numeric], dtype=float)
    if fit:
        bundle["tfidf"] = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=3, max_features=4000, sublinear_tf=True)
        bundle["tx_scaler"] = StandardScaler()
        return hstack([bundle["tfidf"].fit_transform(texts), csr_matrix(bundle["tx_scaler"].fit_transform(num))]).tocsr()
    return hstack([bundle["tfidf"].transform(texts), csr_matrix(bundle["tx_scaler"].transform(num))]).tocsr()


def _statements(rng: random.Random, n: int):
    texts, numeric, labels = [], [], []
    for _ in range(n):
        txs, lab = generate_statement(rng)
        texts += [tx_text(t) for t in txs]
        numeric += statement_features(txs)
        labels += [lab[t.id] for t in txs]
    return texts, numeric, labels


def _train_scanner(bundle: dict, rng: random.Random) -> dict:
    texts, numeric, y = _statements(rng, 500)
    te_texts, te_numeric, te_y = _statements(rng, 200)
    X = _tx_matrix(bundle, texts, numeric, fit=True)
    clf = LogisticRegression(C=4.0, max_iter=1000)
    clf.fit(X, y)
    bundle["scanner"] = clf

    pred = clf.predict(_tx_matrix(bundle, te_texts, te_numeric))
    classes = [c for c in TX_CLASSES if c != "none"]
    p, r, f, s = precision_recall_fscore_support(te_y, pred, labels=classes, zero_division=0)
    # бинарно: «есть повод» против «нет повода»
    bin_true = np.array([v != "none" for v in te_y])
    bin_pred = np.array([v != "none" for v in pred])
    tp = int((bin_true & bin_pred).sum())
    return {
        "train_transactions": len(y), "test_transactions": len(te_y),
        "precision": round(tp / max(1, bin_pred.sum()), 3),
        "recall": round(tp / max(1, bin_true.sum()), 3),
        "per_class": {c: {"precision": round(float(p[i]), 3), "recall": round(float(r[i]), 3),
                          "f1": round(float(f[i]), 3), "support": int(s[i])} for i, c in enumerate(classes)},
    }


def scan(bundle: dict, txs) -> list[tuple[str, float]]:
    """Для каждой операции: самый вероятный класс и вероятность того, что повод есть."""
    if not txs:
        return []
    X = _tx_matrix(bundle, [tx_text(t) for t in txs], statement_features(txs))
    proba = bundle["scanner"].predict_proba(X)
    classes = list(bundle["scanner"].classes_)
    none_i = classes.index("none")
    out = []
    for row in proba:
        row = row.copy()
        p_case = 1 - row[none_i]
        row[none_i] = -1
        out.append((classes[int(row.argmax())], float(p_case)))
    return out


# --- скоринг шанса успеха -----------------------------------------------------

def _case_matrix(bundle: dict, rows: list[dict], fit: bool = False):
    X = np.array([[r[c] for c in CASE_COLUMNS] for r in rows], dtype=float)
    if fit:
        bundle["case_scaler"] = StandardScaler().fit(X)
    return bundle["case_scaler"].transform(X)


def _train_scorer(bundle: dict, rng: random.Random) -> dict:
    train, test = generate_cases(rng, 8000), generate_cases(rng, 2000)
    X = _case_matrix(bundle, [f for f, _ in train], fit=True)
    clf = LogisticRegression(C=1.0, max_iter=2000)
    clf.fit(X, [y for _, y in train])
    bundle["scorer"] = clf
    bundle["case_reference"] = {c: float(np.mean([f[c] for f, _ in train])) for c in CASE_COLUMNS}

    y_te = [y for _, y in test]
    p = clf.predict_proba(_case_matrix(bundle, [f for f, _ in test]))[:, 1]
    expert = [next(EXPERT_CHANCE[k.removeprefix("kind_")] for k in f if k.startswith("kind_") and f[k]) for f, _ in test]
    weights = dict(zip(CASE_COLUMNS, clf.coef_[0] / bundle["case_scaler"].scale_))
    return {
        "train_cases": len(train), "test_cases": len(test),
        "success_rate": round(float(np.mean(y_te)), 3),
        "auc": round(float(roc_auc_score(y_te, p)), 3),
        "auc_expert": round(float(roc_auc_score(y_te, expert)), 3),
        "brier": round(float(brier_score_loss(y_te, p)), 3),
        "brier_expert": round(float(brier_score_loss(y_te, expert)), 3),
        "weights": {k: round(float(v), 4) for k, v in weights.items()},
    }


def score(bundle: dict, rows: list[dict]) -> list[float]:
    if not rows:
        return []
    return [float(p) for p in bundle["scorer"].predict_proba(_case_matrix(bundle, rows))[:, 1]]


# --- обучение и загрузка ------------------------------------------------------

def train(save: bool = True) -> dict:
    started = time.time()
    rng = random.Random(SEED)
    bundle: dict = {"version": DATA_VERSION, "sklearn": sklearn.__version__}
    scanner_metrics = _train_scanner(bundle, rng)
    scorer_metrics = _train_scorer(bundle, rng)
    bundle["metrics"] = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_seconds": round(time.time() - started, 1),
        "data": "синтетические выписки и история дел (генератор backend/app/ml/synth.py)",
        "scanner": scanner_metrics,
        "scorer": scorer_metrics,
    }
    if save:
        ARTIFACTS.mkdir(exist_ok=True)
        joblib.dump(bundle, MODEL_FILE)
    return bundle


_bundle: dict | None = None
_lock = threading.Lock()


def get() -> dict:
    """Модели в памяти: из файла, а если его нет или он от другой версии — обучает заново."""
    global _bundle
    if _bundle is not None:
        return _bundle
    with _lock:
        if _bundle is None:
            loaded = None
            if MODEL_FILE.exists():
                try:
                    loaded = joblib.load(MODEL_FILE)
                except Exception:  # повреждённый файл или несовместимый pickle
                    loaded = None
            if not loaded or loaded.get("version") != DATA_VERSION or loaded.get("sklearn") != sklearn.__version__:
                loaded = train(save=True)
            _bundle = loaded
    return _bundle

