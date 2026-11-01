"""ML поверх правил: дополнительные случаи от сканера и шанс успеха от модели скоринга."""
from datetime import date, timedelta

from ..models import CaseOut, ClaimPart, Factor, Transaction
from . import model
from .features import CASE_COLUMNS, KIND_LABELS, case_features, merchant_key

SCAN_THRESHOLD = 0.6  # ниже этой уверенности сканер случай не показывает

FACTOR_GROUPS = {
    "merchant": ["merchant_success", "merchant_known", "response_days"],
    "amount": ["log_amount"],
    "age": ["age_days", "cool_expired", "imposed_late"],
    "evidence": ["evidence"],
    "delay": ["delay_h"],
    "source": ["src_ml", "src_ai"],
}


def _fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _rub(n: float) -> str:
    return f"{round(n):,}".replace(",", " ") + " ₽"


def _factor_label(group: str, f: dict, case: CaseOut) -> str:
    if group == "merchant":
        if not f["merchant_known"]:
            return "Мерчант новый для пилота: берём среднюю успешность"
        return f"Мерчант в пилоте возвращает деньги в {round(f['merchant_success'] * 100)}% дел, отвечает за {round(f['response_days'])} дн."
    if group == "amount":
        return f"Сумма требования {_rub(case.amount)}"
    if group == "age":
        if f["cool_expired"]:
            return "Прошло больше 14 дней периода охлаждения"
        if f["imposed_late"]:
            return "Прошло больше 30 дней на отказ от доп. услуги"
        return f"С последней операции по делу прошло {round(f['age_days'])} дн."
    if group == "evidence":
        n = round(f["evidence"])
        return f"Подтверждающих операций в выписке: {n}"
    if group == "delay":
        return f"Задержка рейса {str(f['delay_h']).replace('.', ',')} ч"
    return "Случай найден ИИ, нужна проверка юриста" if f["src_ai"] else "Случай найден ML-сканером, а не правилом"


def explain(bundle: dict, f: dict, p: float, case: CaseOut) -> list[Factor]:
    """Вклад групп признаков в п.п.: насколько изменится шанс, если признак сделать «средним»."""
    ref = bundle["case_reference"]
    variants, groups = [], []
    for g, cols in FACTOR_GROUPS.items():
        if g == "delay" and not f["delay_h"]:
            continue
        if g == "source" and not (f["src_ml"] or f["src_ai"]):
            continue
        alt = dict(f)
        for c in cols:
            alt[c] = 0.0 if c in ("src_ml", "src_ai", "cool_expired", "imposed_late") else ref[c]
        variants.append(alt)
        groups.append(g)
    base = model.score(bundle, variants)
    factors = [Factor(label=_factor_label(g, f, case), impact=round((p - b) * 100)) for g, b in zip(groups, base)]
    factors = [x for x in factors if x.impact]
    return sorted(factors, key=lambda x: abs(x.impact), reverse=True)[:4]


def score_cases(cases: list[CaseOut], txs: list[Transaction]) -> list[CaseOut]:
    """Проставляет шанс успеха от модели. Экспертная оценка правил сохраняется в expert_chance."""
    if not cases:
        return []
    bundle = model.get()
    today = max(t.date for t in txs) if txs else None
    feats = [case_features(c, txs, today) for c in cases]
    probs = model.score(bundle, feats)
    out = []
    for c, f, p in zip(cases, feats, probs):
        out.append(c.model_copy(update={
            "expert_chance": c.expert_chance or c.chance,
            "chance": max(1, min(99, round(p * 100))),
            "chance_source": "ml",
            "factors": explain(bundle, f, p, c),
        }))
    return out


