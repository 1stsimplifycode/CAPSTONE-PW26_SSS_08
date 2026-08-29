"""XAI sanity checks (spec section 24).

Adapted from the model- and data-randomisation tests of Adebayo et al. (2018), applied to
tabular attributions rather than saliency maps.

The logic is simple and unforgiving. If an attribution method produces nearly the same
explanation for a *randomised* model, then the explanation is a description of the input
data and not of the model's reasoning, and it must not be presented as insight into the
model however plausible it looks.

Pass criteria used throughout this repository, chosen before running anything:

============================  =====================================================
check                          passes when
============================  =====================================================
model randomisation            Spearman(original, randomised) < 0.5
label randomisation            Spearman(original, label-randomised) < 0.5
attribution sparsity           top-10 features carry >= 25 % of |attribution| mass
sign consistency               repeated runs agree on sign for >= 80 % of features
============================  =====================================================
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.xai.methods import Attribution

SANITY_VERSION = "xai-sanity-v1"

MODEL_RANDOMISATION_MAX_RHO = 0.5
LABEL_RANDOMISATION_MAX_RHO = 0.5
MIN_TOP10_MASS = 0.25
MIN_SIGN_CONSISTENCY = 0.80


@dataclass
class SanityResult:
    check: str
    statistic: float
    threshold: float
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return {"check": self.check, "statistic": self.statistic,
                "threshold": self.threshold, "passed": bool(self.passed),
                "detail": self.detail}


def model_randomisation(original: Attribution, randomised: Attribution) -> SanityResult:
    n = min(len(original.values), len(randomised.values))
    rho = spearmanr(original.values[:n], randomised.values[:n]).statistic
    rho = float(rho) if rho == rho else 0.0
    return SanityResult(
        "model_randomisation", rho, MODEL_RANDOMISATION_MAX_RHO,
        abs(rho) < MODEL_RANDOMISATION_MAX_RHO,
        "Spearman between attributions from the fitted model and from a model refitted "
        "on shuffled targets; a high value means the explanation ignores the model")


def label_randomisation(original: Attribution, randomised: Attribution) -> SanityResult:
    n = min(len(original.values), len(randomised.values))
    rho = spearmanr(original.values[:n], randomised.values[:n]).statistic
    rho = float(rho) if rho == rho else 0.0
    return SanityResult(
        "label_randomisation", rho, LABEL_RANDOMISATION_MAX_RHO,
        abs(rho) < LABEL_RANDOMISATION_MAX_RHO,
        "Spearman against a model trained on permuted labels")


def sparsity(attr: Attribution, k: int = 10) -> SanityResult:
    v = np.abs(attr.values)
    total = v.sum()
    frac = float(np.sort(v)[-k:].sum() / total) if total > 0 else 0.0
    return SanityResult("attribution_sparsity", frac, MIN_TOP10_MASS,
                        frac >= MIN_TOP10_MASS,
                        "share of absolute attribution mass carried by the top %d "
                        "features; a flat attribution explains nothing" % k)


def sign_consistency(runs: list[Attribution]) -> SanityResult:
    if len(runs) < 2:
        return SanityResult("sign_consistency", np.nan, MIN_SIGN_CONSISTENCY, False,
                            "needs at least two runs")
    M = np.sign(np.vstack([r.values for r in runs]))
    majority = np.sign(M.sum(axis=0))
    agree = float(np.mean((majority == M).mean(axis=0)))
    return SanityResult("sign_consistency", agree, MIN_SIGN_CONSISTENCY,
                        agree >= MIN_SIGN_CONSISTENCY,
                        "mean fraction of runs agreeing with the majority sign per feature")


def randomised_model_predict(X: np.ndarray, y: np.ndarray, seed: int = 20260818
                             ) -> Callable[[np.ndarray], np.ndarray]:
    """Refit the same learner class on shuffled targets and return its predict_proba.

    Shuffling the targets rather than the weights keeps the model class, the
    hyperparameters and the input distribution fixed, so any change in the attribution is
    attributable to the model having learned nothing.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    rng = np.random.default_rng(seed)
    yp = y.copy()
    rng.shuffle(yp)
    m = HistGradientBoostingClassifier(max_iter=120, max_depth=4, random_state=seed)
    m.fit(np.nan_to_num(X, nan=0.0), yp)
    return lambda Z: m.predict_proba(np.nan_to_num(Z, nan=0.0))[:, 1]


def run_suite(original: Attribution, model_random: Attribution | None,
              label_random: Attribution | None,
              repeat_runs: list[Attribution] | None = None) -> pd.DataFrame:
    checks: list[SanityResult] = [sparsity(original)]
    if model_random is not None:
        checks.append(model_randomisation(original, model_random))
    if label_random is not None:
        checks.append(label_randomisation(original, label_random))
    if repeat_runs:
        checks.append(sign_consistency(repeat_runs))
    return pd.DataFrame([c.to_dict() for c in checks])
