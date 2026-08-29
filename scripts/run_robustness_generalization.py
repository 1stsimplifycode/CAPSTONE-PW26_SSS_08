"""Execute the STATS-15 robustness and generalization harness.

    python scripts/run_robustness_generalization.py --all
    python scripts/run_robustness_generalization.py --stage period --stage instrument

Writes to ``outputs/stats/15_robustness_generalization/``. Nothing under
``research_artifacts/`` is touched, and the frozen holdout is never read: the harness
refuses to score a frame containing holdout rows.

PLAIN ENGLISH -- what this whole file is about:

THE "TRY TO BREAK IT" RUNNER.

Everything so far has asked "does the model work?" This asks the two harder questions:

ROBUSTNESS -- does it still work when things go WRONG? Damage the data on purpose. Add
noise. Switch whole categories of evidence off. Train it on far less data. Then measure how
much worse it gets.

GENERALIZATION -- does it work on things it has NEVER SEEN? Train on early months, test on
later ones. Train on one set of companies, test on completely different companies.

A model that only performs on the exact data it was built for is not useful. A model that
degrades gracefully when you break things is.

AND THE HOLDOUT IS NEVER TOUCHED. There is a slice of data locked away and never looked at,
saved for one final honest test. Every fit in this run passes through a guard that REFUSES,
loudly, if a single locked-away row sneaks in. Not "we were careful" -- a check that stops
the program.
"""
from __future__ import annotations

# argparse: reads the options typed after the command.
import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Find the project's top folder (two levels up from this file: scripts/ -> project) and put
# it at the front of the import search path, so `research.*` can be imported when this
# script is run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# `noqa: E402` on each of these: the style checker normally objects to imports below other
# code, but these MUST come after the path line above or they would not be found.
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.evaluation import robustness as rb  # noqa: E402

# Where the results go.
OUT = paths.REPO_ROOT / "outputs" / "stats" / "15_robustness_generalization"
# A fixed random seed, so "random" damage is the SAME random damage every time. Anybody can
# rerun this and get identical numbers.
SEED = 20260818

# The five ways the model is stress-tested, in order of increasing difficulty.
STAGES = ("input", "missingness", "training_size", "period", "instrument")


