"""Fixtures for the Week 2 criteria tests. Everything reads the real artifacts.

PLAIN ENGLISH -- what this whole file is about:

THE SHARED SETUP FOR THE WEEK 2 TESTS, AND ONE IMPORTANT DECISION.

`conftest.py` is a special filename pytest looks for automatically. Anything defined here is
available to every test file in this folder, without being imported.

THE DECISION IS IN THE FIRST LINE: "Everything reads the real artifacts."
Most test suites invent small fake datasets -- neat, fast, and completely under the test
author's control. These tests read THE ACTUAL FILES the pipeline produced. So they check what
was really computed, not a tidy imitation of it.

The trade-off is that they cannot run before the pipeline has run. Which is handled below by
SKIPPING rather than failing -- and the skip message says exactly which command to run.
"""
from __future__ import annotations

import pandas as pd
import pytest

from research.core import paths

# The five artifact files and the summary these tests examine.
INTRADAY = paths.REFERENCE / "intraday_bars.parquet"
RV = paths.REFERENCE / "realised_variance.parquet"
PI = paths.REFERENCE / "price_impact.parquet"
ARRIVAL = paths.REFERENCE / "arrival_fits.parquet"
STATE = paths.REFERENCE / "liquidity_state.parquet"
SUMMARY = paths.REPO_ROOT / "outputs" / "week2" / "foundation_summary.json"


def _require(p):
    # SKIP, NOT FAIL -- and the distinction matters.
    # A FAILURE means "something is broken". A SKIP means "this could not be checked here".
    # A missing artifact on a fresh checkout is not a broken pipeline, so reporting it as a
    # failure would cry wolf and teach people to ignore red results.
    # AND THE MESSAGE NAMES THE EXACT COMMAND that would produce the missing file.
    if not p.exists():
        pytest.skip("%s not built; run scripts/build_week2_foundation.py" % p.name)
    return p


# `scope="session"` throughout: read each file ONCE for the whole test run, not once per test.
# The files are large and nothing modifies them.
@pytest.fixture(scope="session")
def bars() -> pd.DataFrame:
    return pd.read_parquet(_require(INTRADAY))


@pytest.fixture(scope="session")
def rv_table() -> pd.DataFrame:
    # Realised variance: how much a price actually moved, measured from intraday bars.
    return pd.read_parquet(_require(RV))


@pytest.fixture(scope="session")
def estimates() -> pd.DataFrame:
    # Price impact: how far the price moves when somebody trades a given size.
    return pd.read_parquet(_require(PI))


@pytest.fixture(scope="session")
def arrival() -> pd.DataFrame:
    # Trade-arrival fits: do trades arrive like raindrops, or in bursts?
    return pd.read_parquet(_require(ARRIVAL))


@pytest.fixture(scope="session")
def state() -> pd.DataFrame:
    # The liquidity state each session was classified into.
    return pd.read_parquet(_require(STATE))


@pytest.fixture(scope="session")
def summary() -> dict:
    # The headline results of the real pipeline run -- which is what lets the tests below
    # check the ACTUAL run rather than only a fresh calculation on the same data.
    import json
    return json.loads(_require(SUMMARY).read_text(encoding="utf-8"))
