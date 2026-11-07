"""Write predictions.csv (template order) and answers.json, then run the organiser's validator.

Evidence strings are built ONLY from records that exist in the store, so a citation can never be invented:
    "<pdf_file> p.<page> (<pdf_section>); <xml_file> <record_id>"       (XML only when no PDF page is known)
ABSENT-* pseudo-records are cited as what was searched; early abstentions list what was checked.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pandas as pd

from . import config
from .answer import Answer

COLUMNS = ["question_id", "answer", "evidence", "confidence", "notes"]


def record_evidence(row: pd.Series) -> str:
    xml = f"{row['source_file']} {row['record_id']}"
    page = row.get("pdf_page")
    if pd.notna(page) and isinstance(row.get("pdf_file"), str):
        sec = row.get("pdf_section")
        sec = f" ({sec})" if isinstance(sec, str) and sec else ""
        return f"{row['pdf_file']} p.{int(page)}{sec}; {xml}"
    return xml


def absent_evidence(rid: str, meta: dict) -> str:
    files = [f + ".xml" for f in meta["files"]]
    shown = ", ".join(files[:3]) + (f" (+{len(files) - 3} more)" if len(files) > 3 else "")
    return (f"{rid}: searched {meta['reports']} report(s), {meta['records']} record(s) [{shown}]; "
            f"no {meta['kind']} field exists")


def build_evidence(ans: Answer, records: pd.DataFrame) -> str:
    if ans.early_abstain:
        return ans.evidence_extra
    parts: list[str] = []
    valid = [c for c in ans.cited_ids if c in set(records["record_id"])]  # unknown IDs are dropped, never cited
    rows = records[records["record_id"].isin(valid)].sort_values(["well", "report_date", "record_id"])
    parts += [record_evidence(r) for _, r in rows.iterrows()]
    parts += [absent_evidence(rid, meta) for rid, meta in sorted(ans.absent.items())]
    if not parts:  # abstention with nothing to cite: say what was searched
        files = [c + ".xml" for c in ans.candidates]
        parts.append(f"Searched {len(files)} routed report(s) ({', '.join(files[:4])}"
                     f"{'...' if len(files) > 4 else ''}); no record matches the question")
    return "; ".join(dict.fromkeys(parts))


def answer_notes(ans: Answer) -> str:
    bits = [f"status={ans.status}", f"mode={ans.mode}"] + [n for n in ans.notes if not n.startswith("model=")]
    if ans.rationale and not ans.early_abstain:
        bits.append("rationale: " + ans.rationale)
    return " | ".join(bits)


def template_order() -> list[str]:
    """Question order from the organiser's template (falls back to the questions file)."""
    for base in (config.DATA_ROOT.parent.parent,):
        t = base / "submission" / "template" / "outputs" / "track2_predictions_template.csv"
        if t.is_file():
            with t.open(encoding="utf-8-sig", newline="") as f:
                return [r["question_id"] for r in csv.DictReader(f)]
    with config.QUESTIONS_CSV.open(encoding="utf-8-sig", newline="") as f:
        return [r["question_id"] for r in csv.DictReader(f)]


def write_predictions(answers: list[Answer], records: pd.DataFrame, path: Path | None = None,
                      order: list[str] | None = None, allow_partial: bool = False) -> Path:
    """Write the CSV. All 32 questions are required unless allow_partial (smoke runs write only what ran)."""
    path = Path(path or config.PREDICTIONS_PATH)
    order = order or template_order()
    by_id = {a.question_id: a for a in answers}
    missing = [q for q in order if q not in by_id]
    if missing and not allow_partial:
        raise ValueError(f"No answer for {len(missing)} question(s): {missing[:5]}...")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for qid in order:
            a = by_id.get(qid)
            if a is None:
                continue
            w.writerow({"question_id": qid, "answer": a.answer, "evidence": build_evidence(a, records),
                        "confidence": f"{a.confidence:.2f}", "notes": answer_notes(a)})
    return path


def save_answers_json(answers: list[Answer], records: pd.DataFrame, path: Path | None = None) -> Path:
    """Structured answers (cited IDs, status, verifier result) for the review pack and for audit."""
    path = Path(path or config.ANSWERS_PATH)
    out = []
    for a in sorted(answers, key=lambda x: x.question_id):
        out.append({
            "question_id": a.question_id, "status": a.status, "answer": a.answer, "cited_ids": a.cited_ids,
            "confidence": a.confidence, "mode": a.mode, "candidates": a.candidates, "verified": a.verified,
            "failures": a.failures, "early_abstain": a.early_abstain, "rationale": a.rationale,
            "evidence": build_evidence(a, records), "notes": answer_notes(a), "absent": a.absent,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def load_answers_json(path: Path | None = None) -> list[dict]:
    return json.loads(Path(path or config.ANSWERS_PATH).read_text(encoding="utf-8"))


def find_validator() -> Path | None:
    cand = config.DATA_ROOT.parent.parent / "submission" / "validate_submission.py"
    return cand if cand.is_file() else None


def run_validator(submission_dir: Path | None = None) -> dict | None:
    """Run the organiser's validate_submission() on the submission folder. None if it is not on disk."""
    vp = find_validator()
    if vp is None:
        return None
    spec = importlib.util.spec_from_file_location("organiser_validate_submission", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate_submission(Path(submission_dir or config.SUBMISSION_DIR), 2, config.DATA_ROOT)
