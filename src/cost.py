"""Summarise cost_ledger.csv and project cost for a larger run.

    python -m src.cost                  # summary
    python -m src.cost --project 5000   # + projection for 5000 items
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import get_settings


def load_ledger(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path or get_settings().ledger_path)
    if not path.exists():
        return pd.DataFrame(columns=["input_tokens", "output_tokens", "cost_usd", "cache_hit"])
    df = pd.read_csv(path)
    df["cache_hit"] = df["cache_hit"].astype(str).str.lower() == "true"
    return df


def summarize(path: str | Path | None = None) -> dict:
    df = load_ledger(path)
    paid = df[~df["cache_hit"]] if len(df) else df
    calls = len(df)
    total = float(df["cost_usd"].sum()) if calls else 0.0
    return {
        "calls": calls,
        "cache_hits": int(df["cache_hit"].sum()) if calls else 0,
        "paid_calls": len(paid),
        "input_tokens": int(df["input_tokens"].sum()) if calls else 0,
        "output_tokens": int(df["output_tokens"].sum()) if calls else 0,
        "cost_usd": total,
        "avg_cost_per_call": total / calls if calls else 0.0,
        # New items won't hit the cache, so projections use the paid-call average.
        "avg_cost_per_paid_call": total / len(paid) if len(paid) else 0.0,
    }


def project(n_items: int, calls_per_item: float = 1.0, summary: dict | None = None) -> float:
    """Estimated USD for n_items new items, from the measured paid-call average."""
    summary = summary or summarize()
    return n_items * calls_per_item * summary["avg_cost_per_paid_call"]


def format_summary(summary: dict) -> str:
    return (
        f"LLM calls: {summary['calls']} (paid {summary['paid_calls']}, "
        f"cache hits {summary['cache_hits']})\n"
        f"Tokens: {summary['input_tokens']:,} in / {summary['output_tokens']:,} out\n"
        f"Cost: ${summary['cost_usd']:.4f} total, "
        f"${summary['avg_cost_per_call']:.5f}/call, "
        f"${summary['avg_cost_per_paid_call']:.5f}/paid call"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise the LLM cost ledger.")
    parser.add_argument("--ledger", help="Path to ledger CSV (default from config)")
    parser.add_argument("--project", type=int, metavar="N", help="Project cost for N items")
    parser.add_argument("--calls-per-item", type=float, default=1.0)
    args = parser.parse_args()

    summary = summarize(args.ledger)
    print(format_summary(summary))
    if args.project:
        est = project(args.project, args.calls_per_item, summary)
        print(f"Projected for {args.project} items x {args.calls_per_item} calls: ${est:.2f}")


if __name__ == "__main__":
    main()
