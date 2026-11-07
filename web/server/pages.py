"""Serve PDF pages with the evidence highlighted, from the data pack only (pre-rendered JPEG pages + precomputed boxes).
No PDF is opened. The highlighted PNG is composed with PyMuPDF (image + translucent rectangles on a blank page, never saved
as a PDF) and cached under RUNTIME_CACHE_DIR/pages."""

from __future__ import annotations

import threading
from pathlib import Path

import pymupdf

from .datapack import DataPack
from .highlight import PageError

MAX_ZOOM = 2.0           # the pack's page images are rendered at 2x
_PYMU = threading.Lock()


class PageService:
    def __init__(self, pack: DataPack, cache_dir: Path):
        self.pack = pack
        self.cache = Path(cache_dir) / "pages"
        self.known = set(pack.records["record_id"])

    def boxes(self, rid: str) -> dict:
        if rid not in self.known:
            raise PageError(404, "unknown_record", f"No record with id {rid!r} in the evidence store.", record_id=rid)
        b = self.pack.boxes[rid]
        if "error" in b:
            e = dict(b["error"])
            raise PageError(e.pop("status"), e.pop("code"), e.pop("message"), **e)
        return {**b, "png_url": f"/pages/{rid}.png"}

    def png(self, rid: str, zoom: float = 1.5, highlight: bool = True) -> bytes:
        b = self.boxes(rid)
        zoom = min(MAX_ZOOM, max(0.5, float(zoom)))
        key = self.cache / f"{rid}_z{zoom:g}_{'h' if highlight else 'p'}.png"
        if key.is_file():
            return key.read_bytes()
        img = self.pack.pages_dir / f"{Path(b['pdf_file']).stem}_p{b['page']}.jpg"
        if not img.is_file():
            raise PageError(404, "page_image_missing", f"The page image for {b['pdf_file']} p.{b['page']} is not in the data pack.", record_id=rid)
        w, h = b["page_width"] * zoom, b["page_height"] * zoom
        with _PYMU:
            doc = pymupdf.open()
            try:
                page = doc.new_page(width=w, height=h)
                page.insert_image(page.rect, filename=str(img))
                if highlight:
                    for bx in b["boxes"]:
                        r = pymupdf.Rect((bx["x0"] - 1) * zoom, (bx["y0"] - 1) * zoom, (bx["x1"] + 1) * zoom, (bx["y1"] + 1) * zoom)
                        page.draw_rect(r, color=(0.85, 0.45, 0.0), fill=(1.0, 0.9, 0.2), fill_opacity=0.35, width=0.8, overlay=True)
                data = page.get_pixmap(alpha=False).tobytes("png")
            finally:
                doc.close()
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            key.write_bytes(data)
        except OSError:
            pass
        return data

    def page_count(self, pdf_file: str) -> int | None:
        return self.pack.page_counts.get(pdf_file)
