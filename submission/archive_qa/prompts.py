"""Fixed system prompt and JSON contract (copied from the benchmark so the submission does not depend on tools/).

SYSTEM_PROMPT is the benchmark's `compact_ts` variant: short (about 250 tokens), no per-question rules.
The sha256 of the prompt is part of every cache key, so editing it invalidates cached answers on purpose.
"""

from __future__ import annotations

import hashlib

SYSTEM_PROMPT = """Answer the question using ONLY the evidence lines. Reply with JSON only:
{"status":"answered"|"partial"|"abstain","answer":str,"cited_ids":[str],"rationale":str}
Rules: cite the IDs of the lines you used; never invent an ID; include units; if the lines do not contain the information, status "abstain" with empty answer; if only part of the question is supported, status "partial" and answer that part only; never substitute a different field for the one asked. rationale: one short sentence.
Record IDs carry the report date; a sample/event timestamp may fall on the day before the report date and still belongs to that report: answer from that line and state its actual timestamp."""

# Strict JSON schema sent as response_format (json_schema). Same four fields as the prompt.
ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "partial", "abstain"]},
        "answer": {"type": "string"},
        "cited_ids": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["status", "answer", "cited_ids", "rationale"],
    "additionalProperties": False,
}


def prompt_sha(text: str = SYSTEM_PROMPT) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
