"""Builds build/flow.html from pages_a.py and pages_b.py. Then: node render_pdf.mjs flow.html ../Flow_and_Architecture.pdf"""
from pathlib import Path
import pages_a, pages_b

HERE = Path(__file__).resolve().parent
NM = HERE.parents[2] / "web/app/node_modules/@fontsource-variable"
css = (HERE / "style.css").read_text()
css = css.replace("FONT_INTER", (NM / "inter/files/inter-latin-wght-normal.woff2").as_uri()).replace("FONT_MONO", (NM / "jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2").as_uri())
dia = (HERE.parent / "diagrams").as_uri()
pages = pages_a.PAGES + pages_b.PAGES
body = ""
for i, p in enumerate(pages, 1):
    body += p.replace("__PG__", f"{i} / {len(pages)}").replace("DIA", dia)
(HERE / "flow.html").write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Intelligent Well Archive: flow and architecture</title><style>{css}</style></head><body>{body}</body></html>', encoding="utf-8")
print(len(pages), "pages")
