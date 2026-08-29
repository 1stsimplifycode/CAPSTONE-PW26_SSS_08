"""Canonical filesystem locations. Nothing else in the codebase hardcodes a path."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ARTIFACTS = Path(os.environ.get("AEGIS_ARTIFACTS", REPO_ROOT / "research_artifacts"))
FIGURES = ARTIFACTS / "figures"
TABLES = ARTIFACTS / "tables"
CAPTIONS = ARTIFACTS / "captions"
STATISTICS = ARTIFACTS / "statistics"
REPORTS = ARTIFACTS / "experiment_reports"
SUPPLEMENTARY = ARTIFACTS / "supplementary"
LATEX = ARTIFACTS / "latex"
CSV = ARTIFACTS / "csv"
JSON = ARTIFACTS / "json"
MANIFESTS = ARTIFACTS / "manifests"

DATA = Path(os.environ.get("AEGIS_DATA", REPO_ROOT / "data"))
PANEL = DATA / "panel"
CACHE = DATA / "cache"

#: Authoritative exchange reference data downloaded by ``research.reference.acquire``.
#: Every file here has a row in ``reference_manifest.json`` naming its source, retrieval
#: instant, licence and checksum. Never hand-edited.
REFERENCE = DATA / "reference"

#: Records rejected by ingestion validation. Preserved, never deleted: a dropped row that
#: nobody can inspect is indistinguishable from a row that never existed.
QUARANTINE = DATA / "quarantine"

#: Read-only external NSE bhavcopy archive discovered by the repository audit.
#: Never written to. Overridable so the pipeline is portable off this machine.
NSE_ARCHIVE = Path(
    os.environ.get(
        "AEGIS_NSE_ARCHIVE",
        REPO_ROOT.parent / "capstone project" / "beta layer" / "data" / "raw",
    )
)

_ALL = [
    ARTIFACTS, FIGURES, TABLES, CAPTIONS, STATISTICS, REPORTS, SUPPLEMENTARY,
    LATEX, CSV, JSON, MANIFESTS, DATA, PANEL, CACHE, REFERENCE, QUARANTINE,
]


def ensure_dirs() -> None:
    for p in _ALL:
        p.mkdir(parents=True, exist_ok=True)
