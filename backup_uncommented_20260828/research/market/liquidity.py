"""The liquidity state vector, its stress gate, and what the gate blames when it fires.

Four Week 2 estimators, each measuring a different way a market can be illiquid, and each
computed elsewhere in this package from real data::

    L_t = [ RV_t , lambda_i , Amihud_it , Fano_i ]

``RV_t``       realised variance from intraday returns (research.market.realised_variance)
``lambda_i``   price impact per unit signed flow      (research.market.price_impact)
``Amihud_it``  |return| per unit turnover             (research.market.features)
``Fano_i``     trade-arrival dispersion               (research.market.arrival)

They are deliberately not redundant. Realised variance says the price moved; price impact
says it moved *because* someone traded; Amihud says the same thing from daily data and
survives where intraday does not; arrival dispersion says the trades came in bursts rather
than steadily. A security can be high on one and ordinary on the rest, and the attribution
below is what makes that visible instead of averaging it away.

**Normalisation.** Components are on incomparable scales -- variance in squared log
returns, ``lambda`` in log-price per share -- so they are standardised before combination
by a *robust* z-score::

    z = (x - median(x)) / (1.4826 * MAD(x))

Median and MAD rather than mean and standard deviation, for the same reason the thresholds
are conformal: these distributions are skewed and heavy-tailed, and a single extreme
security would otherwise set the scale for everything and flatten the rest toward zero.
The 1.4826 makes MAD consistent with the standard deviation under normality, so a z of 2
keeps its usual reading without the normality being assumed.

**The stress gate** fires when the aggregate stress score crosses a threshold that is
itself distribution-free (:mod:`research.market.thresholds`) and fitted to a declared
false-alarm budget. The score is the mean of the available components' robust z-scores,
so it is defined even when a component is missing for a security -- which matters, because
realised variance exists only for the recent intraday window while Amihud spans the daily
panel.

**Attribution is arithmetic, not narration.** When the gate fires, each component's
contribution is its own z-score's share of the total::

    contribution_j = z_j / sum_k z_k        (over components with z_k > 0)

That is computed from the same numbers that produced the score. There is no lookup table
of explanations, and :func:`attribute` has no access to any text: change an estimator and
the attribution changes, which is what the C6 test asserts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from scipy import stats

from research.market import thresholds as T

LIQUIDITY_VERSION = "liquidity-v1"

#: MAD -> standard deviation under normality.
MAD_SCALE = 1.4826

#: The state vector's components and the direction in which each means "less liquid".
#: Every one is produced by a Week 2 estimator; none is invented to pad the vector.
COMPONENTS = {
    "realised_variance": "upper",
    "price_impact_lambda": "upper",
    "amihud": "upper",
    "arrival_fano": "upper",
}

#: Human labels, for display only. Never used in the attribution arithmetic.
COMPONENT_LABELS = {
    "realised_variance": "Realised variance",
    "price_impact_lambda": "Price impact",
    "amihud": "Amihud illiquidity",
    "arrival_fano": "Trade-arrival dispersion",
}


def robust_z(x: pd.Series | np.ndarray) -> np.ndarray:
    """Median/MAD standardisation. Zero-MAD columns return zeros, never infinities."""
    v = np.asarray(x, dtype=float)
    finite = v[np.isfinite(v)]
    if len(finite) < 2:
        return np.full(len(v), np.nan)
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med)))
    scale = MAD_SCALE * mad
    if scale <= 0:
        # Degenerate spread: every observation is the same, so none is unusual.
        return np.where(np.isfinite(v), 0.0, np.nan)
    return (v - med) / scale


# -- C3: does the daily proxy rank securities the way intraday impact does? -------------

@dataclass
class RankCrossCheck:
    """Spearman and Kendall agreement between two liquidity rankings."""

    measure_a: str
    measure_b: str
    n: int
    spearman_rho: float
    spearman_p_value: float
    spearman_ci_low: float
    spearman_ci_high: float
    kendall_tau: float
    kendall_p_value: float
    interpretation: str
    computed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _fisher_ci(rho: float, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Fisher z confidence interval for a rank correlation.

    The variance uses ``1.06/(n-3)``, the Spearman-specific correction, rather than the
    Pearson ``1/(n-3)``: rank correlations are slightly more variable and the narrower
    interval would overstate the agreement.
    """
    if n < 5 or not np.isfinite(rho) or abs(rho) >= 1.0:
        return float("nan"), float("nan")
    z = np.arctanh(rho)
    se = np.sqrt(1.06 / (n - 3))
    crit = stats.norm.ppf(0.5 + conf / 2.0)
    return float(np.tanh(z - crit * se)), float(np.tanh(z + crit * se))


