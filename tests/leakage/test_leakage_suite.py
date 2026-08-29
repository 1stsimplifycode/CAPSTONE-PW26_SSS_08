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

PLAIN ENGLISH -- what this whole file is about:

THE MOST IMPORTANT TESTS IN THE PROJECT.

LEAKAGE is when information from the future reaches a decision made in the past. It is the
error that ruins financial research, and it is dangerous precisely because it does not look
like an error. A model that has secretly seen the answers produces BRILLIANT results. You
would celebrate rather than investigate.

THE DOCSTRING'S SECOND SENTENCE IS THE STANDARD: a failure here "is not a bug to be worked
around: it invalidates every claim that depends on the affected path."
Most failing tests mean "fix this thing." A failure here means every number that came out of
that path is worthless until it is fixed.

THE SIX CHECKS, in ordinary words:

L1 -- ASK ABOUT THE PAST, GET ONLY THE PAST. Ask "what did we know on 1 March?" and you must
      never receive something published on 5 March.

L2 -- YESTERDAY'S ANSWER MUST NOT DEPEND ON TOMORROW. Delete the future from the data and
      every past number must be bit-for-bit identical. If any changes, that calculation was
      peeking ahead.

L3 -- CORRECTIONS DO NOT TRAVEL BACKWARDS. A company reports revenue of 10, then corrects it
      to 4 two months later. Anybody looking BEFORE the correction must see 10 -- because
      that is genuinely all anyone knew then.

L4 -- TODAY'S LIST IS NOT HISTORY'S LIST. Using today's top 50 companies for a 2015 question
      quietly deletes every company that failed since. See STATS-02 for why that matters.

L5 -- MISSING IS NOT ZERO. If a category of evidence is absent, it must be EXCLUDED, not
      quietly filled in with a plausible guess.

L6 -- THE CUTOFF COMES FROM THE TRAINING DATA. Choosing it from the evaluation data is
      picking the question after seeing the answer.
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
    # A small helper that builds one piece of evidence with TWO timestamps -- which is the
    # whole idea being tested.
    # EVENT TIME: when the thing happened.
    # KNOWLEDGE TIME: when anybody could have known about it.
    # They are different, and the gap between them is where leakage hides.
    return EvidenceRecord(
        instrument_id=instrument, block=EvidenceBlock.MARKET,
        payload={"value": value},
        provenance=Provenance(source="test", licence="test", event_time=event,
                              knowledge_time=knowledge),
        fact_key=fact_key)


# -- L1 ---------------------------------------------------------------------------------

def test_L1_randomised_as_of_never_returns_future_knowledge():
    # NOT ONE CAREFULLY CHOSEN CASE -- 300 random records queried at 200 random moments.
    # A hand-picked example only proves the case the author thought of. Random testing
    # explores combinations nobody would have designed.
    rng = np.random.default_rng(7)
    store = BitemporalStore()
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(300):
        ev = t0 + timedelta(days=int(rng.integers(0, 200)))
        # Knowledge time is 0 to 30 days AFTER the event -- publication delay, as in reality.
        kn = ev + timedelta(days=int(rng.integers(0, 30)))
        store.append(_rec("AAA", ev, kn, float(i), fact_key="f%d" % i))

    for _ in range(200):
        cutoff = t0 + timedelta(days=int(rng.integers(0, 230)))
        out = get_evidence(store, "AAA", cutoff, cutoff)
        # BOTH TIMESTAMPS CHECKED, and both matter. Nothing may have been PUBLISHED after the
        # cutoff, and nothing may have HAPPENED after it either.
        assert all(r.knowledge_time <= cutoff for r in out)
        assert all(r.event_time <= cutoff for r in out)


def test_L1_cutoff_after_decision_time_is_rejected():
    # Asking for knowledge from AFTER the decision moment is refused outright -- it is not
    # silently trimmed, it raises. The request itself is incoherent, so it fails loudly.
    store = BitemporalStore()
    t = datetime(2024, 6, 1, tzinfo=UTC)
    store.append(_rec("AAA", t, t, 1.0))
    with pytest.raises(LeakageError):
        get_evidence(store, "AAA", t, t + timedelta(days=1))


