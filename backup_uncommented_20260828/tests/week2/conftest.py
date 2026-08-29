"""Fixtures for the Week 2 criteria tests. Everything reads the real artifacts."""
from __future__ import annotations

import pandas as pd
import pytest

from research.core import paths

INTRADAY = paths.REFERENCE / "intraday_bars.parquet"
RV = paths.REFERENCE / "realised_variance.parquet"
PI = paths.REFERENCE / "price_impact.parquet"
ARRIVAL = paths.REFERENCE / "arrival_fits.parquet"
STATE = paths.REFERENCE / "liquidity_state.parquet"
SUMMARY = paths.REPO_ROOT / "outputs" / "week2" / "foundation_summary.json"


def _require(p):
    if not p.exists():
        pytest.skip("%s not built; run scripts/build_week2_foundation.py" % p.name)
    return p


@pytest.fixture(scope="session")
def bars() -> pd.DataFrame:
    return pd.read_parquet(_require(INTRADAY))


@pytest.fixture(scope="session")
def rv_table() -> pd.DataFrame:
    return pd.read_parquet(_require(RV))


@pytest.fixture(scope="session")
def estimates() -> pd.DataFrame:
    return pd.read_parquet(_require(PI))


@pytest.fixture(scope="session")
def arrival() -> pd.DataFrame:
    return pd.read_parquet(_require(ARRIVAL))


@pytest.fixture(scope="session")
def state() -> pd.DataFrame:
    return pd.read_parquet(_require(STATE))


@pytest.fixture(scope="session")
def summary() -> dict:
    import json
    return json.loads(_require(SUMMARY).read_text(encoding="utf-8"))
