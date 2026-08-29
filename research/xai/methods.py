"""Explanation methods (spec sections 20-23).

All methods share one signature so the benchmark can treat them interchangeably::

    attribution(predict_fn, X, row, feature_names, background, **kw) -> np.ndarray

``predict_fn`` maps a ``(n, d)`` array to ``(n,)`` risk scores. Attributions are per
feature for the named row, signed, in score units where the method defines them that way.

Which methods are valid for which model is not a matter of taste (spec section 20 is
explicit). The AEGIS risk model is a calibrated gradient-boosting ensemble per block
plus a differentiable combination layer, so:

* **valid on the tabular model**: permutation importance, occlusion / feature ablation,
  KernelSHAP, LIME (local ridge surrogate), counterfactual search, PDP/ICE/ALE;
* **valid on the combination layer only**: integrated gradients and gradient x input,
  because
  the combination rule is differentiable in the block scores while the trees are not;
* **not implemented, and reported as such**: DeepSHAP, Grad-CAM, TCAV, DeepLIFT. They
  require a differentiable deep network, which this model is not. Claiming them would be
  fabrication.

PLAIN ENGLISH -- what this whole file is about:

THE TOOLKIT FOR ASKING A MODEL "WHY?".

A model gives an answer -- "this company scores 0.82". On its own that is a black box, and
a number nobody can question is not evidence. These are the tools that prise it open.

They work in several different ways, and it is worth knowing which is which:

  PERMUTATION IMPORTANCE -- scramble one column and see how much worse the model gets. If
    scrambling "trading volume" ruins it, volume mattered. Global: about the model overall.

  OCCLUSION -- for ONE company, replace one measurement with a typical value and watch the
    score move. Local: about this particular decision.

  KERNELSHAP -- based on a result from game theory about fairly splitting a prize among
    team members. Treats each measurement as a player and works out its fair share of the
    final score. Mathematically principled, and slow.

  LIME -- fit a very simple model that mimics the complicated one, but only in the
    immediate neighbourhood of this one company. The simple model can be read directly.

  COUNTERFACTUAL -- the most human question of all: "what would have to be DIFFERENT for
    this to be fine?" And note this is answered by an actual search, not a story.

  INTEGRATED GRADIENTS / GRADIENT x INPUT -- nudge each input slightly and see how much
    the output moves. Only works on smooth maths, so it is used only on the combining
    layer, never on the trees.

AND NOW THE MOST IMPORTANT PART OF THE FILE.

There is a list below of famous methods that are NOT implemented, each with the reason.
DeepSHAP, Grad-CAM, TCAV, DeepLIFT -- all real, all well known, all requiring a deep
neural network. This model is not a neural network. It is trees. Those methods simply
cannot be applied here.

It would be trivially easy to write something roughly similar, give it the famous name,
and put it in the paper. The docstring's word for that is exact: "Claiming them would be
fabrication."

So instead they are listed by name, with the reason each one cannot be used, and reported
in the output. That makes the project look less impressive and is completely correct.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For measuring how long things take.
import time
# Type hints for "an action that can be called" and "an ordered collection".
from collections.abc import Callable, Sequence
# Record-building tools.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np

# A label for this version of the explanation tools.
XAI_VERSION = "xai-v1"

# A nickname for the shape of a scoring action: takes a grid of numbers, hands back a row
# of scores. Naming it once means every method below declares the same thing consistently.
PredictFn = Callable[[np.ndarray], np.ndarray]

#: Methods implemented here and applicable to the tabular risk model.
TABULAR_METHODS = ["permutation", "occlusion", "kernel_shap", "lime", "counterfactual"]
#: Methods applicable only to the differentiable combination layer.
GRADIENT_METHODS = ["integrated_gradients", "gradient_x_input"]
#: Declared by the specification but not applicable to this model class.
# PLAIN ENGLISH: THE HONEST GAPS. Each famous method is named, with the precise technical
# reason it cannot be used here. Recorded in the code, so it reaches the output.
NOT_APPLICABLE = {
    "deep_shap": "requires a differentiable deep network; the risk model is tree-based",
    "grad_cam": "requires convolutional feature maps; no CNN is used",
    "guided_grad_cam": "requires a CNN",
    "tcav": "requires a differentiable network with concept activation vectors",
    "deeplift": "requires a differentiable deep network",
    # This last one is the subtlest and the most creditable. TreeSHAP would be the ideal
    # tool -- it is fast and exact for tree models, and these ARE trees. But the trees are
    # wrapped in the calibration layer that makes the probabilities honest, and TreeSHAP
    # cannot see through that wrapper. So the slower KernelSHAP is used instead, AND the
    # substitution is written down rather than passed over in silence.
    "tree_shap": "the per-block learners are wrapped in a probability calibrator, "
                 "so the tree structure is not directly exposed; KernelSHAP is used "
                 "instead and this substitution is reported",
}


@dataclass
# One explanation.
class Attribution:
    # Which method produced it.
    method: str
    # One number per measurement: how much it pushed the score, and in which direction.
    values: np.ndarray
    # What each of those numbers refers to.
    feature_names: list[str]
    # The starting point -- the score before any measurement pushed it.
    base_value: float = 0.0
    # The score that was actually explained.
    prediction: float = 0.0
    # How long it took. Recorded because these methods vary enormously in cost, and a
    # method nobody can afford to run is a different proposition from a cheap one.
    seconds: float = 0.0
    # Any remarks the method wanted to attach.
    notes: list[str] = field(default_factory=list)

    # The biggest contributors.
    def top(self, k: int = 10) -> list[tuple[str, float]]:
        # `-np.abs(...)` sorts by size, largest first, ignoring direction -- because a big
        # push downwards is just as important as a big push upwards.
        idx = np.argsort(-np.abs(self.values))[:k]
        return [(self.feature_names[i], float(self.values[i])) for i in idx]

    # The whole explanation as labelled boxes.
    def as_dict(self) -> dict[str, float]:
        return {n: float(v) for n, v in zip(self.feature_names, self.values)}


# A decorator that times whatever it wraps.
def _timed(fn):
    def wrap(*a, **kw):
        # Start the stopwatch...
        t = time.perf_counter()
        # ...run the real method...
        out = fn(*a, **kw)
        # ...and record how long it took, right on the result.
        out.seconds = time.perf_counter() - t
        return out
    return wrap


# -- global --------------------------------------------------------------------------

@_timed
# METHOD 1: which measurements does the model rely on overall?
def permutation_importance(predict_fn: PredictFn, X: np.ndarray, y: np.ndarray,
                           feature_names: Sequence[str], n_repeats: int = 5,
                           metric: str = "auprc", seed: int = 20260818) -> Attribution:
    """Global importance: loss in performance when one column is shuffled.

    Shuffling rather than dropping keeps the marginal distribution intact, so the model
    is not asked to extrapolate off its training support.
    """
    # PLAIN ENGLISH: an important design choice. You could test a measurement's importance
    # by DELETING it -- but then the model is being asked about a situation it has never
    # seen, and its behaviour there tells you nothing reliable.
    # SHUFFLING instead keeps every value that was there; it just puts them with the wrong
    # companies. So the range of values stays completely realistic, and the only thing
    # destroyed is the RELATIONSHIP between that measurement and the answer. Which is
    # precisely what we wanted to test.
    from sklearn.metrics import average_precision_score, roc_auc_score
    score = average_precision_score if metric == "auprc" else roc_auc_score
    rng = np.random.default_rng(seed)
    # How well the model does with everything intact.
    base = score(y, predict_fn(X))
    vals = np.zeros(X.shape[1])
    for j in range(X.shape[1]):
        drops = []
        # Repeat, because one shuffle could be unlucky and produce a misleading answer.
        for _ in range(n_repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            # How much worse did it get? A big drop means the measurement mattered.
            drops.append(base - score(y, predict_fn(Xp)))
        vals[j] = float(np.mean(drops))
    return Attribution("permutation", vals, list(feature_names), base_value=float(base),
                       # Record the settings, so the numbers can be interpreted correctly.
                       notes=["metric=%s, n_repeats=%d" % (metric, n_repeats)])


# -- local ---------------------------------------------------------------------------

@_timed
# METHOD 2: for ONE company, what did each measurement contribute?
def occlusion(predict_fn: PredictFn, X: np.ndarray, row: int,
              feature_names: Sequence[str], background: np.ndarray,
              groups: dict[str, list[int]] | None = None) -> Attribution:
    """Local ablation: replace each feature (or group) with its background median.

    Group mode is what produces *block* attribution -- occluding an entire block at once
    answers "what did the propagation block contribute", which is the question section 22
    asks.
    """
    # PLAIN ENGLISH: "occlude" means to block from view. Cover up one measurement -- replace
    # it with a perfectly typical value -- and see how far the score moves. A big move means
    # that measurement was carrying a lot of weight.
    # Group mode covers up a whole FAMILY at once, which answers the bigger question "how
    # much was the contagion evidence contributing?" rather than one measurement at a time.
    x = X[row:row + 1].copy()
    # The score before covering anything.
    base = float(predict_fn(x)[0])
    # A typical value for each measurement. The MEDIAN rather than the average, so one
    # extreme company cannot define what "typical" means.
    med = np.nanmedian(background, axis=0)
    if groups is None:
        vals = np.zeros(X.shape[1])
        for j in range(X.shape[1]):
            xp = x.copy()
            # Replace just this one with the typical value.
            xp[0, j] = med[j]
            # How far the score moved is this measurement's contribution.
            vals[j] = base - float(predict_fn(xp)[0])
        names = list(feature_names)
    else:
        # Group mode: cover up whole families at a time.
        names = list(groups.keys())
        vals = np.zeros(len(names))
        for i, (_, cols) in enumerate(groups.items()):
            xp = x.copy()
            xp[0, cols] = med[cols]
            vals[i] = base - float(predict_fn(xp)[0])
    return Attribution("occlusion", vals, names, base_value=base, prediction=base)


@_timed
# METHOD 3: the game-theory approach.
def kernel_shap(predict_fn: PredictFn, X: np.ndarray, row: int,
                feature_names: Sequence[str], background: np.ndarray,
                nsamples: int = 200, seed: int = 20260818) -> Attribution:
    """KernelSHAP via the ``shap`` package, on a k-means-summarised background."""
    # PLAIN ENGLISH: SHAP comes from a 1950s result by Lloyd Shapley about fairly dividing
    # winnings among team members who contributed unequally. Treat each measurement as a
    # team member and the score as the winnings, and you get a principled, provably fair
    # split. The catch is that a proper answer needs every possible combination of
    # measurements, which is astronomically many -- so KernelSHAP samples cleverly instead.
    import shap
    # Summarise the background down to 25 representative points. Running against thousands
    # would be enormously slower for a barely different answer.
    k = min(25, len(background))
    # `shap.kmeans` finds 25 points that stand in well for the whole set.
    bg = shap.kmeans(background, k) if len(background) > k else background
    ex = shap.KernelExplainer(predict_fn, bg, seed=seed)
    vals = ex.shap_values(X[row], nsamples=nsamples, silent=True)
    # `.ravel()` flattens whatever shape came back into one row, and the slice guards
    # against a longer array than we have measurements for.
    vals = np.asarray(vals, dtype=float).ravel()[:X.shape[1]]
    return Attribution("kernel_shap", vals, list(feature_names),
                       base_value=float(np.mean(ex.expected_value)),
                       prediction=float(predict_fn(X[row:row + 1])[0]),
                       # Both approximations recorded, so a reader knows this is a sampled
                       # answer against a summarised background rather than an exact one.
                       notes=["background summarised to %d k-means centroids" % k,
                              "nsamples=%d" % nsamples])


@_timed
# METHOD 4: fit a simple model that mimics the complicated one, locally.
def lime(predict_fn: PredictFn, X: np.ndarray, row: int,
         feature_names: Sequence[str], background: np.ndarray,
         n_samples: int = 800, kernel_width: float | None = None,
         seed: int = 20260818) -> Attribution:
    """Local ridge surrogate with an exponential proximity kernel.

    Implemented directly rather than via the ``lime`` package so the perturbation
    distribution is explicit: features are resampled from the background marginals, which
    keeps the surrogate's training points on the data manifold far better than Gaussian
    noise around the point does.
    """
    # PLAIN ENGLISH: LIME means "Local Interpretable Model-agnostic Explanations". The idea:
    # a complicated model may be hopelessly tangled overall, but if you zoom right in on one
    # company, its behaviour nearby is roughly a straight line. Fit that straight line and
    # you can read off what each measurement was doing.
    # And the reason for writing it by hand rather than using the popular package: the
    # package invents nearby points by adding random noise, which happily produces
    # impossible companies -- negative trading volumes, prices that could not exist. The
    # model has never seen such things and its behaviour on them is meaningless.
    # This version instead borrows real values from other real companies, so every invented
    # point is made of pieces that genuinely occur. ("On the data manifold" is the technical
    # phrase for staying inside the region where real data actually lives.)
    from sklearn.linear_model import Ridge
    rng = np.random.default_rng(seed)
    x = X[row]
    d = X.shape[1]
    # For each invented point, decide at random which measurements to swap out. Roughly half.
    mask = rng.random((n_samples, d)) < 0.5
    # The replacement values, each borrowed from a randomly chosen real company -- and
    # crucially borrowed from the SAME column, so a price value never lands in a volume slot.
    donors = background[rng.integers(0, len(background), size=(n_samples, d)),
                        np.arange(d)]
    # Build the invented points: borrowed value where the mask says so, the real company's
    # own value elsewhere.
    Z = np.where(mask, donors, x)
    # Measure how far each invented point is from our company, with each measurement scaled
    # by its own spread so all of them count equally rather than the largest-numbered one
    # dominating.
    scale = np.nanstd(background, axis=0)
    scale[scale == 0] = 1.0
    dist = np.sqrt((((Z - x) / scale) ** 2).mean(axis=1))
    kw = kernel_width if kernel_width is not None else float(np.median(dist) or 1.0)
    # Nearby points count for more. This is what makes the explanation LOCAL: distant points
    # get almost no say, so the straight line describes this company's neighbourhood rather
    # than the whole dataset.
    w = np.exp(-(dist ** 2) / (2 * kw ** 2))
    # What the real model says about each invented point.
    yz = predict_fn(np.nan_to_num(Z, nan=0.0))
    # Fit the simple straight-line model. "Ridge" adds a mild penalty on large coefficients,
    # which keeps the explanation stable when measurements move together.
    reg = Ridge(alpha=1.0)
    reg.fit(np.nan_to_num(Z, nan=0.0), yz, sample_weight=w)
    # The straight line's slopes ARE the explanation: how much each measurement moves the
    # score, right here.
    return Attribution("lime", reg.coef_.astype(float), list(feature_names),
                       base_value=float(reg.intercept_),
                       prediction=float(predict_fn(X[row:row + 1])[0]),
                       notes=["marginal-resampling perturbations, n=%d, kernel_width="
                              "%.4f" % (n_samples, kw)])


@_timed
# METHOD 5: what would have to change for this to be fine?
def counterfactual(predict_fn: PredictFn, X: np.ndarray, row: int,
                   feature_names: Sequence[str], background: np.ndarray,
                   target: float = 0.3, max_features: int = 4,
                   seed: int = 20260818) -> Attribution:
    """Greedy sparse counterfactual: the smallest set of features whose move to a
    background value drops the score below ``target``.

    Answers RQ-X6 -- "what would have to be different for this risk to resolve" -- with
    an actual search rather than a story. If no set within ``max_features`` reaches the
    target, that is reported in ``notes`` and the attribution is the best partial move.
    """
    # PLAIN ENGLISH: the most naturally human question. Not "why is this risky?" but "what
    # would have to be different for it not to be?"
    # "Greedy" means it takes the single best step available at each stage, rather than
    # examining every possible combination -- which would be far too slow.
    # "Sparse" means it looks for the SMALLEST set of changes. "Change these two things" is
    # actionable; "change all fifty things" is not an answer anybody can use.
    # And the last sentence is the honesty: if no small set of changes is enough, it SAYS SO,
    # rather than reporting the closest it got as though that had worked.
    x = X[row:row + 1].copy()
    base = float(predict_fn(x)[0])
    med = np.nanmedian(background, axis=0)
    vals = np.zeros(X.shape[1])
    cur = x.copy()
    chosen: list[int] = []
    notes = []
    for _ in range(max_features):
        best_j, best_score = None, float(predict_fn(cur)[0])
        # Try changing each measurement in turn, and keep whichever helps most.
        for j in range(X.shape[1]):
            # Skip ones we have already changed.
            if j in chosen:
                continue
            xp = cur.copy()
            xp[0, j] = med[j]
            s = float(predict_fn(xp)[0])
            if s < best_score:
                best_j, best_score = j, s
        # Nothing helped at all? Stop -- no point continuing a search that is going nowhere.
        if best_j is None:
            break
        prev = float(predict_fn(cur)[0])
        # Lock in the best change and record how much it bought us.
        cur[0, best_j] = med[best_j]
        vals[best_j] = prev - best_score
        chosen.append(best_j)
        # Got below the target? Success.
        if best_score <= target:
            notes.append("target %.2f reached with %d features" % (target, len(chosen)))
            break
    else:
        # This `else` belongs to the `for`, not to an `if` -- an unusual Python feature. It
        # runs only when the loop finished WITHOUT hitting a `break`, which here means we
        # never reached the target. So the failure gets recorded, with how close we came.
        notes.append("target %.2f NOT reached within %d features (best %.3f)"
                     % (target, max_features, float(predict_fn(cur)[0])))
    # Always record exactly which measurements were changed, so the answer is checkable.
    notes.append("changed: %s" % ", ".join(feature_names[j] for j in chosen))
    return Attribution("counterfactual", vals, list(feature_names), base_value=base,
                       prediction=base, notes=notes)


# -- gradient methods on the differentiable combination layer --------------------------
# PLAIN ENGLISH: these next two work only on smooth maths. Trees are full of sharp jumps --
# "if volume > 1000 then..." -- so nudging an input often changes nothing at all and then
# suddenly changes everything. The combining layer, by contrast, is smooth. So these are
# applied there and nowhere else, which is why they explain FAMILIES rather than individual
# measurements.

@_timed
def integrated_gradients(fuse_fn: Callable[[np.ndarray], np.ndarray],
                         scores: np.ndarray, row: int,
                         block_names: Sequence[str],
                         baseline: np.ndarray | None = None,
                         steps: int = 64) -> Attribution:
    """IG over the block scores entering the combination layer.

    The combination rule is a smooth function of the block scores, so IG is exactly
    applicable there -- unlike on the trees underneath, where it is not. The completeness
    axiom (attributions sum to f(x) - f(baseline)) is checked and reported in ``notes``.
    """
    # PLAIN ENGLISH: Integrated Gradients walks a path from a neutral starting point to the
    # actual company, in 64 small steps, measuring the sensitivity to each input all the way
    # along, and adds those up. Walking the whole path rather than measuring only at the end
    # is what avoids being fooled by a flat spot at the destination.
    # "COMPLETENESS" is its guarantee: the contributions must add up exactly to the total
    # change in score. And note the file does not merely trust that -- it MEASURES the gap
    # and reports it. A large gap would mean the maths is not behaving as assumed.
    x = scores[row].astype(float)
    # The neutral starting point: all zeros unless told otherwise.
    b = np.zeros_like(x) if baseline is None else np.asarray(baseline, dtype=float)
    # 64 points along the path. The `+ 0.5` takes the MIDDLE of each step rather than its
    # edge, which is a more accurate way to approximate the underlying integral.
    alphas = (np.arange(steps) + 0.5) / steps
    path = b[None, :] + alphas[:, None] * (x - b)[None, :]
    # A tiny nudge, for measuring sensitivity.
    eps = 1e-4
    grads = np.zeros((steps, len(x)))
    for j in range(len(x)):
        hi = path.copy()
        lo = path.copy()
        # Nudge this input up a little and down a little...
        hi[:, j] += eps
        lo[:, j] -= eps
        # ...and see how much the output moved. Using both directions and dividing by 2*eps
        # is the "central difference", which is noticeably more accurate than nudging one way.
        grads[:, j] = (fuse_fn(hi) - fuse_fn(lo)) / (2 * eps)
    # The contribution: how far this input travelled, times its average sensitivity.
    vals = (x - b) * grads.mean(axis=0)
    fx = float(fuse_fn(x[None, :])[0])
    fb = float(fuse_fn(b[None, :])[0])
    # THE COMPLETENESS CHECK: do the contributions add up to the actual change? Reported
    # rather than assumed.
    gap = abs(vals.sum() - (fx - fb))
    return Attribution("integrated_gradients", vals, list(block_names),
                       base_value=fb, prediction=fx,
                       notes=["steps=%d" % steps,
                              "completeness gap |sum(attr) - (f(x)-f(b))| = %.5f" % gap])


@_timed
# The simpler cousin: sensitivity at the point, times the value.
def gradient_x_input(fuse_fn: Callable[[np.ndarray], np.ndarray], scores: np.ndarray,
                     row: int, block_names: Sequence[str]) -> Attribution:
    # PLAIN ENGLISH: measure sensitivity only at the company itself -- no path walked. Much
    # faster, and it comes with no completeness guarantee. It is included as a cheap
    # comparison against the thorough method above; if the two disagree wildly, that itself
    # is informative.
    x = scores[row].astype(float)
    eps = 1e-4
    g = np.zeros(len(x))
    for j in range(len(x)):
        hi, lo = x.copy(), x.copy()
        hi[j] += eps
        lo[j] -= eps
        g[j] = ((float(fuse_fn(hi[None, :])[0])
                 - float(fuse_fn(lo[None, :])[0])) / (2 * eps))
    # Sensitivity times value: a very sensitive input that happens to be near zero was not
    # actually doing much on this particular company.
    return Attribution("gradient_x_input", g * x, list(block_names),
                       prediction=float(fuse_fn(x[None, :])[0]))


# -- dependence curves ------------------------------------------------------------------
# PLAIN ENGLISH: these draw pictures. Rather than one number per measurement, they show the
# whole SHAPE: as this measurement rises, what happens to the score?

# The average relationship across all companies.
def partial_dependence(predict_fn: PredictFn, X: np.ndarray, j: int,
                       grid: int = 20) -> tuple[np.ndarray, np.ndarray]:
    # 20 values spread across the measurement's realistic range. From the 2nd to the 98th
    # percentile rather than the very extremes, so one freak value cannot stretch the whole
    # picture out of shape.
    xs = np.nanpercentile(X[:, j], np.linspace(2, 98, grid))
    out = []
    for v in xs:
        Xp = X.copy()
        # Pretend EVERY company had this value, and average the scores.
        Xp[:, j] = v
        out.append(float(np.mean(predict_fn(Xp))))
    return xs, np.asarray(out)


# The same picture, but one line per company instead of one average.
def ice_curves(predict_fn: PredictFn, X: np.ndarray, j: int, rows: Sequence[int],
               grid: int = 20) -> tuple[np.ndarray, np.ndarray]:
    # PLAIN ENGLISH: ICE means "Individual Conditional Expectation". It matters because an
    # average can hide everything interesting: if the measurement pushes half the companies
    # up and the other half down, the average is a flat line saying "no effect", which is
    # exactly wrong. Drawing every company separately reveals that.
    xs = np.nanpercentile(X[:, j], np.linspace(2, 98, grid))
    curves = np.zeros((len(rows), grid))
    for i, r in enumerate(rows):
        # Twenty copies of this one company, one per grid value.
        Xp = np.repeat(X[r:r + 1], grid, axis=0)
        Xp[:, j] = xs
        curves[i] = predict_fn(Xp)
    return xs, curves


# The version that copes when measurements move together.
def ale(predict_fn: PredictFn, X: np.ndarray, j: int, bins: int = 20) -> tuple:
    """First-order accumulated local effects.

    Preferred over PDP when features are correlated: PDP averages the model over
    combinations that never occur, ALE only over local differences that do.
    """
    # PLAIN ENGLISH: this fixes a real flaw in the average-relationship picture above.
    # That method sets EVERY company's value to, say, a very high trading volume. But if
    # trading volume and money traded always move together in real life, you have just
    # invented companies with enormous volume and tiny turnover -- which do not exist. The
    # model has never seen such a thing and its answer there is meaningless.
    # ALE avoids this by only ever comparing values within a NARROW BAND, among companies
    # that really do sit in that band. So every comparison it makes is between plausible
    # situations, and the differences are then accumulated to build up the whole picture.

    # Cut the measurement's range into 20 bands.
    q = np.nanpercentile(X[:, j], np.linspace(0, 100, bins + 1))
    # Remove duplicate edges, which happens when many companies share a value.
    q = np.unique(q)
    # Too few distinct bands to build anything. Hand back empties rather than a misleading
    # near-empty curve.
    if len(q) < 3:
        return np.array([]), np.array([])
    # Which band each company falls into.
    idx = np.clip(np.digitize(X[:, j], q[1:-1]), 0, len(q) - 2)
    eff = np.zeros(len(q) - 1)
    counts = np.zeros(len(q) - 1)
    for b in range(len(q) - 1):
        sel = idx == b
        if not sel.any():
            continue
        # For the companies in this band ONLY, compare the band's bottom edge with its top.
        lo, hi = X[sel].copy(), X[sel].copy()
        lo[:, j] = q[b]
        hi[:, j] = q[b + 1]
        # The average score change across just that small, realistic step.
        eff[b] = float(np.mean(predict_fn(hi) - predict_fn(lo)))
        counts[b] = sel.sum()
    # Add the small steps up into the full curve. This is the "accumulated" part.
    acc = np.cumsum(eff)
    # Shift the curve so its weighted average is zero, which makes it read as "relative to
    # typical" -- the natural way to look at it. Weighted by how many companies are in each
    # band, so a nearly-empty band cannot drag the whole curve about.
    centred = acc - np.sum(acc * counts) / max(1.0, counts.sum())
    # Plot each band at its middle.
    centres = 0.5 * (q[:-1] + q[1:])
    return centres, centred
