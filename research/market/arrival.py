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

PLAIN ENGLISH -- what this whole file is about:

THE QUESTION: do trades arrive like raindrops, or like buses?

RAINDROPS arrive independently. One drop landing does not make the next more likely.
Mathematicians call this a POISSON process, and it has one lovely, convenient property:
if the average is 100, the amount it bounces about (technically the "variance") is also
100. Average and bounce are equal. That single fact makes all the sums easy.

BUSES are famously not like that. You wait ages, then three come at once. Something makes
them clump together.

So: which are trades? It matters enormously, because if you assume raindrops when the
truth is buses, every alarm you build will be far too twitchy.

HOW WE TELL. We use a number called the FANO FACTOR, which is simply:

        how much it bounces about  ÷  the average

If trades were raindrops, that comes out at 1. If they clump, it comes out bigger than 1.
And this project measured it on real Indian stock exchange data. The answer was not 1.
It was not 2. It was in the THOUSANDS. Trades do not merely clump -- they clump violently.
Which makes perfect sense once you think about it: traders watch each other, news sets off
a hundred people at once, and one big trade attracts more.

THE HONEST LIMITATION, stated before any result rather than buried at the end. We only
have DAILY totals -- "3,412 trades happened on Tuesday". We do not have the individual
timestamps saying which second each one happened. So we can measure how bursty things are
from day to day, but we genuinely cannot model the clustering WITHIN a single day. Some
famous models (Hawkes processes) do exactly that, and this file says plainly that we
cannot fit one, rather than fitting something that looks similar and hoping nobody asks.

TWO MODELS ARE COMPARED:
  * POISSON            -- the raindrop model. One dial: the average.
  * NEGATIVE BINOMIAL  -- the bus model. A second dial for how much things clump.
The second contains the first: turn the clumping dial all the way down and you get
raindrops back. That is what "nested" means, and it is why comparing them is fair.

WHY ANY OF THIS MATTERS: an alarm built on the raindrop assumption sets its trigger far
too close to normal. It then shrieks every single day, and an alarm that always shrieks
is exactly as useful as no alarm at all.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# `asdict` turns a record into boxes; `dataclass` marks a tidy record; `fields` lists a
# record's declared slots by name.
from dataclasses import asdict, dataclass, fields
# The world clock and the tool for reading the time.
from datetime import UTC, datetime

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd
# scipy's statistics toolbox, which knows the standard probability distributions and tests.
from scipy import stats

# A label saying what KIND of claim a number is -- measured from exchange data, assumed,
# and so on. Carrying that through means a reader can always tell fact from assumption.
from research.reference import Basis

# A label for this version of the model.
ARRIVAL_VERSION = "arrival-v1"

#: Below this many sessions a dispersion statistic is not reported: the chi-squared test
#: has no power and the Fano factor is dominated by its own sampling error.
# PLAIN ENGLISH: with fewer than 30 days of data, any answer would be mostly luck. "No
# power" means the test could not spot clumping even if it were there, and "dominated by
# sampling error" means the number would wobble more from the shortage of data than from
# anything real. So we decline to report rather than reporting noise.
MIN_SESSIONS = 30

#: A Fano factor above this, with a significant test, is treated as overdispersed.
#: Exactly 1.0 is the Poisson boundary; the margin absorbs estimation noise.
# The dividing line. Exactly 1 is raindrops; above 1 is clumping.
FANO_POISSON = 1.0

#: Significance level for the dispersion test.
# PLAIN ENGLISH: how unlikely a result must be before we accept it as real. 0.05 means
# "there is less than a 5% chance we would see something this extreme if trades really
# were raindrops". It is the conventional scientific threshold, stated openly here rather
# than being buried in the code.
ALPHA = 0.05


