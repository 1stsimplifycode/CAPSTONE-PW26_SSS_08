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

PLAIN ENGLISH -- what this whole file is about:

THE PROBLEM: choosing which companies to study, without cheating.

The "Nifty 50" is a famous list of India's 50 biggest companies. It sounds like the
perfect group to study. But there is a trap, and it has a name: SURVIVORSHIP BIAS.

Here is the trap, told with a school. Suppose you want to know "how well do pupils at
this school do?", and you decide to measure it by asking the pupils who are in Year 11
TODAY. You have just made a huge mistake: every pupil who struggled and left is missing
from your survey. You only asked the survivors. So the school looks far better than it
really is -- not because anybody lied, but because of who you chose to ask.

Now the same trap with companies. Today's Nifty 50 list contains 50 successful firms.
If you use TODAY'S list to study the year 2015, you are secretly using knowledge from
the future: you already know these particular 50 turned out well. The ones that
collapsed between 2015 and now are simply absent, so your study never sees a single
failure and concludes that everything always goes brilliantly.

The honest fix is to use the list AS IT WAS IN 2015. But that historical list is not
something this project is legally allowed to obtain (and the rules of the project
explicitly forbid making one up and pretending). So instead, this file offers two
choices, and it is very clear about the standing of each:

  1. THE HONEST STAND-IN (the default). Every month, look at which companies were
     ACTUALLY being traded most heavily, using only information that existed at that
     moment, and take the top 50. A company that collapsed in 2017 still appears in the
     2015 list, because in 2015 it was genuinely busy. That is exactly right. But we
     never, ever call this "the Nifty 50", because it is not -- it is our own measure
     that happens to be about the same size.

  2. THE FIXED LIST (dangerous). Just use one list for all of history. This is the
     biased approach, and the code REFUSES to do it for past dates unless you explicitly
     tick a box marked "yes, I know this is biased". That box exists so a test can
     MEASURE how big the bias is -- not so somebody can quietly switch the safety off.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass
# `date` is a day with no time attached; `datetime` is a day plus a time.
from datetime import date, datetime
# `Protocol` describes a SHAPE that a thing must have, rather than a family it must belong
# to. Explained properly where it is used below.
from typing import Protocol

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd


# A new kind of error, for when somebody uses a future list to study the past.
class SurvivorshipBiasError(RuntimeError):
    """Raised when a forward-looking constituent list is used for a historical date."""


# A description of what any "list of companies" provider must be able to do.
class MembershipProvider(Protocol):
    # PLAIN ENGLISH: a Protocol is like a job advert rather than a family tree. It says
    # "to count as a membership provider, you must be able to do these things". Anything
    # that can do them qualifies, with no need to formally sign up. That keeps the two very
    # different providers below interchangeable without either having to inherit from the
    # other.

    # It must have a name, so results can record which provider produced them. That matters
    # enormously here: "top 50 by liquidity" and "the Nifty 50" must never be confused, and
    # carrying the name through to every result is what keeps them apart.
    name: str

    # It must be able to answer "who was in the list on this day?".
    def members_on(self, d: date) -> list[str]:
        # `...` is Python's literal "ellipsis", used here to mean "no body -- this is only
        # a description of the shape, not a real implementation".
        ...

    # It must be able to hand over the whole membership history as a table.
    def membership_table(self) -> pd.DataFrame:
        ...


