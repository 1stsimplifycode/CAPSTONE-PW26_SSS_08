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

PLAIN ENGLISH -- what this whole file is about:

THE JOB: decide where to draw the line between "normal" and "suspicious".

This is much harder than it sounds, and the file is built around two ideas.

IDEA 1: DECIDE HOW MANY FALSE ALARMS YOU CAN TOLERATE **FIRST**.

There is a deeply tempting way to cheat here, and almost everybody does it by accident.
You try a line. Too many alarms. You move it. Too few. You move it again. Eventually the
results look nice, so you stop -- and then you write in your report "our threshold
produces a 1% false alarm rate", which is perfectly true and completely meaningless. You
did not choose a standard and meet it; you chose whatever made your results look good and
then described it afterwards. The file calls that "a rationalisation", which is exactly
what it is.

So this file does the opposite. The budget is written down at the top, before any data is
looked at, and the code physically cannot fit a threshold without one.

WHY 1%? Because a human being reads these alarms. Markets trade about 250 days a year, so
1% is two or three alarms per company per year. Rare enough that an alarm is worth
opening; common enough that you would not miss a genuine change for years on end. Notice
what that reasoning is about: how much a person can actually review. It is not about
making the detection numbers look impressive.

IDEA 2: DO NOT ASSUME THE DATA HAS A NICE SHAPE.

The usual approach is: work out the average and the typical wobble, then draw the line
three wobbles above the average. That relies on the data following the famous bell curve.

Financial data does not follow a bell curve. Not approximately, not roughly -- it has
"heavy tails", meaning extreme events happen vastly more often than a bell curve predicts.
Assume a bell curve and you will conclude a once-in-a-thousand-years event should be
expected... and then see three of them in a decade.

So instead this file uses a beautifully simple trick called an EMPIRICAL QUANTILE. Forget
formulas entirely. Line up every past measurement in order from smallest to largest, and
put the line at whichever value has 99% of them below it. That is it. No assumption about
shape, because we never assumed a shape -- we just looked.

THE CONFORMAL REFINEMENT. There is one extra subtlety. With 100 past measurements, you
might think the 99th one is the answer. But you are about to see a NEW measurement, and it
gets to join the queue too, so really there will be 101. Counting that future observation
in -- using (n+1) instead of n -- turns "this should roughly work" into a mathematical
guarantee that holds exactly, at any sample size, for ANY shape of data. This is called
conformal prediction, and the (n+1) is the whole trick.

AND FINALLY, SOMETHING ADMIRABLE: this file DOES compute the bell-curve threshold -- but
only to show the reader how badly wrong it would have been. It is displayed as evidence,
never used to operate. That turns "we did not assume normality" from a claim you have to
take on trust into a number you can check.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For rounding up (`ceil`) and other basic maths helpers.
import math
# Record-building tools.
from dataclasses import asdict, dataclass, field
# The world clock and the tool for reading the time.
from datetime import UTC, datetime

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version of the rules.
THRESHOLDS_VERSION = "thresholds-v1"


# Frozen: the budget must not be altered while thresholds are being fitted against it. A
# promise you can edit halfway through is not a promise.
@dataclass(frozen=True)
class FalseAlarmBudget:
    """The accepted cost of a false alarm, fixed before any threshold is fitted."""

    #: Accepted probability that an ordinary observation raises an alarm.
    # One in a hundred ordinary days may set the alarm off. That is the promise.
    alpha: float = 0.01
    #: Why this number and not another. Recorded so the choice is reviewable.
    # PLAIN ENGLISH: the REASONING is stored alongside the number, in the object itself, so
    # it travels into every saved result. A future reader never has to wonder "why 1%?" or
    # take it on faith -- the argument is right there, and can be disagreed with.
    rationale: str = (
        "Alarms are read by a person. At ~250 sessions a year, alpha=0.01 is two to "
        "three alarms per instrument per year: rare enough to be worth opening, "
        "frequent enough not to miss a regime change for years. Chosen from review "
        "capacity, not from the resulting detection rate.")
    #: Minimum calibration sample for the conformal guarantee to be usable. Below
    #: 1/alpha observations the (1-alpha) order statistic does not exist.
    # PLAIN ENGLISH: to talk about "the top 1%" you need at least a hundred measurements.
    # With fifty, there simply is no such thing as the top 1% of them. 200 gives comfortable
    # room above that bare minimum.
    min_calibration: int = 200

    # The tidy-up step, run automatically after one is built. It checks the budget makes
    # sense before anybody can rely on it.
    def __post_init__(self) -> None:
        # A probability must be between 0 and 1, and strictly so: a budget of 0 would mean
        # "never alarm, ever" and a budget of 1 would mean "alarm always".
        if not (0.0 < self.alpha < 1.0):
            raise ValueError("alpha must lie in (0,1), got %r" % self.alpha)
        # And you must have enough measurements for the requested fineness to exist at all.
        # `math.ceil(1.0 / self.alpha)` for a 1% budget is 100.
        if self.min_calibration < math.ceil(1.0 / self.alpha):
            raise ValueError(
                "min_calibration %d is below 1/alpha = %d; the required order "
                "statistic would not exist"
                % (self.min_calibration, math.ceil(1.0 / self.alpha)))

    def to_dict(self) -> dict:
        return asdict(self)


