"""Market-data features (spec section 28) and microstructure proxies (section 29).

Every feature at date *t* is a function of bars up to and including *t*. That is legal
because the decision time is defined to be after the bhavcopy for *t* is published; see
``research/data/nse_bhavcopy.py``. No feature reads a future bar, and this is enforced by
leakage test L2, which shifts the panel forward and asserts the features move with it.

Features that cannot be computed from the daily bhavcopy are absent rather than
approximated by something unrelated. The microstructure block is explicitly labelled as
*proxies* -- NSE does not publish historical order-book depth openly, so order-flow
imbalance, VPIN and depth are ``NOT MEASURED`` (limitation L-02).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.market import returns as R

FEATURE_VERSION = "market-v1"

#: Windows used throughout. Kept in one place so ablations can reference them.
SHORT, MED, LONG = 5, 21, 63

MARKET_FEATURES = [
    "ret_1d", "ret_5d", "ret_21d",
    "vol_5d", "vol_21d", "vol_63d",
    "vol_ratio_5_63",
    "range_pct", "gap_pct", "close_loc",
    "turnover_z_21", "volume_z_21",
    "drawdown_63", "ret_acf1_21", "hurst_63", "ret_entropy_21",
    "amihud_21", "abnormal_ret_21",
]

#: The Week 1 return convention (``research.market.returns``), computed alongside the
#: legacy simple-return columns rather than replacing them. Replacing ``ret_1d`` in place
#: would silently redefine an input that trained models and frozen artifacts already
#: consume, so the canonical columns are added under their own names and the C6 test
#: asserts they carry the log definition. New work reads these.
LOG_RETURN_FEATURES = ["logret_1d", "logret_5d", "logret_21d"]

MICROSTRUCTURE_PROXIES = [
    "avg_trade_size", "trade_size_z_21", "trades_z_21", "turnover_per_trade_z_21",
]

#: Declared but not computable from open daily data. Emitted as NaN with this reason so
#: the coverage table can say so out loud instead of the field quietly not existing.
MICROSTRUCTURE_NOT_MEASURED = {
    "order_book_imbalance": "NSE does not publish historical L2 depth openly",
    "order_flow_imbalance": "requires signed trade-level data; not in daily bhavcopy",
    "depth": "requires L2 book snapshots",
    "vpin": "requires trade-level volume buckets",
    "cancellation_rate": "requires order-level messages",
    "execution_aggression": "requires trade-side flags",
}


def _windows(x: np.ndarray, window: int) -> np.ndarray:
    """All complete trailing windows as a (n_windows, window) view."""
    from numpy.lib.stride_tricks import sliding_window_view
    return sliding_window_view(x, window)


def _rolling_hurst(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling rescaled-range Hurst exponent.

    Classical R/S estimator regressed over dyadic sub-window sizes. NaN where the window
    is incomplete or degenerate (zero variance) -- never a filled-in 0.5, which would be
    a fabricated "random walk" reading.

    Vectorised over all windows at once: the naive per-window loop cost ~1 s per symbol,
    which is 5 minutes across the research universe for one feature.
    """
    n = len(x)
    out = np.full(n, np.nan)
    if n < window:
        return out
    sizes = [s for s in (8, 16, 32, 64) if s <= window]
    if len(sizes) < 2:
        return out

    w = _windows(x, window)                    # (m, window)
    m = w.shape[0]
    finite = np.isfinite(w).all(axis=1)
    rs = np.full((m, len(sizes)), np.nan)
    for j, s in enumerate(sizes):
        k = window // s
        chunks = w[:, :k * s].reshape(m, k, s)
        mean = chunks.mean(axis=2, keepdims=True)
        dev = np.cumsum(chunks - mean, axis=2)
        rng = dev.max(axis=2) - dev.min(axis=2)          # (m, k)
        sd = chunks.std(axis=2, ddof=1)                  # (m, k)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(sd > 0, rng / sd, np.nan)
        finite_ratio = np.isfinite(ratio)
        # A window in which no sub-chunk has positive variance yields NaN by design;
        # np.nanmean would emit a RuntimeWarning for each such row, so the all-NaN case
        # is handled explicitly instead of being warned about thousands of times.
        counts = finite_ratio.sum(axis=1)
        sums = np.where(finite_ratio, ratio, 0.0).sum(axis=1)
        rs[:, j] = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)

    logs = np.log(np.asarray(sizes, dtype=float))
    y = np.log(rs)
    ok = finite & np.isfinite(y).all(axis=1)
    if ok.any():
        xc = logs - logs.mean()
        denom = float((xc ** 2).sum())
        slope = ((y[ok] - y[ok].mean(axis=1, keepdims=True)) * xc).sum(axis=1) / denom
        out[window - 1:][ok] = slope
    return out