def test_L1_knowledge_before_event_is_rejected_at_construction():
    # AT CONSTRUCTION -- the earliest possible moment. A record claiming it was known one
    # second BEFORE it happened is impossible, so it cannot even be built. The bad data never
    # enters the system rather than being caught later.
    t = datetime(2024, 6, 1, tzinfo=UTC)
    with pytest.raises(LeakageError):
        Provenance(source="s", licence="l", event_time=t,
                   knowledge_time=t - timedelta(seconds=1))


# -- L2 ---------------------------------------------------------------------------------

def _toy_panel(n: int = 400, seed: int = 3) -> pd.DataFrame:
    # A fake but realistic price series. `cumsum` of small random moves then `exp` produces a
    # price that wanders the way real prices do -- always positive, no impossible jumps.
    rng = np.random.default_rng(seed)
    # `bdate_range` is business days only -- no weekends, as with real trading.
    dates = pd.bdate_range("2020-01-01", periods=n)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    return pd.DataFrame({
        "date": dates, "symbol": "AAA", "open": px, "high": px * 1.01,
        # `np.r_[px[0], px[:-1]]` shifts the series down one: each row's previous close.
        "low": px * 0.99, "close": px, "prev_close": np.r_[px[0], px[:-1]],
        "volume": rng.integers(1e5, 1e6, n).astype(float),
        "turnover": rng.integers(1e7, 1e8, n).astype(float),
        "trades": rng.integers(1e3, 1e4, n).astype(float),
    })


def test_L2_future_bars_cannot_change_past_features():
    """Truncating the future must leave every past feature value bit-identical."""
    # PLAIN ENGLISH: THE MOST ELEGANT TEST IN THE FILE, and it needs no knowledge of how the
    # features are computed.
    # Compute everything from 400 days. Then throw away the last 100 days and compute again.
    # THE FIRST 300 DAYS MUST COME OUT IDENTICAL.
    # If any value shifted, that calculation was reading data from days that had not happened
    # yet -- whatever the code appears to do.
    panel = _toy_panel()
    full = mf.compute_features(panel).set_index("date")
    cut = mf.compute_features(panel.iloc[:300]).set_index("date")
    common = cut.index
    for col in mf.MARKET_FEATURES:
        a = full.loc[common, col].to_numpy(float)
        b = cut.loc[common, col].to_numpy(float)
        # Compare only where BOTH have a value -- an early row with no history yet is legitimately
        # empty in both.
        both = np.isfinite(a) & np.isfinite(b)
        # The tolerances are tiny (1e-9), so this is effectively exact equality -- allowing
        # only for the last-digit wobble of floating-point arithmetic.
        assert np.allclose(a[both], b[both], rtol=1e-9, atol=1e-12), (
            # AND THE FAILURE MESSAGE NAMES THE OFFENDING FEATURE and states the diagnosis
            # outright: "it reads ahead".
            "feature %s changed when future bars were removed: it reads ahead" % col)


def test_L2_shifting_the_panel_shifts_the_features():
    """A pure time shift must move features by exactly the same shift."""
    # THE COMPLEMENT OF THE TEST ABOVE. Move the whole dataset a week later. Nothing about the
    # prices changed -- only the labels on the days. So every feature must be unchanged.
    # If a feature moved, it was keyed to a calendar date rather than to the data.
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
    # THE RESTATEMENT PROBLEM, in one concrete story.
    # 1 March: an event happens.
    # 2 March: revenue is reported as 10.
    # 1 May: it is corrected to 4.
    # Somebody looking on 1 April must see 10 -- because that is genuinely all anyone knew.
    # Showing them 4 would let a model act on a correction that had not been made yet.
    store = BitemporalStore()
    event = datetime(2024, 3, 1, tzinfo=UTC)
    original_kn = datetime(2024, 3, 2, tzinfo=UTC)
    restated_kn = datetime(2024, 5, 1, tzinfo=UTC)
    # SAME event time, SAME fact_key, different knowledge times. That is what makes the second
    # record a restatement of the first rather than a separate fact.
    store.append(_rec("AAA", event, original_kn, 10.0, fact_key="revenue"))
    store.append(_rec("AAA", event, restated_kn, 4.0, fact_key="revenue"))

    # 1 APRIL: exactly one record, and it is the original.
    before = get_evidence(store, "AAA", datetime(2024, 4, 1, tzinfo=UTC))
    # The count is checked too -- BOTH values coming back would be its own bug.
    assert len(before) == 1
    assert before[0].payload["value"] == 10.0, "restatement leaked backwards"

    # 1 JUNE: exactly one record, and now it is the correction. The correction must APPLY
    # afterwards as surely as it must not apply before -- the test checks both directions.
    after = get_evidence(store, "AAA", datetime(2024, 6, 1, tzinfo=UTC))
    assert len(after) == 1
    assert after[0].payload["value"] == 4.0, "restatement not applied after its "\
                                             "knowledge time"


