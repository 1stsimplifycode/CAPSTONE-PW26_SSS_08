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
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RETURNS_VERSION = "returns-v1"

#: The canonical column names. Anything in the foundation reporting a return uses one.
LOG_RETURN_COLUMNS = ("logret_1d", "logret_5d", "logret_21d")

#: Pre-existing simple-return columns, frozen for artifact compatibility. Not the
#: convention, never presented as it, and excluded from the C6 enforcement scan.
LEGACY_SIMPLE_RETURN_COLUMNS = ("ret_1d", "ret_5d", "ret_21d", "return_pct")

#: Trading sessions per year, for annualising a standard deviation of daily log returns.
SESSIONS_PER_YEAR = 252


def log_return(price: pd.Series | np.ndarray,
               prior: pd.Series | np.ndarray | None = None) -> pd.Series:
    """``ln(P_t / P_{t-1})``.

    With ``prior`` given, each element is paired with its own prior price -- which is how
    the bhavcopy states it, and which survives gaps in the panel that a positional shift
    would silently span. Without it, the prior is the previous element.
    """
    p = pd.Series(np.asarray(price, dtype=float))
    if prior is None:
        q = p.shift(1)
    else:
        q = pd.Series(np.asarray(prior, dtype=float), index=p.index)
    out = np.log(p.where(p > 0) / q.where(q > 0))
    return out


def simple_from_log(r: pd.Series | np.ndarray) -> pd.Series:
    """``exp(r) - 1``. For display only; never for storage or aggregation."""
    return pd.Series(np.expm1(np.asarray(r, dtype=float)))


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
    out = panel[close_col].astype(float).copy()
    if adjustments is None or adjustments.empty:
        return out

    adj = adjustments[["symbol", "ex_date", "combined_price_factor"]].dropna()
    if adj.empty:
        return out
    by_symbol: dict[str, pd.DataFrame] = {
        s: g.sort_values("ex_date") for s, g in adj.groupby("symbol", sort=False)}

    frame = panel[["symbol", "date"]].copy()
    frame["_row"] = np.arange(len(frame))
    for sym, g in frame.groupby("symbol", sort=False):
        events = by_symbol.get(sym)
        if events is None:
            continue
        dates = g["date"].to_numpy()
        # Cumulative product of the factors of every event strictly after the session.
        ex = events["ex_date"].to_numpy()
        fac = events["combined_price_factor"].to_numpy(dtype=float)
        # searchsorted on ex-dates: a session on or after an ex-date is already adjusted.
        idx = np.searchsorted(ex, dates, side="right")
        tail = np.concatenate([np.cumprod(fac[::-1])[::-1], [1.0]])
        # Divide, not multiply. A pre-split price is quoted in old, larger share units;
        # restating it onto today's terms scales it *down* by every factor that has
        # since applied. Multiplying would double the discontinuity instead of removing
        # it, and would do so silently.
        out.iloc[g["_row"].to_numpy()] = (
            out.iloc[g["_row"].to_numpy()].to_numpy() / tail[idx])
    return out


def attach_log_returns(panel: pd.DataFrame,
                       adjustments: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add ``logret_1d/5d/21d`` and ``adj_close`` to a symbol-date panel.

    The one-day return uses the bhavcopy's own ``prev_close`` when it is present, so a
    symbol that did not trade for a fortnight is not handed a fortnight-old prior price.
    Multi-day returns are rolling sums, which is the whole point of the convention.
    """
    df = panel.sort_values(["symbol", "date"]).copy()
    df["adj_close"] = adjusted_close(df, adjustments)

    if adjustments is not None and not adjustments.empty:
        prior = df.groupby("symbol", sort=False)["adj_close"].shift(1)
        df["logret_1d"] = log_return(df["adj_close"], prior)
    elif "prev_close" in df.columns:
        df["logret_1d"] = log_return(df["close"], df["prev_close"])
    else:
        prior = df.groupby("symbol", sort=False)["close"].shift(1)
        df["logret_1d"] = log_return(df["close"], prior)

    g = df.groupby("symbol", sort=False)["logret_1d"]
    for window, name in ((5, "logret_5d"), (21, "logret_21d")):
        df[name] = g.rolling(window).sum().reset_index(level=0, drop=True)
    return df


def realised_volatility(logret: pd.Series, window: int = 21,
                        annualise: bool = True) -> pd.Series:
    """Sample standard deviation of daily log returns, annualised by convention."""
    v = logret.rolling(window).std(ddof=1)
    return v * np.sqrt(SESSIONS_PER_YEAR) if annualise else v
