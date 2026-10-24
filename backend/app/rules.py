"""Движок правил: находит в операциях случаи, когда клиенту положен возврат.

Каждое правило возвращает список случаев с расчётом суммы, правовыми основаниями
и операциями-доказательствами. Шанс успеха пока экспертная оценка по типу случая.
"""
import math
import re
from collections import defaultdict
from datetime import date, timedelta

from .models import CaseOut, ClaimPart, Transaction

TRAVEL_PAYOUT = 3000  # демо-условие страховки к карте: задержка рейса от 4 ч
COOLING_DAYS = 14


def _fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[«»\"']", "", s.lower())).strip()


def _term_months(details: str, default: int = 12) -> int:
    m = re.search(r"срок\s*(\d+)", details, re.I)
    return int(m[1]) if m else default


def _case(**kw) -> CaseOut:
    parts = kw["parts"]
    return CaseOut(**kw, amount=round(sum(p.sum for p in parts), 2))


def flight_delays(txs: list[Transaction], today: date) -> list[CaseOut]:
    found = []
    for t in txs:
        if not re.search(r"авиа", t.cat, re.I) or t.amount <= 0:
            continue
        dm = re.search(r"задержк\S*\s*([\d.,]+)", t.details, re.I)
        if not dm:
            continue
        hours = float(dm[1].replace(",", "."))
        if hours < 2:
            continue
        fdm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", t.details)
        fdate = date(int(fdm[3]), int(fdm[2]), int(fdm[1])) if fdm else None
        fm = re.search(r"рейс\s*([A-ZА-Я0-9]{2}\s?\d{2,4})", t.details, re.I)
        flight = fm[1] if fm else ""

        full_hours = math.floor(hours)
        parts = [ClaimPart(label=f"Штраф перевозчика: 25 ₽ × {full_hours} ч", sum=min(25 * full_hours, t.amount * 0.5))]
        basis = ["ст. 120 Воздушного кодекса РФ: 25 ₽ за каждый час задержки, не более 50% стоимости перевозки"]
        evidence = [t.id]
        if hours >= 4:
            parts.append(ClaimPart(label="Выплата по страховке «Путешествия» к карте (задержка от 4 ч)", sum=TRAVEL_PAYOUT))
            basis.append("Условия страховой программы к карте: задержка рейса от 4 часов")
        if fdate:
            for x in txs:
                if (x.amount > 0 and x.date == fdate and re.search(r"кафе|ресторан|питан", x.cat, re.I)
                        and re.search(r"аэропорт", f"{x.desc} {x.details}", re.I)):
                    parts.append(ClaimPart(label="Расходы на питание в аэропорту во время задержки", sum=x.amount))
                    evidence.append(x.id)
            if len(evidence) > 1:
                basis.append("п. 99 ФАП-82: при задержке более 4 ч перевозчик обязан обеспечить горячее питание; расходы подлежат возмещению как убытки")

        found.append(_case(
            id=f"flight-{t.id}", kind="Рейсы",
            title=f"Задержка рейса на {str(hours).replace('.', ',')} ч",
            sub=(f"{flight} · " if flight else "") + _fmt(fdate or t.date),
            parts=parts, basis=basis, evidence=evidence, chance=90 if hours >= 4 else 75,
            to="Авиаперевозчик и страховая компания по программе к карте",
            deadline="Перевозчик отвечает на претензию в течение 30 дней (ст. 124 ВК РФ).",
        ))
    return found


def trial_subscriptions(txs: list[Transaction], today: date) -> list[CaseOut]:
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in txs:
        if re.search(r"подписк", t.cat, re.I) and t.amount > 0:
            groups[_norm(t.desc)].append(t)
    found = []
    for arr in groups.values():
        arr.sort(key=lambda t: t.date)
        trial = next((t for t in arr if t.amount <= 10), None)
        if not trial:
            continue
        paid = [t for t in arr if t.amount > 10 and t.date > trial.date]
        if not paid:
            continue
        last = paid[-1]
        used = min(30, max(0, (today - last.date).days))
        refund = round(last.amount * (30 - used) / 30)
        if refund <= 0:
            continue
        found.append(_case(
            id=f"sub-{last.id}", kind="Подписки", title="Пробный период стал платной подпиской",
            sub=f"{last.desc} · {len(paid)} платн. списания",
            parts=[ClaimPart(label=f"Возврат за неиспользованные {30 - used} дн. текущего периода", sum=refund)],
            basis=["ст. 32 Закона о защите прав потребителей: отказ от услуги в любой момент с оплатой только фактически оказанного",
                   "ст. 16 ЗоЗПП: недопустимы условия, ущемляющие права потребителя"],
            evidence=[trial.id, *[p.id for p in paid]], chance=60,
            to="Сервис подписки",
            deadline="Требование о возврате удовлетворяется в течение 10 дней (ст. 31 ЗоЗПП).",
        ))
    return found


