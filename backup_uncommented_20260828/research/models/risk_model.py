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
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research.data import dataset as ds
from research.models.combiner import BlockCombiner

MODEL_VERSION = "aegis-risk-v1"

DEFAULT_BLOCKS = ["market", "microstructure", "regime", "propagation"]


@dataclass
class BlockLearner:
    name: str
    columns: list[str]
    seed: int = 20260818
    min_rows: int = 50
    model: object | None = field(default=None, repr=False)
    calibrator: object | None = field(default=None, repr=False)
    status: str = "NOT FIT"
    n_train: int = 0
    n_dropped_all_nan: int = 0

    def fit(self, X: pd.DataFrame, y: np.ndarray, coverage: np.ndarray) -> None:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import HistGradientBoostingClassifier

        mask = coverage > 0
        ys = y[mask]
        self.n_train = int(mask.sum())
        if self.n_train < self.min_rows or len(np.unique(ys)) < 2:
            self.status = "INSUFFICIENT DATA"
            return
        # Columns that are entirely absent on the training rows carry no information and
        # make the histogram binner fail outright. Dropping them here -- and recording
        # how many were dropped -- is what lets an ablation blank a feature block
        # without the arm failing and disappearing from the results table.
        sub = X.loc[mask, self.columns]
        usable = [c for c in self.columns if sub[c].notna().any()]
        self.n_dropped_all_nan = len(self.columns) - len(usable)
        if not usable:
            self.status = "INSUFFICIENT DATA"
            return
        self.columns = usable
        Xs = sub[usable]
        base = HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.06, max_depth=4, l2_regularization=1.0,
            early_stopping=True, validation_fraction=0.15, random_state=self.seed)
        # Isotonic needs a decent sample; below that Platt scaling is the safer choice.
        method = "isotonic" if self.n_train >= 800 else "sigmoid"
        self.model = CalibratedClassifierCV(base, method=method, cv=3)
        self.model.fit(Xs, ys)
        self.status = "OK"

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.status != "OK" or self.model is None:
            return np.full(len(X), 0.5)
        return self.model.predict_proba(X[self.columns])[:, 1]

    def confidence(self, p: np.ndarray) -> np.ndarray:
        """Distance from the decision boundary, mapped to [0, 1]. A calibrated 0.5 means
        the learner has nothing to say; 0.02 or 0.98 means it does."""
        return np.clip(2.0 * np.abs(p - 0.5), 0.0, 1.0)


@dataclass
class AegisRiskModel:
    blocks: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKS))
    combination_rule: str = "regime_corrected"
    seed: int = 20260818
    n_regimes: int = 6
    learners: dict[str, BlockLearner] = field(default_factory=dict)
    combiner: BlockCombiner | None = None
    version: str = MODEL_VERSION

    # -- fit ------------------------------------------------------------------------

    #: Pseudo-block name for the early rule, which by definition has no per-block
    #: decomposition: there is one learner over the union of the features.
    EARLY_UNION = "__union__"

    def fit(self, df: pd.DataFrame, y: np.ndarray) -> AegisRiskModel:
        if self.combination_rule == "early":
            return self._fit_early(df, y)
        self.learners = {}
        for m in self.blocks:
            cols = [c for c in ds.FEATURE_BLOCKS[m] if c in df.columns]
            if not cols:
                continue
            lr = BlockLearner(m, cols, self.seed)
            lr.fit(df, y, self._coverage_col(df, m))
            self.learners[m] = lr

        active = [m for m, lr in self.learners.items() if lr.status == "OK"]
        if not active:
            raise RuntimeError("no block learner could be fitted")
        self.active_ = active
        scores = np.column_stack([self.learners[m].predict(df) for m in active])
        cov = np.column_stack([self._coverage_col(df, m) for m in active])
        self.combiner = BlockCombiner(self.combination_rule, self.n_regimes, active,
                                      self.seed)
        self.combiner.fit(scores, y, cov, self._regime(df))
        return self

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
        cols: list[str] = []
        for m in self.blocks:
            cols.extend(c for c in ds.FEATURE_BLOCKS[m] if c in df.columns)
        cols = list(dict.fromkeys(cols))
        if not cols:
            raise RuntimeError("no block columns present for the early rule")

        # A row is usable if *any* block covers it, matching the per-block path where a
        # row survives when at least one learner can score it.
        cov_each = np.column_stack([self._coverage_col(df, m) for m in self.blocks])
        coverage = cov_each.max(axis=1)

        lr = BlockLearner(self.EARLY_UNION, cols, self.seed)
        lr.fit(df, y, coverage)
        if lr.status != "OK":
            raise RuntimeError("early learner could not be fitted: %s" % lr.status)

        self.learners = {self.EARLY_UNION: lr}
        self.active_ = [self.EARLY_UNION]
        scores = lr.predict(df)[:, None]
        self.combiner = BlockCombiner("late", self.n_regimes, self.active_, self.seed)
        self.combiner.fit(scores, y, coverage[:, None], self._regime(df))
        return self

    # -- predict --------------------------------------------------------------------

    def predict(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        active = self.active_
        scores = np.column_stack([self.learners[m].predict(df) for m in active])
        conf = np.column_stack([self.learners[m].confidence(scores[:, i])
                                for i, m in enumerate(active)])
        cov = np.column_stack([self._coverage_col(df, m) for m in active])
        res = self.combiner.combine(scores, cov, conf, self._regime(df))
        return {
            "integrity_risk": res.score,
            "uncertainty": res.uncertainty,
            "coverage": res.coverage,
            "block_scores": scores,
            "block_weights": res.weights,
            "block_names": active,
            #: score * weight, i.e. each block's additive share of the combined number.
            "block_contribution": scores * res.weights,
        }

    # -- helpers ---------------------------------------------------------------------

    def _coverage_col(self, df: pd.DataFrame, m: str) -> np.ndarray:
        if m == self.EARLY_UNION:
            each = np.column_stack([self._coverage_col(df, k) for k in self.blocks])
            return each.max(axis=1)
        key = {"microstructure": "cov_micro"}.get(m, "cov_%s" % m)
        if key in df.columns:
            return df[key].fillna(0.0).to_numpy(dtype=float)
        return np.ones(len(df))

    def _regime(self, df: pd.DataFrame) -> np.ndarray | None:
        if "regime_id" not in df.columns:
            return None
        r = df["regime_id"].fillna(0).to_numpy()
        return np.clip(r.astype(int), 0, self.n_regimes - 1)

    def summary(self) -> pd.DataFrame:
        rows = []
        for m, lr in self.learners.items():
            w = np.nan
            if self.combiner is not None and m in self.combiner.blocks:
                i = self.combiner.blocks.index(m)
                w = float(self.combiner.logits_[i]) if self.combiner.logits_ is not None \
                    else np.nan
            rows.append({"block": m, "status": lr.status, "n_train": lr.n_train,
                         "n_features": len(lr.columns),
                         "n_dropped_all_nan": lr.n_dropped_all_nan,
                         "combiner_logit": w})
        return pd.DataFrame(rows)
