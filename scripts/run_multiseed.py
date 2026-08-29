"""Execute the STATS-16 multi-seed and significance harness.

    python scripts/run_multiseed.py --seeds 10
    python scripts/run_multiseed.py --seeds 5 --jobs 4

Repeats every ablation arm across seeds, then applies the existing cluster bootstrap,
paired permutation, Benjamini-Hochberg correction and power analysis to the repeated
measurements. Writes to ``outputs/stats/16_multiseed_significance/``; nothing under
``research_artifacts/`` is touched.

The evaluation split is ``validation``. The frozen holdout is not used for seed variance
either: repeating a measurement on the holdout ten times is ten looks at the data it was
frozen to protect.

PLAIN ENGLISH -- what this whole file is about:

THE "WAS THAT DIFFERENCE REAL, OR JUST LUCK?" RUNNER.

Machine learning has randomness inside it. Start the same model with a different random
starting point -- a different SEED -- and you get a slightly different answer. Same data,
same code, different number.

So imagine you run two versions and one scores 0.712 while the other scores 0.708. Is the
first genuinely better? Or would rerunning both with different seeds flip the ordering?

THIS FILE ANSWERS THAT by running everything TEN TIMES with ten different seeds. Then it
measures how much the answers wobble on their own. That wobble is the NOISE FLOOR: any
difference smaller than it is not a finding, it is the dice.

AND THE BEST DECISION IN THE FILE: differences that survive AND differences that dissolve
are BOTH written into the output, under headings that say which is which. The easy thing is
to keep the survivors and quietly drop the rest. This keeps them "so the ones that dissolve
stay visible."

THE HOLDOUT ARGUMENT IS SUBTLE AND WORTH FOLLOWING. You might think "we are just measuring
noise, so peeking at the locked data is harmless." It is not: running ten seeds against the
holdout is TEN LOOKS at the data whose whole value is that nobody has looked. Ten looks with
an innocent motive still spend it.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Make the project importable when this script is run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.evaluation import ablations as ab  # noqa: E402
from research.evaluation import multiseed as ms  # noqa: E402
from research.statistics import power as pw  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="market_dataset.parquet")
    # Ten repeats by default.
    ap.add_argument("--seeds", type=int, default=10)
    # How many to run at once. 0 lets the machinery decide.
    ap.add_argument("--jobs", type=int, default=0)
    # AUPRC rather than AUROC -- the right measure when the thing being looked for is rare.
    ap.add_argument("--metric", default="auprc")
    # FULL: everything switched on. Every other version is compared against it.
    ap.add_argument("--reference", default="FULL")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    # The seeds come from a FIXED published list, sliced to the number asked for. So "seeds 5"
    # always means the same five, and results are reproducible.
    seeds = list(ms.DEFAULT_SEEDS)[:args.seeds]
    arms = ab.all_arms()
    dataset_path = str(paths.PANEL / args.dataset)
    data = pd.read_parquet(dataset_path)
    # Arms x seeds = the total number of fits. 12 arms and 10 seeds is 120 model trainings.
    progress.log("[stats-16] %d arms x %d seeds on %d validation rows"
                 % (len(arms), len(seeds),
                    # VALIDATION rows only. The holdout is not counted because it is not used.
                    int((data["split"] == "validation").sum())))

    # Run them all, several at a time where possible.
    table = ms.run_seeds_parallel(dataset_path, arms, seeds=seeds,
                                  n_jobs=args.jobs, log=progress.log)
    table.to_csv(OUT / "seed_table.csv", index=False)
    # HOW MANY ACTUALLY WORKED, out of how many were attempted. Failures are counted rather
    # than dropped -- "9 of 120 succeeded" would be visible here.
    n_ok = int((table["status"] == "OK").sum())
    progress.log("  %d/%d fits succeeded" % (n_ok, len(table)))

    # Collapse the repeats into one row per arm: average, spread, best, worst.
    agg = ms.aggregate(table)
    agg.to_csv(OUT / "seed_summary.csv", index=False)
    focus = agg[agg["metric"] == args.metric].sort_values("mean", ascending=False)
    for _, r in focus.head(6).iterrows():
        # THE FORMAT IS THE ARGUMENT. Never the average alone: mean +/- spread, then the
        # actual best and worst, then the range. A reader can see immediately whether an arm
        # scoring 0.71 ever scored 0.55.
        progress.log("    %-24s %s %.4f +/- %.4f  [%.4f, %.4f]  range %.4f"
                     % (r["arm"], args.metric, r["mean"], r["sd"], r["min"], r["max"],
                        r["range"]))

    # Compare each arm against FULL, seed by seed, on the same seeds -- a PAIRED test, which
    # cancels out the luck the two shared.
    tests = ms.paired_seed_tests(table, reference=args.reference, metric=args.metric)
    tests.to_csv(OUT / "paired_tests.csv", index=False)
    # THE NOISE FLOOR. How far apart two numbers can be purely by chance. Anything closer
    # than this is not a difference.
    floor = ms.seed_noise_floor(table, metric=args.metric)
    # `%%` prints a literal percent sign, since `%` is the formatting character.
    progress.log("  pooled seed sd %.5f; 95%% noise floor %.5f %s"
                 % (floor.get("pooled_seed_sd", float("nan")),
                    floor.get("noise_floor_95", float("nan")), args.metric))

    # Which single-run differences survive seed variance, and which do not.
    # PLAIN ENGLISH: two lists, and both get saved. The ones that hold up, and the ones that
    # turn out to have been noise all along.
    survives, dissolves = [], []
    if "mean_difference" in tests.columns:
        for _, r in tests[tests.get("status") == "OK"].iterrows():
            item = {"arm": r["arm"],
                    "mean_difference": float(r["mean_difference"]),
                    "p_value": float(r["p_value"]),
                    # The p-value AFTER correcting for having run many comparisons -- test
                    # twelve things and one will look impressive by luck alone.
                    "adjusted_p": (None if pd.isna(r.get("adjusted_p"))
                                   else float(r.get("adjusted_p"))),
                    # AND THE DIFFERENCE MEASURED AGAINST THE NOISE FLOOR. Negative means the
                    # difference is smaller than the pipeline's own random wobble.
                    "abs_difference_vs_noise_floor":
                        float(abs(r["mean_difference"])
                              - floor.get("noise_floor_95", float("nan")))}
            # A compact way to append to one list or the other depending on the verdict.
            (survives if bool(r.get("reject")) else dissolves).append(item)
    progress.log("  %d of %d arm differences survive BH correction at 0.05"
                 % (len(survives), len(survives) + len(dissolves)))

    # Within-run sampling variance for one seed, to contrast with the seed spread.
    # PLAIN ENGLISH: TWO DIFFERENT KINDS OF WOBBLE, and confusing them is a classic error.
    # ACROSS SEEDS: rerun the same thing and get a different answer.
    # WITHIN ONE RUN: how much the answer depends on which particular episodes landed in the
    # sample.
    # Both must be smaller than a difference for that difference to mean anything.
    within = pd.DataFrame()
    try:
        top = list(focus["arm"].head(4)) + [args.reference]
        _t, per_row = ms.run_seeds(data, [a for a in arms if a.name in set(top)],
                                   seeds=[seeds[0]], log=None)
        within = ms.within_run_intervals(per_row, sorted(set(top)), seeds[0])
        within.to_csv(OUT / "within_run_intervals.csv", index=False)
    except Exception as exc:  # noqa: BLE001
        # If this optional extra fails, SAY SO with the actual error and carry on. The main
        # result is not lost to a failure in a supplementary calculation.
        progress.log("  within-run intervals skipped: %s: %s"
                     % (type(exc).__name__, exc))

    # Minimum detectable effect, from the machinery that already exists.
    # PLAIN ENGLISH: the MDE turns a failure into information. "We found no difference" is
    # nearly useless on its own -- no difference big enough to see, or no difference at all?
    # The MDE answers it: with this much data, the smallest difference we COULD have detected
    # is X. Anything smaller was never findable here, whether or not it exists.
    mde = {}
    try:
        ref_rows = per_row.get((args.reference, seeds[0]))
        # The best-scoring arm that is not the reference itself.
        alt_name = next((a for a in focus["arm"] if a != args.reference), None)
        alt_rows = per_row.get((alt_name, seeds[0])) if alt_name else None
        if ref_rows is not None and alt_rows is not None:
            paired = ref_rows[["symbol", "episode_id", "is_episode"]].copy()
            paired["a"] = ref_rows["integrity_risk"].to_numpy()
            paired["b"] = alt_rows["integrity_risk"].to_numpy()
            # THE CLUSTER KEY, and this is the statistically important line.
            # Rows from the same episode are not independent -- they are the same event seen
            # on consecutive days. Treating them as independent would inflate the sample size
            # and make everything look far more significant than it is.
            # So rows inside an episode are grouped as "symbol|episode", and rows belonging to
            # no episode are grouped by symbol alone.
            paired["cluster"] = np.where(
                paired["episode_id"].astype(str) != "",
                paired["symbol"].astype(str) + "|"
                + paired["episode_id"].astype(str),
                paired["symbol"].astype(str))
            mde = pw.minimum_detectable_effect(paired, "cluster", "a", "b")
            mde["compared"] = "%s vs %s" % (args.reference, alt_name)
    except Exception as exc:  # noqa: BLE001
        # NOT SILENTLY OMITTED. If it could not be computed, the artifact carries
        # "NOT COMPUTED" and the exact reason -- so an absent MDE is never mistaken for an
        # MDE of zero.
        mde = {"status": "NOT COMPUTED", "reason": "%s: %s" % (type(exc).__name__, exc)}

    summary = {
        "n_arms": len(arms), "n_seeds": len(seeds), "seeds": seeds,
        "metric": args.metric, "reference_arm": args.reference,
        "n_fits": int(len(table)), "n_fits_ok": n_ok,
        "seed_noise_floor": floor,
        # BOTH LISTS, side by side, under names that say plainly what each contains.
        "differences_surviving_correction": survives,
        "differences_within_seed_noise": dissolves,
        "within_run_intervals": within.to_dict(orient="records") if len(within) else [],
        "minimum_detectable_effect": mde,
        "interpretation": (
            # THE PARAGRAPH THE WHOLE FILE EXISTS FOR, and its middle sentence is the one to
            # remember: a difference smaller than the noise floor "is not evidence that one
            # arm is better; it is evidence that the pipeline is stochastic."
            # It also admits, in the first sentence, that everything reported before this was
            # a single run -- correcting the project's own earlier work in its own output.
            "Every previously reported arm difference was a single run. A difference "
            "smaller than the seed noise floor above is not evidence that one arm is "
            "better; it is evidence that the pipeline is stochastic. Differences are "
            "reported both ways rather than filtered, so the ones that dissolve stay "
            "visible."),
        "holdout_policy": (
            "Validation only. Repeating a measurement on the frozen holdout across ten "
            "seeds would be ten looks at the data the freeze exists to protect."),
        # Everything needed to reproduce this exact run.
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "multiseed_version": ms.MULTISEED_VERSION,
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "significance.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
