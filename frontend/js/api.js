// Клиент HTTP API бэкенда.
//
// В браузере API живёт на том же адресе, что и страница. В Android-приложении
// (Capacitor) адрес сервера задаёт пользователь, а без сервера приложение
// работает офлайн: демо-выписка и дашборд берутся из data/offline.json, а свою
// выписку разбирает офлайн-движок offline.js прямо на телефоне.
import * as engine from "./offline.js";

const SERVER_KEY = "rekuperator.server";

function savedServer() {
  try { return localStorage.getItem(SERVER_KEY) || ""; } catch { return ""; }
}

const native = Boolean(globalThis.Capacitor?.isNativePlatform?.());

export const conn = {
  native,
  base: native ? savedServer() : "",
  offline: native,  // в приложении офлайн, пока сервер не ответил на /api/health
};

const NEED_SERVER = "Доп. проверка ИИ работает только с сервером. Нажмите «Сервер» и укажите адрес бэкенда.";

export function setServer(url) {
  const clean = url.trim().replace(/\/+$/, "");
  const base = clean && !/^https?:\/\//i.test(clean) ? `http://${clean}` : clean;
  try {
    if (base) localStorage.setItem(SERVER_KEY, base);
    else localStorage.removeItem(SERVER_KEY);
  } catch { /* хранилище недоступно */ }
  conn.base = base;
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(conn.base + path, options);
  } catch {
    throw new Error(conn.base ? `Сервер ${conn.base} не отвечает.` : "Сервер не отвечает.");
  }
  let body = null;
  try { body = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : `Ошибка сервера (${res.status})`;
    throw new Error(detail);
  }
  return body;
}

let offlineData = null;
async function offline() {
  if (!offlineData) offlineData = await (await fetch("data/offline.json")).json();
  return offlineData;
}

// Запрос к серверу или, в офлайн-режиме, ответ из встроенных данных.
async function call(path, options, fromOffline) {
  if (!conn.offline) return request(path, options);
  if (!fromOffline) throw new Error(NEED_SERVER);
  return fromOffline(await offline());
}

// Как на сервере: UTF-8, а если не читается, то Windows-1251 (выгрузки из Excel).
async function readText(file) {
  const buf = await file.arrayBuffer();
  try { return new TextDecoder("utf-8", { fatal: true }).decode(buf); } catch { return new TextDecoder("windows-1251").decode(buf); }
}

const jsonBody = (data) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

export const api = {
  health: async () => {
    if (native && !conn.base) return { status: "offline", ai_enabled: false };
    const res = await request("/api/health", { signal: AbortSignal.timeout(5000) });
    conn.offline = false;
    return res;
  },
  demo: () => call("/api/demo", {}, (d) => d.demo),
  analyze: (file) => {
    if (conn.offline) return readText(file).then((text) => engine.analyze(text, file.name || "upload.csv"));
    const form = new FormData();
    form.append("file", file);
    return request("/api/analyze", { method: "POST", body: form });
  },
  claim: (caseData, transactions) => {
    if (conn.offline) {
      return Promise.resolve({ text: engine.templateClaim(caseData, transactions), source: "template",
        note: "Офлайн-режим: претензия собрана по шаблону." });
    }
    return request("/api/claim", jsonBody({ case: caseData, transactions }));
  },
  aiScan: (transactions, cases) => call("/api/ai-scan", jsonBody({ transactions, cases })),
  dashboard: () => call("/api/dashboard", {}, (d) => d.dashboard),
};
