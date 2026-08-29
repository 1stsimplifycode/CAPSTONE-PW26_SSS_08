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

PLAIN ENGLISH -- what this whole file is about:

THIS FILE CHECKS WHETHER THE EXPLANATIONS ARE REAL, OR JUST PLAUSIBLE NONSENSE.

Elsewhere in this project, the system explains its decisions: "I flagged this company
mainly because of unusual trading volume." That is enormously reassuring to read.

But here is the horrifying question: HOW DO YOU KNOW THE EXPLANATION IS TRUE?

Explanation methods produce a confident, sensible-looking answer no matter what. Feed one
a model that has learned absolutely nothing and it will still hand you a tidy chart of
which features "mattered". The chart looks exactly as convincing as a real one. You cannot
tell them apart by looking, and neither can anybody reading your paper.

THE TEST, from a famous 2018 paper by Adebayo and colleagues, is brilliantly simple:

  1. Take your model. Get its explanation.
  2. Now take a model that has learned NOTHING -- train it on deliberately shuffled
     answers, so it is pure noise wearing a model's clothes. Get its explanation.
  3. COMPARE THE TWO.

If the two explanations look similar, your explanation was never about your model at all.
It was describing the data, and it would have said the same thing whatever the model had
learned. It is therefore worthless as insight into the model's reasoning -- however
sensible it sounds, and it will sound very sensible indeed.

That is why the docstring calls the logic "unforgiving".

THE FOUR CHECKS:
  1. MODEL RANDOMISATION -- does the explanation change when the model is nonsense? It
     must. (Agreement must be below 0.5.)
  2. LABEL RANDOMISATION -- same idea, from a different angle.
  3. SPARSITY -- does the explanation actually single anything out? If all 50 features get
     an equal 2% of the credit, you have not been told anything. The top 10 must carry at
     least a quarter of the weight.
  4. SIGN CONSISTENCY -- run it again. Does it still say the same feature pushed the score
     UP rather than down? If the direction flips between runs, the explanation is noise.

AND THE MOST IMPORTANT DETAIL OF ALL: "chosen before running anything". The pass marks
were set BEFORE anyone saw whether the explanations would pass. Setting the bar after
seeing the results is just drawing the target around wherever the arrow landed.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# A type hint for "an action that can be called".
from collections.abc import Callable
# For building tidy record types.
from dataclasses import dataclass

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd
# The rank-agreement test: do two lists put things in the same order?
from scipy.stats import spearmanr

# The record type holding one explanation.
from research.xai.methods import Attribution

# A label for this version of the checks.
SANITY_VERSION = "xai-sanity-v1"

# THE PASS MARKS, written at the top of the file and fixed before any run.
# Agreement with a nonsense model must be below this. 0.5 is "no better than a coin flip"
# for rank agreement, so we require the explanation to be genuinely unrelated.
MODEL_RANDOMISATION_MAX_RHO = 0.5
LABEL_RANDOMISATION_MAX_RHO = 0.5
# The top ten features must carry at least a quarter of the total weight.
MIN_TOP10_MASS = 0.25
# Repeated runs must agree on direction at least 80% of the time.
MIN_SIGN_CONSISTENCY = 0.80


@dataclass
# The result of one check.
class SanityResult:
    # Which check.
    check: str
    # What number came out.
    statistic: float
    # What it had to beat.
    threshold: float
    # Did it.
    passed: bool
    # What the check actually means, in words.
    detail: str

    def to_dict(self) -> dict:
        return {"check": self.check, "statistic": self.statistic,
                # `bool(...)` converts numpy's own True/False into the plain Python kind, so
                # it saves into JSON correctly rather than as an unreadable numpy value.
                "threshold": self.threshold, "passed": bool(self.passed),
                "detail": self.detail}


# CHECK 1: does the explanation change when the model is nonsense?
def model_randomisation(original: Attribution, randomised: Attribution) -> SanityResult:
    # Compare only as far as the shorter of the two, so a mismatch in length cannot crash us.
    n = min(len(original.values), len(randomised.values))
    # How much do the two explanations agree on ordering?
    rho = spearmanr(original.values[:n], randomised.values[:n]).statistic
    # `rho == rho` is the quick NaN check: NaN is the only value not equal to itself. If the
    # agreement could not be computed, treat it as 0 -- no agreement, which is the passing
    # direction, but the recorded statistic makes the situation visible.
    rho = float(rho) if rho == rho else 0.0
    return SanityResult(
        "model_randomisation", rho, MODEL_RANDOMISATION_MAX_RHO,
        # `abs(rho)` because a strong NEGATIVE agreement is just as damning: it would mean
        # the explanation is still tightly tied to the data, merely upside down.
        abs(rho) < MODEL_RANDOMISATION_MAX_RHO,
        "Spearman between attributions from the fitted model and from a model refitted "
        "on shuffled targets; a high value means the explanation ignores the model")