def cross_check_rankings(amihud: pd.Series, price_impact: pd.Series) -> RankCrossCheck:
    """Compare the Amihud illiquidity ranking against the price-impact ranking.

    Both are estimates of the same latent quantity -- how far a given amount of trading
    moves the price -- reached by different routes and from different data. Agreement is
    evidence that the daily proxy is measuring what the intraday regression measures; a
    weak correlation is equally informative and is reported rather than suppressed.
    """
    joined = pd.concat([amihud.rename("amihud"),
                        price_impact.rename("lambda")], axis=1).dropna()
    n = len(joined)
    if n < 5:
        return RankCrossCheck(
            "amihud", "price_impact_lambda", n, float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan"), float("nan"),
            "Too few securities with both measures to compare rankings.",
            datetime.now(UTC).isoformat())

    rho, p_rho = stats.spearmanr(joined["amihud"], joined["lambda"])
    tau, p_tau = stats.kendalltau(joined["amihud"], joined["lambda"])
    lo, hi = _fisher_ci(float(rho), n)

    if p_rho < 0.05 and rho > 0:
        interp = ("The two rankings agree (rho=%.3f, p=%.4g, n=%d): securities the "
                  "daily Amihud proxy calls illiquid are the ones the intraday "
                  "regression finds have the largest price impact."
                  % (rho, p_rho, n))
    elif p_rho < 0.05 and rho < 0:
        interp = ("The rankings disagree significantly (rho=%.3f, p=%.4g, n=%d). "
                  "One of the two is not measuring illiquidity on this sample."
                  % (rho, p_rho, n))
    else:
        interp = ("No significant rank agreement (rho=%.3f, p=%.4g, n=%d). The daily "
                  "proxy is not demonstrated to track intraday price impact here."
                  % (rho, p_rho, n))

    return RankCrossCheck(
        measure_a="amihud", measure_b="price_impact_lambda", n=n,
        spearman_rho=float(rho), spearman_p_value=float(p_rho),
        spearman_ci_low=lo, spearman_ci_high=hi,
        kendall_tau=float(tau), kendall_p_value=float(p_tau),
        interpretation=interp, computed_at=datetime.now(UTC).isoformat())


# -- C6: the state vector --------------------------------------------------------------

def build_state_vector(components: pd.DataFrame) -> pd.DataFrame:
    """Standardise the components and combine them into a stress score.

    One row per security. Each component keeps its raw value *and* its robust z-score,
    because the attribution needs the z and the reader needs the raw number.
    """
    present = [c for c in COMPONENTS if c in components.columns]
    if not present:
        raise ValueError(
            "no liquidity components present; expected some of %s" % list(COMPONENTS))

    out = components.copy()
    zcols = []
    for c in present:
        zc = "z_%s" % c
        out[zc] = robust_z(out[c])
        zcols.append(zc)

    # Mean over the components that exist for this row: a security with no intraday
    # coverage still gets a score from the daily components rather than being dropped.
    out["stress_score"] = out[zcols].mean(axis=1, skipna=True)
    out["components_available"] = out[zcols].notna().sum(axis=1)
    out.attrs["components"] = present
    out.attrs["z_columns"] = zcols
    return out


def attribute(row: pd.Series, components: list[str]) -> dict[str, float]:
    """Each component's share of the stress this row shows.

    Only components pushing *toward* stress (positive z) can take credit for it, and the
    shares are normalised over those. A component sitting below the median is not
    responsible for an alarm, and giving it a negative share would let two components
    cancel into a confident-looking zero.

    Computed entirely from ``row``. No constants, no strings, no lookup.
    """
    z = {c: float(row.get("z_%s" % c, np.nan)) for c in components}
    positive = {c: v for c, v in z.items() if np.isfinite(v) and v > 0}
    total = sum(positive.values())
    if total <= 0:
        return dict.fromkeys(components, 0.0)
    return {c: (positive.get(c, 0.0) / total) for c in components}


