"""Market panel assembly.

Produces one row per (instrument, decision_time) with every feature block attached, plus
the coverage flags that the uncertainty-aware model needs. This is the only place where
the blocks meet; everything upstream computes a single block and everything downstream
consumes this frame.

Point-in-time discipline, in one sentence: every block for row *t* is computed from a
strictly backward-looking window ending at *t*, and the knowledge cutoff attached to the
row is the bhavcopy publication instant for *t*.

PLAIN ENGLISH -- what this whole file is about:

This file is the KITCHEN where all the separate ingredients get combined into one dish.

Elsewhere in the project, different bits of code each work out one kind of measurement:
  * one works out price behaviour,
  * one works out the fine detail of trading,
  * one works out what mood the whole market was in,
  * one works out trouble spreading in from connected companies.

Each of those is called a "block" of "features". A "feature" is simply one measured
number that we think might be useful.

This file is the only place where all four blocks come together. That is deliberate and
worth pausing on: if four different files each combined things in slightly their own
way, they would drift apart and nobody could say which was correct. One kitchen means
one recipe.

The result is one big table. Each row answers: "for THIS company, on THIS day, here is
every measurement we had, plus how complete that information was."

That last part -- "how complete" -- is called COVERAGE, and it is unusually honest. Most
systems quietly pretend missing information is zero. This one records what fraction it
actually had, so a confident-looking answer built on a quarter of the data can be told
apart from the same answer built on all of it.

And the discipline sentence at the top means: to work out a row for the 5th of March, we
look only at the 5th of March and BEFORE. Never after. Not even a minute after.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types with smarter defaults.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The town crier, for announcing progress during a long build.
from research.core import progress
# The market-features code, nicknamed `mf` so we can write `mf.MARKET_FEATURES`.
from research.market import features as mf
# The propagation (spreading-trouble) code, nicknamed `pg` for "propagation graph".
from research.propagation import graph as pg

# A label for this recipe. Written into results so that if the recipe changes, old results
# can still be identified as following the old one.
DATASET_VERSION = "dataset-v1"

#: Sessions of history a row needs before it is eligible. Every block is windowed, and a
#: row without a full window would carry a block computed from a shorter one.
# PLAIN ENGLISH: measurements like "how jumpy has this share been?" need a run-up of past
# days to be worked out at all. A row from a company's first week would have a "jumpiness"
# figure calculated from five days while everybody else's used sixty. Those two numbers are
# not comparable, and mixing them would quietly corrupt everything downstream. So we simply
# refuse to produce a row until sixty days of history exist.
FEATURE_LOOKBACK = 60

# The four lists of column names, one per block. `list(...)` takes a copy, so that editing
# one of these here can never reach back and alter the original definitions elsewhere.
# The propagation block: trouble arriving from connected companies.
PROPAGATION_BLOCK = list(pg.PROPAGATION_FEATURES)
# The market block: prices, returns, jumpiness.
MARKET_BLOCK = list(mf.MARKET_FEATURES)
# The microstructure block: the fine grain of how trading actually happened.
MICRO_BLOCK = list(mf.MICROSTRUCTURE_PROXIES)
# The largest number of market moods we allow for.
MAX_REGIMES = 6
# The regime block is built rather than imported: one column saying which mood was most
# likely, plus one probability column per possible mood.
# `["regime_p%d" % k for k in range(MAX_REGIMES)]` builds the names regime_p0, regime_p1,
# ... up to regime_p5. `range(6)` counts 0,1,2,3,4,5 -- six numbers, starting at zero as
# programmers count.
# We keep the probabilities for EVERY mood, not just the winner, because "70% calm" and
# "35% calm, and it was merely the highest" are very different situations that would
# otherwise look identical.
REGIME_BLOCK = ["regime_id"] + ["regime_p%d" % k for k in range(MAX_REGIMES)]

# The four honesty columns, one per block, recording how much of that block we really had.
COVERAGE_FLAGS = ["cov_market", "cov_micro", "cov_regime", "cov_propagation"]

#: The feature blocks the panel carries, in the order the interface reads them. Every
#: block name here is also a valid ablation arm and a valid coverage row.
# PLAIN ENGLISH: an "ablation" is an experiment where you deliberately remove one
# ingredient to see how much worse things get without it -- like taking the salt out of a
# recipe to find out whether it was doing anything. Because every block is listed here with
# a name, each one can be switched off by name and tested. Having one list serve as the
# definition, the display order AND the experiment menu means those three can never
# disagree with one another.
FEATURE_BLOCKS = {
    "market": MARKET_BLOCK,
    "microstructure": MICRO_BLOCK,
    "regime": REGIME_BLOCK,
    "propagation": PROPAGATION_BLOCK,
}

# Every feature name, in one flat list, in a fixed order. The order matters: models take
# their input as a plain row of numbers with no labels attached, so if the order ever
# shifted between training and use, the model would read the jumpiness figure as if it were
# the trading volume and produce confident nonsense.
ALL_FEATURES = MARKET_BLOCK + MICRO_BLOCK + REGIME_BLOCK + PROPAGATION_BLOCK


@dataclass
# The settings for one build of the table.
class BuildConfig:
    # How many days BEFORE a known trouble episode to include, so the model can see the
    # run-up. Without this we would only ever show it the fire, never the smoke.
    episode_context_before: int = 40
    # How many days AFTER to include, so we can see the aftermath.
    episode_context_after: int = 20
    # How many ordinary, nothing-happening days to include for comparison. You cannot learn
    # what "unusual" looks like without plenty of examples of "usual".
    background_rows: int = 5000
    # The starting point for anything random, so the same build can be repeated exactly.
    # It looks like a date -- 18 August 2026 -- which is a common way of picking a seed that
    # is memorable and obviously arbitrary rather than secretly tuned.
    seed: int = 20260818
    # Whether to work out the spreading-trouble block, which is the slow part.
    enable_propagation: bool = True
    # Any remarks a human wanted to attach to this build.
    notes: list[str] = field(default_factory=list)


# A small helper: make a set of boxes for a block, all empty.
def _empty(block: list[str]) -> dict:
    # `dict.fromkeys(names, value)` builds boxes with those labels, all holding the same
    # value. `np.nan` is "Not a Number" and is used here to mean "we do not know", which is
    # importantly different from zero. Zero would be a claim; NaN is an admission.
    return dict.fromkeys(block, np.nan)


# THE MAIN ACTION: put the whole table together.
def build(panel_feat: pd.DataFrame, labels: pd.DataFrame,
          regimes: pd.DataFrame | None, cfg: BuildConfig) -> pd.DataFrame:
    """Assemble the modelling frame.

    ``panel_feat`` must already carry market features (episode-injected if applicable).
    ``labels`` is the episode ground truth; ``regimes`` a per-date frame with
    ``regime_id`` and probability columns.
    """
    # PLAIN ENGLISH on the three inputs:
    #   panel_feat -- the big table of market data with the measurements already worked out.
    #   labels     -- the "right answers": which companies had real trouble, and when.
    #                 ("Ground truth" is the researcher's phrase for what actually happened,
    #                 as opposed to what a model guessed.)
    #   regimes    -- what mood the market was in on each date.

    # Start the random-number generator from our fixed seed. Same seed, same "random"
    # choices, every single time -- which is what makes the build repeatable.
    rng = np.random.default_rng(cfg.seed)
    # Sort by company, then by date within each company, so that "the row before this one"
    # reliably means "the previous trading day for this same company".
    # `.reset_index(drop=True)` renumbers the rows 0,1,2... and throws the old numbering
    # away, so that counting positions later is straightforward.
    panel_feat = panel_feat.sort_values(["symbol", "date"]).reset_index(drop=True)

    # A set of the (company, date) pairs we want rows for. A set rather than a list because
    # the two selection passes below can easily pick the same day twice, and a set silently
    # keeps just one copy.
    wanted: set[tuple[str, pd.Timestamp]] = set()
    # PASS ONE: the days around known trouble.
    # `if labels is not None and not labels.empty` -- only if we actually have right answers.
    if labels is not None and not labels.empty:
        # Split the big table into one small table per company, each sorted by date, so we
        # can look each company up instantly instead of searching the whole table each time.
        per_sym = {s: g.sort_values("date").reset_index(drop=True)
                   for s, g in panel_feat.groupby("symbol")}
        # Walk through each distinct episode of trouble. The underscore in `_episode_id`
        # is the usual signal for "we have to name this to unpack it, but we do not use it".
        for (sym, _episode_id), g in labels.groupby(["symbol", "episode_id"]):
            # Find that company's history. `.get` hands back None rather than crashing if
            # the company is not in the market data at all.
            sdf = per_sym.get(sym)
            if sdf is None:
                continue
            dates = sdf["date"]
            # Find where the episode starts in this company's list of dates, then step back
            # 40 days to catch the run-up.
            lo = dates.searchsorted(g["date"].min()) - cfg.episode_context_before
            # And where it ends, then step forward 20 days to catch the aftermath.
            hi = dates.searchsorted(g["date"].max()) + cfg.episode_context_after
            # Take every date in that window. `max(0, lo)` stops us running off the start of
            # the data and `min(len(dates), hi)` off the end -- both perfectly possible when
            # an episode sits near the beginning or end of the record.
            for d in dates.iloc[max(0, lo):min(len(dates), hi)]:
                wanted.add((sym, pd.Timestamp(d)))

    # Background rows drawn from the same symbols and calendar, so the negative class is
    # not distinguishable by symbol identity or by date.
    # PLAIN ENGLISH: this comment describes a subtle and very serious trap. Suppose all our
    # trouble examples came from 2018 and all our calm examples from 2021. A model could
    # then score brilliantly by learning nothing at all about trouble -- it would simply
    # learn "2018 means trouble". Worse, it would look like a triumph. By drawing the calm
    # examples from the SAME companies and the SAME dates, we make that shortcut unavailable,
    # so the only way to do well is to genuinely learn what trouble looks like.
    # ("Negative class" is the machine-learning term for the boring examples -- the ones
    # where the thing you are hunting for did not happen.)
    # Only consider rows where the jumpiness measure exists, as a rough test that the row
    # has enough history behind it to be usable.
    pool = panel_feat[panel_feat["vol_63d"].notna()]
    # Only if there is anything to draw from and background rows were actually asked for.
    if len(pool) and cfg.background_rows:
        # Pick rows at random. `min(...)` asks for no more than exist, so a small dataset
        # does not cause a crash. `replace=False` means "never pick the same row twice".
        take = rng.choice(len(pool), size=min(cfg.background_rows, len(pool)),
                          replace=False)
        # Add each chosen (company, date) pair to the wanted set.
        for r in pool.iloc[take][["symbol", "date"]].itertuples(index=False):
            wanted.add((r.symbol, pd.Timestamp(r.date)))

    # Build a fast lookup from (company, date) straight to that day's right answer. Without
    # this, finding the answer for each row would mean searching the whole labels table
    # every time -- painfully slow when there are thousands of rows.
    label_map = {}
    if labels is not None and not labels.empty:
        for r in labels.itertuples(index=False):
            label_map[(r.symbol, pd.Timestamp(r.date))] = r

    # The same trick for market moods, which are per-date and shared by every company, so
    # the date alone is enough of a label.
    regime_map = {}
    if regimes is not None and not regimes.empty:
        for r in regimes.itertuples(index=False):
            regime_map[pd.Timestamp(r.date)] = r

    # Regroup the wanted pairs by company, so we can handle one company at a time.
    by_symbol: dict[str, list[pd.Timestamp]] = {}
    for s_, d_ in wanted:
        # `.setdefault(key, [])` means "give me the list for this company, creating an empty
        # one first if this is the first time I have asked". It saves an explicit check.
        by_symbol.setdefault(s_, []).append(d_)

    # Somewhere to collect the finished rows.
    rows = []
    # Start the counter that will pipe up every 200 rows, so a long build shows signs of life.
    ticker = progress.Ticker("assembling rows", len(wanted), every=200)
    # Go through the market data one company at a time. `sort=False` skips re-sorting the
    # groups, which we do not need and which costs time on a big table.
    for sym, sdf in panel_feat.groupby("symbol", sort=False):
        # Renumber this company's rows from 0, so positions are simple to reason about.
        sdf = sdf.reset_index(drop=True)
        # Build a lookup from a date to its row position within this company's history.
        idx_of = {pd.Timestamp(d): i for i, d in enumerate(sdf["date"])}
        # Go through the wanted dates for this company, in time order. `by_symbol.get(sym, ())`
        # hands back an empty collection if this company had none wanted, rather than crashing.
        for date in sorted(by_symbol.get(sym, ())):
            # Count this row for the progress display.
            ticker.tick()
            # Where does this date sit in the company's history?
            i = idx_of.get(date)
            # Two reasons to skip. `i is None` means this company has no data for that date
            # at all. `i < FEATURE_LOOKBACK` means it is within the first sixty days, so the
            # measurements would be computed from a short window -- the rule from the top of
            # the file.
            if i is None or i < FEATURE_LOOKBACK:
                continue
            # Start building this row.
            row = {"symbol": sym, "date": date,
                   # When the decision is being made.
                   "decision_time": sdf.at[i, "event_time"],
                   # What we were allowed to know by then. Copied from the source row rather
                   # than recalculated, so the point-in-time stamp travels with the data
                   # instead of being derived again and possibly differently.
                   "knowledge_cutoff": sdf.at[i, "knowledge_time"]}

            # Copy across every market and microstructure measurement.
            for c in MARKET_BLOCK + MICRO_BLOCK:
                # If the column exists take its value; otherwise record "we do not know".
                # Being tolerant here matters because different data sources supply
                # different columns, and a missing column should weaken the row, not kill it.
                row[c] = sdf.at[i, c] if c in sdf.columns else np.nan
            # Now the honesty figure for the market block: what fraction of its measurements
            # are real numbers? `np.isfinite` is True for a proper number and False for NaN
            # or infinity, and `np.mean` of a list of True/False gives the fraction that are
            # True -- so 1.0 means everything present, 0.5 means half missing.
            row["cov_market"] = float(np.mean(
                [np.isfinite(row[c]) for c in MARKET_BLOCK]))
            # The same honesty figure for the microstructure block.
            row["cov_micro"] = float(np.mean(
                [np.isfinite(row[c]) for c in MICRO_BLOCK]))

            # Do we know what mood the market was in on this date?
            rg = regime_map.get(date)
            if rg is not None:
                # Which mood was judged most likely.
                row["regime_id"] = float(rg.regime_id)
                # And the probability of each possible mood.
                for k in range(MAX_REGIMES):
                    # Ask politely: if this run found only four moods, the fifth and sixth
                    # columns simply come back as "unknown" rather than crashing.
                    row["regime_p%d" % k] = float(getattr(rg, "regime_p%d" % k, np.nan))
                # Full coverage: we had the mood information.
                row["cov_regime"] = 1.0
            else:
                # No mood known. Fill the whole block with "unknown"...
                row.update(_empty(REGIME_BLOCK))
                # ...and record coverage of zero. Note what is NOT done here: we do not put
                # in a default mood, or the most common one, or zero. Any of those would be
                # inventing evidence. Saying "unknown, coverage 0" is the honest report, and
                # it lets the model downstream lower its confidence accordingly.
                row["cov_regime"] = 0.0

            # Now the right answer for this row, if there is one.
            lab = label_map.get((sym, date))
            # 1 if this day was part of a trouble episode, 0 if not.
            row["is_episode"] = 1 if lab is not None else 0
            # Which stage of trouble. On a calm day, "NORMAL".
            row["state"] = lab.state if lab is not None else "NORMAL"
            # Which phase of the episode. On a calm day, "none".
            row["phase"] = lab.phase if lab is not None else "none"
            # How severe. On a calm day, zero -- and here zero is genuinely correct, not a
            # stand-in for missing, because a day with no episode really did have no
            # intensity.
            row["intensity"] = float(lab.intensity) if lab is not None else 0.0
            # Which episode this belongs to; empty text on a calm day.
            row["episode_id"] = lab.episode_id if lab is not None else ""
            # When the episode began and ended. `pd.NaT` is "Not a Time" -- the date version
            # of "we do not know", used because a calm day has no episode boundaries at all.
            row["t_entry"] = lab.t_entry if lab is not None else pd.NaT
            row["t_exit"] = lab.t_exit if lab is not None else pd.NaT
            # Add the finished row to the pile.
            rows.append(row)

    # Turn all the rows into one proper table.
    df = pd.DataFrame(rows)
    # Sort by date, then company. A fixed order makes two runs directly comparable, instead
    # of differing merely because rows came out shuffled.
    df = df.sort_values(["date", "symbol"]).reset_index(drop=True)

    # Add the spreading-trouble block, if it was asked for and there is anything to add to.
    if cfg.enable_propagation and len(df):
        df = attach_propagation(df, panel_feat)
    else:
        # Otherwise fill that block with "unknown" and record zero coverage -- so the table
        # always has exactly the same columns whether or not this step ran. Everything
        # downstream can then rely on the shape without having to check.
        for c in PROPAGATION_BLOCK:
            df[c] = np.nan
        df["cov_propagation"] = 0.0
    return df


# Work out the spreading-trouble measurements and join them onto the table.
def attach_propagation(df: pd.DataFrame, panel_feat: pd.DataFrame) -> pd.DataFrame:
    """Merge the neighbour-stress block onto an assembled frame.

    Kept as a separate stage rather than folded into the row loop for two reasons: the
    correlation graph is shared by every instrument on a date, so building it per row
    would rebuild the same matrix a hundred times; and row assembly is the expensive part
    of the build, so a failure here must not discard it. The build script checkpoints the
    assembled frame before calling this.
    """
    # PLAIN ENGLISH on the two reasons:
    #   1. SPEED. Working out which companies move together is one big calculation covering
    #      everybody on a given day. Doing it inside the row loop would redo that identical
    #      calculation once per company -- a hundred times the work for the same answer.
    #   2. SAFETY. Assembling the rows takes a long time. If this step crashed while tangled
    #      up in that loop, all that work would be lost. Keeping it separate means the
    #      expensive part is finished and saved before the risky part begins.
    # ("Checkpoints" means the build saves the finished rows to disk first, so a crash here
    # costs minutes rather than hours.)

    # Work out the neighbour-stress measurements for every date in our table.
    with_prop = pg.build_stress_features(panel_feat, df["date"].unique())
    # Drop any placeholder propagation columns first. Merging onto columns of the same
    # name silently produces `_x`/`_y` suffixes, which leaves the real block invisible to
    # everything downstream -- the failure mode this function shipped with.
    # PLAIN ENGLISH: this records a real bug that got shipped. When you join two tables that
    # both have a column called "prop_stress", pandas does not complain -- it quietly renames
    # them "prop_stress_x" and "prop_stress_y". Nothing crashes. But every later piece of
    # code is looking for "prop_stress", finds nothing, and treats the whole block as
    # missing. A silent, invisible failure, which is the very worst kind. Removing the
    # placeholders first means there is nothing to collide with.
    base = df.drop(columns=[c for c in PROPAGATION_BLOCK if c in df.columns],
                   # `errors="ignore"` means "do not complain about columns that were not
                   # there anyway".
                   errors="ignore")
    # Remove the old coverage column too, for the same collision reason.
    if "cov_propagation" in base.columns:
        base = base.drop(columns=["cov_propagation"])
    # Join the two tables, matching on company and date.
    # `how="left"` means "keep every row of my table, and add the new information where it
    # exists". So a company with no neighbour data keeps its row, with blanks in the new
    # columns -- rather than vanishing, which is what a different join would have done.
    out = base.merge(with_prop, on=["symbol", "date"], how="left")
    # Belt and braces: check for those suffixed columns anyway. We believe we removed the
    # cause above, but this bug was invisible once before, so it gets a tripwire as well as
    # a fix.
    suffixed = [c for c in out.columns if c.endswith(("_x", "_y"))
                # `c[:-2]` chops the last two characters off, so "prop_stress_x" becomes
                # "prop_stress", and we then check whether that is one of our block's names.
                and c[:-2] in PROPAGATION_BLOCK]
    if suffixed:
        # Stop loudly. The message names the offending columns and, crucially, says what the
        # CONSEQUENCE would have been -- so whoever reads it understands why this is fatal
        # rather than cosmetic.
        raise RuntimeError(
            "propagation merge produced suffixed columns %s: the block would be "
            "silently empty" % suffixed)
    # Make sure every expected column exists, adding "unknown" ones where the join produced
    # nothing. Again this guarantees a consistent shape for everything downstream.
    for c in PROPAGATION_BLOCK:
        if c not in out.columns:
            out[c] = np.nan
    # The honesty figure for this block: did we actually find any neighbours for this row?
    # `.notna()` gives True/False, and `.astype(float)` turns those into 1.0 and 0.0 so the
    # column matches the other three coverage columns in type as well as in meaning.
    out["cov_propagation"] = out["prop_n_neighbours"].notna().astype(float)
    return out