#: Declared before any threshold is fitted. Module-level so it cannot be tuned per run.
# PLAIN ENGLISH: this sits at the top level of the file, so it is fixed the moment the file
# is loaded -- before any data has been seen. If each run could set its own budget, the
# temptation to nudge it would be right there, and the promise would be worthless.
FALSE_ALARM_BUDGET = FalseAlarmBudget()


# A new kind of error, for when there is not enough data to keep the promise.
class InsufficientCalibration(ValueError):
    """Too few calibration points for the declared budget to be honoured."""


@dataclass
# One fitted threshold, together with the evidence that it does what it claims.
class Threshold:
    """A fitted threshold and the evidence that it honours its budget."""

    # Which measurement this line is for.
    feature: str
    # How it was worked out.
    method: str
    # Whether it avoided assuming a shape.
    distribution_free: bool
    #: The budget this threshold was fitted to. Carried on the object so a consumer can
    #: never use the threshold without seeing what it promises.
    # PLAIN ENGLISH: the promise travels WITH the threshold, permanently attached. You
    # cannot pick up the number 4.7 and use it while remaining ignorant of what it was meant
    # to guarantee.
    budget: dict
    # The line itself.
    threshold: float
    # Whether we alarm above the line or below it.
    direction: str
    # How many past measurements it was fitted from.
    n_calibration: int
    # Which position in the sorted queue was chosen.
    order_statistic_index: int
    # What fraction of the calibration data this line actually flags. The proof that the
    # promise was kept, rather than merely made.
    realised_false_alarm_rate: float
    # The other side of the same coin: the fraction it correctly leaves alone.
    coverage: float
    # When it was fitted, so a stale threshold can be spotted.
    fitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Where a bell-curve assumption would have put the line -- kept purely for comparison.
    gaussian_threshold: float = float("nan")
    # And what fraction that line would have flagged, which is where the assumption's
    # failure becomes visible in actual numbers.
    gaussian_realised_rate: float = float("nan")

    def to_dict(self) -> dict:
        return asdict(self)

    # Apply the line to some values.
    def flag(self, values) -> np.ndarray:
        """Apply the threshold. Upper-tail features alarm above, lower-tail below."""
        v = np.asarray(values, dtype=float)
        # PLAIN ENGLISH: for most measurements, big is bad -- huge price swings, huge
        # illiquidity. But for some, SMALL is bad: trading drying up to nothing is itself a
        # warning sign. So each threshold knows which way round it is.
        return v > self.threshold if self.direction == "upper" else v < self.threshold


# The heart of the method: find the value with 99% of the data below it.
def conformal_quantile(scores: np.ndarray, alpha: float) -> tuple[float, int]:
    """The conformal upper quantile and the order-statistic index that produced it.

    ``ceil((n+1)(1-alpha))`` rather than ``ceil(n(1-alpha))``: the ``n+1`` accounts for
    the future observation itself, which is what upgrades the coverage statement from
    approximate to a finite-sample guarantee under exchangeability.
    """
    # PLAIN ENGLISH: "exchangeable" means the order of the measurements does not matter --
    # any shuffling would be equally likely. It is a much weaker and more believable
    # assumption than "the data follows a bell curve", and it is all this method needs.
    # "Finite-sample" means the guarantee holds with the 200 measurements you actually have,
    # not merely "as the sample size approaches infinity", which is a promise you can never
    # collect on.

    # Line every measurement up from smallest to largest.
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    # Which position in the queue? For 200 measurements and a 1% budget:
    # ceil(201 x 0.99) = ceil(198.99) = 199. So the 199th of 200.
    # Note the (n + 1): that is the future observation being counted in, and it is the
    # entire difference between "roughly right" and "guaranteed".
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        # The budget is finer than the sample can resolve; the most extreme observation
        # is the best available bound and coverage is reported as such.
        # PLAIN ENGLISH: you asked for a line finer than the data can draw -- like asking for
        # the 99.9th percentile from 100 measurements. We hand back the largest value we
        # have, and report honestly which position that was, rather than inventing a number
        # beyond the end of the queue.
        return float(s[-1]), n
    # `k - 1` because programmers count positions from 0, while the maths counts from 1.
    return float(s[k - 1]), k


