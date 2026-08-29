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

PLAIN ENGLISH -- what this whole file is about:

FIRST, THE WARNING AT THE TOP, BECAUSE IT IS THE MOST IMPORTANT PART.

This file is NOT telling anybody to buy or sell anything. It never says "invest in this"
or "avoid that". Telling people what to do with their money is a regulated activity in
most countries and requires licences this project does not have -- and quite apart from
the law, this system does not actually know what anybody should do.

So what IS it for? It answers one scientific question, and only one:

    "IF somebody had used our risk scores to hold back from risky companies,
     WOULD their worst days have been less bad?"

That is a measurement about history, not a recommendation about the future. The difference
is enormous, and the file states it in the first line rather than burying it at the end.

WHAT THE "GATE" DOES: it is a tap, not a decision. As the risk score rises, the tap closes.
  Risk below 0.30 -- tap fully open. Hold the normal amount.
  Risk above 0.80 -- tap fully shut. Hold nothing.
  In between      -- the tap closes smoothly.
The maths word for "the tap never opens as risk rises" is MONOTONIC, and there is an
automatic test that checks this across thousands of values. It matters because a rule that
sometimes allowed MORE exposure at higher risk would be incoherent -- and the failure could
easily hide in a corner of the range nobody happened to look at.

THE EXPERIMENT'S DESIGN, which is the real achievement here.
Two runs, absolutely identical in every respect -- the same companies, the same days, the
same starting amounts, the same trading costs -- except for ONE thing: whether the tap is
used.
That single difference is everything. Because the two runs match in every other way, any
difference in the outcome can only have been caused by the tap. This is exactly how a
proper drug trial works: identical groups, one difference, so the difference is
attributable. Change two things at once and you learn nothing about either.

AND ONE MORE PIECE OF DISCIPLINE, further down: money held back is NOT put anywhere else.
It just sits there earning nothing. That deliberately makes the results look worse. If we
reinvested it we would be measuring "our risk score plus our reinvestment idea", and we
would never know which part did the work.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version.
GATE_VERSION = "gate-v1"


# Frozen: the rule must not change during a run, or the two arms would not be comparable.
@dataclass(frozen=True)
class GatePolicy:
    """Non-increasing cap on exposure as a function of integrity risk."""
    # Below this risk, no restriction at all.
    full_allowance_below: float = 0.30
    # Above this risk, hold nothing.
    zero_allowance_above: float = 0.80
    # The least the tap may ever be open. 0.0 means it can close completely.
    floor: float = 0.0
    #: Widen the effective risk by this multiple of the uncertainty, so an uncertain
    #: high reading is treated at least as cautiously as a confident one.
    # PLAIN ENGLISH: if we are unsure, we err towards caution. A reading of "0.6 risk, and
    # we are very unsure" gets treated as somewhat worse than 0.6, rather than the same. The
    # alternative -- treating an uncertain reading exactly like a confident one -- would mean
    # our own ignorance never made us any more careful.
    uncertainty_penalty: float = 0.5

    # Work out how open the tap should be.
    def cap(self, risk: np.ndarray, uncertainty: np.ndarray | None = None
            ) -> np.ndarray:
        r = np.asarray(risk, dtype=float)
        if uncertainty is not None:
            # Inflate the risk in proportion to how unsure we are, capped at 1.0. Note it is
            # multiplied by `r` as well, so uncertainty about a LOW risk barely matters --
            # which is right: being unsure whether something is very safe or fairly safe is
            # not a reason for alarm.
            r = np.clip(r + self.uncertainty_penalty * np.asarray(uncertainty, float)
                        * r, 0.0, 1.0)
        lo, hi = self.full_allowance_below, self.zero_allowance_above
        # Three cases, read from the inside out:
        #   risk <= 0.30 -- tap fully open (1.0)
        #   risk >= 0.80 -- tap at the floor
        #   in between   -- slide smoothly from 1.0 down to the floor. A straight line, so
        #                   there is no cliff edge where a hair's-breadth change in the score
        #                   would cause a dramatic jump in behaviour.
        c = np.where(r <= lo, 1.0,
                     np.where(r >= hi, self.floor,
                              # `max(1e-9, hi - lo)` guards against a divide by zero if
                              # somebody set the two thresholds equal.
                              1.0 - (1.0 - self.floor) * (r - lo) / max(1e-9, hi - lo)))
        # Belt and braces: force the answer inside its legal range.
        return np.clip(c, self.floor, 1.0)


