"""Baselines (spec section 72).

Chosen so that the comparison is honest rather than flattering. Three of them are
deliberately strong -- a market-only gradient booster is a serious competitor on this
task, and if the full model cannot beat it then that is the result to report.

``statistical_anomaly``   no learning at all: a z-score composite of turnover and
                          abnormal return. The bar any ML model must clear.
``market_only``           the market block through the same learner.
``micro_only``            the microstructure block through the same learner.
``regime_only``           the regime block through the same learner.
``propagation_only``      the cross-instrument stress block through the same learner.
``single_block_best``     post-hoc best single block; an optimistic baseline that uses
                          information (which block wins) not available at training time,
                          and is labelled as such.

The combination-rule variants (static, regime-inherited, regime-corrected,
uncertainty-aware) are not baselines in the usual sense -- they are arms of the same
model and are produced by the ablation runner.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.data import dataset as ds

BASELINE_VERSION = "baselines-v1"


@dataclass
class BaselineResult:
    name: str
    train_score: np.ndarray
    eval_score: np.ndarray
    status: str = "OK"
    note: str = ""


def statistical_anomaly(train: pd.DataFrame, evald: pd.DataFrame,
                        y_train: np.ndarray) -> BaselineResult:
    """Unlearned composite z-score, squashed to [0, 1] by a logistic.

    Scale is set from the *training* split only, so the eval split cannot influence the
    operating range.
    """
    def raw(df):
        cols = [c for c in ("turnover_z_21", "volume_z_21", "trades_z_21") if c in df]
        z = df[cols].fillna(0.0).to_numpy().mean(axis=1) if cols else np.zeros(len(df))
        ab = df["abnormal_ret_21"].fillna(0.0).abs().to_numpy() \
            if "abnormal_ret_21" in df else np.zeros(len(df))
        return 0.6 * z + 0.4 * ab

    r_tr = raw(train)
    mu, sd = float(np.nanmean(r_tr)), float(np.nanstd(r_tr) or 1.0)
    f = lambda r: 1.0 / (1.0 + np.exp(-(r - mu) / sd))
    return BaselineResult("statistical_anomaly", f(r_tr), f(raw(evald)),
                          note="unlearned; scale fitted on train split only")


def _learner(train: pd.DataFrame, evald: pd.DataFrame, y: np.ndarray,
             cols: list[str], name: str, seed: int = 20260818) -> BaselineResult:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    cols = [c for c in cols if c in train.columns and train[c].notna().any()]
    if not cols or len(np.unique(y)) < 2:
        return BaselineResult(name, np.full(len(train), 0.5), np.full(len(evald), 0.5),
                              status="FAILED", note="no usable columns or single class")
    base = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=4,
                                          l2_regularization=1.0, random_state=seed)
    m = CalibratedClassifierCV(base, method="isotonic" if len(train) >= 800
                               else "sigmoid", cv=3)
    m.fit(train[cols], y)
    return BaselineResult(name, m.predict_proba(train[cols])[:, 1],
                          m.predict_proba(evald[cols])[:, 1])


def market_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.MARKET_BLOCK, "market_only", seed)


def micro_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.MICRO_BLOCK, "micro_only", seed)


def regime_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.REGIME_BLOCK, "regime_only", seed)


def propagation_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.PROPAGATION_BLOCK, "propagation_only", seed)


ALL_BASELINES = {
    "statistical_anomaly": lambda tr, ev, y, s: statistical_anomaly(tr, ev, y),
    "market_only": market_only,
    "micro_only": micro_only,
    "regime_only": regime_only,
    "propagation_only": propagation_only,
}


def run_all(train: pd.DataFrame, evald: pd.DataFrame, y_train: np.ndarray,
            seed: int = 20260818) -> dict[str, BaselineResult]:
    out = {}
    for name, fn in ALL_BASELINES.items():
        try:
            out[name] = fn(train, evald, y_train, seed)
        except Exception as exc:
            out[name] = BaselineResult(name, np.full(len(train), np.nan),
                                       np.full(len(evald), np.nan), status="FAILED",
                                       note="%s: %s" % (type(exc).__name__, exc))
    return out