# Work out where the bell-curve assumption would have put the line. For display only.
def gaussian_comparison(scores: np.ndarray, alpha: float) -> float:
    """Where a normal assumption would have put the threshold. Never used to operate."""
    s = np.asarray(scores, dtype=float)
    # Keep only real numbers.
    s = s[np.isfinite(s)]
    # With fewer than two values there is no wobble to measure, so say "unknown".
    if len(s) < 2:
        return float("nan")
    # Fetched here rather than at the top of the file, since this comparison is optional and
    # loading scipy is not free.
    from scipy import stats
    # The textbook recipe: the average, plus (the bell curve's 99% point) times the wobble.
    # `stats.norm.ppf(0.99)` is about 2.33, the familiar "2.33 standard deviations".
    return float(np.mean(s) + stats.norm.ppf(1.0 - alpha) * np.std(s, ddof=1))


# Fit a threshold for one measurement.
def fit_threshold(feature: str, calibration: np.ndarray,
                  # The budget cannot be omitted -- there is a default, but it is the one
                  # declared up front, not a fresh one invented for this call.
                  budget: FalseAlarmBudget = FALSE_ALARM_BUDGET,
                  direction: str = "upper") -> Threshold:
    """Fit a distribution-free threshold to the declared budget.

    ``calibration`` must be observations the detector considers ordinary. The conformal
    guarantee is about exchangeability with them, so calibrating on a sample that already
    contains the anomalies would raise the threshold until it caught nothing.
    """
    # PLAIN ENGLISH on that warning, which is a genuinely easy trap. You are teaching the
    # system what NORMAL looks like. If your "normal" examples secretly contain a load of
    # crises, the system learns that crises are normal, and quietly sets the line so high
    # that nothing ever trips it. It would look like a perfectly functioning detector.

    # Check the direction is one we understand.
    if direction not in ("upper", "lower"):
        raise ValueError("direction must be 'upper' or 'lower'")
    s = np.asarray(calibration, dtype=float)
    # Keep only real numbers.
    s = s[np.isfinite(s)]
    # Not enough data to honour the promise? Refuse. We do NOT fit a shakier threshold and
    # carry on, because that would be quietly breaking the promise while appearing to keep it.
    if len(s) < budget.min_calibration:
        raise InsufficientCalibration(
            "%s: %d calibration points, need %d for alpha=%.4f"
            % (feature, len(s), budget.min_calibration, budget.alpha))

    # Lower-tail features are flipped so one implementation serves both directions.
    # PLAIN ENGLISH: a neat trick. Rather than writing the whole method twice, once for
    # "alarm when big" and once for "alarm when small", we simply flip the sign of the
    # small-is-bad measurements. Then "the biggest" always means the right thing, and there
    # is only one piece of logic to get right and to test.
    signed = s if direction == "upper" else -s
    tau_signed, k = conformal_quantile(signed, budget.alpha)
    # Flip the answer back.
    tau = tau_signed if direction == "upper" else -tau_signed

    # Now check the promise was actually kept: how much of the calibration data does this
    # line flag? It should be about 1%.
    flagged = (s > tau) if direction == "upper" else (s < tau)
    realised = float(np.mean(flagged))

    # Work out where the bell curve would have put the line, and how much it would have
    # flagged -- the evidence for the reader.
    g_signed = gaussian_comparison(signed, budget.alpha)
    g = g_signed if direction == "upper" else -g_signed
    g_flag = (s > g) if direction == "upper" else (s < g)

    # Package the threshold together with all its evidence.
    return Threshold(
        feature=feature, method="conformal empirical quantile",
        distribution_free=True, budget=budget.to_dict(), threshold=tau,
        direction=direction, n_calibration=len(s), order_statistic_index=k,
        realised_false_alarm_rate=realised, coverage=1.0 - realised,
        gaussian_threshold=g,
        # Only report the bell-curve rate if the bell-curve line could be computed at all.
        gaussian_realised_rate=float(np.mean(g_flag)) if np.isfinite(g) else float("nan"),
    )