#: Bin edges in units of the window's own standard deviation. Fixed (not quantile)
#: edges are essential: quantile edges make every window uniform by construction, so the
#: entropy would be pinned near 1.0 and carry no information. With sigma edges the
#: statistic falls when returns concentrate in the central bin (quiet, mean-reverting)
#: and rises when they spread into the tail bins (fat-tailed, disorderly).
_ENTROPY_SIGMA_EDGES = np.array([-1.5, -0.5, 0.5, 1.5])


def _rolling_return_entropy(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling normalised Shannon entropy of the standardised return distribution.

    Returns are standardised by the window's own mean and standard deviation, then binned
    on :data:`_ENTROPY_SIGMA_EDGES`. Normalised by log(n_bins) so the result lies in
    [0, 1] and is comparable across symbols and volatility regimes.
    """
    n = len(x)
    out = np.full(n, np.nan)
    if n < window:
        return out
    w = _windows(x, window)                     # (m, window)
    m = w.shape[0]
    finite = np.isfinite(w).all(axis=1)
    mu = w.mean(axis=1, keepdims=True)
    sd = w.std(axis=1, ddof=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (w - mu) / np.where(sd > 0, sd, np.nan)
    nbins = len(_ENTROPY_SIGMA_EDGES) + 1
    idx = np.searchsorted(_ENTROPY_SIGMA_EDGES, np.nan_to_num(z, nan=0.0), side="right")
    counts = np.zeros((m, nbins), dtype=float)
    np.add.at(counts, (np.repeat(np.arange(m), window), idx.ravel()), 1.0)
    p = counts / window
    ent = -np.where(p > 0, p * np.log(np.where(p > 0, p, 1.0)), 0.0).sum(axis=1)
    ent = ent / np.log(nbins)
    ent[(sd[:, 0] == 0) | ~np.isfinite(sd[:, 0])] = np.nan
    out[window - 1:] = np.where(finite, ent, np.nan)
    return out


def compute_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Long panel in, long panel out with the feature columns appended.

    Expects columns: date, symbol, open, high, low, close, prev_close, volume,
    turnover, trades.
    """
    df = panel.sort_values(["symbol", "date"]).copy()
    g = df.groupby("symbol", sort=False)

    close = df["close"]
    df["ret_1d"] = g["close"].pct_change()
    df["logret"] = np.log(close) - np.log(g["close"].shift(1))
    lr = df.groupby("symbol", sort=False)["logret"]

    # The canonical Week 1 convention. `logret` above is positional -- it uses the
    # previous *row*, which is stale by however long the symbol went untraded. The
    # canonical column pairs each close with the bhavcopy's own prev_close, so a gap in
    # the panel cannot manufacture a return across it.
    if "prev_close" in df.columns:
        df["logret_1d"] = R.log_return(df["close"], df["prev_close"]).to_numpy()
    else:
        df["logret_1d"] = df["logret"]
    clr = df.groupby("symbol", sort=False)["logret_1d"]
    df["logret_5d"] = clr.rolling(SHORT).sum().reset_index(level=0, drop=True)
    df["logret_21d"] = clr.rolling(MED).sum().reset_index(level=0, drop=True)

    df["ret_5d"] = np.expm1(lr.rolling(SHORT).sum().reset_index(level=0, drop=True))
    df["ret_21d"] = np.expm1(lr.rolling(MED).sum().reset_index(level=0, drop=True))

    for w, name in ((SHORT, "vol_5d"), (MED, "vol_21d"), (LONG, "vol_63d")):
        df[name] = (lr.rolling(w).std().reset_index(level=0, drop=True)
                    * np.sqrt(252.0))
    df["vol_ratio_5_63"] = df["vol_5d"] / df["vol_63d"].replace(0, np.nan)

    df["range_pct"] = (df["high"] - df["low"]) / close.replace(0, np.nan)
    df["gap_pct"] = (df["open"] - df["prev_close"]) / df["prev_close"].replace(0, np.nan)
    span = (df["high"] - df["low"]).replace(0, np.nan)
    df["close_loc"] = (close - df["low"]) / span

    df["turnover_z_21"] = _zscore(df, "turnover", MED)
    df["volume_z_21"] = _zscore(df, "volume", MED)

    roll_max = df.groupby("symbol", sort=False)["close"].transform(
        lambda s: s.rolling(LONG, min_periods=LONG // 2).max())
    df["drawdown_63"] = close / roll_max - 1.0

    df["ret_acf1_21"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: s.rolling(MED).corr(s.shift(1)))

    df["hurst_63"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: pd.Series(_rolling_hurst(s.to_numpy(dtype=float), LONG),
                            index=s.index))

    df["ret_entropy_21"] = df.groupby("symbol", sort=False)["logret"].transform(
        lambda s: pd.Series(_rolling_return_entropy(s.to_numpy(dtype=float), MED),
                            index=s.index))

    illiq = df["ret_1d"].abs() / df["turnover"].replace(0, np.nan)
    df["amihud_21"] = illiq.groupby(df["symbol"]).transform(
        lambda s: s.rolling(MED).mean())

    # Abnormal return: excess over the equal-weighted cross-section that day, scaled by
    # the symbol's own trailing volatility. A cheap, transparent event-study residual.
    mkt = df.groupby("date")["logret"].transform("mean")
    df["abnormal_ret_21"] = (df["logret"] - mkt) / df["vol_21d"].replace(0, np.nan)

    # -- microstructure proxies (daily-aggregate only; see MICROSTRUCTURE_NOT_MEASURED)
    df["avg_trade_size"] = df["volume"] / df["trades"].replace(0, np.nan)
    df["trade_size_z_21"] = _zscore(df, "avg_trade_size", MED)
    df["trades_z_21"] = _zscore(df, "trades", MED)
    tpt = df["turnover"] / df["trades"].replace(0, np.nan)
    df["_tpt"] = tpt
    df["turnover_per_trade_z_21"] = _zscore(df, "_tpt", MED)
    df = df.drop(columns=["_tpt"])

    for col in MICROSTRUCTURE_NOT_MEASURED:
        df[col] = np.nan

    return df


def _zscore(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    grp = df.groupby("symbol", sort=False)[col]
    mean = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).mean())
    std = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).std())
    return (df[col] - mean) / std.replace(0, np.nan)


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-feature non-null fraction. This is what gets published instead of imputing."""
    cols = MARKET_FEATURES + MICROSTRUCTURE_PROXIES + list(MICROSTRUCTURE_NOT_MEASURED)
    rows = []
    for c in cols:
        if c not in df.columns:
            rows.append({"feature": c, "coverage": 0.0, "status": "ABSENT"})
            continue
        cov = float(df[c].notna().mean())
        status = ("NOT MEASURED" if c in MICROSTRUCTURE_NOT_MEASURED
                  else "OK" if cov > 0.5 else "SPARSE")
        rows.append({"feature": c, "coverage": cov, "status": status})
    return pd.DataFrame(rows)
