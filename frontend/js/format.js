// Форматирование чисел, дат и безопасная вставка текста в HTML.

export const rub = (n) => Math.round(n).toLocaleString("ru-RU").replace(/[\s,]/g, " ") + " ₽";

export const thousands = (n) => Math.round(n).toLocaleString("ru-RU").replace(/[\s,]/g, " ");

// "2026-10-01" -> "01.10.2026"
export const fmtDate = (iso) => {
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
};

export const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export const pluralCases = (n) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "случай";
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return "случая";
  return "случаев";
};
