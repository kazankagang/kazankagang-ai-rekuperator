"""Разбор банковской выписки в CSV.

Формат: дата;описание;сумма;категория;детали. Разделитель «;» или «,».
Дата в виде 2026-10-01 или 01.10.2026. Списание положительное, поступление отрицательное.
"""
import re
from datetime import date

from .models import Transaction


class StatementError(ValueError):
    pass


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})", raw)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    return None


def parse_csv(text: str) -> list[Transaction]:
    lines = [line for line in text.lstrip("﻿").splitlines() if line.strip()]
    if len(lines) < 2:
        raise StatementError("В файле нет строк с операциями.")
    delim = ";" if ";" in lines[0] else ","
    result: list[Transaction] = []
    for i, line in enumerate(lines[1:]):
        cells = line.split(delim)
        d = parse_date(cells[0] if cells else "")
        try:
            amount = float((cells[2] if len(cells) > 2 else "").replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        if d is None:
            continue
        result.append(Transaction(
            id=f"t{i}",
            date=d,
            desc=(cells[1] if len(cells) > 1 else "").strip(),
            amount=amount,
            cat=(cells[3] if len(cells) > 3 else "").strip(),
            details=delim.join(cells[4:]).strip(),
        ))
    if not result:
        raise StatementError("Не удалось прочитать операции. Проверьте формат: дата;описание;сумма;категория;детали.")
    return sorted(result, key=lambda t: t.date)
