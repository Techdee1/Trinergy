"""FastAPI app: the contract is in schemas.py (OpenAPI at /docs) and web/server/API.md.

Run from the repo root:   uvicorn web.server.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from submission.archive_qa import config

from . import archive_view, costs_view
from .datapack import ATTRIBUTION
from .clientid import client_identity, identity_mode
from .engine import AskDisabled, Engine, clean_question
from .guards import RateLimited, RateLimiter
from .highlight import PageError
from .pages import PageService
from .safety import install_log_redaction, redact
from .schemas import AskRequest, Health, QuestionDetail
from .settings import VERSION, Settings

log = logging.getLogger("web.server")


API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# FastAPI's /docs (Swagger UI) and /redoc load their bundle from cdn.jsdelivr.net and use an inline bootstrap script/style
DOCS_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; "
            "worker-src blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def security_headers(path: str) -> dict[str, str]:
    docs = path in ("/docs", "/redoc", "/docs/oauth2-redirect")
    return {"Strict-Transport-Security": "max-age=31536000; includeSubDomains", "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": DOCS_CSP if docs else API_CSP}


def _err(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or (engine.s if engine else Settings())
    limiter = RateLimiter(settings.rate_per_min, settings.rate_per_day)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        install_log_redaction()
        eng = engine or Engine(settings)
        app.state.engine = eng
        app.state.pages = PageService(eng.pack, settings.runtime_dir)
        app.state.sem = asyncio.Semaphore(settings.max_concurrent_asks)
        app.state.identity_sources = {}
        if settings.warm_on_start:
            threading.Thread(target=eng.warm, daemon=True, name="warm").start()
        yield
        if engine is None:
            eng.close()

    app = FastAPI(
        title="Intelligent Well Archive API", version=VERSION, lifespan=lifespan,
        description="Local backend for the Volve daily-drilling-report Q&A pipeline (NAPE AICE 2026, Track 2). "
                    "Every answer carries a full trace of what the pipeline did. Contract notes: web/server/API.md.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["*"], expose_headers=["Retry-After"])

    @app.middleware("http")
    async def common_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Data-Attribution"] = ATTRIBUTION
        for k, v in security_headers(request.url.path).items():
            resp.headers.setdefault(k, v)
        return resp

    def eng(request: Request) -> Engine:
        return request.app.state.engine

    # ------------------------------------------------------------------ errors
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errs = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "message": "Invalid request.", "errors": errs}})

    @app.exception_handler(PageError)
    async def _page_error(request: Request, exc: PageError):
        return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message, **exc.extra}})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.error("unhandled error on %s: %s", request.url.path, redact(f"{type(exc).__name__}: {exc}"))
        # ServerErrorMiddleware sits outside the app's middleware, so this response gets the common headers here
        return JSONResponse(status_code=500, content={"detail": {"code": "internal_error", "message": "Internal server error."}},
                            headers={"X-Data-Attribution": ATTRIBUTION, **security_headers(request.url.path)})

    # ------------------------------------------------------------------ health
    @app.get("/health", response_model=Health, tags=["meta"])
    def health(request: Request):
        e = eng(request)
        return Health(status="ok", live_mode=e.live_mode, models=e.models(), version=VERSION, attribution=ATTRIBUTION,
                      budget_remaining_usd=round(e.spend.remaining, 6),
                      details={"records": len(e.records), "reports": len(e.reports), "catalog_questions": len(e.catalog),
                               "warm_seconds": e.warm_seconds, "data_pack": {k: e.pack.manifest.get(k) for k in ("built", "records", "reports", "pages", "total_bytes")}, "provider_fallback_active": e.provider_fallback_active,
                               "server_budget_usd": e.s.server_budget_usd, "max_question_chars": e.s.max_question_chars,
                               "rate_limit": {"per_minute": e.s.rate_per_min, "per_day": e.s.rate_per_day,
                                              "client_identity": {"mode": identity_mode(e.s.trust_proxy, e.s.trusted_proxy_hops),
                                                                  "trust_proxy": e.s.trust_proxy, "trusted_proxy_hops": e.s.trusted_proxy_hops,
                                                                  "sources_used_since_start": dict(request.app.state.identity_sources)}},
                               "key_configured": e.key_present})

    @app.get("/whoami", tags=["meta"])
    def whoami(request: Request):
        """Diagnostic: the proxy headers exactly as this server sees them for THIS request, and which one the rate limiter would use.
        It only echoes what the caller sent plus the proxy's own additions (the caller's own address and hop addresses); no secret."""
        e = eng(request)
        host = request.client.host if request.client else None
        key, source = client_identity(request.headers, host, e.s.trust_proxy, e.s.trusted_proxy_hops)
        h = request.headers
        return {"mode": identity_mode(e.s.trust_proxy, e.s.trusted_proxy_hops), "identity_source": source, "bucket_key": key,
                "seen": {"x-forwarded-for": h.get("x-forwarded-for"), "cf-connecting-ip": h.get("cf-connecting-ip"),
                         "x-real-ip": h.get("x-real-ip"), "forwarded": h.get("forwarded"), "x-forwarded-proto": h.get("x-forwarded-proto"),
                         "connection_address": host}}

    # ------------------------------------------------------------------ questions
    @app.get("/questions", tags=["questions"])
    def questions(request: Request, set: str | None = None):
        """The 32 challenge questions plus the unseen generalisation set, each flagged by `set`."""
        e = eng(request)
        out = []
        for c in e.catalog:
            if set and c["set"] != set:
                continue
            d = e.replayed(c["id"])
            out.append({"id": c["id"], "set": c["set"], "question": c["question"], "status": d.status,
                        "confidence": d.confidence, "flags": d.flags, "router_mode": d.router_mode})
        counts: dict[str, int] = {}
        for r in out:
            counts[r["set"]] = counts.get(r["set"], 0) + 1
        return {"count": len(out), "sets": counts, "questions": out}

    @app.get("/questions/{question_id}", response_model=QuestionDetail, tags=["questions"])
    def question(request: Request, question_id: str):
        """A catalog question (or an earlier /ask answer, id ASK-xxxxxxxx), replayed offline from the caches."""
        d = eng(request).replayed(question_id)
        if d is None:
            raise _err(404, "unknown_question", f"No question with id {question_id!r}.")
        return d

    # ------------------------------------------------------------------ ask
    def _prepare(request: Request, body: AskRequest) -> str:
        e = eng(request)
        if len(body.question) > e.s.max_question_chars:
            raise _err(422, "question_too_long", f"The question is {len(body.question)} characters; the maximum is {e.s.max_question_chars}.")
        q = clean_question(body.question)
        if not q:
            raise _err(422, "question_empty", "The question is empty.")
        key, source = client_identity(request.headers, request.client.host if request.client else None, e.s.trust_proxy, e.s.trusted_proxy_hops)
        seen = request.app.state.identity_sources
        seen[source] = seen.get(source, 0) + 1
        try:
            limiter.check(key)
        except RateLimited as r:
            raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": r.message},
                                headers={"Retry-After": str(r.retry_after)})
        return q

    @app.post("/ask", response_model=QuestionDetail, tags=["ask"])
    async def ask(request: Request, body: AskRequest):
        """Cache first, live model if a key exists and the server budget remains. Never writes the committed files."""
        q = _prepare(request, body)
        e = eng(request)
        loop = asyncio.get_running_loop()
        async with request.app.state.sem:
            try:
                return await asyncio.wait_for(loop.run_in_executor(None, e.ask, q), timeout=e.s.ask_timeout_s)
            except asyncio.TimeoutError:
                raise _err(504, "timeout", f"The question did not finish within {e.s.ask_timeout_s:.0f} s.")
            except AskDisabled as a:
                raise _err(503, a.code, a.message)

    def _sse(event: str, data, eid: int | None = None) -> str:
        head = f"id: {eid}\n" if eid is not None else ""
        return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.post("/ask/stream", tags=["ask"], response_class=StreamingResponse,
              responses={200: {"content": {"text/event-stream": {}}, "description": "SSE: one event per real pipeline stage "
                          "(route, gate, context_built, aggregates_added, second_pass, escalate, arbitrate, model_call, verify, "
                          "warning), then `result` (the full QuestionDetail) or `error`."}})
    async def ask_stream(request: Request, body: AskRequest):
        q = _prepare(request, body)
        e = eng(request)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def put(kind, payload):
            loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))

        def work():
            try:
                put("result", e.ask(q, sink=lambda ev: put("event", ev)))
            except AskDisabled as a:
                put("error", {"code": a.code, "message": a.message})
            except Exception as ex:  # noqa: BLE001
                log.error("stream failed: %s", e.safe_error(ex))
                put("error", {"code": "internal_error", "message": "The question failed on the server."})

        async def gen():
            async with request.app.state.sem:
                fut = loop.run_in_executor(None, work)
                deadline = loop.time() + e.s.ask_timeout_s
                while True:
                    left = deadline - loop.time()
                    if left <= 0:
                        yield _sse("error", {"code": "timeout", "message": f"The question did not finish within {e.s.ask_timeout_s:.0f} s."})
                        return
                    try:
                        kind, payload = await asyncio.wait_for(queue.get(), timeout=min(10.0, left))
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if kind == "event":
                        yield _sse(payload["stage"], payload, payload["seq"])
                    elif kind == "result":
                        yield _sse("result", payload.model_dump(mode="json"), len(payload.trace.events))
                        await fut
                        return
                    else:
                        yield _sse("error", payload)
                        await fut
                        return

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

    # ------------------------------------------------------------------ pages
    @app.get("/pages/{record_id}.png", tags=["evidence"], response_class=Response,
             responses={200: {"content": {"image/png": {}}}, 404: {"description": "unknown record, XML-only evidence, or PDF not on this server"}})
    def page_png(request: Request, record_id: str, zoom: float = 1.5, highlight: bool = True):
        """The PDF page holding the record, evidence highlighted. 404 `xml_only` when the value is not printed in the PDF."""
        data = request.app.state.pages.png(record_id, zoom, highlight)
        return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/pages/{record_id}/boxes", tags=["evidence"])
    def page_boxes(request: Request, record_id: str):
        """Highlight rectangles for the record on its page (PDF points and page fractions)."""
        return request.app.state.pages.boxes(record_id)

    # ------------------------------------------------------------------ archive
    @app.get("/archive", tags=["archive"])
    def archive(request: Request):
        e, pages = eng(request), request.app.state.pages
        return {**archive_view.archive_summary(e.reports, e.records, lambda f: pages.page_count(f)), "attribution": ATTRIBUTION}

    @app.get("/trajectories", tags=["archive"])
    def trajectories(request: Request):
        e = eng(request)
        return archive_view.trajectories(e.records, e.s.trajectory_min_stations)

    # ------------------------------------------------------------------ costs and generalisation
    @app.get("/costs", tags=["meta"])
    def costs(request: Request):
        e = eng(request)
        sets = {c["id"]: c["set"] for c in e.catalog}
        return costs_view.costs(config.LLM_CACHE_PATH, e.pack.cost_csv, e.runtime_cache.path, [e.pack.gen_cache], e.spend, e.stats, sets)

    @app.get("/generalisation", tags=["meta"])
    def generalisation(request: Request):
        """The unseen-set results, read from the data pack (built once from the evaluation outputs)."""
        return {**eng(request).pack.generalisation(), "attribution": ATTRIBUTION}

    return app


app = create_app()
