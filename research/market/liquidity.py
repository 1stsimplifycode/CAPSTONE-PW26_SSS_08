"""The liquidity state vector, its stress gate, and what the gate blames when it fires.

Four Week 2 estimators, each measuring a different way a market can be illiquid, and each
computed elsewhere in this package from real data::

    L_t = [ RV_t , lambda_i , Amihud_it , Fano_i ]

``RV_t``       realised variance from intraday returns (research.market.realised_variance)
``lambda_i``   price impact per unit signed flow      (research.market.price_impact)
``Amihud_it``  |return| per unit turnover             (research.market.features)
``Fano_i``     trade-arrival dispersion               (research.market.arrival)

They are deliberately not redundant. Realised variance says the price moved; price impact
says it moved *because* someone traded; Amihud says the same thing from daily data and
survives where intraday does not; arrival dispersion says the trades came in bursts rather
than steadily. A security can be high on one and ordinary on the rest, and the attribution
below is what makes that visible instead of averaging it away.

**Normalisation.** Components are on incomparable scales -- variance in squared log
returns, ``lambda`` in log-price per share -- so they are standardised before combination
by a *robust* z-score::

    z = (x - median(x)) / (1.4826 * MAD(x))

Median and MAD rather than mean and standard deviation, for the same reason the thresholds
are conformal: these distributions are skewed and heavy-tailed, and a single extreme
security would otherwise set the scale for everything and flatten the rest toward zero.
The 1.4826 makes MAD consistent with the standard deviation under normality, so a z of 2
keeps its usual reading without the normality being assumed.

**The stress gate** fires when the aggregate stress score crosses a threshold that is
itself distribution-free (:mod:`research.market.thresholds`) and fitted to a declared
false-alarm budget. The score is the mean of the available components' robust z-scores,
so it is defined even when a component is missing for a security -- which matters, because
realised variance exists only for the recent intraday window while Amihud spans the daily
panel.

**Attribution is arithmetic, not narration.** When the gate fires, each component's
contribution is its own z-score's share of the total::

    contribution_j = z_j / sum_k z_k        (over components with z_k > 0)

That is computed from the same numbers that produced the score. There is no lookup table
of explanations, and :func:`attribute` has no access to any text: change an estimator and
the attribution changes, which is what the C6 test asserts.

PLAIN ENGLISH -- what this whole file is about:

WHAT IS "LIQUIDITY"? It is how easily you can buy or sell something without shoving the
price about.

A popular share is LIQUID: sell a thousand of them and the price barely notices. A share
nobody wants is ILLIQUID: try to sell a thousand and the price collapses, because you
have to keep dropping your asking price to find anybody willing to buy.

Illiquidity matters because it is where trouble hides. Prices become unreliable, small
trades cause big moves, and people who need to get out cannot.

FOUR DIFFERENT WAYS TO SPOT IT. This file uses four measurements, and the reason there
are four is that each one catches a different thing:

  1. REALISED VARIANCE     -- "the price moved a lot."
  2. PRICE IMPACT          -- "the price moved BECAUSE somebody traded."
  3. AMIHUD ILLIQUIDITY    -- the same idea as 2, but computed from daily data, so it
                              still works where the fine-grained data is missing.
  4. ARRIVAL DISPERSION    -- "the trades came in bursts rather than steadily."

Notice how 1 and 2 differ. A price can move a lot on news with almost no trading at all --
that is measurement 1 shouting while 2 stays quiet. That difference is real information,
and averaging the four into one number would destroy it. So this file keeps them separate
and, when the alarm goes off, says WHICH ones caused it.

THE PROBLEM OF COMPARING APPLES AND ORANGES. The four are measured in completely different
units -- one in squared price wiggles, another in price-per-share. Adding them together
would be like adding your height to your age. So first each is converted into "how unusual
is this compared with other companies", which is a number with no units at all, and those
can fairly be combined.

WHY "ROBUST" MATTERS. The usual way to measure "unusual" uses the average and the standard
wobble. But one absolutely catastrophic company would drag the average up and inflate the
wobble so much that every other company would look perfectly normal by comparison. So we
use the MEDIAN (the middle company) and the MAD (the typical distance from the middle)
instead. Neither of those cares what the single worst company did, so the scale stays
sensible and everybody else stays visible.
(The 1.4826 is a conversion constant: it makes MAD numerically comparable to the familiar
standard deviation, so a score of 2 still reads as "quite unusual". Note it lets us keep
the familiar reading WITHOUT having to assume the data is bell-shaped.)

AND THE BEST IDEA IN THE FILE -- HONEST BLAME.
When the alarm fires, the system says which measurement is responsible. It works this out
by pure arithmetic: each measurement's share of the total. There is no list of
pre-written explanations anywhere. This matters enormously, because a lookup table of
explanations would keep producing confident, plausible sentences even after somebody
changed the underlying maths -- the explanation would quietly stop matching the thing it
claimed to explain. Here, change an estimator and the blame changes automatically,
because the blame IS the estimator's own numbers. A test called C6 checks exactly that.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import asdict, dataclass
# The world clock and the tool for reading the time.
from datetime import UTC, datetime

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd
# The statistics toolbox.
from scipy import stats

# The threshold-fitting file explained earlier, nicknamed `T`.
from research.market import thresholds as T

# A label for this version.
LIQUIDITY_VERSION = "liquidity-v1"

#: MAD -> standard deviation under normality.
# The conversion constant that makes MAD read like a standard deviation.
MAD_SCALE = 1.4826

#: The state vector's components and the direction in which each means "less liquid".
#: Every one is produced by a Week 2 estimator; none is invented to pad the vector.
# PLAIN ENGLISH: all four are "upper", meaning a BIG value is the bad one. And the second
# sentence is a quiet point of pride: nothing was added merely to make the list look more
# impressive. Every entry is a real measurement doing real work.
COMPONENTS = {
    "realised_variance": "upper",
    "price_impact_lambda": "upper",
    "amihud": "upper",
    "arrival_fano": "upper",
}

#: Human labels, for display only. Never used in the attribution arithmetic.
# PLAIN ENGLISH: the friendly names for showing a person. The warning is the important
# part: these words never touch the maths. The blame calculation cannot see them at all, so
# it is impossible for a nice-sounding label to influence which measurement gets blamed.
COMPONENT_LABELS = {
    "realised_variance": "Realised variance",
    "price_impact_lambda": "Price impact",
    "amihud": "Amihud illiquidity",
    "arrival_fano": "Trade-arrival dispersion",
}


# Convert values into "how unusual is this", the robust way.
def robust_z(x: pd.Series | np.ndarray) -> np.ndarray:
    """Median/MAD standardisation. Zero-MAD columns return zeros, never infinities."""
    v = np.asarray(x, dtype=float)
    # Keep only real numbers for working out the middle and the spread.
    finite = v[np.isfinite(v)]
    # With fewer than two values there is no spread to speak of. Say unknown.
    if len(finite) < 2:
        return np.full(len(v), np.nan)
    # The middle value.
    med = float(np.median(finite))
    # MAD: the "median absolute deviation" -- the typical distance from the middle. Note it
    # is a median of distances, so one company a thousand times out from the middle shifts
    # it hardly at all, whereas it would send an ordinary standard deviation soaring.
    mad = float(np.median(np.abs(finite - med)))
    scale = MAD_SCALE * mad
    if scale <= 0:
        # Degenerate spread: every observation is the same, so none is unusual.
        # PLAIN ENGLISH: if every company has an identical value, there is no such thing as
        # unusual, and everybody scores zero. Dividing by the zero spread would have produced
        # infinity, which would then have swamped every score it was combined with.
        return np.where(np.isfinite(v), 0.0, np.nan)
    # How far from the middle, measured in typical distances.
    return (v - med) / scale


# -- C3: does the daily proxy rank securities the way intraday impact does? -------------
# PLAIN ENGLISH: a check that two very different ways of measuring the same thing agree.

@dataclass
# The result of comparing two rankings.
class RankCrossCheck:
    """Spearman and Kendall agreement between two liquidity rankings."""
    # PLAIN ENGLISH: Spearman and Kendall are two ways of asking "do these two lists put
    # things in the same ORDER?". Both deliberately ignore the actual values and look only
    # at the ranking, which is the right question here, since the two measurements are in
    # different units and could never be compared value for value.

    # The names of the two measurements being compared.
    measure_a: str
    measure_b: str
    # How many companies had both.
    n: int
    # Spearman's agreement number: 1 means identical order, 0 means unrelated, -1 means
    # exactly opposite.
    spearman_rho: float
    # How likely such agreement would be by pure luck.
    spearman_p_value: float
    # The range the true agreement plausibly lies in.
    spearman_ci_low: float
    spearman_ci_high: float
    # Kendall's version of the same question. Two methods are reported because they weigh
    # disagreements differently, and showing both is more honest than picking the flattering
    # one.
    kendall_tau: float
    kendall_p_value: float
    # The whole thing in a sentence.
    interpretation: str
    computed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


# Work out the plausible range for a rank agreement figure.
def _fisher_ci(rho: float, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Fisher z confidence interval for a rank correlation.

    The variance uses ``1.06/(n-3)``, the Spearman-specific correction, rather than the
    Pearson ``1/(n-3)``: rank correlations are slightly more variable and the narrower
    interval would overstate the agreement.
    """
    # PLAIN ENGLISH: a lovely piece of care. The standard textbook formula is for a
    # different kind of correlation. Applying it here would produce a range about 3% too
    # narrow -- which would make the agreement look slightly more certain than it is. Small,
    # and in the flattering direction, so exactly the sort of thing that never gets fixed.
    # Here it was.

    # Refuse to answer when the answer would be meaningless: too few companies, an unknown
    # figure, or a perfect 1 or -1 (for which the maths below produces infinity).
    if n < 5 or not np.isfinite(rho) or abs(rho) >= 1.0:
        return float("nan"), float("nan")
    # Fisher's transformation reshapes the correlation so that its uncertainty behaves like
    # a nice symmetric bell, which is what makes a simple interval valid.
    z = np.arctanh(rho)
    se = np.sqrt(1.06 / (n - 3))
    # How many wobbles wide a 95% range is -- about 1.96.
    crit = stats.norm.ppf(0.5 + conf / 2.0)
    # Build the range, then `tanh` transforms it back to ordinary correlation units.
    return float(np.tanh(z - crit * se)), float(np.tanh(z + crit * se))