@dataclass(frozen=True)
class CostModel:
    """Round-trip cost applied to turnover. Indian large-cap cash equity, deliberately
    conservative: brokerage + exchange + STT + impact."""
    # PLAIN ENGLISH: trading is not free. Every time you buy or sell there is a broker's fee,
    # an exchange fee, a government tax (STT is Securities Transaction Tax), and "impact" --
    # the fact that your own trading nudges the price against you.
    # 25 basis points is 0.25%. "Deliberately conservative" means we have assumed costs on
    # the high side. That makes our results look WORSE, which is the honest direction to err
    # in: a strategy that survives pessimistic costs is a real result, whereas one that only
    # works with optimistic costs is an artefact of the assumption.
    bps_per_unit_turnover: float = 25.0

    def apply(self, turnover: np.ndarray) -> np.ndarray:
        # `1e4` because a basis point is one ten-thousandth.
        return np.asarray(turnover, float) * self.bps_per_unit_turnover / 1e4


# The starting point both arms share.
def equal_weight_base(scored: pd.DataFrame) -> pd.DataFrame:
    """The pre-declared base policy: equal weight across the universe each date.

    Chosen because it embeds no view whatsoever. A base policy with its own alpha would
    confound the gate's effect with the alpha's.
    """
    # PLAIN ENGLISH: put the same amount into every company. Deliberately the most
    # opinion-free starting point there is. If we had started with a clever selection of our
    # own, we could never tell afterwards whether an improvement came from the risk gate or
    # from the cleverness underneath it. ("Alpha" is the finance word for a genuine edge.)
    out = scored.copy()
    # How many companies there are on each date.
    n = out.groupby("date")["symbol"].transform("nunique")
    # One divided by that: an equal share each.
    out["w_base"] = 1.0 / n
    return out


# Apply the tap.
def apply_gate(scored: pd.DataFrame, policy: GatePolicy = GatePolicy(),
               risk_col: str = "integrity_risk",
               unc_col: str = "uncertainty") -> pd.DataFrame:
    out = equal_weight_base(scored)
    # Use uncertainty if the data has it; otherwise do without rather than assuming a value.
    unc = out[unc_col].to_numpy(float) if unc_col in out.columns else None
    out["cap"] = policy.cap(out[risk_col].to_numpy(float), unc)
    # The gated amount is the base amount times how open the tap is.
    out["w_gated"] = out["w_base"] * out["cap"]
    # Released capital is not redeployed into other names: doing so would turn the gate
    # into an allocation strategy and confound the measurement. It sits uninvested.
    # PLAIN ENGLISH: the discipline from the top of the file, stated at the point where the
    # temptation would arise. Money pulled out of a risky company just sits there earning
    # nothing. That makes the results look worse -- and it means the ONE thing being measured
    # is the risk score, not the risk score plus a reinvestment idea.
    return out


# Replay one arm day by day.
def backtest(scored: pd.DataFrame, weight_col: str, forward_return_col: str,
             cost: CostModel = CostModel()) -> pd.DataFrame:
    """Daily portfolio series for one arm. Returns per-date pnl, turnover and costs."""
    df = scored.sort_values(["date", "symbol"]).copy()
    # Each company's contribution: how much was held, times how it did.
    df["_contrib"] = df[weight_col] * df[forward_return_col].fillna(0.0)
    # Added up per day, that is the day's gross result.
    per_date = df.groupby("date").agg(gross=("_contrib", "sum"))

    # Reshape so we can see how the holdings changed from one day to the next.
    piv = df.pivot_table(index="date", columns="symbol", values=weight_col,
                         fill_value=0.0)
    # "Turnover" is how much was bought and sold. `.diff().abs().sum()` measures the total
    # change across all companies -- `abs` because both buying and selling cost money.
    turnover = piv.diff().abs().sum(axis=1)
    # The first day has no previous day to compare with, so its turnover is the full cost of
    # building the initial holdings from nothing. Missing this would quietly hand both arms a
    # free first day.
    turnover.iloc[0] = piv.iloc[0].abs().sum()
    per_date["turnover"] = turnover
    per_date["cost"] = cost.apply(turnover.to_numpy())
    # The result after costs -- the only figure that means anything.
    per_date["net"] = per_date["gross"] - per_date["cost"]
    # The running total. `.cumprod()` multiplies the daily results together, because returns
    # compound: 10% then 10% is 21%, not 20%.
    per_date["equity"] = (1.0 + per_date["net"]).cumprod()
    return per_date.reset_index()


