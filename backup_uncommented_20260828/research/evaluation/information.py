"""Block information decomposition and selective-risk analysis.

Answers the question the ablation table cannot: is a block contributing *unique*
information, merely *re-encoding* what another block already carries, actively
*conflicting*, or simply *missing*?

The decomposition, all measured on the same rows:

``total``      AUPRC of the block on its own
``unique``     AUPRC(all) - AUPRC(all without m). What is lost if m is removed.
``redundant``  total - unique, floored at zero. What m knows that others also know.
``conflict``   share of rows where m's score sits on the opposite side of the operating
               threshold from the fused score
``missing``    1 - coverage

This is not a formal partial-information decomposition -- those require estimating joint
distributions this sample cannot support (see L-12). It is an operational decomposition
in the metric that matters, and it is labelled as such wherever it appears.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

INFORMATION_VERSION = "information-v1"


def _auprc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import average_precision_score
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    if ok.sum() < 10 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], p[ok]))


def decomposition(per_arm: dict[str, pd.DataFrame], full_arm: str = "FULL",
                  block_arms: dict[str, tuple[str, str]] | None = None,
                  coverage: dict[str, float] | None = None,
                  threshold: float = 0.5) -> pd.DataFrame:
    """Build the block contribution matrix.

    ``block_arms`` maps a block name to ``(only_arm, without_arm)``. Both arms
    must be present in ``per_arm``; a missing arm yields NaN rather than a guess.
    """
    if full_arm not in per_arm:
        raise KeyError("full arm %r missing from per-arm scores" % full_arm)
    full = per_arm[full_arm]
    y_full = full["is_episode"].to_numpy(int)
    auprc_full = _auprc(y_full, full["integrity_risk"].to_numpy(float))

    rows = []
    for mod, (only_arm, without_arm) in (block_arms or {}).items():
        only = per_arm.get(only_arm)
        without = per_arm.get(without_arm)
        total = _auprc(only["is_episode"].to_numpy(int),
                       only["integrity_risk"].to_numpy(float)) if only is not None \
            else np.nan
        auprc_without = _auprc(without["is_episode"].to_numpy(int),
                               without["integrity_risk"].to_numpy(float)) \
            if without is not None else np.nan
        unique = auprc_full - auprc_without if np.isfinite(auprc_without) else np.nan

        # Conflict: the block's own score disagrees with the combined decision.
        conflict = np.nan
        col = "score_%s" % mod
        if col in full.columns:
            own = full[col].to_numpy(float)
            fused = full["integrity_risk"].to_numpy(float)
            ok = np.isfinite(own) & np.isfinite(fused)
            if ok.sum() > 20:
                conflict = float(np.mean((own[ok] >= threshold)
                                         != (fused[ok] >= threshold)))

        redundant = (total - unique) if (np.isfinite(total) and np.isfinite(unique)) \
            else np.nan
        rows.append({
            "block": mod,
            "total_auprc": total,
            "unique": unique,
            "redundant": max(0.0, redundant) if np.isfinite(redundant) else np.nan,
            "redundant_raw": redundant,
            "conflict_rate": conflict,
            "missing_rate": (1.0 - coverage.get(mod, np.nan)) if coverage else np.nan,
            "auprc_full": auprc_full,
            "auprc_without": auprc_without,
        })
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("unique", ascending=False).reset_index(drop=True)
    return out


def selective_risk(y: np.ndarray, p: np.ndarray, uncertainty: np.ndarray,
                   coverages: tuple[float, ...] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,
                                                   0.3, 0.2)) -> pd.DataFrame:
    """Risk on the most-certain fraction of rows.

    Selective risk is the error rate among retained predictions. A model whose
    uncertainty is informative should show risk falling as coverage falls; a flat curve
    means the uncertainty ranks nothing useful.
    """
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    u = np.asarray(uncertainty, dtype=float)
    ok = np.isfinite(p) & np.isfinite(u)
    y, p, u = y[ok], p[ok], u[ok]
    order = np.argsort(u)                      # most certain first
    rows = []
    n = len(y)
    for c in coverages:
        k = max(20, int(n * c))
        idx = order[:k]
        yy, pp = y[idx], p[idx]
        if len(np.unique(yy)) < 2:
            continue
        thr = 0.5
        pred = (pp >= thr).astype(int)
        rows.append({
            "coverage": c,
            "n": int(k),
            "selective_risk": float(np.mean(pred != yy)),
            "auprc": _auprc(yy, pp),
            "positive_rate": float(yy.mean()),
        })
    return pd.DataFrame(rows)


def calibration_by_bucket(df: pd.DataFrame, bucket_col: str, y_col: str = "is_episode",
                          p_col: str = "integrity_risk", n_buckets: int = 5,
                          min_rows: int = 100) -> pd.DataFrame:
    """ECE and Brier within buckets of an exogenous variable (e.g. coverage).

    Buckets with fewer than ``min_rows`` observations are reported with a status rather
    than a number, because an ECE computed on 30 rows is noise.
    """
    from research.evaluation.metrics import expected_calibration_error

    d = df[[bucket_col, y_col, p_col]].dropna()
    if d.empty:
        return pd.DataFrame()
    vals = d[bucket_col].to_numpy(float)
    uniq = np.unique(vals)
    # A variable with fewer distinct values than requested buckets cannot be bucketed:
    # quantile edges collapse into duplicates and the resulting "trend" is an artifact of
    # the binning, not a property of the data. Say so rather than fit a line to it.
    if len(uniq) < 3:
        return pd.DataFrame([{"bucket_low": float(uniq.min()),
                              "bucket_high": float(uniq.max()),
                              "n": int(len(d)), "ece": np.nan, "brier": np.nan,
                              "auprc": np.nan,
                              "status": "NOT MEASURABLE: only %d distinct values"
                                        % len(uniq)}])
    if len(uniq) <= n_buckets:
        # Discrete variable: group by exact value. Interval edges over discrete values
        # overlap at the boundaries and count the same rows into two buckets, which is
        # how a spurious trend appears.
        rows = []
        from research.evaluation.metrics import expected_calibration_error as _ece
        for v in uniq:
            sel = d[d[bucket_col] == v]
            if len(sel) < min_rows or sel[y_col].nunique() < 2:
                rows.append({"bucket_low": float(v), "bucket_high": float(v),
                             "n": int(len(sel)), "ece": np.nan, "brier": np.nan,
                             "auprc": np.nan, "status": "INSUFFICIENT DATA"})
                continue
            y = sel[y_col].to_numpy(int)
            p = sel[p_col].to_numpy(float)
            rows.append({"bucket_low": float(v), "bucket_high": float(v),
                         "n": int(len(sel)), "ece": _ece(y, p),
                         "brier": float(np.mean((p - y) ** 2)),
                         "auprc": _auprc(y, p), "status": "OK"})
        return pd.DataFrame(rows)
    edges = np.unique(np.quantile(vals, np.linspace(0, 1, n_buckets + 1)))
    if len(edges) < 3:
        return pd.DataFrame([{"bucket_low": float(vals.min()),
                              "bucket_high": float(vals.max()),
                              "n": int(len(d)), "ece": np.nan, "brier": np.nan,
                              "auprc": np.nan,
                              "status": "NOT MEASURABLE: degenerate quantile edges"}])
    rows = []
    seen: set[tuple[float, float]] = set()
    for lo, hi in zip(edges[:-1], edges[1:]):
        if (float(lo), float(hi)) in seen:
            continue                      # duplicate edge pair: would double-count rows
        seen.add((float(lo), float(hi)))
        sel = d[(d[bucket_col] >= lo) & (d[bucket_col] <= hi)]
        if len(sel) < min_rows or sel[y_col].nunique() < 2:
            rows.append({"bucket_low": float(lo), "bucket_high": float(hi),
                         "n": int(len(sel)), "ece": np.nan, "brier": np.nan,
                         "auprc": np.nan, "status": "INSUFFICIENT DATA"})
            continue
        y = sel[y_col].to_numpy(int)
        p = sel[p_col].to_numpy(float)
        rows.append({
            "bucket_low": float(lo), "bucket_high": float(hi), "n": int(len(sel)),
            "ece": expected_calibration_error(y, p),
            "brier": float(np.mean((p - y) ** 2)),
            "auprc": _auprc(y, p),
            "status": "OK",
        })
    return pd.DataFrame(rows)