# Compare the cheap daily measure against the expensive intraday one.
def cross_check_rankings(amihud: pd.Series, price_impact: pd.Series) -> RankCrossCheck:
    """Compare the Amihud illiquidity ranking against the price-impact ranking.

    Both are estimates of the same latent quantity -- how far a given amount of trading
    moves the price -- reached by different routes and from different data. Agreement is
    evidence that the daily proxy is measuring what the intraday regression measures; a
    weak correlation is equally informative and is reported rather than suppressed.
    """
    # PLAIN ENGLISH: "latent" means the real underlying thing you cannot observe directly.
    # Nobody can measure "illiquidity" itself; you can only measure its symptoms. Two very
    # different routes agreeing is real evidence they are both tracking the same hidden
    # thing.
    # And note the last clause: a WEAK result is reported just as plainly as a strong one.
    # It would be trivially easy to run this check, dislike the answer, and quietly leave it
    # out of the report. Committing in advance to publish either way is what makes the check
    # worth anything.

    # Line the two up side by side and keep only companies that have both.
    joined = pd.concat([amihud.rename("amihud"),
                        price_impact.rename("lambda")], axis=1).dropna()
    n = len(joined)
    # Too few to say anything? Report that honestly rather than computing a meaningless
    # number from four companies.
    if n < 5:
        return RankCrossCheck(
            "amihud", "price_impact_lambda", n, float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"), float("nan"),
            "Too few securities with both measures to compare rankings.",
            datetime.now(UTC).isoformat())

    # Run both agreement tests.
    rho, p_rho = stats.spearmanr(joined["amihud"], joined["lambda"])
    tau, p_tau = stats.kendalltau(joined["amihud"], joined["lambda"])
    lo, hi = _fisher_ci(float(rho), n)

    # Write the verdict. Three genuinely different outcomes, each described honestly.
    # CASE 1: they agree, and it is unlikely to be luck. Good -- the cheap measure works.
    if p_rho < 0.05 and rho > 0:
        interp = ("The two rankings agree (rho=%.3f, p=%.4g, n=%d): securities the "
                  "daily Amihud proxy calls illiquid are the ones the intraday "
                  "regression finds have the largest price impact."
                  % (rho, p_rho, n))
    # CASE 2: they significantly DISAGREE. Alarming, and stated plainly: one of the two is
    # wrong, and we are not saying which, because we do not know.
    elif p_rho < 0.05 and rho < 0:
        interp = ("The rankings disagree significantly (rho=%.3f, p=%.4g, n=%d). "
                  "One of the two is not measuring illiquidity on this sample."
                  % (rho, p_rho, n))
    # CASE 3: no clear relationship. Note the careful phrasing -- "is not demonstrated to
    # track", not "does not track". Failing to show a link is not the same as showing there
    # is none, and the sentence respects that difference.
    else:
        interp = ("No significant rank agreement (rho=%.3f, p=%.4g, n=%d). The daily "
                  "proxy is not demonstrated to track intraday price impact here."
                  % (rho, p_rho, n))

    return RankCrossCheck(
        measure_a="amihud", measure_b="price_impact_lambda", n=n,
        spearman_rho=float(rho), spearman_p_value=float(p_rho),
        spearman_ci_low=lo, spearman_ci_high=hi,
        kendall_tau=float(tau), kendall_p_value=float(p_tau),
        interpretation=interp, computed_at=datetime.now(UTC).isoformat())


