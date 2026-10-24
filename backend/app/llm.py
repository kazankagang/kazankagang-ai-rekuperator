"""Обращения к Claude API: генерация претензии и дополнительный поиск случаев.

Ключ берётся из окружения (ANTHROPIC_API_KEY или профиль `ant auth login`).
Без ключа сервис работает: претензия собирается по шаблону, а доп. проверка ИИ отключена.
"""
import json
import os
import re

import anthropic

from .models import CaseOut, ClaimPart, Transaction

MODEL = os.getenv("REKUPERATOR_MODEL", "claude-opus-5-5")

_client: anthropic.Anthropic | None = None


def ai_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _ask(prompt: str, max_tokens: int = 8000) -> str:
    """Один запрос к модели. Возвращает текст ответа; при отказе модели бросает RuntimeError."""
    response = _get_client().beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Модель отказалась отвечать на этот запрос.")
    return "".join(b.text for b in response.content if b.type == "text").strip()


def _tx_lines(txs: list[Transaction]) -> str:
    return "\n".join(f"{t.id}; {t.date:%d.%m.%Y}; {t.desc}; {t.amount:g}; {t.cat}; {t.details}" for t in txs)


def claim_prompt(case: CaseOut, evidence: list[Transaction]) -> str:
    parts = "\n".join(f"- {p.label}: {round(p.sum)} ₽" for p in case.parts)
    basis = "\n".join(f"- {b}" for b in case.basis)
    return f"""Ты юрист по защите прав потребителей в России. Напиши претензию от имени клиента банка.

Ситуация: {case.title}. {case.sub}.
Адресат: {case.to}.
Операции из выписки (id; дата; описание; сумма; категория; детали):
{_tx_lines(evidence) or "нет"}
Расчёт требования:
{parts}
Итого: {round(case.amount)} ₽.
Правовые основания:
{basis}
Срок ответа: {case.deadline or "по закону"}

Требования к тексту:
- официальный деловой стиль, русский язык, 200–350 слов;
- шапка «Кому / От кого», заголовок ПРЕТЕНЗИЯ, обстоятельства, правовые основания со ссылками на статьи, чёткое требование с суммой и сроком, предупреждение об обращении в суд и Роспотребнадзор, перечень приложений, место для даты и подписи;
- личные данные не выдумывай: ставь заглушки [ФИО], [паспорт], [адрес], [телефон], [реквизиты счёта], [название организации];
- ссылайся только на нормы из списка выше, суммы не меняй;
- только текст претензии, без пояснений и без Markdown-разметки."""


def generate_claim(case: CaseOut, evidence: list[Transaction]) -> str:
    return _ask(claim_prompt(case, evidence))


def scan_statement(txs: list[Transaction], known: list[CaseOut]) -> list[CaseOut]:
    """Просит модель найти поводы для возврата, которые не поймали правила."""
    known_text = "; ".join(f"{c.title} — {c.sub}" for c in known) or "нет"
    prompt = f"""Ты аналитик сервиса, который ищет в банковской выписке клиента из России случаи, когда ему положен возврат денег или компенсация (ЗоЗПП, ГК РФ, Воздушный кодекс, ФАП-82, 353-ФЗ, Указание ЦБ 3854-У, гарантия, переплаты).

Правила уже нашли такие случаи (их не повторяй): {known_text}.

Выписка (id; дата; описание; сумма, плюс = списание, минус = поступление; категория; детали):
{_tx_lines(txs[-200:])}

Найди до 3 дополнительных правдоподобных поводов для возврата, которые следуют из этих операций. Не выдумывай факты, которых нет в выписке. Если поводов нет, верни пустой массив.
Ответь только JSON-массивом объектов без пояснений:
[{{"title": "короткое название", "reason": "почему положен возврат, 1-2 предложения", "amount": 0, "basis": "норма закона или условие", "to": "кому направить", "tx_ids": ["t1"]}}]
amount — оценка суммы в рублях числом, 0 если оценить нельзя."""
    text = _ask(prompt)
    m = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(m[0] if m else text)
    except json.JSONDecodeError as e:
        raise RuntimeError("ИИ ответил в неверном формате.") from e

    ids = {t.id for t in txs}
    cases = []
    for i, x in enumerate(items[:3] if isinstance(items, list) else []):
        if not isinstance(x, dict) or not x.get("title"):
            continue
        try:
            amount = max(0.0, float(x.get("amount") or 0))
        except (TypeError, ValueError):
            amount = 0.0
        cases.append(CaseOut(
            id=f"ai-{i}", ai=True, kind="ИИ-находка", title=str(x["title"]),
            sub=str(x.get("reason", "")), parts=[ClaimPart(label="Оценка ИИ", sum=amount)],
            basis=[str(x.get("basis") or "Требует проверки юристом")],
            evidence=[str(t) for t in x.get("tx_ids", []) if str(t) in ids],
            to=str(x.get("to") or "[адресат]"),
            deadline="Случай найден ИИ: проверьте основания перед отправкой.",
            amount=amount,
        ))
    return cases
