// Офлайн-движок для Android-приложения: разбор CSV-выписки, правила и шаблон претензии.
// Это порт backend/app/statement.py, rules.py и claims.py. Логику меняйте в обоих местах:
// тест backend/tests/test_offline_js.py сверяет результаты на демо-выписках.
import { rub } from "./format.js";

export class StatementError extends Error {}

const TRAVEL_PAYOUT = 3000;
const COOLING_DAYS = 14;
const DAY = 86400000;

const toTime = (iso) => Date.parse(`${iso}T00:00:00Z`);
const daysBetween = (a, b) => Math.round((toTime(b) - toTime(a)) / DAY);
const addDays = (iso, n) => new Date(toTime(iso) + n * DAY).toISOString().slice(0, 10);
const fmt = (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };
const pad = (n) => String(n).padStart(2, "0");
const norm = (s) => s.toLowerCase().replace(/[«»"']/g, "").replace(/\s+/g, " ").trim();
const round2 = (n) => Math.round(n * 100) / 100;
const termMonths = (details, def = 12) => { const m = /срок\s*(\d+)/i.exec(details); return m ? +m[1] : def; };
// Строка числа как в Python str(float): 5.0 -> "5.0", 4.3 -> "4.3"
const pyFloat = (n) => (Number.isInteger(n) ? `${n}.0` : String(n));

function parseDate(raw) {
  raw = raw.trim();
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(raw);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return null;
}

export function parseCsv(text) {
  const lines = text.replace(/^﻿/, "").split(/\r\n|\r|\n/).filter((l) => l.trim());
  if (lines.length < 2) throw new StatementError("В файле нет строк с операциями.");
  const delim = lines[0].includes(";") ? ";" : ",";
  const result = [];
  lines.slice(1).forEach((line, i) => {
    const cells = line.split(delim);
    const d = parseDate(cells[0] || "");
    const rawAmount = (cells[2] || "").replace(/ /g, "").replace(/,/g, ".").trim();
    const amount = rawAmount === "" ? NaN : Number(rawAmount);
    if (Number.isNaN(amount) || d === null) return;
    result.push({
      id: `t${i}`, date: d, desc: (cells[1] || "").trim(), amount,
      cat: (cells[3] || "").trim(), details: cells.slice(4).join(delim).trim(),
    });
  });
  if (!result.length) throw new StatementError("Не удалось прочитать операции. Проверьте формат: дата;описание;сумма;категория;детали.");
  return result.sort((a, b) => toTime(a.date) - toTime(b.date));
}

function makeCase(c) {
  return { ...c, ai: false, amount: round2(c.parts.reduce((s, p) => s + p.sum, 0)) };
}

function flightDelays(txs) {
  const found = [];
  for (const t of txs) {
    if (!/авиа/i.test(t.cat) || t.amount <= 0) continue;
    const dm = /задержк\S*\s*([\d.,]+)/i.exec(t.details);
    if (!dm) continue;
    const hours = Number(dm[1].replace(",", "."));
    if (Number.isNaN(hours) || hours < 2) continue;
    const fdm = /(\d{2})\.(\d{2})\.(\d{4})/.exec(t.details);
    const fdate = fdm ? `${fdm[3]}-${pad(fdm[2])}-${pad(fdm[1])}` : null;
    const fm = /рейс\s*([A-ZА-Я0-9]{2}\s?\d{2,4})/i.exec(t.details);
    const flight = fm ? fm[1] : "";

    const fullHours = Math.floor(hours);
    const parts = [{ label: `Штраф перевозчика: 25 ₽ × ${fullHours} ч`, sum: Math.min(25 * fullHours, t.amount * 0.5) }];
    const basis = ["ст. 120 Воздушного кодекса РФ: 25 ₽ за каждый час задержки, не более 50% стоимости перевозки"];
    const evidence = [t.id];
    if (hours >= 4) {
      parts.push({ label: "Выплата по страховке «Путешествия» к карте (задержка от 4 ч)", sum: TRAVEL_PAYOUT });
      basis.push("Условия страховой программы к карте: задержка рейса от 4 часов");
    }
    if (fdate) {
      for (const x of txs) {
        if (x.amount > 0 && x.date === fdate && /кафе|ресторан|питан/i.test(x.cat) && /аэропорт/i.test(`${x.desc} ${x.details}`)) {
          parts.push({ label: "Расходы на питание в аэропорту во время задержки", sum: x.amount });
          evidence.push(x.id);
        }
      }
      if (evidence.length > 1) basis.push("п. 99 ФАП-82: при задержке более 4 ч перевозчик обязан обеспечить горячее питание; расходы подлежат возмещению как убытки");
    }
    found.push(makeCase({
      id: `flight-${t.id}`, kind: "Рейсы",
      title: `Задержка рейса на ${pyFloat(hours).replace(".", ",")} ч`,
      sub: (flight ? `${flight} · ` : "") + fmt(fdate || t.date),
      parts, basis, evidence, chance: hours >= 4 ? 90 : 75,
      to: "Авиаперевозчик и страховая компания по программе к карте",
      deadline: "Перевозчик отвечает на претензию в течение 30 дней (ст. 124 ВК РФ).",
    }));
  }
  return found;
}

function trialSubscriptions(txs, today) {
  const groups = new Map();
  for (const t of txs) {
    if (!/подписк/i.test(t.cat) || t.amount <= 0) continue;
    const k = norm(t.desc);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(t);
  }
  const found = [];
  for (const arr of groups.values()) {
    arr.sort((a, b) => toTime(a.date) - toTime(b.date));
    const trial = arr.find((t) => t.amount <= 10);
    if (!trial) continue;
    const paid = arr.filter((t) => t.amount > 10 && t.date > trial.date);
    if (!paid.length) continue;
    const last = paid[paid.length - 1];
    const used = Math.min(30, Math.max(0, daysBetween(last.date, today)));
    const refund = Math.round(last.amount * (30 - used) / 30);
    if (refund <= 0) continue;
    found.push(makeCase({
      id: `sub-${last.id}`, kind: "Подписки", title: "Пробный период стал платной подпиской",
      sub: `${last.desc} · ${paid.length} платн. списания`,
      parts: [{ label: `Возврат за неиспользованные ${30 - used} дн. текущего периода`, sum: refund }],
      basis: ["ст. 32 Закона о защите прав потребителей: отказ от услуги в любой момент с оплатой только фактически оказанного",
        "ст. 16 ЗоЗПП: недопустимы условия, ущемляющие права потребителя"],
      evidence: [trial.id, ...paid.map((p) => p.id)], chance: 60,
      to: "Сервис подписки",
      deadline: "Требование о возврате удовлетворяется в течение 10 дней (ст. 31 ЗоЗПП).",
    }));
  }
  return found;
}

function doubleCharges(txs) {
  const groups = new Map();
  for (const t of txs) {
    if (t.amount <= 0 || /подписк|кредит/i.test(t.cat)) continue;
    const k = JSON.stringify([t.date, norm(t.desc), t.amount]);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(t);
  }
  const found = [];
  for (const g of groups.values()) {
    if (g.length < 2) continue;
    found.push(makeCase({
      id: `dup-${g[0].id}`, kind: "Двойное списание", title: "Двойное списание за одну покупку",
      sub: `${g[0].desc} · ${fmt(g[0].date)}`,
      parts: [{ label: `Повторное списание × ${g.length - 1}`, sum: g[0].amount * (g.length - 1) }],
      basis: ["ст. 1102 ГК РФ: возврат неосновательного обогащения",
        "Оспаривание операции через банк по правилам платёжной системы"],
      evidence: g.map((x) => x.id), chance: 95,
      to: "Продавец; параллельно банк открывает спор по операции",
      deadline: "Оспаривание через банк обычно занимает до 30 дней.",
    }));
  }
  return found;
}

function insurance(txs, today) {
  const policies = txs.filter((t) => t.amount > 0 && /страх/i.test(`${t.cat} ${t.desc}`));
  const early = txs.filter((t) => /досрочн/i.test(`${t.desc} ${t.details}`));
  const found = [], usedIds = new Set();

  for (const t of policies) {
    if (!/кредит/i.test(`${t.desc} ${t.details}`)) continue;
    const e = early.find((x) => x.date > t.date);
    if (!e) continue;
    const term = termMonths(t.details);
    const monthsUsed = Math.max(1, Math.ceil(daysBetween(t.date, e.date) / 30.44));
    const left = Math.max(0, term - monthsUsed);
    const refund = Math.round(t.amount * left / term);
    if (refund <= 0) continue;
    usedIds.add(t.id);
    found.push(makeCase({
      id: `loanins-${t.id}`, kind: "Страховки", title: "Страховка по досрочно погашенному кредиту",
      sub: `Кредит погашен ${fmt(e.date)}`,
      parts: [{ label: `Часть премии за ${left} из ${term} мес.`, sum: refund }],
      basis: ["ч. 10 и 12 ст. 11 Закона № 353-ФЗ «О потребительском кредите»: при досрочном погашении возвращается часть премии пропорционально неистёкшему сроку",
        "Срок возврата: 7 рабочих дней с даты заявления"],
      evidence: [t.id, e.id], chance: 85,
      to: "Страховая компания (при её отказе — кредитор, ч. 12 ст. 11 353-ФЗ)",
      deadline: "Страховщик возвращает деньги в течение 7 рабочих дней.",
    }));
  }

  for (const t of policies) {
    if (usedIds.has(t.id)) continue;
    const days = daysBetween(t.date, today);
    if (days > COOLING_DAYS) continue;
    const term = termMonths(t.details);
    const refund = Math.round(t.amount * (1 - days / (term * 30.44)));
    found.push(makeCase({
      id: `cool-${t.id}`, kind: "Страховки", title: "Отказ от страховки в период охлаждения",
      sub: `${t.desc} · куплена ${days} дн. назад, осталось ${COOLING_DAYS - days} дн.`,
      parts: [{ label: days ? `Премия за вычетом ${days} дн. действия` : "Премия полностью", sum: refund }],
      basis: ["Указание Банка России № 3854-У: отказ от добровольного страхования в течение 14 календарных дней",
        "Возврат премии в течение 10 рабочих дней"],
      evidence: [t.id], chance: 92,
      to: "Страховая компания",
      deadline: `Заявление нужно подать до ${fmt(addDays(t.date, COOLING_DAYS))}.`,
    }));
  }
  return found;
}

const RULES = [flightDelays, trialSubscriptions, doubleCharges, insurance];

export function detect(txs, today = null) {
  if (!txs.length) return [];
  today = today || txs.reduce((m, t) => (t.date > m ? t.date : m), txs[0].date);
  const cases = RULES.flatMap((rule) => rule(txs, today));
  return cases.sort((a, b) => b.amount - a.amount);
}

export function analyze(text, source) {
  const transactions = parseCsv(text);
  return { source, transactions, cases: detect(transactions) };
}

export function templateClaim(c, evidence) {
  const ev = evidence.map((t) => `– ${fmt(t.date)}: ${t.desc}, ${rub(t.amount)}` + (t.details ? ` (${t.details})` : "")).join("\n");
  const basis = c.basis.map((b) => `– ${b}`).join("\n");
  const parts = c.parts.map((p) => `– ${p.label}: ${rub(p.sum)}`).join("\n");
  return `Кому: ${c.to}
От: [ФИО], паспорт [серия, номер], адрес: [адрес], телефон: [телефон]

ПРЕТЕНЗИЯ

${c.title}.

Обстоятельства:
${ev}

Правовые основания:
${basis}

Требование: выплатить ${rub(c.amount)}:
${parts}

Денежные средства прошу перечислить на счёт: [реквизиты счёта].
${c.deadline}
В случае отказа оставляю за собой право обратиться в суд и в Роспотребнадзор.

Приложения: выписка по операциям, подтверждение оплаты.

[дата]                                   [подпись]`;
}