def _ml_case(kind: str, group: list[Transaction], confidence: float, today: date) -> CaseOut | None:
    t = group[-1]
    if kind == "dup":
        return CaseOut(
            id=f"ml-dup-{t.id}", kind="Двойное списание", title="Похоже на повторное списание",
            sub=f"{t.desc} · {_fmt(t.date)}",
            parts=[ClaimPart(label="Повторное списание", sum=t.amount)],
            basis=["ст. 1102 ГК РФ: возврат неосновательного обогащения",
                   "Оспаривание операции через банк по правилам платёжной системы"],
            evidence=[x.id for x in group], to="Продавец; параллельно банк открывает спор по операции",
            deadline="Перед отправкой проверьте, что вторая покупка не была сделана сознательно.",
            ml=True, confidence=confidence, amount=t.amount,
        )
    if kind == "sub":
        used = min(30, max(0, (today - t.date).days))
        refund = round(t.amount * (30 - used) / 30)
        if refund <= 0:
            return None
        return CaseOut(
            id=f"ml-sub-{t.id}", kind="Подписки", title="Подписка списывается после пробного периода",
            sub=f"{t.desc} · {len(group)} платн. списания",
            parts=[ClaimPart(label=f"Возврат за неиспользованные {30 - used} дн. текущего периода", sum=refund)],
            basis=["ст. 32 Закона о защите прав потребителей: отказ от услуги в любой момент с оплатой только фактически оказанного"],
            evidence=[x.id for x in group], to="Сервис подписки",
            deadline="Требование о возврате удовлетворяется в течение 10 дней (ст. 31 ЗоЗПП).",
            ml=True, confidence=confidence, amount=refund,
        )
    if kind == "imposed":
        last_day = t.date + timedelta(days=30)
        return CaseOut(
            id=f"ml-imposed-{t.id}", kind="Навязанные услуги", title="Доп. услуга, подключённая при выдаче кредита",
            sub=f"{t.desc} · {_fmt(t.date)}",
            parts=[ClaimPart(label="Полная стоимость услуги", sum=t.amount)],
            basis=["ч. 2.7 ст. 7 Закона № 353-ФЗ: отказ от доп. услуги, оформленной при выдаче кредита, в течение 30 дней с возвратом денег",
                   "ст. 16 ЗоЗПП: запрещено обусловливать одну услугу обязательным приобретением другой"],
            evidence=[x.id for x in group], to="Продавец услуги; при отказе — кредитор (ч. 2.10 ст. 7 353-ФЗ)",
            deadline=(f"Заявление нужно подать до {_fmt(last_day)}." if today <= last_day
                      else "30 дней на отказ прошли, возврат возможен только через суд по ст. 16 ЗоЗПП."),
            ml=True, confidence=confidence, amount=t.amount,
        )
    return None


def find_cases(txs: list[Transaction], rule_cases: list[CaseOut]) -> list[CaseOut]:
    """Случаи, которые нашёл сканер и не нашли правила."""
    if not txs:
        return []
    covered = {i for c in rule_cases for i in c.evidence}
    today = max(t.date for t in txs)
    preds = model.scan(model.get(), txs)
    seen_groups: set[tuple[str, str]] = set()
    found = []
    for t, (kind, p) in zip(txs, preds):
        if p < SCAN_THRESHOLD or t.id in covered or kind not in ("dup", "sub", "imposed"):
            continue
        key = merchant_key(t.desc)[:12]
        if kind == "dup":
            group = [x for x in txs if x.amount == t.amount and merchant_key(x.desc)[:6] == key[:6]
                     and 0 <= (t.date - x.date).days <= 1 and x.date <= t.date]
        elif kind == "sub":
            if (kind, key) in seen_groups:
                continue
            group = sorted((x for x in txs if merchant_key(x.desc)[:12] == key and x.amount > 0), key=lambda x: x.date)
        else:
            group = [t]
        seen_groups.add((kind, key))
        c = _ml_case(kind, group, round(p, 3), today)
        if c:
            found.append(c)
    return found


def enrich(txs: list[Transaction], rule_cases: list[CaseOut]) -> list[CaseOut]:
    """Правила + сканер, у всех шанс от модели. Сортировка по ожидаемой сумме возврата."""
    cases = score_cases(rule_cases + find_cases(txs, rule_cases), txs)
    return sorted(cases, key=lambda c: c.amount * c.chance, reverse=True)


def info() -> dict:
    bundle = model.get()
    m = bundle["metrics"]
    w = m["scorer"]["weights"]
    return {
        "models": [
            {"name": "Сканер операций", "algorithm": "TF-IDF по тексту операции + признаки выписки, логистическая регрессия",
             "classes": list(bundle["scanner"].classes_), "threshold": SCAN_THRESHOLD},
            {"name": "Скоринг шанса успеха", "algorithm": "логистическая регрессия",
             "features": CASE_COLUMNS},
        ],
        "metrics": m,
        "kind_labels": KIND_LABELS,
        "top_weights": sorted(w.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6],
        "sklearn": bundle["sklearn"],
    }

