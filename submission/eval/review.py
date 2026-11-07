"""Build the human review pack: submission/eval/review/index.html + key_template.csv.

For each question: answer, status, confidence, evidence, notes, and the cited PDF page(s) rendered with the
cited text highlighted. Images are derived from the raw PDFs, so submission/eval/review/ is git-ignored.

    python -m submission.eval.review
"""

from __future__ import annotations

import csv
import html
from pathlib import Path

import pandas as pd
import pymupdf

try:  # notebook: submission/ is on sys.path; CLI from the repo root: package is submission.archive_qa
    from archive_qa import config
    from archive_qa.write import load_answers_json
except ImportError:
    from submission.archive_qa import config
    from submission.archive_qa.write import load_answers_json

EVAL_DIR = Path(__file__).resolve().parent
REVIEW_DIR = EVAL_DIR / "review"
KEY_TEMPLATE = EVAL_DIR / "key_template.csv"
MAX_PAGES_PER_QUESTION = 4


def highlight_terms(row: pd.Series) -> list[str]:
    """Strings to highlight for a cited record: its value, and a snippet of long remarks."""
    terms: list[str] = []
    v = row.get("value")
    if isinstance(v, str) and v.strip():
        if len(v) > 40:
            first = v.strip().splitlines()[0]
            terms += [first[:60], first[:30]]
        else:
            terms.append(v.strip())
    return terms


def render_page(pdf_path: Path, page_no: int, terms: list[str], out_png: Path, dpi: int = 80) -> bool:
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_no - 1]
        for t in terms:
            for quad in page.search_for(t, quads=True):
                page.add_highlight_annot(quad)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=dpi).save(out_png)
    return True


def build_review(records: pd.DataFrame, questions: pd.DataFrame, answers: list[dict] | None = None,
                 out_dir: Path = REVIEW_DIR, key_path: Path = KEY_TEMPLATE, with_images: bool = True) -> Path:
    answers = answers if answers is not None else load_answers_json()
    qtext = dict(zip(questions["question_id"], questions["question_text"]))
    idx = records.set_index("record_id", drop=False)
    out_dir.mkdir(parents=True, exist_ok=True)

    queue = [a for a in answers if (not a["early_abstain"]) and (not a["verified"] or a["confidence"] < 0.6 or a.get("disagree"))]
    cards: list[str] = []
    for a in answers:
        qid = a["question_id"]
        imgs: list[str] = []
        if with_images:
            seen: set[tuple[str, int]] = set()
            for rid in a["cited_ids"]:
                if rid not in idx.index:
                    continue
                r = idx.loc[rid]
                if pd.isna(r["pdf_page"]) or (r["pdf_file"], int(r["pdf_page"])) in seen:
                    continue
                if len(seen) >= MAX_PAGES_PER_QUESTION:
                    break
                seen.add((r["pdf_file"], int(r["pdf_page"])))
                terms = [t for rid2 in a["cited_ids"] if rid2 in idx.index
                         and idx.loc[rid2]["pdf_file"] == r["pdf_file"] and idx.loc[rid2]["pdf_page"] == r["pdf_page"]
                         for t in highlight_terms(idx.loc[rid2])]
                png = out_dir / "img" / f"{qid}_{len(seen)}.png"
                render_page(config.PDF_DIR / r["pdf_file"], int(r["pdf_page"]), terms, png)
                imgs.append(f'<figure><img src="img/{png.name}" loading="lazy"><figcaption>{html.escape(r["pdf_file"])} '
                            f'p.{int(r["pdf_page"])}</figcaption></figure>')
        flag = " review" if a in queue else ""
        cards.append(
            f'<section class="card{flag}" id="{qid}"><h2>{qid} <span class="st {a["status"]}">{a["status"]}</span> '
            f'<span class="cf">confidence {a["confidence"]:.2f}</span></h2>'
            f'<p class="q">{html.escape(qtext.get(qid, ""))}</p>'
            f'<p><b>Answer:</b> {html.escape(a["answer"])}</p>'
            f'<p><b>Evidence:</b> {html.escape(a["evidence"])}</p>'
            f'<p class="notes"><b>Notes:</b> {html.escape(a["notes"])}</p>'
            f'<div class="imgs">{"".join(imgs)}</div></section>')
    toc = "".join(f'<li><a href="#{a["question_id"]}">{a["question_id"]}</a> {html.escape(a["status"])} '
                  f'{a["confidence"]:.2f}{" (REVIEW)" if a in queue else ""}</li>' for a in answers)
    page = f"""<!doctype html><meta charset="utf-8"><title>Track 2 review pack</title>
<style>body{{font:14px system-ui;margin:1rem auto;max-width:1100px;padding:0 1rem}}
.card{{border:1px solid #ccc;border-radius:8px;padding:.5rem 1rem;margin:1rem 0}}
.card.review{{border-color:#c0392b;background:#fff5f4}} .st{{font-size:12px;padding:2px 8px;border-radius:10px;background:#eee}}
.st.answered{{background:#d5f5e3}} .st.partial{{background:#fdebd0}} .st.abstain{{background:#d6eaf8}}
.cf{{font-size:12px;color:#555}} .q{{color:#444;font-style:italic}} .notes{{color:#666;font-size:12px}}
.imgs{{display:flex;gap:1rem;flex-wrap:wrap}} img{{max-width:100%;border:1px solid #999}} figure{{margin:0;max-width:520px}}</style>
<h1>Track 2 review pack</h1><p>{len(answers)} answers; {len(queue)} in the review queue (verifier failed, confidence &lt; 0.6, or the two runs disagree).
Fill <code>submission/eval/key.csv</code> (copy of key_template.csv) from the PDFs, then run
<code>python -m submission.eval.evaluate</code>.</p><ul>{toc}</ul>{"".join(cards)}"""
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")

    with key_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "question_text", "our_answer", "reviewer", "verdict", "notes"])
        for a in answers:
            w.writerow([a["question_id"], qtext.get(a["question_id"], ""), a["answer"], "", "", ""])
    return index


def main() -> None:
    try:
        from archive_qa import route, store
    except ImportError:
        from submission.archive_qa import route, store

    idx = build_review(store.get_store(), route.load_questions())
    print(f"Review pack: {idx}\nKey template: {KEY_TEMPLATE}")


if __name__ == "__main__":
    main()
