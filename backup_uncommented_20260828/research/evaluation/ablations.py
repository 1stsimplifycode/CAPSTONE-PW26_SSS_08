"""Ablation arm definitions (spec sections 36, 71).

Each arm is a declarative edit to the feature frame plus a combination rule. Defining them
as data rather than code means the arm list, the results table and the paper table are
generated from one source and cannot drift apart.

Three kinds of arm:

*block*      which evidence blocks are available
*component*  which parts of the method are switched off (regime conditioning,
             uncertainty weighting, propagation)
*combiner*   which combination rule is used, holding the evidence fixed
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research.propagation import graph as pg

ALL_BLOCKS = ["market", "microstructure", "regime", "propagation"]

#: The two blocks describing price and volume behaviour directly, as opposed to the
#: derived regime and cross-instrument blocks built on top of them.
PRICE_BLOCKS = ["market", "microstructure"]

#: Columns that encode *derived* market structure as opposed to the raw descriptors.
#: Dropping exactly these answers RQ3 -- does the derived representation add anything
#: over the underlying descriptors -- without also removing the block.
DERIVED_COLUMNS = [
    "vol_ratio_5_63", "ret_acf1_21", "hurst_63", "ret_entropy_21",
    "amihud_21", "abnormal_ret_21", "trade_size_z_21", "trades_z_21",
    "turnover_per_trade_z_21",
]

PROPAGATION_COLUMNS = list(pg.PROPAGATION_FEATURES)


@dataclass
class Arm:
    name: str
    blocks: list[str]
    combiner: str = "regime_corrected"
    drop_columns: list[str] = field(default_factory=list)
    kind: str = "block"
    hypothesis: str = ""
    note: str = ""


def _block_arms() -> list[Arm]:
    base = "regime_corrected"
    arms = [
        Arm("FULL", ALL_BLOCKS, base, kind="reference",
            hypothesis="the complete evidence stack detects injected integrity "
                       "episodes better than any subset"),
        Arm("MARKET_ONLY", ["market"], base),
        Arm("MICRO_ONLY", ["microstructure"], base),
        Arm("REGIME_ONLY", ["regime"], base),
        Arm("PROPAGATION_ONLY", ["propagation"], base),
        Arm("MARKET_MICRO", list(PRICE_BLOCKS), base),
        Arm("MARKET_REGIME", ["market", "regime"], base),
        Arm("MARKET_PROPAGATION", ["market", "propagation"], base),
        Arm("MICRO_REGIME", ["microstructure", "regime"], base),
        Arm("MICRO_PROPAGATION", ["microstructure", "propagation"], base),
        Arm("REGIME_PROPAGATION", ["regime", "propagation"], base),
        Arm("PRICE_BLOCKS", list(PRICE_BLOCKS), base),
        Arm("PRICE_BLOCKS_REGIME", PRICE_BLOCKS + ["regime"], base),
        Arm("PRICE_BLOCKS_PROPAGATION", PRICE_BLOCKS + ["propagation"], base),
    ]
    for m in ALL_BLOCKS:
        arms.append(Arm("NO_%s" % m.upper(), [b for b in ALL_BLOCKS if b != m], base,
                        hypothesis="removing %s degrades detection" % m))
    return arms


def _component_arms() -> list[Arm]:
    return [
        Arm("NO_DERIVED", ALL_BLOCKS, "regime_corrected",
            drop_columns=list(DERIVED_COLUMNS), kind="component",
            hypothesis="the derived market-structure representation adds information "
                       "beyond the raw descriptors (RQ3)"),
        Arm("NO_REGIME_CONDITIONING",
            [b for b in ALL_BLOCKS if b != "regime"], "static_attention",
            kind="component",
            hypothesis="regime conditioning improves combination (RQ9)"),
        Arm("NO_UNCERTAINTY", ALL_BLOCKS, "static_attention", kind="component",
            hypothesis="uncertainty-aware weighting reduces false positives (RQ8)",
            note="uncertainty is still reported, it is simply not used for weighting"),
        Arm("NO_PROPAGATION_COMPONENT", [b for b in ALL_BLOCKS if b != "propagation"],
            "regime_corrected", kind="component",
            hypothesis="cross-instrument propagation improves early detection (RQ7)"),
    ]


def _combiner_arms() -> list[Arm]:
    return [
        Arm("COMBINER_EARLY", ALL_BLOCKS, "early", kind="combiner"),
        Arm("COMBINER_LATE", ALL_BLOCKS, "late", kind="combiner"),
        Arm("COMBINER_STATIC", ALL_BLOCKS, "static_attention", kind="combiner"),
        Arm("COMBINER_REGIME_INHERITED", ALL_BLOCKS, "regime_inherited", kind="combiner",
            hypothesis="the inherited regime-conditioned formulation is degenerate and "
                       "must equal static attention (section 57)"),
        Arm("COMBINER_REGIME_CORRECTED", ALL_BLOCKS, "regime_corrected", kind="combiner"),
        Arm("COMBINER_UNCERTAINTY", ALL_BLOCKS, "uncertainty", kind="combiner"),
    ]


def all_arms() -> list[Arm]:
    return _block_arms() + _component_arms() + _combiner_arms()


def apply_arm(df: pd.DataFrame, arm: Arm) -> pd.DataFrame:
    """Blank the columns an arm removes. Block removal is handled by the runner."""
    if not arm.drop_columns:
        return df
    out = df.copy()
    for c in arm.drop_columns:
        if c in out.columns:
            out[c] = np.nan
    return out


def arm_table() -> pd.DataFrame:
    return pd.DataFrame([{"arm": a.name, "kind": a.kind,
                          "blocks": ",".join(a.blocks),
                          "combiner": a.combiner,
                          "dropped_columns": len(a.drop_columns),
                          "hypothesis": a.hypothesis or ""} for a in all_arms()])
