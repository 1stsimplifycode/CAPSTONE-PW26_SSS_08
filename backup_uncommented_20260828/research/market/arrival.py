"""Trade-arrival intensity, and whether a Poisson process can describe it.

The exchange publishes, for every security and session, the number of transactions
executed: ``TOTALTRADES`` in the legacy bhavcopy, ``TtlNbOfTxsExctd`` in UDiFF. That is a
genuine count of arrivals from NSE's own file, and it is what this module models.

**The resolution limit, stated first because it bounds every claim here.** These are
*daily* counts. NSE does not publish trade timestamps in any dataset obtained by this
repository, so the inter-arrival times within a session are not observable and no Hawkes
or duration model can be fitted. What can be fitted is the arrival *intensity* at daily
resolution and, crucially, its dispersion.

Two nested models are compared:

**Poisson.** One parameter, ``lambda`` = mean daily count, and the defining property that
the variance equals the mean. If trades arrived independently at a constant rate this
would hold.

**Negative binomial.** Adds a dispersion parameter ``k``, giving
``Var = mu + mu^2 / k``. It is the model you need when arrivals cluster -- when a busy
session makes the next trade more likely rather than less.

The quantity that decides between them is the **Fano factor**, ``Var / Mean``. Under
Poisson it is 1. The test statistic ``(n-1) * Var / Mean`` is chi-squared with ``n-1``
degrees of freedom under the Poisson null, which turns "the variance looks too big" into a
p-value.

Why this matters downstream, and the reason the Week 8 detector consumes it: an event
detector that assumes Poisson arrivals sets its alarm threshold from the Poisson variance.
If the true variance is several times larger, that threshold is far too tight and the
detector fires constantly on ordinary sessions. The dispersion measured here is what lets
Week 8 widen its expectation to match the counts the market actually produces.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from scipy import stats

from research.reference import Basis

ARRIVAL_VERSION = "arrival-v1"

#: Below this many sessions a dispersion statistic is not reported: the chi-squared test
#: has no power and the Fano factor is dominated by its own sampling error.
MIN_SESSIONS = 30

#: A Fano factor above this, with a significant test, is treated as overdispersed.
#: Exactly 1.0 is the Poisson boundary; the margin absorbs estimation noise.
FANO_POISSON = 1.0

#: Significance level for the dispersion test.
ALPHA = 0.05


@dataclass
class ArrivalFit:
    """One security's arrival model, both fits, and the verdict between them."""

    symbol: str
    n_sessions: int
    mean_daily_trades: float
    var_daily_trades: float
    #: Poisson MLE is the sample mean; its standard error is sqrt(lambda/n).
    poisson_lambda: float
    poisson_lambda_standard_error: float
    #: Var/Mean. 1.0 under Poisson.
    fano_factor: float
    #: Method-of-moments negative-binomial dispersion. Large k -> approaches Poisson.
    nb_dispersion_k: float
    #: chi-squared dispersion test against the Poisson null.
    dispersion_chi2: float
    dispersion_p_value: float
    overdispersed: bool
    model_selected: str
    interpretation: str

    def to_dict(self) -> dict:
        return asdict(self)


def fit_symbol(symbol: str, counts: np.ndarray,
               alpha: float = ALPHA) -> ArrivalFit | None:
    """Fit both models to one security's daily trade counts."""
    c = np.asarray(counts, dtype=float)
    c = c[np.isfinite(c) & (c >= 0)]
    n = len(c)
    if n < MIN_SESSIONS:
        return None

    mean = float(np.mean(c))
    var = float(np.var(c, ddof=1))
    if mean <= 0:
        return None

    fano = var / mean
    # Under H0: Poisson, (n-1) * s^2 / xbar ~ chi2(n-1).
    chi2 = (n - 1) * fano
    # One-sided: overdispersion is the alternative that matters.
    p = float(stats.chi2.sf(chi2, df=n - 1))

    # Method of moments for the negative binomial: Var = mu + mu^2 / k.
    k = float(mean ** 2 / (var - mean)) if var > mean else float("inf")

    over = bool(fano > FANO_POISSON and p < alpha)
    model = "negative_binomial" if over else "poisson"
    if over:
        interp = ("Counts are overdispersed: variance is %.1fx the mean, which a Poisson "
                  "process cannot produce. Arrivals cluster." % fano)
    elif fano < FANO_POISSON:
        interp = ("Counts are underdispersed (Fano %.2f): more regular than Poisson."
                  % fano)
    else:
        interp = ("Dispersion is not distinguishable from Poisson at the %.2f "
                  "level." % alpha)

    return ArrivalFit(
        symbol=symbol, n_sessions=n, mean_daily_trades=mean, var_daily_trades=var,
        poisson_lambda=mean,
        poisson_lambda_standard_error=float(np.sqrt(mean / n)),
        fano_factor=float(fano), nb_dispersion_k=k,
        dispersion_chi2=float(chi2), dispersion_p_value=p,
        overdispersed=over, model_selected=model, interpretation=interp,
    )


