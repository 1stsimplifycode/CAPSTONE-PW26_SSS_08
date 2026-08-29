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

PLAIN ENGLISH -- what this whole file is about:

WHAT MOOD IS THE MARKET IN?

Markets have moods, and everyone who watches them knows it. Some months are calm: prices
drift, nothing much happens. Some are frightened: everything lurches together, volumes
explode. These moods are called REGIMES.

This file finds them automatically, without anybody telling it what to look for. It
watches five things each day and lets the days sort themselves into groups.

THE METHOD: a "Gaussian mixture". Imagine tipping a bag of marbles onto a table. They fall
into three loose clumps. The method's job is to find those clumps -- to notice that days
naturally cluster into a few recognisable kinds.

WHY NOT SOMETHING FANCIER? There is a more sophisticated tool for this called a Hidden
Markov Model, which additionally ASSUMES that moods are sticky -- that today's mood is
probably yesterday's. That assumption is very likely true, and it is exactly why it is not
used here. If you build stickiness into your assumptions, you will find sticky moods no
matter what, and you will never know whether the data actually contains them. So this file
uses the simpler tool, MEASURES the stickiness afterwards, and reports whatever it finds.
The docstring's phrasing is precise: if the moods turn out not to be persistent, "that is
a finding, not something to be hidden by a transition prior."

THREE VALIDATION CHECKS, all of which could fail and all of which are reported:

 1. HOW MANY MOODS? Not chosen by taste. Several counts are tried and scored, and a rule
    written down in advance picks the winner.

 2. ARE THE MOODS STABLE? Refit on a random chunk of the data. Do the same days end up
    grouped together? If not, the moods were an accident of this particular sample.

 3. THE SHUFFLE TEST -- and this is the sharpest one. Shuffle the days into random order,
    destroying all the time structure, and refit. If the shuffled version produces moods
    that look just as convincing, then "moods" were never really there -- any wobbly
    series can be chopped into groups that look meaningful. Testing against this is what
    separates a finding from a Rorschach blot.

AND THE TIMING RULE: the moods are learned from the practice period only, then applied
forwards. Learning them from the whole history and then reading them back into the past
would mean the "mood" of March 2019 was partly determined by what happened in 2021 -- a
classic leak, and one that a chart makes look completely innocent.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version.
REGIME_VERSION = "regime-gmm-v1"

# The five things watched each day, which together describe the market's mood.
REGIME_FEATURES = ["mkt_ret", "mkt_vol_21", "dispersion", "breadth", "turnover_growth"]


# Squash the whole market down to one row per day.
def index_descriptors(panel: pd.DataFrame) -> pd.DataFrame:
    """Collapse the cross-section to one row per session.

    Equal-weighted rather than cap-weighted: market capitalisation is not in the
    bhavcopy, and inventing weights would be fabrication. The consequence -- these are
    equal-weighted market descriptors, not Nifty-50 index returns -- is stated wherever
    they are used.
    """
    # PLAIN ENGLISH: real market indices weight big companies more heavily -- a giant firm
    # moves the index far more than a small one. To do that we would need each company's
    # total market value, which the exchange's daily file does not contain.
    # So every company counts equally instead. That is a genuine difference, not a detail,
    # and rather than quietly calling the result "the index", the project states plainly
    # everywhere it appears that these are equal-weighted descriptors and not Nifty-50
    # returns. Making something up in order to use the more famous name would be fabrication.
    df = panel.copy()
    # Work out daily returns if they are not already there.
    if "logret" not in df.columns:
        df["logret"] = np.log(df["close"]) - np.log(df["prev_close"])
    g = df.groupby("date")
    out = pd.DataFrame({
        # How the average company did that day.
        "mkt_ret": g["logret"].mean(),
        # How much companies differed from each other. High dispersion means the market is
        # picking winners and losers; low means everything is moving as one lump, which is
        # what panic looks like.
        "dispersion": g["logret"].std(),
        # What fraction of companies went up. 0.5 is a mixed day; 0.05 means almost
        # everything fell, which is a different kind of day entirely.
        "breadth": g["logret"].apply(lambda s: float((s > 0).mean())),
        # Total money traded.
        "turnover": g["turnover"].sum(),
        # How many companies traded at all -- kept for context on how solid each row is.
        "n_symbols": g["symbol"].nunique(),
    })
    # How jumpy the market has been over the last month, annualised for comparability.
    out["mkt_vol_21"] = out["mkt_ret"].rolling(21).std() * np.sqrt(252.0)
    # How trading activity has changed over the last week. In logs, so a doubling and a
    # halving are equal and opposite rather than +100% and -50%.
    out["turnover_growth"] = np.log(out["turnover"]).diff(5)
    # Drop days where any of the five is missing, since a mood cannot be judged from a
    # partial description.
    return out.dropna(subset=REGIME_FEATURES)


