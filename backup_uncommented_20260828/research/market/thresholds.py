"""Distribution-free anomaly thresholds, set from a false-alarm budget declared first.

The budget comes before the data. :data:`FALSE_ALARM_BUDGET` is a module constant, fixed
before any threshold is fitted, and :func:`fit_threshold` cannot be called without one.
That ordering is the criterion: a threshold chosen to make results look good and then
described by its realised false-alarm rate is not a budget, it is a rationalisation.

**Why the budget is 1%.** These alarms are read by a person. Sessions run about 250 a
year, so a 1% budget is roughly two or three alarms per instrument per year -- rare enough
that an alarm is worth opening, frequent enough that a real regime change is not missed
for years. It is a review-capacity number, and it is written down here rather than tuned.

**Why the method is distribution-free.** The threshold is an *empirical quantile* of the
calibration sample::

    tau = Quantile_{1 - alpha}( {s_1, ..., s_n} )

with the conformal finite-sample correction: the order statistic at index
``ceil((n+1)(1-alpha))``. That correction is what makes the guarantee exact rather than
asymptotic -- for exchangeable scores, the probability that a fresh observation exceeds
``tau`` is at most ``alpha`` for *any* underlying distribution. No density is assumed, no
moments are needed, and the guarantee survives the heavy tails and skew that liquidity
features actually have.

What is explicitly *not* used, and why each would fail here:

* **mean +/- k sigma** -- assumes symmetry and finite, well-estimated variance. Amihud
  illiquidity is right-skewed by construction (a ratio with turnover in the denominator),
  so a symmetric band is wrong on both sides at once.
* **Gaussian z-scores** -- assume normality that intraday variance and trade counts
  visibly do not have; the tail probability would be understated by orders of magnitude.
* **a round percentage** -- is not a guarantee about anything.

A Gaussian threshold *is* computed, but only as a labelled comparison in
:func:`gaussian_comparison`, to show how far the parametric assumption would have been
off. It never sets the operating threshold.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

THRESHOLDS_VERSION = "thresholds-v1"


@dataclass(frozen=True)
class FalseAlarmBudget:
    """The accepted cost of a false alarm, fixed before any threshold is fitted."""

    #: Accepted probability that an ordinary observation raises an alarm.
    alpha: float = 0.01
    #: Why this number and not another. Recorded so the choice is reviewable.
    rationale: str = (
        "Alarms are read by a person. At ~250 sessions a year, alpha=0.01 is two to "
        "three alarms per instrument per year: rare enough to be worth opening, "
        "frequent enough not to miss a regime change for years. Chosen from review "
        "capacity, not from the resulting detection rate.")
    #: Minimum calibration sample for the conformal guarantee to be usable. Below
    #: 1/alpha observations the (1-alpha) order statistic does not exist.
    min_calibration: int = 200

    def __post_init__(self) -> None:
        if not (0.0 < self.alpha < 1.0):
            raise ValueError("alpha must lie in (0,1), got %r" % self.alpha)
        if self.min_calibration < math.ceil(1.0 / self.alpha):
            raise ValueError(
                "min_calibration %d is below 1/alpha = %d; the required order "
                "statistic would not exist"
                % (self.min_calibration, math.ceil(1.0 / self.alpha)))

    def to_dict(self) -> dict:
        return asdict(self)


#: Declared before any threshold is fitted. Module-level so it cannot be tuned per run.
FALSE_ALARM_BUDGET = FalseAlarmBudget()


class InsufficientCalibration(ValueError):
    """Too few calibration points for the declared budget to be honoured."""


@dataclass
class Threshold:
    """A fitted threshold and the evidence that it honours its budget."""

    feature: str
    method: str
    distribution_free: bool
    #: The budget this threshold was fitted to. Carried on the object so a consumer can
    #: never use the threshold without seeing what it promises.
    budget: dict
    threshold: float
    direction: str
    n_calibration: int
    order_statistic_index: int
    realised_false_alarm_rate: float
    coverage: float
    fitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    gaussian_threshold: float = float("nan")
    gaussian_realised_rate: float = float("nan")

    def to_dict(self) -> dict:
        return asdict(self)

    def flag(self, values) -> np.ndarray:
        """Apply the threshold. Upper-tail features alarm above, lower-tail below."""
        v = np.asarray(values, dtype=float)
        return v > self.threshold if self.direction == "upper" else v < self.threshold


def conformal_quantile(scores: np.ndarray, alpha: float) -> tuple[float, int]:
    """The conformal upper quantile and the order-statistic index that produced it.

    ``ceil((n+1)(1-alpha))`` rather than ``ceil(n(1-alpha))``: the ``n+1`` accounts for
    the future observation itself, which is what upgrades the coverage statement from
    approximate to a finite-sample guarantee under exchangeability.
    """
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        # The budget is finer than the sample can resolve; the most extreme observation
        # is the best available bound and coverage is reported as such.
        return float(s[-1]), n
    return float(s[k - 1]), k


def gaussian_comparison(scores: np.ndarray, alpha: float) -> float:
    """Where a normal assumption would have put the threshold. Never used to operate."""
    s = np.asarray(scores, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < 2:
        return float("nan")
    from scipy import stats
    return float(np.mean(s) + stats.norm.ppf(1.0 - alpha) * np.std(s, ddof=1))


def fit_threshold(feature: str, calibration: np.ndarray,
                  budget: FalseAlarmBudget = FALSE_ALARM_BUDGET,
                  direction: str = "upper") -> Threshold:
    """Fit a distribution-free threshold to the declared budget.

    ``calibration`` must be observations the detector considers ordinary. The conformal
    guarantee is about exchangeability with them, so calibrating on a sample that already
    contains the anomalies would raise the threshold until it caught nothing.
    """
    if direction not in ("upper", "lower"):
        raise ValueError("direction must be 'upper' or 'lower'")
    s = np.asarray(calibration, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < budget.min_calibration:
        raise InsufficientCalibration(
            "%s: %d calibration points, need %d for alpha=%.4f"
            % (feature, len(s), budget.min_calibration, budget.alpha))

    # Lower-tail features are flipped so one implementation serves both directions.
    signed = s if direction == "upper" else -s
    tau_signed, k = conformal_quantile(signed, budget.alpha)
    tau = tau_signed if direction == "upper" else -tau_signed

    flagged = (s > tau) if direction == "upper" else (s < tau)
    realised = float(np.mean(flagged))

    g_signed = gaussian_comparison(signed, budget.alpha)
    g = g_signed if direction == "upper" else -g_signed
    g_flag = (s > g) if direction == "upper" else (s < g)

    return Threshold(
        feature=feature, method="conformal empirical quantile",
        distribution_free=True, budget=budget.to_dict(), threshold=tau,
        direction=direction, n_calibration=len(s), order_statistic_index=k,
        realised_false_alarm_rate=realised, coverage=1.0 - realised,
        gaussian_threshold=g,
        gaussian_realised_rate=float(np.mean(g_flag)) if np.isfinite(g) else float("nan"),
    )


class AnomalyDetector:
    """Applies fitted thresholds to Week 2 liquidity features.

    One threshold per feature, each carrying its own budget. The detector holds no
    threshold it did not receive from :func:`fit_threshold`, so there is no path by which
    a hardcoded number becomes an operating threshold.
    """

    def __init__(self, thresholds: dict[str, Threshold]) -> None:
        if not thresholds:
            raise ValueError("an anomaly detector with no thresholds detects nothing")
        self.thresholds = thresholds

    @property
    def features(self) -> list[str]:
        return sorted(self.thresholds)

    @property
    def budget(self) -> dict:
        return next(iter(self.thresholds.values())).budget

    def detect(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Per-row alarm flags, one column per feature, plus the union."""
        out = frame.copy()
        cols = []
        for feature, th in self.thresholds.items():
            if feature not in out.columns:
                continue
            col = "anomaly_%s" % feature
            out[col] = th.flag(out[feature].to_numpy())
            cols.append(col)
        out["anomaly_any"] = out[cols].any(axis=1) if cols else False
        out["anomaly_count"] = out[cols].sum(axis=1) if cols else 0
        return out

    def to_dict(self) -> dict:
        return {
            "thresholds_version": THRESHOLDS_VERSION,
            "features": self.features,
            "false_alarm_budget": self.budget,
            "budget_declared_before_fitting": True,
            "method": "conformal empirical quantile (distribution-free)",
            "thresholds": {f: t.to_dict() for f, t in self.thresholds.items()},
        }


def fit_detector(calibration: pd.DataFrame, features: dict[str, str],
                 budget: FalseAlarmBudget = FALSE_ALARM_BUDGET) -> AnomalyDetector:
    """Fit one threshold per Week 2 liquidity feature.

    ``features`` maps a column name to its alarm direction: ``upper`` for features where
    large is anomalous (realised variance, price impact, illiquidity), ``lower`` where
    small is (traded value drying up).
    """
    fitted: dict[str, Threshold] = {}
    for feature, direction in features.items():
        if feature not in calibration.columns:
            continue
        try:
            fitted[feature] = fit_threshold(
                feature, calibration[feature].to_numpy(), budget, direction)
        except InsufficientCalibration:
            continue
    return AnomalyDetector(fitted)
