"""Shared loading and slicing for the live analysis adapters.

Two jobs, both of which exist so the analysis adapters can stay thin:

**Caching.** A live analysis runs on request, and re-reading a 300,000-row parquet on
every keystroke would make the interface feel broken for reasons that have nothing to do
with the research. Frames are read once per process and reused. They are never mutated:
every slicing helper returns a copy, because an adapter that filtered in place would
poison the cache for the next request.

**One filter.** Every adapter that takes a date range and an instrument list applies it
the same way, so two modules asked for the same slice see the same rows. A slice that is
too small to analyse is refused here rather than producing a confident number over eleven
observations.

PLAIN ENGLISH -- what this whole file is about:

LOADING THE DATA ONCE, AND CUTTING IT THE SAME WAY EVERY TIME.

JOB ONE: CACHING. The data file has 300,000 rows. Reading it from disk takes real time. If
every button press re-read it, the website would feel broken -- and for a reason that has
nothing to do with the research being slow.
So it is read once and kept in memory.

AND THE TRAP THAT COMES WITH THAT: if one adapter filters the shared copy IN PLACE, the next
request gets the already-filtered version, and its answer is silently wrong. So every
function here returns a COPY. The phrase in the docstring is exactly right -- filtering in
place would "poison the cache for the next request."

JOB TWO: ONE FILTER FOR EVERYONE. Two modules asked for "January, these five companies"
must see the SAME rows. Two separate filtering implementations would eventually disagree
about an edge case -- and produce two different answers to one question.

AND THE SUBTLEST IDEA IN THE FILE is the difference between "which days did you ASK about"
and "what could we have KNOWN by then". Read `slice_frame` below -- they are not the same
thing, and confusing them is how a system accidentally cheats.
"""
from __future__ import annotations

# functools provides the caching decorator used throughout.
import functools

import pandas as pd

from research.core import paths
from research.data import pit

#: Below this many rows a slice does not produce a small result, it produces a
#: meaningless one. Adapters refuse rather than return one.
MIN_ROWS = 30


# `lru_cache` means: run this once, remember the answer, hand the same answer back for every
# later call. `maxsize=1` because there is only one panel.
@functools.lru_cache(maxsize=1)
def panel() -> pd.DataFrame:
    """The assembled modelling panel."""
    return pd.read_parquet(paths.PANEL / "market_dataset.parquet")


@functools.lru_cache(maxsize=1)
def cash_panel() -> pd.DataFrame:
    """The NSE daily cash panel, for anything needing prices rather than features."""
    return pd.read_parquet(paths.PANEL / "cash_panel.parquet")


@functools.lru_cache(maxsize=1)
def universe() -> pd.DataFrame:
    """The point-in-time liquidity-proxy universe and its membership history."""
    # "Membership history" matters: which companies were in the sample changes over time, and
    # using today's list for a 2019 question would be hindsight.
    return pd.read_parquet(paths.PANEL / "universe.parquet")


# maxsize=48 here, because there are many arms and each has its own file.
@functools.lru_cache(maxsize=48)
def per_row(arm: str) -> pd.DataFrame | None:
    """Per-row scores for one executed ablation arm, or None if that arm was not run."""
    p = paths.ARTIFACTS / "experiments" / ("per_row_%s.parquet" % arm)
    # None for "that arm was never run" -- distinct from an empty table, which would mean
    # "it ran and found nothing".
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def available_arms() -> tuple[str, ...]:
    d = paths.ARTIFACTS / "experiments"
    if not d.exists():
        # An empty tuple, not a crash. The site can still say "no arms have been run".
        return ()
    # LOOK AT WHAT IS ACTUALLY ON DISK rather than trusting a hard-coded list. `.stem` is the
    # filename without its extension; stripping the prefix leaves the arm name.
    return tuple(sorted(p.stem.replace("per_row_", "")
                        for p in d.glob("per_row_*.parquet")))


@functools.lru_cache(maxsize=1)
def symbols() -> tuple[str, ...]:
    # Every company in the panel, alphabetically.
    return tuple(sorted(panel()["symbol"].unique()))


@functools.lru_cache(maxsize=1)
def panel_dates() -> tuple[str, str]:
    # The real first and last date IN THE DATA -- so the interface's date pickers cannot
    # offer a range the data does not cover.
    d = panel()["date"]
    return str(d.min().date()), str(d.max().date())


