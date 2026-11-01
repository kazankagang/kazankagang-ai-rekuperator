"""Шаблон претензии на случай, когда ИИ недоступен."""
from .models import CaseOut, Transaction


def rub(n: float) -> str:
    return f"{round(n):,}".replace(",", " ") + " ₽"


def template_claim(case: CaseOut, evidence: list[Transaction]) -> str:
    ev = "\n".join(
        f"– {t.date:%d.%m.%Y}: {t.desc}, {rub(t.amount)}" + (f" ({t.details})" if t.details else "")
        for t in evidence
    )
    basis = "\n".join(f"– {b}" for b in case.basis)
    parts = "\n".join(f"– {p.label}: {rub(p.sum)}" for p in case.parts)
    return f"""Кому: {case.to}
От: [ФИО], паспорт [серия, номер], адрес: [адрес], телефон: [телефон]

ПРЕТЕНЗИЯ

{case.title}.

Обстоятельства:
{ev}

Правовые основания:
{basis}

Требование: выплатить {rub(case.amount)}:
{parts}

Денежные средства прошу перечислить на счёт: [реквизиты счёта].
{case.deadline}
В случае отказа оставляю за собой право обратиться в суд и в Роспотребнадзор.

Приложения: выписка по операциям, подтверждение оплаты.

[дата]                                   [подпись]"""