@dataclass
# The complete answer for one company.
class ArrivalFit:
    """One security's arrival model, both fits, and the verdict between them."""

    # Which company.
    symbol: str
    # How many days of data went into this.
    n_sessions: int
    # The average number of trades per day.
    mean_daily_trades: float
    # How much that number bounces about.
    var_daily_trades: float
    #: Poisson MLE is the sample mean; its standard error is sqrt(lambda/n).
    # PLAIN ENGLISH: "MLE" means "maximum likelihood estimate" -- the best guess for the
    # dial setting, given the data we saw. For the raindrop model that best guess is simply
    # the average, which is unusually convenient.
    poisson_lambda: float
    # How uncertain that best guess is. More days of data means a smaller, more confident
    # figure.
    poisson_lambda_standard_error: float
    #: Var/Mean. 1.0 under Poisson.
    # THE HEADLINE NUMBER: bounce divided by average.
    fano_factor: float
    #: Method-of-moments negative-binomial dispersion. Large k -> approaches Poisson.
    # The clumping dial for the bus model. Counter-intuitively, a BIG number here means
    # LESS clumping -- turn it up far enough and you are back to raindrops.
    nb_dispersion_k: float
    #: chi-squared dispersion test against the Poisson null.
    # The formal test result, and how surprising it would be under the raindrop assumption.
    dispersion_chi2: float
    dispersion_p_value: float
    # The verdict: does it clump?
    overdispersed: bool
    # Which model won.
    model_selected: str
    # The whole thing in a plain English sentence.
    interpretation: str

    # Turn the record into labelled boxes for saving.
    def to_dict(self) -> dict:
        return asdict(self)


# Fit both models to one company's daily trade counts.
def fit_symbol(symbol: str, counts: np.ndarray,
               alpha: float = ALPHA) -> ArrivalFit | None:
    """Fit both models to one security's daily trade counts."""
    # Turn the counts into a plain row of decimals.
    c = np.asarray(counts, dtype=float)
    # Keep only sensible values: real numbers (not NaN or infinity) that are zero or more.
    # A negative trade count is impossible, so its presence would mean corrupt data, and
    # letting it through would quietly poison the average and the bounce.
    c = c[np.isfinite(c) & (c >= 0)]
    n = len(c)
    # Not enough days? Hand back None -- an honest "cannot say" rather than a shaky answer.
    if n < MIN_SESSIONS:
        return None

    # The average number of trades per day.
    mean = float(np.mean(c))
    # How much it bounces about. `ddof=1` is a small but genuine correction: when you
    # estimate the bounce from a sample rather than knowing it for the whole population,
    # dividing by n-1 instead of n removes a systematic tendency to underestimate.
    var = float(np.var(c, ddof=1))
    # An average of zero would mean a share that never traded at all, and dividing by it
    # below would be impossible. Decline rather than crash.
    if mean <= 0:
        return None

    # THE HEADLINE CALCULATION. Raindrops give 1. Buses give more.
    fano = var / mean
    # Under H0: Poisson, (n-1) * s^2 / xbar ~ chi2(n-1).
    # PLAIN ENGLISH: "H0" (said "H nought") is the "null hypothesis" -- the boring
    # explanation we are trying to rule out, here "it really is just raindrops". If that were
    # true, this particular sum would follow a known bell-like shape called chi-squared. So
    # we can work out exactly how surprising our number is.
    chi2 = (n - 1) * fano
    # One-sided: overdispersion is the alternative that matters.
    # `sf` is the "survival function": the chance of getting a value THIS BIG OR BIGGER by
    # luck alone. "One-sided" because we only care about too much clumping; counts that are
    # unusually regular are not a problem for an alarm band.
    p = float(stats.chi2.sf(chi2, df=n - 1))

    # Method of moments for the negative binomial: Var = mu + mu^2 / k.
    # PLAIN ENGLISH: "method of moments" means solving for the dial that makes the model's
    # bounce match the bounce we actually observed -- simple algebra rather than a search.
    # `if var > mean` guards it: if the bounce is not bigger than the average, there is no
    # clumping to describe, so we say the dial is infinite, which means "no clumping at all"
    # and is exactly the raindrop model.
    k = float(mean ** 2 / (var - mean)) if var > mean else float("inf")

    # The verdict needs BOTH things: the Fano factor above 1, AND the result being unlikely
    # enough to be taken seriously. Requiring both is what stops us calling a small wobble
    # in a short series "clumping".
    over = bool(fano > FANO_POISSON and p < alpha)
    model = "negative_binomial" if over else "poisson"
    # Write the plain English verdict. Three genuinely different cases, each described
    # honestly rather than being squashed into "significant / not significant".
    if over:
        interp = ("Counts are overdispersed: variance is %.1fx the mean, which a Poisson "
                  "process cannot produce. Arrivals cluster." % fano)
    elif fano < FANO_POISSON:
        # Rarer, and worth naming: MORE regular than raindrops, like a metronome. That
        # happens with automated trading running to a schedule.
        interp = ("Counts are underdispersed (Fano %.2f): more regular than Poisson."
                  % fano)
    else:
        # And the honest third case: we cannot tell. Note it does not say "it is Poisson" --
        # failing to prove a difference is not the same as proving sameness.
        interp = ("Dispersion is not distinguishable from Poisson at the %.2f "
                  "level." % alpha)

    # Package the whole answer up.
    return ArrivalFit(
        symbol=symbol, n_sessions=n, mean_daily_trades=mean, var_daily_trades=var,
        # For the raindrop model, the best guess for the dial simply IS the average.
        poisson_lambda=mean,
        # How uncertain that is: the square root of the average divided by the number of
        # days. More days makes it smaller, which is exactly as it should be.
        poisson_lambda_standard_error=float(np.sqrt(mean / n)),
        fano_factor=float(fano), nb_dispersion_k=k,
        dispersion_chi2=float(chi2), dispersion_p_value=p,
        overdispersed=over, model_selected=model, interpretation=interp,
    )


