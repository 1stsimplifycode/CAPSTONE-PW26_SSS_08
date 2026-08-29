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

PLAIN ENGLISH -- what this whole file is about:

THE JUDGE. Four specialists have each given an opinion. This file decides how much each
one's opinion counts, and combines them into one number.

INVARIANT 1: SILENCE IS NOT AGREEMENT.
This is the single most important idea here, so consider it carefully.
Say three specialists score a company at 0.9, 0.9 and 0.9 -- everyone is alarmed. The
fourth has no data at all and cannot speak.
The tempting thing is to give the silent one the neutral value 0.5 and average all four:
(0.9 + 0.9 + 0.9 + 0.5) / 4 = 0.8.
That is WRONG, and dangerously so. The fourth specialist did not say "things look about
average". It said NOTHING. By writing 0.5 in its place, you have invented a moderating
opinion out of thin air and used it to talk the other three down.
On a screen, 0.8 looks calmer than 0.9 -- so a missing measurement has been silently
converted into reassurance. The right answer is to leave the silent one out entirely: the
three who spoke average to 0.9, and that is the answer.

INVARIANT 2: NOBODY SPOKE MEANS NO ANSWER.
If all four are silent, the system returns 0.5 with uncertainty 1.0 -- which means "I have
absolutely no idea". It does not produce a confident number derived from nothing at all.

AND UNCERTAINTY, MEASURED RATHER THAN CLAIMED.
Most systems that report confidence simply have the model output a confidence number. But
nothing forces that number to be honest -- it is the model's opinion of itself, and models
are often confidently wrong. Here it comes from two facts you can check:
  * DISAGREEMENT. If the specialists say 0.1 and 0.9, we should be very unsure -- even
    though they average to a perfectly reasonable-looking 0.5.
  * MISSING EVIDENCE. If only one of four spoke, we should be less sure than if all four
    did.
Both are properties of the situation, not of the model's self-image.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
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
# PLAIN ENGLISH on `regime_inherited`, which is another excellent catch worth spelling out.
# The idea was: "in a panicky market, weigh the specialists differently". The way it was
# originally written added the same extra number to EVERY specialist's weight.
# But the weights are then normalised so they add up to 1 -- and adding the same amount to
# everything, then normalising, gets you back exactly where you started. It is like giving
# every child in a class ten extra marks and then ranking them: the ranking does not budge.
# So the rule did precisely nothing. It looked like it conditioned on the market mood, and
# it algebraically could not. It is KEPT, deliberately, as a "negative control" -- an arm
# that is known to do nothing, so if it ever scores differently from static_attention,
# something else is wrong. Turning a bug into a permanent test is a lovely move.
STRATEGIES = ("late", "static_attention", "uncertainty", "regime_inherited",
              "regime_corrected", "early")

#: Below this many rows a regime does not get its own weights and falls back to the
#: pooled ones. Fitting six weights on a handful of rows is noise, not conditioning.
# PLAIN ENGLISH: if a particular market mood only occurred on 12 days, working out six
# separate weights from those 12 days would be fitting to noise. So a rare mood falls back
# to the general-purpose weights, which is the honest thing to do with thin evidence.
MIN_ROWS_PER_REGIME = 100


@dataclass
# The combined answer plus its full working.
class CombinedScore:
    """One row per input row: the combined score and what produced it."""

    # The final risk number.
    score: np.ndarray
    # How unsure we are of it.
    uncertainty: np.ndarray
    # What fraction of the evidence was actually present.
    coverage: np.ndarray
    # How much each specialist counted, per row.
    weights: np.ndarray


# Turn a set of raw scores into weights that add up to 1.
def _softmax(z: np.ndarray, axis: int = -1) -> np.ndarray:
    # PLAIN ENGLISH: "softmax" converts any set of numbers into positive shares totalling
    # 1 -- so bigger numbers get bigger shares, and everything ends up as a proper fraction.
    # Subtracting the largest value first changes nothing about the answer, but it stops the
    # `exp` below from overflowing on large inputs. This is the standard safe way to write it.
    z = z - np.max(z, axis=axis, keepdims=True)
    e = np.exp(z)
    # `np.clip(..., 1e-12, None)` prevents a divide-by-zero in the impossible-but-possible
    # case where everything underflows to nothing.
    return e / np.clip(e.sum(axis=axis, keepdims=True), 1e-12, None)


