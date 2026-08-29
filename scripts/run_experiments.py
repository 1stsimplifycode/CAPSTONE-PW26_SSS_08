"""Run baselines and every ablation arm, with statistics.

    python scripts/run_experiments.py --dataset market_dataset.parquet

Writes one artifact bundle per arm under ``research_artifacts/experiment_reports/`` and a
consolidated results table. Nothing is hand-entered: the tables the paper uses are read
back from these files.

PLAIN ENGLISH -- what this whole file is about:

THE MAIN EXPERIMENT. Everything, measured, in one run.

Three things happen here, in order:

1. BASELINES -- the simple, dumb methods. Rank by volume. Rank by price move. Pick at
   random. These exist to answer the question that sinks most machine-learning claims:
   is the clever model actually better than the obvious thing?

2. ABLATION ARMS -- take the full model and remove ONE piece. Then another. Each "arm" is
   the whole system minus one component. If removing a piece changes nothing, that piece was
   not doing anything, whatever the design document claims.

3. STATISTICS -- confidence intervals and paired tests, so a difference between two arms
   can be judged rather than merely observed.

AND THE LAST SENTENCE OF THE DOCSTRING IS THE ONE THAT MATTERS:
"Nothing is hand-entered: the tables the paper uses are read back from these files."
Nobody types a number into the write-up. The write-up READS the files this produces. Which
means a number in the paper cannot drift from the number that was computed -- the commonest
way honest research goes quietly wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Silence library warnings so the progress output stays readable. Everything that MATTERS is
# logged explicitly below.
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import paths, progress
from research.core.manifest import environment_snapshot
from research.evaluation import ablations as ab
from research.evaluation import experiment as ex
from research.evaluation import metrics as mx
from research.models import baselines as bl
from research.statistics import tests as stx


def auprc_of(df: pd.DataFrame, col: str = "integrity_risk") -> float:
    # Imported inside the function because sklearn is slow to load, and this is only needed
    # when a score is actually computed.
    from sklearn.metrics import average_precision_score
    y = df["is_episode"].to_numpy(int)
    # ALL ONE CLASS -> not-a-number, honestly.
    # PLAIN ENGLISH: if every row is "normal", or every row is "an episode", there is nothing
    # to tell apart and the score is undefined. Returning 0 would look like terrible
    # performance; returning 1 would look perfect. Both would be inventions. NaN says "this
    # question has no answer here", and the machinery downstream knows how to handle that.
    if len(np.unique(y)) < 2:
        return float("nan")
    # AUPRC -- area under the precision-recall curve. The right measure when the thing being
    # detected is rare, because it is not flattered by the mass of easy negatives.
    return float(average_precision_score(y, df[col].to_numpy(float)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="market_dataset.parquet")
    # VALIDATION, not holdout. The frozen slice stays frozen.
    ap.add_argument("--eval-split", default="validation")
    ap.add_argument("--seed", type=int, default=20260818)
    # 600 resamples for the bootstrap intervals.
    ap.add_argument("--bootstrap", type=int, default=600)
    args = ap.parse_args()

    paths.ensure_dirs()
    progress.log("loading %s" % args.dataset)
    data = pd.read_parquet(paths.PANEL / args.dataset)
    progress.log("dataset %d rows, splits %s"
                 % (len(data), data["split"].value_counts().to_dict()))

    # TRAIN and EVALUATE are separate slices, and they never mix. Testing on data the model
    # learned from is like marking your own homework with the answers open.
    train = data[data["split"] == "train"]
    evald = data[data["split"] == args.eval_split]
    y_tr = train["is_episode"].to_numpy(int)
    y_ev = evald["is_episode"].to_numpy(int)
    # THE POSITIVE RATE PRINTED FOR BOTH. Essential: an AUPRC of 0.4 is superb if only 2% of
    # rows are positive, and dreadful if 40% are. The number is meaningless without this.
    progress.log("train %d (%.3f positive) | eval %d (%.3f positive)"
                 % (len(train), y_tr.mean(), len(evald), y_ev.mean()))

    # -- baselines --------------------------------------------------------------------
    # THE SIMPLE METHODS FIRST, so the clever one has something to beat.
    progress.log("running baselines")
    base_rows = []
    base_scores: dict[str, np.ndarray] = {}
    for name, res in bl.run_all(train, evald, y_tr, args.seed).items():
        if res.status != "OK":
            # A baseline that could not run is RECORDED as such, with its reason -- not
            # quietly dropped, which would leave the comparison looking cleaner than it was.
            base_rows.append({"model": name, "status": res.status, "note": res.note})
            progress.log("  %-22s %s" % (name, res.status))
            continue
        m = mx.detection_metrics(y_ev, res.eval_score)
        base_scores[name] = res.eval_score
        # `**m` unpacks all the metrics into the row alongside the name.
        base_rows.append({"model": name, "status": "OK", **m})
        progress.log("  %-22s auprc=%.4f auroc=%.4f" % (name, m["auprc"], m["auroc"]))
    baselines_df = pd.DataFrame(base_rows)

    # -- ablation arms ----------------------------------------------------------------
    arms = ab.all_arms()
    progress.log("running %d ablation arms" % len(arms))
    results: list[ex.ExperimentResult] = []
    per_row_scores: dict[str, pd.DataFrame] = {}
    t0 = time.time()
    # `enumerate(arms, 1)` numbers them from 1 rather than 0, for the progress display.
    for i, arm in enumerate(arms, 1):
        # THE SPEC IS FILLED IN BEFORE THE ARM RUNS -- hypothesis, which blocks are included,
        # how they combine, which data, which seed, what it is compared against. The question
        # is written down before the answer exists.
        spec = ex.ExperimentSpec(
            experiment_id="ablation", hypothesis=arm.hypothesis or
            "arm %s vs FULL" % arm.name,
            arm=arm.name, blocks=list(arm.blocks),
            combination_rule=arm.combiner, dataset_path=args.dataset,
            eval_split=args.eval_split, seed=args.seed,
            baseline="FULL", notes=[arm.note] if arm.note else [])
        # Switch off this arm's missing pieces, then run.
        d = ab.apply_arm(data, arm)
        r = ex.run(spec, d)
        results.append(r)
        if r.status == "OK":
            # Keep the per-row scores -- needed for the paired statistics below.
            per_row_scores[arm.name] = r.per_row
            progress.log("  [%2d/%d] %-26s auprc=%.4f auroc=%.4f f1=%.3f"
                         % (i, len(arms), arm.name, r.detection.get("auprc", np.nan),
                            r.detection.get("auroc", np.nan),
                            r.detection.get("f1", np.nan)))
        else:
            # FAILURES PRINTED IN THE SAME LIST, with the reason. A reader scanning the log
            # sees the gaps rather than a suspiciously tidy run of successes.
            progress.log("  [%2d/%d] %-26s FAILED: %s"
                         % (i, len(arms), arm.name, r.failure_reason))
    progress.log("arms done in %.1fs" % (time.time() - t0))

    table = ex.results_table(results)

    # -- statistics -------------------------------------------------------------------
    progress.log("bootstrap intervals and paired tests vs FULL")
    stat_rows = []
    ci_rows = []
    ref = per_row_scores.get("FULL")
    for arm in arms:
        pr = per_row_scores.get(arm.name)
        if pr is None:
            continue
        # Cluster on episode where present, otherwise on symbol: rows inside one episode
        # are not independent draws.
        # PLAIN ENGLISH: THE MOST IMPORTANT STATISTICAL IDEA IN THE FILE.
        # A bootstrap works by resampling. But you must resample the right THING.
        # An episode covering five days gives five rows that are really ONE event seen five
        # times. Resampling individual rows would treat them as five independent pieces of
        # evidence, which pretends you have far more information than you do -- and produces
        # confidence intervals that are far too narrow, making everything look significant.
        # So whole EPISODES are resampled, not rows. Rows outside any episode are grouped by
        # company, for the same reason.
        pr = pr.copy()
        pr["cluster"] = np.where(pr["episode_id"].astype(str) != "",
                                 pr["episode_id"].astype(str),
                                 "sym_" + pr["symbol"].astype(str))
        # The interval: not just "0.712" but "0.712, and repeated sampling puts it between
        # 0.68 and 0.74."
        ci = stx.cluster_bootstrap_ci(pr, auprc_of, "cluster", b=args.bootstrap,
                                      seed=args.seed)
        ci_rows.append({"arm": arm.name, "auprc": ci.statistic,
                        "ci_low": ci.ci_low, "ci_high": ci.ci_high,
                        "n": ci.n, "test": ci.name})
        if ref is not None and arm.name != "FULL":
            # PAIRED comparison: line this arm's score up against FULL's score ON THE SAME
            # ROWS, matched by company and date. Comparing overall averages instead would mix
            # in the difference between which rows each happened to see.
            merged = pr[["symbol", "date", "is_episode", "episode_id",
                         "integrity_risk"]].merge(
                ref[["symbol", "date", "integrity_risk"]],
                # The suffixes keep the two score columns distinguishable after the join.
                on=["symbol", "date"], suffixes=("_arm", "_full"))
            merged["cluster"] = np.where(merged["episode_id"].astype(str) != "",
                                         merged["episode_id"].astype(str),
                                         "sym_" + merged["symbol"].astype(str))
            # And the difference gets its OWN interval and p-value, again clustered.
            t = stx.paired_bootstrap_difference(
                merged, lambda d: auprc_of(d, "integrity_risk_full"),
                lambda d: auprc_of(d, "integrity_risk_arm"),
                "cluster", b=args.bootstrap, seed=args.seed)
            stat_rows.append({"arm": arm.name, "comparison": "FULL - arm",
                              "delta_auprc": t.statistic, "p_value": t.p_value,
                              "ci_low": t.ci_low, "ci_high": t.ci_high,
                              # The test NAMES ITSELF and describes what it did, so the row is
                              # readable without the code.
                              "test": t.name, "description": t.test_description})
    stats_df = pd.DataFrame(stat_rows)
    if len(stats_df):
        # BENJAMINI-HOCHBERG. Run twelve comparisons and, purely by chance, one will look
        # "significant at 5%" even if nothing is going on -- because 5% of twelve is more than
        # one. BH raises the bar to account for how many questions were asked.
        bh = stx.benjamini_hochberg(stats_df["p_value"].tolist())
        # BOTH the raw and the adjusted p-value are kept, so a reader can see what the
        # correction cost.
        stats_df["adjusted_p"] = bh["adjusted_p"].to_numpy()
        stats_df["significant_fdr_5pct"] = bh["reject"].to_numpy()
    ci_df = pd.DataFrame(ci_rows)

    # `how="left"` keeps every arm even if it has no interval -- a failed arm stays in the
    # table rather than vanishing from it.
    merged_table = table.merge(ci_df[["arm", "ci_low", "ci_high"]], on="arm",
                               how="left")

    # -- persist ----------------------------------------------------------------------
    out = paths.ARTIFACTS / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    # EVERYTHING IS SAVED: the results, the baselines, the tests, the intervals, the exact
    # definition of each arm, and the raw per-row scores. Enough for somebody else to redo
    # every calculation without rerunning the models.
    merged_table.to_csv(out / "ablation_results.csv", index=False)
    baselines_df.to_csv(out / "baseline_results.csv", index=False)
    stats_df.to_csv(out / "ablation_statistics.csv", index=False)
    ci_df.to_csv(out / "ablation_confidence_intervals.csv", index=False)
    ab.arm_table().to_csv(out / "arm_definitions.csv", index=False)
    for name, pr in per_row_scores.items():
        pr.to_parquet(out / ("per_row_%s.parquet" % name), index=False)

    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "dataset": args.dataset,
        "eval_split": args.eval_split,
        "n_train": int(len(train)), "n_eval": int(len(evald)),
        # THE POSITIVE RATE SAVED WITH THE RESULTS, so every AUPRC in this bundle can be read
        # against the base rate it should be judged by.
        "positive_rate_eval": float(y_ev.mean()),
        "n_arms": len(arms),
        # SUCCEEDED AND FAILED, both counted. The denominator is never hidden.
        "n_arms_ok": int((table["status"] == "OK").sum()),
        "n_arms_failed": int((table["status"] != "OK").sum()),
        "bootstrap_resamples": args.bootstrap,
        "environment": environment_snapshot(),
    }
    # `default=str` lets anything unusual (a date, say) be written as text rather than
    # crashing the save at the last step.
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                          encoding="utf-8")
    progress.log("wrote %s" % out)
    # A final table on screen, best first -- and it carries the confidence bounds beside every
    # score, so the ranking cannot be read without its uncertainty.
    print(merged_table.sort_values("auprc", ascending=False)
          [["arm", "status", "auprc", "auroc", "f1", "ece", "ci_low", "ci_high"]]
          .to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
