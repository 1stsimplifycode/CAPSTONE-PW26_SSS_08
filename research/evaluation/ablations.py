"""Ablation arm definitions (spec sections 36, 71).

Each arm is a declarative edit to the feature frame plus a combination rule. Defining them
as data rather than code means the arm list, the results table and the paper table are
generated from one source and cannot drift apart.

Three kinds of arm:

*block*      which evidence blocks are available
*component*  which parts of the method are switched off (regime conditioning,
             uncertainty weighting, propagation)
*combiner*   which combination rule is used, holding the evidence fixed

PLAIN ENGLISH -- what this whole file is about:

ABLATION: taking ingredients out to find out which ones were doing anything.

If you bake a cake and it is delicious, you do not actually know why. Was it the vanilla?
The butter? So you bake it again without the vanilla. Worse? Then the vanilla mattered.
Identical? Then the vanilla was doing nothing, and you have been buying it for years for
no reason.

That is exactly what happens here. The full system uses four families of evidence. Take
one away and rerun. Whatever the score drops by is what that family was worth.

Each variation is called an ARM -- borrowed from medical trials, where each group of
patients receiving a different treatment is an arm of the study.

THREE KINDS OF ARM, asking three different questions:
  BLOCK arms     -- which EVIDENCE is available? ("What if we had no trading data?")
  COMPONENT arms -- which METHODS are switched on? ("What if we did not adjust for
                    market mood?")
  COMBINER arms  -- how are the opinions COMBINED? Same evidence throughout, so any
                    difference must come from the combining rule alone.

AND THE DESIGN CHOICE IN THE HEADER, which is quietly important:
"Defining them as data rather than code means the arm list, the results table and the
paper table are generated from one source and cannot drift apart."

Meaning: the list of experiments is written down ONCE, here, as data. The code that runs
them reads this list; the results table reads this list; the paper reads this list. If
somebody adds an experiment, all three update together automatically.
The alternative -- typing the experiment list into three places -- guarantees that one day
somebody updates two of them and the paper quietly describes an experiment that no longer
matches the one that ran. Nothing would break. Nothing would warn anybody.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The propagation module, for its list of feature names.
from research.propagation import graph as pg

# The four families of evidence.
ALL_BLOCKS = ["market", "microstructure", "regime", "propagation"]

#: The two blocks describing price and volume behaviour directly, as opposed to the
#: derived regime and cross-instrument blocks built on top of them.
# PLAIN ENGLISH: these two are the raw observations -- what the market actually did. The
# other two are built ON TOP of them by further calculation. Grouping them lets us ask
# "does all the derived cleverness add anything to the plain facts?".
PRICE_BLOCKS = ["market", "microstructure"]

#: Columns that encode *derived* market structure as opposed to the raw descriptors.
#: Dropping exactly these answers RQ3 -- does the derived representation add anything
#: over the underlying descriptors -- without also removing the block.
# PLAIN ENGLISH: a precise and rather elegant experiment. Rather than removing a whole
# family, this removes only the CLEVER measurements within it -- the trend-or-revert score,
# the disorderliness score, and so on -- while keeping the simple ones like prices and
# volumes. So it asks specifically: was the sophisticated processing earning its keep, or
# was the raw data carrying everything all along?
DERIVED_COLUMNS = [
    "vol_ratio_5_63", "ret_acf1_21", "hurst_63", "ret_entropy_21",
    "amihud_21", "abnormal_ret_21", "trade_size_z_21", "trades_z_21",
    "turnover_per_trade_z_21",
]

# The neighbour-stress columns.
PROPAGATION_COLUMNS = list(pg.PROPAGATION_FEATURES)


@dataclass
# One experimental variation.
class Arm:
    # Its name, used in every results table.
    name: str
    # Which families of evidence it is allowed.
    blocks: list[str]
    # Which combining rule it uses.
    combiner: str = "regime_corrected"
    # Which individual measurements to blank out.
    drop_columns: list[str] = field(default_factory=list)
    # Which of the three kinds it is.
    kind: str = "block"
    # WHAT WE EXPECT AND WHY -- written before running. This is what makes the arm a real
    # experiment rather than a number somebody generated and then explained afterwards.
    hypothesis: str = ""
    note: str = ""


# The arms that vary which evidence is available.
def _block_arms() -> list[Arm]:
    base = "regime_corrected"
    arms = [
        # THE REFERENCE: everything switched on. Every other arm is compared against this.
        Arm("FULL", ALL_BLOCKS, base, kind="reference",
            hypothesis="the complete evidence stack detects injected integrity "
                       "episodes better than any subset"),
        # Each family entirely on its own -- how much can each do alone?
        Arm("MARKET_ONLY", ["market"], base),
        Arm("MICRO_ONLY", ["microstructure"], base),
        Arm("REGIME_ONLY", ["regime"], base),
        Arm("PROPAGATION_ONLY", ["propagation"], base),
        # Every PAIR of families. Pairs matter because two families might be worthless
        # separately and powerful together, and only testing them singly would miss that.
        Arm("MARKET_MICRO", list(PRICE_BLOCKS), base),
        Arm("MARKET_REGIME", ["market", "regime"], base),
        Arm("MARKET_PROPAGATION", ["market", "propagation"], base),
        Arm("MICRO_REGIME", ["microstructure", "regime"], base),
        Arm("MICRO_PROPAGATION", ["microstructure", "propagation"], base),
        Arm("REGIME_PROPAGATION", ["regime", "propagation"], base),
        # The raw observations, alone and then plus one derived family at a time.
        Arm("PRICE_BLOCKS", list(PRICE_BLOCKS), base),
        Arm("PRICE_BLOCKS_REGIME", PRICE_BLOCKS + ["regime"], base),
        Arm("PRICE_BLOCKS_PROPAGATION", PRICE_BLOCKS + ["propagation"], base),
    ]
    # And "everything EXCEPT one" for each family -- built automatically rather than typed
    # out, so adding a fifth family in future creates its leave-one-out arm for free.
    # These are the purest ablations: the drop from FULL is exactly what that family adds
    # ON TOP OF everything else, which is a different and more useful question than what it
    # can do on its own.
    for m in ALL_BLOCKS:
        arms.append(Arm("NO_%s" % m.upper(), [b for b in ALL_BLOCKS if b != m], base,
                        hypothesis="removing %s degrades detection" % m))
    return arms


# The arms that switch parts of the METHOD off, holding the evidence fixed.
def _component_arms() -> list[Arm]:
    return [
        # Keep every family, but remove only the sophisticated measurements. Note `blocks`
        # is still ALL_BLOCKS -- it is the columns that are blanked, not the family.
        Arm("NO_DERIVED", ALL_BLOCKS, "regime_corrected",
            drop_columns=list(DERIVED_COLUMNS), kind="component",
            hypothesis="the derived market-structure representation adds information "
                       "beyond the raw descriptors (RQ3)"),
        # Do not adjust for what mood the market is in.
        Arm("NO_REGIME_CONDITIONING",
            [b for b in ALL_BLOCKS if b != "regime"], "static_attention",
            kind="component",
            hypothesis="regime conditioning improves combination (RQ9)"),
        Arm("NO_UNCERTAINTY", ALL_BLOCKS, "static_attention", kind="component",
            hypothesis="uncertainty-aware weighting reduces false positives (RQ8)",
            # A precise and necessary clarification: uncertainty is still MEASURED and
            # REPORTED here; it is simply not used to decide the weights. Without this note a
            # reader could easily think the arm switches off uncertainty reporting entirely,
            # which would be a different experiment altogether.
            note="uncertainty is still reported, it is simply not used for weighting"),
        Arm("NO_PROPAGATION_COMPONENT", [b for b in ALL_BLOCKS if b != "propagation"],
            "regime_corrected", kind="component",
            hypothesis="cross-instrument propagation improves early detection (RQ7)"),
    ]


# The arms that vary only HOW the opinions are combined.
def _combiner_arms() -> list[Arm]:
    # PLAIN ENGLISH: every one of these gets ALL_BLOCKS -- identical evidence throughout. So
    # any difference between them can only come from the combining rule. One variable at a
    # time, which is what makes a comparison mean anything.
    return [
        # One big model over everything.
        Arm("COMBINER_EARLY", ALL_BLOCKS, "early", kind="combiner"),
        # Equal weight to each specialist.
        Arm("COMBINER_LATE", ALL_BLOCKS, "late", kind="combiner"),
        # Learned weights, fixed across all rows.
        Arm("COMBINER_STATIC", ALL_BLOCKS, "static_attention", kind="combiner"),
        # THE NEGATIVE CONTROL. This is the rule that was proved algebraically to do
        # nothing. Read the hypothesis: it predicts the arm MUST equal static attention.
        # That is a prediction that can fail, and if it ever does, something else is broken.
        # Keeping a known-inert arm in the suite is a standing test of the whole harness.
        Arm("COMBINER_REGIME_INHERITED", ALL_BLOCKS, "regime_inherited", kind="combiner",
            hypothesis="the inherited regime-conditioned formulation is degenerate and "
                       "must equal static attention (section 57)"),
        # The fixed version, which genuinely varies weights by market mood.
        Arm("COMBINER_REGIME_CORRECTED", ALL_BLOCKS, "regime_corrected", kind="combiner"),
        # Weights scaled by each specialist's confidence.
        Arm("COMBINER_UNCERTAINTY", ALL_BLOCKS, "uncertainty", kind="combiner"),
    ]


# Every arm, in one list.
def all_arms() -> list[Arm]:
    return _block_arms() + _component_arms() + _combiner_arms()


# Apply an arm's column edits to the data.
def apply_arm(df: pd.DataFrame, arm: Arm) -> pd.DataFrame:
    """Blank the columns an arm removes. Block removal is handled by the runner."""
    # Nothing to blank: hand the data straight back, unchanged and uncopied.
    if not arm.drop_columns:
        return df
    out = df.copy()
    for c in arm.drop_columns:
        if c in out.columns:
            # BLANKED, not deleted. Setting to "unknown" rather than removing the column
            # matters: every arm then has exactly the same shape of table, so nothing
            # downstream has to cope with columns appearing and disappearing. And the model
            # treats it as genuinely missing evidence, which is precisely what the
            # experiment is meant to simulate.
            out[c] = np.nan
    return out


# The whole experiment plan as a readable table.
def arm_table() -> pd.DataFrame:
    # PLAIN ENGLISH: this is the ONE SOURCE the header talks about. The runner, the results
    # table and the paper all read this. Add an arm above and it appears in all three
    # automatically, with no chance of the three descriptions drifting apart.
    return pd.DataFrame([{"arm": a.name, "kind": a.kind,
                          # `",".join(...)` turns the list of families into one readable
                          # piece of text like "market,regime".
                          "blocks": ",".join(a.blocks),
                          "combiner": a.combiner,
                          "dropped_columns": len(a.drop_columns),
                          # `or ""` so an arm with no stated hypothesis shows a blank rather
                          # than the word "None".
                          "hypothesis": a.hypothesis or ""} for a in all_arms()])
