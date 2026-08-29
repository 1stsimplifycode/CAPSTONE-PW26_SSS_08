"""C4 -- distribution-free thresholds fitted to a false-alarm budget declared first."""
from __future__ import annotations

import numpy as np
import pytest

from research.market import thresholds as T


def test_budget_exists_before_any_data():
    b = T.FALSE_ALARM_BUDGET
    assert b.alpha == 0.01
    assert b.rationale and "capacity" in b.rationale
    assert b.min_calibration >= int(np.ceil(1 / b.alpha))


def test_budget_rejects_impossible_configuration():
    with pytest.raises(ValueError):
        T.FalseAlarmBudget(alpha=0.0)
    with pytest.raises(ValueError):
        T.FalseAlarmBudget(alpha=1.5)
    with pytest.raises(ValueError):
        # 50 calibration points cannot resolve a 1-in-1000 quantile.
        T.FalseAlarmBudget(alpha=0.001, min_calibration=50)


def test_threshold_is_distribution_free_across_shapes():
    """The realised rate must honour the budget whatever the distribution."""
    rng = np.random.default_rng(4)
    budget = T.FalseAlarmBudget(alpha=0.05, min_calibration=200)
    for name, sample in {
        "normal": rng.normal(0, 1, 4000),
        "lognormal": rng.lognormal(0, 1.5, 4000),
        "pareto": (rng.pareto(1.5, 4000) + 1),
        "bimodal": np.r_[rng.normal(-4, 0.5, 2000), rng.normal(4, 0.5, 2000)],
    }.items():
        th = T.fit_threshold(name, sample, budget)
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
    rng = np.random.default_rng(6)
    alpha = 0.01
    sample = rng.pareto(1.2, 20000) + 1
    th = T.fit_threshold("heavy", sample, T.FalseAlarmBudget(alpha=alpha))
    conformal_miss = abs(th.realised_false_alarm_rate - alpha)
    gaussian_miss = abs(th.gaussian_realised_rate - alpha)
    assert conformal_miss < 0.002
    assert gaussian_miss > 3 * conformal_miss, (
        "conformal %.4f vs gaussian %.4f against alpha %.3f"
        % (th.realised_false_alarm_rate, th.gaussian_realised_rate, alpha))


def test_conformal_index_uses_the_n_plus_one_correction():
    tau, k = T.conformal_quantile(np.arange(100, dtype=float), 0.05)
    assert k == int(np.ceil(101 * 0.95))


def test_insufficient_calibration_refuses_rather_than_guesses():
    with pytest.raises(T.InsufficientCalibration):
        T.fit_threshold("x", np.arange(50, dtype=float), T.FALSE_ALARM_BUDGET)


def test_threshold_carries_its_budget(rv_table):
    th = T.fit_threshold("realised_variance",
                         rv_table["realised_variance"].to_numpy())
    assert th.budget["alpha"] == T.FALSE_ALARM_BUDGET.alpha
    assert th.budget["rationale"]
    assert th.method == "conformal empirical quantile"


def test_detector_applies_thresholds_to_week2_liquidity_features(rv_table):
    """The threshold must operate on a Week 2 market feature, not only a risk score."""
    det = T.fit_detector(rv_table, {"realised_variance": "upper"})
    assert det.features == ["realised_variance"]
    out = det.detect(rv_table)
    assert "anomaly_realised_variance" in out.columns
    rate = float(out["anomaly_any"].mean())
    assert rate <= T.FALSE_ALARM_BUDGET.alpha + 0.005


def test_the_real_run_honours_its_budget(summary):
    t = summary["c4_thresholds"]
    assert t["budget_declared_before_fitting"] is True
    assert t["false_alarm_budget"]["alpha"] == 0.01
    assert "conformal" in t["method"]
    applied = t["applied_to"]
    assert applied["realised_rate"] <= 0.015
    assert applied["anomalies"] > 0


def test_stress_gate_threshold_is_distribution_free(summary):
    g = summary["c4_thresholds"]["stress_gate_threshold"]
    assert g["distribution_free"] is True
    assert g["method"] == "conformal empirical quantile"
    assert g["budget"]["alpha"] == 0.01


# -- negative controls ------------------------------------------------------------------

def test_changing_the_declared_budget_changes_the_threshold(rv_table):
    """The budget must drive selection. A fixed threshold would not move."""
    x = rv_table["realised_variance"].to_numpy()
    tight = T.fit_threshold("rv", x, T.FalseAlarmBudget(alpha=0.001,
                                                        min_calibration=1000))
    loose = T.fit_threshold("rv", x, T.FalseAlarmBudget(alpha=0.10))
    assert tight.threshold > loose.threshold
    assert tight.realised_false_alarm_rate < loose.realised_false_alarm_rate


def test_budget_change_propagates_to_the_detector(rv_table):
    tight = T.fit_detector(rv_table, {"realised_variance": "upper"},
                           T.FalseAlarmBudget(alpha=0.001, min_calibration=1000))
    loose = T.fit_detector(rv_table, {"realised_variance": "upper"},
                           T.FalseAlarmBudget(alpha=0.10))
    n_tight = int(tight.detect(rv_table)["anomaly_any"].sum())
    n_loose = int(loose.detect(rv_table)["anomaly_any"].sum())
    assert n_loose > n_tight


def test_mean_plus_sigma_is_not_what_is_used(rv_table):
    """A symmetric band on a skewed feature would miss the budget; ours does not."""
    x = rv_table["realised_variance"].to_numpy()
    naive = float(np.mean(x) + 3 * np.std(x, ddof=1))
    th = T.fit_threshold("rv", x, T.FALSE_ALARM_BUDGET)
    assert th.threshold != pytest.approx(naive)
    naive_rate = float(np.mean(x > naive))
    assert abs(th.realised_false_alarm_rate - 0.01) < abs(naive_rate - 0.01)


def test_a_detector_with_no_thresholds_is_refused():
    with pytest.raises(ValueError):
        T.AnomalyDetector({})
