// Рисует иконку и заставку приложения в mobile/assets. Запуск: node scripts/icons.js assets (нужен playwright).
const { chromium } = require('playwright');
const path = require('path');
const out = process.argv[2];
// Логотип: розовая плашка с чернильной тенью и знак ₽ со стрелкой возврата.
const mark = (s) => `
<g transform="translate(${s/2} ${s/2}) rotate(-8)">
  <rect x="-${s*0.2}" y="-${s*0.2}" width="${s*0.4}" height="${s*0.4}" rx="${s*0.09}" fill="#3A1F4D" transform="translate(${s*0.022} ${s*0.022})"/>
  <rect x="-${s*0.2}" y="-${s*0.2}" width="${s*0.4}" height="${s*0.4}" rx="${s*0.09}" fill="#D6336C" stroke="#3A1F4D" stroke-width="${s*0.012}"/>
  <text x="0" y="${s*0.085}" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" font-weight="700" font-size="${s*0.25}" fill="#FFF4F8">₽</text>
</g>`;
const svg = (s, bg) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}">${bg ? `<rect width="${s}" height="${s}" fill="${bg}"/>` : ''}${mark(s)}</svg>`;
const bgOnly = (s, bg) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}"><rect width="${s}" height="${s}" fill="${bg}"/></svg>`;
const splash = (s, bg, ink) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}"><rect width="${s}" height="${s}" fill="${bg}"/>
  <g transform="translate(0 -${s*0.04})">${mark(s*0.5).replace('translate(', `translate(${s*0.25} ${s*0.25}) translate(`)}</g>
  <text x="${s/2}" y="${s*0.67}" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" font-weight="700" font-size="${s*0.045}" fill="${ink}">Рекуператор</text></svg>`;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  const shot = async (name, markup, s) => {
    await p.setViewportSize({ width: s, height: s });
    await p.setContent(`<html><body style="margin:0;background:transparent">${markup}</body></html>`);
    await p.screenshot({ path: path.join(out, name), omitBackground: true });
  };
  await shot('icon-only.png', `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"><rect width="1024" height="1024" fill="#FFC8DD"/><g transform="translate(-153.6 -153.6) scale(1.3)">${mark(1024)}</g></svg>`, 1024);
  // Адаптивная иконка: знак уменьшен, чтобы влезть в безопасную зону маски
  await shot('icon-foreground.png', `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"><g transform="translate(153.6 153.6) scale(0.7)">${mark(1024)}</g></svg>`, 1024);
  await shot('icon-background.png', bgOnly(1024, '#FFC8DD'), 1024);
  await shot('splash.png', splash(2732, '#FFF4F8', '#3A1F4D'), 2732);
  await shot('splash-dark.png', splash(2732, '#1E1228', '#FCE7F3'), 2732);
  await b.close();
})();
