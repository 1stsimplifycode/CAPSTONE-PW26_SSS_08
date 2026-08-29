"""Market panel assembly.

Produces one row per (instrument, decision_time) with every feature block attached, plus
the coverage flags that the uncertainty-aware model needs. This is the only place where
the blocks meet; everything upstream computes a single block and everything downstream
consumes this frame.

Point-in-time discipline, in one sentence: every block for row *t* is computed from a
strictly backward-looking window ending at *t*, and the knowledge cutoff attached to the
row is the bhavcopy publication instant for *t*.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research.core import progress
from research.market import features as mf
from research.propagation import graph as pg

DATASET_VERSION = "dataset-v1"

#: Sessions of history a row needs before it is eligible. Every block is windowed, and a
#: row without a full window would carry a block computed from a shorter one.
FEATURE_LOOKBACK = 60

PROPAGATION_BLOCK = list(pg.PROPAGATION_FEATURES)
MARKET_BLOCK = list(mf.MARKET_FEATURES)
MICRO_BLOCK = list(mf.MICROSTRUCTURE_PROXIES)
MAX_REGIMES = 6
REGIME_BLOCK = ["regime_id"] + ["regime_p%d" % k for k in range(MAX_REGIMES)]

COVERAGE_FLAGS = ["cov_market", "cov_micro", "cov_regime", "cov_propagation"]

#: The feature blocks the panel carries, in the order the interface reads them. Every
#: block name here is also a valid ablation arm and a valid coverage row.
FEATURE_BLOCKS = {
    "market": MARKET_BLOCK,
    "microstructure": MICRO_BLOCK,
    "regime": REGIME_BLOCK,
    "propagation": PROPAGATION_BLOCK,
}

ALL_FEATURES = MARKET_BLOCK + MICRO_BLOCK + REGIME_BLOCK + PROPAGATION_BLOCK


@dataclass
class BuildConfig:
    episode_context_before: int = 40
    episode_context_after: int = 20
    background_rows: int = 5000
    seed: int = 20260818
    enable_propagation: bool = True
    notes: list[str] = field(default_factory=list)


def _empty(block: list[str]) -> dict:
    return dict.fromkeys(block, np.nan)


def build(panel_feat: pd.DataFrame, labels: pd.DataFrame,
          regimes: pd.DataFrame | None, cfg: BuildConfig) -> pd.DataFrame:
    """Assemble the modelling frame.

    ``panel_feat`` must already carry market features (episode-injected if applicable).
    ``labels`` is the episode ground truth; ``regimes`` a per-date frame with
    ``regime_id`` and probability columns.
    """
    rng = np.random.default_rng(cfg.seed)
    panel_feat = panel_feat.sort_values(["symbol", "date"]).reset_index(drop=True)

    wanted: set[tuple[str, pd.Timestamp]] = set()
    if labels is not None and not labels.empty:
        per_sym = {s: g.sort_values("date").reset_index(drop=True)
                   for s, g in panel_feat.groupby("symbol")}
        for (sym, _episode_id), g in labels.groupby(["symbol", "episode_id"]):
            sdf = per_sym.get(sym)
            if sdf is None:
                continue
            dates = sdf["date"]
            lo = dates.searchsorted(g["date"].min()) - cfg.episode_context_before
            hi = dates.searchsorted(g["date"].max()) + cfg.episode_context_after
            for d in dates.iloc[max(0, lo):min(len(dates), hi)]:
                wanted.add((sym, pd.Timestamp(d)))

    # Background rows drawn from the same symbols and calendar, so the negative class is
    # not distinguishable by symbol identity or by date.
    pool = panel_feat[panel_feat["vol_63d"].notna()]
    if len(pool) and cfg.background_rows:
        take = rng.choice(len(pool), size=min(cfg.background_rows, len(pool)),
                          replace=False)
        for r in pool.iloc[take][["symbol", "date"]].itertuples(index=False):
            wanted.add((r.symbol, pd.Timestamp(r.date)))

    label_map = {}
    if labels is not None and not labels.empty:
        for r in labels.itertuples(index=False):
            label_map[(r.symbol, pd.Timestamp(r.date))] = r

    regime_map = {}
    if regimes is not None and not regimes.empty:
        for r in regimes.itertuples(index=False):
            regime_map[pd.Timestamp(r.date)] = r

    by_symbol: dict[str, list[pd.Timestamp]] = {}
    for s_, d_ in wanted:
        by_symbol.setdefault(s_, []).append(d_)

    rows = []
    ticker = progress.Ticker("assembling rows", len(wanted), every=200)
    for sym, sdf in panel_feat.groupby("symbol", sort=False):
        sdf = sdf.reset_index(drop=True)
        idx_of = {pd.Timestamp(d): i for i, d in enumerate(sdf["date"])}
        for date in sorted(by_symbol.get(sym, ())):
            ticker.tick()
            i = idx_of.get(date)
            if i is None or i < FEATURE_LOOKBACK:
                continue
            row = {"symbol": sym, "date": date,
                   "decision_time": sdf.at[i, "event_time"],
                   "knowledge_cutoff": sdf.at[i, "knowledge_time"]}

            for c in MARKET_BLOCK + MICRO_BLOCK:
                row[c] = sdf.at[i, c] if c in sdf.columns else np.nan
            row["cov_market"] = float(np.mean(
                [np.isfinite(row[c]) for c in MARKET_BLOCK]))
            row["cov_micro"] = float(np.mean(
                [np.isfinite(row[c]) for c in MICRO_BLOCK]))

            rg = regime_map.get(date)
            if rg is not None:
                row["regime_id"] = float(rg.regime_id)
                for k in range(MAX_REGIMES):
                    row["regime_p%d" % k] = float(getattr(rg, "regime_p%d" % k, np.nan))
                row["cov_regime"] = 1.0
            else:
                row.update(_empty(REGIME_BLOCK))
                row["cov_regime"] = 0.0

            lab = label_map.get((sym, date))
            row["is_episode"] = 1 if lab is not None else 0
            row["state"] = lab.state if lab is not None else "NORMAL"
            row["phase"] = lab.phase if lab is not None else "none"
            row["intensity"] = float(lab.intensity) if lab is not None else 0.0
            row["episode_id"] = lab.episode_id if lab is not None else ""
            row["t_entry"] = lab.t_entry if lab is not None else pd.NaT
            row["t_exit"] = lab.t_exit if lab is not None else pd.NaT
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values(["date", "symbol"]).reset_index(drop=True)

    if cfg.enable_propagation and len(df):
        df = attach_propagation(df, panel_feat)
    else:
        for c in PROPAGATION_BLOCK:
            df[c] = np.nan
        df["cov_propagation"] = 0.0
    return df


def attach_propagation(df: pd.DataFrame, panel_feat: pd.DataFrame) -> pd.DataFrame:
    """Merge the neighbour-stress block onto an assembled frame.

    Kept as a separate stage rather than folded into the row loop for two reasons: the
    correlation graph is shared by every instrument on a date, so building it per row
    would rebuild the same matrix a hundred times; and row assembly is the expensive part
    of the build, so a failure here must not discard it. The build script checkpoints the
    assembled frame before calling this.
    """
    with_prop = pg.build_stress_features(panel_feat, df["date"].unique())
    # Drop any placeholder propagation columns first. Merging onto columns of the same
    # name silently produces `_x`/`_y` suffixes, which leaves the real block invisible to
    # everything downstream -- the failure mode this function shipped with.
    base = df.drop(columns=[c for c in PROPAGATION_BLOCK if c in df.columns],
                   errors="ignore")
    if "cov_propagation" in base.columns:
        base = base.drop(columns=["cov_propagation"])
    out = base.merge(with_prop, on=["symbol", "date"], how="left")
    suffixed = [c for c in out.columns if c.endswith(("_x", "_y"))
                and c[:-2] in PROPAGATION_BLOCK]
    if suffixed:
        raise RuntimeError(
            "propagation merge produced suffixed columns %s: the block would be "
            "silently empty" % suffixed)
    for c in PROPAGATION_BLOCK:
        if c not in out.columns:
            out[c] = np.nan
    out["cov_propagation"] = out["prop_n_neighbours"].notna().astype(float)
    return out