@dataclass
# The mood-finding model.
class RegimeModel:
    # How many moods to look for.
    n_regimes: int = 3
    seed: int = 20260818
    version: str = REGIME_VERSION
    # The fitted model, hidden from printed descriptions.
    _model: object | None = field(default=None, repr=False)
    # The averages and spreads used to standardise the inputs.
    _mu: np.ndarray | None = field(default=None, repr=False)
    _sd: np.ndarray | None = field(default=None, repr=False)
    # The ordering that keeps mood numbers meaningful between runs.
    order_: list[int] = field(default_factory=list)

    # Put the five measurements on a comparable scale.
    def _standardise(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        # PLAIN ENGLISH: the five are on wildly different scales -- returns are around 0.001,
        # turnover growth might be 2.0. Without standardising, the largest-numbered one would
        # dominate the clustering entirely and the rest would be ignored.
        if fit:
            # LEARN the scale, and only when fitting. When applying the model later we reuse
            # the SAME numbers -- crucial, because re-learning the scale on new data would
            # silently shift what every mood means.
            self._mu = X.mean(axis=0)
            self._sd = X.std(axis=0)
            # Guard against a measurement that never varies, which would be a divide by zero.
            self._sd[self._sd == 0] = 1.0
        return (X - self._mu) / self._sd

    # Find the moods.
    def fit(self, desc: pd.DataFrame) -> RegimeModel:
        from sklearn.mixture import GaussianMixture
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float), fit=True)
        gm = GaussianMixture(self.n_regimes,
                             # "full" lets each mood have its own shape and its own pattern
                             # of which measurements move together -- more flexible than
                             # forcing every mood into the same mould.
                             covariance_type="full",
                             random_state=self.seed,
                             # Try 8 different starting points and keep the best. This kind
                             # of fitting can settle into a poor answer depending on where it
                             # starts, so several attempts is standard practice.
                             n_init=8,
                             # A tiny amount added to keep the maths stable when a mood's
                             # measurements are nearly perfectly related.
                             reg_covar=1e-4)
        gm.fit(X)
        self._model = gm
        # Relabel by mean volatility so regime 0 is always the calmest. Without this the
        # regime ids permute between runs and every downstream table becomes unreadable.
        # PLAIN ENGLISH: the fitting gives the moods arbitrary numbers -- there is nothing to
        # stop "mood 0" being the calm one today and the panicky one tomorrow. Every chart
        # and table downstream would then be meaningless, and worse, would look fine. Sorting
        # by jumpiness fixes 0 as calmest, always.
        lab = gm.predict(X)
        vol_col = REGIME_FEATURES.index("mkt_vol_21")
        # Each mood's average jumpiness. An empty mood is given infinity so it sorts last
        # rather than crashing the comparison.
        means = [X[lab == k, vol_col].mean() if (lab == k).any() else np.inf
                 for k in range(self.n_regimes)]
        self.order_ = list(np.argsort(means))
        return self

    # Which mood was each day in?
    def predict(self, desc: pd.DataFrame) -> np.ndarray:
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        raw = self._model.predict(X)
        # Translate the model's arbitrary numbers into our stable calm-to-wild ordering.
        remap = {old: new for new, old in enumerate(self.order_)}
        return np.array([remap[int(r)] for r in raw])

    # How likely was each mood, rather than just the winner?
    def predict_proba(self, desc: pd.DataFrame) -> np.ndarray:
        # PLAIN ENGLISH: kept because "definitely calm" and "just about calm, but it was
        # nearly a toss-up" are very different days, and the single winning label cannot
        # tell them apart.
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        p = self._model.predict_proba(X)
        # Reorder the columns to match our stable ordering.
        return p[:, self.order_]

    # Two scores for judging how many moods to use.
    def score_bic_aic(self, desc: pd.DataFrame) -> tuple[float, float]:
        # PLAIN ENGLISH: both reward fitting the data well and PENALISE complexity. Without
        # such a penalty, more moods would always win -- with one mood per day you could fit
        # perfectly and learn nothing. BIC penalises complexity more harshly than AIC; both
        # are reported so a reader can see whether they agree.
        X = self._standardise(desc[REGIME_FEATURES].to_numpy(float))
        return float(self._model.bic(X)), float(self._model.aic(X))


