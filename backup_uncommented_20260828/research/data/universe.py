"""Research universe construction (spec section 4).

The specification asks for a NIFTY-50-style universe with *historical* membership. The
audit found no licence-clear source of point-in-time Nifty-50 constituents, and section 85
forbids inventing one. This module therefore offers two providers with very different
standing:

``LiquidityProxyUniverse``
    The default. At each rebalance it ranks symbols by trailing median traded value using
    only bars whose ``knowledge_time`` precedes the rebalance cutoff, and keeps the top
    *N*. It is survivorship-safe by construction: a company that later delists is still
    selected on the dates when it was liquid, and a company that later becomes liquid is
    not selected early. **It is not the Nifty 50 and is never labelled as such.**

``StaticListUniverse``
    A fixed list supplied by the user. Refuses to serve historical dates unless the
    caller passes ``allow_survivorship_bias=True``, which exists so that leakage test L4
    can demonstrate the bias rather than so that experiments can quietly incur it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import numpy as np
import pandas as pd


class SurvivorshipBiasError(RuntimeError):
    """Raised when a forward-looking constituent list is used for a historical date."""


class MembershipProvider(Protocol):
    name: str

    def members_on(self, d: date) -> list[str]:
        ...

    def membership_table(self) -> pd.DataFrame:
        ...


@dataclass
class LiquidityProxyUniverse:
    """Point-in-time top-*N* by trailing median traded value.

    Parameters
    ----------
    panel
        Long panel with ``date``, ``symbol``, ``turnover``, ``knowledge_time``.
    size
        Universe size. 50 mirrors the Nifty-50 cardinality without claiming its identity.
    lookback
        Trading sessions used for the liquidity estimate.
    rebalance
        Pandas offset alias for rebalance dates (``MS`` = month start).
    min_history
        A symbol must have at least this many observations inside the lookback to be
        eligible; prevents a single huge print from buying entry.
    """

    panel: pd.DataFrame
    size: int = 50
    lookback: int = 126
    rebalance: str = "MS"
    min_history: int = 60
    name: str = "pit_liquidity_proxy_top50"

    def __post_init__(self) -> None:
        self._table: pd.DataFrame | None = None

    # -- construction ----------------------------------------------------------------

    def build(self) -> pd.DataFrame:
        """Compute the membership table. One row per (rebalance_date, symbol)."""
        p = self.panel[["date", "symbol", "turnover", "knowledge_time"]].copy()
        p = p.dropna(subset=["turnover"])
        sessions = np.sort(p["date"].unique())
        rebal = pd.Series(sessions).dt.to_period(
            "M" if self.rebalance == "MS" else "Q")
        first_of_period = pd.Series(sessions).groupby(rebal).min()

        wide = p.pivot_table(index="date", columns="symbol", values="turnover",
                             aggfunc="sum")
        wide = wide.sort_index()
        rows = []
        idx = wide.index
        for rd in first_of_period:
            # Strictly prior sessions only: the rebalance happens before the session of
            # `rd` has produced any data, so `rd` itself must not be visible.
            pos = int(idx.searchsorted(rd, side="left"))
            lo = max(0, pos - self.lookback)
            window = wide.iloc[lo:pos]
            if len(window) < self.min_history:
                continue
            counts = window.notna().sum()
            med = window.median(skipna=True)
            eligible = med[counts >= self.min_history].dropna()
            if eligible.empty:
                continue
            top = eligible.sort_values(ascending=False).head(self.size)
            for rank, (sym, val) in enumerate(top.items(), 1):
                rows.append({"rebalance_date": pd.Timestamp(rd), "symbol": sym,
                             "rank": rank, "median_turnover": float(val),
                             "sessions_observed": int(counts[sym])})
        self._table = pd.DataFrame(rows)
        return self._table

    def membership_table(self) -> pd.DataFrame:
        if self._table is None:
            self.build()
        return self._table

    # -- query -----------------------------------------------------------------------

    def members_on(self, d: date | datetime | pd.Timestamp) -> list[str]:
        t = self.membership_table()
        ts = pd.Timestamp(d)
        eff = t[t["rebalance_date"] <= ts]
        if eff.empty:
            return []
        last = eff["rebalance_date"].max()
        return eff[eff["rebalance_date"] == last].sort_values("rank")["symbol"].tolist()

    def turnover_stats(self) -> dict:
        t = self.membership_table()
        per = t.groupby("rebalance_date")["symbol"].nunique()
        allsyms = t["symbol"].unique()
        return {
            "rebalances": int(per.size),
            "first_rebalance": str(per.index.min().date()),
            "last_rebalance": str(per.index.max().date()),
            "universe_size": int(per.median()),
            "distinct_symbols_ever": int(len(allsyms)),
            "mean_turnover_of_members": float(t["median_turnover"].mean()),
        }

    def churn(self) -> pd.DataFrame:
        """Entries and exits per rebalance -- the direct evidence that the universe is
        not a survivorship-biased snapshot."""
        t = self.membership_table()
        out = []
        prev: set[str] = set()
        for rd, grp in t.groupby("rebalance_date"):
            cur = set(grp["symbol"])
            if prev:
                out.append({"rebalance_date": rd,
                            "entries": len(cur - prev),
                            "exits": len(prev - cur),
                            "size": len(cur)})
            prev = cur
        return pd.DataFrame(out)


@dataclass
class StaticListUniverse:
    symbols: list[str]
    as_of: date
    name: str = "static_list"
    source: str = "user-supplied"

    def members_on(self, d: date | datetime | pd.Timestamp,
                   allow_survivorship_bias: bool = False) -> list[str]:
        # Normalise through Timestamp then back to date: `isinstance(Timestamp, date)`
        # is True, so the obvious branch silently kept a Timestamp and the comparison
        # against `self.as_of` (a date) raised.
        ts = pd.Timestamp(d).date()
        if ts < self.as_of and not allow_survivorship_bias:
            raise SurvivorshipBiasError(
                "static list is as of %s; using it for %s imports look-ahead "
                "constituent knowledge. Pass allow_survivorship_bias=True only to "
                "quantify the bias, never to run an experiment." % (self.as_of, ts)
            )
        return list(self.symbols)

    def membership_table(self) -> pd.DataFrame:
        return pd.DataFrame({"rebalance_date": pd.Timestamp(self.as_of),
                             "symbol": self.symbols,
                             "rank": range(1, len(self.symbols) + 1)})
