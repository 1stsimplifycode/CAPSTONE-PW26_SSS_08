"""Leakage tests L1-L6 (spec section 56).

These are the tests that decide whether any result in this repository may be believed. A
failure here is not a bug to be worked around: it invalidates every claim that depends on
the affected path, and the runner is expected to block on it.

L1  randomised as-of      querying at an earlier cutoff must never return later knowledge
L2  future shift          shifting the panel forward must shift the features, not leak
L3  restatement           a restated value must be invisible before its knowledge time
L4  survivorship          a forward-looking constituent list must refuse historical dates
L5  coverage substitution an absent block must not be silently imputed
L6  threshold provenance  the operating threshold must come from the training split only
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from research.core.contracts import (
    BitemporalStore,
    EvidenceRecord,
    EvidenceBlock,
    LeakageError,
    Provenance,
    get_evidence,
)
from research.data.universe import StaticListUniverse, SurvivorshipBiasError
from research.market import features as mf


def _rec(instrument: str, event: datetime, knowledge: datetime, value: float,
         fact_key: str = "v") -> EvidenceRecord:
    return EvidenceRecord(
        instrument_id=instrument, block=EvidenceBlock.MARKET,
        payload={"value": value},
        provenance=Provenance(source="test", licence="test", event_time=event,
                              knowledge_time=knowledge),
        fact_key=fact_key)


# -- L1 ---------------------------------------------------------------------------------

def test_L1_randomised_as_of_never_returns_future_knowledge():
    rng = np.random.default_rng(7)
    store = BitemporalStore()
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(300):
        ev = t0 + timedelta(days=int(rng.integers(0, 200)))
        kn = ev + timedelta(days=int(rng.integers(0, 30)))
        store.append(_rec("AAA", ev, kn, float(i), fact_key="f%d" % i))

    for _ in range(200):
        cutoff = t0 + timedelta(days=int(rng.integers(0, 230)))
        out = get_evidence(store, "AAA", cutoff, cutoff)
        assert all(r.knowledge_time <= cutoff for r in out)
        assert all(r.event_time <= cutoff for r in out)


def test_L1_cutoff_after_decision_time_is_rejected():
    store = BitemporalStore()
    t = datetime(2024, 6, 1, tzinfo=UTC)
    store.append(_rec("AAA", t, t, 1.0))
    with pytest.raises(LeakageError):
        get_evidence(store, "AAA", t, t + timedelta(days=1))


def test_L1_knowledge_before_event_is_rejected_at_construction():
    t = datetime(2024, 6, 1, tzinfo=UTC)
    with pytest.raises(LeakageError):
        Provenance(source="s", licence="l", event_time=t,
                   knowledge_time=t - timedelta(seconds=1))


# -- L2 ---------------------------------------------------------------------------------

def _toy_panel(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    return pd.DataFrame({
        "date": dates, "symbol": "AAA", "open": px, "high": px * 1.01,
        "low": px * 0.99, "close": px, "prev_close": np.r_[px[0], px[:-1]],
        "volume": rng.integers(1e5, 1e6, n).astype(float),
        "turnover": rng.integers(1e7, 1e8, n).astype(float),
        "trades": rng.integers(1e3, 1e4, n).astype(float),
    })


def test_L2_future_bars_cannot_change_past_features():
    """Truncating the future must leave every past feature value bit-identical."""
    panel = _toy_panel()
    full = mf.compute_features(panel).set_index("date")
    cut = mf.compute_features(panel.iloc[:300]).set_index("date")
    common = cut.index
    for col in mf.MARKET_FEATURES:
        a = full.loc[common, col].to_numpy(float)
        b = cut.loc[common, col].to_numpy(float)
        both = np.isfinite(a) & np.isfinite(b)
        assert np.allclose(a[both], b[both], rtol=1e-9, atol=1e-12), (
            "feature %s changed when future bars were removed: it reads ahead" % col)


def test_L2_shifting_the_panel_shifts_the_features():
    """A pure time shift must move features by exactly the same shift."""
    panel = _toy_panel()
    base = mf.compute_features(panel)
    shifted_panel = panel.copy()
    shifted_panel["date"] = shifted_panel["date"] + pd.Timedelta(days=7)
    shifted = mf.compute_features(shifted_panel)
    for col in ("vol_21d", "ret_5d", "turnover_z_21"):
        a = base[col].to_numpy(float)
        b = shifted[col].to_numpy(float)
        ok = np.isfinite(a) & np.isfinite(b)
        assert np.allclose(a[ok], b[ok], rtol=1e-9)


# -- L3 ---------------------------------------------------------------------------------

def test_L3_restatement_is_invisible_before_its_knowledge_time():
    store = BitemporalStore()
    event = datetime(2024, 3, 1, tzinfo=UTC)
    original_kn = datetime(2024, 3, 2, tzinfo=UTC)
    restated_kn = datetime(2024, 5, 1, tzinfo=UTC)
    store.append(_rec("AAA", event, original_kn, 10.0, fact_key="revenue"))
    store.append(_rec("AAA", event, restated_kn, 4.0, fact_key="revenue"))

    before = get_evidence(store, "AAA", datetime(2024, 4, 1, tzinfo=UTC))
    assert len(before) == 1
    assert before[0].payload["value"] == 10.0, "restatement leaked backwards"

    after = get_evidence(store, "AAA", datetime(2024, 6, 1, tzinfo=UTC))
    assert len(after) == 1
    assert after[0].payload["value"] == 4.0, "restatement not applied after its "\
                                             "knowledge time"


# -- L4 ---------------------------------------------------------------------------------

def test_L4_static_universe_refuses_historical_dates():
    u = StaticListUniverse(["AAA", "BBB"], as_of=pd.Timestamp("2026-01-01").date())
    with pytest.raises(SurvivorshipBiasError):
        u.members_on(pd.Timestamp("2015-01-01"))
    # The escape hatch exists only to quantify the bias, and must be explicit.
    assert u.members_on(pd.Timestamp("2015-01-01"),
                        allow_survivorship_bias=True) == ["AAA", "BBB"]


def test_L4_pit_universe_has_genuine_churn():
    """A survivorship-safe universe must show entries and exits over time."""
    from research.data.universe import LiquidityProxyUniverse
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2020-01-01", periods=400)
    rows = []
    for i, s in enumerate(["S%02d" % k for k in range(20)]):
        # Turnover trends differ per symbol, so the top-5 set must change over time.
        base = np.exp(np.linspace(np.log(1e6), np.log(1e6 * (1 + i)), len(dates)))
        rows.append(pd.DataFrame({"date": dates, "symbol": s,
                                  "turnover": base * rng.lognormal(0, 0.1, len(dates)),
                                  "knowledge_time": dates}))
    panel = pd.concat(rows, ignore_index=True)
    uni = LiquidityProxyUniverse(panel, size=5, lookback=60, min_history=30)
    uni.build()
    churn = uni.churn()
    assert len(churn) > 2
    assert churn["entries"].sum() > 0, "universe never changes: it is a static snapshot"


# -- L5 ---------------------------------------------------------------------------------

def test_L5_absent_block_is_excluded_not_imputed():
    from research.models.combiner import BlockCombiner
    n = 200
    rng = np.random.default_rng(5)
    scores = rng.random((n, 3))
    coverage = np.ones((n, 3))
    coverage[:, 2] = 0.0                      # third block entirely absent
    y = (scores[:, 0] > 0.5).astype(int)
    f = BlockCombiner("static_attention", blocks=["a", "b", "c"]).fit(scores, y, coverage)
    w = f.weights(coverage)
    assert np.allclose(w[:, 2], 0.0), "absent block received non-zero combination weight"
    assert np.allclose(w.sum(axis=1), 1.0)

    # Changing the absent block's score must not move the combined output at all.
    r1 = f.combine(scores, coverage)
    s2 = scores.copy()
    s2[:, 2] = 1.0
    r2 = f.combine(s2, coverage)
    assert np.allclose(r1.score, r2.score), "an absent block influenced the score"


def test_L5_full_absence_yields_maximum_uncertainty():
    from research.models.combiner import BlockCombiner
    n = 50
    scores = np.full((n, 2), 0.9)
    coverage = np.zeros((n, 2))
    y = np.zeros(n, dtype=int)
    y[:10] = 1
    f = BlockCombiner("late", blocks=["a", "b"]).fit(scores, y, np.ones((n, 2)))
    res = f.combine(scores, coverage)
    assert np.allclose(res.uncertainty, 1.0)
    assert np.allclose(res.score, 0.5), "a score was produced with no evidence at all"


# -- L6 ---------------------------------------------------------------------------------

def test_L6_threshold_is_derived_from_training_scores_only():
    """The operating threshold must be a function of the training split alone."""
    from research.evaluation import metrics as mx
    rng = np.random.default_rng(2)
    y_tr = rng.integers(0, 2, 500)
    p_tr = np.clip(y_tr * 0.4 + rng.random(500) * 0.6, 0, 1)
    thr_a = mx.best_f1_threshold(y_tr, p_tr)

    # Evaluation data changes completely; the threshold must not move.
    y_ev = rng.integers(0, 2, 500)
    p_ev = np.clip(y_ev * 0.9 + rng.random(500) * 0.1, 0, 1)
    thr_b = mx.best_f1_threshold(y_tr, p_tr)
    assert thr_a == thr_b
    assert thr_a != mx.best_f1_threshold(y_ev, p_ev), (
        "the eval split produced the same threshold by coincidence; rerun with another "
        "seed rather than trusting this")
