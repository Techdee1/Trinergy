from pathlib import Path

import pymupdf
from PIL import Image

from src import image_utils
from src.ingest import find_pdfs, ingest_pdf


def make_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((20, 50), "Hello well log")
    doc.new_page(width=200, height=100)  # blank page: no text layer
    doc.save(path)
    doc.close()
    return path


def test_ingest_renders_pages_and_text(tmp_path):
    pdf = make_pdf(tmp_path / "tiny.pdf")
    pages = ingest_pdf(pdf, out_dir=tmp_path / "pages", dpi=72)

    assert [p.page_number for p in pages] == [1, 2]
    assert "Hello well log" in pages[0].text
    assert pages[1].text == ""
    for p in pages:
        assert Path(p.image_path).exists()
        with Image.open(p.image_path) as img:
            assert img.size == (200, 100) == (p.width, p.height)


def test_ingest_dpi_and_limit(tmp_path):
    pdf = make_pdf(tmp_path / "tiny.pdf")
    pages = ingest_pdf(pdf, out_dir=tmp_path / "pages", dpi=144, limit=1)
    assert len(pages) == 1
    assert (pages[0].width, pages[0].height) == (400, 200)
    # Second run reuses the PNG and reports the same size.
    again = ingest_pdf(pdf, out_dir=tmp_path / "pages", dpi=144, limit=1)
    assert (again[0].width, again[0].height) == (400, 200)


def test_find_pdfs(tmp_path):
    make_pdf(tmp_path / "b.pdf")
    (tmp_path / "sub").mkdir()
    make_pdf(tmp_path / "sub" / "a.PDF")
    (tmp_path / "notes.txt").write_text("x")
    assert [p.name for p in find_pdfs(tmp_path)] == ["b.pdf", "a.PDF"]


def test_image_utils():
    img = Image.new("RGB", (400, 200), "white")
    assert image_utils.crop(img, (10, 10, 110, 60)).size == (100, 50)
    assert image_utils.crop(img, (0, 0, 0.5, 0.5), normalized=True).size == (200, 100)
    assert image_utils.to_grayscale(img).mode == "L"
    assert image_utils.downscale(img, 100).size == (100, 50)
    assert image_utils.downscale(img, 1000).size == (400, 200)  # never upscales
    assert image_utils.to_png_bytes(img).startswith(b"\x89PNG")