# Try several numbers of moods and score each.
def select_order(desc: pd.DataFrame, ks: tuple[int, ...] = (2, 3, 4, 5, 6),
                 seed: int = 20260818) -> pd.DataFrame:
    """Fit each K and report BIC/AIC plus regime persistence."""
    rows = []
    for k in ks:
        m = RegimeModel(k, seed).fit(desc)
        bic, aic = m.score_bic_aic(desc)
        lab = m.predict(desc)
        # How sticky are the moods? What fraction of days had the same mood as the day
        # before. This is the number the fancier model would have ASSUMED; here it is
        # measured, and it is free to come out badly.
        persistence = float(np.mean(lab[1:] == lab[:-1]))
        # What share of days each mood covers.
        occupancy = np.bincount(lab, minlength=k) / len(lab)
        rows.append({"k": k, "bic": bic, "aic": aic,
                     "persistence": persistence,
                     # The rarest mood's share -- the number that catches a "mood" which is
                     # really just a handful of odd days.
                     "min_occupancy": float(occupancy.min()),
                     "n_obs": int(len(lab))})
    return pd.DataFrame(rows)


#: Pre-declared admissibility rule for the number of regimes. Fixed before looking at
#: the fitted values, because "lowest BIC" alone selects models with a 3 %-occupancy
#: regime whose transitions are noise: such a component cannot be conditioned on, and a
#: regime-conditioned combination built over it would be fitting a handful of sessions.
# PLAIN ENGLISH: the scoring rule alone will happily pick a model containing a "mood" that
# occurs on 3% of days. That is not a market regime; it is a handful of odd days with a
# label on them. And it is actively harmful downstream, because the combining layer would
# then try to learn separate weights for a mood that occurred a dozen times.
# So two extra requirements are added -- and set BEFORE anyone saw the numbers.
MIN_REGIME_OCCUPANCY = 0.05
MIN_REGIME_PERSISTENCE = 0.50


# Apply the rule and pick the number of moods.
def select_k(order: pd.DataFrame) -> tuple[int, str]:
    """Apply the admissibility rule and return ``(k, justification)``.

    Rule: among orders whose smallest regime holds at least
    :data:`MIN_REGIME_OCCUPANCY` of sessions *and* whose label persistence is at least
    :data:`MIN_REGIME_PERSISTENCE`, take the lowest BIC. If none qualifies, fall back to
    the lowest BIC overall and say so in the justification.
    """
    # Keep only the candidates that meet both requirements.
    ok = order[(order["min_occupancy"] >= MIN_REGIME_OCCUPANCY)
               & (order["persistence"] >= MIN_REGIME_PERSISTENCE)]
    if len(ok):
        # Among those, the best score wins.
        row = ok.sort_values("bic").iloc[0]
        # And the choice comes with its full reasoning, including how many candidates were
        # rejected -- so the decision can be audited rather than merely accepted.
        why = ("lowest BIC (%.1f) among orders with min occupancy >= %.2f and "
               "persistence >= %.2f; k=%d admitted, %d of %d orders rejected"
               % (row["bic"], MIN_REGIME_OCCUPANCY, MIN_REGIME_PERSISTENCE,
                  int(row["k"]), len(order) - len(ok), len(order)))
        return int(row["k"]), why
    # NOTHING met the rule. We still have to pick something, so we take the best score --
    # but the justification says, in capital letters, that the rule was not met and warns
    # that every mood-based result downstream is unsupported.
    # The alternative would have been to relax the rule until something passed, which is
    # exactly what declaring it in advance is meant to prevent.
    row = order.sort_values("bic").iloc[0]
    return int(row["k"]), ("NO order met the admissibility rule; fell back to lowest "
                           "BIC (k=%d). Treat regime-conditioned results as unsupported."
                           % int(row["k"]))


