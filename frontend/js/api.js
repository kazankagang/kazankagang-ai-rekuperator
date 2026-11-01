// Клиент HTTP API бэкенда.

async function request(path, options = {}) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : `Ошибка сервера (${res.status})`;
    throw new Error(detail);
  }
  return body;
}

const postJson = (path, data) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

export const api = {
  health: () => request("/api/health"),
  demo: () => request("/api/demo"),
  analyze: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/analyze", { method: "POST", body: form });
  },
  claim: (caseData, transactions) => postJson("/api/claim", { case: caseData, transactions }),
  aiScan: (transactions, cases) => postJson("/api/ai-scan", { transactions, cases }),
  dashboard: () => request("/api/dashboard"),
};