def double_charges(txs: list[Transaction], today: date) -> list[CaseOut]:
    groups: dict[tuple, list[Transaction]] = defaultdict(list)
    for t in txs:
        if t.amount > 0 and not re.search(r"подписк|кредит", t.cat, re.I):
            groups[(t.date, _norm(t.desc), t.amount)].append(t)
    found = []
    for g in groups.values():
        if len(g) < 2:
            continue
        found.append(_case(
            id=f"dup-{g[0].id}", kind="Двойное списание", title="Двойное списание за одну покупку",
            sub=f"{g[0].desc} · {_fmt(g[0].date)}",
            parts=[ClaimPart(label=f"Повторное списание × {len(g) - 1}", sum=g[0].amount * (len(g) - 1))],
            basis=["ст. 1102 ГК РФ: возврат неосновательного обогащения",
                   "Оспаривание операции через банк по правилам платёжной системы"],
            evidence=[x.id for x in g], chance=95,
            to="Продавец; параллельно банк открывает спор по операции",
            deadline="Оспаривание через банк обычно занимает до 30 дней.",
        ))
    return found


def insurance(txs: list[Transaction], today: date) -> list[CaseOut]:
    policies = [t for t in txs if t.amount > 0 and re.search(r"страх", f"{t.cat} {t.desc}", re.I)]
    early = [t for t in txs if re.search(r"досрочн", f"{t.desc} {t.details}", re.I)]
    found, used_ids = [], set()

    for t in policies:
        if not re.search(r"кредит", f"{t.desc} {t.details}", re.I):
            continue
        e = next((x for x in early if x.date > t.date), None)
        if not e:
            continue
        term = _term_months(t.details)
        months_used = max(1, math.ceil((e.date - t.date).days / 30.44))
        left = max(0, term - months_used)
        refund = round(t.amount * left / term)
        if refund <= 0:
            continue
        used_ids.add(t.id)
        found.append(_case(
            id=f"loanins-{t.id}", kind="Страховки", title="Страховка по досрочно погашенному кредиту",
            sub=f"Кредит погашен {_fmt(e.date)}",
            parts=[ClaimPart(label=f"Часть премии за {left} из {term} мес.", sum=refund)],
            basis=["ч. 10 и 12 ст. 11 Закона № 353-ФЗ «О потребительском кредите»: при досрочном погашении возвращается часть премии пропорционально неистёкшему сроку",
                   "Срок возврата: 7 рабочих дней с даты заявления"],
            evidence=[t.id, e.id], chance=85,
            to="Страховая компания (при её отказе — кредитор, ч. 12 ст. 11 353-ФЗ)",
            deadline="Страховщик возвращает деньги в течение 7 рабочих дней.",
        ))

    for t in policies:
        if t.id in used_ids:
            continue
        days = (today - t.date).days
        if days > COOLING_DAYS:
            continue
        term = _term_months(t.details)
        refund = round(t.amount * (1 - days / (term * 30.44)))
        found.append(_case(
            id=f"cool-{t.id}", kind="Страховки", title="Отказ от страховки в период охлаждения",
            sub=f"{t.desc} · куплена {days} дн. назад, осталось {COOLING_DAYS - days} дн.",
            parts=[ClaimPart(label=f"Премия за вычетом {days} дн. действия" if days else "Премия полностью", sum=refund)],
            basis=["Указание Банка России № 3854-У: отказ от добровольного страхования в течение 14 календарных дней",
                   "Возврат премии в течение 10 рабочих дней"],
            evidence=[t.id], chance=92,
            to="Страховая компания",
            deadline=f"Заявление нужно подать до {_fmt(t.date + timedelta(days=COOLING_DAYS))}.",
        ))
    return found


RULES = [flight_delays, trial_subscriptions, double_charges, insurance]


def detect(txs: list[Transaction], today: date | None = None) -> list[CaseOut]:
    """Запускает все правила. Дата анализа по умолчанию: последняя дата в выписке."""
    if not txs:
        return []
    today = today or max(t.date for t in txs)
    cases = [c for rule in RULES for c in rule(txs, today)]
    return sorted(cases, key=lambda c: c.amount, reverse=True)
