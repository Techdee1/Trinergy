"""Citation repair, in code only (no model call, no prompt change).

After an answer is final, each cited record is compared with the answer and rationale:

* A cited record that shares no DISTINCTIVE token with them is "weak" (e.g. a hatches-only activity row cited for a
  claim about skidding). It is dropped only if another cited record from the SAME report remains.
* For answered multi-report / archive-wide questions, up to two uncited records from the cited reports are added
  when they overlap the answer on at least two distinctive tokens and carry content the cited ones lack: either a
  distinctive answer token no cited record contains, or the citations include a weak record that they can stand in
  for. Candidates are ranked by rarity-weighted overlap.

A token is distinctive when it is rare in the context the model saw (document frequency <= ~8% of its records) and
is not a stop word. Nothing here knows about any particular question.
"""

from __future__ import annotations

import collections
import math
import re

import pandas as pd

from .context import _STOP, Context
from .match import GENERIC_WORDS, norm_text

_TOK = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*|\d+(?:\.\d+)?")
_FUNCTION = set("the and for with from are its then per has was were which that this into onto also than not but can may "
                "out all any their been being".split())
STOP = set(_STOP) | GENERIC_WORDS | _FUNCTION
MAX_ADDED = 2
MIN_OVERLAP = 2
DF_FRACTION = 0.08
DF_MIN = 4


def tokens(text: str) -> set[str]:
    return {t for t in _TOK.findall(norm_text(text)) if (len(t) >= 3 or "-" in t) and t not in STOP}


def repair_citations(cited: list[str], answer: str, rationale: str, ctx: Context, records: pd.DataFrame, *,
                     mode: str, status: str) -> tuple[list[str], list[str]]:
    """Returns (repaired cited record ids in a stable order, human-readable notes). ABSENT ids are not passed in."""
    real = [c for c in cited if c in ctx.bodies]
    if status not in ("answered", "partial") or not real:
        return list(cited), []
    n = len(ctx.bodies)
    body_tokens = {rid: tokens(b) for rid, b in ctx.bodies.items()}
    df = collections.Counter(t for ts in body_tokens.values() for t in ts)
    thr = max(DF_MIN, math.ceil(DF_FRACTION * n))
    wanted = tokens(f"{answer} {rationale}")
    overlap = {rid: {t for t in ts if df[t] <= thr} & wanted for rid, ts in body_tokens.items()}
    src = dict(zip(records["record_id"], records["source_file"]))

    # --- drop weak citations, but never the last one from a report
    notes: list[str] = []
    by_report: dict[str, list[str]] = collections.defaultdict(list)
    for rid in real:
        by_report[src.get(rid, "?")].append(rid)
    kept: list[str] = []
    dropped: list[str] = []
    for rid in real:
        group = by_report[src.get(rid, "?")]
        if not overlap[rid] and any(overlap[o] for o in group):
            dropped.append(rid)
        else:
            kept.append(rid)
    if dropped:
        notes.append(f"citation repair: dropped {dropped} (no distinctive overlap with the answer; another record from the "
                     "same report is cited)")

    # --- supplement (answered multi-report / archive-wide only)
    added: list[str] = []
    if status == "answered" and mode in ("multi_report", "archive_wide"):
        reports = {src.get(r) for r in kept}
        covered = set().union(*(body_tokens[r] for r in kept)) if kept else set()
        uncovered = {t for t in wanted if 0 < df[t] <= thr} - covered
        weak_left = [r for r in kept if not overlap[r]]
        if weak_left or uncovered:
            cands = [rid for rid in ctx.bodies if rid not in kept and src.get(rid) in reports
                     and len(overlap[rid]) >= MIN_OVERLAP and (weak_left or overlap[rid] & uncovered)]
            cands.sort(key=lambda rid: (-sum(math.log(n / df[t]) for t in overlap[rid]), rid))
            added = cands[:MAX_ADDED]
            if added:
                why = "stands in for a weakly supporting citation" if weak_left else "carries answer content no cited record has"
                notes.append(f"citation repair: added {added} (high overlap with the answer; {why})")
    absent = [c for c in cited if c not in ctx.bodies]
    return kept + added + absent, notes
