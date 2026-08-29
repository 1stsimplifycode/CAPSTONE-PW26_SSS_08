"""C4 -- distribution-free thresholds fitted to a false-alarm budget declared first.

PLAIN ENGLISH -- what this whole file is about:

THE TESTS THAT PROVE THE THRESHOLDS ARE HONEST.

A THRESHOLD turns a measurement into a decision: above this line, raise an alarm. The risk
thresholds page explains the method; THIS FILE CHECKS THE METHOD ACTUALLY DOES WHAT IT CLAIMS.

Three claims are tested, and each one is a claim the project makes publicly:

1. THE BUDGET CAME FIRST. The allowed false-alarm rate was written down before any data was
   looked at. Tested by checking the constant exists with the right value, and that the
   recorded run says `budget_declared_before_fitting: true`.

2. IT IS DISTRIBUTION-FREE. It works whatever shape the data has. Tested by throwing FOUR
   deliberately awkward shapes at it -- including a Pareto, which has a tail so heavy that
   textbook methods fall over.

3. THE SIMPLE ALTERNATIVE REALLY IS WORSE. Not asserted -- MEASURED, in
   `test_a_gaussian_threshold_would_miss_the_budget_on_heavy_tails`, which computes both
   and demands the conformal one be at least three times closer to target.

AND THEN THERE ARE THE NEGATIVE CONTROLS AT THE BOTTOM, which are the cleverest part.
A NEGATIVE CONTROL checks that something WOULD have failed if it were broken. Imagine the
threshold were accidentally hard-coded to a fixed number: every test above would still pass,
because a fixed threshold can still be distribution-free-looking and still honour a budget by
luck. The negative controls catch that by changing the budget and demanding the threshold
MOVE. A hard-coded number would not.
"""
from __future__ import annotations

import numpy as np
import pytest

from research.market import thresholds as T


def test_budget_exists_before_any_data():
    # CLAIM 1, in its simplest form: the budget is a CONSTANT in the code -- fixed, visible,
    # and impossible to have chosen after seeing a result.
    b = T.FALSE_ALARM_BUDGET
    # One false alarm in a hundred.
    assert b.alpha == 0.01
    # AND IT MUST HAVE A REASON. A budget with no rationale is a number somebody picked.
    assert b.rationale and "capacity" in b.rationale
    # THE ARITHMETIC FLOOR: to resolve a 1-in-100 rate you need at least 100 observations.
    # You cannot find the 100th-worst of 50 things.
    assert b.min_calibration >= int(np.ceil(1 / b.alpha))


def test_budget_rejects_impossible_configuration():
    # `pytest.raises` asserts that the code REFUSES. The test passes only if an error is
    # raised -- so silently accepting nonsense would be a failure.
    with pytest.raises(ValueError):
        # A budget of zero false alarms is impossible.
        T.FalseAlarmBudget(alpha=0.0)
    with pytest.raises(ValueError):
        # 150% is not a rate.
        T.FalseAlarmBudget(alpha=1.5)
    with pytest.raises(ValueError):
        # 50 calibration points cannot resolve a 1-in-1000 quantile.
        # PLAIN ENGLISH: the important one. Asking for 1-in-1000 confidence from 50
        # observations is asking for the 50.05th largest of 50 numbers. There is no such
        # thing -- so the code refuses rather than returning something plausible.
        T.FalseAlarmBudget(alpha=0.001, min_calibration=50)


def test_threshold_is_distribution_free_across_shapes():
    """The realised rate must honour the budget whatever the distribution."""
    # CLAIM 2, and this is the test that earns the phrase "distribution-free".
    rng = np.random.default_rng(4)
    budget = T.FalseAlarmBudget(alpha=0.05, min_calibration=200)
    # FOUR DELIBERATELY AWKWARD SHAPES:
    for name, sample in {
        # NORMAL: the friendly bell curve every textbook method assumes.
        "normal": rng.normal(0, 1, 4000),
        # LOGNORMAL: heavily skewed, a long tail to the right.
        "lognormal": rng.lognormal(0, 1.5, 4000),
        # PARETO: extreme values far more common than a bell curve predicts. The shape that
        # breaks naive methods -- and the shape real financial returns actually have.
        "pareto": (rng.pareto(1.5, 4000) + 1),
        # BIMODAL: two separate humps. The "average" sits in the empty gap between them,
        # where nothing ever happens. `np.r_` glues two arrays together.
        "bimodal": np.r_[rng.normal(-4, 0.5, 2000), rng.normal(4, 0.5, 2000)],
    }.items():
        th = T.fit_threshold(name, sample, budget)
        # THE BUDGET IS HONOURED ON ALL FOUR. The trailing `, name` makes a failure report
        # WHICH shape broke it.
        assert th.realised_false_alarm_rate <= budget.alpha + 0.01, name
        assert th.distribution_free is True


