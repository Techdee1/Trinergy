"""Write predictions.csv (template order) and answers.json, then run the organiser's validator.

Evidence strings are built ONLY from records that exist in the store, so a citation can never be invented:
    "<pdf_file> p.<page> (<pdf_section>); <xml_file> <record_id>"       (XML only when no PDF page is known)
ABSENT-* pseudo-records are cited as what was searched; early abstentions list what was checked.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
from pathlib import Path

import pandas as pd

from . import config
from .answer import Answer
from .xmlonly import xml_only_evidence, xml_only_paths

COLUMNS = ["question_id", "answer", "evidence", "confidence", "notes"]


def record_evidence(row: pd.Series) -> str:
    xml = f"{row['source_file']} {row['record_id']}"
    page = row.get("pdf_page")
    if pd.notna(page) and isinstance(row.get("pdf_file"), str):
        sec = row.get("pdf_section")
        sec = f" ({sec})" if isinstance(sec, str) and sec else ""
        return f"{row['pdf_file']} p.{int(page)}{sec}; {xml}"
    return xml


def _files_text(stems: list[str], limit: int = 3) -> list[str]:
    shown = stems[:limit]
    return shown + ([f"(+{len(stems) - limit} more report(s))"] if len(stems) > limit else [])


def absent_evidence(rid: str, meta: dict) -> list[str]:
    """What was searched for a field the archive does not have: the files, and anything considered and rejected."""
    kind = meta["kind"].replace("_", " ")
    out = [f"{f}.pdf: all sections checked, no {kind} field" if not f.startswith("(") else f
           for f in _files_text(meta["files"])]
    if meta.get("near"):
        out.append("considered and rejected: " + "; ".join(f"{n['what']} ({n['reason']})" for n in meta["near"]))
    return out


def build_evidence(ans: Answer, records: pd.DataFrame) -> str:
    """Citations built only from records in the store. Per report: its PDF page references first (one per file+page,
    sections merged), then its XML record ids. Abstentions name the files searched."""
    if ans.status == "not_evaluated":
        return ""                                      # nothing was checked: no evidence is claimed
    if ans.early_abstain:
        return ans.evidence_extra
    known = set(records["record_id"])
    valid = [c for c in ans.cited_ids if c in known]                 # unknown IDs are dropped, never cited
    rows = records[records["record_id"].isin(valid)].sort_values(["well", "report_date", "record_id"])
    parts: list[str] = []
    for _, grp in rows.groupby("source_file", sort=False):
        pages: dict[tuple[str, int], list[str]] = {}
        xml_refs: list[str] = []
        only: list[str] = []
        for _, r in grp.iterrows():
            xo = xml_only_paths(r, ans.question, ans.answer)
            if xo:                                   # the value is not printed in the PDF: cite the XML, no page
                only += xml_only_evidence(r, xo)
                continue
            xml_refs.append(f"{r['source_file']} {r['record_id']}")
            if pd.notna(r.get("pdf_page")) and isinstance(r.get("pdf_file"), str):
                secs = pages.setdefault((r["pdf_file"], int(r["pdf_page"])), [])
                if isinstance(r.get("pdf_section"), str) and r["pdf_section"] and r["pdf_section"] not in secs:
                    secs.append(r["pdf_section"])
        parts += [f"{f} p.{pg}" + (f" ({', '.join(secs)})" if secs else "") for (f, pg), secs in pages.items()]
        parts += xml_refs + only
    for rid, meta in sorted(ans.absent.items()):
        parts += absent_evidence(rid, meta)
    if not parts:  # abstention with nothing to cite: say what was searched
        parts += [f"{c}.pdf: all sections checked, no matching record" for c in ans.candidates[:3]]
        if len(ans.candidates) > 3:
            parts.append(f"(+{len(ans.candidates) - 3} more report(s))")
    return "; ".join(dict.fromkeys(parts))


def prediction_note(ans: Answer) -> str:
    """The `notes` cell of predictions.csv: the short rationale only. Internal flags (retries, escalation, disagreement,
    verifier text) stay in answers.json and the review pack."""
    text = ans.rationale or ""
    text = re.sub(r"^EARLY ABSTAIN:\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


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
                        "confidence": f"{a.confidence:.2f}", "notes": prediction_note(a)})
    return path


def save_answers_json(answers: list[Answer], records: pd.DataFrame, path: Path | None = None) -> Path:
    """Structured answers (cited IDs, status, verifier result) for the review pack and for audit."""
    path = Path(path or config.ANSWERS_PATH)
    out = []
    for a in sorted(answers, key=lambda x: x.question_id):
        out.append({
            "question_id": a.question_id, "status": a.status, "answer": a.answer, "cited_ids": a.cited_ids,
            "confidence": a.confidence, "mode": a.mode, "candidates": a.candidates, "verified": a.verified,
            "failures": a.failures, "early_abstain": a.early_abstain, "rationale": a.rationale, "disagree": a.disagree,
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


def check_format(path: Path | None = None, expected_ids: list[str] | None = None) -> dict:
    """Minimal built-in check of predictions.csv, mirroring the organiser's rules: required columns, no duplicate or unknown
    question ids, every expected id present, confidence blank or within [0, 1]. Used only when the organiser's
    validate_submission.py is not on disk; it does NOT replace it."""
    path = Path(path or config.PREDICTIONS_PATH)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return {"valid": False, "errors": ["predictions.csv not found"], "warnings": [], "rows": 0}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols, rows = list(reader.fieldnames or []), list(reader)
    required = ("question_id", "answer", "evidence", "confidence")
    errors += [f"missing column {c}" for c in required if c not in cols]
    extra = [c for c in cols if c not in required + ("notes",)]
    if extra:
        warnings.append("unexpected columns (ignored in scoring): " + ", ".join(extra))
    ids = [(r.get("question_id") or "").strip() for r in rows]
    errors += [f"duplicate question_id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    expected = expected_ids if expected_ids is not None else template_order()
    errors += [f"unknown question_id {i}" for i in ids if i and i not in expected]
    missing = [i for i in expected if i not in ids]
    if missing:
        warnings.append(f"{len(missing)} of {len(expected)} questions have no row; they will score zero")
    for n, r in enumerate(rows, 2):
        c = (r.get("confidence") or "").strip()
        if c:
            try:
                if not 0 <= float(c) <= 1:
                    errors.append(f"line {n}: confidence must be between 0 and 1")
            except ValueError:
                errors.append(f"line {n}: invalid confidence")
    if not rows:
        errors.append("no data rows")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "rows": len(rows)}


def validate_predictions(submission_dir: Path | None = None, predictions_path: Path | None = None,
                         expected_ids: list[str] | None = None) -> dict:
    """Validate a predictions file and say which validator ran. Returns {"validator","valid","errors","warnings","rows"}.

    * Default run (the organiser's 32 questions, submission/predictions.csv): the organiser's validate_submission(),
      or the built-in check when that script is not on disk.
    * Any other question set or output path: the organiser's validate_csv() for columns and values (its id check is
      against the PUBLISHED questions, so it is skipped) plus an id check against this run's own question ids.
    """
    custom = (predictions_path is not None and Path(predictions_path).resolve() != config.PREDICTIONS_PATH.resolve()) \
        or expected_ids is not None
    if not custom:
        rep = run_validator(submission_dir)
        if rep is not None:
            return {"validator": "organiser validate_submission.py", "valid": rep["valid"],
                    "errors": rep["structure"]["errors"] + rep["csv"]["errors"], "warnings": rep["csv"]["warnings"],
                    "rows": rep["csv"]["rows"]}
        c = check_format(Path(submission_dir) / "predictions.csv" if submission_dir else None)
        return {"validator": "built-in format check (the organiser's validate_submission.py was not found next to the data)", **c}
    path = Path(predictions_path or config.PREDICTIONS_PATH)
    own = check_format(path, expected_ids)
    mod = _load_organiser()
    if mod is None:
        return {"validator": "built-in format check (the organiser's validate_submission.py was not found next to the data)", **own}
    theirs = mod.validate_csv(path, 2, None)
    errors = list(dict.fromkeys(theirs["errors"] + own["errors"]))
    warnings = list(dict.fromkeys(theirs["warnings"] + own["warnings"]))
    return {"validator": "organiser validate_csv (columns and values) + id check against this run's question file",
            "valid": not errors, "errors": errors, "warnings": warnings, "rows": own["rows"]}


def _load_organiser():
    """The organiser's validate_submission module, or None if it is not on disk."""
    try:
        vp = find_validator()
    except FileNotFoundError:
        return None
    if vp is None:
        return None
    spec = importlib.util.spec_from_file_location("organiser_validate_submission", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_validator(submission_dir: Path | None = None) -> dict | None:
    """Run the organiser's validate_submission() on the submission folder. None if it is not on disk."""
    mod = _load_organiser()
    if mod is None:
        return None
    return mod.validate_submission(Path(submission_dir or config.SUBMISSION_DIR), 2, config.DATA_ROOT)
