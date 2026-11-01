// Дашборд банка: показатели пилота, график возвратов, сценарии и рейтинг мерчантов.
import { api } from "./api.js";
import { COMMISSION, allCases, state } from "./client.js";
import { esc, rub, thousands } from "./format.js";

const $ = (id) => document.getElementById(id);
let data = null;

const millions = (thousandsValue) => (thousandsValue / 1000).toFixed(2).replace(".", ",") + " млн ₽";

function renderKpis(k) {
  const tiles = [
    ["Возвращено клиентам", millions(k.returned_thousands), `+${k.month_growth_pct}% к прошлому месяцу`],
    [`Комиссия банка, ${Math.round(data.commission_rate * 100)}%`, millions(k.commission_thousands), "без кредитного риска"],
    ["Успешных дел", `${k.success_rate_pct}%`, "цель пилота: больше 30%"],
    ["Среднее время до возврата", `${k.avg_days_to_return} дней`, `${thousands(k.cases_sent)} дел отправлено`],
  ];
  $("kpis").innerHTML = tiles.map(([label, value, note]) =>
    `<div class="kpi"><span>${esc(label)}</span><strong class="num">${esc(value)}</strong><small>${esc(note)}</small></div>`).join("");
}

function renderChart(months) {
  const W = 640, H = 260, L = 44, R = 8, T = 22, B = 30;
  const step = 600;
  const max = Math.ceil(Math.max(...months.map((m) => m.value)) / step) * step;
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const bw = (W - L - R) / months.length;
  const barW = Math.min(56, bw * 0.56);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Возвращено клиентам по месяцам: ${months.map((m) => `${m.month} ${m.value} тыс. ₽`).join(", ")}">`;
  ticks.forEach((t) => {
    s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"></line><text class="axis" x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${thousands(t)}</text>`;
  });
  months.forEach(({ month, value }, i) => {
    const cx = L + bw * i + bw / 2, top = y(value), base = y(0), r = 4;
    const x0 = cx - barW / 2, x1 = cx + barW / 2;
    const path = `M${x0},${base} L${x0},${top + r} Q${x0},${top} ${x0 + r},${top} L${x1 - r},${top} Q${x1},${top} ${x1},${top + r} L${x1},${base} Z`;
    const last = i === months.length - 1;
    s += `<g data-i="${i}"><rect class="hit" x="${L + bw * i}" y="${T}" width="${bw}" height="${H - T - B}"></rect><path class="bar${last ? " now" : ""}" d="${path}"></path>`;
    if (last || i === 0) s += `<text class="val" x="${cx}" y="${top - 6}" text-anchor="middle">${thousands(value)}</text>`;
    s += `<text class="axis" x="${cx}" y="${H - 10}" text-anchor="middle">${esc(month)}</text></g>`;
  });
  s += "</svg>";

  const box = $("chart"), tip = $("tip"), card = $("chart-card");
  box.innerHTML = s;
  box.querySelectorAll("g[data-i]").forEach((g) => {
    g.addEventListener("mouseenter", () => {
      const { month, value } = months[+g.dataset.i];
      const bar = g.querySelector(".bar").getBoundingClientRect(), c = card.getBoundingClientRect();
      tip.textContent = `${month} 2026: ${thousands(value)} тыс. ₽ · комиссия ${thousands(value * data.commission_rate)} тыс. ₽`;
      tip.style.left = `${bar.left + bar.width / 2 - c.left}px`;
      tip.style.top = `${bar.top - c.top}px`;
      tip.hidden = false;
    });
    g.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

function renderScenarios(list) {
  const max = Math.max(...list.map((x) => x.value));
  $("scen").innerHTML = list.map(({ name, value }) =>
    `<div class="hbar"><span>${esc(name)}</span><b>${thousands(value)}</b><div class="track"><div style="width:${(value / max * 100).toFixed(1)}%"></div></div></div>`).join("");
}

function renderMerchants(list) {
  $("merch").innerHTML = list.map((m, i) => `
    <tr><td class="rank">${i + 1}</td><td><b>${esc(m.name)}</b></td><td>${esc(m.issue)}</td>
    <td class="n">${thousands(m.cases)}</td>
    <td class="n">${m.success_pct}%<span class="mini" aria-hidden="true"><i style="width:${m.success_pct}%"></i></span></td>
    <td class="n">${m.response_days}</td><td class="n">${thousands(m.returned_thousands)} тыс. ₽</td></tr>`).join("");
}

function renderLive() {
  const sent = allCases().filter((c) => state.sent[c.id]);
  const sum = sent.reduce((s, c) => s + c.amount, 0);
  $("live-note").textContent = sent.length
    ? `Из клиентской части отправлено претензий: ${sent.length} на ${rub(sum)}. Комиссия банка при успехе: ${rub(sum * COMMISSION)}.`
    : "В клиентской части пока не отправлено ни одной претензии. Отправьте одну, и она появится здесь.";
}

const CLASS_LABELS = {
  dup: "Двойное списание", sub: "Подписка после пробного", imposed: "Навязанная услуга",
  flight: "Задержка рейса", loanins: "Страховка по кредиту", cool: "Период охлаждения",
};
const pct = (x) => `${Math.round(x * 100)}%`;
const dec = (x) => x.toFixed(2).replace(".", ",");

async function renderMl() {
  let info;
  try {
    info = await api.mlInfo();
  } catch (e) {
    $("ml-note").textContent = `Метрики недоступны: ${e.message}`;
    return;
  }
  const { scanner, scorer } = info.metrics;
  $("ml-note").textContent = `Обучены на синтетических данных: ${thousands(scanner.train_transactions)} операций и ${thousands(scorer.train_cases)} исторических дел. Метрики на отложенной выборке. В пилоте модели переобучаются на исходах реальных дел.`;
  const tiles = [
    ["Сканер: точность", pct(scanner.precision), "доля верных находок"],
    ["Сканер: полнота", pct(scanner.recall), "доля найденных поводов"],
    ["Скоринг: ROC AUC", dec(scorer.auc), `экспертные веса: ${dec(scorer.auc_expert)}`],
    ["Скоринг: Brier", dec(scorer.brier), `экспертные веса: ${dec(scorer.brier_expert)}, меньше лучше`],
  ];
  $("ml-kpis").innerHTML = tiles.map(([label, value, note]) =>
    `<div class="kpi"><span>${esc(label)}</span><strong class="num">${esc(value)}</strong><small>${esc(note)}</small></div>`).join("");
  $("ml-classes").innerHTML = Object.entries(scanner.per_class).map(([k, m]) => `
    <tr><td><b>${esc(CLASS_LABELS[k] || k)}</b></td><td class="n">${pct(m.precision)}</td><td class="n">${pct(m.recall)}</td>
    <td class="n">${dec(m.f1)}</td><td class="n">${thousands(m.support)}</td></tr>`).join("");
}

export async function showDashboard() {
  renderLive();
  if (data) return;
  try {
    data = await api.dashboard();
  } catch (e) {
    $("kpis").innerHTML = `<p class="error">Не удалось загрузить дашборд: ${esc(e.message)}</p>`;
    return;
  }
  $("dash-period").textContent = data.period;
  renderKpis(data.kpis);
  renderChart(data.monthly);
  renderScenarios(data.scenarios);
  renderMerchants(data.merchants);
  renderMl();
}
