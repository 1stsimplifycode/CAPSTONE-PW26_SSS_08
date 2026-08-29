"""Temporal integrity-risk state machine (spec sections 6, 8).

Turns a risk score series into a state trajectory and a risk window
:math:`W_e = [t_{entry}, t_{exit}]`.

Three design decisions, all of which change the numbers and are therefore stated:

**Hysteresis.** Entry needs the score above ``enter_threshold`` for ``enter_persistence``
consecutive sessions; exit needs it below ``exit_threshold`` for ``exit_persistence``.
Separate thresholds with ``exit < enter`` prevent the chattering that a single threshold
produces on a noisy score, and the persistence requirement is what makes ``t_entry`` an
*evidence-supported emergence point* rather than the first noisy crossing.

**Escalation is measured on the trend, not the level.** ESCALATING requires the score to
be rising; PEAK is the local maximum of the episode; RESOLVING requires a sustained fall.
A model that simply sits at a high level therefore reports ACTIVE, never PEAK -- which is
the honest reading.

**Unresolved is a state.** An episode whose score never falls back below the exit
threshold before the series ends is reported ``t_exit = None`` and censored, not silently
closed at the last observation. Premature and delayed resolution are then measurable
(spec section 8).

Thresholds are *detector* parameters. They are selected on the training split only and
frozen before the holdout, which leakage test L6 verifies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research.core.contracts import RiskState

STATE_VERSION = "state-machine-v1"


@dataclass(frozen=True)
class StateConfig:
    enter_threshold: float = 0.55
    exit_threshold: float = 0.40
    early_warning_threshold: float = 0.45
    enter_persistence: int = 2
    exit_persistence: int = 3
    escalation_window: int = 3
    #: Minimum rise over ``escalation_window`` sessions to call ESCALATING.
    escalation_slope: float = 0.02
    peak_margin: float = 0.02


@dataclass
class RiskWindow:
    symbol: str
    t_entry: pd.Timestamp
    t_exit: pd.Timestamp | None
    t_peak: pd.Timestamp
    peak_score: float
    censored: bool
    n_sessions: int
    states: list[str] = field(default_factory=list)

    def duration(self) -> int | None:
        return None if self.t_exit is None else self.n_sessions


def label_states(dates: pd.Series, score: np.ndarray,
                 cfg: StateConfig = StateConfig()) -> list[str]:
    """Assign one :class:`RiskState` per session."""
    n = len(score)
    states = [RiskState.NORMAL.value] * n
    if n == 0:
        return states

    slope = np.full(n, 0.0)
    w = cfg.escalation_window
    if n > w:
        slope[w:] = score[w:] - score[:-w]

    inside = False
    run_hi = run_lo = 0
    entry_i = None
    for i in range(n):
        s = score[i]
        if not inside:
            run_hi = run_hi + 1 if s >= cfg.enter_threshold else 0
            if run_hi >= cfg.enter_persistence:
                inside = True
                entry_i = i - cfg.enter_persistence + 1
                run_lo = 0
                for j in range(entry_i, i + 1):
                    states[j] = RiskState.EMERGING.value
            elif s >= cfg.early_warning_threshold:
                states[i] = RiskState.EARLY_WARNING.value
        else:
            run_lo = run_lo + 1 if s <= cfg.exit_threshold else 0
            if run_lo >= cfg.exit_persistence:
                inside = False
                for j in range(i - cfg.exit_persistence + 1, i):
                    states[j] = RiskState.RESOLVING.value
                states[i] = RiskState.RESOLVED.value
                entry_i = None
                run_hi = 0
                continue
            if slope[i] >= cfg.escalation_slope:
                states[i] = RiskState.ESCALATING.value
            elif slope[i] <= -cfg.escalation_slope:
                states[i] = RiskState.RESOLVING.value
            else:
                states[i] = RiskState.ACTIVE.value

    # PEAK is assigned last, per contiguous elevated run, so it is unique and truly the
    # maximum rather than every point above a threshold.
    i = 0
    while i < n:
        if states[i] in (RiskState.NORMAL.value, RiskState.RESOLVED.value):
            i += 1
            continue
        j = i
        while j + 1 < n and states[j + 1] not in (RiskState.NORMAL.value,
                                                  RiskState.RESOLVED.value):
            j += 1
        seg = score[i:j + 1]
        k = int(np.argmax(seg))
        if seg[k] >= cfg.enter_threshold + cfg.peak_margin:
            states[i + k] = RiskState.PEAK.value
        i = j + 1
    return states


def extract_windows(dates: pd.Series, score: np.ndarray, symbol: str,
                    cfg: StateConfig = StateConfig()) -> list[RiskWindow]:
    states = label_states(dates, score, cfg)
    dates = pd.Series(pd.to_datetime(pd.Series(dates).to_numpy())).reset_index(drop=True)
    out: list[RiskWindow] = []
    i = 0
    n = len(states)
    while i < n:
        if states[i] in (RiskState.NORMAL.value, RiskState.RESOLVED.value,
                         RiskState.EARLY_WARNING.value):
            i += 1
            continue
        j = i
        while j + 1 < n and states[j + 1] not in (RiskState.NORMAL.value,
                                                  RiskState.RESOLVED.value):
            j += 1
        seg = score[i:j + 1]
        k = int(np.argmax(seg))
        # Censored when the run reaches the end of the series without a RESOLVED marker.
        censored = (j + 1 >= n) or (states[j + 1] != RiskState.RESOLVED.value)
        out.append(RiskWindow(
            symbol=symbol, t_entry=dates.iloc[i],
            t_exit=None if censored else dates.iloc[min(j + 1, n - 1)],
            t_peak=dates.iloc[i + k], peak_score=float(seg[k]), censored=censored,
            n_sessions=j - i + 1, states=states[i:j + 1]))
        i = j + 1
    return out


def apply_to_frame(df: pd.DataFrame, score_col: str = "integrity_risk",
                   cfg: StateConfig = StateConfig()) -> pd.DataFrame:
    """Add ``risk_state`` per row, computed per symbol in date order."""
    out = []
    for _sym, g in df.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        g = g.copy()
        g["risk_state"] = label_states(g["date"], g[score_col].to_numpy(float), cfg)
        out.append(g)
    return pd.concat(out).sort_index() if out else df.assign(risk_state=[])


def windows_from_frame(df: pd.DataFrame, score_col: str = "integrity_risk",
                       cfg: StateConfig = StateConfig()) -> list[RiskWindow]:
    wins: list[RiskWindow] = []
    for sym, g in df.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        wins.extend(extract_windows(g["date"], g[score_col].to_numpy(float), sym, cfg))
    return wins
