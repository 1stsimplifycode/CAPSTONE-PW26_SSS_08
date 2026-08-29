"""Multi-seed repetition and significance (STATS-16).

Every headline number in this project has so far been a single run. A single run cannot
distinguish "this arm is better" from "this arm drew a luckier seed", and with a learner
that has stochastic components the second is a live possibility at the effect sizes
involved here.

This module repeats the stochastic part of the pipeline across seeds and hands the
repeated measurements to the statistical machinery that already exists in
``research/statistics/`` -- ``cluster_bootstrap_ci``, ``paired_permutation`` and
``benjamini_hochberg``. Nothing new is invented here; what was missing was the driver that
produces repeated measurements for those functions to consume.

Two distinct sources of variation are kept separate, because conflating them is the usual
way a seed study overstates its own precision:

``across_seeds``  the spread of a metric over seeds, on one fixed evaluation set. This is
                  seed variance and nothing else.
``within_run``    the cluster bootstrap interval of a metric within one run. This is
                  sampling variance of the evaluation set.

An arm difference that is smaller than the seed spread is reported as **not established**,
whatever its single-run value looked like.

PLAIN ENGLISH -- what this whole file is about:

RUN IT AGAIN. AND AGAIN. AND AGAIN.

Here is the problem this file exists to solve, and it is the one that quietly ruins the
most research.

You run your experiment. Method A scores 0.82; method B scores 0.80. A wins!

But models contain randomness. Where the training starts, how the data is shuffled, which
rows land in which fold -- all of that is decided by a "seed". Change the seed and you get
slightly different numbers.

So the honest question is: WOULD A HAVE STILL WON WITH A DIFFERENT SEED?

If A scores between 0.79 and 0.85 depending on the seed, and B scores between 0.78 and
0.84, then your 0.82-versus-0.80 result is noise. You have discovered nothing. You have
simply reported one particular roll of the dice.

So this file runs everything TEN TIMES with ten different seeds, and looks at the spread.

TWO KINDS OF WOBBLE, kept carefully apart, because mixing them is the classic way a study
overstates how precise it is:
  ACROSS SEEDS -- "if I re-ran on the same data, how much would the answer move?"
  WITHIN RUN   -- "if I had tested on slightly different companies, how much would it
                  move?"
Both are real. They are different questions. Add them together carelessly and you get a
number that answers neither.

AND THE RULE THAT MAKES IT BITE, in the last line: any difference smaller than the seed
spread is reported as NOT ESTABLISHED -- however good the single run looked. That is a
commitment made in advance to throw away your own exciting-looking results when they turn
out to be dice rolls.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For running many jobs at once across several processor cores.
import concurrent.futures as cf
# For asking the operating system how many cores there are.
import os

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The experiment definitions.
from research.evaluation import ablations as ab
# The harness that runs one experiment.
from research.evaluation import experiment as ex
# The statistical machinery.
from research.statistics import tests as st

# A label for this version.
MULTISEED_VERSION = "multiseed-v1"

#: Default seed ladder. Fixed and declared rather than drawn, so a rerun reproduces the
#: same set exactly; the spacing is arbitrary and carries no meaning.
# PLAIN ENGLISH: ten seeds, WRITTEN DOWN rather than generated randomly. That matters: if
# the seeds themselves were random, two runs of the study would use different seeds and
# could not be compared. And the note that the spacing is meaningless heads off a reader
# wondering whether consecutive numbers are somehow significant. They are just dates.
DEFAULT_SEEDS = (20260818, 20260819, 20260820, 20260821, 20260822,
                 20260823, 20260824, 20260825, 20260826, 20260827)

# The measures tracked across seeds.
METRICS = ("auprc", "auroc", "f1", "brier", "ece")


# Run every experiment at every seed, one after another.
def run_seeds(data: pd.DataFrame, arms: list, seeds=DEFAULT_SEEDS,
              eval_split: str = "validation", log=None) -> tuple[pd.DataFrame, dict]:
    """Run every arm at every seed. Returns the long table and the per-row scores.

    The per-row scores are kept for the reference arm only at each seed, because that is
    what the paired tests need and holding every arm's per-row frame across ten seeds is
    a lot of memory for nothing.
    """
    rows: list[dict] = []
    per_row: dict[tuple[str, int], pd.DataFrame] = {}
    for seed in seeds:
        for arm in arms:
            # Build the full specification for this one run. Everything -- which evidence,
            # which combining rule, which seed -- is recorded, so any single run can be
            # reproduced exactly on its own.
            spec = ex.ExperimentSpec(
                experiment_id="multiseed",
                hypothesis=arm.hypothesis or ("arm %s across seeds" % arm.name),
                arm=arm.name, blocks=list(arm.blocks),
                combination_rule=arm.combiner, eval_split=eval_split, seed=int(seed),
                baseline="FULL", notes=[arm.note] if arm.note else [])
            # `write=False` -- do not save each of the 80+ individual runs to disk; only the
            # summary matters here.
            res = ex.run(spec, ab.apply_arm(data, arm), write=False)
            # A failed run is RECORDED with its reason, not skipped. A quietly missing row
            # would make an arm look untested rather than broken.
            if res.status != "OK":
                rows.append({"arm": arm.name, "seed": int(seed), "status": res.status,
                             "reason": res.failure_reason})
                continue
            rows.append({"arm": arm.name, "seed": int(seed), "status": "OK",
                         # `**{...}` unpacks the metrics into this row as separate columns.
                         # The isinstance filter keeps only actual numbers, so text fields
                         # do not end up in a numeric table.
                         **{k: v for k, v in res.detection.items()
                            if isinstance(v, (int, float))}})
            per_row[(arm.name, int(seed))] = res.per_row
        # Report progress after each seed, so a long sweep shows signs of life.
        if log:
            done = [r for r in rows if r["seed"] == int(seed) and r["status"] == "OK"]
            log("      seed %d: %d/%d arms OK, mean auprc %.4f"
                % (seed, len(done), len(arms),
                   float(np.mean([d.get("auprc", np.nan) for d in done]))
                   if done else np.nan))
    return pd.DataFrame(rows), per_row


# The pool worker loads the panel once per process rather than receiving it per task:
# the frame is 16k x 119 and there are hundreds of tasks, so pickling it each time would
# cost more than the fit.
# PLAIN ENGLISH: when work is shared across several processes, everything sent to a worker
# must be packed up and copied ("pickling"). This dataset is large. Sending it with each of
# several hundred tasks would cost far more time than the actual computing does. So each
# worker loads it ONCE, from disk, and keeps it. The `global` below is what lets it persist.
_WORKER_DATA: pd.DataFrame | None = None


# Run once when each worker process starts up.
def _worker_init(dataset_path: str, eval_split: str) -> None:
    global _WORKER_DATA
    _WORKER_DATA = pd.read_parquet(dataset_path)


# Do one (experiment, seed) job inside a worker.
def _worker_run(task: tuple) -> dict:
    """Fit one (arm, seed) and return only its metrics.

    Metrics only, deliberately: returning per-row score frames from several hundred tasks
    is gigabytes of pickling for data the aggregate never reads. The one run that needs
    per-row scores is redone in the parent.
    """
    # PLAIN ENGLISH: the same packing-cost reasoning, in the other direction. Sending back
    # every row's score from hundreds of jobs would be gigabytes of copying, for data the
    # summary never even looks at. So workers send back the handful of numbers that matter,
    # and the single run that genuinely needs the detail is simply redone at home.
    arm_name, seed, eval_split = task
    # Rebuild the experiment definitions inside the worker. Cheaper than sending them.
    arms = {a.name: a for a in ab.all_arms()}
    arm = arms[arm_name]
    spec = ex.ExperimentSpec(
        experiment_id="multiseed",
        hypothesis=arm.hypothesis or ("arm %s across seeds" % arm.name),
        arm=arm.name, blocks=list(arm.blocks), combination_rule=arm.combiner,
        eval_split=eval_split, seed=int(seed), baseline="FULL",
        notes=[arm.note] if arm.note else [])
    try:
        res = ex.run(spec, ab.apply_arm(_WORKER_DATA, arm), write=False)
    except Exception as exc:  # noqa: BLE001 - one arm must not take out the sweep
        # PLAIN ENGLISH: the comment explains why a deliberately broad catch is right here.
        # If one job out of eighty crashes, we want the other seventy-nine, plus a record of
        # what went wrong. Letting the crash escape would waste hours of finished work.
        return {"arm": arm_name, "seed": int(seed), "status": "FAILED",
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    if res.status != "OK":
        return {"arm": arm_name, "seed": int(seed), "status": res.status,
                "reason": res.failure_reason}
    return {"arm": arm_name, "seed": int(seed), "status": "OK",
            **{k: v for k, v in res.detection.items()
               if isinstance(v, (int, float))}}


# The same sweep, spread across processor cores.
def run_seeds_parallel(dataset_path: str, arms: list, seeds=DEFAULT_SEEDS,
                       eval_split: str = "validation", n_jobs: int = 0,
                       log=None) -> pd.DataFrame:
    """Same sweep as :func:`run_seeds`, spread over worker processes.

    Each (arm, seed) is independent, so this is a straight fan-out. A single fit takes
    fifteen to twenty seconds, and 8 arms across 10 seeds is 80 of them.
    """
    # PLAIN ENGLISH: eighty jobs at twenty seconds each is about half an hour one at a time.
    # Because no job depends on any other, they can all run at once across the computer's
    # cores -- which is what "a straight fan-out" means, and it is the easy case.
    tasks = [(a.name, int(s), eval_split) for s in seeds for a in arms]
    # How many workers. `(cores - 1)` deliberately leaves one core free so the machine stays
    # usable; capped at 8 so a very large machine does not thrash on memory.
    workers = n_jobs or max(1, min(8, (os.cpu_count() or 2) - 1))
    if log:
        log("      %d fits across %d worker processes" % (len(tasks), workers))

    rows: list[dict] = []
    # Start the pool, telling each new process to load the data first.
    with cf.ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                initargs=(dataset_path, eval_split)) as pool:
        # `pool.map` hands out the jobs and yields results as they finish. `enumerate(..., 1)`
        # numbers them from 1 for the progress message.
        for i, row in enumerate(pool.map(_worker_run, tasks, chunksize=1), 1):
            rows.append(row)
            # A progress report every 20 jobs.
            if log and i % 20 == 0:
                ok = [r for r in rows if r["status"] == "OK"]
                log("        %d/%d fits, %d OK, mean auprc %.4f"
                    % (i, len(tasks), len(ok),
                       float(np.mean([r.get("auprc", np.nan) for r in ok]))
                       if ok else np.nan))
    return pd.DataFrame(rows)


# Summarise each experiment across its seeds.
def aggregate(table: pd.DataFrame, metrics=METRICS) -> pd.DataFrame:
    """Mean, standard deviation, min, max and a 95% interval per arm and metric.

    The interval is the normal-approximation interval on the **mean over seeds**, so it
    narrows as seeds are added. It answers "where is this arm's expected performance", not
    "where would a single future run land"; the min and max columns are there because for
    the second question they are the honest summary.
    """
    # PLAIN ENGLISH: a distinction that trips up almost everybody, explained properly.
    # The interval answers "where is this method's TRUE AVERAGE?" -- and it gets narrower the
    # more seeds you add, because you are pinning down that average more precisely.
    # It does NOT answer "if I run this once more, where will I land?" -- which is a much
    # wider range and does not shrink at all with more seeds.
    # People routinely quote the first and mean the second. So the min and max are reported
    # alongside, because for the second question they are the honest answer.
    ok = table[table["status"] == "OK"]
    out = []
    for arm, g in ok.groupby("arm"):
        for metric in metrics:
            if metric not in g.columns:
                continue
            # `errors="coerce"` turns anything unparseable into "unknown" instead of crashing.
            v = pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy(float)
            if v.size == 0:
                continue
            # The spread across seeds. Undefined with only one seed -- honestly so.
            sd = float(v.std(ddof=1)) if v.size > 1 else float("nan")
            # The standard error: how precisely we have pinned down the average. Note it is
            # the spread divided by the square root of the count, which is exactly why more
            # seeds narrow the interval.
            se = sd / np.sqrt(v.size) if v.size > 1 else float("nan")
            out.append({
                "arm": arm, "metric": metric, "n_seeds": int(v.size),
                "mean": float(v.mean()), "sd": sd,
                # THE HONEST RANGE: the best and worst single runs actually seen.
                "min": float(v.min()), "max": float(v.max()),
                "range": float(v.max() - v.min()),
                # And the interval on the average. 1.96 is the standard 95% multiplier.
                "ci_low": float(v.mean() - 1.96 * se) if v.size > 1 else float("nan"),
                "ci_high": float(v.mean() + 1.96 * se) if v.size > 1 else float("nan"),
            })
    return pd.DataFrame(out)


# Compare each experiment against the reference, using seeds as matched pairs.
def paired_seed_tests(table: pd.DataFrame, reference: str = "FULL",
                      metric: str = "auprc", n_perm: int = 20000,
                      alpha: float = 0.05) -> pd.DataFrame:
    """Compare every arm against ``reference`` using seeds as the pairing unit.

    Pairing on seed removes the run-to-run variation that both arms share, which is the
    whole reason to pair. The p-values are then corrected across arms with
    Benjamini-Hochberg: this is one comparison per arm on one dataset, and reporting a
    dozen uncorrected p-values would manufacture a significant finding by volume.
    """
    # PLAIN ENGLISH: two ideas at once.
    # PAIRING: compare A and B on seed 1, then on seed 2, and so on. If seed 3 happens to be
    # an awkward one, it makes BOTH look bad, and the difference between them is unaffected.
    # That shared difficulty cancels out, which is what makes a paired comparison so much
    # more sensitive than an unpaired one.
    # CORRECTION: with a dozen arms tested at the usual 5% bar, you would expect roughly one
    # false "discovery" from pure chance even if nothing were real. Correcting across the
    # whole family is what stops a finding being manufactured purely by volume of testing.
    ok = table[table["status"] == "OK"]
    if reference not in set(ok["arm"]):
        return pd.DataFrame([{"status": "NO REFERENCE ARM", "reference": reference}])

    # The reference's score at each seed, indexed by seed so it can be lined up exactly.
    ref = ok[ok["arm"] == reference].set_index("seed")[metric].astype(float)
    rows = []
    for arm, g in ok.groupby("arm"):
        # No point comparing the reference with itself.
        if arm == reference:
            continue
        other = g.set_index("seed")[metric].astype(float)
        # Only seeds where BOTH succeeded -- pairing requires both halves of the pair.
        common = sorted(set(ref.index) & set(other.index))
        # Fewer than three pairs: no meaningful test. Say so rather than report a p-value
        # computed from two points.
        if len(common) < 3:
            rows.append({"arm": arm, "status": "INSUFFICIENT SEEDS",
                         "n_paired_seeds": len(common)})
            continue
        # The difference, seed by seed.
        diff = (other.loc[common] - ref.loc[common]).to_numpy(float)
        # The sign-flip test: if the two are really identical, flipping the signs at random
        # should not matter.
        res = st.paired_permutation(diff, n_perm=n_perm, seed=20260818)
        rows.append({
            "arm": arm, "status": "OK", "metric": metric,
            "n_paired_seeds": len(common),
            "mean_difference": float(diff.mean()),
            "sd_difference": float(diff.std(ddof=1)),
            "p_value": float(res.p_value),
            # WINS AND LOSSES: on how many seeds did each side come out ahead? A wonderfully
            # direct sanity check -- "better on average" while losing 4 seeds out of 10 is a
            # very different story from winning all 10, and the averages alone look the same.
            "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()),
        })

    frame = pd.DataFrame(rows)
    usable = frame[frame.get("status") == "OK"] if "status" in frame else frame
    if len(usable) and "p_value" in usable:
        # Apply the multiple-comparisons correction across the whole family of tests.
        bh = st.benjamini_hochberg(usable["p_value"].tolist(), alpha=alpha)
        bh.index = usable.index
        # Both the corrected value and the verdict are added, and the raw p-value is kept
        # too -- so a reader can see exactly how much the correction changed things.
        frame.loc[usable.index, "adjusted_p"] = bh["adjusted_p"]
        frame.loc[usable.index, "reject"] = bh["reject"]
    return frame


# How big must a difference be before it means anything at all?
def seed_noise_floor(table: pd.DataFrame, metric: str = "auprc") -> dict:
    """How large a difference has to be before it can be read as signal.

    Defined as the pooled within-arm standard deviation across seeds. A reported gap
    smaller than this is inside the noise the pipeline generates on its own, whatever a
    single run showed.
    """
    # PLAIN ENGLISH: the single most useful number in this entire file.
    # Take one method and run it ten times, changing nothing but the seed. The results still
    # wobble by, say, 0.015. That wobble is pure noise the pipeline makes all by itself.
    # It follows that ANY difference between two methods smaller than about that much is
    # meaningless. Publishing this number lets a reader apply that test to every single
    # comparison in the paper themselves.
    ok = table[table["status"] == "OK"]
    sds = []
    for _arm, g in ok.groupby("arm"):
        v = pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy(float)
        if v.size > 1:
            sds.append(v.std(ddof=1))
    if not sds:
        return {"status": "INSUFFICIENT DATA"}
    # Pool the spreads across arms. Averaging the SQUARES and then taking the root is the
    # statistically correct way to combine spreads -- averaging them directly would
    # understate the result.
    pooled = float(np.sqrt(np.mean(np.square(sds))))
    return {
        "metric": metric,
        "pooled_seed_sd": pooled,
        # The 95% floor. The `sqrt(2)` is there because a DIFFERENCE between two methods
        # carries the noise of BOTH, so its wobble is larger than either one's alone.
        "noise_floor_95": float(1.96 * pooled * np.sqrt(2)),
        "n_arms": int(ok["arm"].nunique()),
        "n_seeds": int(ok["seed"].nunique()),
        # And the rule spelled out with the actual number in it, carried in the output so it
        # reaches whoever reads the results rather than only whoever reads the code.
        "interpretation": (
            "A difference between two arms smaller than the 95%% floor (%.4f %s) is "
            "within what re-seeding alone produces, and is reported as not established."
            % (float(1.96 * pooled * np.sqrt(2)), metric)),
    }


# The OTHER kind of wobble: how much would a different test set have changed things?
def within_run_intervals(per_row: dict, arms: list[str], seed: int,
                         n_boot: int = 600) -> pd.DataFrame:
    """Cluster bootstrap interval for each arm within one run, for contrast with seeds.

    Clustered on episode where one exists and on symbol otherwise: rows inside a single
    episode are not independent draws, and treating them as such narrows the interval to
    something the data does not support.
    """
    # PLAIN ENGLISH: the dependence rule again. Forty days of one episode are one piece of
    # evidence observed forty times, not forty independent pieces. Shuffling whole episodes
    # rather than individual days is what keeps the interval honest.
    rows = []
    for arm in arms:
        frame = per_row.get((arm, int(seed)))
        if frame is None:
            continue
        pr = frame.copy()
        # Build the grouping label. If the row belongs to an episode, group by company AND
        # episode; otherwise fall back to grouping by company alone. That fallback matters --
        # ordinary calm days are still not independent of each other within one company.
        pr["cluster"] = np.where(pr["episode_id"].astype(str) != "",
                                 pr["symbol"].astype(str) + "|"
                                 + pr["episode_id"].astype(str),
                                 pr["symbol"].astype(str))
        res = st.cluster_bootstrap_ci(pr, _auprc, cluster_col="cluster", b=n_boot,
                                      seed=20260818)
        rows.append({"arm": arm, "seed": int(seed), "statistic": "auprc",
                     "point": float(res.statistic),
                     "ci_low": None if res.ci_low is None else float(res.ci_low),
                     "ci_high": None if res.ci_high is None else float(res.ci_high),
                     # How many independent groups the interval really rests on -- often far
                     # fewer than the row count, and the number that governs how much the
                     # interval can be trusted.
                     "n_clusters": int(pr["cluster"].nunique()),
                     # And the method's own description of what it did.
                     "note": res.test_description})
    return pd.DataFrame(rows)


# The scoring function handed to the bootstrap above.
def _auprc(frame: pd.DataFrame) -> float:
    from sklearn.metrics import average_precision_score
    y = frame["is_episode"].to_numpy(int)
    # A resample containing only one kind of answer cannot be scored. Report unknown; the
    # bootstrap machinery skips those and reports how many were usable.
    if y.min() == y.max():
        return float("nan")
    return float(average_precision_score(y, frame["integrity_risk"].to_numpy(float)))
