"""Loader for the deployment data pack (web/server/data, built by build_data.py). The server reads nothing else about the archive."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from submission.archive_qa.wells import Report

ATTRIBUTION = "Data: Equinor Volve dataset"


class DataPackError(RuntimeError):
    pass


class DataPack:
    def __init__(self, root: Path):
        self.root = Path(root)
        if not (self.root / "records.parquet").is_file():
            raise DataPackError(f"Data pack not found in {self.root} (expected records.parquet). Build it with "
                                "`python -m web.server.build_data` (needs the organiser files) or restore web/server/data from git.")
        self.records = pd.read_parquet(self.root / "records.parquet")
        rows = json.loads((self.root / "reports.json").read_text(encoding="utf-8"))
        self.reports = [Report(r["stem"], r["well"], date.fromisoformat(r["date"]), Path(r["stem"] + ".xml")) for r in rows]
        self.page_counts = {r["pdf_file"]: r["pages"] for r in rows}
        cat = json.loads((self.root / "catalog.json").read_text(encoding="utf-8"))
        self.catalog = [{"id": q["id"], "set": s, "question": q["question"]} for s in ("challenge", "unseen") for q in cat.get(s, [])]
        self.pages_dir = self.root / "pages"
        self.manifest_root = self.root / "track_2"          # a data root holding only metadata/document_manifest.csv
        self.gen_cache = self.root / "generalisation_cache.json"
        self.cost_csv = self.root / "cost_summary.csv"
        self._boxes: dict | None = None
        self.manifest = json.loads((self.root / "MANIFEST.json").read_text(encoding="utf-8")) if (self.root / "MANIFEST.json").exists() else {}

    @property
    def boxes(self) -> dict:
        if self._boxes is None:
            self._boxes = json.loads((self.root / "boxes.json").read_text(encoding="utf-8"))
        return self._boxes

    def generalisation(self) -> dict:
        p = self.root / "generalisation.json"
        if not p.is_file():
            return {"available": False, "message": "The unseen-question results are not part of this deployment "
                    "(data/generalisation.json is missing; build it with `python -m web.server.build_data`).",
                    "summary": None, "questions": []}
        return json.loads(p.read_text(encoding="utf-8"))
