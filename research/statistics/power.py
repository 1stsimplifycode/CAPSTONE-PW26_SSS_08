"""Empirical power analysis for clustered rare-event comparisons (L-12).

A non-significant difference is only informative if the study could have detected a
difference worth caring about. This module answers that with resampling rather than a
parametric formula, because the parametric route would need a distributional assumption
the clustered episode structure does not support.

Method: subsample episodes to a target count, recompute the paired metric difference on a
bootstrap of that subsample, and record the interval half-width. The half-width at the
full episode count is the **minimum detectable effect** at that count: any observed
difference smaller than it cannot be distinguished from zero, whatever the p-value
happens to be.

PLAIN ENGLISH -- what this whole file is about:

THE QUESTION NOBODY ASKS, AND ALWAYS SHOULD: "could I have found it even if it were
there?"

Picture looking for a needle in a haystack with a metal detector that only works on
things bigger than a spoon. You sweep the whole haystack and find nothing. What have you
learned? Absolutely nothing about needles. Your detector could never have found one.

Now the research version. You test whether your improvement helps. The result is "not
significant". Everyone nods and concludes it does not help.

BUT WAIT. What is the smallest difference your study could possibly have detected? If the
answer is "0.05", and your improvement is worth 0.02, then your study was NEVER capable of
seeing it. "Not significant" means nothing here. It is the spoon-only metal detector.

This file measures the size of your spoon. It works out the MINIMUM DETECTABLE EFFECT: the
smallest difference this study could tell apart from zero. And then the crucial sentence:

    "A non-significant difference smaller than the minimum detectable effect is
     uninformative, not evidence of no effect."

Read that twice. "We found no effect" and "we could not have found an effect" look
identical in a results table, and mean completely opposite things.

HOW IT IS MEASURED: by experiment, not by formula. The textbook approach plugs numbers
into an equation -- but that equation assumes your data points are independent, and here
they are not (the episodes again). So instead this file just DOES it: take a quarter of
the episodes, measure how wobbly the answer is. Then 40%, then 55%, and so on up to all of
them. That builds a curve showing exactly how the precision improves with more data, from
this actual dataset, with no assumptions borrowed from a textbook.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# A type hint for "an action that can be called".
from collections.abc import Callable

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version.
POWER_VERSION = "power-v1"


# The default measure of how good a set of predictions is.
def _auprc(frame: pd.DataFrame, col: str, y_col: str = "is_episode") -> float:
    from sklearn.metrics import average_precision_score
    # PLAIN ENGLISH: AUPRC means "Area Under the Precision-Recall Curve". It is the right
    # measure when the thing you are hunting for is RARE. If only 1 in 100 days has trouble,
    # a model that says "no trouble" every single time is 99% accurate and utterly useless.
    # AUPRC ignores that trick entirely and asks only how well you find the rare cases.
    y = frame[y_col].to_numpy(int)
    p = frame[col].to_numpy(float)
    ok = np.isfinite(p)
    # Refuse to answer with fewer than ten usable rows, or when every row has the same
    # answer -- in either case the number would be meaningless rather than merely imprecise.
    if ok.sum() < 10 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], p[ok]))


# Build the curve: how precise is the answer at different amounts of data?
def power_curve(paired: pd.DataFrame, cluster_col: str, col_a: str, col_b: str,
                # The fractions of the data to try: a quarter, then 40%, and so on up to
                # everything. Several points are needed to see the SHAPE of the improvement.
                fractions: tuple[float, ...] = (0.25, 0.4, 0.55, 0.7, 0.85, 1.0),
                b: int = 300, seed: int = 20260818,
                statistic: Callable[[pd.DataFrame, str], float] | None = None
                ) -> pd.DataFrame:
    """Interval half-width for ``stat(col_a) - stat(col_b)`` as clusters are
    subsampled."""
    # Use the supplied measure, or AUPRC by default.
    stat = statistic or _auprc
    rng = np.random.default_rng(seed)
    clusters = paired[cluster_col].dropna().unique()
    groups = {c: g for c, g in paired.groupby(cluster_col)}  # noqa: C416
    n_clusters = len(clusters)
    rows = []
    for frac in fractions:
        # How many episodes at this step. `max(5, ...)` keeps a floor, since an interval
        # from two episodes would be pure noise.
        k = max(5, int(round(n_clusters * frac)))
        diffs = []
        for _ in range(b):
            # Draw that many whole episodes, keeping their days glued together.
            pick = rng.choice(clusters, size=k, replace=True)
            sample = pd.concat([groups[c] for c in pick], ignore_index=True)
            try:
                # Both methods scored on the same resample -- the pairing again.
                d = stat(sample, col_a) - stat(sample, col_b)
            except Exception:
                continue
            if np.isfinite(d):
                diffs.append(d)
        # Not enough usable resamples at this size. Record the failure honestly and move on
        # rather than dropping the row, so the gap is visible in the curve.
        if len(diffs) < 30:
            rows.append({"fraction": frac, "n_clusters": k, "status": "INSUFFICIENT"})
            continue
        arr = np.asarray(diffs)
        lo, hi = np.percentile(arr, [2.5, 97.5])
        rows.append({
            "fraction": frac,
            "n_clusters": k,
            "mean_difference": float(arr.mean()),
            "ci_low": float(lo),
            "ci_high": float(hi),
            # THE KEY NUMBER: half the width of the interval. A narrower interval means a
            # sharper study.
            "half_width": float((hi - lo) / 2.0),
            # The same number under the name that says what it MEANS: the smallest difference
            # this much data could distinguish from zero. Recording it twice, under both
            # names, means a reader meets the interpretation without having to know that a
            # half-width is one.
            "minimum_detectable_effect": float((hi - lo) / 2.0),
            "n_resamples": int(len(arr)),
            "status": "OK",
        })
    return pd.DataFrame(rows)


# The headline number: how small a difference could this study have seen?
def minimum_detectable_effect(paired: pd.DataFrame, cluster_col: str, col_a: str,
                              col_b: str, b: int = 600,
                              seed: int = 20260818) -> dict:
    """Half-width of the paired bootstrap interval at the full cluster count."""
    # Just the one point on the curve: all the data.
    curve = power_curve(paired, cluster_col, col_a, col_b, fractions=(1.0,), b=b,
                        seed=seed)
    if curve.empty or curve.iloc[0].get("status") != "OK":
        return {"status": "INSUFFICIENT"}
    r = curve.iloc[0]
    return {
        "status": "OK",
        "n_clusters": int(r["n_clusters"]),
        # The smallest difference we could have detected.
        "minimum_detectable_effect": float(r["minimum_detectable_effect"]),
        # The difference we actually saw.
        "observed_difference": float(r["mean_difference"]),
        # THE VERDICT THAT MATTERS. Is what we saw bigger than the smallest thing we could
        # have seen? If not, the study simply could not answer the question, and no amount
        # of staring at the p-value will change that.
        "informative": bool(abs(r["mean_difference"])
                            > r["minimum_detectable_effect"]),
        # And the warning spelled out, carried in the result itself so it reaches whoever
        # reads the output rather than only whoever reads the code.
        "interpretation": (
            "A non-significant difference smaller than the minimum detectable effect is "
            "uninformative, not evidence of no effect."),
    }


# How much more data would we need to settle the question?
def required_clusters_for_effect(curve: pd.DataFrame, target_effect: float) -> dict:
    """Extrapolate how many clusters would be needed to resolve ``target_effect``.

    Uses the half-width's empirical scaling exponent rather than assuming the textbook
    inverse-square-root, because clustering and a moving positive rate both distort it.
    """
    # PLAIN ENGLISH: the textbook says precision improves with the square root of sample
    # size -- four times the data for twice the precision. That rule assumes independent
    # observations. Ours are clustered, so the real improvement is slower, and using the
    # textbook rule would produce a cheerfully optimistic answer.
    # So instead we MEASURE the improvement rate from the curve we just built. It is more
    # work and it is the honest number.

    # Keep only the points that worked.
    ok = curve[curve.get("status") == "OK"] if "status" in curve.columns else curve
    ok = ok.dropna(subset=["half_width", "n_clusters"])
    # Need at least three points to fit a trend through.
    if len(ok) < 3:
        return {"status": "INSUFFICIENT"}
    # Take logarithms of both. A relationship like "precision improves as a power of sample
    # size" becomes a straight line once you do that, and the line's slope IS the power.
    x = np.log(ok["n_clusters"].to_numpy(float))
    y = np.log(ok["half_width"].to_numpy(float))
    # Fit the straight line. `1` means a first-degree fit -- a line, not a curve.
    slope, intercept = np.polyfit(x, y, 1)
    # The slope should be NEGATIVE: more data means a narrower interval. If it is not, then
    # in this range more data is not helping at all, and extrapolating would be nonsense.
    # Reporting "no scaling" is far more useful than a confident invented figure.
    if slope >= -1e-6:
        return {"status": "NO SCALING",
                "note": "half-width does not shrink with sample size in this range",
                "scaling_exponent": float(slope)}
    # Rearrange the line to answer "what sample size would give the target precision?".
    needed = float(np.exp((np.log(target_effect) - intercept) / slope))
    return {
        "status": "OK",
        # The measured improvement rate...
        "scaling_exponent": float(slope),
        # ...shown alongside the textbook value, so a reader can see immediately how far
        # reality departs from the assumption most studies quietly make.
        "textbook_exponent": -0.5,
        "target_effect": float(target_effect),
        "required_clusters": needed,
        "current_clusters": int(ok["n_clusters"].max()),
        # How many times more data than we have. Often a sobering number, and expressing it
        # as a multiple makes it immediately graspable -- "we would need 40x more" lands
        # rather harder than a bare count.
        "multiple_of_current": float(needed / max(1, ok["n_clusters"].max())),
        # And the honest caveat attached to the estimate. This is an extrapolation beyond
        # the data we have, so it is a guide to the order of magnitude, not a promise.
        "note": ("Extrapolated from the measured scaling of the bootstrap half-width. "
                 "Treat as an order-of-magnitude guide, not a sample-size guarantee."),
    }