@dataclass
class StressGate:
    """Fires when the stress score crosses a distribution-free threshold."""

    threshold: T.Threshold
    components: list[str]

    def evaluate(self, state: pd.DataFrame) -> pd.DataFrame:
        """Flag stressed rows and attribute each firing to its estimators."""
        out = state.copy()
        out["stress_gate_fired"] = self.threshold.flag(
            out["stress_score"].to_numpy())

        attributions = []
        for _, row in out.iterrows():
            if not row["stress_gate_fired"]:
                attributions.append(dict.fromkeys(self.components, 0.0))
                continue
            attributions.append(attribute(row, self.components))

        for c in self.components:
            out["attribution_%s" % c] = [a.get(c, 0.0) for a in attributions]

        fired = out["stress_gate_fired"]
        cols = ["attribution_%s" % c for c in self.components]
        out["primary_driver"] = np.where(
            fired, out[cols].idxmax(axis=1).str.replace("attribution_", "", regex=False),
            "")
        return out

    def to_dict(self) -> dict:
        return {
            "liquidity_version": LIQUIDITY_VERSION,
            "components": self.components,
            "threshold": self.threshold.to_dict(),
            "attribution_rule": (
                "contribution_j = z_j / sum over components with z_k > 0. Computed from "
                "the state vector's own z-scores; no hardcoded explanation."),
        }


def fit_stress_gate(state: pd.DataFrame,
                    budget: T.FalseAlarmBudget = T.FALSE_ALARM_BUDGET,
                    calibration: np.ndarray | None = None) -> StressGate:
    """Fit the gate's threshold to the declared false-alarm budget."""
    scores = (state["stress_score"].to_numpy() if calibration is None
              else np.asarray(calibration, dtype=float))
    th = T.fit_threshold("stress_score", scores, budget, direction="upper")
    return StressGate(threshold=th, components=list(state.attrs.get("components", [])
                                                    or [c for c in COMPONENTS
                                                        if c in state.columns]))


def summary(state: pd.DataFrame, gate: StressGate,
            cross_check: RankCrossCheck | None) -> dict:
    fired = state.get("stress_gate_fired")
    out = {
        "liquidity_version": LIQUIDITY_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "state_vector": "L = [%s]" % ", ".join(gate.components),
        "components": gate.components,
        "normalisation": "robust z, (x - median) / (1.4826 * MAD)",
        "securities": int(len(state)),
        "stress_threshold": gate.threshold.threshold,
        "false_alarm_budget": gate.threshold.budget,
        "threshold_method": gate.threshold.method,
        "distribution_free": gate.threshold.distribution_free,
        "gate_fired": int(fired.sum()) if fired is not None else 0,
        "attribution_rule": gate.to_dict()["attribution_rule"],
    }
    if fired is not None and fired.any():
        drivers = state.loc[fired, "primary_driver"].value_counts().to_dict()
        out["primary_drivers"] = {k: int(v) for k, v in drivers.items()}
        out["fired_symbols"] = state.loc[fired, "symbol"].tolist()[:20]
    if cross_check is not None:
        out["amihud_vs_price_impact"] = cross_check.to_dict()
    return out


# -- external validation against the exchange's own band-hit record ---------------------

def validate_against_band_hits(state: pd.DataFrame,
                               band_flags: pd.DataFrame) -> dict:
    """Check the stress gate against an independent exchange fact.

    A security pinned at its circuit limit could not trade freely on that session. That is
    NSE's own statement about the session, arrived at with no reference to realised
    variance, price impact, Amihud or arrival dispersion. So the rate at which band hits
    coincide with the gate firing is a genuine external check on whether the state vector
    is detecting illiquidity or detecting itself.

    Reported as a lift with both base rates, not as a pass/fail: the gate is tuned to a 1%
    false-alarm budget on a different quantity, so exact agreement is not expected and
    would be suspicious if it appeared.
    """
    if "stress_gate_fired" not in state.columns:
        return {"available": False, "why": "state vector has no gate result"}

    merged = state.merge(
        band_flags[["symbol", "session", "band_hit"]], on=["symbol", "session"],
        how="left")
    merged["band_hit"] = merged["band_hit"].fillna(False).astype(bool)

    fired = merged["stress_gate_fired"].astype(bool)
    n_fired = int(fired.sum())
    if n_fired == 0:
        return {"available": True, "gate_fired": 0,
                "note": "the gate did not fire on any observation in this window"}

    hit_when_fired = float(merged.loc[fired, "band_hit"].mean())
    hit_when_quiet = float(merged.loc[~fired, "band_hit"].mean())
    base = float(merged["band_hit"].mean())
    return {
        "available": True,
        "observations": int(len(merged)),
        "gate_fired": n_fired,
        "band_hit_base_rate": base,
        "band_hit_rate_when_gate_fired": hit_when_fired,
        "band_hit_rate_when_gate_quiet": hit_when_quiet,
        "lift": (hit_when_fired / base) if base > 0 else None,
        "source": "NSE PR bundle bh member (exchange-published band hits)",
        "interpretation": (
            "Securities the gate called stressed hit a circuit band on %.2f%% of those "
            "sessions, against a %.2f%% base rate across the window."
            % (hit_when_fired * 100, base * 100)),
    }
