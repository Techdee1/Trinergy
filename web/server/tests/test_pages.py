import pytest
import pandas as pd

from submission.archive_qa import config
from web.server.pages import PageService


def test_png_and_boxes(client, engine):
    rid = "19A-19970829-ACT-04"
    r = client.get(f"/pages/{rid}.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    plain = client.get(f"/pages/{rid}.png?highlight=false").content
    assert plain != r.content                                                   # the highlight is really drawn
    b = client.get(f"/pages/{rid}/boxes").json()
    assert b["match"] == "row" and b["section"] == "Operations" and b["page"] == 1 and b["boxes"]
    for x in b["boxes"]:
        assert 0 <= x["x0"] < x["x1"] <= b["page_width"] and 0 <= x["y0"] < x["y1"] <= b["page_height"]
        assert 0 <= x["nx0"] < x["nx1"] <= 1
    assert list((engine.s.runtime_dir / "pages").glob(f"{rid}_*.png"))          # cached on disk, in the runtime dir only


def test_xml_only_and_unknown_are_clear_404s(client, engine):
    rec = engine.records
    rid = rec[rec["pdf_match"] == "not_printed"]["record_id"].iloc[0]
    for path in (f"/pages/{rid}.png", f"/pages/{rid}/boxes"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "xml_only" and "XML-only" in r.json()["detail"]["message"]
    r = client.get("/pages/NOPE.png")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_record"
    r = client.get("/pages/../../etc/passwd.png")
    assert r.status_code == 404


def test_every_located_record_gets_a_highlight(tmp_path, engine):
    ps = PageService(engine.records, config.PDF_DIR, tmp_path)
    kinds = {}
    for rid in engine.records["record_id"]:
        try:
            kinds[rid] = ps.boxes(rid)
        except Exception as e:  # noqa: BLE001
            assert getattr(e, "code", None) == "xml_only", (rid, e)
    assert len(kinds) > 1200
    assert all(b["boxes"] for b in kinds.values()), [r for r, b in kinds.items() if not b["boxes"]][:5]
    assert {b["match"] for b in kinds.values()} <= {"row", "value", "label", "heading"}


def test_cited_xml_only_records_have_no_page_url(client):
    for qid in ("T2-001", "T2-002", "T2-003", "T2-004", "T2-005", "T2-006", "T2-007", "T2-008"):
        for c in client.get(f"/questions/{qid}").json()["cited_records"]:
            ev = c["evidence"]
            assert (ev["page_url"] is None) == (ev["kind"] != "pdf")