# Do the same for every company in the data.
def fit_all(panel: pd.DataFrame, symbols: list[str] | None = None,
            date_from: str | None = None,
            date_to: str | None = None) -> pd.DataFrame:
    """Fit every security's arrival model from the exchange's own trade counts."""
    # Check we have the columns we need.
    need = {"symbol", "date", "trades"}
    missing = need - set(panel.columns)
    if missing:
        raise KeyError("panel is missing %s" % sorted(missing))

    # Take just those three columns and drop rows with no trade count.
    p = panel[["symbol", "date", "trades"]].dropna(subset=["trades"])
    # Optional date filters, applied only if given.
    if date_from:
        p = p[p["date"] >= pd.Timestamp(date_from)]
    if date_to:
        p = p[p["date"] <= pd.Timestamp(date_to)]
    # Optional company filter. `.upper()` makes it case-insensitive, so "reliance" finds
    # RELIANCE.
    if symbols:
        p = p[p["symbol"].isin({s.upper() for s in symbols})]

    fits = []
    # One company at a time.
    for sym, g in p.groupby("symbol", sort=False):
        fit = fit_symbol(sym, g["trades"].to_numpy())
        # Skip the ones that declined to answer for want of data.
        if fit is not None:
            fits.append(fit.to_dict())
    out = pd.DataFrame(fits)
    if out.empty:
        return out
    # Sort with the most clumped companies first, since those are the interesting ones.
    return out.sort_values("fano_factor", ascending=False).reset_index(drop=True)


