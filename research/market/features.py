"""Market-data features (spec section 28) and microstructure proxies (section 29).

Every feature at date *t* is a function of bars up to and including *t*. That is legal
because the decision time is defined to be after the bhavcopy for *t* is published; see
``research/data/nse_bhavcopy.py``. No feature reads a future bar, and this is enforced by
leakage test L2, which shifts the panel forward and asserts the features move with it.

Features that cannot be computed from the daily bhavcopy are absent rather than
approximated by something unrelated. The microstructure block is explicitly labelled as
*proxies* -- NSE does not publish historical order-book depth openly, so order-flow
imbalance, VPIN and depth are ``NOT MEASURED`` (limitation L-02).

PLAIN ENGLISH -- what this whole file is about:

This file turns raw prices into MEASUREMENTS -- the numbers a model can actually reason
about.

The raw data is dull: on Tuesday the share opened at 100, reached 104, dropped to 99 and
closed at 102, with 50,000 shares traded across 300 separate trades. On its own that tells
you almost nothing. What you actually want to know is things like:
  * Is this share jumpier than usual lately?
  * Is far more trading happening than normal?
  * Is it drifting downwards from its recent high?
  * Are the individual trades unusually large -- which hints at big players moving?

Each of those is a "feature": one measured number computed from the raw data.

THE POINT-IN-TIME RULE, again. Every measurement for Tuesday uses Tuesday and earlier.
Never Wednesday. And this is not merely promised -- test L2 checks it by shoving the whole
dataset forward in time and confirming every measurement moves with it. If any measurement
were secretly peeking ahead, it would fail to move correctly and the test would catch it.

AND THE MOST IMPORTANT IDEA IN THIS FILE -- SAYING "WE DO NOT KNOW".

There are famous, powerful measurements in this field, with names like VPIN and order-flow
imbalance. They need to know about every order anybody ever placed, including the ones
that were cancelled before trading. The Indian exchange does not publish that openly, so
we simply cannot compute them.

There are two ways to handle that:
  * THE BAD WAY: compute something vaguely similar, give it the famous name, and hope
    nobody looks too closely. Your report then contains a well-known measurement that is
    not really that measurement.
  * THE WAY THIS FILE CHOOSES: create the column, fill it entirely with "unknown", and
    write down the exact reason we could not compute it. The gap is visible, labelled and
    explained, right in the output.

The second way makes the project look less impressive and is completely correct. It is
also why the ones we CAN compute are carefully called "proxies" -- stand-ins -- rather
than being given the famous names they do not deserve.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The official return convention, nicknamed `R`.
from research.market import returns as R

# A label for this version of the measurements.
FEATURE_VERSION = "market-v1"

#: Windows used throughout. Kept in one place so ablations can reference them.
# Three time horizons, in trading days: about a week, about a month, about three months.
# Defining them once means an experiment can say "the medium window" and mean exactly the
# same thing everywhere, instead of the number 21 being scattered through the code.
SHORT, MED, LONG = 5, 21, 63

# Every market measurement this file produces, by name.
MARKET_FEATURES = [
    # How much the price changed over one day, one week, one month.
    "ret_1d", "ret_5d", "ret_21d",
    # How jumpy the price has been over each of those windows.
    "vol_5d", "vol_21d", "vol_63d",
    # Recent jumpiness compared with longer-term jumpiness. Above 1 means "unusually
    # jumpy just now" -- a ratio, so it is comparable between a calm share and a wild one.
    "vol_ratio_5_63",
    # How wide the day's high-to-low swing was; how far the opening price jumped from
    # yesterday's close; and where in the day's range the price finally settled.
    "range_pct", "gap_pct", "close_loc",
    # How unusual today's trading activity was, in money and in shares.
    "turnover_z_21", "volume_z_21",
    # How far below its recent peak the price has fallen; whether one day's move predicts
    # the next; whether the price trends or reverts; and how disorderly the returns are.
    "drawdown_63", "ret_acf1_21", "hurst_63", "ret_entropy_21",
    # How hard it is to trade without moving the price; and how much the share moved
    # compared with the market as a whole.
    "amihud_21", "abnormal_ret_21",
]

#: The Week 1 return convention (``research.market.returns``), computed alongside the
#: legacy simple-return columns rather than replacing them. Replacing ``ret_1d`` in place
#: would silently redefine an input that trained models and frozen artifacts already
#: consume, so the canonical columns are added under their own names and the C6 test
#: asserts they carry the log definition. New work reads these.
# PLAIN ENGLISH: the correct log returns are ADDED under new names, and the older flawed
# ones are left exactly where they are. Quietly changing what an existing column means
# would corrupt every model already trained on it, without a single error message anywhere.
LOG_RETURN_FEATURES = ["logret_1d", "logret_5d", "logret_21d"]

# The fine-grained trading measurements we CAN compute from daily totals. Called "proxies"
# because they are honest stand-ins for the real thing, not the real thing.
MICROSTRUCTURE_PROXIES = [
    # The average size of a single trade; how unusual that is; how unusual the number of
    # trades is; and how unusual the money-per-trade is.
    "avg_trade_size", "trade_size_z_21", "trades_z_21", "turnover_per_trade_z_21",
]

#: Declared but not computable from open daily data. Emitted as NaN with this reason so
#: the coverage table can say so out loud instead of the field quietly not existing.
# PLAIN ENGLISH: the honest gaps. Each one is named, created as an all-blank column, and
# given the exact reason we could not fill it. A missing column is easy to overlook; a
# column full of "unknown" with a written reason attached is impossible to miss.
MICROSTRUCTURE_NOT_MEASURED = {
    # "L2 depth" means the full list of waiting buy and sell orders at every price.
    "order_book_imbalance": "NSE does not publish historical L2 depth openly",
    # "Signed" means knowing whether each trade was a buy or a sell, which the daily
    # summary does not record.
    "order_flow_imbalance": "requires signed trade-level data; not in daily bhavcopy",
    "depth": "requires L2 book snapshots",
    # VPIN tries to detect informed traders. It needs individual trades, not daily totals.
    "vpin": "requires trade-level volume buckets",
    # How often orders were placed and then withdrawn -- never published.
    "cancellation_rate": "requires order-level messages",
    "execution_aggression": "requires trade-side flags",
}


# A private helper: take every complete window of the data at once.
def _windows(x: np.ndarray, window: int) -> np.ndarray:
    """All complete trailing windows as a (n_windows, window) view."""
    from numpy.lib.stride_tricks import sliding_window_view
    # PLAIN ENGLISH: imagine sliding a little frame of 21 days along the data and writing
    # down what you see at each stop. Normally you would copy each frame out, using enormous
    # amounts of memory. A "view" does not copy anything at all -- it is a clever way of
    # looking at the SAME numbers arranged as if they were many overlapping frames. Same
    # data, no copying, and it is what makes the calculations below fast enough to run.
    return sliding_window_view(x, window)


# Work out the Hurst exponent over a rolling window.
def _rolling_hurst(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling rescaled-range Hurst exponent.

    Classical R/S estimator regressed over dyadic sub-window sizes. NaN where the window
    is incomplete or degenerate (zero variance) -- never a filled-in 0.5, which would be
    a fabricated "random walk" reading.

    Vectorised over all windows at once: the naive per-window loop cost ~1 s per symbol,
    which is 5 minutes across the research universe for one feature.
    """
    # PLAIN ENGLISH: the HURST EXPONENT is a single number describing whether a wiggly line
    # has a memory.
    #   About 0.5 -- no memory. A pure coin-flipping random walk. Yesterday tells you nothing.
    #   Above 0.5 -- it TRENDS. Up days tend to follow up days. It carries on.
    #   Below 0.5 -- it REVERTS. Up days tend to be followed by down days. It bounces back.
    # It is measured with the "rescaled range" method: look at how far the line wanders over
    # windows of different sizes. If wandering over 32 days is much more than twice the
    # wandering over 16, the line has momentum.
    # "Dyadic" simply means the window sizes double each time: 8, 16, 32, 64.
    # And the crucial honesty note: where it cannot be computed, we say "unknown". We never
    # fill in 0.5. Writing 0.5 would be inventing the specific claim "this behaves exactly
    # like a random walk", which is a strong statement to make about data we could not
    # measure at all.

    n = len(x)
    # Start with everything unknown.
    out = np.full(n, np.nan)
    # Not enough data at all? Hand back all unknowns.
    if n < window:
        return out
    # The sub-window sizes, keeping only those that fit inside our window.
    sizes = [s for s in (8, 16, 32, 64) if s <= window]
    # We need at least two sizes to compare, since the whole method is about how the
    # wandering CHANGES with size. One point cannot show a trend.
    if len(sizes) < 2:
        return out

    w = _windows(x, window)                    # (m, window)
    # How many windows we have.
    m = w.shape[0]
    # Which windows are entirely real numbers, with no gaps.
    finite = np.isfinite(w).all(axis=1)
    # Somewhere to keep the "rescaled range" for each window at each size.
    rs = np.full((m, len(sizes)), np.nan)
    for j, s in enumerate(sizes):
        # How many whole chunks of this size fit in the window.
        k = window // s
        # Chop each window into chunks. `w[:, :k * s]` trims off any leftover that does not
        # make a whole chunk, and `.reshape` arranges what remains as chunks.
        chunks = w[:, :k * s].reshape(m, k, s)
        # Each chunk's average.
        mean = chunks.mean(axis=2, keepdims=True)
        # The running total of how far each value strays from that average. This is the
        # "wandering" -- a running tally that drifts far from zero if moves persist.
        dev = np.cumsum(chunks - mean, axis=2)
        rng = dev.max(axis=2) - dev.min(axis=2)          # (m, k)
        # ...and the range of that wandering: highest point minus lowest point.
        sd = chunks.std(axis=2, ddof=1)                  # (m, k)
        # The chunk's ordinary wobble, used to put the range on a comparable scale.
        # `errstate` quietens numpy's complaints about dividing by zero; we handle that
        # case explicitly on the very next line, so the warnings would be pure noise.
        with np.errstate(divide="ignore", invalid="ignore"):
            # The "rescaled range": range divided by wobble. Where the wobble is zero (a
            # completely flat chunk) we say unknown rather than dividing by zero.
            ratio = np.where(sd > 0, rng / sd, np.nan)
        finite_ratio = np.isfinite(ratio)
        # A window in which no sub-chunk has positive variance yields NaN by design;
        # np.nanmean would emit a RuntimeWarning for each such row, so the all-NaN case
        # is handled explicitly instead of being warned about thousands of times.
        # PLAIN ENGLISH: the obvious tool here averages while ignoring unknowns -- but it
        # grumbles loudly when EVERYTHING is unknown, and on a big dataset that means
        # thousands of identical warnings burying anything genuinely important. So we do the
        # averaging by hand instead.
        counts = finite_ratio.sum(axis=1)
        sums = np.where(finite_ratio, ratio, 0.0).sum(axis=1)
        # Average where we have something, unknown where we have nothing. `np.maximum(
        # counts, 1)` prevents a divide-by-zero in the rows that are about to be discarded
        # anyway.
        rs[:, j] = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)

    # Now find the slope. The Hurst exponent is how fast the rescaled range grows as the
    # window size grows, and taking logarithms of both turns that growth into a straight
    # line whose slope is the answer.
    logs = np.log(np.asarray(sizes, dtype=float))
    y = np.log(rs)
    # Only use windows where everything is a real number.
    ok = finite & np.isfinite(y).all(axis=1)
    if ok.any():
        # Fit the straight line by hand rather than calling a general-purpose fitter,
        # because we are fitting thousands of tiny lines at once and doing it directly is
        # far faster. This is the standard least-squares slope formula.
        xc = logs - logs.mean()
        denom = float((xc ** 2).sum())
        slope = ((y[ok] - y[ok].mean(axis=1, keepdims=True)) * xc).sum(axis=1) / denom
        # Put the answers in the right places. The offset `window - 1` is because each
        # window's answer belongs to its LAST day -- the day you would have been standing on
        # when you could first have computed it.
        out[window - 1:][ok] = slope
    return out


