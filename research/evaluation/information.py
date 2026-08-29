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

PLAIN ENGLISH -- what this whole file is about:

WHY DID REMOVING THAT INGREDIENT CHANGE NOTHING?

The ablation table tells you that removing the trading-detail family barely hurt the
score. Fine -- but WHY? There are four completely different explanations, and they call
for four completely different responses:

  1. It genuinely knows nothing useful.              -> Drop it. It is dead weight.
  2. It knows useful things -- that another family
     ALREADY KNOWS. (This is REDUNDANCY.)            -> Keep as a backup; expect no gain.
  3. It knows things and actively DISAGREES with
     the others.                                     -> Investigate. Somebody is wrong.
  4. It was mostly MISSING from the data.            -> Not its fault. Untested, not
                                                        useless.

An ablation table alone cannot tell these apart -- all four look like "removing it made no
difference". This file separates them.

THE TWO KEY MEASUREMENTS:
  TOTAL  -- how well does this family do ON ITS OWN?
  UNIQUE -- how much is lost when you remove it FROM THE FULL SET?

And the gap between them is the whole insight. A family might score brilliantly alone
(high total) and yet cost nothing to remove (zero unique). That means everything it knows,
somebody else already knew. It is not useless -- it is a duplicate. Very different things.

AND AN ADMISSION WORTH ADMIRING, in the last paragraph of the docstring.

There is a formal mathematical theory for exactly this problem, called partial information
decomposition. It is rigorous and it is the "proper" answer. It also needs far more data
than this project has, so any result from it here would be noise dressed up as rigour.

So this file does the practical version instead -- and says so, plainly, every single time
it appears in the output. Not "we performed an information decomposition", which would be
technically defensible and misleading, but "here is an operational approximation, and here
is what it is not."
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version.
INFORMATION_VERSION = "information-v1"


# The rare-event-friendly score, used throughout this file.
def _auprc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import average_precision_score
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    # Too few rows, or only one kind of answer: no meaningful score exists. Say unknown.
    if ok.sum() < 10 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], p[ok]))


# Build the four-way breakdown.
def decomposition(per_arm: dict[str, pd.DataFrame], full_arm: str = "FULL",
                  block_arms: dict[str, tuple[str, str]] | None = None,
                  coverage: dict[str, float] | None = None,
                  threshold: float = 0.5) -> pd.DataFrame:
    """Build the block contribution matrix.

    ``block_arms`` maps a block name to ``(only_arm, without_arm)``. Both arms
    must be present in ``per_arm``; a missing arm yields NaN rather than a guess.
    """
    # PLAIN ENGLISH: for each family we need two experiments already run -- the one with
    # ONLY that family, and the one with everything EXCEPT it. And if either is missing, the
    # answer is "unknown", never an estimate. An invented figure here would sit in the table
    # looking exactly like a measured one.
    if full_arm not in per_arm:
        raise KeyError("full arm %r missing from per-arm scores" % full_arm)
    full = per_arm[full_arm]
    y_full = full["is_episode"].to_numpy(int)
    # How well the complete system does. Everything below is measured against this.
    auprc_full = _auprc(y_full, full["integrity_risk"].to_numpy(float))

    rows = []
    for mod, (only_arm, without_arm) in (block_arms or {}).items():
        # `.get` hands back None for a missing experiment rather than crashing.
        only = per_arm.get(only_arm)
        without = per_arm.get(without_arm)
        # TOTAL: how well this family does entirely alone.
        total = _auprc(only["is_episode"].to_numpy(int),
                       only["integrity_risk"].to_numpy(float)) if only is not None \
            else np.nan
        # How well everything ELSE does without it.
        auprc_without = _auprc(without["is_episode"].to_numpy(int),
                               without["integrity_risk"].to_numpy(float)) \
            if without is not None else np.nan
        # UNIQUE: what is genuinely lost by removing it. This is the number that matters
        # most, because it measures the contribution ON TOP OF everything else, which is the
        # only contribution that is actually available to be had.
        unique = auprc_full - auprc_without if np.isfinite(auprc_without) else np.nan

        # Conflict: the block's own score disagrees with the combined decision.
        # PLAIN ENGLISH: how often does this family shout "trouble!" while the combined
        # verdict says "calm", or the reverse? A high rate is genuinely interesting -- it
        # means this family is seeing something the others are not, or is simply wrong.
        # Either way it is worth a look, and neither would show up in the score at all.
        conflict = np.nan
        col = "score_%s" % mod
        if col in full.columns:
            own = full[col].to_numpy(float)
            fused = full["integrity_risk"].to_numpy(float)
            ok = np.isfinite(own) & np.isfinite(fused)
            # Need a reasonable number of rows for the rate to mean anything.
            if ok.sum() > 20:
                # `!=` on two True/False columns is True wherever they disagree; the mean of
                # those is the disagreement rate.
                conflict = float(np.mean((own[ok] >= threshold)
                                         != (fused[ok] >= threshold)))

        # REDUNDANT: what it knows that others also know. Total minus unique -- everything
        # it can do, less the part only it can do.
        redundant = (total - unique) if (np.isfinite(total) and np.isfinite(unique)) \
            else np.nan
        rows.append({
            "block": mod,
            "total_auprc": total,
            "unique": unique,
            # Floored at zero, because a negative redundancy is meaningless -- it is an
            # artefact of measurement noise rather than a real quantity.
            "redundant": max(0.0, redundant) if np.isfinite(redundant) else np.nan,
            # But the UNFLOORED value is kept too. That is careful: a strongly negative raw
            # value is a signal that something is odd, and flooring it everywhere would hide
            # the evidence of the problem along with the problem.
            "redundant_raw": redundant,
            "conflict_rate": conflict,
            # How often this family's evidence was simply absent. The fourth explanation.
            "missing_rate": (1.0 - coverage.get(mod, np.nan)) if coverage else np.nan,
            # The underlying scores, so a reader can recompute the subtraction themselves.
            "auprc_full": auprc_full,
            "auprc_without": auprc_without,
        })
    out = pd.DataFrame(rows)
    if len(out):
        # Most genuinely useful family first.
        out = out.sort_values("unique", ascending=False).reset_index(drop=True)
    return out


