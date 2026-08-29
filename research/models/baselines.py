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

PLAIN ENGLISH -- what this whole file is about:

BASELINES: the competitors your clever new thing has to beat.

Suppose you build an elaborate system and it gets 80% right. Is that good? You have
absolutely no idea until you know what SIMPLE things score. If just looking at trading
volume with no learning at all gets 78%, then all that machinery bought you two points,
and you should say so.

THE DISHONEST WAY TO PICK BASELINES -- and it is extremely common, usually without any
conscious intent to deceive -- is to choose weak ones. Compare your system against
something feeble, win by a mile, and report a triumph. Nothing you wrote is false. The
comparison is simply rigged by the choice of opponent.

THIS FILE DOES THE OPPOSITE, and says so out loud: the baselines are chosen to be STRONG.
One of them is the same powerful learner as the real model, just given a single family of
evidence. That is a genuinely serious opponent. And then comes the sentence that matters
most in the whole file:

    "if the full model cannot beat it then that is the result to report"

Deciding in advance to publish a disappointing result is what separates research from
marketing.

THE SIX COMPETITORS:
 1. statistical_anomaly -- no learning at all. Just "is trading unusually heavy and did
    the price move oddly?". The floor. If the fancy model cannot beat THIS, it has
    achieved nothing whatsoever.
 2-5. Each family of evidence on its own, through the same strong learner. These answer
    "did combining the families actually help, or was one of them doing all the work?"
 6. single_block_best -- takes whichever single family turned out best AFTER seeing the
    answers. That is cheating, and it is labelled as cheating. It exists as a deliberately
    unfair upper bar: if the real model beats even this, the result is very solid indeed.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The file that knows which measurements belong to which family.
from research.data import dataset as ds

# A label for this version of the baselines.
BASELINE_VERSION = "baselines-v1"


@dataclass
# One competitor's results.
class BaselineResult:
    # Its name.
    name: str
    # Its scores on the practice data...
    train_score: np.ndarray
    # ...and on the test data. Both are kept, because a competitor that does brilliantly
    # on practice and badly on the test has memorised rather than learned, and keeping only
    # one of the two would hide that.
    eval_score: np.ndarray
    # How it got on.
    status: str = "OK"
    # Any remark worth recording.
    note: str = ""


# COMPETITOR 1: no learning at all.
def statistical_anomaly(train: pd.DataFrame, evald: pd.DataFrame,
                        y_train: np.ndarray) -> BaselineResult:
    """Unlearned composite z-score, squashed to [0, 1] by a logistic.

    Scale is set from the *training* split only, so the eval split cannot influence the
    operating range.
    """
    # PLAIN ENGLISH on that second sentence, which is a real point-in-time discipline. Even
    # something as innocent as "what counts as an average value" must be worked out from the
    # practice data alone. Using the test data to set the scale would leak information from
    # the exam into the revision, and the leak would be completely invisible in the result.

    # A little helper that computes the raw suspicion score for a table.
    def raw(df):
        # How unusual today's trading was, on three measures, averaged.
        cols = [c for c in ("turnover_z_21", "volume_z_21", "trades_z_21") if c in df]
        # Missing values count as zero -- i.e. "not unusual" -- which is the conservative
        # reading for a baseline that is meant to be simple and honest rather than clever.
        z = df[cols].fillna(0.0).to_numpy().mean(axis=1) if cols else np.zeros(len(df))
        # And how far the price moved compared with everything else. `.abs()` because a big
        # move in either direction is equally interesting.
        ab = df["abnormal_ret_21"].fillna(0.0).abs().to_numpy() \
            if "abnormal_ret_21" in df else np.zeros(len(df))
        # Mix them 60/40. Round numbers, chosen up front and not tuned -- which is right for
        # a baseline, since a baseline that has been optimised is no longer a fair floor.
        return 0.6 * z + 0.4 * ab

    r_tr = raw(train)
    # The middle and spread of those raw scores, from the PRACTICE data only.
    # `or 1.0` guards against a spread of zero, which would mean dividing by zero below.
    mu, sd = float(np.nanmean(r_tr)), float(np.nanstd(r_tr) or 1.0)
    # A little inline action that squashes any number onto a 0-to-1 scale using the logistic
    # curve, so the output is comparable with the real model's probabilities.
    f = lambda r: 1.0 / (1.0 + np.exp(-(r - mu) / sd))
    return BaselineResult("statistical_anomaly", f(r_tr), f(raw(evald)),
                          note="unlearned; scale fitted on train split only")