def slice_frame(df: pd.DataFrame, date_from: str | None = None,
                date_to: str | None = None,
                instruments: list[str] | None = None,
                split: str | None = None,
                asof: pit.AsOf | None = None,
                require_point_in_time: bool = True) -> pd.DataFrame:
    """Apply the caller's selection point-in-time. The cached frame is never touched.

    The date range selects *which sessions the caller asked about*. It is not, and must
    not be, the leakage boundary: the bhavcopy for the last requested session is
    published after that session closes, so a range filter alone would expose rows the
    system could not have known. The knowledge bound is applied separately by
    :func:`research.data.pit.as_of_frame`, from ``asof``.

    ``asof`` defaults to the publication instant of ``date_to`` -- the honest reading of
    "give me everything through this session". Frames that carry no knowledge-time column
    are read with ``require_point_in_time=False``; :data:`NON_BITEMPORAL_FRAMES` records
    which those are and why.

    PLAIN ENGLISH -- THE MOST IMPORTANT IDEA IN THIS FILE.

    TWO DIFFERENT QUESTIONS THAT LOOK LIKE ONE:
      "Which days am I asking about?"  -> the date range.
      "What could we have known by then?" -> the knowledge cutoff.

    Here is why they differ. You ask for everything up to 5 March. The official end-of-day
    summary for 5 March -- the bhavcopy -- is not published until that evening, after the
    market shuts. So a date filter alone hands you 5 March's figures as though they were
    available ON 5 March. They were not. Nobody had them yet.

    That is LEAKAGE: using information from the future. A model fed leaked data looks
    brilliant in testing and falls apart in reality, because in reality the information
    arrives too late to act on.

    So the date range picks the sessions, and a SEPARATE knowledge cutoff removes anything
    that had not been published yet. Two filters, doing two different jobs.
    """
    out = df
    # The date range: which sessions were asked about.
    if date_from:
        out = out[out["date"] >= pd.Timestamp(date_from)]
    if date_to:
        out = out[out["date"] <= pd.Timestamp(date_to)]
    if instruments:
        # Upper-case both sides, so "reliance" finds RELIANCE.
        wanted = {s.upper() for s in instruments}
        out = out[out["symbol"].str.upper().isin(wanted)]
    if split and split != "all" and "split" in out.columns:
        out = out[out["split"] == split]

    if require_point_in_time:
        # THE KNOWLEDGE CUTOFF. `after_publication(date_to)` means "the moment that session's
        # figures actually became available" -- not midnight on that date.
        cutoff = asof or (pit.AsOf.after_publication(date_to) if date_to
                          else pit.AsOf.latest())
        out = pit.as_of_frame(out, cutoff)
        # AND THEN IT IS CHECKED AGAIN. Belt and braces: the filter above should already have
        # removed everything too new, and this raises if anything slipped through. A silent
        # leak is the failure that would invalidate every downstream number, so it gets a
        # guard rather than trust.
        pit.assert_no_leakage(out, cutoff)
    # `.copy()` ALWAYS, at the very end. This is the line that protects the cache: the caller
    # gets their own copy to do as they like with, and the shared original is untouched.
    return out.copy()


#: Frames with no knowledge-time column, and the reason each is exempt. Anything not
#: named here is read point-in-time; the C2 test asserts this list does not grow
#: silently.
# PLAIN ENGLISH: a very short list of exceptions -- and each one comes with an argument for
# why it is legitimately exempt, not merely a note that it is.
# AND A TEST WATCHES THE LIST. Adding a new exemption fails that test, so nobody can quietly
# widen the exception by one more entry, then another.
NON_BITEMPORAL_FRAMES = {
    # Model outputs, not market observations -- and their INPUTS were already read
    # point-in-time, so the leakage question was answered upstream.
    "per_row_scores": ("Model scores for an already-executed experiment arm. Not "
                       "market history: they are outputs of a run whose inputs were "
                       "themselves read point-in-time."),
    # The labels were CONSTRUCTED, not observed -- so there is no publication moment to
    # respect. And the limitation it creates is named right here: L-04.
    "episode_labels": ("Synthetic episode ground truth generated with the panel, not "
                       "observed from the market (limitation L-04)."),
}


def as_of_for(date_to: str | None) -> pit.AsOf:
    """The knowledge cutoff implied by a request for sessions through ``date_to``."""
    # No end date -> "everything known now".
    return pit.AsOf.after_publication(date_to) if date_to else pit.AsOf.latest()


def describe_slice(df: pd.DataFrame, source: str, asof: pit.AsOf | None = None,
                   **selection) -> dict:
    """What the caller actually got, so a response can never imply a wider slice."""
    # PLAIN ENGLISH: you ask for 2020 to 2024 across fifty companies. The data only holds
    # 2022 to 2023 for twelve of them. Without this, the answer would arrive looking like an
    # answer about fifty companies over five years.
    # So every response carries a description of WHAT WAS ACTUALLY ANALYSED -- the real row
    # count, the real company count, the real first and last date.
    out = {
        "source": source,
        "rows": int(len(df)),
        # The `if ... in df.columns` guards make this safe on frames of any shape.
        "instruments": int(df["symbol"].nunique()) if "symbol" in df.columns else None,
        # The ACTUAL first and last date present, not the ones requested.
        "date_from": str(df["date"].min().date()) if len(df) and "date" in df else None,
        "date_to": str(df["date"].max().date()) if len(df) and "date" in df else None,
        # AND WHAT WAS ASKED FOR, kept alongside -- so the difference between request and
        # result is visible. Empty values are dropped, to keep the record readable.
        "selection": {k: v for k, v in selection.items() if v not in (None, "", [])},
    }
    if asof is not None:
        # The knowledge cutoff travels with the result too.
        out["point_in_time"] = asof.to_dict()
    return out