# -- C6: the state vector --------------------------------------------------------------

# Combine the four measurements into one stress score.
def build_state_vector(components: pd.DataFrame) -> pd.DataFrame:
    """Standardise the components and combine them into a stress score.

    One row per security. Each component keeps its raw value *and* its robust z-score,
    because the attribution needs the z and the reader needs the raw number.
    """
    # PLAIN ENGLISH: both are kept, deliberately. The maths needs the standardised score,
    # but a human reading the report wants the actual measurement -- "Amihud was 0.0043"
    # means something checkable, whereas "z was 2.7" only means something relative.

    # Which of the four are actually present in this data.
    present = [c for c in COMPONENTS if c in components.columns]
    # None at all? There is nothing to build, so stop rather than producing an empty score
    # that would look like a real one.
    if not present:
        raise ValueError(
            "no liquidity components present; expected some of %s" % list(COMPONENTS))

    out = components.copy()
    zcols = []
    # Standardise each one, storing the result in a new column beside the original.
    for c in present:
        zc = "z_%s" % c
        out[zc] = robust_z(out[c])
        zcols.append(zc)

    # Mean over the components that exist for this row: a security with no intraday
    # coverage still gets a score from the daily components rather than being dropped.
    # PLAIN ENGLISH: a genuinely useful choice. Fine-grained intraday data only exists for a
    # recent window, while the daily measures go back years. Insisting on all four would
    # throw away most of the history. `skipna=True` averages whatever is there.
    out["stress_score"] = out[zcols].mean(axis=1, skipna=True)
    # And record HOW MANY were available, so a reader can tell a score from four
    # measurements apart from a score from one. Without this the two would look identical.
    out["components_available"] = out[zcols].notna().sum(axis=1)
    # `.attrs` is a little notepad attached to the table, carrying which measurements were
    # used so later steps do not have to work it out again and risk disagreeing.
    out.attrs["components"] = present
    out.attrs["z_columns"] = zcols
    return out


