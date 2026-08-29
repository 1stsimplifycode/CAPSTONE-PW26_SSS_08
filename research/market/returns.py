"""The Week 1 return convention, in one place, enforced by a test rather than a comment.

    r_t = ln(P_t / P_{t-1})

Log returns, everywhere in the market-intelligence foundation. The convention is fixed
here so that "which return is this?" has a single answer, and
``tests/week1/test_c6_log_returns.py`` fails the build if a foundation module computes a
return any other way.

Two properties are why it is log and not simple:

* **additivity** -- a multi-session return is the sum of its daily returns, so a rolling
  window is a rolling sum and a horizon change is not a re-derivation;
* **symmetry** -- a fall and the rise that undoes it are equal and opposite, which simple
  returns are not, and which matters the moment a return is averaged.

Corporate actions are handled *before* the log is taken, not after. ``P_t`` on an ex-date
is a post-action price and ``P_{t-1}`` is a pre-action one, so the ratio carries a
mechanical jump that has nothing to do with the market. :func:`adjusted_close` divides it
out using the corroborated factors from
:mod:`research.reference.corporate_actions`; :func:`log_return` on the raw close would
report a 1:4 bonus as a 75% loss.

Scope, stated plainly: this is the convention for the Week 1 market foundation -- the
panel's ``logret_*`` columns, the index, and everything the product shows. The frozen
``ret_1d``/``ret_5d``/``ret_21d`` columns that older experiments consume are simple
returns and are left untouched, because silently redefining a column that trained models
already read would corrupt results this change has no business touching. They are marked
:data:`LEGACY_SIMPLE_RETURN_COLUMNS` and are excluded from the foundation by name.

PLAIN ENGLISH -- what this whole file is about:

HOW DO YOU MEASURE "how much did the price change?"

The obvious way: a share went from 100 to 110, so it went up 10%. That is called a
SIMPLE return, and it has two nasty flaws.

FLAW 1 -- YOU CANNOT ADD THEM UP.
Monday it rises 10%: 100 becomes 110.
Tuesday it rises 10%: 110 becomes 121.
Over two days, did it rise 20%? No! It rose 21%. The percentages do not add up, because
the second day's rise was calculated on the bigger number. So working out a week's return
means multiplying, not adding, and everything gets fiddly and error-prone.

FLAW 2 -- UPS AND DOWNS ARE NOT FAIR PARTNERS.
A share falls 50%: 100 becomes 50.
To get back to 100, it must now rise 100% -- not 50%.
So a fall of 50% and the rise that exactly undoes it have completely different numbers
(-50% and +100%). If you average those, you get +25%, and you conclude the share did
brilliantly. It ended exactly where it started. That is a real way people are misled.

THE FIX: LOG RETURNS. Take the logarithm of (new price / old price).
A logarithm is the mathematical tool that turns multiplying into ADDING. And with it:
  * Monday's log return + Tuesday's log return = the two-day log return. Exactly. Always.
    So a week is just a sum, and no horizon needs re-deriving.
  * A halving and a doubling come out as exactly -0.693 and +0.693. Equal and opposite.
    Average them and you get zero, which is the truth.

THE OTHER BIG IDEA IN THIS FILE: CORPORATE ACTIONS.
Sometimes a company splits each share into four smaller ones. If a share was 400 rupees,
tomorrow it is 100 rupees -- and NOBODY HAS LOST ANYTHING. You now simply own four
hundred-rupee shares instead of one four-hundred-rupee share.
But a naive calculation sees 400 becoming 100 and screams "a 75% crash!". So before doing
any of the maths, we must undo those mechanical changes. That is what "adjusted close"
means: every old price restated in today's share terms, so the line is comparable
end to end.

AND FINALLY, A NOTE ON HONESTY. There are older columns in this project that use the
simple, flawed method. The tempting thing would be to quietly fix them. This file
deliberately does NOT, because models were already trained reading those columns, and
silently changing what a column means would corrupt results that this work has no
business touching. So the old ones are left alone, clearly labelled as old, and excluded
by name from the new rules.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version of the convention.
RETURNS_VERSION = "returns-v1"

#: The canonical column names. Anything in the foundation reporting a return uses one.
# One day, one week (5 trading days) and one month (21 trading days). Markets shut at
# weekends, so a "month" of trading is about 21 days rather than 30.
LOG_RETURN_COLUMNS = ("logret_1d", "logret_5d", "logret_21d")

#: Pre-existing simple-return columns, frozen for artifact compatibility. Not the
#: convention, never presented as it, and excluded from the C6 enforcement scan.
# PLAIN ENGLISH: the old, flawed columns. Named here so the automatic checker knows to
# leave them alone, and so nobody reading the code mistakes them for the real thing.
LEGACY_SIMPLE_RETURN_COLUMNS = ("ret_1d", "ret_5d", "ret_21d", "return_pct")

#: Trading sessions per year, for annualising a standard deviation of daily log returns.
# About 252 days a year have trading on them: 365 minus weekends minus public holidays.
SESSIONS_PER_YEAR = 252


# Work out the log return.
def log_return(price: pd.Series | np.ndarray,
               prior: pd.Series | np.ndarray | None = None) -> pd.Series:
    """``ln(P_t / P_{t-1})``.

    With ``prior`` given, each element is paired with its own prior price -- which is how
    the bhavcopy states it, and which survives gaps in the panel that a positional shift
    would silently span. Without it, the prior is the previous element.
    """
    # PLAIN ENGLISH on why supplying the prior price matters so much. Suppose a share did
    # not trade for two weeks. If you just take "the row above", you compare today with a
    # price from a fortnight ago and call the difference a ONE DAY return. That is wrong,
    # and nothing in the data would show it. The exchange's own file already states each
    # day's proper previous price, so using that survives the gap honestly.

    # Turn the prices into a series of decimals.
    p = pd.Series(np.asarray(price, dtype=float))
    if prior is None:
        # No prior prices given, so fall back to "the row above". `.shift(1)` moves
        # everything down one place.
        q = p.shift(1)
    else:
        # Use the supplied prior prices, lined up with the same row numbering so the two
        # series pair up correctly rather than by accident.
        q = pd.Series(np.asarray(prior, dtype=float), index=p.index)
    # The calculation itself.
    # `p.where(p > 0)` keeps prices that are above zero and replaces anything else with
    # "unknown". That guard is essential: the logarithm of zero is negative infinity and the
    # logarithm of a negative number does not exist at all, so without it one bad price
    # would produce a monstrous value that then poisons every average built on top of it.
    out = np.log(p.where(p > 0) / q.where(q > 0))
    return out


# Convert a log return back into an ordinary percentage.
def simple_from_log(r: pd.Series | np.ndarray) -> pd.Series:
    """``exp(r) - 1``. For display only; never for storage or aggregation."""
    # PLAIN ENGLISH: people think in percentages, so a log return of 0.0953 is shown to them
    # as "up 10%". But the warning is firm: convert only at the very last moment, purely to
    # show a human. The instant you store or add up percentages you are back to both flaws
    # described at the top of this file.
    # `np.expm1(x)` computes exp(x) - 1, and it is used rather than writing `np.exp(x) - 1`
    # because for very small changes -- which is most days -- it is far more accurate. For a
    # tiny x, exp(x) is a whisker above 1, and subtracting 1 from it throws away most of the
    # meaningful digits. expm1 works the answer out without ever forming that near-1 value.
    return pd.Series(np.expm1(np.asarray(r, dtype=float)))


# Restate every historical price in today's share terms.
def adjusted_close(panel: pd.DataFrame, adjustments: pd.DataFrame | None,
                   close_col: str = "close") -> pd.Series:
    """Close restated onto a single corporate-action-free scale, per symbol.

    Walking backwards from the most recent session, every price before an ex-date is
    divided by that event's factor, so the whole history is expressed in today's share
    terms. The cumulative divisor is the product of every factor at or after the session,
    which is the standard back-adjustment and is exactly the per-security analogue of the
    index divisor in :mod:`research.market.index_construction`.

    With no adjustments the close is returned unchanged -- and is then not
    corporate-action safe, which callers must not paper over.
    """
    # PLAIN ENGLISH: an "ex-date" is the day a split or bonus takes effect -- from that
    # morning the shares are the new, smaller kind. A "factor" is how many new shares each
    # old one became: 4 for a four-for-one split.
    # We work BACKWARDS from today. Everything before a 4-for-1 split gets divided by 4, so
    # an old 400-rupee price is restated as 100 -- what it would have been if the shares had
    # always been today's size. And if there were several splits, we divide by all of them
    # multiplied together.
    # That final sentence is another piece of honesty: hand this no adjustment data and it
    # simply hands the prices back untouched. It does not pretend to have fixed anything, and
    # it warns the caller not to treat the result as safe.

    # Work on our own copy, as decimals.
    out = panel[close_col].astype(float).copy()
    # Nothing to adjust for? Hand the prices straight back.
    if adjustments is None or adjustments.empty:
        return out

    # Take the three columns we need and drop incomplete rows.
    adj = adjustments[["symbol", "ex_date", "combined_price_factor"]].dropna()
    if adj.empty:
        return out
    # Group the events by company, each sorted by date. Sorting matters because the running
    # multiplication below assumes time order.
    by_symbol: dict[str, pd.DataFrame] = {
        s: g.sort_values("ex_date") for s, g in adj.groupby("symbol", sort=False)}

    # A small working table of company and date.
    frame = panel[["symbol", "date"]].copy()
    # Remember each row's original position, so we can put answers back in the right places
    # after grouping shuffles things about.
    frame["_row"] = np.arange(len(frame))
    # One company at a time.
    for sym, g in frame.groupby("symbol", sort=False):
        events = by_symbol.get(sym)
        # No splits or bonuses for this company? Nothing to do.
        if events is None:
            continue
        dates = g["date"].to_numpy()
        # Cumulative product of the factors of every event strictly after the session.
        # The event dates and their factors.
        ex = events["ex_date"].to_numpy()
        fac = events["combined_price_factor"].to_numpy(dtype=float)
        # searchsorted on ex-dates: a session on or after an ex-date is already adjusted.
        # PLAIN ENGLISH: for each trading day, how many splits had ALREADY happened by then?
        # `side="right"` means a day that IS the ex-date counts as already adjusted -- which
        # is correct, because the new share size applies from that morning onwards.
        idx = np.searchsorted(ex, dates, side="right")
        # Build the running divisor for each position.
        # `fac[::-1]` reverses the factors, `np.cumprod` multiplies them up cumulatively, and
        # `[::-1]` reverses back. The result at each position is "all the factors from here
        # onwards, multiplied together". The `[1.0]` on the end covers days after every event
        # has happened -- divide by 1, meaning leave the price exactly as it is.
        tail = np.concatenate([np.cumprod(fac[::-1])[::-1], [1.0]])
        # Divide, not multiply. A pre-split price is quoted in old, larger share units;
        # restating it onto today's terms scales it *down* by every factor that has
        # since applied. Multiplying would double the discontinuity instead of removing
        # it, and would do so silently.
        # PLAIN ENGLISH: this comment is guarding against a genuinely easy mistake. Get the
        # direction wrong and you do not merely fail to fix the 400-to-100 cliff -- you turn
        # it into a 1600-to-100 cliff, four times worse, with nothing to warn you.
        out.iloc[g["_row"].to_numpy()] = (
            out.iloc[g["_row"].to_numpy()].to_numpy() / tail[idx])
    return out


# Add all the return columns to a table.
def attach_log_returns(panel: pd.DataFrame,
                       adjustments: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add ``logret_1d/5d/21d`` and ``adj_close`` to a symbol-date panel.

    The one-day return uses the bhavcopy's own ``prev_close`` when it is present, so a
    symbol that did not trade for a fortnight is not handed a fortnight-old prior price.
    Multi-day returns are rolling sums, which is the whole point of the convention.
    """
    # PLAIN ENGLISH on "which is the whole point of the convention": because log returns add
    # up, a week's return is literally just five daily ones summed. With simple returns this
    # would need a chain of multiplications and a separate derivation for every horizon.

    # Sort by company and date, on our own copy.
    df = panel.sort_values(["symbol", "date"]).copy()
    # Work out the split-adjusted prices first, since the returns must be built from those.
    df["adj_close"] = adjusted_close(df, adjustments)

    # Three cases, in order of how trustworthy they are.
    # BEST: we have adjustment data, so use the adjusted prices and the previous row.
    if adjustments is not None and not adjustments.empty:
        prior = df.groupby("symbol", sort=False)["adj_close"].shift(1)
        df["logret_1d"] = log_return(df["adj_close"], prior)
    # NEXT BEST: no adjustment data, but the exchange told us each day's own previous price,
    # which correctly handles gaps where a share did not trade.
    elif "prev_close" in df.columns:
        df["logret_1d"] = log_return(df["close"], df["prev_close"])
    # LAST RESORT: fall back to the row above. Note the grouping by company -- without it,
    # the first day of one firm would be compared against the last day of the previous firm,
    # producing a completely meaningless number.
    else:
        prior = df.groupby("symbol", sort=False)["close"].shift(1)
        df["logret_1d"] = log_return(df["close"], prior)

    # Now the multi-day returns, per company.
    g = df.groupby("symbol", sort=False)["logret_1d"]
    for window, name in ((5, "logret_5d"), (21, "logret_21d")):
        # Just a rolling SUM -- no multiplication, no compounding, no special cases. This
        # simplicity is the entire payoff of choosing log returns.
        # `.reset_index(level=0, drop=True)` removes the extra company label that grouping
        # adds, so the answer lines back up with the original rows.
        df[name] = g.rolling(window).sum().reset_index(level=0, drop=True)
    return df


# How much has the price been bouncing about?
def realised_volatility(logret: pd.Series, window: int = 21,
                        annualise: bool = True) -> pd.Series:
    """Sample standard deviation of daily log returns, annualised by convention."""
    # PLAIN ENGLISH: "volatility" is how jumpy a price is. A steady share has low volatility;
    # one that lurches about has high volatility. "Realised" means measured from what
    # actually happened, as opposed to what the market predicts will happen.
    # `.rolling(21).std(ddof=1)` measures the wobble over the last 21 trading days. The
    # `ddof=1` is the small correction for estimating from a sample rather than knowing the
    # whole truth.
    v = logret.rolling(window).std(ddof=1)
    # "Annualising" converts a daily wobble into a yearly one, so figures are comparable
    # with everybody else's. It uses the square root of 252 rather than 252 itself because
    # wobble grows with the SQUARE ROOT of time, not with time -- a well-known result which
    # follows from variances adding up while standard deviations do not.
    return v * np.sqrt(SESSIONS_PER_YEAR) if annualise else v
