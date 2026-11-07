"""Projected prediction score from the human-filled key.

    python -m submission.eval.evaluate [path/to/key.csv]

verdicts: correct = 1, correct-abstention = 1, partial = 0.5, wrong = 0. Score = points / 32 x 40.
The key is read here only; nothing in archive_qa reads it.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

POINTS = {"correct": 1.0, "correct-abstention": 1.0, "partial": 0.5, "wrong": 0.0}
N_QUESTIONS = 32
WEIGHT = 40


def evaluate(path: Path) -> dict:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    verdicts = [(r.get("verdict") or "").strip().lower() for r in rows]
    bad = sorted({v for v in verdicts if v and v not in POINTS})
    if bad:
        raise ValueError(f"Unknown verdict(s) {bad}; use one of {sorted(POINTS)}")
    counts = Counter(v for v in verdicts if v)
    points = sum(POINTS[v] * n for v, n in counts.items())
    graded = sum(counts.values())
    return {"counts": dict(counts), "graded": graded, "ungraded": len(rows) - graded, "rows": len(rows),
            "points": points, "projected_score": points / N_QUESTIONS * WEIGHT}


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path(__file__).resolve().parent / "key.csv"
    r = evaluate(path)
    for v in POINTS:
        print(f"  {v:20s} {r['counts'].get(v, 0)}")
    print(f"graded {r['graded']}/{r['rows']} (ungraded {r['ungraded']}); points {r['points']:.1f}/{N_QUESTIONS}")
    print(f"projected prediction score: {r['projected_score']:.1f} / {WEIGHT}"
          + ("  (PARTIAL: some answers still ungraded)" if r["ungraded"] else ""))


if __name__ == "__main__":
    main()