@dataclass
# THE HONEST PROVIDER: choose the busiest companies, judged only on what was known at the
# time.
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
    # PLAIN ENGLISH on the jargon:
    #   "liquidity"        -- how easy something is to buy and sell. A share thousands of
    #                         people trade every day is liquid; one nobody touches is not.
    #   "traded value"     -- how much MONEY changed hands (not how many shares), which is
    #                         the fairer measure since one share of a big firm is worth far
    #                         more than one of a small one.
    #   "trailing"         -- looking backwards from now.
    #   "median"           -- the middle value when you line them all up. Used instead of the
    #                         average because one freakish day cannot drag the median about,
    #                         whereas it can badly distort an average.
    #   "rebalance"        -- redo the choosing. Here, once a month.
    #   "cardinality"      -- simply how many things are in a group.
    #   "a single huge print" -- one enormous one-off trade. Without the min_history rule, a
    #                         company nobody normally trades could have one giant day and
    #                         gatecrash the list, which would be nonsense.

    # The big table of market data to work from.
    panel: pd.DataFrame
    # How many companies to keep. 50 to match the Nifty's size -- and no more than that.
    size: int = 50
    # How many past trading days to judge on. 126 is roughly six months of trading days
    # (markets are shut at weekends, so a year is about 252 days, and half of that is 126).
    lookback: int = 126
    # How often to redo the choosing. "MS" is pandas shorthand for "Month Start".
    rebalance: str = "MS"
    # How many days of the lookback a company must actually have data for. 60 out of 126 is
    # roughly half: enough that a genuinely traded company qualifies while a one-day wonder
    # cannot.
    min_history: int = 60
    # The name carried into every result. Read it: it says "proxy" (a stand-in) and
    # "liquidity", and it pointedly does not say "nifty". The honesty is baked into the name
    # so it cannot be lost on the way to the report.
    name: str = "pit_liquidity_proxy_top50"

    # The tidy-up step run automatically after one of these is built.
    def __post_init__(self) -> None:
        # Somewhere to remember the answer once worked out, so a second question does not
        # redo all the work. None means "not worked out yet".
        self._table: pd.DataFrame | None = None

    # -- construction ----------------------------------------------------------------

    # Do the actual work: decide who is in the list at every rebalance date in history.
    def build(self) -> pd.DataFrame:
        """Compute the membership table. One row per (rebalance_date, symbol)."""
        # Take only the four columns we need, and `.copy()` to get our own private copy so
        # that anything we do here cannot possibly disturb the caller's original table.
        p = self.panel[["date", "symbol", "turnover", "knowledge_time"]].copy()
        # Throw away rows with no turnover figure. `subset=` limits the dropping to that one
        # column, so a row missing something else we do not care about is kept.
        p = p.dropna(subset=["turnover"])
        # Every distinct trading day, in order. `.unique()` removes repeats (the same date
        # appears once per company), and `np.sort` puts them in time order.
        sessions = np.sort(p["date"].unique())
        # Work out which month (or quarter) each session belongs to. `.dt.to_period("M")`
        # squashes a date down to just its month, so all of March 2015 becomes one label.
        rebal = pd.Series(sessions).dt.to_period(
            "M" if self.rebalance == "MS" else "Q")
        # For each month, the earliest session in it -- our rebalance day. We use the first
        # REAL trading session rather than the 1st of the month, because the 1st might be a
        # Sunday or a public holiday when nothing traded.
        first_of_period = pd.Series(sessions).groupby(rebal).min()

        # Reshape the data from tall to wide: dates down the side, companies across the top,
        # money traded in the middle. That shape makes "look back 126 days for everybody at
        # once" a single fast operation rather than a slow loop.
        wide = p.pivot_table(index="date", columns="symbol", values="turnover",
                             # If the same company somehow has two rows on one day, add them
                             # together, since the total money traded is the honest answer.
                             aggfunc="sum")
        # Put the dates into order. Everything below depends on the rows being in time order.
        wide = wide.sort_index()
        # Somewhere to collect the finished rows.
        rows = []
        # The list of dates down the side of the wide table.
        idx = wide.index
        # Now go through each rebalance day in turn.
        for rd in first_of_period:
            # Strictly prior sessions only: the rebalance happens before the session of
            # `rd` has produced any data, so `rd` itself must not be visible.
            # PLAIN ENGLISH: this is the whole point-in-time principle, in one line. We are
            # choosing the list on the MORNING of `rd`, when that day has not happened yet.
            # `searchsorted(rd, side="left")` finds where `rd` would slot into the sorted
            # dates, and "left" means "just BEFORE any entry equal to it" -- which is exactly
            # what excludes `rd` itself. Had it said "right", today's own trading would have
            # been included, and the whole thing would be quietly cheating.
            pos = int(idx.searchsorted(rd, side="left"))
            # The start of our window: 126 days back. `max(0, ...)` stops us running off the
            # beginning of the data in the earliest months, where less history exists.
            lo = max(0, pos - self.lookback)
            # Take that slice of history. `.iloc[lo:pos]` means "rows lo up to but NOT
            # including pos" -- and that exclusion is again what keeps `rd` out.
            window = wide.iloc[lo:pos]
            # Not enough history to judge fairly? Skip this rebalance entirely rather than
            # publishing a list we do not trust.
            if len(window) < self.min_history:
                continue
            # For each company, how many days in the window did it actually trade?
            # `.notna()` marks each cell True when a value is present, and `.sum()` counts
            # the Trues, since True counts as 1.
            counts = window.notna().sum()
            # For each company, the middle day's money traded. `skipna=True` means missing
            # days are ignored rather than being treated as zero -- important, because "did
            # not trade" and "traded nothing" are different claims.
            med = window.median(skipna=True)
            # Keep only companies with enough trading days, then drop any left with no
            # figure at all. This is the rule that stops one giant one-off trade buying a
            # company its way in.
            eligible = med[counts >= self.min_history].dropna()
            # Nobody qualified? Skip this rebalance.
            if eligible.empty:
                continue
            # Sort from busiest down, and keep the top 50.
            top = eligible.sort_values(ascending=False).head(self.size)
            # Write down one row per chosen company. `enumerate(..., 1)` numbers them
            # starting at 1 rather than the usual 0, because a human reading "rank 1" expects
            # the busiest, not "rank 0".
            for rank, (sym, val) in enumerate(top.items(), 1):
                rows.append({"rebalance_date": pd.Timestamp(rd), "symbol": sym,
                             "rank": rank, "median_turnover": float(val),
                             # Recording how many days it was observed on lets a reader
                             # judge how solid each choice was, rather than just trusting it.
                             "sessions_observed": int(counts[sym])})
        # Turn the collected rows into a proper table and remember it for next time.
        self._table = pd.DataFrame(rows)
        return self._table

    # Hand over the membership table, working it out first if that has not been done yet.
    def membership_table(self) -> pd.DataFrame:
        # This "work it out once, then remember" pattern is called lazy evaluation: do no
        # work until somebody actually asks, and then never do it twice.
        if self._table is None:
            self.build()
        return self._table

    # -- query -----------------------------------------------------------------------

    # Who was in the list on a particular day?
    def members_on(self, d: date | datetime | pd.Timestamp) -> list[str]:
        # Get the full history (built on demand).
        t = self.membership_table()
        # Turn whatever we were handed into one timestamp.
        ts = pd.Timestamp(d)
        # Every rebalance at or before that day. The ones after it have not happened yet from
        # the point of view of the question being asked.
        eff = t[t["rebalance_date"] <= ts]
        # Asking about a date before the very first rebalance? Then there is no list yet, and
        # the honest answer is an empty one -- not a guess.
        if eff.empty:
            return []
        # Of the rebalances that had happened, the most recent one is the list in force.
        last = eff["rebalance_date"].max()
        # Take that rebalance's rows, put them in rank order, and hand back just the company
        # names as a plain list.
        return eff[eff["rebalance_date"] == last].sort_values("rank")["symbol"].tolist()

    # A summary of the whole membership history, for the report.
    def turnover_stats(self) -> dict:
        t = self.membership_table()
        # For each rebalance date, how many different companies were chosen. `nunique` counts
        # distinct values.
        per = t.groupby("rebalance_date")["symbol"].nunique()
        # Every company that was ever in the list at any point.
        allsyms = t["symbol"].unique()
        return {
            # How many times we redid the choosing.
            "rebalances": int(per.size),
            # The first and last rebalance dates, as plain readable text.
            "first_rebalance": str(per.index.min().date()),
            "last_rebalance": str(per.index.max().date()),
            # The typical size of the list. Usually 50, but smaller in early months where
            # not enough companies had the required history.
            "universe_size": int(per.median()),
            # How many different companies appeared over the whole period. THIS IS THE
            # HEADLINE NUMBER against survivorship bias: if it is far more than 50 -- say
            # 130 -- then the list really did change over time, and companies really did come
            # and go. Had it come out at exactly 50, that would mean the same 50 firms every
            # month for years, which is precisely the biased snapshot we set out to avoid.
            "distinct_symbols_ever": int(len(allsyms)),
            # The average size of a chosen company's typical trading day.
            "mean_turnover_of_members": float(t["median_turnover"].mean()),
        }

    # Who joined and who left at each rebalance.
    def churn(self) -> pd.DataFrame:
        """Entries and exits per rebalance -- the direct evidence that the universe is
        not a survivorship-biased snapshot."""
        # PLAIN ENGLISH: "churn" means coming and going. This is the PROOF, not the claim.
        # A frozen, biased list would show zero entries and zero exits forever. Real churn
        # numbers are the visible evidence that companies genuinely dropped out when they
        # stopped being busy, and that we did not quietly keep only the ones that survived.
        t = self.membership_table()
        out = []
        # Remember the previous rebalance's membership. Starts empty.
        prev: set[str] = set()
        # Walk through the rebalance dates in order, with each one's group of rows.
        for rd, grp in t.groupby("rebalance_date"):
            # This rebalance's companies, as a set -- which makes the comparisons below easy.
            cur = set(grp["symbol"])
            # Skip the very first one, since with nothing before it there is nothing to
            # compare against and "everyone is new" would be a meaningless entry.
            if prev:
                out.append({"rebalance_date": rd,
                            # `cur - prev` is "in the new list but not the old" -- the
                            # newcomers. `len(...)` counts them.
                            "entries": len(cur - prev),
                            # `prev - cur` is "was in the old list but has gone" -- the
                            # leavers.
                            "exits": len(prev - cur),
                            "size": len(cur)})
            # This rebalance becomes the "previous" one for the next time round the loop.
            prev = cur
        return pd.DataFrame(out)