# CHECK 2: are the moods stable, or an accident of this sample?
def bootstrap_stability(desc: pd.DataFrame, k: int, n_boot: int = 50,
                        seed: int = 20260818) -> dict:
    """Adjusted Rand index between the full-sample labelling and bootstrap refits.

    Blocks of 21 sessions are resampled rather than individual days, because daily
    market descriptors are strongly autocorrelated and an iid bootstrap would report a
    stability that the data does not support.
    """
    # PLAIN ENGLISH: the "adjusted Rand index" measures how much two groupings agree, while
    # correcting for the agreement you would get by pure chance. 1 means identical, 0 means
    # no better than random.
    # And blocks again: calm periods come in runs. Picking individual days at random would
    # scatter those runs and destroy the very structure being measured.
    from sklearn.metrics import adjusted_rand_score
    rng = np.random.default_rng(seed)
    # The reference grouping, from all the data.
    base = RegimeModel(k, seed).fit(desc)
    base_lab = base.predict(desc)
    n = len(desc)
    block = 21
    scores = []
    for _ in range(n_boot):
        # Pick random month-long stretches and glue them together.
        starts = rng.integers(0, max(1, n - block), size=max(1, n // block))
        idx = np.concatenate([np.arange(s, min(n, s + block)) for s in starts])
        sub = desc.iloc[np.sort(idx)]
        try:
            # Refit from scratch on that sample, with a DIFFERENT random seed -- so we are
            # testing the stability of the finding, not merely repeating one calculation.
            m = RegimeModel(k, int(rng.integers(0, 10 ** 6))).fit(sub)
            scores.append(adjusted_rand_score(base_lab[np.sort(idx)], m.predict(sub)))
        except Exception:
            continue
    # Nothing worked: report a clear failure rather than a misleading number.
    if not scores:
        return {"n_boot": 0, "ari_mean": float("nan"), "status": "FAILED"}
    a = np.array(scores)
    # Report the average AND the range. A high average with an enormous spread means the
    # moods are sometimes stable and sometimes not, which the average alone would hide.
    return {"n_boot": len(a), "ari_mean": float(a.mean()), "ari_std": float(a.std()),
            "ari_p05": float(np.percentile(a, 5)),
            "ari_p95": float(np.percentile(a, 95)), "status": "OK"}


# CHECK 3: the sharpest test. Would random data look just as convincing?
def shuffle_null(desc: pd.DataFrame, k: int, n_perm: int = 100,
                 seed: int = 20260818) -> dict:
    """Regime-shuffle test.

    Statistic: label persistence. Under the null, the *rows* of the descriptor frame are
    permuted, destroying temporal structure while preserving every marginal. A fitted
    persistence that a permuted sample reproduces is not evidence of regimes.
    """
    # PLAIN ENGLISH: this is beautifully designed. Shuffling the days into random order
    # destroys ALL the time structure -- there can be no such thing as a persistent mood in
    # shuffled data -- while keeping every individual day exactly as it was. So the shuffled
    # data has identical volatility, identical everything, and no chronology.
    # Now refit. If the shuffled version ALSO produces sticky-looking moods, then stickiness
    # was never evidence of anything; it was just what this method does to any wobbly series.
    rng = np.random.default_rng(seed)
    base = RegimeModel(k, seed).fit(desc)
    # How sticky the real moods are.
    obs = float(np.mean(base.predict(desc)[1:] == base.predict(desc)[:-1]))
    null = []
    for _ in range(n_perm):
        # Shuffle the rows. `frac=1.0` keeps every row, `replace=False` uses each exactly
        # once -- so it is a genuine reordering, not a resample.
        sh = desc.sample(frac=1.0, replace=False,
                         random_state=int(rng.integers(0, 10 ** 6)))
        m = RegimeModel(k, seed).fit(sh)
        lab = m.predict(sh)
        null.append(float(np.mean(lab[1:] == lab[:-1])))
    null = np.array(null)
    # How often did shuffled data reach our real stickiness? If often, we have nothing.
    # The +1 top and bottom keeps p from ever being exactly zero.
    p = float((null >= obs).sum() + 1) / (len(null) + 1)
    return {"observed_persistence": obs, "null_mean": float(null.mean()),
            # The 95th percentile of the shuffled results: the bar the real number had to
            # clear. Giving it lets a reader judge the margin, not just the verdict.
            "null_p95": float(np.percentile(null, 95)), "p_value": p,
            "n_perm": len(null),
            # And the test described in words, carried in the output.
            "test": "one-sided permutation on label persistence; rows shuffled to "
                    "destroy temporal ordering while preserving marginals"}