#: Bin edges in units of the window's own standard deviation. Fixed (not quantile)
#: edges are essential: quantile edges make every window uniform by construction, so the
#: entropy would be pinned near 1.0 and carry no information. With sigma edges the
#: statistic falls when returns concentrate in the central bin (quiet, mean-reverting)
#: and rises when they spread into the tail bins (fat-tailed, disorderly).
# PLAIN ENGLISH: this comment records a subtle trap and how it was avoided. If you place
# your bin boundaries so that each bin holds the same NUMBER of days ("quantile edges"),
# then every window is perfectly evenly spread by definition, and the measurement always
# comes out the same. It would look like a working measurement while containing zero
# information. Using FIXED boundaries -- at -1.5, -0.5, +0.5 and +1.5 wobbles from the
# average -- means the spread is genuinely measured rather than manufactured.
_ENTROPY_SIGMA_EDGES = np.array([-1.5, -0.5, 0.5, 1.5])


# Measure how disorderly the returns are.
def _rolling_return_entropy(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling normalised Shannon entropy of the standardised return distribution.

    Returns are standardised by the window's own mean and standard deviation, then binned
    on :data:`_ENTROPY_SIGMA_EDGES`. Normalised by log(n_bins) so the result lies in
    [0, 1] and is comparable across symbols and volatility regimes.
    """
    # PLAIN ENGLISH: ENTROPY measures how spread out or unpredictable something is.
    #   Low entropy  -- nearly every day is much like the others. Boring, predictable.
    #   High entropy -- days are all over the place. Disorderly, hard to predict.
    # Named after Claude Shannon, who invented information theory.
    # "Normalised" means squashed onto a 0-to-1 scale by dividing by the largest possible
    # value, so a sleepy utility and a wild tech stock can be compared directly.

    n = len(x)
    out = np.full(n, np.nan)
    if n < window:
        return out
    w = _windows(x, window)                     # (m, window)
    m = w.shape[0]
    finite = np.isfinite(w).all(axis=1)
    # Each window's own average and wobble.
    mu = w.mean(axis=1, keepdims=True)
    sd = w.std(axis=1, ddof=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        # Convert each day into "how many wobbles away from this window's average". Using
        # the window's OWN average and wobble is what makes the result comparable between a
        # calm period and a wild one.
        z = (w - mu) / np.where(sd > 0, sd, np.nan)
    # Four boundaries make five bins.
    nbins = len(_ENTROPY_SIGMA_EDGES) + 1
    # Work out which bin each day falls into. `np.nan_to_num(z, nan=0.0)` temporarily parks
    # unknown values in the middle bin so the sorting does not fail; those whole rows are
    # thrown away at the end anyway.
    idx = np.searchsorted(_ENTROPY_SIGMA_EDGES, np.nan_to_num(z, nan=0.0), side="right")
    # Count how many days land in each bin, for every window at once.
    counts = np.zeros((m, nbins), dtype=float)
    # `np.add.at` adds 1 at each (window, bin) position. It is used instead of ordinary
    # addition because the same position comes up many times and ordinary addition would
    # only keep the last one instead of accumulating.
    np.add.at(counts, (np.repeat(np.arange(m), window), idx.ravel()), 1.0)
    # Turn counts into fractions.
    p = counts / window
    # Shannon's formula: minus the sum of (fraction x log of fraction).
    # The `np.where(p > 0, ...)` guards are because the logarithm of zero does not exist,
    # and an empty bin should contribute nothing at all to the total.
    ent = -np.where(p > 0, p * np.log(np.where(p > 0, p, 1.0)), 0.0).sum(axis=1)
    # Squash onto a 0-to-1 scale by dividing by the largest possible value, which occurs
    # when every bin is equally full.
    ent = ent / np.log(nbins)
    # Where the wobble was zero or unknown, the answer is meaningless. Say unknown.
    ent[(sd[:, 0] == 0) | ~np.isfinite(sd[:, 0])] = np.nan
    # Place the answers at the last day of each window.
    out[window - 1:] = np.where(finite, ent, np.nan)
    return out


# THE MAIN ACTION: work out every measurement for a whole table.
def compute_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Long panel in, long panel out with the feature columns appended.

    Expects columns: date, symbol, open, high, low, close, prev_close, volume,
    turnover, trades.
    """
    # Sort by company then date, on our own copy.
    df = panel.sort_values(["symbol", "date"]).copy()
    # Group by company. EVERYTHING below is computed per company -- otherwise one firm's
    # last day would flow into the next firm's first day and produce nonsense.
    g = df.groupby("symbol", sort=False)

    close = df["close"]
    # The simple (percentage) one-day return, kept for the older columns.
    df["ret_1d"] = g["close"].pct_change()
    # The log return using the previous ROW.
    df["logret"] = np.log(close) - np.log(g["close"].shift(1))
    lr = df.groupby("symbol", sort=False)["logret"]

    # The canonical Week 1 convention. `logret` above is positional -- it uses the
    # previous *row*, which is stale by however long the symbol went untraded. The
    # canonical column pairs each close with the bhavcopy's own prev_close, so a gap in
    # the panel cannot manufacture a return across it.
    # PLAIN ENGLISH: if a share did not trade for a fortnight, "the previous row" is from a
    # fortnight ago, and calling that a one-day return is simply false. The exchange states
    # each day's own previous price, so using that survives the gap honestly.
    if "prev_close" in df.columns:
        df["logret_1d"] = R.log_return(df["close"], df["prev_close"]).to_numpy()
    else:
        # No previous-close column available, so fall back to the positional version.
        df["logret_1d"] = df["logret"]
    clr = df.groupby("symbol", sort=False)["logret_1d"]
    # A week and a month are simply rolling sums -- the payoff of using log returns.
    df["logret_5d"] = clr.rolling(SHORT).sum().reset_index(level=0, drop=True)
    df["logret_21d"] = clr.rolling(MED).sum().reset_index(level=0, drop=True)

    # The older simple-return columns: sum the log returns and convert back to a percentage.
    df["ret_5d"] = np.expm1(lr.rolling(SHORT).sum().reset_index(level=0, drop=True))
    df["ret_21d"] = np.expm1(lr.rolling(MED).sum().reset_index(level=0, drop=True))

    # Jumpiness over three windows, annualised so the figures are comparable with the rest
    # of the world's.
    for w, name in ((SHORT, "vol_5d"), (MED, "vol_21d"), (LONG, "vol_63d")):
        df[name] = (lr.rolling(w).std().reset_index(level=0, drop=True)
                    * np.sqrt(252.0))
    # Recent jumpiness against long-run jumpiness. `.replace(0, np.nan)` avoids dividing by
    # zero: a share that never moved has no meaningful ratio, so we say unknown.
    df["vol_ratio_5_63"] = df["vol_5d"] / df["vol_63d"].replace(0, np.nan)

    # How wide the day's swing was, as a fraction of the price -- so it means the same for a
    # 20-rupee share and a 2,000-rupee one.
    df["range_pct"] = (df["high"] - df["low"]) / close.replace(0, np.nan)
    # How far the opening price jumped from yesterday's close. Big gaps mean news arrived
    # overnight, while the market was shut.
    df["gap_pct"] = (df["open"] - df["prev_close"]) / df["prev_close"].replace(0, np.nan)
    span = (df["high"] - df["low"]).replace(0, np.nan)
    # Where in the day's range the price finished. Near 1 means it closed at the top of the
    # day (buyers won); near 0 means at the bottom (sellers won).
    df["close_loc"] = (close - df["low"]) / span

    # How unusual today's trading was compared with the last month, for money and for shares.
    df["turnover_z_21"] = _zscore(df, "turnover", MED)
    df["volume_z_21"] = _zscore(df, "volume", MED)

    # The highest closing price of the last three months.
    roll_max = df.groupby("symbol", sort=False)["close"].transform(
        # `min_periods=LONG // 2` produces an answer once about half the window exists,
        # rather than leaving the first three months entirely blank.
        lambda s: s.rolling(LONG, min_periods=LONG // 2).max())
    # "Drawdown": how far below that peak we are now. 0 means at the peak; -0.2 means 20%
    # below it.
    df["drawdown_63"] = close / roll_max - 1.0

    # "Autocorrelation": does yesterday's move predict today's? Positive means moves
    # persist; negative means they bounce back; near zero means yesterday tells you nothing.
    df["ret_acf1_21"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: s.rolling(MED).corr(s.shift(1)))

    # The trend-or-revert measurement from earlier.
    df["hurst_63"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: pd.Series(_rolling_hurst(s.to_numpy(dtype=float), LONG),
                            # Keeping the original row numbering is what makes the answers
                            # line back up with the right rows.
                            index=s.index))

    # The disorderliness measurement from earlier.
    df["ret_entropy_21"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: pd.Series(_rolling_return_entropy(s.to_numpy(dtype=float), MED),
                            index=s.index))

    # The Amihud illiquidity measure: how much the price moved per unit of money traded.
    # A high value means even small trades shove the price about -- the share is hard to
    # trade. A low value means you can trade a lot without disturbing it.
    illiq = df["ret_1d"].abs() / df["turnover"].replace(0, np.nan)
    df["amihud_21"] = illiq.groupby(df["symbol"]).transform(
        lambda s: s.rolling(MED).mean())

    # Abnormal return: excess over the equal-weighted cross-section that day, scaled by
    # the symbol's own trailing volatility. A cheap, transparent event-study residual.
    # PLAIN ENGLISH: if EVERY share fell 3% today, then this one falling 3% is not news --
    # that was the whole market. What matters is how it did COMPARED with everything else.
    # So we subtract the average of all companies that day, then divide by this company's own
    # jumpiness, so "unusual" means the same thing for a calm share and a wild one.
    mkt = df.groupby("date")["logret"].transform("mean")
    df["abnormal_ret_21"] = (df["logret"] - mkt) / df["vol_21d"].replace(0, np.nan)

    # -- microstructure proxies (daily-aggregate only; see MICROSTRUCTURE_NOT_MEASURED)
    # The average size of a single trade: total shares divided by number of trades. Rising
    # average trade size hints at large players moving rather than many small ones.
    df["avg_trade_size"] = df["volume"] / df["trades"].replace(0, np.nan)
    # How unusual that is compared with the last month.
    df["trade_size_z_21"] = _zscore(df, "avg_trade_size", MED)
    # How unusual the NUMBER of trades is.
    df["trades_z_21"] = _zscore(df, "trades", MED)
    # The money per trade, which is the trade size measured in cash rather than in shares.
    tpt = df["turnover"] / df["trades"].replace(0, np.nan)
    # Parked in a temporary column because the helper below works on named columns. The
    # underscore marks it as scaffolding.
    df["_tpt"] = tpt
    df["turnover_per_trade_z_21"] = _zscore(df, "_tpt", MED)
    # Tidy the scaffolding away, so it cannot be mistaken for a real measurement later.
    df = df.drop(columns=["_tpt"])

    # THE HONEST GAPS. Create every uncomputable measurement as an all-unknown column, so
    # the absence is explicit and visible in the data rather than being silently missing.
    for col in MICROSTRUCTURE_NOT_MEASURED:
        df[col] = np.nan

    return df


# A private helper: how unusual is today's value compared with the recent past?
def _zscore(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    # PLAIN ENGLISH: a "z-score" answers "how many typical wobbles away from normal is this?"
    # A z of 0 means exactly average; 2 means twice the usual wobble above average; -3 means
    # three below. It puts everything on one comparable scale, so a huge number of shares and
    # a huge amount of money can be judged by the same standard.
    grp = df.groupby("symbol", sort=False)[col]
    # What is normal for this company lately, and how much does it usually wobble.
    mean = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).mean())
    std = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).std())
    # Today, minus normal, divided by the usual wobble. The `.replace(0, np.nan)` says that
    # a company that never varies at all has no meaningful z-score, rather than dividing by
    # zero and producing infinity.
    return (df[col] - mean) / std.replace(0, np.nan)


