"""Text normalisation and question-token matching shared by the context builder and the verifier.

Used to find the records that match the distinctive tokens of a question ("50%", "formation", ...) regardless of
how the archive happens to write them: case, whitespace, "50 %" vs "50%", "2586 m" vs "2586m", "0,05" vs "0.05".
Nothing here knows about any particular question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .wells import find_wells

_UNITS = r"(?:%|mmd|mtvd|m/h|m|bar|psi|ppm|rpm|lpm|sg|g/cm3|kn|knm|ton|tonne|hrs?)"
_SPACE_BEFORE_UNIT = re.compile(rf"(\d)\s+({_UNITS})(?![a-z0-9])")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d{1,2}(?!\d))")
_NUM_UNIT = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNITS}|\")(?![a-z0-9])")
_TEMPORAL = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?|(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])")
_WORD = re.compile(r"[a-z][a-z-]{3,}")

# words that carry no information about WHAT is asked (question scaffolding, archive vocabulary)
GENERIC_WORDS = set("""what which when where who whom whose how many much were was does did there their across during between
from with that this these those have been being into onto than then also only each every both after before while
report reports dated date dates days daily well wells archive drilling depth depths record records sidetrack
sidetracks following listed state states stated give list name""".split())


def norm_text(s: str) -> str:
    """Lowercase, collapse whitespace, "50 %" -> "50%", "2586 m" -> "2586m", decimal comma "0,05" -> "0.05"."""
    s = re.sub(r"\s+", " ", (s or "").lower())
    s = _DECIMAL_COMMA.sub(".", s)
    return _SPACE_BEFORE_UNIT.sub(r"\1\2", s)


def _stem(w: str) -> str:
    if w.endswith("ies") and len(w) > 5:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 4:
        return w[:-1]
    return w


@dataclass(frozen=True)
class QTokens:
    num_units: frozenset[str]   # numbers with a unit, normalised: "50%", "36\"", "2586m"
    words: frozenset[str]       # content-word stems

    def __bool__(self) -> bool:
        return bool(self.num_units or self.words)


def question_tokens(question: str) -> QTokens:
    """The distinctive tokens of a question: numbers with units, and content words. Dates, times and well names
    are removed first (they select reports, not records)."""
    text = question or ""
    spans = [(m.start, m.end) for m in find_wells(text)]
    for m in _TEMPORAL.finditer(text):
        spans.append((m.start(), m.end()))
    keep, last = [], 0
    for a, b in sorted(spans):
        keep.append(text[last:a])
        last = max(last, b)
    keep.append(text[last:])
    clean = norm_text(" ".join(keep))
    nums = frozenset(f"{n}{u}" for n, u in _NUM_UNIT.findall(clean))
    words = frozenset(_stem(w) for w in _WORD.findall(_NUM_UNIT.sub(" ", clean)) if w not in GENERIC_WORDS)
    return QTokens(nums, words)


def match_score(body: str, qt: QTokens) -> int:
    """0 = no match. With a numeric-unit token in the question a record must contain it AND a content word;
    without one it must contain at least two content words."""
    b = norm_text(body)
    num_hits = sum(1 for t in qt.num_units if t in b)
    word_hits = sum(1 for w in qt.words if w in b)
    if qt.num_units:
        return 2 * num_hits + word_hits if (num_hits and word_hits) else 0
    return word_hits if word_hits >= 2 else 0
