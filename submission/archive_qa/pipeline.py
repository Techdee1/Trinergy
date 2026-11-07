"""Question-file handling and output safety for the notebook: any question set, one set of rules.

* QUESTIONS_CSV  None = the organiser's published questions (the committed cache covers them).
* OUTPUT_PATH    None = submission/predictions.csv for the published questions, and a NEW file next to it
                 (predictions_<questions-file-stem>.csv) for any other question file. The committed
                 predictions.csv is replaced by a different run only if OUTPUT_PATH names it explicitly.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from . import config
from .answer import NOT_EVALUATED_NO_KEY, Answer

ID_COLUMNS = ("question_id", "id", "qid", "question_no")
TEXT_COLUMNS = ("question_text", "question", "text", "prompt", "query")


def detect_columns(columns: list[str]) -> tuple[str, str]:
    """(id column, question column) by case-insensitive name; raises ValueError listing what was found."""
    low = {str(c).strip().lower(): c for c in columns}
    qid = next((low[n] for n in ID_COLUMNS if n in low), None)
    txt = next((low[n] for n in TEXT_COLUMNS if n in low), None)
    if qid is None or txt is None:
        raise ValueError(f"Cannot find the question id / question text columns. Columns present: {list(columns)}. "
                         f"Expected an id column ({', '.join(ID_COLUMNS)}) and a text column ({', '.join(TEXT_COLUMNS)}), "
                         f"in any letter case.")
    return qid, txt


def read_questions(path: str | Path | None = None) -> pd.DataFrame:
    """Questions as a frame with columns question_id and question_text (other columns dropped), file order kept."""
    path = Path(path) if path else config.QUESTIONS_CSV
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    qid, txt = detect_columns(list(df.columns))
    out = pd.DataFrame({"question_id": df[qid].str.strip(), "question_text": df[txt]})
    out = out[(out["question_id"] != "") & (out["question_text"].str.strip() != "")].reset_index(drop=True)
    dup = sorted(out.loc[out["question_id"].duplicated(), "question_id"].unique())
    if dup:
        raise ValueError(f"Duplicate question ids in {path.name}: {dup[:5]}")
    return out


def is_default_questions(questions_csv: str | Path | None) -> bool:
    if questions_csv is None:
        return True
    try:
        return Path(questions_csv).resolve() == Path(config.QUESTIONS_CSV).resolve()
    except FileNotFoundError:
        return False


def resolve_output(questions_csv: str | Path | None = None, output_path: str | Path | None = None) -> Path:
    if output_path:
        return Path(output_path)
    if is_default_questions(questions_csv):
        return config.PREDICTIONS_PATH
    return config.SUBMISSION_DIR / f"predictions_{Path(questions_csv).stem}.csv"


def not_evaluated_summary(answers: list[Answer]) -> str:
    """One clear paragraph at the end of a run: what could not be answered and why. Empty when everything was."""
    ne = [a for a in answers if a.status == "not_evaluated"]
    if not ne:
        return ""
    no_key = [a.question_id for a in ne if a.answer == NOT_EVALUATED_NO_KEY]
    other = [a.question_id for a in ne if a.answer != NOT_EVALUATED_NO_KEY]
    lines = [f"{len(ne)} of {len(answers)} question(s) were NOT EVALUATED and carry no answer or evidence (confidence 0)."]
    if no_key:
        lines.append(f"  {len(no_key)} have no cached answer and no API key was found: {', '.join(no_key[:10])}"
                     f"{' ...' if len(no_key) > 10 else ''}. Set OPENROUTER_KEY (or put it in .env) and rerun to answer them.")
    if other:
        lines.append(f"  {len(other)} failed during the model call (see the warnings above): {', '.join(other[:10])}.")
    return "\n".join(lines)


def read_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
