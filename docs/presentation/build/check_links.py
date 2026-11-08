"""Checks the documentation: every relative markdown link resolves, every file path named in backticks exists, no em or en dashes,
no secrets. Run from anywhere: python docs/presentation/build/check_links.py"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = [ROOT / "submission/docs/REVIEWER_GUIDE.md", ROOT / "submission/docs/ARCHITECTURE.md", ROOT / "docs/presentation/Demo_Script.md",
        ROOT / "docs/presentation/TODO_URLS.md", ROOT / "docs/presentation/QA_Drill.md"]
README = ROOT / "submission/README.md"
problems = []
EXT = r"(?:md|py|csv|json|ipynb|yml|yaml|txt|svg|png|pdf|mjs|ts|tsx|css|example|parquet)"
SKIP = ("metadata/document_manifest.csv", "predictions_demo_questions.csv", "predictions_<", "<", "*", "TODO-URL", "http", "~", "/tmp", "$")
for doc in DOCS + [README]:
    text = doc.read_text(encoding="utf-8")
    if doc == README:
        text = "\n".join(text.splitlines()[:3])             # only the link block was added to the README
    for m in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        t = m.group(1)
        if t.startswith(("http", "mailto:")):
            continue
        if not (doc.parent / t).resolve().exists():
            problems.append(f"{doc.relative_to(ROOT)}: broken link {t}")
    if doc == README:
        continue
    for m in re.finditer(r"`([^`\s]+)`", text):
        t = m.group(1).rstrip(".,;:)")
        if "/" not in t or any(s in t for s in SKIP) or not re.search(rf"\.{EXT}$|/$", t):
            continue
        cands = [ROOT / t, doc.parent / t, ROOT / "submission" / t, ROOT / "submission/archive_qa" / t, ROOT / "web/server" / t, ROOT / "web/app" / t]
        if not any(c.exists() for c in cands):
            problems.append(f"{doc.relative_to(ROOT)}: path not found `{t}`")
    for ch in ("—", "–"):
        if ch in text:
            problems.append(f"{doc.relative_to(ROOT)}: contains a dash character U+{ord(ch):04X}")
    if re.search(r"sk-or-[A-Za-z0-9]|Bearer [A-Za-z0-9]{12,}", text):
        problems.append(f"{doc.relative_to(ROOT)}: looks like a secret")
for f in (ROOT / "docs/presentation/build").glob("*.py"):
    pass
print("\n".join(problems) if problems else "docs check: all links and paths resolve; no dash characters; no secrets")
sys.exit(1 if problems else 0)