# Frozen: a measurement that other parts of the system depend on must not be editable
# after the fact.
@dataclass(frozen=True)
class OverdispersionResult:
    """The Week 2 result that Week 8 consumes.

    Deliberately a small, explicit value object rather than a loose float. Week 8 must be
    able to tell "no Week 2 result was supplied" from "a Week 2 result said dispersion is
    1.0", and a bare number cannot express that difference.
    """
    # PLAIN ENGLISH: this is a really nice distinction. Imagine passing round just the
    # number 1.0. Does that mean "we measured it carefully and there is no clumping", or
    # "nobody measured anything and 1.0 was the default"? The number cannot tell you. This
    # full record can: it carries where it came from, when it was computed, and what it was
    # based on. So the detector downstream can insist on evidence, not just an answer.

    # The measured clumping factor.
    fano_factor: float
    # The bus model's clumping dial.
    nb_dispersion_k: float
    # Does it clump?
    overdispersed: bool
    # Which model won.
    model_selected: str
    # How many companies went into this.
    n_symbols: int
    # And how many days each typically had.
    n_sessions: int
    # The typical daily trade count.
    median_daily_trades: float
    # Where the data came from.
    source: str
    # When this was worked out, so a reader can spot a stale measurement.
    computed_at: str
    # What KIND of claim this is. The default says it was derived from real exchange data --
    # not assumed, not guessed.
    basis: str = str(Basis.DERIVED_FROM_EXCHANGE_DATA)

    # How much wider the BOUNCE is than raindrops would say.
    def variance_inflation(self) -> float:
        """How much wider than Poisson the count *variance* is: the Fano factor itself.

        Under Poisson it is 1.0, so a consumer that multiplies by it is unchanged in
        the degenerate case, which is right when there is nothing to correct.
        """
        # `max(1.0, ...)` never lets this go below 1. Widening a band is a safety measure;
        # NARROWING it below the standard assumption would make the alarm more twitchy than
        # the textbook, which is the opposite of what this correction is for.
        return max(1.0, float(self.fano_factor))

    # How much wider the alarm band should be.
    def sd_inflation(self) -> float:
        """How much wider than Poisson the count *standard deviation* is.

        ``sqrt(Fano)``, and this is the one an alarm band wants. A detector that sets its
        band at ``k * sqrt(lambda)`` on the Poisson assumption is too tight by exactly
        this factor; multiplying the band by it restores the coverage the detector thinks
        it has. The distinction from :meth:`variance_inflation` is not pedantry -- using
        the variance multiplier on a standard-deviation band would widen it by the square
        of what is needed.
        """
        # PLAIN ENGLISH, because this trips people up constantly.
        # "Variance" and "standard deviation" are two ways of saying how much something
        # bounces, and one is the square of the other. If the variance is 100 times bigger,
        # the standard deviation is only 10 times bigger, because 10 squared is 100.
        # Alarm bands are built from standard deviations. So if you carelessly used the
        # variance multiplier of 100 where you needed 10, your band would be TEN TIMES too
        # wide and the alarm would never go off at all. That is why this file provides both
        # numbers under clearly different names, and says out loud which is which.
        return float(np.sqrt(self.variance_inflation()))

    # Turn it into labelled boxes for saving.
    def to_dict(self) -> dict:
        d = asdict(self)
        # Include both derived numbers, so a reader of the saved file does not have to know
        # the formula or work anything out.
        d["variance_inflation"] = self.variance_inflation()
        d["sd_inflation"] = self.sd_inflation()
        return d

    # Rebuild one of these from a saved file.
    @classmethod
    def from_dict(cls, d: dict) -> OverdispersionResult:
        """Rebuild from a persisted payload.

        Keeps only the declared fields. The stored artifact also carries derived values
        and bookkeeping the writer added (``sd_inflation``, ``written_at``,
        ``consumed_by``), and a strict constructor would reject the very file it wrote.
        """
        # PLAIN ENGLISH: a lovely little trap, neatly sidestepped. When we SAVE, we helpfully
        # add extra entries (the derived numbers, the timestamp, who should read it). When we
        # LOAD, those extras are not slots on the record, so handing them all over would
        # cause an error -- the program would refuse to read the very file it had just
        # written. So we filter down to only the declared slots first.
        # `fields(cls)` lists the record's real slots, and the line below keeps only those.
        allowed = {f.name for f in fields(cls)}
        # `cls(**{...})` builds the record, handing each surviving box over by name.
        return cls(**{k: v for k, v in d.items() if k in allowed})