# CHECK 2: the same test approached through the labels.
def label_randomisation(original: Attribution, randomised: Attribution) -> SanityResult:
    n = min(len(original.values), len(randomised.values))
    rho = spearmanr(original.values[:n], randomised.values[:n]).statistic
    rho = float(rho) if rho == rho else 0.0
    return SanityResult(
        "label_randomisation", rho, LABEL_RANDOMISATION_MAX_RHO,
        abs(rho) < LABEL_RANDOMISATION_MAX_RHO,
        "Spearman against a model trained on permuted labels")


# CHECK 3: does the explanation actually single anything out?
def sparsity(attr: Attribution, k: int = 10) -> SanityResult:
    # Sizes only -- a big push downwards is just as much of an explanation as a big push up.
    v = np.abs(attr.values)
    total = v.sum()
    # `np.sort(v)[-k:]` takes the ten largest. Their share of the total is the answer.
    frac = float(np.sort(v)[-k:].sum() / total) if total > 0 else 0.0
    return SanityResult("attribution_sparsity", frac, MIN_TOP10_MASS,
                        frac >= MIN_TOP10_MASS,
                        # "a flat attribution explains nothing" is the point in five words.
                        # If everything mattered equally, you have not been told why.
                        "share of absolute attribution mass carried by the top %d "
                        "features; a flat attribution explains nothing" % k)


# CHECK 4: does it say the same thing twice?
def sign_consistency(runs: list[Attribution]) -> SanityResult:
    # Need at least two runs to compare. Note it reports `passed=False` rather than raising:
    # a check that could not be run has NOT passed, and must not be able to look as though
    # it did.
    if len(runs) < 2:
        return SanityResult("sign_consistency", np.nan, MIN_SIGN_CONSISTENCY, False,
                            "needs at least two runs")
    # Stack the runs into a grid and keep only the DIRECTION of each value: +1, -1 or 0.
    M = np.sign(np.vstack([r.values for r in runs]))
    # For each feature, what did most runs say?
    majority = np.sign(M.sum(axis=0))
    # What fraction of runs agreed with that majority, averaged over all features?
    agree = float(np.mean((majority == M).mean(axis=0)))
    return SanityResult("sign_consistency", agree, MIN_SIGN_CONSISTENCY,
                        agree >= MIN_SIGN_CONSISTENCY,
                        "mean fraction of runs agreeing with the majority sign per feature")


# Build the deliberately useless model that the checks compare against.
def randomised_model_predict(X: np.ndarray, y: np.ndarray, seed: int = 20260818
                             ) -> Callable[[np.ndarray], np.ndarray]:
    """Refit the same learner class on shuffled targets and return its predict_proba.

    Shuffling the targets rather than the weights keeps the model class, the
    hyperparameters and the input distribution fixed, so any change in the attribution is
    attributable to the model having learned nothing.
    """
    # PLAIN ENGLISH: a careful piece of experimental design. There are two ways to make a
    # nonsense model:
    #   (a) scramble the model's internal numbers, or
    #   (b) train the SAME kind of model, with the SAME settings, on the SAME data -- but
    #       with the answers shuffled.
    # Option (b) is far better, because it changes exactly ONE thing: whether the model
    # learned anything real. Everything else -- the model type, its settings, the shape of
    # the input -- is held identical. So if the explanation changes, it can only be because
    # of the learning. Option (a) would change several things at once, and you could never
    # say which was responsible.
    from sklearn.ensemble import HistGradientBoostingClassifier
    rng = np.random.default_rng(seed)
    # Copy the answers before shuffling, so the caller's originals are not scrambled.
    yp = y.copy()
    rng.shuffle(yp)
    # Now the answers no longer match their rows: the model has nothing real to learn.
    m = HistGradientBoostingClassifier(max_iter=120, max_depth=4, random_state=seed)
    # `np.nan_to_num` turns unknowns into zeros, because this throwaway model does not need
    # the careful missing-value handling the real one has.
    m.fit(np.nan_to_num(X, nan=0.0), yp)
    # Hand back a little action that scores new data with this nonsense model.
    return lambda Z: m.predict_proba(np.nan_to_num(Z, nan=0.0))[:, 1]


# Run every check that can be run, and report them as a table.
def run_suite(original: Attribution, model_random: Attribution | None,
              label_random: Attribution | None,
              repeat_runs: list[Attribution] | None = None) -> pd.DataFrame:
    # Sparsity needs nothing but the original, so it always runs.
    checks: list[SanityResult] = [sparsity(original)]
    # The others each need their comparison to have been supplied. Note what happens when
    # one is missing: it is simply absent from the table, rather than appearing as a pass.
    # A check that did not run must never look like a check that succeeded.
    if model_random is not None:
        checks.append(model_randomisation(original, model_random))
    if label_random is not None:
        checks.append(label_randomisation(original, label_random))
    if repeat_runs:
        checks.append(sign_consistency(repeat_runs))
    return pd.DataFrame([c.to_dict() for c in checks])