def test_a_gaussian_threshold_would_miss_the_budget_on_heavy_tails():
    """Why the parametric route is a comparison and not the method.

    The miss can go either way and here it goes upward: a Pareto sample's standard
    deviation is dominated by its tail, so mean + z*sd lands far above the true 99th
    percentile and the detector fires on almost nothing. Under-firing is a budget failure
    exactly as over-firing is -- the budget is a target, not a ceiling -- so the assertion
    is on the absolute distance from alpha.
    """
    # PLAIN ENGLISH: A GENUINELY SUBTLE POINT, and the docstring explains it properly.
    # The bell-curve method sets its line at "average plus three standard deviations". On a
    # Pareto sample the standard deviation is enormous -- driven entirely by a few extreme
    # values -- so that line lands FAR ABOVE where it should. The detector then fires on
    # almost nothing.
    # AND UNDER-FIRING IS A FAILURE TOO. "The budget is a target, not a ceiling": promising
    # one alarm in a hundred and delivering one in ten thousand means the detector is
    # missing things it was supposed to catch.
    # Which is why the test measures ABSOLUTE DISTANCE from alpha -- wrong in either
    # direction is wrong.
    rng = np.random.default_rng(6)
    alpha = 0.01
    sample = rng.pareto(1.2, 20000) + 1
    th = T.fit_threshold("heavy", sample, T.FalseAlarmBudget(alpha=alpha))
    conformal_miss = abs(th.realised_false_alarm_rate - alpha)
    gaussian_miss = abs(th.gaussian_realised_rate - alpha)
    # The method used lands very close to target.
    assert conformal_miss < 0.002
    # AND THE ALTERNATIVE MISSES BY AT LEAST THREE TIMES AS MUCH. So the choice of method is
    # demonstrated rather than asserted -- and the failure message prints both numbers, so a
    # reader can see the actual comparison rather than only "assertion failed".
    assert gaussian_miss > 3 * conformal_miss, (
        "conformal %.4f vs gaussian %.4f against alpha %.3f"
        % (th.realised_false_alarm_rate, th.gaussian_realised_rate, alpha))


def test_conformal_index_uses_the_n_plus_one_correction():
    # THE "+1" THAT MAKES THE GUARANTEE EXACT.
    # 100 observations, and the index used is ceil(101 x 0.95) -- one hundred and ONE.
    # That extra 1 counts the FUTURE observation you are trying to make a promise about. It
    # is what turns "approximately" into a guarantee that holds at any sample size.
    # Off-by-one errors are invisible in output and silently break the guarantee, so this
    # gets its own test.
    tau, k = T.conformal_quantile(np.arange(100, dtype=float), 0.05)
    assert k == int(np.ceil(101 * 0.95))


def test_insufficient_calibration_refuses_rather_than_guesses():
    # THE NAME OF THIS TEST IS THE PRINCIPLE. Given 50 points and asked for a 1-in-100
    # threshold, the code raises a specific, named error -- InsufficientCalibration -- rather
    # than returning the closest thing it can find.
    # A returned approximation would look exactly like a real threshold and quietly break the
    # promise attached to it.
    with pytest.raises(T.InsufficientCalibration):
        T.fit_threshold("x", np.arange(50, dtype=float), T.FALSE_ALARM_BUDGET)


def test_threshold_carries_its_budget(rv_table):
    # `rv_table` is a fixture from conftest.py -- pytest supplies it automatically. This runs
    # against REAL data.
    th = T.fit_threshold("realised_variance",
                         rv_table["realised_variance"].to_numpy())
    # THE THRESHOLD CARRIES ITS OWN PROVENANCE: the budget it was fitted to, the reason for
    # that budget, and the method used. So a threshold can never be found on its own with no
    # way to tell where it came from.
    assert th.budget["alpha"] == T.FALSE_ALARM_BUDGET.alpha
    assert th.budget["rationale"]
    assert th.method == "conformal empirical quantile"


def test_detector_applies_thresholds_to_week2_liquidity_features(rv_table):
    """The threshold must operate on a Week 2 market feature, not only a risk score."""
    # PLAIN ENGLISH: it is easy to build machinery that only works on the one number it was
    # designed around. This checks it works on an actual market measurement -- realised
    # variance -- end to end.
    det = T.fit_detector(rv_table, {"realised_variance": "upper"})
    assert det.features == ["realised_variance"]
    out = det.detect(rv_table)
    assert "anomaly_realised_variance" in out.columns
    # AND THE ALARM RATE ON REAL DATA HONOURS THE BUDGET.
    rate = float(out["anomaly_any"].mean())
    assert rate <= T.FALSE_ALARM_BUDGET.alpha + 0.005