# Report how complete each measurement actually is.
def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-feature non-null fraction. This is what gets published instead of imputing."""
    # PLAIN ENGLISH: "imputing" means filling in missing values with a guess -- often the
    # average. It is extremely common and it quietly turns "we do not know" into "we do
    # know, and the answer is average", which is a fabricated claim. This project publishes
    # the gaps instead, and this table is where the gaps get published.
    cols = MARKET_FEATURES + MICROSTRUCTURE_PROXIES + list(MICROSTRUCTURE_NOT_MEASURED)
    rows = []
    for c in cols:
        # The column does not exist at all.
        if c not in df.columns:
            rows.append({"feature": c, "coverage": 0.0, "status": "ABSENT"})
            continue
        # What fraction of rows actually have a value. `.notna()` gives True/False, and the
        # average of those is the fraction present.
        cov = float(df[c].notna().mean())
        # Three honest statuses:
        #   NOT MEASURED -- we know why this is empty, and the reason is recorded.
        #   OK           -- present for more than half the rows.
        #   SPARSE       -- computable in principle, but mostly missing here. Different from
        #                   NOT MEASURED, and worth flagging separately so a reader knows to
        #                   treat any conclusion drawn from it with suspicion.
        status = ("NOT MEASURED" if c in MICROSTRUCTURE_NOT_MEASURED
                  else "OK" if cov > 0.5 else "SPARSE")
        rows.append({"feature": c, "coverage": cov, "status": status})
    return pd.DataFrame(rows)