# Does the model know when it does not know?
def selective_risk(y: np.ndarray, p: np.ndarray, uncertainty: np.ndarray,
                   coverages: tuple[float, ...] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,
                                                   0.3, 0.2)) -> pd.DataFrame:
    """Risk on the most-certain fraction of rows.

    Selective risk is the error rate among retained predictions. A model whose
    uncertainty is informative should show risk falling as coverage falls; a flat curve
    means the uncertainty ranks nothing useful.
    """
    # PLAIN ENGLISH: this is the sharpest possible test of a model's self-knowledge, and it
    # is beautifully simple.
    # Sort every prediction by how confident the model claimed to be. Now answer only the
    # 20% it was most sure about. Is it more accurate on those?
    #   IF YES -- the confidence means something real. You could genuinely use it to decide
    #     which cases to trust automatically and which to hand to a human.
    #   IF THE LINE IS FLAT -- the model is equally wrong on the cases it was sure about as
    #     on the ones it was unsure about. Its confidence is decoration. And note this test
    #     would catch that even if every other measure in the project looked excellent.
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    u = np.asarray(uncertainty, dtype=float)
    ok = np.isfinite(p) & np.isfinite(u)
    y, p, u = y[ok], p[ok], u[ok]
    order = np.argsort(u)                      # most certain first
    rows = []
    n = len(y)
    for c in coverages:
        # Take the most confident c% -- but never fewer than 20 rows, or the error rate
        # would be pure noise.
        k = max(20, int(n * c))
        idx = order[:k]
        yy, pp = y[idx], p[idx]
        # Only one kind of answer left: nothing to measure.
        if len(np.unique(yy)) < 2:
            continue
        thr = 0.5
        pred = (pp >= thr).astype(int)
        rows.append({
            "coverage": c,
            "n": int(k),
            # The error rate among the kept predictions. This should FALL as we keep fewer
            # and fewer, if the confidence is worth anything.
            "selective_risk": float(np.mean(pred != yy)),
            "auprc": _auprc(yy, pp),
            # Included because a shifting positive rate can move the error rate all by
            # itself, and without this column a reader could mistake that for the model
            # improving.
            "positive_rate": float(yy.mean()),
        })
    return pd.DataFrame(rows)