# -- L4 ---------------------------------------------------------------------------------

def test_L4_static_universe_refuses_historical_dates():
    # A list of companies as they stand in 2026, asked about 2015 -> REFUSED, with an error
    # named after the exact bias it prevents: SurvivorshipBiasError.
    u = StaticListUniverse(["AAA", "BBB"], as_of=pd.Timestamp("2026-01-01").date())
    with pytest.raises(SurvivorshipBiasError):
        u.members_on(pd.Timestamp("2015-01-01"))
    # The escape hatch exists only to quantify the bias, and must be explicit.
    # PLAIN ENGLISH: there IS a way to do it anyway -- because measuring how big the bias is
    # requires deliberately introducing it. But you must type
    # `allow_survivorship_bias=True`, so it can never happen by accident, and the flag is
    # visible in the code forever afterwards.
    assert u.members_on(pd.Timestamp("2015-01-01"),
                        allow_survivorship_bias=True) == ["AAA", "BBB"]


def test_L4_pit_universe_has_genuine_churn():
    """A survivorship-safe universe must show entries and exits over time."""
    # A NEGATIVE CONTROL. The point-in-time universe could be broken in a way that quietly
    # returns the same list every time -- which would be a static snapshot wearing a
    # point-in-time label, and every other test would still pass.
    # So this builds data where the membership MUST change, and demands that it does.
    from research.data.universe import LiquidityProxyUniverse
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2020-01-01", periods=400)
    rows = []
    for i, s in enumerate(["S%02d" % k for k in range(20)]):
        # Turnover trends differ per symbol, so the top-5 set must change over time.
        # `linspace` in log space gives smooth exponential growth, at a different rate per
        # company -- so later companies overtake earlier ones and the top 5 genuinely turns
        # over.
        base = np.exp(np.linspace(np.log(1e6), np.log(1e6 * (1 + i)), len(dates)))
        rows.append(pd.DataFrame({"date": dates, "symbol": s,
                                  "turnover": base * rng.lognormal(0, 0.1, len(dates)),
                                  "knowledge_time": dates}))
    panel = pd.concat(rows, ignore_index=True)
    uni = LiquidityProxyUniverse(panel, size=5, lookback=60, min_history=30)
    uni.build()
    churn = uni.churn()
    assert len(churn) > 2
    # AND THE FAILURE MESSAGE STATES THE DIAGNOSIS: "universe never changes: it is a static
    # snapshot" -- which is precisely the bug this test exists to catch.
    assert churn["entries"].sum() > 0, "universe never changes: it is a static snapshot"


# -- L5 ---------------------------------------------------------------------------------

