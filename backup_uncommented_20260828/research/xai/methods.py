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
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

XAI_VERSION = "xai-v1"

PredictFn = Callable[[np.ndarray], np.ndarray]

#: Methods implemented here and applicable to the tabular risk model.
TABULAR_METHODS = ["permutation", "occlusion", "kernel_shap", "lime", "counterfactual"]
#: Methods applicable only to the differentiable combination layer.
GRADIENT_METHODS = ["integrated_gradients", "gradient_x_input"]
#: Declared by the specification but not applicable to this model class.
NOT_APPLICABLE = {
    "deep_shap": "requires a differentiable deep network; the risk model is tree-based",
    "grad_cam": "requires convolutional feature maps; no CNN is used",
    "guided_grad_cam": "requires a CNN",
    "tcav": "requires a differentiable network with concept activation vectors",
    "deeplift": "requires a differentiable deep network",
    "tree_shap": "the per-block learners are wrapped in a probability calibrator, "
                 "so the tree structure is not directly exposed; KernelSHAP is used "
                 "instead and this substitution is reported",
}


@dataclass
class Attribution:
    method: str
    values: np.ndarray
    feature_names: list[str]
    base_value: float = 0.0
    prediction: float = 0.0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    def top(self, k: int = 10) -> list[tuple[str, float]]:
        idx = np.argsort(-np.abs(self.values))[:k]
        return [(self.feature_names[i], float(self.values[i])) for i in idx]

    def as_dict(self) -> dict[str, float]:
        return {n: float(v) for n, v in zip(self.feature_names, self.values)}


def _timed(fn):
    def wrap(*a, **kw):
        t = time.perf_counter()
        out = fn(*a, **kw)
        out.seconds = time.perf_counter() - t
        return out
    return wrap


# -- global --------------------------------------------------------------------------