# Is the model equally honest in every situation?
def calibration_by_bucket(df: pd.DataFrame, bucket_col: str, y_col: str = "is_episode",
                          p_col: str = "integrity_risk", n_buckets: int = 5,
                          min_rows: int = 100) -> pd.DataFrame:
    """ECE and Brier within buckets of an exogenous variable (e.g. coverage).

    Buckets with fewer than ``min_rows`` observations are reported with a status rather
    than a number, because an ECE computed on 30 rows is noise.
    """
    # PLAIN ENGLISH: a model can be honest ON AVERAGE while being badly overconfident in a
    # particular situation -- say, whenever half its evidence is missing. The overall figure
    # would hide that completely. Splitting by situation is what reveals it.
    from research.evaluation.metrics import expected_calibration_error

    d = df[[bucket_col, y_col, p_col]].dropna()
    if d.empty:
        return pd.DataFrame()
    vals = d[bucket_col].to_numpy(float)
    uniq = np.unique(vals)
    # A variable with fewer distinct values than requested buckets cannot be bucketed:
    # quantile edges collapse into duplicates and the resulting "trend" is an artifact of
    # the binning, not a property of the data. Say so rather than fit a line to it.
    # PLAIN ENGLISH: a genuinely subtle trap. If the variable only ever takes two values, and
    # you insist on five buckets, several buckets end up with identical boundaries. Rows then
    # get counted into more than one bucket, and a smooth-looking "trend" appears across the
    # chart -- entirely manufactured by the binning. It would look like a discovery.
    if len(uniq) < 3:
        return pd.DataFrame([{"bucket_low": float(uniq.min()),
                              "bucket_high": float(uniq.max()),
                              "n": int(len(d)), "ece": np.nan, "brier": np.nan,
                              "auprc": np.nan,
                              # And the refusal states its own reason, so a reader sees why
                              # the row is blank rather than assuming a bug.
                              "status": "NOT MEASURABLE: only %d distinct values"
                                        % len(uniq)}])
    if len(uniq) <= n_buckets:
        # Discrete variable: group by exact value. Interval edges over discrete values
        # overlap at the boundaries and count the same rows into two buckets, which is
        # how a spurious trend appears.
        # PLAIN ENGLISH: if the variable only takes a handful of exact values, do not draw
        # ranges around them at all -- just group by the value itself. Then a row belongs to
        # exactly one bucket and cannot be counted twice.
        rows = []
        from research.evaluation.metrics import expected_calibration_error as _ece
        for v in uniq:
            sel = d[d[bucket_col] == v]
            # Too little data, or only one kind of answer: report the shortage rather than a
            # number computed from thirty rows.
            if len(sel) < min_rows or sel[y_col].nunique() < 2:
                rows.append({"bucket_low": float(v), "bucket_high": float(v),
                             "n": int(len(sel)), "ece": np.nan, "brier": np.nan,
                             "auprc": np.nan, "status": "INSUFFICIENT DATA"})
                continue
            y = sel[y_col].to_numpy(int)
            p = sel[p_col].to_numpy(float)
            rows.append({"bucket_low": float(v), "bucket_high": float(v),
                         "n": int(len(sel)), "ece": _ece(y, p),
                         # Brier: the average squared error of the probabilities. Lower is
                         # better, and it punishes confident mistakes hardest of all.
                         "brier": float(np.mean((p - y) ** 2)),
                         "auprc": _auprc(y, p), "status": "OK"})
        return pd.DataFrame(rows)
    # A genuinely continuous variable: cut it at quantiles, so each bucket holds a similar
    # number of rows. `np.unique` removes any duplicate edges before they can cause trouble.
    edges = np.unique(np.quantile(vals, np.linspace(0, 1, n_buckets + 1)))
    # Even after that, too few distinct edges to form buckets. Refuse, with the reason.
    if len(edges) < 3:
        return pd.DataFrame([{"bucket_low": float(vals.min()),
                              "bucket_high": float(vals.max()),
                              "n": int(len(d)), "ece": np.nan, "brier": np.nan,
                              "auprc": np.nan,
                              "status": "NOT MEASURABLE: degenerate quantile edges"}])
    rows = []
    # Remember which ranges we have already done, so an identical pair cannot slip through.
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