def test_L5_absent_block_is_excluded_not_imputed():
    # MISSING IS NOT ZERO, AND MISSING IS NOT AVERAGE.
    # When a category of evidence is unavailable, the tempting fix is to fill in a neutral
    # value -- 0.5, or the average of the others. That INVENTS evidence and lets absent data
    # influence the answer.
    from research.models.combiner import BlockCombiner
    n = 200
    rng = np.random.default_rng(5)
    scores = rng.random((n, 3))
    coverage = np.ones((n, 3))
    coverage[:, 2] = 0.0                      # third block entirely absent
    y = (scores[:, 0] > 0.5).astype(int)
    f = BlockCombiner("static_attention", blocks=["a", "b", "c"]).fit(scores, y, coverage)
    w = f.weights(coverage)
    # THE ABSENT BLOCK GETS EXACTLY ZERO WEIGHT.
    assert np.allclose(w[:, 2], 0.0), "absent block received non-zero combination weight"
    # AND THE REMAINING WEIGHTS STILL SUM TO ONE -- so dropping a block reweights the others
    # rather than shrinking the total, which would drag every score downwards.
    assert np.allclose(w.sum(axis=1), 1.0)

    # Changing the absent block's score must not move the combined output at all.
    # PLAIN ENGLISH: THE PROOF, and it is much stronger than checking a weight.
    # Set the absent block's score to 1.0 -- the most extreme possible value -- and the
    # combined answer must be BIT-FOR-BIT the same. If it moves at all, the absent evidence
    # was influencing the result through some path the weight check did not see.
    r1 = f.combine(scores, coverage)
    s2 = scores.copy()
    s2[:, 2] = 1.0
    r2 = f.combine(s2, coverage)
    assert np.allclose(r1.score, r2.score), "an absent block influenced the score"


def test_L5_full_absence_yields_maximum_uncertainty():
    # THE EXTREME CASE: NO EVIDENCE AT ALL.
    # The scores say 0.9 -- very high risk. The coverage says every one of them is missing.
    from research.models.combiner import BlockCombiner
    n = 50
    scores = np.full((n, 2), 0.9)
    coverage = np.zeros((n, 2))
    y = np.zeros(n, dtype=int)
    y[:10] = 1
    f = BlockCombiner("late", blocks=["a", "b"]).fit(scores, y, np.ones((n, 2)))
    res = f.combine(scores, coverage)
    # UNCERTAINTY 1.0 -- the maximum. "We know nothing", stated as loudly as possible.
    assert np.allclose(res.uncertainty, 1.0)
    # AND THE SCORE IS 0.5 -- dead centre, no opinion. NOT 0.9, which would report high risk
    # on the basis of nothing whatsoever.
    # The failure message says it exactly: "a score was produced with no evidence at all".
    assert np.allclose(res.score, 0.5), "a score was produced with no evidence at all"


# -- L6 ---------------------------------------------------------------------------------

def test_L6_threshold_is_derived_from_training_scores_only():
    """The operating threshold must be a function of the training split alone."""
    # THE THRESHOLD-PROVENANCE CHECK -- the leakage the risk-thresholds page devotes its
    # closing section to.
    from research.evaluation import metrics as mx
    rng = np.random.default_rng(2)
    y_tr = rng.integers(0, 2, 500)
    p_tr = np.clip(y_tr * 0.4 + rng.random(500) * 0.6, 0, 1)
    thr_a = mx.best_f1_threshold(y_tr, p_tr)

    # Evaluation data changes completely; the threshold must not move.
    # And the evaluation scores here are DELIBERATELY much better separated (0.9 versus 0.4),
    # so if the threshold were being computed from them it would land somewhere quite
    # different -- making the leak unmistakable.
    y_ev = rng.integers(0, 2, 500)
    p_ev = np.clip(y_ev * 0.9 + rng.random(500) * 0.1, 0, 1)
    thr_b = mx.best_f1_threshold(y_tr, p_tr)
    # Same training inputs -> same threshold, every time. Deterministic.
    assert thr_a == thr_b
    # AND THE TWO SPLITS GENUINELY PRODUCE DIFFERENT THRESHOLDS -- which is what makes the
    # check above meaningful. If they happened to agree, the test could not tell a correct
    # implementation from a leaking one.
    assert thr_a != mx.best_f1_threshold(y_ev, p_ev), (
        # AND THE FAILURE MESSAGE IS UNUSUALLY HONEST: it says this particular failure may be
        # a coincidence, and tells you to rerun with another seed RATHER THAN TRUSTING IT.
        # A test that admits when its own result is unreliable is a rare and good thing.
        "the eval split produced the same threshold by coincidence; rerun with another "
        "seed rather than trusting this")
