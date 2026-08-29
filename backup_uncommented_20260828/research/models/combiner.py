"""The block combination layer: turning per-block scores into one calibrated number.

The risk model fits one learner per feature block (market, microstructure, regime,
propagation). This module decides how much each of those calibrated scores counts toward
the final integrity-risk score, and how uncertain that final number is.

Two invariants hold for every combination rule, and both are enforced by the leakage
suite rather than by convention:

* **An absent block is excluded, never imputed.** A block whose coverage is zero on a row
  receives exactly zero weight on that row, so changing its score cannot move the output.
  The alternative -- imputing a neutral 0.5 and letting it dilute the mean -- would let a
  block that was never measured pull the score toward the middle, which reads on the
  interface as evidence of normality rather than as absence of evidence.
* **No evidence produces no score.** When every block is absent the rule returns 0.5 with
  uncertainty 1.0, rather than a confident number derived from nothing.

Uncertainty comes from two measurable sources -- disagreement between the blocks that are
present, and how much of the evidence stack is missing -- not from a learned scalar that
nothing constrains.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Every combination rule this layer implements.
#:
#: ``late``                 equal weight over whichever blocks cover the row.
#: ``static_attention``     one learned weight per block, fixed across rows.
#: ``uncertainty``          static weights scaled by each learner's own confidence.
#: ``regime_inherited``     the inherited formulation: a per-regime term added
#:                          *identically to every block's* logit. Kept as a named
#:                          negative control, because a term that is constant across
#:                          blocks cancels under softmax normalisation -- the rule is
#:                          algebraically identical to ``static_attention`` and cannot
#:                          condition on regime at all. This is the mistake
#:                          ``regime_corrected`` corrects.
#: ``regime_corrected``     a genuinely per-regime, per-block weight vector, applied at
#:                          the row's own regime.
#: ``early``                one learner over the union of features, so this layer has a
#:                          single column to pass through.
STRATEGIES = ("late", "static_attention", "uncertainty", "regime_inherited",
              "regime_corrected", "early")

#: Below this many rows a regime does not get its own weights and falls back to the
#: pooled ones. Fitting six weights on a handful of rows is noise, not conditioning.
MIN_ROWS_PER_REGIME = 100


@dataclass
class CombinedScore:
    """One row per input row: the combined score and what produced it."""

    score: np.ndarray
    uncertainty: np.ndarray
    coverage: np.ndarray
    weights: np.ndarray


def _softmax(z: np.ndarray, axis: int = -1) -> np.ndarray:
    z = z - np.max(z, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / np.clip(e.sum(axis=axis, keepdims=True), 1e-12, None)


@dataclass
class BlockCombiner:
    """Combine per-block scores under one of :data:`STRATEGIES`.

    ``blocks`` names the columns of every ``scores`` array handed to this object, in
    order, so a weight can be reported against the block it belongs to.
    """

    strategy: str = "regime_corrected"
    n_regimes: int = 6
    blocks: list[str] = field(default_factory=list)
    seed: int = 20260818

    #: Pooled per-block logits, shape (n_blocks,). ``None`` until fitted.
    logits_: np.ndarray | None = None
    #: Per-regime, per-block logits, shape (n_regimes, n_blocks). ``regime_corrected``
    #: only.
    regime_logits_: np.ndarray | None = None
    #: Per-regime scalar added to every block's logit. ``regime_inherited`` only.
    regime_offset_: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ValueError("unknown combination strategy %r; expected one of %s"
                             % (self.strategy, ", ".join(STRATEGIES)))

    # -- fit ----------------------------------------------------------------------------

    def fit(self, scores: np.ndarray, y: np.ndarray, coverage: np.ndarray,
            regime: np.ndarray | None = None) -> BlockCombiner:
        """Learn the block weights from the training split alone.

        A block's weight is driven by how well its calibrated score separates the two
        classes *on the rows it actually covers*. Scoring it on rows it does not cover
        would credit or punish it for the neutral 0.5 the learner emits there.
        """
        scores = np.atleast_2d(np.asarray(scores, dtype=float))
        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        y = np.asarray(y).astype(int)
        k = scores.shape[1]

        self.logits_ = self._fit_logits(scores, y, coverage, np.ones(len(y), dtype=bool))

        if self.strategy == "regime_inherited":
            # The inherited formulation adds one term per regime to the softmax
            # numerator, the *same* term for every block. Reproduced here exactly as
            # specified, because the point of keeping this rule is to show that such a
            # term cancels under normalisation and leaves static attention untouched.
            reg = self._regime_index(regime, len(y))
            counts = np.bincount(reg, minlength=self.n_regimes).astype(float)
            with np.errstate(divide="ignore"):
                self.regime_offset_ = np.log(np.clip(counts / max(counts.sum(), 1),
                                                     1e-6, None))
            self.regime_logits_ = None
        elif self.strategy == "regime_corrected":
            reg = self._regime_index(regime, len(y))
            per = np.repeat(self.logits_[None, :], self.n_regimes, axis=0)
            counts = np.bincount(reg, minlength=self.n_regimes)
            for r in range(self.n_regimes):
                sel = reg == r
                if counts[r] >= MIN_ROWS_PER_REGIME and len(np.unique(y[sel])) > 1:
                    per[r] = self._fit_logits(scores, y, coverage, sel)
            self.regime_logits_ = per
        else:
            self.regime_logits_ = None

        assert self.logits_.shape == (k,)
        return self

    def _fit_logits(self, scores: np.ndarray, y: np.ndarray, coverage: np.ndarray,
                    sel: np.ndarray) -> np.ndarray:
        """Per-block separation on the selected rows, as a logit.

        Uses the rank statistic behind AUC (the Mann-Whitney U), which is what the
        evaluation reports and is invariant to any monotone rescaling a calibrator may
        have applied. A block that cannot be evaluated -- absent, or one-class on these
        rows -- gets logit 0, i.e. the weight it would have had under ``late``.
        """
        k = scores.shape[1]
        out = np.zeros(k, dtype=float)
        if self.strategy == "late" or not sel.any():
            return out
        for j in range(k):
            m = sel & (coverage[:, j] > 0)
            yj = y[m]
            if m.sum() < 2 or len(np.unique(yj)) < 2:
                continue
            auc = _auc(yj, scores[m, j])
            # 0.5 (no separation) maps to 0, so an uninformative block sits exactly at
            # the equal-weight point rather than being suppressed or promoted.
            out[j] = float(np.clip(4.0 * (auc - 0.5), -4.0, 4.0))
        return out

    # -- weights ------------------------------------------------------------------------

    def weights(self, coverage: np.ndarray, regime: np.ndarray | None = None,
                confidence: np.ndarray | None = None) -> np.ndarray:
        """Per-row, per-block weights. Rows sum to 1, or to 0 when nothing covers them.

        Zero coverage means zero weight, enforced by masking before the normalisation
        rather than after it, so the surviving blocks absorb the absent one's share
        instead of the row summing to less than one.
        """
        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        n, k = coverage.shape
        present = coverage > 0

        if self.strategy == "late" or self.logits_ is None:
            z = np.zeros((n, k), dtype=float)
        elif self.strategy in ("regime_inherited", "regime_corrected") \
                and self.regime_logits_ is not None:
            if self.strategy == "regime_inherited":
                idx = np.full(n, self.inherited_regime_, dtype=int)
            else:
                idx = self._regime_index(regime, n)
            z = self.regime_logits_[idx]
        else:
            z = np.repeat(self.logits_[None, :], n, axis=0)

        if self.strategy == "uncertainty" and confidence is not None:
            # A learner sitting on the decision boundary has nothing to say; scale its
            # weight down rather than letting a static weight speak for it.
            conf = np.clip(np.atleast_2d(np.asarray(confidence, dtype=float)), 0.0, 1.0)
            z = z + np.log(np.clip(conf, 1e-3, None))

        z = np.where(present, z, -np.inf)
        w = np.where(np.isfinite(z), _softmax(np.where(np.isfinite(z), z, 0.0)), 0.0)
        w = np.where(present, w, 0.0)
        total = w.sum(axis=1, keepdims=True)
        return np.divide(w, total, out=np.zeros_like(w), where=total > 0)

    # -- combine ------------------------------------------------------------------------

    def combine(self, scores: np.ndarray, coverage: np.ndarray,
                confidence: np.ndarray | None = None,
                regime: np.ndarray | None = None) -> CombinedScore:
        """Weighted combination of the block scores, with its uncertainty."""
        scores = np.atleast_2d(np.asarray(scores, dtype=float))
        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        w = self.weights(coverage, regime, confidence)

        covered = w.sum(axis=1) > 0
        score = np.where(covered, (w * scores).sum(axis=1), 0.5)

        # Coverage as the interface reports it: the share of blocks that spoke.
        cov_frac = (coverage > 0).mean(axis=1)

        # Disagreement: the weighted spread of the present blocks' scores. Two blocks at
        # 0.1 and 0.9 average to the same 0.5 as two blocks at 0.5, and only one of those
        # is a confident answer.
        centred = scores - score[:, None]
        spread = np.sqrt(np.clip((w * centred ** 2).sum(axis=1), 0.0, None))
        disagreement = np.clip(spread / 0.5, 0.0, 1.0)

        uncertainty = np.clip(1.0 - cov_frac * (1.0 - disagreement), 0.0, 1.0)
        uncertainty = np.where(covered, uncertainty, 1.0)
        return CombinedScore(score=score, uncertainty=uncertainty,
                             coverage=cov_frac, weights=w)

    # -- helpers ------------------------------------------------------------------------

    def _regime_index(self, regime: np.ndarray | None, n: int) -> np.ndarray:
        if regime is None:
            return np.zeros(n, dtype=int)
        r = np.asarray(regime)
        r = np.where(np.isfinite(r.astype(float)), r, 0)
        return np.clip(r.astype(int), 0, self.n_regimes - 1)


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank-based AUC. Ties share the average rank, as the U statistic requires."""
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1, dtype=float)
    ps = p[order]
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))
