"""Synthetic integrity-risk episodes injected into real market data (spec section 31).

Why this exists: no open, labelled corpus of NSE market-integrity incidents was found
(limitation L-04), and inventing incident labels for real companies would be both
fabrication and defamation. The alternative adopted here is to inject *known* episodes
into the real panel and evaluate recovery of what was injected. Every number produced
this way is a statement about the detector's behaviour on injected episodes, never a
claim about real-world manipulation.

Generator/detector separation is structural, not a promise:

* :class:`GeneratorConfig` holds every parameter used to *create* episodes. No module
  under ``research/models`` or ``research/detection/state.py`` imports it, and
  ``tests/property/test_invariants.py`` asserts that.
* Train and test episodes are drawn from disjoint seeds *and* disjoint instrument sets,
  so a detector cannot memorise which symbols carry episodes.

Injection acts on the raw panel -- prices, volumes, trade counts -- and features are
recomputed afterwards. The detector therefore sees only data, exactly as it would in
production, and cannot read an injection flag by accident.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from research.core.contracts import RiskState

_IST = timezone(timedelta(hours=5, minutes=30))

GENERATOR_VERSION = "episodes-v1"

#: Phase order and the state each phase maps to. Not every episode uses every phase.
PHASES = [
    ("early_warning", RiskState.EARLY_WARNING),
    ("emerging", RiskState.EMERGING),
    ("active", RiskState.ACTIVE),
    ("escalating", RiskState.ESCALATING),
    ("peak", RiskState.PEAK),
    ("resolving", RiskState.RESOLVING),
]


@dataclass(frozen=True)
class GeneratorConfig:
    """Parameters of the *data-generating process*. Never visible to a detector."""
    n_episodes: int = 120
    #: Mean phase lengths in trading sessions. Actual lengths are Poisson-jittered.
    phase_days: dict[str, int] = field(default_factory=lambda: {
        "early_warning": 4, "emerging": 5, "active": 6, "escalating": 4,
        "peak": 3, "resolving": 6})
    #: Peak intensity is drawn from a Beta so most episodes are subtle and a few severe.
    intensity_a: float = 2.0
    intensity_b: float = 3.0
    intensity_floor: float = 0.25
    #: Return drift injected at peak intensity, in units of the symbol's own daily vol.
    return_kappa: float = 0.55
    #: Multiplicative volume/turnover inflation at peak intensity.
    volume_kappa: float = 1.60
    #: Trade-count inflation; deliberately smaller than volume, so average trade size
    #: rises -- the microstructure proxies must have something real to detect.
    trades_kappa: float = 0.75
    #: Fraction of episodes that never resolve inside the window (censored).
    censored_fraction: float = 0.15
    seed: int = 20260818


@dataclass
class Episode:
    episode_id: str
    symbol: str
    t_entry: pd.Timestamp
    t_exit: pd.Timestamp | None          # None = censored / unresolved
    t_peak: pd.Timestamp
    peak_intensity: float
    censored: bool
    schedule: pd.DataFrame               # date, state, intensity


def _phase_schedule(rng: np.random.Generator, cfg: GeneratorConfig,
                    sessions: Sequence[pd.Timestamp], start_idx: int,
                    peak_intensity: float, censored: bool
                    ) -> tuple[pd.DataFrame, int]:
    rows = []
    i = start_idx
    # Intensity ramps to the peak phase then decays through resolving.
    ramp = {"early_warning": 0.25, "emerging": 0.45, "active": 0.70,
            "escalating": 0.88, "peak": 1.00, "resolving": 0.45}
    for name, state in PHASES:
        if censored and name == "resolving":
            break
        mean = cfg.phase_days[name]
        n = max(1, int(rng.poisson(mean)))
        for _ in range(n):
            if i >= len(sessions):
                break
            rows.append({"date": sessions[i], "state": state.value,
                         "intensity": peak_intensity * ramp[name], "phase": name})
            i += 1
        if i >= len(sessions):
            break
    return pd.DataFrame(rows), i


def generate(panel: pd.DataFrame, universe_symbols: Sequence[str],
             cfg: GeneratorConfig) -> list[Episode]:
    """Draw episode specifications. Does not touch the panel."""
    rng = np.random.default_rng(cfg.seed)
    sessions = np.sort(panel["date"].unique())
    sessions = [pd.Timestamp(s) for s in sessions]
    counts = panel.groupby("symbol")["date"].count()
    eligible = [s for s in universe_symbols if counts.get(s, 0) > 400]
    if not eligible:
        raise ValueError("no eligible symbols with sufficient history")

    episodes: list[Episode] = []
    for e in range(cfg.n_episodes):
        sym = str(rng.choice(eligible))
        sym_dates = sorted(panel.loc[panel["symbol"] == sym, "date"].unique())
        sym_dates = [pd.Timestamp(d) for d in sym_dates]
        if len(sym_dates) < 300:
            continue
        # Leave room before (feature warm-up) and after (resolution) the episode.
        lo, hi = 150, len(sym_dates) - 60
        if hi <= lo:
            continue
        start = int(rng.integers(lo, hi))
        peak_intensity = max(cfg.intensity_floor,
                             float(rng.beta(cfg.intensity_a, cfg.intensity_b)))
        censored = bool(rng.random() < cfg.censored_fraction)
        sched, end = _phase_schedule(rng, cfg, sym_dates, start, peak_intensity,
                                     censored)
        if sched.empty:
            continue
        peak_rows = sched[sched["phase"] == "peak"]
        t_peak = (peak_rows["date"].iloc[0] if len(peak_rows)
                  else sched["date"].iloc[-1])
        t_exit = None if censored else sched["date"].iloc[-1]
        episodes.append(Episode(
            episode_id="EP%04d" % e, symbol=sym,
            t_entry=sched["date"].iloc[0], t_exit=t_exit, t_peak=t_peak,
            peak_intensity=peak_intensity, censored=censored, schedule=sched))
    return episodes


def inject(panel: pd.DataFrame, episodes: Sequence[Episode],
           cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply episodes to the raw panel.

    Returns ``(modified_panel, labels)``. The modified panel differs from the original
    only in ``close``/``high``/``low``/``volume``/``turnover``/``trades`` inside episode
    windows. Prices are adjusted multiplicatively by the cumulative injected drift so
    that returns -- not levels -- carry the signal, which keeps the series continuous at
    the episode boundary.
    """
    df = panel.copy()
    rng = np.random.default_rng(cfg.seed + 1)

    # Volume and trade counts arrive as integers. Injection multiplies them by a
    # continuous factor, so widen first rather than let pandas refuse (or, worse,
    # silently truncate) the assignment.
    for col in ("close", "high", "low", "prev_close", "volume", "turnover", "trades"):
        if col in df.columns:
            df[col] = df[col].astype(float)

    # Per-symbol daily volatility, used to scale the injected drift so a 0.55-kappa
    # episode means the same thing in a quiet name and a volatile one.
    df["_lr"] = np.log(df["close"]) - np.log(df["prev_close"])
    vol = df.groupby("symbol")["_lr"].transform(
        lambda s: s.rolling(63, min_periods=20).std())
    df["_vol"] = vol.fillna(vol.median())

    key = pd.MultiIndex.from_arrays([df["symbol"], df["date"]])
    df = df.set_index(key)

    label_rows = []
    for ep in episodes:
        sched = ep.schedule
        idx = pd.MultiIndex.from_arrays([[ep.symbol] * len(sched), sched["date"]])
        present = idx.isin(df.index)
        if not present.any():
            continue
        idx = idx[present]
        sched = sched[present]
        inten = sched["intensity"].to_numpy()
        sign = -1.0 if rng.random() < 0.75 else 1.0   # most integrity events are adverse

        v = df.loc[idx, "_vol"].to_numpy()
        drift = sign * cfg.return_kappa * inten * v
        noise = rng.normal(0.0, 0.25 * cfg.return_kappa * inten * v)
        cum = np.exp(np.cumsum(drift + noise))

        for col in ("close", "high", "low"):
            df.loc[idx, col] = df.loc[idx, col].to_numpy() * cum
        vmul = 1.0 + cfg.volume_kappa * inten * np.abs(rng.normal(1.0, 0.3, len(inten)))
        tmul = 1.0 + cfg.trades_kappa * inten * np.abs(rng.normal(1.0, 0.3, len(inten)))
        df.loc[idx, "volume"] = df.loc[idx, "volume"].to_numpy() * vmul
        df.loc[idx, "turnover"] = df.loc[idx, "turnover"].to_numpy() * vmul * cum
        df.loc[idx, "trades"] = df.loc[idx, "trades"].to_numpy() * tmul

        for (_, r) in sched.iterrows():
            label_rows.append({
                "episode_id": ep.episode_id, "symbol": ep.symbol, "date": r["date"],
                "state": r["state"], "phase": r["phase"],
                "intensity": float(r["intensity"]),
                "peak_intensity": ep.peak_intensity, "censored": ep.censored,
                "t_entry": ep.t_entry, "t_exit": ep.t_exit, "t_peak": ep.t_peak,
            })

    df = df.reset_index(drop=True)
    df = df.drop(columns=["_lr", "_vol"])
    # prev_close must stay consistent with the modified closes, or the injected drift
    # would be visible as an impossible overnight jump.
    df = df.sort_values(["symbol", "date"])
    df["prev_close"] = df.groupby("symbol")["close"].shift(1).fillna(df["prev_close"])
    labels = pd.DataFrame(label_rows)
    return df.reset_index(drop=True), labels


def split_by_symbol(episodes: Sequence[Episode], test_fraction: float = 0.35,
                    seed: int = 20260818) -> tuple[list[Episode], list[Episode]]:
    """Disjoint-instrument split.

    Splitting by episode would put the same symbol in train and test, letting a model
    learn "this ticker has episodes" instead of "this pattern is an episode".
    """
    rng = np.random.default_rng(seed)
    syms = sorted({e.symbol for e in episodes})
    rng.shuffle(syms)
    n_test = max(1, int(len(syms) * test_fraction))
    test_syms = set(syms[:n_test])
    train = [e for e in episodes if e.symbol not in test_syms]
    test = [e for e in episodes if e.symbol in test_syms]
    return train, test


def with_seed(cfg: GeneratorConfig, seed: int) -> GeneratorConfig:
    return replace(cfg, seed=seed)
