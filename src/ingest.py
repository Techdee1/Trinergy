"""Render PDF pages to PNG and extract the native text layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from src.config import get_settings


@dataclass
class PageRecord:
    pdf_path: str
    page_number: int  # 1-based
    image_path: str
    width: int
    height: int
    dpi: int
    text: str  # native text layer; "" for pure scans

    def to_dict(self) -> dict:
        return asdict(self)


def ingest_pdf(
    pdf_path: str | Path,
    out_dir: str | Path | None = None,
    dpi: int | None = None,
    limit: int | None = None,
) -> list[PageRecord]:
    """Render up to `limit` pages of one PDF. Already-rendered PNGs are reused."""
    settings = get_settings()
    pdf_path = Path(pdf_path)
    dpi = dpi or settings.render_dpi
    page_dir = Path(out_dir or settings.pages_dir) / f"{pdf_path.stem}_{dpi}dpi"
    page_dir.mkdir(parents=True, exist_ok=True)

    records: list[PageRecord] = []
    with pymupdf.open(pdf_path) as doc:
        n_pages = len(doc) if limit is None else min(limit, len(doc))
        for i in range(n_pages):
            page = doc[i]
            image_path = page_dir / f"page_{i + 1:04d}.png"
            if image_path.exists():
                rect = page.rect
                width, height = round(rect.width * dpi / 72), round(rect.height * dpi / 72)
            else:
                pix = page.get_pixmap(dpi=dpi)
                pix.save(image_path)
                width, height = pix.width, pix.height
            records.append(
                PageRecord(
                    pdf_path=str(pdf_path),
                    page_number=i + 1,
                    image_path=str(image_path),
                    width=width,
                    height=height,
                    dpi=dpi,
                    text=page.get_text("text").strip(),
                )
            )
    return records


def find_pdfs(input_path: str | Path) -> list[Path]:
    """A single PDF, or all PDFs under a directory (recursive, sorted)."""
    input_path = Path(input_path)
    if input_path.is_file():
        return [input_path]
    return sorted(p for p in input_path.rglob("*") if p.suffix.lower() == ".pdf")