# Work out which measurement is to blame.
def attribute(row: pd.Series, components: list[str]) -> dict[str, float]:
    """Each component's share of the stress this row shows.

    Only components pushing *toward* stress (positive z) can take credit for it, and the
    shares are normalised over those. A component sitting below the median is not
    responsible for an alarm, and giving it a negative share would let two components
    cancel into a confident-looking zero.

    Computed entirely from ``row``. No constants, no strings, no lookup.
    """
    # PLAIN ENGLISH on the positive-only rule. Suppose one measurement is wildly high (+3)
    # and another wildly low (-3). If both counted, they would add to zero and the system
    # would confidently announce "nothing to see here" -- while one measurement is screaming.
    # Only counting the ones actually pushing towards trouble prevents that cancellation.
    # And the final line is the guarantee: the blame is worked out from this row's own
    # numbers, and from nothing else at all.

    # Fetch each measurement's standardised score, or unknown where absent.
    z = {c: float(row.get("z_%s" % c, np.nan)) for c in components}
    # Keep only real numbers that are above the middle.
    positive = {c: v for c, v in z.items() if np.isfinite(v) and v > 0}
    total = sum(positive.values())
    # Nothing pushing towards trouble? Then nobody is to blame, and everybody gets zero.
    if total <= 0:
        return dict.fromkeys(components, 0.0)
    # Each one's share of the total, so the shares add up to 1 -- i.e. 100% of the blame is
    # accounted for, with none invented and none lost.
    return {c: (positive.get(c, 0.0) / total) for c in components}


