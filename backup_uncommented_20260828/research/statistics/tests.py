"""Statistical machinery (spec section 48).

Every function returns a record that names the test it ran, because a p-value without its
test is not a result. Nothing here reports significance without also reporting an effect
size and an interval -- an ablation that moves AUPRC by 0.002 with p = 0.04 is a finding
about sample size, not about modelling.

Resampling respects the dependence structure of the data. Instrument-day rows inside one
episode are not independent, so bootstrap and permutation resampling operate on
**episodes and instruments**, not rows. An iid row bootstrap would shrink every interval
by roughly the square root of the average episode length and manufacture significance.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

STATS_VERSION = "stats-v1"
DEFAULT_B = 2000


@dataclass
class TestResult:
    name: str
    statistic: float
    p_value: float | None
    effect_size: float | None
    effect_name: str
    ci_low: float | None
    ci_high: float | None
    ci_level: float
    n: int
    test_description: str
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# -- intervals ------------------------------------------------------------------------

def cluster_bootstrap_ci(df: pd.DataFrame, statistic: Callable[[pd.DataFrame], float],
                         cluster_col: str, b: int = DEFAULT_B, level: float = 0.95,
                         seed: int = 20260818) -> TestResult:
    """Percentile bootstrap CI resampling whole clusters with replacement."""
    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].dropna().unique()
    obs = float(statistic(df))
    boots = []
    groups = {c: g for c, g in df.groupby(cluster_col)}  # noqa: C416
    for _ in range(b):
        pick = rng.choice(clusters, size=len(clusters), replace=True)
        sample = pd.concat([groups[c] for c in pick], ignore_index=True)
        try:
            v = statistic(sample)
        except Exception:
            continue
        if np.isfinite(v):
            boots.append(v)
    if len(boots) < 30:
        return TestResult("cluster_bootstrap", obs, None, None, "none", None, None,
                          level, len(df),
                          "cluster bootstrap failed: fewer than 30 usable resamples",
                          {"n_boot": len(boots)})
    a = np.asarray(boots)
    lo, hi = np.percentile(a, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return TestResult(
        "cluster_bootstrap", obs, None, None, "none", float(lo), float(hi), level,
        len(df),
        "percentile bootstrap over %d resamples, resampling whole '%s' clusters with "
        "replacement to respect within-cluster dependence" % (len(a), cluster_col),
        {"n_boot": len(a), "boot_std": float(a.std())})


# -- paired comparison ------------------------------------------------------------------

def paired_bootstrap_difference(df: pd.DataFrame,
                                stat_a: Callable[[pd.DataFrame], float],
                                stat_b: Callable[[pd.DataFrame], float],
                                cluster_col: str, b: int = DEFAULT_B,
                                level: float = 0.95,
                                seed: int = 20260818) -> TestResult:
    """CI and two-sided p for ``stat_a - stat_b`` on the *same* resampled clusters.

    Pairing matters: two models evaluated on the same rows share the sampling noise of
    those rows, and an unpaired comparison throws that away, widening the interval for no
    reason.
    """
    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].dropna().unique()
    groups = {c: g for c, g in df.groupby(cluster_col)}  # noqa: C416
    obs = float(stat_a(df) - stat_b(df))
    diffs = []
    for _ in range(b):
        pick = rng.choice(clusters, size=len(clusters), replace=True)
        sample = pd.concat([groups[c] for c in pick], ignore_index=True)
        try:
            d = stat_a(sample) - stat_b(sample)
        except Exception:
            continue
        if np.isfinite(d):
            diffs.append(d)
    if len(diffs) < 30:
        return TestResult("paired_cluster_bootstrap", obs, None, None, "difference",
                          None, None, level, len(df),
                          "insufficient usable resamples", {"n_boot": len(diffs)})
    a = np.asarray(diffs)
    lo, hi = np.percentile(a, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    # Two-sided bootstrap p: how often the resampled difference crosses zero.
    p = 2.0 * min((a <= 0).mean(), (a >= 0).mean())
    p = float(min(1.0, max(p, 1.0 / (len(a) + 1))))
    return TestResult(
        "paired_cluster_bootstrap", obs, p, obs, "absolute difference",
        float(lo), float(hi), level, len(df),
        "paired percentile bootstrap over %d resamples of '%s' clusters; p is the "
        "two-sided proportion of resampled differences on the opposite side of zero"
        % (len(a), cluster_col),
        {"n_boot": len(a), "boot_std": float(a.std())})


def permutation_test(x: np.ndarray, y: np.ndarray, n_perm: int = 5000,
                     seed: int = 20260818,
                     alternative: str = "two-sided") -> TestResult:
    """Difference of means by label permutation, with Cohen's d as the effect size."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    if len(x) < 2 or len(y) < 2:
        return TestResult("permutation", np.nan, None, None, "cohens_d", None, None,
                          0.95, len(x) + len(y), "too few observations")
    obs = float(x.mean() - y.mean())
    pooled = np.concatenate([x, y])
    n_x = len(x)
    null = np.empty(n_perm)
    for i in range(n_perm):
        rng.shuffle(pooled)
        null[i] = pooled[:n_x].mean() - pooled[n_x:].mean()
    if alternative == "two-sided":
        p = (np.abs(null) >= abs(obs)).sum()
    elif alternative == "greater":
        p = (null >= obs).sum()
    else:
        p = (null <= obs).sum()
    p = float((p + 1) / (n_perm + 1))
    sd = np.sqrt(((len(x) - 1) * x.var(ddof=1) + (len(y) - 1) * y.var(ddof=1))
                 / max(1, len(x) + len(y) - 2))
    d = float(obs / sd) if sd > 0 else np.nan
    return TestResult("permutation", obs, p, d, "cohens_d", None, None, 0.95,
                      len(x) + len(y),
                      "label-permutation test on the difference of means, %d "
                      "permutations, %s" % (n_perm, alternative),
                      {"n_perm": n_perm, "mean_x": float(x.mean()),
                       "mean_y": float(y.mean())})