# A shared helper for the single-family competitors, so all four are genuinely identical
# except for which measurements they see.
def _learner(train: pd.DataFrame, evald: pd.DataFrame, y: np.ndarray,
             cols: list[str], name: str, seed: int = 20260818) -> BaselineResult:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    # Keep only the measurements that exist and are not entirely empty.
    cols = [c for c in cols if c in train.columns and train[c].notna().any()]
    # Nothing usable, or only one kind of answer? Report a clean failure with 0.5
    # everywhere -- so the competitor still appears in the results table, marked FAILED,
    # rather than silently vanishing from it.
    if not cols or len(np.unique(y)) < 2:
        return BaselineResult(name, np.full(len(train), 0.5), np.full(len(evald), 0.5),
                              status="FAILED", note="no usable columns or single class")
    # EXACTLY the same learner settings the real model uses. That is what makes this a fair
    # fight: the only difference is how much evidence it is allowed to see.
    base = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=4,
                                          l2_regularization=1.0, random_state=seed)
    # And the same calibration rule -- the flexible method with plenty of data, the safe one
    # otherwise.
    m = CalibratedClassifierCV(base, method="isotonic" if len(train) >= 800
                               else "sigmoid", cv=3)
    m.fit(train[cols], y)
    # Score both the practice and the test data.
    return BaselineResult(name, m.predict_proba(train[cols])[:, 1],
                          m.predict_proba(evald[cols])[:, 1])


# COMPETITOR 2: prices only.
def market_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.MARKET_BLOCK, "market_only", seed)


# COMPETITOR 3: trading detail only.
def micro_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.MICRO_BLOCK, "micro_only", seed)


# COMPETITOR 4: market mood only.
def regime_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.REGIME_BLOCK, "regime_only", seed)


# COMPETITOR 5: contagion from other companies only.
def propagation_only(train, evald, y, seed: int = 20260818) -> BaselineResult:
    return _learner(train, evald, y, ds.PROPAGATION_BLOCK, "propagation_only", seed)


# The list of every competitor, by name.
ALL_BASELINES = {
    # The first one takes no seed, since it does no learning and so has no randomness. The
    # little wrapper lets it be called the same way as the others, so the loop below does
    # not need a special case.
    "statistical_anomaly": lambda tr, ev, y, s: statistical_anomaly(tr, ev, y),
    "market_only": market_only,
    "micro_only": micro_only,
    "regime_only": regime_only,
    "propagation_only": propagation_only,
}


# Run every competitor.
def run_all(train: pd.DataFrame, evald: pd.DataFrame, y_train: np.ndarray,
            seed: int = 20260818) -> dict[str, BaselineResult]:
    out = {}
    for name, fn in ALL_BASELINES.items():
        try:
            out[name] = fn(train, evald, y_train, seed)
        except Exception as exc:
            # If one competitor crashes, record the failure and carry on with the rest.
            # Crucially it still appears in the results, marked FAILED and carrying the
            # actual error text. Had it simply been skipped, the results table would silently
            # have one fewer row -- and a missing row is very easy not to notice, especially
            # if the missing competitor was the one that would have won.
            out[name] = BaselineResult(name, np.full(len(train), np.nan),
                                       np.full(len(evald), np.nan), status="FAILED",
                                       note="%s: %s" % (type(exc).__name__, exc))
    return out
