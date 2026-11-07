"""Build the deployment data pack (web/server/data/) from the organiser data and the submission's outputs.

    python -m web.server.build_data            # needs the raw organiser files; run once, commit the result

After this the server needs NO raw file: records, report list, page count, questions, unseen-set results, highlight boxes and
page images are all in the pack. Nothing in submission/ is written.

data/
  records.parquet               the evidence store (copy of submission/indexes/records.parquet, rebuilt if absent)
  reports.json                  one row per report: stem, well, date, pdf_file, pages
  catalog.json                  the 32 challenge questions and the 40 unseen ones (text only)
  generalisation.json           the /generalisation response (questions, answers, expected items, scores, baselines)
  generalisation_cache.json     the unseen set's model answers (read-only replay layer, same format as llm_cache.json)
  cost_summary.csv              copy of the committed per-question cost summary (when present)
  track_2/metadata/document_manifest.csv   the pipeline's early-abstain text reads the manifest through config.DATA_ROOT
  boxes.json                    record id -> page + highlight rectangles (or the XML-only reason)
  pages/<pdf>_p<N>.jpg          every PDF page, rendered once
  MANIFEST.json                 counts, sizes, checksums
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pymupdf

from submission.archive_qa import config, pipeline, store
from submission.archive_qa.route import discover_reports

from . import costs_view
from .highlight import HighlightBuilder, PageError
from .settings import REPO_ROOT

DATA_DIR = REPO_ROOT / "web" / "server" / "data"
GEN_DIR = config.SUBMISSION_DIR / "eval" / "generalisation"
ZOOM, JPG_QUALITY = 2.0, 80          # 2x = 1190 x 1684 px for A4: small table text stays legible; ~7 MB for all 54 pages


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(out: Path = DATA_DIR) -> dict:
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    if config.RECORDS_PATH.exists():
        shutil.copyfile(config.RECORDS_PATH, out / "records.parquet")
    else:
        store.build_store(out_path=out / "records.parquet", verbose=False)
    records = store.load_store(out / "records.parquet")
    reports = discover_reports(config.XML_DIR)

    # --- pages: every PDF page once
    page_counts: dict[str, int] = {}
    for r in reports:
        pdf = config.PDF_DIR / (r.stem + ".pdf")
        with pymupdf.open(pdf) as doc:
            page_counts[r.stem + ".pdf"] = doc.page_count
            for i, page in enumerate(doc, 1):
                page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), alpha=False).save(str(out / "pages" / f"{r.stem}_p{i}.jpg"), jpg_quality=JPG_QUALITY)
    (out / "reports.json").write_text(json.dumps([{"stem": r.stem, "well": r.well, "date": r.iso, "pdf_file": r.stem + ".pdf",
                                                    "pages": page_counts[r.stem + ".pdf"]} for r in reports], indent=1), encoding="utf-8")

    # --- highlight boxes for every record (or why there is no page)
    hb = HighlightBuilder(records, config.PDF_DIR)
    boxes: dict[str, dict] = {}
    for rid in records["record_id"]:
        try:
            boxes[rid] = hb.boxes(rid)
        except PageError as e:
            boxes[rid] = {"error": {"status": e.status, "code": e.code, "message": e.message, **e.extra}}
    (out / "boxes.json").write_text(json.dumps(boxes, separators=(",", ":")), encoding="utf-8")

    # --- questions
    ch = pipeline.read_questions()
    un = pipeline.read_questions(GEN_DIR / "questions.csv") if (GEN_DIR / "questions.csv").exists() else None
    catalog = {"challenge": [{"id": q.question_id, "question": q.question_text} for q in ch.itertuples(index=False)],
               "unseen": [{"id": q.question_id, "question": q.question_text} for q in un.itertuples(index=False)] if un is not None else []}
    (out / "catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- unseen set: static /generalisation response + the model answers needed to replay those questions
    gen = costs_view.generalisation(GEN_DIR)
    (out / "generalisation.json").write_text(json.dumps(gen, indent=1, ensure_ascii=False), encoding="utf-8")
    cache = json.loads((GEN_DIR / "runtime_cache.json").read_text(encoding="utf-8")) if (GEN_DIR / "runtime_cache.json").exists() else {"_meta": {}, "entries": {}}
    (out / "generalisation_cache.json").write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- ledger + manifest shim
    if config.COST_SUMMARY_PATH.exists():
        shutil.copyfile(config.COST_SUMMARY_PATH, out / "cost_summary.csv")
    (out / "track_2" / "metadata").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config.DATA_ROOT / "metadata" / "document_manifest.csv", out / "track_2" / "metadata" / "document_manifest.csv")

    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "MANIFEST.json")
    manifest = {"built": date.today().isoformat(), "attribution": "Data: Equinor Volve dataset", "records": len(records), "reports": len(reports),
                "pages": sum(page_counts.values()), "page_zoom": ZOOM, "jpg_quality": JPG_QUALITY,
                "boxes": len(boxes), "boxes_with_page": sum("error" not in b for b in boxes.values()),
                "total_bytes": sum(p.stat().st_size for p in files), "pages_bytes": sum(p.stat().st_size for p in (out / "pages").glob("*.jpg")),
                "sha256": {p.relative_to(out).as_posix(): _sha(p) for p in files if p.suffix != ".jpg"}}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = build()
    print(json.dumps({k: v for k, v in m.items() if k != "sha256"}, indent=1))
    sys.exit(0)
