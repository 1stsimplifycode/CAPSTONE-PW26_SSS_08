"""Integrity risk gate and capital-consequence measurement (spec sections 33, 34).

**This is not investment advice and produces none.** The exposure policy below is a
*research instrument*: a fixed, pre-declared rule whose only purpose is to measure whether
integrity-risk information, if it had been used to cap exposure, would have changed tail
outcomes on the evaluation sample. It emits no instruction to any person, no target
price, no allocation for anyone's capital, and nothing in this module is surfaced to a
product user. See ``docs/NON_ADVISORY.md``.

The gate satisfies the monotonicity requirement of section 33:

.. math::

    w_{i,t} \\le c(I_{i,t}), \\qquad I \\uparrow \\;\\Rightarrow\\; c(I) \\downarrow

with :math:`c` non-increasing in integrity risk, which
``tests/property/test_invariants.py`` verifies over a dense grid.

Control and treatment differ in exactly one thing -- whether ``c`` is applied. Same
universe, same rebalance dates, same base weights, same cost model. Any difference in
outcome is therefore attributable to the gate, which is the entire point of the design.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

GATE_VERSION = "gate-v1"


@dataclass(frozen=True)
class GatePolicy:
    """Non-increasing cap on exposure as a function of integrity risk."""
    full_allowance_below: float = 0.30
    zero_allowance_above: float = 0.80
    floor: float = 0.0
    #: Widen the effective risk by this multiple of the uncertainty, so an uncertain
    #: high reading is treated at least as cautiously as a confident one.
    uncertainty_penalty: float = 0.5

    def cap(self, risk: np.ndarray, uncertainty: np.ndarray | None = None
            ) -> np.ndarray:
        r = np.asarray(risk, dtype=float)
        if uncertainty is not None:
            r = np.clip(r + self.uncertainty_penalty * np.asarray(uncertainty, float)
                        * r, 0.0, 1.0)
        lo, hi = self.full_allowance_below, self.zero_allowance_above
        c = np.where(r <= lo, 1.0,
                     np.where(r >= hi, self.floor,
                              1.0 - (1.0 - self.floor) * (r - lo) / max(1e-9, hi - lo)))
        return np.clip(c, self.floor, 1.0)


@dataclass(frozen=True)
class CostModel:
    """Round-trip cost applied to turnover. Indian large-cap cash equity, deliberately
    conservative: brokerage + exchange + STT + impact."""
    bps_per_unit_turnover: float = 25.0

    def apply(self, turnover: np.ndarray) -> np.ndarray:
        return np.asarray(turnover, float) * self.bps_per_unit_turnover / 1e4


def equal_weight_base(scored: pd.DataFrame) -> pd.DataFrame:
    """The pre-declared base policy: equal weight across the universe each date.

    Chosen because it embeds no view whatsoever. A base policy with its own alpha would
    confound the gate's effect with the alpha's.
    """
    out = scored.copy()
    n = out.groupby("date")["symbol"].transform("nunique")
    out["w_base"] = 1.0 / n
    return out


def apply_gate(scored: pd.DataFrame, policy: GatePolicy = GatePolicy(),
               risk_col: str = "integrity_risk",
               unc_col: str = "uncertainty") -> pd.DataFrame:
    out = equal_weight_base(scored)
    unc = out[unc_col].to_numpy(float) if unc_col in out.columns else None
    out["cap"] = policy.cap(out[risk_col].to_numpy(float), unc)
    out["w_gated"] = out["w_base"] * out["cap"]
    # Released capital is not redeployed into other names: doing so would turn the gate
    # into an allocation strategy and confound the measurement. It sits uninvested.
    return out


def backtest(scored: pd.DataFrame, weight_col: str, forward_return_col: str,
             cost: CostModel = CostModel()) -> pd.DataFrame:
    """Daily portfolio series for one arm. Returns per-date pnl, turnover and costs."""
    df = scored.sort_values(["date", "symbol"]).copy()
    df["_contrib"] = df[weight_col] * df[forward_return_col].fillna(0.0)
    per_date = df.groupby("date").agg(gross=("_contrib", "sum"))

    piv = df.pivot_table(index="date", columns="symbol", values=weight_col,
                         fill_value=0.0)
    turnover = piv.diff().abs().sum(axis=1)
    turnover.iloc[0] = piv.iloc[0].abs().sum()
    per_date["turnover"] = turnover
    per_date["cost"] = cost.apply(turnover.to_numpy())
    per_date["net"] = per_date["gross"] - per_date["cost"]
    per_date["equity"] = (1.0 + per_date["net"]).cumprod()
    return per_date.reset_index()


def tail_metrics(net: np.ndarray, alpha: float = 0.05) -> dict:
    """CVaR, VaR, max drawdown and the usual summary statistics."""
    r = np.asarray(net, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return dict.fromkeys(
            ("mean", "vol_annual", "var", "cvar", "max_drawdown", "worst_day",
             "downside_vol", "n"), np.nan)
    var = float(np.percentile(r, alpha * 100))
    tail = r[r <= var]
    equity = np.cumprod(1.0 + r)
    dd = equity / np.maximum.accumulate(equity) - 1.0
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "total_return": float(equity[-1] - 1.0),
        "vol_annual": float(r.std(ddof=1) * np.sqrt(252)),
        "downside_vol": float(r[r < 0].std(ddof=1) * np.sqrt(252))
        if (r < 0).sum() > 2 else np.nan,
        "var": var,
        "cvar": float(tail.mean()) if len(tail) else np.nan,
        "max_drawdown": float(dd.min()),
        "worst_day": float(r.min()),
    }


def capital_consequence(scored: pd.DataFrame, forward_return_col: str,
                        policy: GatePolicy = GatePolicy(),
                        cost: CostModel = CostModel()) -> dict:
    """Run control and treatment and report the difference.

    ``control``   the base policy, ungated
    ``treatment`` the identical base policy with the integrity gate applied
    """
    gated = apply_gate(scored, policy)
    ctrl = backtest(gated, "w_base", forward_return_col, cost)
    trt = backtest(gated, "w_gated", forward_return_col, cost)
    m_ctrl = tail_metrics(ctrl["net"].to_numpy())
    m_trt = tail_metrics(trt["net"].to_numpy())
    delta = {k: (m_trt[k] - m_ctrl[k]) if np.isfinite(m_ctrl.get(k, np.nan))
             and np.isfinite(m_trt.get(k, np.nan)) else np.nan
             for k in m_ctrl if k != "n"}
    # Opportunity cost: return given up by holding capital back.
    opp = float(m_ctrl["total_return"] - m_trt["total_return"])
    return {
        "control": m_ctrl, "treatment": m_trt, "delta": delta,
        "opportunity_cost_total_return": opp,
        "mean_cap": float(gated["cap"].mean()),
        "mean_gated_exposure": float(gated["w_gated"].sum()
                                     / max(1, gated["date"].nunique())),
        "control_series": ctrl, "treatment_series": trt,
        "policy": {"full_allowance_below": policy.full_allowance_below,
                   "zero_allowance_above": policy.zero_allowance_above,
                   "floor": policy.floor,
                   "uncertainty_penalty": policy.uncertainty_penalty,
                   "cost_bps": cost.bps_per_unit_turnover},
        "disclaimer": ("hypothetical research exposure policy applied to historical "
                       "data; not advice, not a strategy, and not an achievable return"),
    }
