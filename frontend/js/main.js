// Точка входа: переключение экранов «Главная», «Клиент», «Банк».
import { initClient } from "./client.js";
import { showDashboard } from "./dashboard.js";

const $ = (id) => document.getElementById(id);

const BAND_TEXT = {
  client: "Загрузите выписку по карте. Сервис найдёт операции, по которым вам положен возврат или компенсация, и подготовит претензию.",
  bank: "Что банк видит в пилоте: сколько денег вернули клиентам, сколько заработал на комиссии и какие мерчанты нарушают чаще всего.",
};

function showView(view) {
  const home = view === "home";
  document.body.classList.toggle("home", home);
  $("view-home").hidden = !home;
  document.querySelector("header.band").hidden = home;
  document.querySelector("main").hidden = home;
  document.querySelector("footer").hidden = home;
  window.scrollTo(0, 0);
  if (home) return;

  const bank = view === "bank";
  $("view-client").hidden = bank;
  $("view-bank").hidden = !bank;
  $("client-totals").hidden = bank;
  $("tab-home").setAttribute("aria-selected", "false");
  $("tab-client").setAttribute("aria-selected", String(!bank));
  $("tab-bank").setAttribute("aria-selected", String(bank));
  $("band-text").textContent = BAND_TEXT[view];
  if (bank) showDashboard();
}

$("tab-home").addEventListener("click", () => showView("home"));
$("tab-client").addEventListener("click", () => showView("client"));
$("tab-bank").addEventListener("click", () => showView("bank"));
document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.go)));

const initial = { "#client": "client", "#bank": "bank" }[location.hash] || "home";
showView(initial);
initClient();