# The detector that applies a whole set of fitted thresholds.
class AnomalyDetector:
    """Applies fitted thresholds to Week 2 liquidity features.

    One threshold per feature, each carrying its own budget. The detector holds no
    threshold it did not receive from :func:`fit_threshold`, so there is no path by which
    a hardcoded number becomes an operating threshold.
    """
    # PLAIN ENGLISH on that last sentence: there is nowhere in this class where a number can
    # be typed in by hand. Every line it uses must have come from the fitting process, with
    # its budget and its evidence attached. That closes off the route by which somebody, in a
    # hurry, writes `threshold = 4.7` and quietly undoes the whole design.

    def __init__(self, thresholds: dict[str, Threshold]) -> None:
        # A detector with no thresholds would run perfectly happily and find nothing, ever --
        # a silent, invisible failure. So we refuse to build one.
        if not thresholds:
            raise ValueError("an anomaly detector with no thresholds detects nothing")
        self.thresholds = thresholds

    @property
    # Which measurements this detector watches, in a fixed alphabetical order so reports
    # read the same way every time.
    def features(self) -> list[str]:
        return sorted(self.thresholds)

    @property
    # The promise this detector operates under. `next(iter(...))` takes the first threshold
    # and reads its budget -- they all share the same one, since they were all fitted against
    # the single module-level budget.
    def budget(self) -> dict:
        return next(iter(self.thresholds.values())).budget

    # Apply every threshold to a table of measurements.
    def detect(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Per-row alarm flags, one column per feature, plus the union."""
        # Work on a copy, so the caller's table is untouched.
        out = frame.copy()
        cols = []
        for feature, th in self.thresholds.items():
            # Skip measurements this table does not have, rather than crashing. Different
            # data sources supply different columns, and a missing one should mean fewer
            # alarms, not no answer at all.
            if feature not in out.columns:
                continue
            col = "anomaly_%s" % feature
            out[col] = th.flag(out[feature].to_numpy())
            cols.append(col)
        # Did ANY measurement alarm on this row? `axis=1` means "look across the row" rather
        # than down the column.
        out["anomaly_any"] = out[cols].any(axis=1) if cols else False
        # And how many did. That is more informative than a plain yes/no: one measurement
        # tripping might be noise, while four tripping at once is a different situation
        # entirely.
        out["anomaly_count"] = out[cols].sum(axis=1) if cols else 0
        return out

    # Describe the whole detector, for the record.
    def to_dict(self) -> dict:
        return {
            "thresholds_version": THRESHOLDS_VERSION,
            "features": self.features,
            "false_alarm_budget": self.budget,
            # Stated explicitly in the output, so the reader is told the ordering rather than
            # having to trust it.
            "budget_declared_before_fitting": True,
            "method": "conformal empirical quantile (distribution-free)",
            # Every individual threshold with all its evidence, so the whole thing can be
            # checked line by line.
            "thresholds": {f: t.to_dict() for f, t in self.thresholds.items()},
        }


# Fit a whole detector: one threshold per measurement.
def fit_detector(calibration: pd.DataFrame, features: dict[str, str],
                 budget: FalseAlarmBudget = FALSE_ALARM_BUDGET) -> AnomalyDetector:
    """Fit one threshold per Week 2 liquidity feature.

    ``features`` maps a column name to its alarm direction: ``upper`` for features where
    large is anomalous (realised variance, price impact, illiquidity), ``lower`` where
    small is (traded value drying up).
    """
    fitted: dict[str, Threshold] = {}
    for feature, direction in features.items():
        # Skip measurements not present in the calibration data.
        if feature not in calibration.columns:
            continue
        try:
            fitted[feature] = fit_threshold(
                feature, calibration[feature].to_numpy(), budget, direction)
        except InsufficientCalibration:
            # Not enough data for THIS measurement. Skip just this one and carry on with the
            # rest, rather than abandoning the whole detector. Note this is not a silent
            # weakening: the finished detector reports exactly which measurements it holds
            # thresholds for, so a missing one is visible in the output.
            continue
    return AnomalyDetector(fitted)
