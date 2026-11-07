"""Small image helpers used to shrink what we send to the LLM."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

BBox = tuple[float, float, float, float]  # (x0, y0, x1, y1)


def load(path: str | Path) -> Image.Image:
    with Image.open(path) as img:
        return img.copy()


def crop(img: Image.Image, bbox: BBox, normalized: bool = False) -> Image.Image:
    """Crop to bbox. With normalized=True, bbox values are fractions (0..1) of width/height."""
    x0, y0, x1, y1 = bbox
    if normalized:
        x0, x1 = x0 * img.width, x1 * img.width
        y0, y1 = y0 * img.height, y1 * img.height
    box = (
        max(0, round(x0)),
        max(0, round(y0)),
        min(img.width, round(x1)),
        min(img.height, round(y1)),
    )
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"Empty crop for bbox {bbox} on image {img.size}")
    return img.crop(box)


def to_grayscale(img: Image.Image) -> Image.Image:
    return img.convert("L")


def downscale(img: Image.Image, max_side: int) -> Image.Image:
    """Shrink so the longest side is <= max_side. Never upscales."""
    longest = max(img.size)
    if longest <= max_side:
        return img
    scale = max_side / longest
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
