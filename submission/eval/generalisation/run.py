"""Run the real pipeline on questions.csv with its own runtime cache; write predictions.csv + results.json here.

    python submission/eval/generalisation/run.py [--fresh]     (--fresh deletes this folder's runtime cache first)

Uses the API key from the environment / .env (hybrid mode); the committed cache is read-only.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from archive_qa import answer, config, llm, pipeline, route, store, write  # noqa: E402

RUNTIME_CACHE = HERE / "runtime_cache.json"          # git-ignored


def main(argv: list[str]) -> None:
    if "--fresh" in argv and RUNTIME_CACHE.exists():
        RUNTIME_CACHE.unlink()
    print(llm.describe_key())
    records = store.build_store(verbose=False) if not config.RECORDS_PATH.exists() else store.load_store()
    reports = route.discover_reports(config.XML_DIR)
    questions = pipeline.read_questions(HERE / "questions.csv")
    client = llm.LLM.from_env(runtime_cache_path=RUNTIME_CACHE)
    t0 = time.time()
    answers = answer.answer_all(questions, records, reports, client, dump=False)
    secs = time.time() - t0
    order = list(questions["question_id"])
    write.write_predictions(answers, records, HERE / "predictions.csv", order=order)
    rep = write.validate_predictions(predictions_path=HERE / "predictions.csv", expected_ids=order)
    results = {a.question_id: {"status": a.status, "mode": a.mode, "early_abstain": a.early_abstain, "candidates": a.candidates,
                               "confidence": a.confidence, "cost_usd": a.cost_usd, "live_calls": a.live_calls,
                               "verified": a.verified, "failures": a.failures, "answer": a.answer,
                               "evidence": write.build_evidence(a, records), "trace_mode": getattr(a, "trace_mode", "normal")}
               for a in answers}
    (HERE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(answers)} questions in {secs:.1f}s | live calls {client.live_calls} | cache hits {client.cache_hits} | "
          f"spent ${client.spent:.4f} | validator valid={rep['valid']} {rep['errors']}")
    print(pipeline.not_evaluated_summary(answers))


if __name__ == "__main__":
    main(sys.argv[1:])
