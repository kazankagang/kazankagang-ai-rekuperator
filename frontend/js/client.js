// Клиентская часть: выписка, найденные случаи, претензия и согласие.
import { api, conn, setServer } from "./api.js";
import { esc, fmtDate, pluralCases, rub } from "./format.js";

export const COMMISSION = 0.2;

export const state = {
  txs: [],
  cases: [],
  aiCases: [],
  selected: null,
  claims: {},   // id случая -> { text, source, note }
  sent: {},     // id случая -> true
  aiEnabled: false,
};

const $ = (id) => document.getElementById(id);

export const allCases = () => [...state.cases, ...state.aiCases];
const txById = (id) => state.txs.find((t) => t.id === id);

function showError(msg) {
  const el = $("src-error");
  el.textContent = msg;
  el.hidden = !msg;
  if (msg) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderTotals() {
  const sum = state.cases.reduce((s, c) => s + c.amount, 0);
  const n = state.cases.length;
  $("t-total").textContent = rub(sum);
  $("t-net").textContent = rub(sum * (1 - COMMISSION));
  $("t-count").textContent = n
    ? `${n} ${pluralCases(n)} по правилам` + (state.aiCases.length ? ` + ${state.aiCases.length} от ИИ` : "")
    : "случаев не найдено";
}

function chanceChip(c) {
  if (c.ai) return '<span class="chip ai">Найдено ИИ · проверить</span>';
  return `<span class="chip ${c.chance >= 80 ? "good" : "warn"}">Шанс ${c.chance}%</span>`;
}

function renderCases() {
  const box = $("cases");
  const list = allCases();
  if (!list.length) {
    box.innerHTML = '<div class="empty">В этой выписке правила не нашли поводов для возврата. Попробуйте «Доп. проверку ИИ» или загрузите выписку за другой период.</div>';
    return;
  }
  box.innerHTML = list.map((c) => `
    <button type="button" class="case" data-id="${esc(c.id)}" aria-pressed="${state.selected === c.id}">
      <div class="case-top">
        <div><div class="case-title">${esc(c.title)}</div><div class="case-sub">${esc(c.sub)}</div></div>
        <div class="case-sum num">${c.amount ? rub(c.amount) : "—"}</div>
      </div>
      <div class="chips"><span class="chip cat">${esc(c.kind)}</span>${chanceChip(c)}${state.sent[c.id] ? '<span class="chip good">Отправлено</span>' : ""}</div>
    </button>`).join("");
  box.querySelectorAll(".case").forEach((b) => b.addEventListener("click", () => select(b.dataset.id)));
}

function renderTx() {
  const hits = new Set(allCases().flatMap((c) => c.evidence || []));
  $("tx-body").innerHTML = state.txs.map((t) => `
    <tr class="${hits.has(t.id) ? "hit" : ""}">
      <td class="num">${fmtDate(t.date)}</td><td>${esc(t.desc)}</td><td>${esc(t.cat)}</td><td>${esc(t.details)}</td>
      <td class="amt ${t.amount < 0 ? "in" : ""}">${t.amount < 0 ? "+" + rub(-t.amount) : "−" + rub(t.amount)}</td>
    </tr>`).join("");
  $("st-meta").textContent = `${state.txs.length} операций · подсвечены операции, по которым найден случай`;
}

function renderPanel() {
  const p = $("panel");
  const c = allCases().find((x) => x.id === state.selected);
  if (!c) {
    p.innerHTML = '<div class="panel-head"><h2>Выберите случай</h2><p class="status">Слева список того, что можно вернуть. Откройте случай, чтобы увидеть расчёт, основания и претензию.</p></div>';
    return;
  }
  const ev = (c.evidence || []).map(txById).filter(Boolean);
  const fee = c.amount * COMMISSION;
  const claim = state.claims[c.id];
  p.innerHTML = `
    <div class="panel-head">
      <div class="chips"><span class="chip cat">${esc(c.kind)}</span>${chanceChip(c)}</div>
      <h2>${esc(c.title)}</h2>
      <span class="status">${esc(c.sub)}</span>
    </div>
    <div class="split">
      <div class="block">
        <h3>Расчёт</h3>
        <table class="sumtable num">
          ${c.parts.map((x) => `<tr><td>${esc(x.label)}</td><td>${rub(x.sum)}</td></tr>`).join("")}
          ${c.amount ? `<tr class="fee"><td>Комиссия сервиса 20%, только при успехе</td><td>− ${rub(fee)}</td></tr>
          <tr class="total-row"><td>Вам на счёт</td><td>${rub(c.amount - fee)}</td></tr>` : ""}
        </table>
      </div>
      <div class="block">
        <h3>Правовые основания</h3>
        <ul class="basis">${c.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
        ${c.ai ? "" : `<h3 style="margin-top:6px">Вероятность успеха</h3><div class="meter" role="img" aria-label="Вероятность успеха ${c.chance}%"><div style="width:${c.chance}%"></div></div>`}
      </div>
    </div>
    ${ev.length ? `<div class="block"><h3>Операции из выписки</h3><div class="evidence">${ev.map((t) => `<div class="ev"><span>${fmtDate(t.date)} · ${esc(t.desc)}</span><span class="num">${rub(t.amount)}</span></div>`).join("")}</div></div>` : ""}
    <div class="block">
      <h3>Претензия · кому: ${esc(c.to)}</h3>
      <div class="claim-box ${claim ? "" : "placeholder"}" id="claim">${claim ? esc(claim.text) : (state.aiEnabled ? "Нажмите «Сгенерировать претензию»: ИИ напишет текст по данным операции и нормам выше." : "Нажмите «Сгенерировать претензию». ИИ на сервере не подключён, поэтому текст соберётся по шаблону.")}</div>
      <div class="claim-actions">
        <button class="btn primary" id="btn-gen" type="button">${claim ? "Сгенерировать заново" : "Сгенерировать претензию"}</button>
        <button class="btn" id="btn-copy" type="button" ${claim ? "" : "disabled"}>Скопировать</button>
        <span class="status" id="claim-status">${claim && claim.note ? esc(claim.note) : ""}</span>
      </div>
      <p class="status">${esc(c.deadline || "")}</p>
    </div>
    <div class="block">
      ${state.sent[c.id] ? `<div class="sent">Заявка принята в работу. В пилоте здесь появится статус дела: отправка, ответ, зачисление.</div>` : `
      <label class="consent"><input type="checkbox" id="consent"> <span>Даю согласие на отправку претензии от моего имени по электронной доверенности. Комиссия 20% удерживается только после поступления денег.</span></label>
      <div><button class="btn primary" id="btn-send" type="button" disabled>Подписать и отправить</button></div>`}
    </div>`;

  $("btn-gen").addEventListener("click", () => generateClaim(c));
  $("btn-copy").addEventListener("click", copyClaim);
  const consent = $("consent");
  if (consent) {
    const send = $("btn-send");
    consent.addEventListener("change", () => { send.disabled = !consent.checked || !state.claims[c.id]; });
    send.addEventListener("click", () => { state.sent[c.id] = true; renderCases(); renderPanel(); });
    if (!claim) $("claim-status").textContent = "Сначала подготовьте претензию, затем подтвердите отправку.";
  }
}

function select(id) {
  state.selected = id;
  renderCases();
  renderPanel();
  if (window.matchMedia("(max-width: 860px)").matches) $("panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generateClaim(c) {
  const btn = $("btn-gen");
  btn.disabled = true;
  $("claim").classList.remove("placeholder");
  $("claim").textContent = state.aiEnabled ? "ИИ пишет претензию…" : "Собираю претензию…";
  $("claim-status").textContent = "";
  try {
    const evidence = state.txs.filter((t) => (c.evidence || []).includes(t.id));
    state.claims[c.id] = await api.claim(c, evidence);
  } catch (e) {
    if (state.selected === c.id) { $("claim").textContent = ""; $("claim-status").textContent = e.message; btn.disabled = false; }
    return;
  }
  if (state.selected === c.id) renderPanel();
}

async function copyClaim() {
  const claim = state.claims[state.selected];
  if (!claim) return;
  try {
    await navigator.clipboard.writeText(claim.text);
    $("claim-status").textContent = "Скопировано.";
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("claim"));
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    $("claim-status").textContent = "Текст выделен, скопируйте его вручную.";
  }
}

async function aiScan() {
  const btn = $("btn-ai");
  const label = btn.lastChild.textContent;
  showError("");
  btn.disabled = true;
  btn.lastChild.textContent = " ИИ анализирует выписку…";
  try {
    const res = await api.aiScan(state.txs, state.cases);
    state.aiCases = res.cases.map((c) => ({ ...c, id: `${c.id}-${Date.now()}` }));
    if (!state.aiCases.length) showError("ИИ не нашёл дополнительных поводов в этой выписке.");
    renderAll();
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.lastChild.textContent = label;
  }
}

function renderAll() { renderTotals(); renderCases(); renderPanel(); renderTx(); }

function applyResult(res, name, meta) {
  state.txs = res.transactions;
  state.cases = res.cases;
  state.aiCases = [];
  state.claims = {};
  state.sent = {};
  state.selected = state.cases[0] ? state.cases[0].id : null;
  $("src-name").textContent = name;
  const first = state.txs[0], last = state.txs[state.txs.length - 1];
  $("src-meta").textContent = `${meta} · ${state.txs.length} операций, ${fmtDate(first.date)} – ${fmtDate(last.date)}`;
  showError("");
  renderAll();
}

async function loadDemo() {
  try {
    applyResult(await api.demo(), "Демо-выписка клиента", "Пример данных, не реальный клиент");
  } catch (e) {
    showError(`Не удалось загрузить демо: ${e.message}`);
  }
}

// Android-приложение: выбор адреса бэкенда и пометка офлайн-режима.
function initServer(serverError) {
  const btn = $("btn-server");
  btn.hidden = false;
  btn.addEventListener("click", () => {
    const url = window.prompt("Адрес сервера Рекуператора, например http://192.168.1.10:8000. Пусто: офлайн-демо.", conn.base);
    if (url === null) return;
    setServer(url);
    location.reload();
  });
  const note = $("conn-note");
  if (conn.offline) {
    note.textContent = (serverError ? `${serverError} ` : "") +
      "Офлайн-режим: выписка разбирается прямо на телефоне, претензии собираются по шаблону. Чтобы включить ИИ, нажмите «Сервер».";
  } else {
    note.textContent = `Подключено к серверу ${conn.base}.`;
  }
  note.hidden = false;
}

export async function initClient() {
  $("file").addEventListener("change", async (ev) => {
    const f = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!f) return;
    try {
      applyResult(await api.analyze(f), f.name, "Ваш файл");
    } catch (e) {
      showError(e.message);
    }
  });
  // В Android-приложении фильтр по типу прячет CSV, которые пришли из мессенджеров без MIME-типа.
  if (conn.native) $("file").removeAttribute("accept");
  $("btn-demo").addEventListener("click", loadDemo);
  $("btn-ai").addEventListener("click", aiScan);

  let serverError = "";
  try {
    const health = await api.health();
    state.aiEnabled = health.ai_enabled;
  } catch (e) { state.aiEnabled = false; serverError = e.message; }
  if (!state.aiEnabled) $("btn-ai").title = "Задайте ANTHROPIC_API_KEY на сервере, чтобы включить ИИ";
  if (conn.native) initServer(serverError);

  await loadDemo();
}
