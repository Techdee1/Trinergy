// Renders diagrams/*.svg to PNG with Playwright (from web/app/node_modules). Usage: node render_png.mjs
import { chromium } from '../../../web/app/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(here, '..', 'diagrams');
const b = await chromium.launch();
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.svg'))) {
  const svg = fs.readFileSync(path.join(dir, f), 'utf8');
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const w = +m[1], h = +m[2];
  const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  await p.goto(pathToFileURL(path.join(dir, f)).href);
  await p.screenshot({ path: path.join(dir, f.replace('.svg', '.png')) });
  await p.close();
  console.log('png', f);
}
await b.close();
