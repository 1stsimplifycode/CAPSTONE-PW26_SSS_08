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
"""
from __future__ import annotations

import concurrent.futures as cf
import os

import numpy as np
import pandas as pd

from research.evaluation import ablations as ab
from research.evaluation import experiment as ex
from research.statistics import tests as st

MULTISEED_VERSION = "multiseed-v1"

#: Default seed ladder. Fixed and declared rather than drawn, so a rerun reproduces the
#: same set exactly; the spacing is arbitrary and carries no meaning.
DEFAULT_SEEDS = (20260818, 20260819, 20260820, 20260821, 20260822,
                 20260823, 20260824, 20260825, 20260826, 20260827)

METRICS = ("auprc", "auroc", "f1", "brier", "ece")


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
            spec = ex.ExperimentSpec(
                experiment_id="multiseed",
                hypothesis=arm.hypothesis or ("arm %s across seeds" % arm.name),
                arm=arm.name, blocks=list(arm.blocks),
                combination_rule=arm.combiner, eval_split=eval_split, seed=int(seed),
                baseline="FULL", notes=[arm.note] if arm.note else [])
            res = ex.run(spec, ab.apply_arm(data, arm), write=False)
            if res.status != "OK":
                rows.append({"arm": arm.name, "seed": int(seed), "status": res.status,
                             "reason": res.failure_reason})
                continue
            rows.append({"arm": arm.name, "seed": int(seed), "status": "OK",
                         **{k: v for k, v in res.detection.items()
                            if isinstance(v, (int, float))}})
            per_row[(arm.name, int(seed))] = res.per_row
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
_WORKER_DATA: pd.DataFrame | None = None


def _worker_init(dataset_path: str, eval_split: str) -> None:
    global _WORKER_DATA
    _WORKER_DATA = pd.read_parquet(dataset_path)


def _worker_run(task: tuple) -> dict:
    """Fit one (arm, seed) and return only its metrics.

    Metrics only, deliberately: returning per-row score frames from several hundred tasks
    is gigabytes of pickling for data the aggregate never reads. The one run that needs
    per-row scores is redone in the parent.
    """
    arm_name, seed, eval_split = task
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
        return {"arm": arm_name, "seed": int(seed), "status": "FAILED",
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    if res.status != "OK":
        return {"arm": arm_name, "seed": int(seed), "status": res.status,
                "reason": res.failure_reason}
    return {"arm": arm_name, "seed": int(seed), "status": "OK",
            **{k: v for k, v in res.detection.items()
               if isinstance(v, (int, float))}}


def run_seeds_parallel(dataset_path: str, arms: list, seeds=DEFAULT_SEEDS,
                       eval_split: str = "validation", n_jobs: int = 0,
                       log=None) -> pd.DataFrame:
    """Same sweep as :func:`run_seeds`, spread over worker processes.

    Each (arm, seed) is independent, so this is a straight fan-out. A single fit takes
    fifteen to twenty seconds, and 8 arms across 10 seeds is 80 of them.
    """
    tasks = [(a.name, int(s), eval_split) for s in seeds for a in arms]
    workers = n_jobs or max(1, min(8, (os.cpu_count() or 2) - 1))
    if log:
        log("      %d fits across %d worker processes" % (len(tasks), workers))

    rows: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                initargs=(dataset_path, eval_split)) as pool:
        for i, row in enumerate(pool.map(_worker_run, tasks, chunksize=1), 1):
            rows.append(row)
            if log and i % 20 == 0:
                ok = [r for r in rows if r["status"] == "OK"]
                log("        %d/%d fits, %d OK, mean auprc %.4f"
                    % (i, len(tasks), len(ok),
                       float(np.mean([r.get("auprc", np.nan) for r in ok]))
                       if ok else np.nan))
    return pd.DataFrame(rows)


def aggregate(table: pd.DataFrame, metrics=METRICS) -> pd.DataFrame:
    """Mean, standard deviation, min, max and a 95% interval per arm and metric.

    The interval is the normal-approximation interval on the **mean over seeds**, so it
    narrows as seeds are added. It answers "where is this arm's expected performance", not
    "where would a single future run land"; the min and max columns are there because for
    the second question they are the honest summary.
    """
    ok = table[table["status"] == "OK"]
    out = []
    for arm, g in ok.groupby("arm"):
        for metric in metrics:
            if metric not in g.columns:
                continue
            v = pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy(float)
            if v.size == 0:
                continue
            sd = float(v.std(ddof=1)) if v.size > 1 else float("nan")
            se = sd / np.sqrt(v.size) if v.size > 1 else float("nan")
            out.append({
                "arm": arm, "metric": metric, "n_seeds": int(v.size),
                "mean": float(v.mean()), "sd": sd,
                "min": float(v.min()), "max": float(v.max()),
                "range": float(v.max() - v.min()),
                "ci_low": float(v.mean() - 1.96 * se) if v.size > 1 else float("nan"),
                "ci_high": float(v.mean() + 1.96 * se) if v.size > 1 else float("nan"),
            })
    return pd.DataFrame(out)


def paired_seed_tests(table: pd.DataFrame, reference: str = "FULL",
                      metric: str = "auprc", n_perm: int = 20000,
                      alpha: float = 0.05) -> pd.DataFrame:
    """Compare every arm against ``reference`` using seeds as the pairing unit.

    Pairing on seed removes the run-to-run variation that both arms share, which is the
    whole reason to pair. The p-values are then corrected across arms with
    Benjamini-Hochberg: this is one comparison per arm on one dataset, and reporting a
    dozen uncorrected p-values would manufacture a significant finding by volume.
    """
    ok = table[table["status"] == "OK"]
    if reference not in set(ok["arm"]):
        return pd.DataFrame([{"status": "NO REFERENCE ARM", "reference": reference}])

    ref = ok[ok["arm"] == reference].set_index("seed")[metric].astype(float)
    rows = []
    for arm, g in ok.groupby("arm"):
        if arm == reference:
            continue
        other = g.set_index("seed")[metric].astype(float)
        common = sorted(set(ref.index) & set(other.index))
        if len(common) < 3:
            rows.append({"arm": arm, "status": "INSUFFICIENT SEEDS",
                         "n_paired_seeds": len(common)})
            continue
        diff = (other.loc[common] - ref.loc[common]).to_numpy(float)
        res = st.paired_permutation(diff, n_perm=n_perm, seed=20260818)
        rows.append({
            "arm": arm, "status": "OK", "metric": metric,
            "n_paired_seeds": len(common),
            "mean_difference": float(diff.mean()),
            "sd_difference": float(diff.std(ddof=1)),
            "p_value": float(res.p_value),
            "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()),
        })

    frame = pd.DataFrame(rows)
    usable = frame[frame.get("status") == "OK"] if "status" in frame else frame
    if len(usable) and "p_value" in usable:
        bh = st.benjamini_hochberg(usable["p_value"].tolist(), alpha=alpha)
        bh.index = usable.index
        frame.loc[usable.index, "adjusted_p"] = bh["adjusted_p"]
        frame.loc[usable.index, "reject"] = bh["reject"]
    return frame


def seed_noise_floor(table: pd.DataFrame, metric: str = "auprc") -> dict:
    """How large a difference has to be before it can be read as signal.

    Defined as the pooled within-arm standard deviation across seeds. A reported gap
    smaller than this is inside the noise the pipeline generates on its own, whatever a
    single run showed.
    """
    ok = table[table["status"] == "OK"]
    sds = []
    for _arm, g in ok.groupby("arm"):
        v = pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy(float)
        if v.size > 1:
            sds.append(v.std(ddof=1))
    if not sds:
        return {"status": "INSUFFICIENT DATA"}
    pooled = float(np.sqrt(np.mean(np.square(sds))))
    return {
        "metric": metric,
        "pooled_seed_sd": pooled,
        "noise_floor_95": float(1.96 * pooled * np.sqrt(2)),
        "n_arms": int(ok["arm"].nunique()),
        "n_seeds": int(ok["seed"].nunique()),
        "interpretation": (
            "A difference between two arms smaller than the 95%% floor (%.4f %s) is "
            "within what re-seeding alone produces, and is reported as not established."
            % (float(1.96 * pooled * np.sqrt(2)), metric)),
    }


def within_run_intervals(per_row: dict, arms: list[str], seed: int,
                         n_boot: int = 600) -> pd.DataFrame:
    """Cluster bootstrap interval for each arm within one run, for contrast with seeds.

    Clustered on episode where one exists and on symbol otherwise: rows inside a single
    episode are not independent draws, and treating them as such narrows the interval to
    something the data does not support.
    """
    rows = []
    for arm in arms:
        frame = per_row.get((arm, int(seed)))
        if frame is None:
            continue
        pr = frame.copy()
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
                     "n_clusters": int(pr["cluster"].nunique()),
                     "note": res.test_description})
    return pd.DataFrame(rows)


def _auprc(frame: pd.DataFrame) -> float:
    from sklearn.metrics import average_precision_score
    y = frame["is_episode"].to_numpy(int)
    if y.min() == y.max():
        return float("nan")
    return float(average_precision_score(y, frame["integrity_risk"].to_numpy(float)))