@dataclass
# The alarm itself.
class StressGate:
    """Fires when the stress score crosses a distribution-free threshold."""

    # The line, fitted to the declared false-alarm budget by the thresholds file.
    threshold: T.Threshold
    # Which measurements make up the score.
    components: list[str]

    # Run the alarm over a table of scores.
    def evaluate(self, state: pd.DataFrame) -> pd.DataFrame:
        """Flag stressed rows and attribute each firing to its estimators."""
        out = state.copy()
        # Which rows are above the line.
        out["stress_gate_fired"] = self.threshold.flag(
            out["stress_score"].to_numpy())

        attributions = []
        # Work out the blame for each row.
        for _, row in out.iterrows():
            # No alarm means no blame to apportion -- everybody zero.
            if not row["stress_gate_fired"]:
                attributions.append(dict.fromkeys(self.components, 0.0))
                continue
            attributions.append(attribute(row, self.components))

        # Turn the blame into proper columns, one per measurement.
        for c in self.components:
            out["attribution_%s" % c] = [a.get(c, 0.0) for a in attributions]

        fired = out["stress_gate_fired"]
        cols = ["attribution_%s" % c for c in self.components]
        # The single biggest culprit for each firing. `.idxmax(axis=1)` finds which COLUMN
        # holds the largest value in each row, and `.str.replace(...)` strips the
        # "attribution_" prefix off to leave the bare measurement name.
        out["primary_driver"] = np.where(
            fired, out[cols].idxmax(axis=1).str.replace("attribution_", "", regex=False),
            # Quiet rows get an empty name, not a made-up culprit.
            "")
        return out

    def to_dict(self) -> dict:
        return {
            "liquidity_version": LIQUIDITY_VERSION,
            "components": self.components,
            "threshold": self.threshold.to_dict(),
            # The blame rule written out in words, in the output itself, so a reader can
            # check the arithmetic without reading any code.
            "attribution_rule": (
                "contribution_j = z_j / sum over components with z_k > 0. Computed from "
                "the state vector's own z-scores; no hardcoded explanation."),
        }


# Fit the alarm's threshold.
def fit_stress_gate(state: pd.DataFrame,
                    budget: T.FalseAlarmBudget = T.FALSE_ALARM_BUDGET,
                    calibration: np.ndarray | None = None) -> StressGate:
    """Fit the gate's threshold to the declared false-alarm budget."""
    # Use a separate calibration sample if one was given; otherwise use the scores we have.
    # Being able to pass a separate one matters, because the honest way to set the line is
    # from a period known to be ordinary, not from the same data you are about to judge.
    scores = (state["stress_score"].to_numpy() if calibration is None
              else np.asarray(calibration, dtype=float))
    # Fit it using the distribution-free method from the thresholds file.
    th = T.fit_threshold("stress_score", scores, budget, direction="upper")
    return StressGate(threshold=th, components=list(state.attrs.get("components", [])
                                                    # Fall back to working the list out from
                                                    # the columns, in case the notepad was
                                                    # lost when the table was copied about.
                                                    or [c for c in COMPONENTS
                                                        if c in state.columns]))


# Write the report.
def summary(state: pd.DataFrame, gate: StressGate,
            cross_check: RankCrossCheck | None) -> dict:
    fired = state.get("stress_gate_fired")
    out = {
        "liquidity_version": LIQUIDITY_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        # The formula written out, e.g. "L = [realised_variance, amihud]".
        "state_vector": "L = [%s]" % ", ".join(gate.components),
        "components": gate.components,
        # How the measurements were made comparable -- stated, not assumed.
        "normalisation": "robust z, (x - median) / (1.4826 * MAD)",
        "securities": int(len(state)),
        "stress_threshold": gate.threshold.threshold,
        # The promise the line was fitted to, carried right through to the report.
        "false_alarm_budget": gate.threshold.budget,
        "threshold_method": gate.threshold.method,
        "distribution_free": gate.threshold.distribution_free,
        "gate_fired": int(fired.sum()) if fired is not None else 0,
        "attribution_rule": gate.to_dict()["attribution_rule"],
    }
    # If anything fired, add the detail.
    if fired is not None and fired.any():
        # How often each measurement was the main culprit.
        drivers = state.loc[fired, "primary_driver"].value_counts().to_dict()
        out["primary_drivers"] = {k: int(v) for k, v in drivers.items()}
        # A sample of the companies flagged. `[:20]` keeps the report readable rather than
        # dumping thousands of names into it.
        out["fired_symbols"] = state.loc[fired, "symbol"].tolist()[:20]
    if cross_check is not None:
        out["amihud_vs_price_impact"] = cross_check.to_dict()
    return out


