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
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

POWER_VERSION = "power-v1"


def _auprc(frame: pd.DataFrame, col: str, y_col: str = "is_episode") -> float:
    from sklearn.metrics import average_precision_score
    y = frame[y_col].to_numpy(int)
    p = frame[col].to_numpy(float)
    ok = np.isfinite(p)
    if ok.sum() < 10 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], p[ok]))


def power_curve(paired: pd.DataFrame, cluster_col: str, col_a: str, col_b: str,
                fractions: tuple[float, ...] = (0.25, 0.4, 0.55, 0.7, 0.85, 1.0),
                b: int = 300, seed: int = 20260818,
                statistic: Callable[[pd.DataFrame, str], float] | None = None
                ) -> pd.DataFrame:
    """Interval half-width for ``stat(col_a) - stat(col_b)`` as clusters are
    subsampled."""
    stat = statistic or _auprc
    rng = np.random.default_rng(seed)
    clusters = paired[cluster_col].dropna().unique()
    groups = {c: g for c, g in paired.groupby(cluster_col)}  # noqa: C416
    n_clusters = len(clusters)
    rows = []
    for frac in fractions:
        k = max(5, int(round(n_clusters * frac)))
        diffs = []
        for _ in range(b):
            pick = rng.choice(clusters, size=k, replace=True)
            sample = pd.concat([groups[c] for c in pick], ignore_index=True)
            try:
                d = stat(sample, col_a) - stat(sample, col_b)
            except Exception:
                continue
            if np.isfinite(d):
                diffs.append(d)
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
            "half_width": float((hi - lo) / 2.0),
            "minimum_detectable_effect": float((hi - lo) / 2.0),
            "n_resamples": int(len(arr)),
            "status": "OK",
        })
    return pd.DataFrame(rows)


def minimum_detectable_effect(paired: pd.DataFrame, cluster_col: str, col_a: str,
                              col_b: str, b: int = 600,
                              seed: int = 20260818) -> dict:
    """Half-width of the paired bootstrap interval at the full cluster count."""
    curve = power_curve(paired, cluster_col, col_a, col_b, fractions=(1.0,), b=b,
                        seed=seed)
    if curve.empty or curve.iloc[0].get("status") != "OK":
        return {"status": "INSUFFICIENT"}
    r = curve.iloc[0]
    return {
        "status": "OK",
        "n_clusters": int(r["n_clusters"]),
        "minimum_detectable_effect": float(r["minimum_detectable_effect"]),
        "observed_difference": float(r["mean_difference"]),
        "informative": bool(abs(r["mean_difference"])
                            > r["minimum_detectable_effect"]),
        "interpretation": (
            "A non-significant difference smaller than the minimum detectable effect is "
            "uninformative, not evidence of no effect."),
    }


def required_clusters_for_effect(curve: pd.DataFrame, target_effect: float) -> dict:
    """Extrapolate how many clusters would be needed to resolve ``target_effect``.

    Uses the half-width's empirical scaling exponent rather than assuming the textbook
    inverse-square-root, because clustering and a moving positive rate both distort it.
    """
    ok = curve[curve.get("status") == "OK"] if "status" in curve.columns else curve
    ok = ok.dropna(subset=["half_width", "n_clusters"])
    if len(ok) < 3:
        return {"status": "INSUFFICIENT"}
    x = np.log(ok["n_clusters"].to_numpy(float))
    y = np.log(ok["half_width"].to_numpy(float))
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= -1e-6:
        return {"status": "NO SCALING",
                "note": "half-width does not shrink with sample size in this range",
                "scaling_exponent": float(slope)}
    needed = float(np.exp((np.log(target_effect) - intercept) / slope))
    return {
        "status": "OK",
        "scaling_exponent": float(slope),
        "textbook_exponent": -0.5,
        "target_effect": float(target_effect),
        "required_clusters": needed,
        "current_clusters": int(ok["n_clusters"].max()),
        "multiple_of_current": float(needed / max(1, ok["n_clusters"].max())),
        "note": ("Extrapolated from the measured scaling of the bootstrap half-width. "
                 "Treat as an order-of-magnitude guide, not a sample-size guarantee."),
    }