def test_the_real_run_honours_its_budget(summary):
    # NOT A FRESH CALCULATION -- THIS READS THE RECORD OF THE ACTUAL PIPELINE RUN.
    # Everything above proves the method is sound. This proves the real run used it.
    t = summary["c4_thresholds"]
    # THE CLAIM THAT MATTERS MOST, checked as a machine-readable flag rather than trusted as
    # prose: the budget was declared BEFORE fitting.
    assert t["budget_declared_before_fitting"] is True
    assert t["false_alarm_budget"]["alpha"] == 0.01
    assert "conformal" in t["method"]
    applied = t["applied_to"]
    assert applied["realised_rate"] <= 0.015
    # AND IT ACTUALLY FIRED. A detector that never raises an alarm would honour any budget
    # perfectly and be completely useless -- so "more than zero" is checked too.
    assert applied["anomalies"] > 0


def test_stress_gate_threshold_is_distribution_free(summary):
    # The same three checks applied to the second threshold in the real run.
    g = summary["c4_thresholds"]["stress_gate_threshold"]
    assert g["distribution_free"] is True
    assert g["method"] == "conformal empirical quantile"
    assert g["budget"]["alpha"] == 0.01


# -- negative controls ------------------------------------------------------------------
# PLAIN ENGLISH: THE CLEVEREST TESTS IN THE FILE.
# A normal test asks "does it work?" A NEGATIVE CONTROL asks "would we NOTICE if it were
# broken?"
# Suppose somebody accidentally hard-coded the threshold to a fixed number. Every test above
# could still pass. These three catch exactly that.

def test_changing_the_declared_budget_changes_the_threshold(rv_table):
    """The budget must drive selection. A fixed threshold would not move."""
    # DEMAND STRICTER, GET A HIGHER BAR. Demand looser, get a lower one. A hard-coded value
    # would sit still and fail here.
    x = rv_table["realised_variance"].to_numpy()
    tight = T.fit_threshold("rv", x, T.FalseAlarmBudget(alpha=0.001,
                                                        min_calibration=1000))
    loose = T.fit_threshold("rv", x, T.FalseAlarmBudget(alpha=0.10))
    assert tight.threshold > loose.threshold
    # AND THE CONSEQUENCE FOLLOWS TOO: the stricter threshold really does fire less often.
    assert tight.realised_false_alarm_rate < loose.realised_false_alarm_rate


def test_budget_change_propagates_to_the_detector(rv_table):
    # THE SAME CHECK ONE LEVEL UP. The threshold moving is not enough -- the DETECTOR that
    # uses it must change its behaviour too. A detector ignoring the threshold it was handed
    # would pass the previous test and fail this one.
    tight = T.fit_detector(rv_table, {"realised_variance": "upper"},
                           T.FalseAlarmBudget(alpha=0.001, min_calibration=1000))
    loose = T.fit_detector(rv_table, {"realised_variance": "upper"},
                           T.FalseAlarmBudget(alpha=0.10))
    n_tight = int(tight.detect(rv_table)["anomaly_any"].sum())
    n_loose = int(loose.detect(rv_table)["anomaly_any"].sum())
    assert n_loose > n_tight


def test_mean_plus_sigma_is_not_what_is_used(rv_table):
    """A symmetric band on a skewed feature would miss the budget; ours does not."""
    # THE TEST THAT PROVES THE SHORTCUT WAS NOT TAKEN, on real data.
    # `mean + 3*std` is the classic textbook line. It is symmetric, and realised variance is
    # anything but -- it cannot go below zero and has a long tail above.
    x = rv_table["realised_variance"].to_numpy()
    naive = float(np.mean(x) + 3 * np.std(x, ddof=1))
    th = T.fit_threshold("rv", x, T.FALSE_ALARM_BUDGET)
    # First: the two are genuinely different numbers, so the naive rule is definitely not
    # what is running underneath. `pytest.approx` allows for floating-point wobble.
    assert th.threshold != pytest.approx(naive)
    naive_rate = float(np.mean(x > naive))
    # AND SECOND, THE STRONGER CLAIM: the method used lands CLOSER TO TARGET than the naive
    # one on this real data. Different AND better, both measured.
    assert abs(th.realised_false_alarm_rate - 0.01) < abs(naive_rate - 0.01)


def test_a_detector_with_no_thresholds_is_refused():
    # A detector built with no thresholds at all would detect nothing, forever, silently --
    # and every alarm-rate check would pass perfectly. So constructing one is refused
    # outright.
    with pytest.raises(ValueError):
        T.AnomalyDetector({})
