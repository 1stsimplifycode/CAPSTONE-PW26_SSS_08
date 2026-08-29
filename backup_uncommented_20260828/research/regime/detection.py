"""Market regime detection and its validation (spec section 30).

A Gaussian mixture over index-level daily descriptors (return, realised volatility,
cross-sectional dispersion, breadth, turnover growth). Mixture rather than a full HMM
because the validation burden is lower and the persistence that an HMM would impose is
instead *measured* and reported -- if the fitted regimes are not persistent, that is a
finding, not something to be hidden by a transition prior.

Everything the spec asks to validate is validated and the numbers are emitted:

* model order by BIC and AIC over a range of K,
* label stability under bootstrap resampling (adjusted Rand index),
* a regime-shuffle null, which is what distinguishes "the regimes carry information"
  from "any partition of a volatile series looks like this".

Point-in-time note: :meth:`RegimeModel.fit` is fitted on the *training window only* and
then applied forward. Fitting on the full sample and reading labels back into the
training period is a classic leak and is blocked by leakage test L2.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REGIME_VERSION = "regime-gmm-v1"

REGIME_FEATURES = ["mkt_ret", "mkt_vol_21", "dispersion", "breadth", "turnover_growth"]


def index_descriptors(panel: pd.DataFrame) -> pd.DataFrame:
    """Collapse the cross-section to one row per session.

    Equal-weighted rather than cap-weighted: market capitalisation is not in the
    bhavcopy, and inventing weights would be fabrication. The consequence -- these are
    equal-weighted market descriptors, not Nifty-50 index returns -- is stated wherever
    they are used.
    """
    df = panel.copy()
    if "logret" not in df.columns:
        df["logret"] = np.log(df["close"]) - np.log(df["prev_close"])
    g = df.groupby("date")
    out = pd.DataFrame({
        "mkt_ret": g["logret"].mean(),
        "dispersion": g["logret"].std(),
        "breadth": g["logret"].apply(lambda s: float((s > 0).mean())),
        "turnover": g["turnover"].sum(),
        "n_symbols": g["symbol"].nunique(),
    })
    out["mkt_vol_21"] = out["mkt_ret"].rolling(21).std() * np.sqrt(252.0)
    out["turnover_growth"] = np.log(out["turnover"]).diff(5)
    return out.dropna(subset=REGIME_FEATURES)


@dataclass
class RegimeModel:
    n_regimes: int = 3
    seed: int = 20260818
    version: str = REGIME_VERSION
    _model: object | None = field(default=None, repr=False)
    _mu: np.ndarray | None = field(default=None, repr=False)
    _sd: np.ndarray | None = field(default=None, repr=False)
    order_: list[int] = field(default_factory=list)

    def _standardise(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        if fit:
            self._mu = X.mean(axis=0)
            self._sd = X.std(axis=0)
            self._sd[self._sd == 0] = 1.0
        return (X - self._mu) / self._sd

    def fit(self, desc: pd.DataFrame) -> RegimeModel:
        from sklearn.mixture import GaussianMixture
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float), fit=True)
        gm = GaussianMixture(self.n_regimes, covariance_type="full",
                             random_state=self.seed, n_init=8, reg_covar=1e-4)
        gm.fit(X)
        self._model = gm
        # Relabel by mean volatility so regime 0 is always the calmest. Without this the
        # regime ids permute between runs and every downstream table becomes unreadable.
        lab = gm.predict(X)
        vol_col = REGIME_FEATURES.index("mkt_vol_21")
        means = [X[lab == k, vol_col].mean() if (lab == k).any() else np.inf
                 for k in range(self.n_regimes)]
        self.order_ = list(np.argsort(means))
        return self

    def predict(self, desc: pd.DataFrame) -> np.ndarray:
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        raw = self._model.predict(X)
        remap = {old: new for new, old in enumerate(self.order_)}
        return np.array([remap[int(r)] for r in raw])

    def predict_proba(self, desc: pd.DataFrame) -> np.ndarray:
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        p = self._model.predict_proba(X)
        return p[:, self.order_]

    def score_bic_aic(self, desc: pd.DataFrame) -> tuple[float, float]:
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        return float(self._model.bic(X)), float(self._model.aic(X))


def select_order(desc: pd.DataFrame, ks: tuple[int, ...] = (2, 3, 4, 5, 6),
                 seed: int = 20260818) -> pd.DataFrame:
    """Fit each K and report BIC/AIC plus regime persistence."""
    rows = []
    for k in ks:
        m = RegimeModel(k, seed).fit(desc)
        bic, aic = m.score_bic_aic(desc)
        lab = m.predict(desc)
        persistence = float(np.mean(lab[1:] == lab[:-1]))
        occupancy = np.bincount(lab, minlength=k) / len(lab)
        rows.append({"k": k, "bic": bic, "aic": aic,
                     "persistence": persistence,
                     "min_occupancy": float(occupancy.min()),
                     "n_obs": int(len(lab))})
    return pd.DataFrame(rows)


#: Pre-declared admissibility rule for the number of regimes. Fixed before looking at
#: the fitted values, because "lowest BIC" alone selects models with a 3 %-occupancy
#: regime whose transitions are noise: such a component cannot be conditioned on, and a
#: regime-conditioned combination built over it would be fitting a handful of sessions.
MIN_REGIME_OCCUPANCY = 0.05
MIN_REGIME_PERSISTENCE = 0.50


def select_k(order: pd.DataFrame) -> tuple[int, str]:
    """Apply the admissibility rule and return ``(k, justification)``.

    Rule: among orders whose smallest regime holds at least
    :data:`MIN_REGIME_OCCUPANCY` of sessions *and* whose label persistence is at least
    :data:`MIN_REGIME_PERSISTENCE`, take the lowest BIC. If none qualifies, fall back to
    the lowest BIC overall and say so in the justification.
    """
    ok = order[(order["min_occupancy"] >= MIN_REGIME_OCCUPANCY)
               & (order["persistence"] >= MIN_REGIME_PERSISTENCE)]
    if len(ok):
        row = ok.sort_values("bic").iloc[0]
        why = ("lowest BIC (%.1f) among orders with min occupancy >= %.2f and "
               "persistence >= %.2f; k=%d admitted, %d of %d orders rejected"
               % (row["bic"], MIN_REGIME_OCCUPANCY, MIN_REGIME_PERSISTENCE,
                  int(row["k"]), len(order) - len(ok), len(order)))
        return int(row["k"]), why
    row = order.sort_values("bic").iloc[0]
    return int(row["k"]), ("NO order met the admissibility rule; fell back to lowest "
                           "BIC (k=%d). Treat regime-conditioned results as unsupported."
                           % int(row["k"]))


def bootstrap_stability(desc: pd.DataFrame, k: int, n_boot: int = 50,
                        seed: int = 20260818) -> dict:
    """Adjusted Rand index between the full-sample labelling and bootstrap refits.

    Blocks of 21 sessions are resampled rather than individual days, because daily
    market descriptors are strongly autocorrelated and an iid bootstrap would report a
    stability that the data does not support.
    """
    from sklearn.metrics import adjusted_rand_score
    rng = np.random.default_rng(seed)
    base = RegimeModel(k, seed).fit(desc)
    base_lab = base.predict(desc)
    n = len(desc)
    block = 21
    scores = []
    for _ in range(n_boot):
        starts = rng.integers(0, max(1, n - block), size=max(1, n // block))
        idx = np.concatenate([np.arange(s, min(n, s + block)) for s in starts])
        sub = desc.iloc[np.sort(idx)]
        try:
            m = RegimeModel(k, int(rng.integers(0, 10 ** 6))).fit(sub)
            scores.append(adjusted_rand_score(base_lab[np.sort(idx)], m.predict(sub)))
        except Exception:
            continue
    if not scores:
        return {"n_boot": 0, "ari_mean": float("nan"), "status": "FAILED"}
    a = np.array(scores)
    return {"n_boot": len(a), "ari_mean": float(a.mean()), "ari_std": float(a.std()),
            "ari_p05": float(np.percentile(a, 5)),
            "ari_p95": float(np.percentile(a, 95)), "status": "OK"}


def shuffle_null(desc: pd.DataFrame, k: int, n_perm: int = 100,
                 seed: int = 20260818) -> dict:
    """Regime-shuffle test.

    Statistic: label persistence. Under the null, the *rows* of the descriptor frame are
    permuted, destroying temporal structure while preserving every marginal. A fitted
    persistence that a permuted sample reproduces is not evidence of regimes.
    """
    rng = np.random.default_rng(seed)
    base = RegimeModel(k, seed).fit(desc)
    obs = float(np.mean(base.predict(desc)[1:] == base.predict(desc)[:-1]))
    null = []
    for _ in range(n_perm):
        sh = desc.sample(frac=1.0, replace=False,
                         random_state=int(rng.integers(0, 10 ** 6)))
        m = RegimeModel(k, seed).fit(sh)
        lab = m.predict(sh)
        null.append(float(np.mean(lab[1:] == lab[:-1])))
    null = np.array(null)
    p = float((null >= obs).sum() + 1) / (len(null) + 1)
    return {"observed_persistence": obs, "null_mean": float(null.mean()),
            "null_p95": float(np.percentile(null, 95)), "p_value": p,
            "n_perm": len(null),
            "test": "one-sided permutation on label persistence; rows shuffled to "
                    "destroy temporal ordering while preserving marginals"}
