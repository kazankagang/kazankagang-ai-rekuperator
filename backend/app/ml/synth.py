"""Генератор синтетических данных для обучения.

1. Выписки клиентов с внедрёнными сценариями возврата: у каждой операции есть метка
   (none, dup, sub, imposed, flight, loanins, cool). На них учится сканер операций.
2. История дел пилота: признаки случая и исход (деньги вернули или нет). На ней учится
   модель шанса успеха. Исходы порождаются скрытой логистической зависимостью с шумом,
   похожей на то, что мы ожидаем увидеть в реальном пилоте.

Реальных данных клиентов здесь нет. В пилоте генератор заменяется выгрузкой размеченных дел.
"""
import math
import random
from datetime import date, timedelta

from ..models import Transaction
from .features import CASE_KINDS, add_interactions, GLOBAL_RESPONSE_DAYS, GLOBAL_SUCCESS, KNOWN_MERCHANTS

TX_CLASSES = ["none", "dup", "sub", "imposed", "flight", "loanins", "cool"]

EVERYDAY = [  # описание, категория, мин, макс, частота в месяц
    ("Супермаркет «Утро»", "Продукты", 400, 4500, 6),
    ("Гипермаркет «Лента дня»", "Продукты", 900, 7000, 3),
    ("Пекарня «Колос»", "Продукты", 120, 600, 3),
    ("Такси", "Транспорт", 250, 1400, 5),
    ("Метро, проезд", "Транспорт", 63, 63, 10),
    ("Кофейня", "Кафе и рестораны", 220, 450, 8),
    ("Ресторан «Сад»", "Кафе и рестораны", 1500, 6500, 1),
    ("Аптека", "Здоровье", 250, 3200, 2),
    ("Клиника «Медлайн»", "Здоровье", 1800, 6000, 0.3),
    ("АЗС «Ойл»", "Авто", 1500, 4000, 2),
    ("Маркетплейс «Корзина»", "Маркетплейсы", 300, 9000, 3),
    ("Маркетплейс «Полка»", "Маркетплейсы", 250, 6000, 2),
    ("Магазин электроники «Вольт»", "Электроника", 1500, 45000, 0.4),
    ("Магазин одежды «Стиль»", "Одежда", 1200, 9000, 0.6),
    ("Кинотеатр «Звезда»", "Развлечения", 400, 1600, 0.5),
    ("Перевод по номеру телефона", "Переводы", 300, 15000, 2),
    ("Юридическая консультация «Право»", "Услуги", 2000, 6000, 0.1),
    ("Пакет «Связь+» оператора", "Связь", 450, 900, 1),
]
MONTHLY = [  # оплачиваемые регулярно без пробного периода: это не повод для возврата
    ("Музыкальный сервис «Звук»", "Подписки", 199),
    ("Облачное хранилище «Диск»", "Подписки", 149),
    ("Коммунальные услуги", "ЖКХ", 6800),
    ("Интернет «Домолинк»", "Связь", 650),
    ("Фитнес-клуб «Пульс»", "Спорт", 3500),
]
TRIAL_SERVICES = ["Онлайн-кинотеатр «Кино+»", "Онлайн-кинотеатр «Экран»", "Сервис книг «Читай»",
                  "Приложение «Фитнес Про»", "Онлайн-школа «Английский»", "VPN-сервис «Тоннель»"]
IMPOSED = [
    ("СМС-информирование к кредиту", "Услуги банка", 590, 1990),
    ("Сервис «Юрист 24» при выдаче кредита", "Услуги", 2990, 9900),
    ("Телемедицина «Доктор рядом»", "Услуги", 1990, 6900),
    ("Пакет услуг «Комфорт» к кредиту", "Услуги", 4900, 19900),
    ("Карта помощи на дорогах «АвтоПлюс»", "Услуги", 9900, 49000),
    ("Сертификат «Финансовая защита»", "Услуги", 2500, 15000),
]
AIRLINES = ["Авиакомпания «Северный ветер»", "Авиакомпания «Горизонт»", "Авиакомпания «Крыло»"]
INSURERS = ["СК «Надёжный полис»", "СК «Опора»", "Страховая «Гарант»"]


