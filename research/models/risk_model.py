"""The AEGIS integrity-risk model: per-block learners plus a combination layer.

Architecture, and why it is this shape rather than one big network:

* One gradient-boosted learner per feature block. Each is trained only on rows where that
  block is present, so a missing block is never imputed.
* Each learner is probability-calibrated on a held-out inner fold, because the combination
  layer averages scores and averaging uncalibrated scores is meaningless.
* The combination layer (:mod:`research.models.combiner`) weighs the calibrated scores.
* Uncertainty comes from two measurable sources -- disagreement between present blocks,
  and how much of the evidence stack is missing -- not from a learned scalar that nothing
  constrains.

The per-block decomposition is what makes block ablation and block attribution exact
rather than approximate: dropping a block means dropping a learner, and a block's
contribution is its calibrated score times its combination weight.

PLAIN ENGLISH -- what this whole file is about:

THE MODEL. This is the part that actually looks at a company and says how worried it is.

THE DESIGN: A PANEL OF SPECIALISTS, NOT ONE KNOW-IT-ALL.

Most systems would feed everything into one big model and let it sort things out. This one
instead trains FOUR SEPARATE SPECIALISTS, one per family of evidence:
  * a price specialist,
  * a trading-detail specialist,
  * a market-mood specialist,
  * a contagion specialist.
Then a final layer listens to all four and decides how much to trust each one.

WHY BOTHER? Three real reasons.

1. MISSING EVIDENCE IS HANDLED HONESTLY. Suppose we have no market-mood data for a
   company. With one big model, you would have to invent a value to fill the hole
   ("imputing"), which means feeding the model a number nobody measured. Here, the mood
   specialist simply does not speak. The other three carry on. Nothing was invented.

2. YOU CAN ASK "WHAT WAS THAT ONE WORTH?". Want to know how much the contagion evidence
   was contributing? Remove that specialist and rerun. That is an exact answer, because
   the specialist genuinely was a separate thing. With one big tangled model you could
   only ever approximate it.

3. THE EXPLANATION IS EXACT ARITHMETIC. Each specialist's contribution is simply its
   score multiplied by how much it was trusted. That is not an estimate of the
   explanation -- it IS the calculation.

CALIBRATION, and why it is not optional here. A model can be good at RANKING without its
numbers meaning anything. It might reliably put the riskiest companies at the top while
its "0.8" actually corresponds to about a 30% chance in reality. That is fine if you only
ever sort things. It is a disaster if you AVERAGE numbers from four such models, because
you would be averaging four different private languages. So each specialist is
"calibrated": adjusted until its 0.8 really does mean an 80% chance.

UNCERTAINTY, done honestly. Most systems that report confidence just have the model output
a confidence number -- but nothing forces that number to be truthful, so it is really the
model's opinion of itself. Here uncertainty comes from two things you can actually check:
  * do the specialists DISAGREE with each other? (they should be less sure if so)
  * how much of the evidence was missing? (less evidence, less certainty)
Both are measurable facts about the situation, not the model's self-assessment.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The table-assembly file, which knows which measurements belong to which family.
from research.data import dataset as ds
# The layer that weighs the specialists' opinions.
from research.models.combiner import BlockCombiner

# A label for this version of the model.
MODEL_VERSION = "aegis-risk-v1"

# The four families of evidence, and therefore the four specialists.
DEFAULT_BLOCKS = ["market", "microstructure", "regime", "propagation"]


@dataclass
# One specialist.
class BlockLearner:
    # Which family it specialises in.
    name: str
    # Which measurements it reads.
    columns: list[str]
    # The starting point for randomness, so training can be repeated exactly.
    seed: int = 20260818
    # The fewest examples it will accept before agreeing to learn anything.
    min_rows: int = 50
    # The trained model itself. `repr=False` keeps it out of printed descriptions, because
    # a trained model prints as pages of unreadable numbers.
    model: object | None = field(default=None, repr=False)
    # The adjustment that makes its numbers mean what they say.
    calibrator: object | None = field(default=None, repr=False)
    # How it got on. Starts as "not yet trained".
    status: str = "NOT FIT"
    # How many examples it learned from.
    n_train: int = 0
    # How many of its measurements turned out to be completely empty.
    n_dropped_all_nan: int = 0

    # Train this specialist.
    def fit(self, X: pd.DataFrame, y: np.ndarray, coverage: np.ndarray) -> None:
        # Fetched here rather than at the top of the file, because scikit-learn is large and
        # slow to load, and not every use of this file needs to train anything.
        # `CalibratedClassifierCV` is the wrapper that makes a model's numbers honest.
        from sklearn.calibration import CalibratedClassifierCV
        # The learner itself: "gradient boosting" builds many small decision trees, each one
        # fixing the mistakes of the ones before it. It is the standard strong choice for
        # table-shaped data like this, and it copes with missing values natively.
        from sklearn.ensemble import HistGradientBoostingClassifier

        # Only train on rows where this family of evidence exists at all.
        mask = coverage > 0
        ys = y[mask]
        self.n_train = int(mask.sum())
        # Two reasons to refuse. Too few examples to learn anything reliable, or...
        # `len(np.unique(ys)) < 2` means every example has the same answer -- all "trouble"
        # or all "fine". You cannot learn to tell two things apart from examples of only one.
        if self.n_train < self.min_rows or len(np.unique(ys)) < 2:
            self.status = "INSUFFICIENT DATA"
            return
        # Columns that are entirely absent on the training rows carry no information and
        # make the histogram binner fail outright. Dropping them here -- and recording
        # how many were dropped -- is what lets an ablation blank a feature block
        # without the arm failing and disappearing from the results table.
        # PLAIN ENGLISH: a real bug, neatly handled. When an experiment deliberately blanks
        # out a family of evidence to see what happens without it, the learner used to CRASH
        # rather than cope -- so that experiment produced no result at all and silently
        # vanished from the results table. A missing row in a table is very easy not to
        # notice. Dropping the empty columns, and recording how many were dropped, means the
        # experiment runs and reports honestly instead.
        sub = X.loc[mask, self.columns]
        usable = [c for c in self.columns if sub[c].notna().any()]
        self.n_dropped_all_nan = len(self.columns) - len(usable)
        # Nothing at all left to learn from.
        if not usable:
            self.status = "INSUFFICIENT DATA"
            return
        self.columns = usable
        Xs = sub[usable]
        # Set up the learner. Each setting explained:
        base = HistGradientBoostingClassifier(
            # At most 200 little trees.
            max_iter=200,
            # How big a correction each tree may make. Small means slow, careful learning,
            # which resists memorising the training data.
            learning_rate=0.06,
            # Each tree may ask at most 4 questions deep. Shallow trees keep it simple and
            # generalising rather than memorising.
            max_depth=4,
            # A penalty on complexity, pushing it towards simpler explanations.
            l2_regularization=1.0,
            # Stop early if it stops improving...
            early_stopping=True,
            # ...judged on 15% of the data held back for exactly that purpose.
            validation_fraction=0.15,
            # Fixed randomness, so training the same data twice gives the same model.
            random_state=self.seed)
        # Isotonic needs a decent sample; below that Platt scaling is the safer choice.
        # PLAIN ENGLISH: two ways of making the numbers honest.
        #   "isotonic" is flexible and can fix any shape of distortion -- but being flexible,
        #     it will happily memorise noise if you do not give it plenty of data.
        #   "sigmoid" (Platt scaling) can only apply one simple smooth curve. Less powerful,
        #     but far harder to fool with a small sample.
        # So: plenty of data, use the flexible one; not much, use the safe one.
        method = "isotonic" if self.n_train >= 800 else "sigmoid"
        # `cv=3` means the calibration is worked out on data the model did not train on,
        # three separate times. Calibrating on the training data would produce a model that
        # looked beautifully honest about examples it had already memorised.
        self.model = CalibratedClassifierCV(base, method=method, cv=3)
        self.model.fit(Xs, ys)
        self.status = "OK"

    # Ask this specialist for its opinion.
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        # Never trained? Answer 0.5 for everything -- exactly "I have no idea", the honest
        # halfway point. It does not guess "probably fine", which would be a real claim.
        if self.status != "OK" or self.model is None:
            return np.full(len(X), 0.5)
        # `predict_proba` gives the chance of each answer; `[:, 1]` takes the second column,
        # which is the chance of "trouble".
        return self.model.predict_proba(X[self.columns])[:, 1]

    # How strongly does this specialist feel?
    def confidence(self, p: np.ndarray) -> np.ndarray:
        """Distance from the decision boundary, mapped to [0, 1]. A calibrated 0.5 means
        the learner has nothing to say; 0.02 or 0.98 means it does."""
        # PLAIN ENGLISH: 0.5 means "could go either way" -- no opinion. Both 0.02 and 0.98
        # are strong opinions, just in opposite directions. So confidence is DISTANCE from
        # the middle, in either direction.
        # `abs(p - 0.5)` gives 0 to 0.5, and doubling it gives a clean 0 to 1 scale.
        # `np.clip` pins it inside that range in case of arithmetic dust at the edges.
        return np.clip(2.0 * np.abs(p - 0.5), 0.0, 1.0)


@dataclass
# The whole model: the panel of specialists plus the layer that weighs them.
class AegisRiskModel:
    # Which families to use.
    blocks: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKS))
    # How to combine the opinions.
    combination_rule: str = "regime_corrected"
    seed: int = 20260818
    # How many market moods to allow for.
    n_regimes: int = 6
    # The specialists, once trained.
    learners: dict[str, BlockLearner] = field(default_factory=dict)
    # The combining layer, once fitted.
    combiner: BlockCombiner | None = None
    version: str = MODEL_VERSION

    # -- fit ------------------------------------------------------------------------

    #: Pseudo-block name for the early rule, which by definition has no per-block
    #: decomposition: there is one learner over the union of the features.
    # A special name for the single combined learner used by the "early" approach. The
    # double underscores make it obvious it is not a real family of evidence.
    EARLY_UNION = "__union__"

    # Train everything.
    def fit(self, df: pd.DataFrame, y: np.ndarray) -> AegisRiskModel:
        # The "early" approach is a completely different shape, handled separately below.
        if self.combination_rule == "early":
            return self._fit_early(df, y)
        self.learners = {}
        # Train one specialist per family.
        for m in self.blocks:
            # Which measurements from this family are actually present in the data.
            cols = [c for c in ds.FEATURE_BLOCKS[m] if c in df.columns]
            if not cols:
                continue
            lr = BlockLearner(m, cols, self.seed)
            lr.fit(df, y, self._coverage_col(df, m))
            self.learners[m] = lr

        # Which specialists actually managed to learn something.
        active = [m for m, lr in self.learners.items() if lr.status == "OK"]
        # None at all? Stop, rather than producing a model that silently answers 0.5 to
        # everything while looking perfectly functional.
        if not active:
            raise RuntimeError("no block learner could be fitted")
        # The trailing underscore is the scikit-learn convention marking something learned
        # during training, as opposed to a setting chosen beforehand.
        self.active_ = active
        # Collect every working specialist's opinion into a grid, one column each.
        scores = np.column_stack([self.learners[m].predict(df) for m in active])
        # And how much evidence each one had for each row.
        cov = np.column_stack([self._coverage_col(df, m) for m in active])
        # Now fit the layer that decides how much to trust each specialist.
        self.combiner = BlockCombiner(self.combination_rule, self.n_regimes, active,
                                      self.seed)
        self.combiner.fit(scores, y, cov, self._regime(df))
        return self

    # The alternative shape: one big learner instead of a panel.
    def _fit_early(self, df: pd.DataFrame, y: np.ndarray) -> AegisRiskModel:
        """The early rule: one learner over the concatenated features of every block.

        This is what "early" means and it was previously not implemented. The rule name
        existed and ``BlockCombiner.weights`` mapped it onto the same all-zero logits as
        ``late``, so the COMBINER_EARLY arm was the late rule under another label and
        produced predictions identical to COMBINER_LATE on every seed. A single run showed
        two adjacent numbers agreeing to four decimals, which reads as "the early and late
        rules perform comparably"; ten seeds showed the two columns identical to machine
        precision, which is not a finding but a missing implementation.

        The consequence is structural rather than incidental: fitting one model over the
        union lets it use interactions *between* blocks, which per-block learners cannot
        see at all, and it gives up the per-block attribution that the rest of the
        pipeline reports. That trade is the reason to compare the two.
        """
        # PLAIN ENGLISH: this comment records one of the best catches in the whole project,
        # and it is worth reading slowly.
        # There were meant to be two different approaches being compared. But one of them was
        # never actually built -- its name existed, and it quietly ran the OTHER approach.
        # So the results table showed two methods scoring, say, 0.8213 and 0.8214. A person
        # reading that would sensibly conclude "the two approaches perform about the same",
        # which sounds like a finding. It was not a finding. It was the same method twice.
        # How was it caught? By running the experiment with TEN different random seeds. Two
        # genuinely different methods would drift apart slightly on different seeds. These
        # two stayed identical to the last decimal place, every time. Identical to that
        # degree is impossible for two different methods -- so it had to be one method.
        # And what is the real difference? One big model can spot COMBINATIONS across
        # families -- "high price volatility AND unusual trade sizes together" -- which
        # separate specialists can never see, because neither one sees the other's evidence.
        # In exchange it gives up the clean per-family explanation. That trade is precisely
        # what the comparison is for.

        # Gather every measurement from every family into one list.
        cols: list[str] = []
        for m in self.blocks:
            cols.extend(c for c in ds.FEATURE_BLOCKS[m] if c in df.columns)
        # `dict.fromkeys` removes duplicates while keeping the original order -- important,
        # since a model reads its input by position and a shuffled order would scramble it.
        cols = list(dict.fromkeys(cols))
        if not cols:
            raise RuntimeError("no block columns present for the early rule")

        # A row is usable if *any* block covers it, matching the per-block path where a
        # row survives when at least one learner can score it.
        # PLAIN ENGLISH: the two approaches must be judged on the SAME rows, or the
        # comparison is meaningless -- one would be answering an easier question.
        cov_each = np.column_stack([self._coverage_col(df, m) for m in self.blocks])
        coverage = cov_each.max(axis=1)

        # Train the single combined learner.
        lr = BlockLearner(self.EARLY_UNION, cols, self.seed)
        lr.fit(df, y, coverage)
        if lr.status != "OK":
            raise RuntimeError("early learner could not be fitted: %s" % lr.status)

        self.learners = {self.EARLY_UNION: lr}
        self.active_ = [self.EARLY_UNION]
        # `[:, None]` reshapes a flat row of scores into a single-column grid, so the
        # combining layer sees the same shape it expects from the panel version.
        scores = lr.predict(df)[:, None]
        # With only one opinion there is nothing to weigh, so the simple "late" rule is used.
        self.combiner = BlockCombiner("late", self.n_regimes, self.active_, self.seed)
        self.combiner.fit(scores, y, coverage[:, None], self._regime(df))
        return self

    # -- predict --------------------------------------------------------------------

    # Ask the whole model about some companies.
    def predict(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        active = self.active_
        # Every specialist's opinion.
        scores = np.column_stack([self.learners[m].predict(df) for m in active])
        # And how strongly each one holds it.
        conf = np.column_stack([self.learners[m].confidence(scores[:, i])
                                for i, m in enumerate(active)])
        # And how much evidence each one had.
        cov = np.column_stack([self._coverage_col(df, m) for m in active])
        # Combine it all.
        res = self.combiner.combine(scores, cov, conf, self._regime(df))
        return {
            # The headline answer.
            "integrity_risk": res.score,
            # How unsure we are of it.
            "uncertainty": res.uncertainty,
            # How much of the evidence we actually had.
            "coverage": res.coverage,
            # And the full working, so the answer can be taken apart and checked.
            "block_scores": scores,
            "block_weights": res.weights,
            "block_names": active,
            #: score * weight, i.e. each block's additive share of the combined number.
            # THE EXPLANATION. Not an estimate of what the model did -- literally the
            # multiplication the model performed. Add these up and you get the headline
            # answer back exactly.
            "block_contribution": scores * res.weights,
        }

    # -- helpers ---------------------------------------------------------------------

    # How much of a family's evidence was present, per row.
    def _coverage_col(self, df: pd.DataFrame, m: str) -> np.ndarray:
        # The combined learner counts as covered if ANY family covers the row.
        if m == self.EARLY_UNION:
            each = np.column_stack([self._coverage_col(df, k) for k in self.blocks])
            return each.max(axis=1)
        # The column names mostly follow one pattern, except microstructure which was
        # shortened. The little dictionary handles that one exception without a special case.
        key = {"microstructure": "cov_micro"}.get(m, "cov_%s" % m)
        if key in df.columns:
            # Missing coverage counts as zero coverage -- the safe reading, since unknown
            # evidence should not be treated as present.
            return df[key].fillna(0.0).to_numpy(dtype=float)
        # No coverage column at all: assume full coverage. This is the tolerant fallback for
        # simple test data that does not carry the honesty columns.
        return np.ones(len(df))

    # Which market mood each row was in.
    def _regime(self, df: pd.DataFrame) -> np.ndarray | None:
        # None known? Say so, and the combining layer will do without.
        if "regime_id" not in df.columns:
            return None
        r = df["regime_id"].fillna(0).to_numpy()
        # `np.clip` forces the value into the valid range, so a stray mood number from a
        # differently-configured run cannot cause an out-of-range crash deeper in.
        return np.clip(r.astype(int), 0, self.n_regimes - 1)

    # A readable table describing how training went.
    def summary(self) -> pd.DataFrame:
        rows = []
        for m, lr in self.learners.items():
            w = np.nan
            # Find how much this specialist ended up being trusted, if the combining layer
            # was fitted and knows about it.
            if self.combiner is not None and m in self.combiner.blocks:
                i = self.combiner.blocks.index(m)
                w = float(self.combiner.logits_[i]) if self.combiner.logits_ is not None \
                    else np.nan
            rows.append({"block": m, "status": lr.status, "n_train": lr.n_train,
                         "n_features": len(lr.columns),
                         # Reported so a reader can see when an experiment blanked a family
                         # out, rather than that fact being invisible.
                         "n_dropped_all_nan": lr.n_dropped_all_nan,
                         "combiner_logit": w})
        return pd.DataFrame(rows)