def main() -> int:
    # `description=__doc__` reuses the docstring above as the command's help text.
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    # `action="append"` lets --stage be given several times, collecting into a list.
    ap.add_argument("--stage", action="append", choices=list(STAGES))
    ap.add_argument("--dataset", default="market_dataset.parquet")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    # --all means every stage; otherwise whichever were named; otherwise just the first.
    stages = list(STAGES) if args.all else (args.stage or ["input"])

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    data = pd.read_parquet(paths.PANEL / args.dataset)
    # `working_set` returns ONLY train+validation -- the holdout is stripped here, before
    # anything else can see it.
    work = rb.working_set(data)
    # AND THE COUNT OF WHAT WAS LOCKED AWAY IS PRINTED, so the reader can see the frozen
    # rows exist and were left alone.
    progress.log("[stats-15] %d rows in train+validation, %d held frozen and untouched"
                 % (len(work), int((data["split"] == "holdout").sum())))

    # Two collections, because the two question types produce different tables.
    robustness_frames, generalization_frames = [], []
    summary: dict = {"seed": args.seed, "dataset": args.dataset,
                     "n_rows_used": int(len(work)),
                     # The frozen count recorded in the summary file too.
                     "n_rows_frozen_and_unused": int(
                         (data["split"] == "holdout").sum())}

    if "input" in stages:
        # THE CRUCIAL DETAIL, stated in the log line: the model is fitted ONCE on clean data,
        # and only the data it is TESTED on gets degraded. Retraining on the damaged data
        # would let the model adapt to the damage, which answers a different question.
        progress.log("[input] degrading the evaluation signal; "
                     "the model is fitted once on clean data")
        f = rb.input_robustness(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "missingness" in stages:
        # Switch off a whole category of evidence -- as if that data feed went dark.
        progress.log("[missingness] taking each block offline")
        f = rb.missingness_robustness(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "training_size" in stages:
        # How good is it with 10 companies? 20? 50? The curve shows whether more data would
        # still help, or whether it has flattened out.
        progress.log("[training size] symbol-level learning curve")
        f = rb.training_size_curve(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "period" in stages:
        # Train on the past, test on the future -- the direction time actually runs.
        progress.log("[period] expanding-window transfer forward in time")
        generalization_frames.append(rb.period_transfer(data, seed=args.seed,
                                                        log=progress.log))
    if "instrument" in stages:
        # "Disjoint" means ZERO overlap: entirely different companies.
        progress.log("[instrument] transfer to disjoint tickers")
        generalization_frames.append(rb.instrument_transfer(data, seed=args.seed,
                                                            log=progress.log))

    if robustness_frames:
        # Stack all the robustness tables into one and save it.
        table = pd.concat(robustness_frames, ignore_index=True)
        table.to_csv(OUT / "robustness.csv", index=False)
        summary["robustness_rows"] = int(len(table))
        # Find the WORST case: exclude the undamaged baseline, keep rows that actually have a
        # degradation number. `table.iloc[0:0]` is an empty table of the right shape, used
        # when the column is absent so the code below still works.
        worst = table[(table.get("corruption") != "none")
                      & table.get("degradation").notna()] \
            if "degradation" in table.columns else table.iloc[0:0]
        if len(worst):
            # `idxmax` finds the row with the largest degradation -- the worst beating the
            # model took. AND IT IS REPORTED PROMINENTLY, in the summary and the log. Not the
            # best result; the worst.
            w = worst.loc[worst["degradation"].idxmax()]
            summary["worst_degradation"] = {
                "family": w.get("family"), "corruption": w.get("corruption"),
                "target": w.get("target"), "severity": float(w.get("severity", 0.0)),
                "auprc": float(w.get("auprc", float("nan"))),
                "degradation": float(w.get("degradation", float("nan")))}
            progress.log("  worst degradation: %s %s at %.2f -> auprc %.4f (%+.4f)"
                         % (w.get("corruption"), w.get("target"),
                            w.get("severity", 0.0), w.get("auprc", float("nan")),
                            # Negated, so it prints as a minus sign -- a loss looks like a
                            # loss.
                            -w.get("degradation", 0.0)))

    if generalization_frames:
        table = pd.concat(generalization_frames, ignore_index=True)
        table.to_csv(OUT / "generalization.csv", index=False)
        summary["generalization_rows"] = int(len(table))
        # Only folds that actually completed.
        ok = table[table["status"] == "OK"] if "status" in table.columns else table
        for family, g in ok.groupby("family"):
            summary["%s_transfer" % family] = {
                # MEAN, MIN AND MAX -- not just the average. An average of 0.7 hides the
                # difference between "0.69 to 0.71 every time" and "0.2 on one fold and 0.95
                # on another". The spread is the finding.
                "n_folds": int(len(g)),
                "auprc_mean": float(g["auprc"].mean()),
                "auprc_min": float(g["auprc"].min()),
                "auprc_max": float(g["auprc"].max()),
            }
            progress.log("  %s transfer: %d folds, auprc %.4f (%.4f - %.4f)"
                         % (family, len(g), g["auprc"].mean(), g["auprc"].min(),
                            g["auprc"].max()))

    # Whether the model was ever tested on a genuinely different dataset.
    summary["dataset_transfer"] = rb.dataset_transfer_status()
    # AND A DECLARED NON-RESULT, written into the output file itself.
    # PLAIN ENGLISH: everything above breaks the data RANDOMLY. An attacker is not random --
    # they can see how the detector works and aim at its weakest point. Random damage tells
    # you nothing about that.
    # So rather than let "robust" quietly be read as "attack-proof", the file says NOT RUN,
    # and says what such an experiment would actually require.
    summary["adversarial_robustness"] = (
        "NOT RUN. Every corruption here is random. An adversarial claim needs a threat "
        "model and an attacker who sees the detector, which is a different experiment.")
    # The holdout promise, recorded in the artifact -- and it names the guard function, so
    # the claim is checkable in the code rather than merely asserted.
    summary["holdout_policy"] = (
        "The frozen holdout was neither read nor scored. assert_no_holdout() raises on "
        "any frame carrying holdout rows, and every fit in this run passed through it.")
    # WHEN, WHICH VERSION OF THE CODE, WHICH LIBRARY VERSIONS, HOW LONG. Everything needed to
    # reproduce this run exactly.
    summary.update({"run_at": datetime.now(UTC).isoformat(),
                    "git_commit": git_commit(),
                    "robustness_version": rb.ROBUSTNESS_VERSION,
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})
    jsonio.write(OUT / "run.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    # 0 means success, by long-standing convention.
    return 0


# Only runs when this file is executed directly, not when imported. `SystemExit` passes the
# return code out to the shell, so a script that calls this one can tell whether it worked.
if __name__ == "__main__":
    raise SystemExit(main())