@_timed
def permutation_importance(predict_fn: PredictFn, X: np.ndarray, y: np.ndarray,
                           feature_names: Sequence[str], n_repeats: int = 5,
                           metric: str = "auprc", seed: int = 20260818) -> Attribution:
    """Global importance: loss in performance when one column is shuffled.

    Shuffling rather than dropping keeps the marginal distribution intact, so the model
    is not asked to extrapolate off its training support.
    """
    from sklearn.metrics import average_precision_score, roc_auc_score
    score = average_precision_score if metric == "auprc" else roc_auc_score
    rng = np.random.default_rng(seed)
    base = score(y, predict_fn(X))
    vals = np.zeros(X.shape[1])
    for j in range(X.shape[1]):
        drops = []
        for _ in range(n_repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            drops.append(base - score(y, predict_fn(Xp)))
        vals[j] = float(np.mean(drops))
    return Attribution("permutation", vals, list(feature_names), base_value=float(base),
                       notes=["metric=%s, n_repeats=%d" % (metric, n_repeats)])


# -- local ---------------------------------------------------------------------------

@_timed
def occlusion(predict_fn: PredictFn, X: np.ndarray, row: int,
              feature_names: Sequence[str], background: np.ndarray,
              groups: dict[str, list[int]] | None = None) -> Attribution:
    """Local ablation: replace each feature (or group) with its background median.

    Group mode is what produces *block* attribution -- occluding an entire block at once
    answers "what did the propagation block contribute", which is the question section 22
    asks.
    """
    x = X[row:row + 1].copy()
    base = float(predict_fn(x)[0])
    med = np.nanmedian(background, axis=0)
    if groups is None:
        vals = np.zeros(X.shape[1])
        for j in range(X.shape[1]):
            xp = x.copy()
            xp[0, j] = med[j]
            vals[j] = base - float(predict_fn(xp)[0])
        names = list(feature_names)
    else:
        names = list(groups.keys())
        vals = np.zeros(len(names))
        for i, (_, cols) in enumerate(groups.items()):
            xp = x.copy()
            xp[0, cols] = med[cols]
            vals[i] = base - float(predict_fn(xp)[0])
    return Attribution("occlusion", vals, names, base_value=base, prediction=base)


@_timed
def kernel_shap(predict_fn: PredictFn, X: np.ndarray, row: int,
                feature_names: Sequence[str], background: np.ndarray,
                nsamples: int = 200, seed: int = 20260818) -> Attribution:
    """KernelSHAP via the ``shap`` package, on a k-means-summarised background."""
    import shap
    k = min(25, len(background))
    bg = shap.kmeans(background, k) if len(background) > k else background
    ex = shap.KernelExplainer(predict_fn, bg, seed=seed)
    vals = ex.shap_values(X[row], nsamples=nsamples, silent=True)
    vals = np.asarray(vals, dtype=float).ravel()[:X.shape[1]]
    return Attribution("kernel_shap", vals, list(feature_names),
                       base_value=float(np.mean(ex.expected_value)),
                       prediction=float(predict_fn(X[row:row + 1])[0]),
                       notes=["background summarised to %d k-means centroids" % k,
                              "nsamples=%d" % nsamples])


@_timed
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
    from sklearn.linear_model import Ridge
    rng = np.random.default_rng(seed)
    x = X[row]
    d = X.shape[1]
    mask = rng.random((n_samples, d)) < 0.5
    donors = background[rng.integers(0, len(background), size=(n_samples, d)),
                        np.arange(d)]
    Z = np.where(mask, donors, x)
    scale = np.nanstd(background, axis=0)
    scale[scale == 0] = 1.0
    dist = np.sqrt((((Z - x) / scale) ** 2).mean(axis=1))
    kw = kernel_width if kernel_width is not None else float(np.median(dist) or 1.0)
    w = np.exp(-(dist ** 2) / (2 * kw ** 2))
    yz = predict_fn(np.nan_to_num(Z, nan=0.0))
    reg = Ridge(alpha=1.0)
    reg.fit(np.nan_to_num(Z, nan=0.0), yz, sample_weight=w)
    return Attribution("lime", reg.coef_.astype(float), list(feature_names),
                       base_value=float(reg.intercept_),
                       prediction=float(predict_fn(X[row:row + 1])[0]),
                       notes=["marginal-resampling perturbations, n=%d, kernel_width="
                              "%.4f" % (n_samples, kw)])


@_timed
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
    x = X[row:row + 1].copy()
    base = float(predict_fn(x)[0])
    med = np.nanmedian(background, axis=0)
    vals = np.zeros(X.shape[1])
    cur = x.copy()
    chosen: list[int] = []
    notes = []
    for _ in range(max_features):
        best_j, best_score = None, float(predict_fn(cur)[0])
        for j in range(X.shape[1]):
            if j in chosen:
                continue
            xp = cur.copy()
            xp[0, j] = med[j]
            s = float(predict_fn(xp)[0])
            if s < best_score:
                best_j, best_score = j, s
        if best_j is None:
            break
        prev = float(predict_fn(cur)[0])
        cur[0, best_j] = med[best_j]
        vals[best_j] = prev - best_score
        chosen.append(best_j)
        if best_score <= target:
            notes.append("target %.2f reached with %d features" % (target, len(chosen)))
            break
    else:
        notes.append("target %.2f NOT reached within %d features (best %.3f)"
                     % (target, max_features, float(predict_fn(cur)[0])))
    notes.append("changed: %s" % ", ".join(feature_names[j] for j in chosen))
    return Attribution("counterfactual", vals, list(feature_names), base_value=base,
                       prediction=base, notes=notes)


# -- gradient methods on the differentiable combination layer --------------------------

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
    x = scores[row].astype(float)
    b = np.zeros_like(x) if baseline is None else np.asarray(baseline, dtype=float)
    alphas = (np.arange(steps) + 0.5) / steps
    path = b[None, :] + alphas[:, None] * (x - b)[None, :]
    eps = 1e-4
    grads = np.zeros((steps, len(x)))
    for j in range(len(x)):
        hi = path.copy()
        lo = path.copy()
        hi[:, j] += eps
        lo[:, j] -= eps
        grads[:, j] = (fuse_fn(hi) - fuse_fn(lo)) / (2 * eps)
    vals = (x - b) * grads.mean(axis=0)
    fx = float(fuse_fn(x[None, :])[0])
    fb = float(fuse_fn(b[None, :])[0])
    gap = abs(vals.sum() - (fx - fb))
    return Attribution("integrated_gradients", vals, list(block_names),
                       base_value=fb, prediction=fx,
                       notes=["steps=%d" % steps,
                              "completeness gap |sum(attr) - (f(x)-f(b))| = %.5f" % gap])


@_timed
def gradient_x_input(fuse_fn: Callable[[np.ndarray], np.ndarray], scores: np.ndarray,
                     row: int, block_names: Sequence[str]) -> Attribution:
    x = scores[row].astype(float)
    eps = 1e-4
    g = np.zeros(len(x))
    for j in range(len(x)):
        hi, lo = x.copy(), x.copy()
        hi[j] += eps
        lo[j] -= eps
        g[j] = ((float(fuse_fn(hi[None, :])[0])
                 - float(fuse_fn(lo[None, :])[0])) / (2 * eps))
    return Attribution("gradient_x_input", g * x, list(block_names),
                       prediction=float(fuse_fn(x[None, :])[0]))


# -- dependence curves ------------------------------------------------------------------

def partial_dependence(predict_fn: PredictFn, X: np.ndarray, j: int,
                       grid: int = 20) -> tuple[np.ndarray, np.ndarray]:
    xs = np.nanpercentile(X[:, j], np.linspace(2, 98, grid))
    out = []
    for v in xs:
        Xp = X.copy()
        Xp[:, j] = v
        out.append(float(np.mean(predict_fn(Xp))))
    return xs, np.asarray(out)


def ice_curves(predict_fn: PredictFn, X: np.ndarray, j: int, rows: Sequence[int],
               grid: int = 20) -> tuple[np.ndarray, np.ndarray]:
    xs = np.nanpercentile(X[:, j], np.linspace(2, 98, grid))
    curves = np.zeros((len(rows), grid))
    for i, r in enumerate(rows):
        Xp = np.repeat(X[r:r + 1], grid, axis=0)
        Xp[:, j] = xs
        curves[i] = predict_fn(Xp)
    return xs, curves


def ale(predict_fn: PredictFn, X: np.ndarray, j: int, bins: int = 20) -> tuple:
    """First-order accumulated local effects.

    Preferred over PDP when features are correlated: PDP averages the model over
    combinations that never occur, ALE only over local differences that do.
    """
    q = np.nanpercentile(X[:, j], np.linspace(0, 100, bins + 1))
    q = np.unique(q)
    if len(q) < 3:
        return np.array([]), np.array([])
    idx = np.clip(np.digitize(X[:, j], q[1:-1]), 0, len(q) - 2)
    eff = np.zeros(len(q) - 1)
    counts = np.zeros(len(q) - 1)
    for b in range(len(q) - 1):
        sel = idx == b
        if not sel.any():
            continue
        lo, hi = X[sel].copy(), X[sel].copy()
        lo[:, j] = q[b]
        hi[:, j] = q[b + 1]
        eff[b] = float(np.mean(predict_fn(hi) - predict_fn(lo)))
        counts[b] = sel.sum()
    acc = np.cumsum(eff)
    centred = acc - np.sum(acc * counts) / max(1.0, counts.sum())
    centres = 0.5 * (q[:-1] + q[1:])
    return centres, centred