# Collapse every company's answer into the single number the detector needs.
def aggregate_overdispersion(fits: pd.DataFrame,
                             source: str = "cash_panel.trades") -> OverdispersionResult:
    """Collapse per-security dispersion into the one figure Week 8 consumes.

    The median rather than the mean: the Fano factor is heavily right-skewed across
    securities, and a handful of very clustered names would otherwise set the detector's
    variance for everything.
    """
    # PLAIN ENGLISH: "right-skewed" means most companies have a modest figure and a few have
    # enormous ones. If you took the average, those few monsters would drag it far above
    # where nearly every company actually sits, and the alarm would then be set far too wide
    # for the typical firm. The median -- the middle company -- ignores the extremes and
    # describes the ordinary case, which is what we want here.
    if fits.empty:
        raise ValueError("no arrival fits to aggregate")
    # The middle company's clumping factor.
    fano = float(fits["fano_factor"].median())
    # For the clumping dial, first drop the infinities (the companies with no clumping at
    # all), because a median including infinity is meaningless.
    finite_k = fits.loc[np.isfinite(fits["nb_dispersion_k"]), "nb_dispersion_k"]
    return OverdispersionResult(
        fano_factor=fano,
        # The middle finite dial, or infinity if every single company was raindrop-like.
        nb_dispersion_k=float(finite_k.median()) if len(finite_k) else float("inf"),
        # Do MOST companies clump? `.mean()` on a column of True/False gives the fraction
        # that are True, so "> 0.5" means "more than half".
        overdispersed=bool(fits["overdispersed"].mean() > 0.5),
        model_selected=("negative_binomial" if fits["overdispersed"].mean() > 0.5
                        else "poisson"),
        # How much evidence this rests on -- how many companies, and typically how many days.
        n_symbols=int(len(fits)),
        n_sessions=int(fits["n_sessions"].median()),
        median_daily_trades=float(fits["mean_daily_trades"].median()),
        source=source,
        computed_at=datetime.now(UTC).isoformat(),
    )


# Write the full report of what was found.
def summary(fits: pd.DataFrame, agg: OverdispersionResult) -> dict:
    return {
        "arrival_version": ARRIVAL_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        # Exactly which columns of which exchange file this came from.
        "data": "NSE bhavcopy trade counts (TOTALTRADES / TtlNbOfTxsExctd)",
        # THE LIMITATION, restated right in the results rather than only in the code.
        # Anybody reading the output learns what we cannot do, without having to open a file.
        "resolution": "daily counts; NSE publishes no trade timestamps in any dataset "
                      "obtained here, so inter-arrival times are not observable",
        # Exactly how the numbers were worked out, so somebody else could redo it.
        "estimator": "Poisson MLE lambda = mean daily count; negative binomial by "
                     "method of moments Var = mu + mu^2/k",
        # And exactly how the verdict was reached.
        "dispersion_test": "chi-squared (n-1)*Var/Mean against the Poisson null, "
                           "one-sided at alpha=%.2f" % ALPHA,
        # How many companies were fitted, and how many clump.
        "symbols_fitted": int(len(fits)),
        "overdispersed_symbols": int(fits["overdispersed"].sum()),
        "overdispersed_share": float(fits["overdispersed"].mean()),
        # The middle, smallest and largest clumping factors. Giving the whole range rather
        # than just the middle lets a reader see how varied companies really are.
        "median_fano_factor": float(fits["fano_factor"].median()),
        "min_fano_factor": float(fits["fano_factor"].min()),
        "max_fano_factor": float(fits["fano_factor"].max()),
        "median_daily_trades": float(fits["mean_daily_trades"].median()),
        # The single figure the detector will consume, with all its provenance attached.
        "aggregate_for_week8": agg.to_dict(),
        # And the label saying this was measured from real exchange data, not assumed.
        "basis": str(Basis.DERIVED_FROM_EXCHANGE_DATA),
    }
