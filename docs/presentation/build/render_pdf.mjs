// Usage: node render_pdf.mjs <html> <pdf> [w h]. Prints overflow warnings per slide.
import { chromium } from '../../../web/app/node_modules/playwright/index.mjs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const [html, pdf, w = '1280', h = '720'] = process.argv.slice(2);
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: +w, height: +h } });
await p.goto(pathToFileURL(path.resolve(here, html)).href);
await p.evaluate(() => document.fonts.ready);
await p.evaluate(({ max }) => {
  document.querySelectorAll('.slide').forEach(s => {
    const inn = s.querySelector('.in'); if (!inn) return;
    const src = s.querySelector('.src');
    const limit = (src ? src.getBoundingClientRect().top : s.getBoundingClientRect().bottom) - 14 - s.getBoundingClientRect().top;
    let lo = 1, hi = max;
    for (let k = 0; k < 14; k++) {
      const mid = (lo + hi) / 2; inn.style.zoom = mid;
      const bottom = inn.getBoundingClientRect().bottom - s.getBoundingClientRect().top;
      if (bottom <= limit) lo = mid; else hi = mid;
    }
    inn.style.zoom = lo;
    s.dataset.zoom = lo.toFixed(2);
  });
}, { max: 1.3 });
const issues = await p.evaluate(({ h }) => {
  const out = [];
  document.querySelectorAll('.slide').forEach((s, i) => {
    const sb = s.getBoundingClientRect();
    const src = s.querySelector('.src');
    const limit = src ? src.getBoundingClientRect().top : sb.bottom - 10;
    s.querySelectorAll('h1,h2,h3,p,li,table,pre,.card,.step,img,.big,.lab').forEach(e => {
      if (e.closest('.src')) return;
      const r = e.getBoundingClientRect();
      if (r.bottom > limit + 1 && r.height > 0) out.push(`slide ${i + 1}: <${e.tagName.toLowerCase()}> bottom ${Math.round(r.bottom - sb.top)} passes source line ${Math.round(limit - sb.top)}: "${(e.textContent || '').trim().slice(0, 50)}"`);
      if (r.right > sb.right - 20) out.push(`slide ${i + 1}: <${e.tagName.toLowerCase()}> right edge ${Math.round(r.right - sb.left)}`);
    });
    s.querySelectorAll('.card,.step,pre').forEach(e => { if (e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2) out.push(`slide ${i + 1}: box clipped "${(e.textContent || '').trim().slice(0, 40)}"`); });
  });
  return [...new Set(out)];
}, { h: +h });
console.log(issues.length ? issues.join('\n') : 'no overflow found');
await p.pdf({ path: path.resolve(here, pdf), width: `${w}px`, height: `${h}px`, printBackground: true });
await b.close();
