from datetime import date
from pathlib import Path

import pytest

from backend.app.rules import detect
from backend.app.statement import StatementError, parse_csv

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo_statement.csv"


@pytest.fixture
def demo_cases():
    return {c.kind + "|" + c.title: c for c in detect(parse_csv(DEMO.read_text(encoding="utf-8")))}


def test_demo_finds_all_scenarios(demo_cases):
    assert len(demo_cases) == 5
    assert round(sum(c.amount for c in demo_cases.values())) == 30705


def test_flight_delay_amounts(demo_cases):
    c = demo_cases["Рейсы|Задержка рейса на 4,3 ч"]
    assert [p.sum for p in c.parts] == [100, 3000, 1250]  # штраф 25 ₽ × 4 ч, страховка, питание
    assert c.chance == 90


def test_loan_insurance_refund(demo_cases):
    c = demo_cases["Страховки|Страховка по досрочно погашенному кредиту"]
    assert c.amount == 16000  # 24 000 ₽ × 16 / 24 мес.


def test_double_charge(demo_cases):
    assert demo_cases["Двойное списание|Двойное списание за одну покупку"].amount == 7990


def test_cooling_period_expires():
    csv = "дата;описание;сумма;категория;детали\n2026-01-01;Страхование «Защита»;1990;Страхование;срок 12 мес\n"
    txs = parse_csv(csv)
    assert detect(txs, today=date(2026, 1, 10))
    assert not detect(txs, today=date(2026, 1, 20))


def test_short_delay_has_no_insurance():
    csv = "дата;описание;сумма;категория;детали\n2026-05-01;Билет;5000;Авиабилеты;рейс AB123, 02.05.2026, задержка 2.5 ч\n"
    [c] = detect(parse_csv(csv))
    assert [p.sum for p in c.parts] == [50]
    assert c.chance == 75


def test_parse_errors():
    with pytest.raises(StatementError):
        parse_csv("только заголовок\n")
    with pytest.raises(StatementError):
        parse_csv("дата;описание;сумма\nвчера;что-то;много\n")


def test_comma_delimiter_and_ru_dates():
    txs = parse_csv("дата,описание,сумма,категория\n01.10.2026,Кофе,250,Кафе\n")
    assert txs[0].date == date(2026, 10, 1) and txs[0].amount == 250
