"""Pydantic models = the API contract (OpenAPI at /docs, prose in API.md). One Trace schema is shared by every
endpoint that returns an answer: GET /questions/{id}, POST /ask and the final `result` event of POST /ask/stream."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

QuestionSet = Literal["challenge", "unseen", "adhoc"]
AnswerStatus = Literal["answered", "partial", "abstain", "not_evaluated"]


# ------------------------------------------------------------------ trace


class StageEvent(BaseModel):
    """One thing the pipeline actually did, in order. The SSE stream emits exactly these, as they happen."""
    seq: int
    stage: Literal["route", "gate", "context_built", "aggregates_added", "second_pass", "escalate", "arbitrate",
                   "model_call", "verify", "warning", "result"]
    t_ms: int = Field(description="milliseconds since the request started")
    data: dict[str, Any]


class RouterConfidence(BaseModel):
    level: Literal["high", "medium", "low"]
    basis: str = Field(description="server-derived from the router's output (the router itself has no score)")


class WellConsidered(BaseModel):
    well: str
    in_archive: bool
    reports_available: int


class ReportSelected(BaseModel):
    report: str = Field(description="XML report file stem")
    well: str
    date: str
    reason: str


class RouterUnmatched(BaseModel):
    well: str | None
    date: str | None
    message: str


class RouterTrace(BaseModel):
    mode: str = Field(description="single_report | multi_report | archive_wide")
    confidence: RouterConfidence
    reason: str = Field(description="the router's own reason string, verbatim")
    wells_named: list[str]
    dates_named: list[str]
    date_range: list[str] | None
    topics: list[str] = Field(description="record sections the question's wording points at")
    early_abstain: bool
    wells_considered: list[WellConsidered]
    reports_selected: list[ReportSelected]
    unmatched: list[RouterUnmatched]
    gate: str | None = Field(None, description="`needs_clarification` when the server stopped a vague, uncached question before any model call")


class ContextRecord(BaseModel):
    id: str
    type: str = Field(description="record section (activity, survey, fluid, ...), or aggregate / absent")
    report: str | None


class AggregateTrace(BaseModel):
    id: str
    text: str
    sources: list[str]


class AbsentTrace(BaseModel):
    id: str
    kind: str
    reports_searched: int
    records_searched: int
    considered_and_rejected: list[dict[str, Any]]


class ContextTrace(BaseModel):
    pass_name: Literal["first_pass", "second_pass"]
    final: bool = Field(description="True when this is the context the committed answer was produced from")
    est_tokens: int = Field(description="ESTIMATE: characters/4 of the context text")
    lines: int
    truncated: bool
    notes: list[str]
    records: list[ContextRecord]
    aggregates: list[AggregateTrace]
    absent: list[AbsentTrace]


class ModelCall(BaseModel):
    n: int
    purpose: str
    role: str
    run: str
    model: str
    context_pass: Literal["first_pass", "second_pass"] | None
    outcome: Literal["cache_hit", "live", "cache_miss_offline", "budget_blocked", "error"]
    cache_hit: bool
    prompt_tokens: int | None = Field(description="as reported by the provider (OpenRouter `usage`); null when no call was made or the provider sent no usage. Never estimated.")
    completion_tokens: int | None = Field(description="as reported by the provider; null as above")
    tokens_source: Literal["provider_reported", "provider_reported_cached", "not_reported", "no_call"] = Field(
        description="provider_reported = this live call; provider_reported_cached = the provider's numbers stored with the cached answer "
                    "(from when it was generated); not_reported = a call whose reply carried no usage; no_call = lookup missed, nothing was sent")
    context_tokens_estimate: int | None = Field(None, description="ESTIMATE ONLY: characters/4 of the evidence text sent (excludes the system prompt "
                                                                  "and the question). Compare with prompt_tokens for a sanity check; never use it as a bill.")
    latency_ms: int
    cost_usd: float = Field(description="what this call cost when it was generated (the cached value for a cache hit)")
    incurred_usd: float = Field(description="charged now: 0 for a cache hit")
    finish_reason: str | None
    max_tokens: int | None
    reply_status: str | None
    reply_cited: list[str]
    feedback: str | None = Field(description="verifier / arbitration feedback sent with this call, clipped")
    error: str | None = None


class Check(BaseModel):
    name: str
    label: str
    result: Literal["pass", "fail", "flag", "not_applicable"]
    detail: list[str] = Field(default_factory=list)


class VerifyTrace(BaseModel):
    n: int
    target: str = Field(description="which model call's reply was checked, or citation_repair")
    target_call: int | None
    reply_status: str | None
    ok: bool
    checks: list[Check]
    failures: list[str]
    flags: list[str]
    flagged_ids: list[str]


class Totals(BaseModel):
    model_calls: int
    live_calls: int
    cache_hits: int
    prompt_tokens: int = Field(description="sum of the provider-reported prompt tokens (calls without a report count as 0, see calls_without_token_report)")
    completion_tokens: int
    calls_without_token_report: int
    generation_cost_usd: float
    incurred_cost_usd: float
    model_latency_ms: int
    wall_ms: int


class CitedTrace(BaseModel):
    model_cited: list[str] | None = Field(description="ids in the reply the committed answer came from")
    final: list[str] = Field(description="record ids shown as evidence (aggregates expanded to their sources)")
    aggregates_cited: list[str]
    absent_cited: list[str]


class Trace(BaseModel):
    router: RouterTrace
    contexts: list[ContextTrace]
    model_calls: list[ModelCall]
    verifier: list[VerifyTrace]
    retries: list[int] = Field(description="model_calls[].n of truncated/invalid-JSON retries")
    escalations: list[dict[str, Any]]
    second_pass: dict[str, Any]
    arbitration: dict[str, Any]
    cited: CitedTrace
    decisions: list[str] = Field(description="the pipeline's own notes about what it decided, verbatim")
    warnings: list[dict[str, str]]
    totals: Totals
    events: list[StageEvent]


# ------------------------------------------------------------------ answer


class Evidence(BaseModel):
    kind: Literal["pdf", "xml_only", "absent"]
    label: str = Field(description="'<pdf> p.N (Section)', 'XML only', or what was searched")
    pdf_file: str | None = None
    page: int | None = None
    section: str | None = None
    xml_file: str | None = None
    xml_only_paths: list[str] = Field(default_factory=list)
    page_url: str | None = None
    boxes_url: str | None = None


class CitedRecord(BaseModel):
    id: str
    type: str
    text: str
    report: str | None
    well: str | None
    report_date: str | None
    evidence: Evidence


class Clarification(BaseModel):
    message: str
    examples: list[str] = Field(description="real answered questions of the catalog, so each example can be asked as is")


class QuestionSummary(BaseModel):
    id: str
    set: QuestionSet
    question: str
    status: AnswerStatus
    confidence: float
    flags: list[str]
    router_mode: str


class QuestionDetail(BaseModel):
    id: str
    set: QuestionSet
    question: str
    status: AnswerStatus
    answer: str
    rationale: str
    confidence: float
    verified: bool
    flags: list[str]
    router_mode: str
    source: Literal["cache", "live", "mixed", "none"] = Field(
        description="cache = every model call was a cache hit; live = at least one call was made; none = no model call (early abstain)")
    evidence: str = Field(description="the predictions.csv-style evidence string")
    cited_records: list[CitedRecord]
    clarification: Clarification | None = Field(None, description="set only when the question was too vague to look up (flag needs_clarification)")
    trace: Trace


class AskRequest(BaseModel):
    question: str = Field(min_length=1, description="max 400 characters (MAX_QUESTION_CHARS)")


class Health(BaseModel):
    status: str
    live_mode: bool
    models: dict[str, str | None]
    version: str
    attribution: str
    budget_remaining_usd: float
    details: dict[str, Any] = Field(default_factory=dict)
