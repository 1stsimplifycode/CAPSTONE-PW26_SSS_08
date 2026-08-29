"""Statistical machinery (spec section 48).

Every function returns a record that names the test it ran, because a p-value without its
test is not a result. Nothing here reports significance without also reporting an effect
size and an interval -- an ablation that moves AUPRC by 0.002 with p = 0.04 is a finding
about sample size, not about modelling.

Resampling respects the dependence structure of the data. Instrument-day rows inside one
episode are not independent, so bootstrap and permutation resampling operate on
**episodes and instruments**, not rows. An iid row bootstrap would shrink every interval
by roughly the square root of the average episode length and manufacture significance.

PLAIN ENGLISH -- what this whole file is about:

THE QUESTION EVERY RESULT MUST ANSWER: "could this just be luck?"

Suppose your new model scores 0.82 and the old one scores 0.80. Better! Or is it? If you
had tested on a different set of companies, might the numbers have come out the other way
round? Statistics is the machinery for answering that, and this file holds it.

THREE RULES THIS FILE ENFORCES.

RULE 1: A P-VALUE ON ITS OWN IS NOT A RESULT.
A "p-value" is the chance of seeing a difference this big if there were really no
difference at all. Small p, so probably real. But on its own it is nearly useless, because
p depends heavily on how much data you have. With enough data, a completely trivial
difference becomes "statistically significant".
The docstring gives the perfect example: a difference of 0.002 with p = 0.04. That passes
the usual significance bar -- and 0.002 is nothing. Nobody would ever act on it. So that
result tells you about your sample size, not about your model. Hence every function here
also reports:
  * the EFFECT SIZE -- how big is the difference, in units a person can judge?
  * the INTERVAL -- what range is the truth plausibly inside?

RULE 2: RESAMPLE THE RIGHT THING. This is the deepest idea in the file.
"Bootstrapping" means: shuffle your data, redo the sum, and repeat thousands of times, to
see how much the answer wobbles. The wobble tells you how much to trust it.
But it only works if the things you shuffle are INDEPENDENT of each other. And here they
are not. One episode of trouble spans forty consecutive days for one company. Those forty
rows are not forty independent pieces of evidence -- they are one event, observed forty
times. They rise and fall together.
Shuffle individual ROWS and the computer thinks it has 40 times more evidence than it
really does. Your interval comes out roughly the square root of 40 -- about six times --
too narrow. Everything looks six times more certain than it is, and results that are pure
noise come out "significant".
The fix: shuffle whole EPISODES, keeping their days glued together. Then one episode
counts as one piece of evidence, which is what it is.

RULE 3: NAME THE TEST IN THE OUTPUT. Every result carries the name of the test that
produced it and a written description of what it did. A number floating free of its method
cannot be checked by anybody.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# `Callable` is a type hint for "an action that can be called"; `Sequence` for "an ordered
# collection you can count and index into".
from collections.abc import Callable, Sequence
# Record-building tools.
from dataclasses import asdict, dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version of the statistics.
STATS_VERSION = "stats-v1"
# How many resamples to do by default. 2,000 is enough for a stable 95% interval, and more
# would cost time without meaningfully changing the answer.
DEFAULT_B = 2000


@dataclass
# The shape every statistical result takes.
class TestResult:
    # Which test was run. Named, so a number can never travel without its method.
    name: str
    # The number that came out.
    statistic: float
    # How likely such a result would be by luck. `| None` because some tests do not produce
    # one, and saying None is more honest than inventing one.
    p_value: float | None
    # How BIG the difference is -- the thing that actually matters.
    effect_size: float | None
    # What kind of effect size it is, so it can be interpreted correctly.
    effect_name: str
    # The plausible range for the truth.
    ci_low: float | None
    ci_high: float | None
    # How confident that range is, usually 0.95 (95%).
    ci_level: float
    # How much data went into it.
    n: int
    # A written description of exactly what was done.
    test_description: str
    # Any extra detail worth keeping.
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# -- intervals ------------------------------------------------------------------------

# Work out a plausible range for a number, respecting the grouping in the data.
def cluster_bootstrap_ci(df: pd.DataFrame, statistic: Callable[[pd.DataFrame], float],
                         cluster_col: str, b: int = DEFAULT_B, level: float = 0.95,
                         seed: int = 20260818) -> TestResult:
    """Percentile bootstrap CI resampling whole clusters with replacement."""
    # PLAIN ENGLISH: a "cluster" is a group of rows that belong together and must be kept
    # together -- one episode, or one company. "With replacement" means after picking a
    # cluster we put it back, so it can be picked again. That is deliberate: it is what
    # simulates "what if we had happened to collect a slightly different sample?".

    rng = np.random.default_rng(seed)
    # Every distinct group.
    clusters = df[cluster_col].dropna().unique()
    # The answer on the real, unshuffled data.
    obs = float(statistic(df))
    boots = []
    # Pre-split into groups once. Doing this inside the loop would repeat the same work two
    # thousand times.
    groups = {c: g for c, g in df.groupby(cluster_col)}  # noqa: C416
    for _ in range(b):
        # Draw the same NUMBER of groups as we really have, but with repeats allowed -- so
        # some appear twice and some not at all. That is exactly the sampling variation we
        # are trying to imitate.
        pick = rng.choice(clusters, size=len(clusters), replace=True)
        # Glue the chosen groups together into a pretend dataset.
        sample = pd.concat([groups[c] for c in pick], ignore_index=True)
        try:
            v = statistic(sample)
        except Exception:
            # A resample can legitimately be unusable -- for instance if it happens to
            # contain only one kind of answer. Skip it rather than crashing the whole run.
            continue
        if np.isfinite(v):
            boots.append(v)
    # Too few usable resamples to say anything? Report that plainly, with p and the interval
    # left as None. It does NOT report a shaky interval that would look just like a good one.
    if len(boots) < 30:
        return TestResult("cluster_bootstrap", obs, None, None, "none", None, None,
                          level, len(df),
                          "cluster bootstrap failed: fewer than 30 usable resamples",
                          {"n_boot": len(boots)})
    a = np.asarray(boots)
    # The interval: the middle 95% of the resampled answers. For 95%, that is everything
    # between the 2.5th and 97.5th percentiles.
    lo, hi = np.percentile(a, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return TestResult(
        "cluster_bootstrap", obs, None, None, "none", float(lo), float(hi), level,
        len(df),
        # The description spells out what was resampled and why, so a reader can see the
        # dependence was handled without having to read the code.
        "percentile bootstrap over %d resamples, resampling whole '%s' clusters with "
        "replacement to respect within-cluster dependence" % (len(a), cluster_col),
        {"n_boot": len(a), "boot_std": float(a.std())})


# -- paired comparison ------------------------------------------------------------------

# Compare two methods on the same data.
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
    # PLAIN ENGLISH: think of two runners racing. If they run on the SAME track on the SAME
    # day, you can compare them directly -- the wind and the weather affected both equally,
    # so they cancel out. If they ran on different days, some of the difference is just the
    # weather, and you would need a far bigger gap before you could call a winner.
    # Both models are being scored on the same companies, so the awkward companies make both
    # look bad together. Comparing them on the same resamples cancels that shared difficulty
    # out, and the interval on the DIFFERENCE is much tighter and much fairer.

    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].dropna().unique()
    groups = {c: g for c, g in df.groupby(cluster_col)}  # noqa: C416
    # The real gap between the two methods.
    obs = float(stat_a(df) - stat_b(df))
    diffs = []
    for _ in range(b):
        pick = rng.choice(clusters, size=len(clusters), replace=True)
        sample = pd.concat([groups[c] for c in pick], ignore_index=True)
        try:
            # THE PAIRING: both methods scored on the SAME resample. That is the whole point.
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
    # PLAIN ENGLISH: if method A really is better, nearly every resample should show a
    # positive gap. If the gap flips sign a lot, the two are indistinguishable. `min(...)`
    # takes whichever side is rarer, and doubling makes it "two-sided" -- we were not
    # committed in advance to which method would win.
    p = 2.0 * min((a <= 0).mean(), (a >= 0).mean())
    # The floor of 1/(n+1) is honesty about resolution: with 2,000 resamples you cannot
    # distinguish anything finer than about 0.0005, so we never report p = 0, which would
    # claim an impossible certainty.
    p = float(min(1.0, max(p, 1.0 / (len(a) + 1))))
    return TestResult(
        "paired_cluster_bootstrap", obs, p, obs, "absolute difference",
        float(lo), float(hi), level, len(df),
        "paired percentile bootstrap over %d resamples of '%s' clusters; p is the "
        "two-sided proportion of resampled differences on the opposite side of zero"
        % (len(a), cluster_col),
        {"n_boot": len(a), "boot_std": float(a.std())})


# Test whether two groups really differ, by shuffling the labels.
def permutation_test(x: np.ndarray, y: np.ndarray, n_perm: int = 5000,
                     seed: int = 20260818,
                     alternative: str = "two-sided") -> TestResult:
    """Difference of means by label permutation, with Cohen's d as the effect size."""
    # PLAIN ENGLISH: a beautifully direct idea. Suppose group X averages higher than group Y.
    # Is that real? Throw all the values into one pot, deal them back out at random into two
    # groups of the same sizes, and see what gap you get. Do that 5,000 times. If the real
    # gap is bigger than nearly all the random ones, it is real. If random shuffling produces
    # gaps that big all the time, it was luck.
    # This assumes nothing at all about the shape of the data, which is why it is trustworthy.

    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    # Keep only real numbers.
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    # Too few to say anything.
    if len(x) < 2 or len(y) < 2:
        return TestResult("permutation", np.nan, None, None, "cohens_d", None, None,
                          0.95, len(x) + len(y), "too few observations")
    # The real gap.
    obs = float(x.mean() - y.mean())
    # Everything in one pot.
    pooled = np.concatenate([x, y])
    n_x = len(x)
    null = np.empty(n_perm)
    for i in range(n_perm):
        # Shuffle the pot, then split it back into the same two sizes and measure the gap.
        rng.shuffle(pooled)
        null[i] = pooled[:n_x].mean() - pooled[n_x:].mean()
    # Count how many random gaps were at least as extreme as the real one.
    if alternative == "two-sided":
        # Either direction counts -- we were not committed to which group would be higher.
        p = (np.abs(null) >= abs(obs)).sum()
    elif alternative == "greater":
        # Only "X higher than Y" counts. Use this only if you predicted the direction BEFORE
        # looking, otherwise it is cheating.
        p = (null >= obs).sum()
    else:
        p = (null <= obs).sum()
    # The +1 on top and bottom means p can never be exactly 0. It is the standard correction,
    # and it is honest: 5,000 shuffles cannot prove something is impossible.
    p = float((p + 1) / (n_perm + 1))
    # Cohen's d: the gap measured in units of the data's own spread. This is the EFFECT SIZE,
    # and it is what makes the result interpretable. Roughly: 0.2 small, 0.5 medium, 0.8 large.
    sd = np.sqrt(((len(x) - 1) * x.var(ddof=1) + (len(y) - 1) * y.var(ddof=1))
                 / max(1, len(x) + len(y) - 2))
    d = float(obs / sd) if sd > 0 else np.nan
    return TestResult("permutation", obs, p, d, "cohens_d", None, None, 0.95,
                      len(x) + len(y),
                      "label-permutation test on the difference of means, %d "
                      "permutations, %s" % (n_perm, alternative),
                      # Both group averages are reported too, so a reader sees the actual
                      # numbers and not just the gap between them.
                      {"n_perm": n_perm, "mean_x": float(x.mean()),
                       "mean_y": float(y.mean())})


