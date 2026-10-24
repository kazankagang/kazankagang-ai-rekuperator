"""Признаки для ML-моделей: по операции в контексте всей выписки и по найденному случаю."""
import math
import re
from collections import defaultdict
from datetime import date

from ..models import CaseOut, Transaction

# Справочник мерчантов пилота: доля успешных дел и срок ответа (те же цифры, что на дашборде).
from ..dashboard import MERCHANTS

GLOBAL_SUCCESS = 0.64
GLOBAL_RESPONSE_DAYS = 14

KNOWN_MERCHANTS = {
    re.sub(r"[«»\"']", "", name).lower(): (success / 100, days)
    for name, _issue, _cases, success, days, _ret in MERCHANTS
}


def merchant_key(desc: str) -> str:
    """Нормализованное имя мерчанта: без кавычек, цифр, номеров терминалов и лишних пробелов."""
    s = re.sub(r"[«»\"'*#№]", " ", desc.lower())
    s = re.sub(r"\d+", " ", s)
    s = re.sub(r"[,.;:()—-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def merchant_stats(text: str) -> tuple[float, float, bool]:
    """Успешность и срок ответа мерчанта из пилота. Неизвестный мерчант получает средние по пилоту."""
    t = re.sub(r"[«»\"']", "", text).lower()
    for name, (success, days) in KNOWN_MERCHANTS.items():
        # «Авиакомпания Северный ветер»: достаточно совпадения собственного имени
        own = name.split(" ", 1)[-1] if " " in name else name
        if name in t or own in t:
            return success, days, True
    return GLOBAL_SUCCESS, GLOBAL_RESPONSE_DAYS, False


def delay_hours(details: str) -> float:
    m = re.search(r"задерж\S*\s*([\d.,]+)", details, re.I)
    if not m:
        return 0.0
    try:
        return float(m[1].replace(",", ".").rstrip("."))
    except ValueError:
        return 0.0


# --- Сканер операций ---------------------------------------------------------

TX_NUMERIC = [
    "log_amount", "same_day_twin", "next_day_twin", "twin_other_desc", "merchant_count",
    "prev_trial", "trial_then_paid", "paid_after_trial_n", "loan_before_3d", "loan_before_x_service",
    "early_payoff_after", "days_to_end", "delay_h", "is_small", "habitual", "twin_not_habitual",
]


def tx_text(t: Transaction) -> str:
    return f"{t.desc} | {t.cat} | {t.details}".lower()


def statement_features(txs: list[Transaction], today: date | None = None) -> list[dict]:
    """Числовые признаки каждой операции с учётом соседних операций выписки."""
    if not txs:
        return []
    today = today or max(t.date for t in txs)
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in txs:
        if t.amount > 0:
            by_merchant[merchant_key(t.desc)].append(t)
    loans = [t for t in txs if t.amount < 0 and re.search(r"кредит|займ", t.desc, re.I)]
    payoffs = [t for t in txs if re.search(r"досрочн", f"{t.desc} {t.details}", re.I)]

    rows = []
    for t in txs:
        f = dict.fromkeys(TX_NUMERIC, 0.0)
        f["log_amount"] = math.log1p(abs(t.amount))
        f["days_to_end"] = min(120, (today - t.date).days) / 30
        f["delay_h"] = delay_hours(t.details)
        if t.amount <= 0:
            f["is_small"] = 0.0
            rows.append(f)
            continue
        same = by_merchant[merchant_key(t.desc)]
        f["merchant_count"] = math.log1p(len(same))
        f["is_small"] = float(t.amount <= 10)
        # дубль: та же сумма у того же мерчанта раньше в тот же или предыдущий день
        earlier = [x for x in same if x is not t and x.amount == t.amount and 0 <= (t.date - x.date).days <= 1
                   and (x.date, x.id) < (t.date, t.id)]
        f["same_day_twin"] = float(any(x.date == t.date for x in earlier))
        f["next_day_twin"] = float(any(x.date != t.date for x in earlier))
        f["twin_other_desc"] = float(any(
            x is not t and x.amount == t.amount and x.amount >= 300 and merchant_key(x.desc) != merchant_key(t.desc)
            and merchant_key(x.desc)[:6] == merchant_key(t.desc)[:6] and 0 <= (t.date - x.date).days <= 1
            and (x.date, x.id) < (t.date, t.id) for x in txs))
        # привычные покупки: много списаний у мерчанта с похожей суммой (кофе, проезд)
        f["habitual"] = float(len(same) >= 4)
        trials = [x for x in same if x.amount <= 10 and x.date < t.date]
        f["prev_trial"] = float(bool(trials))
        if trials and t.amount > 10:
            f["trial_then_paid"] = 1.0
            f["paid_after_trial_n"] = sum(1 for x in same if x.amount > 10 and x.date > trials[0].date)
        lb = [x for x in loans if 0 <= (t.date - x.date).days <= 3]
        f["loan_before_3d"] = float(bool(lb))
        f["loan_before_x_service"] = float(bool(lb) and not re.search(r"кредит|погашен", t.desc, re.I))
        f["early_payoff_after"] = float(any(x.date > t.date for x in payoffs))
        f["twin_not_habitual"] = float((f["same_day_twin"] or f["next_day_twin"] or f["twin_other_desc"])
                                       and not f["habitual"])
        rows.append(f)
    return rows


# --- Скоринг шанса успеха ----------------------------------------------------

CASE_KINDS = ["flight", "sub", "dup", "loanins", "cool", "imposed", "other"]
KIND_LABELS = {
    "flight": "задержка рейса", "sub": "подписка после пробного периода", "dup": "двойное списание",
    "loanins": "страховка по погашенному кредиту", "cool": "период охлаждения",
    "imposed": "навязанная услуга", "other": "нестандартный случай",
}
CASE_NUMERIC = ["log_amount", "merchant_success", "merchant_known", "response_days", "age_days",
                "evidence", "delay_h", "src_ml", "src_ai", "cool_expired", "imposed_late"]


def case_kind(case: CaseOut) -> str:
    cid = case.id.removeprefix("ml-")
    for k in ("flight", "sub", "dup", "loanins", "cool", "imposed"):
        if cid.startswith(k + "-"):
            return k
    return "other"


def case_features(case: CaseOut, txs: list[Transaction], today: date | None = None) -> dict:
    by_id = {t.id: t for t in txs}
    ev = [by_id[i] for i in case.evidence if i in by_id]
    today = today or (max(t.date for t in txs) if txs else date.today())
    success, days, known = merchant_stats(" ".join([*(t.desc for t in ev), case.sub]))
    hours = max([delay_hours(t.details) for t in ev] + [0.0])
    if not hours:
        m = re.search(r"на\s*([\d,]+)\s*ч", case.title)
        hours = float(m[1].replace(",", ".")) if m else 0.0
    age = (today - max(t.date for t in ev)).days if ev else 30  # от последнего события: платежа, погашения
    kind = case_kind(case)
    f = {f"kind_{k}": float(k == kind) for k in CASE_KINDS}
    f.update({
        "log_amount": math.log1p(max(case.amount, 0)),
        "merchant_success": success,
        "merchant_known": float(known),
        "response_days": days,
        "age_days": min(age, 365),
        "evidence": min(len(ev) or 1, 5),
        "delay_h": hours,
        "src_ml": float(case.ml),
        "src_ai": float(case.ai),
    })
    return add_interactions(f)


def add_interactions(f: dict) -> dict:
    """Сроки, после которых право на возврат слабеет: охлаждение 14 дней, отказ от доп. услуги 30 дней."""
    f["cool_expired"] = float(f["kind_cool"] and f["age_days"] > 14)
    f["imposed_late"] = float(f["kind_imposed"] and f["age_days"] > 30)
    return f


CASE_COLUMNS = [f"kind_{k}" for k in CASE_KINDS] + CASE_NUMERIC