def fit_all(panel: pd.DataFrame, symbols: list[str] | None = None,
            date_from: str | None = None,
            date_to: str | None = None) -> pd.DataFrame:
    """Fit every security's arrival model from the exchange's own trade counts."""
    need = {"symbol", "date", "trades"}
    missing = need - set(panel.columns)
    if missing:
        raise KeyError("panel is missing %s" % sorted(missing))

    p = panel[["symbol", "date", "trades"]].dropna(subset=["trades"])
    if date_from:
        p = p[p["date"] >= pd.Timestamp(date_from)]
    if date_to:
        p = p[p["date"] <= pd.Timestamp(date_to)]
    if symbols:
        p = p[p["symbol"].isin({s.upper() for s in symbols})]

    fits = []
    for sym, g in p.groupby("symbol", sort=False):
        fit = fit_symbol(sym, g["trades"].to_numpy())
        if fit is not None:
            fits.append(fit.to_dict())
    out = pd.DataFrame(fits)
    if out.empty:
        return out
    return out.sort_values("fano_factor", ascending=False).reset_index(drop=True)


@dataclass(frozen=True)
class OverdispersionResult:
    """The Week 2 result that Week 8 consumes.

    Deliberately a small, explicit value object rather than a loose float. Week 8 must be
    able to tell "no Week 2 result was supplied" from "a Week 2 result said dispersion is
    1.0", and a bare number cannot express that difference.
    """

    fano_factor: float
    nb_dispersion_k: float
    overdispersed: bool
    model_selected: str
    n_symbols: int
    n_sessions: int
    median_daily_trades: float
    source: str
    computed_at: str
    basis: str = str(Basis.DERIVED_FROM_EXCHANGE_DATA)

    def variance_inflation(self) -> float:
        """How much wider than Poisson the count *variance* is: the Fano factor itself.

        Under Poisson it is 1.0, so a consumer that multiplies by it is unchanged in
        the degenerate case, which is right when there is nothing to correct.
        """
        return max(1.0, float(self.fano_factor))

    def sd_inflation(self) -> float:
        """How much wider than Poisson the count *standard deviation* is.

        ``sqrt(Fano)``, and this is the one an alarm band wants. A detector that sets its
        band at ``k * sqrt(lambda)`` on the Poisson assumption is too tight by exactly
        this factor; multiplying the band by it restores the coverage the detector thinks
        it has. The distinction from :meth:`variance_inflation` is not pedantry -- using
        the variance multiplier on a standard-deviation band would widen it by the square
        of what is needed.
        """
        return float(np.sqrt(self.variance_inflation()))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["variance_inflation"] = self.variance_inflation()
        d["sd_inflation"] = self.sd_inflation()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> OverdispersionResult:
        """Rebuild from a persisted payload.

        Keeps only the declared fields. The stored artifact also carries derived values
        and bookkeeping the writer added (``sd_inflation``, ``written_at``,
        ``consumed_by``), and a strict constructor would reject the very file it wrote.
        """
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})


def aggregate_overdispersion(fits: pd.DataFrame,
                             source: str = "cash_panel.trades") -> OverdispersionResult:
    """Collapse per-security dispersion into the one figure Week 8 consumes.

    The median rather than the mean: the Fano factor is heavily right-skewed across
    securities, and a handful of very clustered names would otherwise set the detector's
    variance for everything.
    """
    if fits.empty:
        raise ValueError("no arrival fits to aggregate")
    fano = float(fits["fano_factor"].median())
    finite_k = fits.loc[np.isfinite(fits["nb_dispersion_k"]), "nb_dispersion_k"]
    return OverdispersionResult(
        fano_factor=fano,
        nb_dispersion_k=float(finite_k.median()) if len(finite_k) else float("inf"),
        overdispersed=bool(fits["overdispersed"].mean() > 0.5),
        model_selected=("negative_binomial" if fits["overdispersed"].mean() > 0.5
                        else "poisson"),
        n_symbols=int(len(fits)),
        n_sessions=int(fits["n_sessions"].median()),
        median_daily_trades=float(fits["mean_daily_trades"].median()),
        source=source,
        computed_at=datetime.now(UTC).isoformat(),
    )


def summary(fits: pd.DataFrame, agg: OverdispersionResult) -> dict:
    return {
        "arrival_version": ARRIVAL_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "data": "NSE bhavcopy trade counts (TOTALTRADES / TtlNbOfTxsExctd)",
        "resolution": "daily counts; NSE publishes no trade timestamps in any dataset "
                      "obtained here, so inter-arrival times are not observable",
        "estimator": "Poisson MLE lambda = mean daily count; negative binomial by "
                     "method of moments Var = mu + mu^2/k",
        "dispersion_test": "chi-squared (n-1)*Var/Mean against the Poisson null, "
                           "one-sided at alpha=%.2f" % ALPHA,
        "symbols_fitted": int(len(fits)),
        "overdispersed_symbols": int(fits["overdispersed"].sum()),
        "overdispersed_share": float(fits["overdispersed"].mean()),
        "median_fano_factor": float(fits["fano_factor"].median()),
        "min_fano_factor": float(fits["fano_factor"].min()),
        "max_fano_factor": float(fits["fano_factor"].max()),
        "median_daily_trades": float(fits["mean_daily_trades"].median()),
        "aggregate_for_week8": agg.to_dict(),
        "basis": str(Basis.DERIVED_FROM_EXCHANGE_DATA),
    }