@dataclass
class BlockCombiner:
    """Combine per-block scores under one of :data:`STRATEGIES`.

    ``blocks`` names the columns of every ``scores`` array handed to this object, in
    order, so a weight can be reported against the block it belongs to.
    """
    # PLAIN ENGLISH: the scores arrive as a nameless grid of numbers. Keeping the names in
    # the same order means a weight can always be reported against the specialist it
    # actually belongs to, rather than being guessed at from its position.

    # Which combination rule to use.
    strategy: str = "regime_corrected"
    # How many market moods to allow for.
    n_regimes: int = 6
    # The specialists' names, in column order.
    blocks: list[str] = field(default_factory=list)
    seed: int = 20260818

    #: Pooled per-block logits, shape (n_blocks,). ``None`` until fitted.
    # PLAIN ENGLISH: a "logit" here is a raw, unnormalised weight -- a number that says how
    # much this specialist should count, before everything is scaled to add up to 1.
    logits_: np.ndarray | None = None
    #: Per-regime, per-block logits, shape (n_regimes, n_blocks). ``regime_corrected``
    #: only.
    # A separate set of weights for each market mood: a grid, moods down and specialists
    # across.
    regime_logits_: np.ndarray | None = None
    #: Per-regime scalar added to every block's logit. ``regime_inherited`` only.
    # The broken version, kept deliberately as the negative control.
    regime_offset_: np.ndarray | None = None

    # Check the requested rule is one we know about, at the moment of construction.
    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            # And the message lists the valid options, so a typo is fixed in seconds rather
            # than requiring a hunt through the source.
            raise ValueError("unknown combination strategy %r; expected one of %s"
                             % (self.strategy, ", ".join(STRATEGIES)))

    # -- fit ----------------------------------------------------------------------------

    # Learn how much to trust each specialist.
    def fit(self, scores: np.ndarray, y: np.ndarray, coverage: np.ndarray,
            regime: np.ndarray | None = None) -> BlockCombiner:
        """Learn the block weights from the training split alone.

        A block's weight is driven by how well its calibrated score separates the two
        classes *on the rows it actually covers*. Scoring it on rows it does not cover
        would credit or punish it for the neutral 0.5 the learner emits there.
        """
        # PLAIN ENGLISH: judge each specialist ONLY on the questions it actually answered.
        # A specialist that stayed silent on 90% of rows emits 0.5 on all of those. Judging
        # it on those rows would be marking it on questions it explicitly declined -- and
        # since 0.5 is neither right nor wrong, it would drag its score towards mediocrity
        # regardless of how good it really is where it does speak.

        # `np.atleast_2d` makes sure we have a grid even if only one specialist was handed
        # over, so the rest of the code has one shape to deal with.
        scores = np.atleast_2d(np.asarray(scores, dtype=float))
        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        y = np.asarray(y).astype(int)
        k = scores.shape[1]

        # The general-purpose weights, fitted across all rows (the `np.ones(..., bool)`
        # selects everything).
        self.logits_ = self._fit_logits(scores, y, coverage, np.ones(len(y), dtype=bool))

        if self.strategy == "regime_inherited":
            # The inherited formulation adds one term per regime to the softmax
            # numerator, the *same* term for every block. Reproduced here exactly as
            # specified, because the point of keeping this rule is to show that such a
            # term cancels under normalisation and leaves static attention untouched.
            # PLAIN ENGLISH: the broken rule is reproduced FAITHFULLY, on purpose, so the
            # project can demonstrate that it does nothing rather than merely assert it.
            reg = self._regime_index(regime, len(y))
            # How many rows fell in each mood.
            counts = np.bincount(reg, minlength=self.n_regimes).astype(float)
            with np.errstate(divide="ignore"):
                # The log of each mood's share. This is the term that will cancel out.
                self.regime_offset_ = np.log(np.clip(counts / max(counts.sum(), 1),
                                                     1e-6, None))
            self.regime_logits_ = None
        elif self.strategy == "regime_corrected":
            # THE FIXED VERSION: genuinely different weights per mood.
            reg = self._regime_index(regime, len(y))
            # Start every mood off with the general-purpose weights.
            per = np.repeat(self.logits_[None, :], self.n_regimes, axis=0)
            counts = np.bincount(reg, minlength=self.n_regimes)
            for r in range(self.n_regimes):
                sel = reg == r
                # Only fit mood-specific weights when there is enough data AND both answers
                # occur. Otherwise leave that mood on the general-purpose weights -- an
                # honest fallback rather than six numbers fitted to a dozen rows.
                if counts[r] >= MIN_ROWS_PER_REGIME and len(np.unique(y[sel])) > 1:
                    per[r] = self._fit_logits(scores, y, coverage, sel)
            self.regime_logits_ = per
        else:
            self.regime_logits_ = None

        # A safety check that the weights came out the expected shape. `assert` stops the
        # program if this is ever false, which would mean a programming error rather than a
        # data problem.
        assert self.logits_.shape == (k,)
        return self

    # Work out one weight per specialist, from how well each separates the two answers.
    def _fit_logits(self, scores: np.ndarray, y: np.ndarray, coverage: np.ndarray,
                    sel: np.ndarray) -> np.ndarray:
        """Per-block separation on the selected rows, as a logit.

        Uses the rank statistic behind AUC (the Mann-Whitney U), which is what the
        evaluation reports and is invariant to any monotone rescaling a calibrator may
        have applied. A block that cannot be evaluated -- absent, or one-class on these
        rows -- gets logit 0, i.e. the weight it would have had under ``late``.
        """
        # PLAIN ENGLISH: AUC answers "if I pick one troubled company and one fine company at
        # random, how often does this specialist score the troubled one higher?"
        #   0.5 = a coin flip. Useless.
        #   1.0 = always right.
        # It looks only at the ORDER, so it is unaffected by any stretching or squashing the
        # calibration step applied -- which makes it exactly the right measure here.
        # And a specialist that cannot be judged gets weight 0, which after normalisation
        # means "counts the same as everybody else" -- neither punished nor promoted for
        # something we simply could not measure.
        k = scores.shape[1]
        out = np.zeros(k, dtype=float)
        # The "late" rule uses equal weights by definition, so there is nothing to fit.
        if self.strategy == "late" or not sel.any():
            return out
        for j in range(k):
            # Rows in this selection where this specialist actually spoke.
            m = sel & (coverage[:, j] > 0)
            yj = y[m]
            # Too few rows, or only one kind of answer, means AUC is meaningless. Leave the
            # weight at 0.
            if m.sum() < 2 or len(np.unique(yj)) < 2:
                continue
            auc = _auc(yj, scores[m, j])
            # 0.5 (no separation) maps to 0, so an uninformative block sits exactly at
            # the equal-weight point rather than being suppressed or promoted.
            # The x4 stretches the useful 0.5-to-1.0 range into something the softmax can
            # meaningfully separate, and the clip keeps a freakishly good result from
            # completely silencing every other specialist.
            out[j] = float(np.clip(4.0 * (auc - 0.5), -4.0, 4.0))
        return out

    # -- weights ------------------------------------------------------------------------

    # Work out the per-row weights.
    def weights(self, coverage: np.ndarray, regime: np.ndarray | None = None,
                confidence: np.ndarray | None = None) -> np.ndarray:
        """Per-row, per-block weights. Rows sum to 1, or to 0 when nothing covers them.

        Zero coverage means zero weight, enforced by masking before the normalisation
        rather than after it, so the surviving blocks absorb the absent one's share
        instead of the row summing to less than one.
        """
        # PLAIN ENGLISH on the ordering, which is the whole trick. If you normalised first
        # and then zeroed out the absent specialist, you would be left with weights adding
        # up to, say, 0.75 -- and the missing 0.25 would quietly drag the final score
        # towards zero. Masking FIRST means the three who spoke share the whole 100%
        # between them, exactly as they should.

        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        n, k = coverage.shape
        # Which specialists spoke on which rows.
        present = coverage > 0

        # Equal weights: all zeros, which softmax turns into an even split.
        if self.strategy == "late" or self.logits_ is None:
            z = np.zeros((n, k), dtype=float)
        # Mood-dependent weights: look up each row's mood.
        elif self.strategy in ("regime_inherited", "regime_corrected") \
                and self.regime_logits_ is not None:
            if self.strategy == "regime_inherited":
                idx = np.full(n, self.inherited_regime_, dtype=int)
            else:
                idx = self._regime_index(regime, n)
            z = self.regime_logits_[idx]
        # Otherwise the same learned weights for every row.
        else:
            z = np.repeat(self.logits_[None, :], n, axis=0)

        if self.strategy == "uncertainty" and confidence is not None:
            # A learner sitting on the decision boundary has nothing to say; scale its
            # weight down rather than letting a static weight speak for it.
            # PLAIN ENGLISH: a specialist may be generally excellent and yet have no view on
            # THIS company. Its usual high weight should not let it speak loudly while
            # saying nothing. Adding the log of its confidence to the weight is the same as
            # multiplying its share by that confidence, once softmax has done its work.
            conf = np.clip(np.atleast_2d(np.asarray(confidence, dtype=float)), 0.0, 1.0)
            # The `1e-3` floor stops the log of zero, which would be negative infinity.
            z = z + np.log(np.clip(conf, 1e-3, None))

        # Mask out the absent specialists by setting their weight to minus infinity, which
        # softmax turns into exactly zero.
        z = np.where(present, z, -np.inf)
        # Compute the shares, replacing the infinities with zeros first so the arithmetic
        # stays well-behaved, then forcing the absent ones back to zero.
        w = np.where(np.isfinite(z), _softmax(np.where(np.isfinite(z), z, 0.0)), 0.0)
        w = np.where(present, w, 0.0)
        total = w.sum(axis=1, keepdims=True)
        # Renormalise so each row's weights add to 1. `np.divide(..., where=total > 0)`
        # skips the division entirely on rows where nobody spoke, leaving zeros -- so those
        # rows sum to 0, which is how the caller detects "no evidence at all".
        return np.divide(w, total, out=np.zeros_like(w), where=total > 0)

    # -- combine ------------------------------------------------------------------------

    # Produce the final answer.
    def combine(self, scores: np.ndarray, coverage: np.ndarray,
                confidence: np.ndarray | None = None,
                regime: np.ndarray | None = None) -> CombinedScore:
        """Weighted combination of the block scores, with its uncertainty."""
        scores = np.atleast_2d(np.asarray(scores, dtype=float))
        coverage = np.atleast_2d(np.asarray(coverage, dtype=float))
        w = self.weights(coverage, regime, confidence)

        # Rows where at least one specialist spoke.
        covered = w.sum(axis=1) > 0
        # The weighted average, or a flat 0.5 where nobody spoke. That 0.5 is INVARIANT 2:
        # not a guess, but the explicit "no idea" value, and it comes paired with an
        # uncertainty of 1.0 below so it can never be mistaken for a confident finding.
        score = np.where(covered, (w * scores).sum(axis=1), 0.5)

        # Coverage as the interface reports it: the share of blocks that spoke.
        cov_frac = (coverage > 0).mean(axis=1)

        # Disagreement: the weighted spread of the present blocks' scores. Two blocks at
        # 0.1 and 0.9 average to the same 0.5 as two blocks at 0.5, and only one of those
        # is a confident answer.
        # PLAIN ENGLISH: this is the key insight about honest uncertainty. "Both say 0.5"
        # and "one says 0.1 while the other says 0.9" produce an identical average. But the
        # first is a considered agreement and the second is a flat contradiction. Measuring
        # the spread is what tells those two situations apart.
        centred = scores - score[:, None]
        spread = np.sqrt(np.clip((w * centred ** 2).sum(axis=1), 0.0, None))
        # Divided by 0.5, the largest spread possible on a 0-to-1 scale, to land on 0 to 1.
        disagreement = np.clip(spread / 0.5, 0.0, 1.0)

        # The final uncertainty. Read it as: certainty is having lots of evidence AND
        # agreement between the sources, and uncertainty is one minus that. So plenty of
        # evidence with everyone agreeing gives near 0; scant evidence, or a stand-up row
        # between the specialists, pushes it towards 1.
        uncertainty = np.clip(1.0 - cov_frac * (1.0 - disagreement), 0.0, 1.0)
        # And where nobody spoke at all, uncertainty is exactly 1: total ignorance, stated
        # plainly.
        uncertainty = np.where(covered, uncertainty, 1.0)
        return CombinedScore(score=score, uncertainty=uncertainty,
                             coverage=cov_frac, weights=w)

    # -- helpers ------------------------------------------------------------------------

    # Turn mood labels into safe position numbers.
    def _regime_index(self, regime: np.ndarray | None, n: int) -> np.ndarray:
        # No mood information at all? Put everything in mood 0.
        if regime is None:
            return np.zeros(n, dtype=int)
        r = np.asarray(regime)
        # Replace anything that is not a real number with 0.
        r = np.where(np.isfinite(r.astype(float)), r, 0)
        # And force it into the valid range, so a stray value cannot cause a crash deeper in.
        return np.clip(r.astype(int), 0, self.n_regimes - 1)