# The matched-pairs version of the same idea.
def paired_permutation(diff: np.ndarray, n_perm: int = 5000,
                       seed: int = 20260818) -> TestResult:
    """Sign-flip test for paired differences (the correct null when pairs are matched)."""
    # PLAIN ENGLISH: when each measurement is a matched pair -- the same company under two
    # methods -- shuffling everything into one pot would be wrong, because it would break the
    # pairing that makes the comparison powerful.
    # The right shuffle is: for each pair, randomly flip which method you call "first". If
    # the two methods are really identical, flipping should not matter, and the average
    # difference should hover around zero. That is the "sign-flip" test.

    rng = np.random.default_rng(seed)
    d = np.asarray(diff, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return TestResult("paired_permutation", np.nan, None, None, "mean_difference",
                          None, None, 0.95, len(d), "too few pairs")
    obs = float(d.mean())
    null = np.empty(n_perm)
    for i in range(n_perm):
        # Randomly flip the sign of each difference.
        signs = rng.choice([-1.0, 1.0], size=len(d))
        null[i] = (d * signs).mean()
    p = float(((np.abs(null) >= abs(obs)).sum() + 1) / (n_perm + 1))
    # The effect size: the average difference in units of its own spread.
    eff = float(obs / d.std(ddof=1)) if d.std(ddof=1) > 0 else np.nan
    return TestResult("paired_permutation", obs, p, eff, "standardised_mean_difference",
                      None, None, 0.95, len(d),
                      "sign-flip permutation on paired differences, %d permutations"
                      % n_perm, {"n_perm": n_perm})


# -- multiple testing -------------------------------------------------------------------

# Correct for having run lots of tests at once.
def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> pd.DataFrame:
    """BH step-up FDR control. Returns adjusted p-values and reject flags.

    BH rather than Bonferroni because the ablation family is large and its tests are
    positively dependent (they share data), which is exactly the regime BH is built for.
    """
    # PLAIN ENGLISH: THE MULTIPLE COMPARISONS PROBLEM, and why it matters enormously.
    # If you run one test at the usual 5% bar, you have a 1-in-20 chance of a false alarm.
    # Fine. But run TWENTY tests and you should EXPECT one false alarm even if nothing is
    # real at all. Run a hundred and you will collect five exciting findings from pure noise.
    # This is how a great deal of published science goes wrong, usually with no bad intent.
    # Two standard fixes:
    #   BONFERRONI -- divide the bar by the number of tests. Simple and very strict; on a
    #     large family it becomes so strict that genuine findings get thrown out too.
    #   BENJAMINI-HOCHBERG -- controls the FALSE DISCOVERY RATE instead: "of the things I
    #     call findings, at most 5% should be false". Less brutal, and it is specifically
    #     built for the case where the tests overlap and share data, which is exactly what
    #     happens when many experiments are run on one dataset.

    # Convert to numbers, turning any missing p-value into "unknown".
    p = np.asarray([np.nan if v is None else v for v in p_values], dtype=float)
    ok = np.isfinite(p)
    out = pd.DataFrame({"p_value": p, "adjusted_p": np.nan, "reject": False})
    # Nothing usable at all.
    if ok.sum() == 0:
        return out
    # Sort the usable p-values from smallest to largest.
    idx = np.where(ok)[0]
    order = idx[np.argsort(p[idx])]
    m = len(order)
    adj = np.empty(m)
    prev = 1.0
    # Walk BACKWARDS, from the largest p-value to the smallest. That direction is what makes
    # it a "step-up" procedure.
    for rank in range(m - 1, -1, -1):
        # Each p-value is scaled by (how many tests) / (its position in the ranking). So the
        # smallest p-value gets the harshest scaling and the largest gets none.
        val = p[order[rank]] * m / (rank + 1)
        # `min(prev, val)` enforces monotonicity: an adjusted p-value can never be larger
        # than one further down the list. Without this you could get the nonsensical result
        # that a stronger finding is judged weaker than a lesser one.
        prev = min(prev, val)
        adj[rank] = prev
    out.loc[order, "adjusted_p"] = adj
    # And the verdict, using the ADJUSTED values rather than the raw ones.
    out.loc[order, "reject"] = adj <= alpha
    return out


# Build a table of one metric with intervals, for several methods.
def bootstrap_metric_table(df: pd.DataFrame, metric: Callable[[pd.DataFrame], float],
                           groups: Sequence[str], cluster_col: str,
                           b: int = 1000, seed: int = 20260818) -> pd.DataFrame:
    rows = []
    for g in groups:
        # `"arm"` is the experimental word for one version being compared, like an arm of a
        # medical trial. Fall back to the whole table if there is no arm column.
        sub = df[df["arm"] == g] if "arm" in df.columns else df
        r = cluster_bootstrap_ci(sub, metric, cluster_col, b=b, seed=seed)
        # Every row carries its interval, so no number in the table ever appears without its
        # uncertainty beside it.
        rows.append({"arm": g, "value": r.statistic, "ci_low": r.ci_low,
                     "ci_high": r.ci_high, "n": r.n})
    return pd.DataFrame(rows)


# The version for time series, where nearby days are related.
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
    # PLAIN ENGLISH on blocks: this is Rule 2 again, in its time-series form. Calm markets
    # come in runs and turbulent markets come in runs -- so picking individual days at random
    # would scatter those runs and destroy the very structure that makes the data realistic.
    # Picking blocks of 21 consecutive days (about a trading month) keeps the runs intact.
    # And the second paragraph is a striking piece of research integrity. There is duplicated
    # code elsewhere producing a published number. The tidy instinct is to remove the
    # duplication. But refactoring might shift the published figure in its last decimal, and
    # you must not change a number that has been cited because it made the code neater. So
    # the duplication STAYS, and a test pins the two together, guaranteeing they still agree.

    rng = np.random.default_rng(seed)
    c = np.asarray(control, dtype=float)
    t = np.asarray(treatment, dtype=float)
    # Use whichever series is shorter, so the two stay lined up day for day.
    n = int(min(len(c), len(t)))
    # Need at least two whole blocks for the method to mean anything.
    if n < block * 2:
        return TestResult("moving_block_paired", float("nan"), None, None, "difference",
                          None, None, level, n,
                          "series too short for %d-session blocks" % block, {})
    # The real difference between the two.
    obs = float(statistic(t[:n]) - statistic(c[:n]))
    deltas = []
    for _ in range(b):
        # Pick random starting points, enough blocks to rebuild a series of about the
        # original length.
        starts = rng.integers(0, max(1, n - block), size=max(1, n // block))
        # Build the list of day positions those blocks cover.
        idx = np.concatenate([np.arange(s, min(n, s + block)) for s in starts])
        try:
            # THE PAIRING: exactly the same days used for both arms.
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


# The average of the worst outcomes.
def cvar(series: np.ndarray, alpha: float = 0.05) -> float:
    """Mean of the worst ``alpha`` tail.

    Written once so that every caller cuts the tail at the same quantile.
    """
    # PLAIN ENGLISH: CVaR is "Conditional Value at Risk", and it answers "when things go
    # badly, HOW badly?". It takes the worst 5% of days and averages them.
    # It is preferred to the more famous "Value at Risk", which only says where the worst 5%
    # begins and is completely silent about how far beyond that the losses run. CVaR looks
    # inside the tail rather than merely pointing at its entrance.
    # And "written once so that every caller cuts the tail at the same quantile" matters more
    # than it sounds: if one part of the project used the worst 5% and another the worst 1%,
    # their numbers would silently not be comparable.
    a = np.asarray(series, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan")
    # Where the worst 5% begins.
    q = np.percentile(a, alpha * 100)
    # Everything at or below that.
    tail = a[a <= q]
    # Their average, or "unknown" if the tail somehow came out empty.
    return float(tail.mean()) if tail.size else float("nan")
