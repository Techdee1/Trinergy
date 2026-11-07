"""End-to-end pipeline (placeholder).

    python -m src.pipeline --input data/raw --limit 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from src.config import get_settings
from src.cost import format_summary, summarize
from src.ingest import PageRecord, find_pdfs, ingest_pdf


def run(input_path: Path, limit: int | None, dpi: int | None) -> list[PageRecord]:
    settings = get_settings()
    pdfs = find_pdfs(input_path)
    if not pdfs:
        print(f"No PDFs found under {input_path}")
        return []

    pages: list[PageRecord] = []
    for pdf in tqdm(pdfs, desc="Ingest"):
        remaining = None if limit is None else limit - len(pages)
        if remaining is not None and remaining <= 0:
            break
        pages.extend(ingest_pdf(pdf, dpi=dpi, limit=remaining))

    n_text = sum(1 for p in pages if p.text)
    print(f"Ingested {len(pages)} pages from {len(pdfs)} PDF(s); {n_text} have a text layer.")

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = settings.output_dir / "pages.parquet"
    pd.DataFrame([p.to_dict() for p in pages]).to_parquet(manifest, index=False)
    print(f"Page manifest: {manifest}")

    # TODO(extraction): task-specific logic goes here once we have seen real data.
    #   For each page: use p.text if it is good enough; otherwise crop/downscale
    #   the relevant region (src.image_utils) and call src.llm.call_llm(...,
    #   source=f"{Path(p.pdf_path).name}:p{p.page_number}") with a compact
    #   JSON schema. Write results to settings.output_dir.

    return pages


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Legacy well records -> structured data.")
    parser.add_argument("--input", type=Path, default=settings.raw_dir,
                        help="PDF file or folder of PDFs (default: data/raw)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max total pages to process (for cheap trial runs)")
    parser.add_argument("--dpi", type=int, default=None,
                        help=f"Render DPI (default: RENDER_DPI={settings.render_dpi})")
    args = parser.parse_args()

    run(args.input, args.limit, args.dpi)
    print("\n" + format_summary(summarize()))


if __name__ == "__main__":
    main()
