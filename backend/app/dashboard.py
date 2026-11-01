"""Демо-данные дашборда банка: модель пилота на 10 000 клиентов, май – октябрь 2026."""

COMMISSION = 0.2

MONTHLY_RETURNS = [  # тыс. ₽
    ("Май", 412), ("Июн", 655), ("Июл", 980), ("Авг", 1140), ("Сен", 1380), ("Окт", 1610),
]

SCENARIOS = [  # тыс. ₽ за пилот
    ("Страховки по кредитам", 2650),
    ("Задержки и отмены рейсов", 2100),
    ("Подписки и автопродления", 690),
    ("Двойные списания", 520),
    ("Период охлаждения", 217),
]

MERCHANTS = [  # мерчант, частое нарушение, дел, успех %, ответ дней, возвращено тыс. ₽
    ("Авиакомпания «Северный ветер»", "Задержки рейсов без выплаты штрафа", 412, 71, 24, 1180),
    ("Онлайн-кинотеатр «Кино+»", "Пробный период без уведомления", 268, 58, 9, 96),
    ("СК «Надёжный полис»", "Затягивание возврата премии", 197, 83, 6, 1940),
    ("Маркетплейс «Корзина»", "Двойные списания, отказ в возврате", 154, 66, 11, 310),
    ("Авиакомпания «Горизонт»", "Отмены рейсов", 133, 62, 27, 520),
    ("Магазин электроники «Вольт»", "Двойные списания", 61, 91, 5, 210),
]


def build() -> dict:
    total = sum(v for _, v in MONTHLY_RETURNS)
    last, prev = MONTHLY_RETURNS[-1][1], MONTHLY_RETURNS[-2][1]
    return {
        "period": "Демо-данные: модель пилота на 10 000 клиентов, май – октябрь 2026",
        "commission_rate": COMMISSION,
        "kpis": {
            "returned_thousands": total,
            "commission_thousands": round(total * COMMISSION),
            "month_growth_pct": round((last / prev - 1) * 100),
            "success_rate_pct": 64,
            "avg_days_to_return": 12,
            "cases_sent": 2340,
        },
        "monthly": [{"month": m, "value": v} for m, v in MONTHLY_RETURNS],
        "scenarios": [{"name": n, "value": v} for n, v in SCENARIOS],
        "merchants": [
            {"name": n, "issue": i, "cases": c, "success_pct": s, "response_days": d, "returned_thousands": r}
            for n, i, c, s, d, r in MERCHANTS
        ],
    }