def paired_permutation(diff: np.ndarray, n_perm: int = 5000,
                       seed: int = 20260818) -> TestResult:
    """Sign-flip test for paired differences (the correct null when pairs are matched)."""
    rng = np.random.default_rng(seed)
    d = np.asarray(diff, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return TestResult("paired_permutation", np.nan, None, None, "mean_difference",
                          None, None, 0.95, len(d), "too few pairs")
    obs = float(d.mean())
    null = np.empty(n_perm)
    for i in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(d))
        null[i] = (d * signs).mean()
    p = float(((np.abs(null) >= abs(obs)).sum() + 1) / (n_perm + 1))
    eff = float(obs / d.std(ddof=1)) if d.std(ddof=1) > 0 else np.nan
    return TestResult("paired_permutation", obs, p, eff, "standardised_mean_difference",
                      None, None, 0.95, len(d),
                      "sign-flip permutation on paired differences, %d permutations"
                      % n_perm, {"n_perm": n_perm})


# -- multiple testing -------------------------------------------------------------------

def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> pd.DataFrame:
    """BH step-up FDR control. Returns adjusted p-values and reject flags.

    BH rather than Bonferroni because the ablation family is large and its tests are
    positively dependent (they share data), which is exactly the regime BH is built for.
    """
    p = np.asarray([np.nan if v is None else v for v in p_values], dtype=float)
    ok = np.isfinite(p)
    out = pd.DataFrame({"p_value": p, "adjusted_p": np.nan, "reject": False})
    if ok.sum() == 0:
        return out
    idx = np.where(ok)[0]
    order = idx[np.argsort(p[idx])]
    m = len(order)
    adj = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        val = p[order[rank]] * m / (rank + 1)
        prev = min(prev, val)
        adj[rank] = prev
    out.loc[order, "adjusted_p"] = adj
    out.loc[order, "reject"] = adj <= alpha
    return out


def bootstrap_metric_table(df: pd.DataFrame, metric: Callable[[pd.DataFrame], float],
                           groups: Sequence[str], cluster_col: str,
                           b: int = 1000, seed: int = 20260818) -> pd.DataFrame:
    rows = []
    for g in groups:
        sub = df[df["arm"] == g] if "arm" in df.columns else df
        r = cluster_bootstrap_ci(sub, metric, cluster_col, b=b, seed=seed)
        rows.append({"arm": g, "value": r.statistic, "ci_low": r.ci_low,
                     "ci_high": r.ci_high, "n": r.n})
    return pd.DataFrame(rows)


def moving_block_paired_delta(control: np.ndarray, treatment: np.ndarray,
                              statistic: Callable[[np.ndarray], float],
                              block: int = 21, b: int = 2000,
                              level: float = 0.95,
                              seed: int = 20260818) -> TestResult:
    """Interval on ``statistic(treatment) - statistic(control)`` for two paired series.

    Daily returns are autocorrelated, so resampling individual days would treat a run of
    correlated sessions as independent evidence and produce an interval that is far too
    narrow. Blocks of ``block`` consecutive sessions are resampled instead, and the *same*
    block indices are applied to both arms because the two arms are the same days under
    two policies — breaking that pairing would discard the shared sampling noise and widen
    the interval for no reason.

    ``scripts/generate_paper_artifacts.py`` carries an inline equivalent of this routine
    for the headline capital-consequence figure. It is deliberately left where it is: its
    output is a protected artifact the claim ledger cites, and refactoring it to call this
    would be a change to a published number with no scientific justification.
    ``tests/unit/test_scenario.py`` pins the two together by checking that this function
    reproduces that artifact's interval.
    """
    rng = np.random.default_rng(seed)
    c = np.asarray(control, dtype=float)
    t = np.asarray(treatment, dtype=float)
    n = int(min(len(c), len(t)))
    if n < block * 2:
        return TestResult("moving_block_paired", float("nan"), None, None, "difference",
                          None, None, level, n,
                          "series too short for %d-session blocks" % block, {})
    obs = float(statistic(t[:n]) - statistic(c[:n]))
    deltas = []
    for _ in range(b):
        starts = rng.integers(0, max(1, n - block), size=max(1, n // block))
        idx = np.concatenate([np.arange(s, min(n, s + block)) for s in starts])
        try:
            d = statistic(t[idx]) - statistic(c[idx])
        except Exception:
            continue
        if np.isfinite(d):
            deltas.append(float(d))
    if len(deltas) < 30:
        return TestResult("moving_block_paired", obs, None, None, "difference",
                          None, None, level, n, "insufficient usable resamples",
                          {"n_boot": len(deltas)})
    a = np.asarray(deltas)
    lo, hi = np.percentile(a, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    p = 2.0 * min((a <= 0).mean(), (a >= 0).mean())
    return TestResult(
        "moving_block_paired", obs, float(min(1.0, max(p, 1.0 / (len(a) + 1)))),
        obs, "absolute difference", float(lo), float(hi), level, n,
        "moving-block bootstrap (%d-session blocks, %d resamples) on the paired daily "
        "series; the same block indices are applied to both arms" % (block, len(a)),
        {"n_boot": len(a), "block": block, "boot_std": float(a.std())})


def cvar(series: np.ndarray, alpha: float = 0.05) -> float:
    """Mean of the worst ``alpha`` tail.

    Written once so that every caller cuts the tail at the same quantile.
    """
    a = np.asarray(series, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan")
    q = np.percentile(a, alpha * 100)
    tail = a[a <= q]
    return float(tail.mean()) if tail.size else float("nan")