# -- external validation against the exchange's own band-hit record ---------------------

# Check the alarm against a completely independent fact.
def validate_against_band_hits(state: pd.DataFrame,
                               band_flags: pd.DataFrame) -> dict:
    """Check the stress gate against an independent exchange fact.

    A security pinned at its circuit limit could not trade freely on that session. That is
    NSE's own statement about the session, arrived at with no reference to realised
    variance, price impact, Amihud or arrival dispersion. So the rate at which band hits
    coincide with the gate firing is a genuine external check on whether the state vector
    is detecting illiquidity or detecting itself.

    Reported as a lift with both base rates, not as a pass/fail: the gate is tuned to a 1%
    false-alarm budget on a different quantity, so exact agreement is not expected and
    would be suspicious if it appeared.
    """
    # PLAIN ENGLISH: a "circuit limit" or "band" is a rule stopping a share moving more than
    # a set percentage in one day. Hit the limit and trading in it effectively stops. That is
    # about as clear a statement of "this could not be traded normally" as exists.
    # The crucial thing is that the exchange decides this on its own, knowing nothing about
    # our four measurements. So it is a genuinely OUTSIDE opinion. Everything else in this
    # file is our own reasoning checking our own reasoning; this is the one place something
    # independent gets a say -- which is why the docstring says it checks whether the vector
    # is "detecting illiquidity or detecting itself".
    # And the last paragraph is unusually wise: we do NOT expect the two to match perfectly,
    # and we say so IN ADVANCE. If they matched perfectly we would be suspicious rather than
    # delighted, because they are measuring related but different things. Stating what would
    # count as too-good-to-be-true, before looking, is exactly how you avoid fooling yourself.

    # Nothing to check against.
    if "stress_gate_fired" not in state.columns:
        return {"available": False, "why": "state vector has no gate result"}

    # Join our results to the exchange's record, matching on company and session.
    merged = state.merge(
        band_flags[["symbol", "session", "band_hit"]], on=["symbol", "session"],
        # `how="left"` keeps every one of our rows, whether or not the exchange has a
        # matching record for it.
        how="left")
    # Where there is no exchange record, treat it as "did not hit the band" -- which is the
    # right reading, since the exchange publishes hits and silence means no hit.
    merged["band_hit"] = merged["band_hit"].fillna(False).astype(bool)

    fired = merged["stress_gate_fired"].astype(bool)
    n_fired = int(fired.sum())
    # If the alarm never fired there is nothing to compare, and we say so plainly rather
    # than dividing by zero.
    if n_fired == 0:
        return {"available": True, "gate_fired": 0,
                "note": "the gate did not fire on any observation in this window"}

    # How often the band was hit on days we called stressed...
    hit_when_fired = float(merged.loc[fired, "band_hit"].mean())
    # ...how often on days we called quiet...
    hit_when_quiet = float(merged.loc[~fired, "band_hit"].mean())
    # ...and how often overall. All three are reported, because the first number alone means
    # nothing without something to compare it against.
    base = float(merged["band_hit"].mean())
    return {
        "available": True,
        "observations": int(len(merged)),
        "gate_fired": n_fired,
        "band_hit_base_rate": base,
        "band_hit_rate_when_gate_fired": hit_when_fired,
        "band_hit_rate_when_gate_quiet": hit_when_quiet,
        # "Lift" is how many times more likely a band hit is when we fire than in general.
        # A lift of 5 means five times more likely, which would be strong evidence the alarm
        # is finding something real.
        "lift": (hit_when_fired / base) if base > 0 else None,
        # Exactly where the independent fact came from.
        "source": "NSE PR bundle bh member (exchange-published band hits)",
        # And the finding in a plain sentence, with both rates side by side so the reader
        # always sees the comparison rather than an impressive-looking number on its own.
        "interpretation": (
            "Securities the gate called stressed hit a circuit band on %.2f%% of those "
            "sessions, against a %.2f%% base rate across the window."
            % (hit_when_fired * 100, base * 100)),
    }
