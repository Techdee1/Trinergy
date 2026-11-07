import logging
import math

import pandas as pd

from web.server import safety
from web.server.archive_view import min_curvature, parent_well, trajectories
from web.server.guards import SpendLedger


def test_min_curvature_vertical_and_arc():
    st = [{"md": 0, "incl": 0, "azi": 0}, {"md": 100, "incl": 0, "azi": 0}, {"md": 200, "incl": 0, "azi": 0}]
    assert [p["tvd"] for p in min_curvature(st, 0)] == [0, 100, 200] and all(p["x"] == p["y"] == 0 for p in min_curvature(st, 0))
    R = 600.0                                     # circular build 0 -> 90 deg towards north: exact for minimum curvature
    arc = [{"md": R * math.radians(a), "incl": a, "azi": 0} for a in (0, 45, 90)]
    p = min_curvature(arc, 0)[-1]
    assert abs(p["y"] - R) < 0.1 and abs(p["tvd"] - R) < 0.1 and p["x"] == 0
    east = [{"md": 0, "incl": 90, "azi": 90}, {"md": 50, "incl": 90, "azi": 90}]
    assert min_curvature(east, 1000)[-1] == {"x": 50.0, "y": 0.0, "tvd": 1000.0}


def test_trajectory_skips_wellbores_with_too_few_or_missing_stations():
    def row(i, md, incl, azi, well="W"):
        import json
        return {"record_id": f"{well}-{i}", "well": well, "report_date": "2000-01-01", "section": "survey", "field": "incl",
                "value": str(incl), "value_num": incl, "missing": incl is None, "timestamp": None,
                "attrs": json.dumps({"md": {"value": md}, "azi": {"value": azi}, "tvd": {"value": None}})}
    df = pd.DataFrame([row(1, 0, 0, 0), row(2, 100, 10, 90), row(3, 200, 20, 90), row(4, 200, 20, 90),
                       row(5, 10, 5, None, "X"), row(6, 20, 5, None, "X"), row(7, 30, 5, None, "X"),
                       row(8, 0, 0, 0, "Y"), row(9, 50, 5, 5, "Y")])
    by = {w["wellbore"]: w for w in trajectories(df, 3)["wellbores"]}
    assert by["W"]["status"] == "ok" and by["W"]["stations_used"] == 3 and by["W"]["duplicate_stations_ignored"] == 1
    assert by["W"]["tvd_origin"].startswith("assumed vertical")
    assert by["X"]["status"] == "skipped" and "azi: 3" in by["X"]["reason"] and "-999.99" in by["X"]["reason"]
    assert by["Y"]["status"] == "skipped" and by["Y"]["stations"] == []


def test_parent_well_is_derived_from_the_name():
    assert [parent_well(w) for w in ("15/9-F-1-C", "15/9-F-11-T2", "15/9-F-12", "15/9-19-A")] == ["15/9-F-1", "15/9-F-11", "15/9-F-12", "15/9-19"]


def test_spend_ledger_persists(tmp_path):
    a = SpendLedger(tmp_path / "s.json", 1.0)
    a.add(0.25)
    b = SpendLedger(tmp_path / "s.json", 1.0)
    assert b.spent == 0.25 and b.remaining == 0.75


def test_secret_never_survives_redaction(caplog):
    key = "sk-or-v1-" + "a1b2c3d4" * 6
    safety.register_secret(key)
    assert key not in safety.redact(f"HTTP 401 for Bearer {key} on {key}") and "***" in safety.redact(f"x {key}")
    assert "sk-or-" not in safety.redact("token sk-or-v1-deadbeefdeadbeef0000")
    safety.install_log_redaction()
    lg = logging.getLogger("web.server")
    lg.warning("leaked %s", "plain")                     # args intact for ordinary records