# Measure how bad the bad days were.
def tail_metrics(net: np.ndarray, alpha: float = 0.05) -> dict:
    """CVaR, VaR, max drawdown and the usual summary statistics."""
    # PLAIN ENGLISH: the whole point of the gate is to see whether the WORST outcomes get
    # less bad. So the measurements here concentrate on the bad tail rather than the average.
    r = np.asarray(net, dtype=float)
    r = r[np.isfinite(r)]
    # Fewer than 20 days: tail statistics from that would be meaningless. Report all-unknown
    # rather than numbers that would look real.
    if len(r) < 20:
        return dict.fromkeys(
            ("mean", "vol_annual", "var", "cvar", "max_drawdown", "worst_day",
             "downside_vol", "n"), np.nan)
    # VaR: where the worst 5% of days begins.
    var = float(np.percentile(r, alpha * 100))
    tail = r[r <= var]
    # The running total, and how far below its own peak it ever fell.
    equity = np.cumprod(1.0 + r)
    dd = equity / np.maximum.accumulate(equity) - 1.0
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "total_return": float(equity[-1] - 1.0),
        # How jumpy the results were, annualised.
        "vol_annual": float(r.std(ddof=1) * np.sqrt(252)),
        # Jumpiness counting only the DOWN days. Reported separately because upward
        # jumpiness is not something anybody minds, and lumping the two together disguises
        # that. The guard requires at least three down days for the figure to mean anything.
        "downside_vol": float(r[r < 0].std(ddof=1) * np.sqrt(252))
        if (r < 0).sum() > 2 else np.nan,
        "var": var,
        # CVaR: the AVERAGE of the worst 5%. More informative than VaR, which only marks
        # where the tail starts and says nothing about how far it runs.
        "cvar": float(tail.mean()) if len(tail) else np.nan,
        # The worst peak-to-trough fall. The number people actually feel.
        "max_drawdown": float(dd.min()),
        "worst_day": float(r.min()),
    }


# THE EXPERIMENT: run both arms and report the difference.
def capital_consequence(scored: pd.DataFrame, forward_return_col: str,
                        policy: GatePolicy = GatePolicy(),
                        cost: CostModel = CostModel()) -> dict:
    """Run control and treatment and report the difference.

    ``control``   the base policy, ungated
    ``treatment`` the identical base policy with the integrity gate applied
    """
    # PLAIN ENGLISH: "control" and "treatment" are borrowed straight from medicine. The
    # control group gets nothing; the treatment group gets the thing being tested; and the
    # two are identical in every other respect.
    gated = apply_gate(scored, policy)
    # Both arms replayed from the SAME table, with the SAME costs. Only the weight column
    # differs -- which is what makes the comparison clean.
    ctrl = backtest(gated, "w_base", forward_return_col, cost)
    trt = backtest(gated, "w_gated", forward_return_col, cost)
    m_ctrl = tail_metrics(ctrl["net"].to_numpy())
    m_trt = tail_metrics(trt["net"].to_numpy())
    # The difference on every measure. The `np.isfinite` guards mean a measure that could not
    # be computed for one arm reports as unknown rather than producing a nonsense difference.
    delta = {k: (m_trt[k] - m_ctrl[k]) if np.isfinite(m_ctrl.get(k, np.nan))
             and np.isfinite(m_trt.get(k, np.nan)) else np.nan
             for k in m_ctrl if k != "n"}
    # Opportunity cost: return given up by holding capital back.
    # PLAIN ENGLISH: the price of caution, reported prominently rather than tucked away.
    # Holding back from risky companies means missing out when they do well, and that cost is
    # real. Reporting only the reduced losses, and not the forgone gains, would be a
    # half-truth.
    opp = float(m_ctrl["total_return"] - m_trt["total_return"])
    return {
        "control": m_ctrl, "treatment": m_trt, "delta": delta,
        "opportunity_cost_total_return": opp,
        # How open the tap was on average -- context for how much intervention produced this.
        "mean_cap": float(gated["cap"].mean()),
        "mean_gated_exposure": float(gated["w_gated"].sum()
                                     / max(1, gated["date"].nunique())),
        # The full day-by-day series for both arms, so a reader can plot and check them
        # rather than having to trust the summary.
        "control_series": ctrl, "treatment_series": trt,
        # Every setting used, recorded with the result, so the whole thing can be reproduced.
        "policy": {"full_allowance_below": policy.full_allowance_below,
                   "zero_allowance_above": policy.zero_allowance_above,
                   "floor": policy.floor,
                   "uncertainty_penalty": policy.uncertainty_penalty,
                   "cost_bps": cost.bps_per_unit_turnover},
        # And the warning travels WITH the numbers, so it cannot be separated from them when
        # somebody copies a figure into a slide. Note all three parts: hypothetical, not
        # advice, and not a return anybody could actually have achieved.
        "disclaimer": ("hypothetical research exposure policy applied to historical "
                       "data; not advice, not a strategy, and not an achievable return"),
    }