@dataclass
# THE DANGEROUS PROVIDER: one fixed list, used for everything.
class StaticListUniverse:
    # The companies on the list.
    symbols: list[str]
    # The date the list was accurate. Everything before this date is suspect.
    as_of: date
    # The name carried into results.
    name: str = "static_list"
    # Where the list came from.
    source: str = "user-supplied"

    # Who is in the list on a given day?
    def members_on(self, d: date | datetime | pd.Timestamp,
                   # The safety catch. Off by default, so the dangerous thing needs a
                   # deliberate act rather than merely being the path of least resistance.
                   allow_survivorship_bias: bool = False) -> list[str]:
        # Normalise through Timestamp then back to date: `isinstance(Timestamp, date)`
        # is True, so the obvious branch silently kept a Timestamp and the comparison
        # against `self.as_of` (a date) raised.
        # PLAIN ENGLISH: this comment records a real bug that was found and fixed. The
        # obvious way to write this would have been "if it is already a date, leave it
        # alone" -- but a pandas Timestamp CLAIMS to be a date while not quite being one, so
        # that check passed and then the comparison two lines later blew up. Converting
        # everything the same way, every time, with no clever shortcut, is what fixed it.
        ts = pd.Timestamp(d).date()
        # Is the question about a date before this list was accurate, and has the safety
        # catch NOT been deliberately released?
        if ts < self.as_of and not allow_survivorship_bias:
            # Then refuse. And read the error message: it explains what is wrong, and then
            # explicitly says what the override is and is not for. That last sentence is the
            # important one -- it is there so that somebody who hits this error at
            # midnight cannot tell themselves the flag is a harmless formality.
            raise SurvivorshipBiasError(
                "static list is as of %s; using it for %s imports look-ahead "
                "constituent knowledge. Pass allow_survivorship_bias=True only to "
                "quantify the bias, never to run an experiment." % (self.as_of, ts)
            )
        # `list(...)` makes a fresh copy, so a caller who edits what they receive cannot
        # accidentally rewrite our stored list.
        return list(self.symbols)

    # The membership "history" -- which for a fixed list is a single moment, honestly shown
    # as such rather than being spread across dates it was never checked against.
    def membership_table(self) -> pd.DataFrame:
        return pd.DataFrame({"rebalance_date": pd.Timestamp(self.as_of),
                             "symbol": self.symbols,
                             # Rank them 1, 2, 3... in the order they were given, since a
                             # plain list carries no other notion of importance.
                             "rank": range(1, len(self.symbols) + 1)})
