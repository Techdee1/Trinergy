"""Pages and boxes are served from the data pack only (pre-rendered JPEGs + precomputed boxes)."""

import json

import pandas as pd
import pytest

from web.server.pages import PageService


def test_png_and_boxes(client, engine):
    rid = "19A-19970829-ACT-04"
    r = client.get(f"/pages/{rid}.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    plain = client.get(f"/pages/{rid}.png?highlight=false").content
    assert plain != r.content                                                   # the highlight is really drawn
    b = client.get(f"/pages/{rid}/boxes").json()
    assert b["match"] == "row" and b["section"] == "Operations" and b["page"] == 1 and b["boxes"] and b["png_url"] == f"/pages/{rid}.png"
    for x in b["boxes"]:
        assert 0 <= x["x0"] < x["x1"] <= b["page_width"] and 0 <= x["y0"] < x["y1"] <= b["page_height"]
        assert 0 <= x["nx0"] < x["nx1"] <= 1
    assert list((engine.s.runtime_dir / "pages").glob(f"{rid}_*.png"))          # composed once, cached in the runtime dir only


def test_zoom_changes_size_and_is_clamped(client):
    import struct
    def size(z):
        d = client.get(f"/pages/19A-19970829-ACT-04.png?zoom={z}").content
        return struct.unpack(">II", d[16:24])
    assert size(1.0) == (595, 842) and size(2.0) == (1190, 1684) and size(9) == size(2.0) and size(0.1) == size(0.5)


def test_xml_only_and_unknown_are_clear_404s(client, engine):
    rec = engine.records
    rid = rec[rec["pdf_match"] == "not_printed"]["record_id"].iloc[0]
    for path in (f"/pages/{rid}.png", f"/pages/{rid}/boxes"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "xml_only" and "XML-only" in r.json()["detail"]["message"]
    r = client.get("/pages/NOPE.png")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_record"
    assert client.get("/pages/../../etc/passwd.png").status_code == 404


def test_every_record_is_covered_by_the_pack(engine):
    boxes, pack = engine.pack.boxes, engine.pack
    assert set(boxes) == set(engine.records["record_id"])
    withpage = {k: b for k, b in boxes.items() if "error" not in b}
    assert len(withpage) > 1200 and all(b["boxes"] for b in withpage.values())
    assert {b["match"] for b in withpage.values()} <= {"row", "value", "label", "heading"}
    assert {b["error"]["code"] for b in boxes.values() if "error" in b} == {"xml_only"}
    for b in withpage.values():                                                 # a page image exists for every box set
        assert (pack.pages_dir / f"{b['pdf_file'][:-4]}_p{b['page']}.jpg").is_file()
    assert sum(p.stat().st_size for p in pack.pages_dir.glob("*.jpg")) < 25_000_000


def test_cited_xml_only_records_have_no_page_url(client):
    for qid in ("T2-001", "T2-002", "T2-003", "T2-004", "T2-005", "T2-006", "T2-007", "T2-008"):
        for c in client.get(f"/questions/{qid}").json()["cited_records"]:
            ev = c["evidence"]
            assert (ev["page_url"] is None) == (ev["kind"] != "pdf")