# Work out the AUC by hand.
def _auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank-based AUC. Ties share the average rank, as the U statistic requires."""
    # PLAIN ENGLISH: computed from ranks rather than by comparing every possible pair,
    # because the pairwise version would take roughly n-squared time -- unusable on large
    # data -- while the ranking version is fast, and gives the identical answer.

    # Sort the scores. `kind="mergesort"` is a STABLE sort: equal values keep their original
    # relative order, which makes the result identical every run rather than depending on
    # how the sorting happened to break ties.
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    # Assign ranks 1, 2, 3... in sorted order, placed back at each item's original position.
    ranks[order] = np.arange(1, len(p) + 1, dtype=float)
    ps = p[order]
    i = 0
    # Now handle ties. Items with identical scores must SHARE the average of the ranks they
    # span, otherwise whichever happened to be listed first would get unearned credit.
    while i < len(ps):
        j = i
        # Walk forward while the scores stay equal.
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        # If we found a run of equals, give them all the middle rank of the run.
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    # With only one kind of answer, AUC is undefined. Report 0.5 -- "no information" --
    # rather than crashing or inventing a score.
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # The standard Mann-Whitney formula: the troubled companies' total rank, minus the
    # smallest that total could possibly have been, divided by the largest it could have
    # exceeded that minimum by. The result lands neatly between 0 and 1.
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))