def _d(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def generate_statement(rng: random.Random, n_days: int | None = None) -> tuple[list[Transaction], dict[str, str]]:
    """Одна выписка: обычные траты плюс случайные сценарии. Возвращает операции и метки по id."""
    n_days = n_days or rng.randint(45, 120)
    end = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
    start = end - timedelta(days=n_days)
    rows: list[tuple[date, str, float, str, str, str]] = []  # дата, описание, сумма, категория, детали, метка

    def add(d, desc, amount, cat, details="", label="none"):
        if start <= d <= end:
            rows.append((d, desc, round(amount, 2), cat, details, label))

    def rand_day(lo=0, hi=None):
        return start + timedelta(days=rng.randint(lo, n_days if hi is None else hi))

    # обычные траты
    for desc, cat, lo, hi, per_month in rng.sample(EVERYDAY, rng.randint(8, len(EVERYDAY))):
        fixed = rng.random() < 0.5 and hi - lo < 300 or lo == hi
        price = rng.randint(lo, hi)
        for _ in range(max(0, round(rng.gauss(per_month, per_month / 3) * n_days / 30))):
            add(rand_day(), desc, price if fixed else rng.randint(lo, hi), cat,
                rng.choice(["", "", "", "покупка", "оплата картой"]))
    # зарплата и регулярные платежи
    salary = rng.randint(45, 250) * 1000
    for k in range(0, n_days, 30):
        add(start + timedelta(days=k + 3), "Зарплата", -salary, "Поступления")
    for desc, cat, price in rng.sample(MONTHLY, rng.randint(1, 4)):
        offset = rng.randint(0, 29)
        for k in range(offset, n_days + 1, 30):
            add(start + timedelta(days=k), desc, price, cat, rng.choice(["", "автоплатёж", "автопродление"]))
    # дубли без нарушения: две одинаковые покупки в один день у привычного мерчанта (кофе, метро)
    if rng.random() < 0.5:
        d = rand_day()
        add(d, "Метро, проезд", 63, "Транспорт")
        add(d, "Метро, проезд", 63, "Транспорт")

    # --- сценарии возврата ---
    if rng.random() < 0.35:  # двойное списание, иногда на следующий день или с другим номером терминала
        desc, cat, lo, hi, _ = rng.choice([e for e in EVERYDAY if e[2] >= 300 and e[1] not in ("Переводы",)])
        d, amount = rand_day(), rng.randint(max(lo, 700), hi)
        add(d, desc, amount, cat)
        variant = rng.random()
        if variant < 0.5:
            add(d, desc, amount, cat, label="dup")
        elif variant < 0.8:
            add(d + timedelta(days=1), desc, amount, cat, label="dup")
        else:
            add(d, f"{desc} *{rng.randint(1000, 9999)}", amount, cat, label="dup")
    if rng.random() < 0.35:  # пробный период стал платной подпиской
        svc = rng.choice(TRIAL_SERVICES)
        d = rand_day(0, max(1, n_days - 35))
        add(d, svc, rng.choice([1, 1, 0.01, 10]), "Подписки", rng.choice(["пробный период", "trial", ""]))
        price = rng.choice([299, 399, 499, 599, 799, 990])
        for k in range(30, n_days, 30):
            add(d + timedelta(days=k), svc, price, rng.choice(["Подписки", "Развлечения", "Цифровые услуги"]),
                rng.choice(["автопродление", "", "продление подписки"]), label="sub")
    if rng.random() < 0.3:  # навязанная услуга при выдаче кредита
        d = rand_day(0, n_days - 2)
        loan_no = f"№ {rng.randint(10, 99)}-{rng.randint(100, 999)}"
        add(d, f"Выдача кредита {loan_no}", -rng.randint(30, 500) * 1000, "Кредиты")
        desc, cat, lo, hi = rng.choice(IMPOSED)
        add(d + timedelta(days=rng.choice([0, 0, 1, 2])), desc, rng.randint(lo, hi), cat,
            rng.choice(["", "подключено при выдаче кредита", f"к кредиту {loan_no}"]), label="imposed")
    if rng.random() < 0.25:  # задержка рейса
        air = rng.choice(AIRLINES)
        d = rand_day()
        fd = d + timedelta(days=rng.randint(3, 40))
        hours = round(rng.uniform(2, 9), 1)
        code = f"{rng.choice(['NW', 'GZ', 'KR', 'SU'])}{rng.randint(100, 9999)}"
        add(d, f"{air}, билет", rng.randint(3500, 25000), "Авиабилеты",
            f"рейс {code}, {_d(fd)}, задержка {hours} ч", label="flight")
    # трудные отрицательные примеры: похожие на сценарии, но повода нет
    if rng.random() < 0.15:  # две одинаковые вещи купили сознательно
        desc, cat, lo, hi, _ = rng.choice([e for e in EVERYDAY if e[1] == "Маркетплейсы"])
        d, amount = rand_day(), rng.randint(lo, hi)
        add(d, desc, amount, cat, "заказ 1 из 2")
        add(d, desc, amount, cat, "заказ 2 из 2")
    if rng.random() < 0.15:  # услуга куплена сама по себе, без кредита
        desc, cat, lo, hi = rng.choice(IMPOSED[1:4])
        add(rand_day(), desc.replace(" при выдаче кредита", "").replace(" к кредиту", ""), rng.randint(lo, hi), cat)
    if rng.random() < 0.1:  # проверка карты на 1 ₽ у магазина
        add(rand_day(), rng.choice(["Маркетплейс «Корзина»", "Такси"]), 1, "Прочее", "проверка карты")
    if rng.random() < 0.15:  # перелёт без задержки: не повод
        add(rand_day(), f"{rng.choice(AIRLINES)}, билет", rng.randint(3500, 25000), "Авиабилеты", "рейс по расписанию")
    if rng.random() < 0.2:  # страховка к кредиту и досрочное погашение
        d = rand_day(0, n_days - 20)
        term = rng.choice([12, 24, 36, 60])
        add(d, f"Страховая премия по полису к кредиту № {rng.randint(10, 99)}-{rng.randint(100, 999)}",
            rng.randint(8, 90) * 1000, "Страхование", f"к кредиту, срок {term} мес", label="loanins")
        add(d + timedelta(days=rng.randint(15, n_days - (d - start).days)), "Досрочное погашение кредита",
            rng.randint(50, 900) * 1000, "Кредиты", "полное досрочное погашение")
    if rng.random() < 0.2:  # страховка в период охлаждения
        d = end - timedelta(days=rng.randint(0, 13))
        add(d, f"{rng.choice(INSURERS)}, страхование «Защита карты»", rng.randint(990, 9900), "Страхование",
            "оформлено при выпуске карты, срок 12 мес", label="cool")
    elif rng.random() < 0.15:  # старая страховка: охлаждение прошло
        add(start + timedelta(days=rng.randint(0, 10)), f"{rng.choice(INSURERS)}, страхование имущества",
            rng.randint(990, 9900), "Страхование", "срок 12 мес")

    rows.sort(key=lambda r: r[0])
    txs, labels = [], {}
    for i, (d, desc, amount, cat, details, label) in enumerate(rows):
        t = Transaction(id=f"t{i}", date=d, desc=desc, amount=amount, cat=cat, details=details)
        txs.append(t)
        labels[t.id] = label
    return txs, labels


# --- история дел пилота -------------------------------------------------------

KIND_BASE = {  # логит базовой вероятности успеха по типу дела
    "flight": 1.2, "sub": 0.25, "dup": 2.2, "loanins": 1.5, "cool": 2.0, "imposed": 0.9, "other": -0.4,
}
KIND_AMOUNT = {"flight": 9000, "sub": 600, "dup": 5000, "loanins": 18000, "cool": 3000, "imposed": 8000, "other": 5000}

UNKNOWN_MERCHANTS = 40


def generate_cases(rng: random.Random, n: int) -> list[tuple[dict, int]]:
    """Признаки исторических дел и исход: 1, если деньги вернули."""
    known = list(KNOWN_MERCHANTS.values())
    unknown = [(min(0.95, max(0.2, rng.gauss(GLOBAL_SUCCESS, 0.12))), rng.randint(5, 30)) for _ in range(UNKNOWN_MERCHANTS)]
    out = []
    for _ in range(n):
        kind = rng.choices(CASE_KINDS, weights=[18, 16, 14, 14, 12, 16, 10])[0]
        is_known = rng.random() < 0.45
        true_success, days = rng.choice(known) if is_known else rng.choice(unknown)
        amount = max(50.0, rng.lognormvariate(math.log(KIND_AMOUNT[kind]), 0.7))
        age = rng.choice([rng.randint(0, 30), rng.randint(0, 120), rng.randint(0, 365)])
        evidence = rng.choice([1, 1, 1, 2, 2, 3])
        hours = round(rng.uniform(2, 9), 1) if kind == "flight" else 0.0
        src = rng.choices(["rules", "ml", "ai"], weights=[70, 20, 10])[0]
        z = (KIND_BASE[kind]
             + 4.0 * (true_success - GLOBAL_SUCCESS)
             - 0.03 * (days - GLOBAL_RESPONSE_DAYS)
             - 0.35 * math.log(amount / KIND_AMOUNT[kind])
             - 0.006 * age
             + 0.3 * (evidence - 1)
             + (0.25 * (hours - 4) if kind == "flight" else 0)
             - (1.6 if kind == "cool" and age > 14 else 0)
             - (1.2 if kind == "imposed" and age > 30 else 0)
             - {"rules": 0, "ml": 0.35, "ai": 0.8}[src]
             + rng.gauss(0, 0.5))
        y = int(rng.random() < 1 / (1 + math.exp(-z)))
        # для известного мерчанта модель видит его статистику пилота, для нового — средние
        f = {f"kind_{k}": float(k == kind) for k in CASE_KINDS}
        f.update({
            "log_amount": math.log1p(amount),
            "merchant_success": true_success if is_known else GLOBAL_SUCCESS,
            "merchant_known": float(is_known),
            "response_days": days if is_known else GLOBAL_RESPONSE_DAYS,
            "age_days": float(age), "evidence": float(evidence), "delay_h": hours,
            "src_ml": float(src == "ml"), "src_ai": float(src == "ai"),
        })
        out.append((add_interactions(f), y))
    return out
