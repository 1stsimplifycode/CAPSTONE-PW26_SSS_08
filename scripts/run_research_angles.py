"""Execute the experiment specifications that need no external data.

    python scripts/run_research_angles.py

The limitations registry marks seven specifications as runnable now. Those are
obligations, not ideas: a research angle whose data is already on disk and which has not
been run is just an unexecuted experiment. This script runs them and writes results into
the registry's result slots.

Everything blocked by external data stays blocked and is reported as such. Nothing here
fabricates a result for an experiment it cannot run.

PLAIN ENGLISH -- what this whole file is about:

DOING THE EXPERIMENTS THERE IS NO EXCUSE NOT TO DO.

The limitations registry lists every gap in the project, and for each one, the experiment
that would close it. Some of those experiments need data nobody has -- real regulator
records, order-book feeds. Those are genuinely blocked.

BUT SEVEN OF THEM NEED NOTHING THAT IS NOT ALREADY ON DISK. And the docstring's sentence
about them is the sharpest in the file:

    "Those are obligations, not ideas: a research angle whose data is already on disk and
     which has not been run is just an unexecuted experiment."

In other words -- you do not get to list an experiment as "future work" when you could run
it this afternoon. Writing the design down and leaving it unrun looks like rigour; it is
avoidance. So this script runs all seven.

AND THE LAST LINE holds the line for the rest: the genuinely blocked ones STAY blocked, and
nothing here invents a result for an experiment it cannot run.

THE SEVEN QUESTIONS, roughly:
  N03 - does the model see anything BEFORE the event, or only during it?
  L10 - is the model badly calibrated exactly when evidence is missing?
  N04 - does the uncertainty-aware version actually help?
  L12 - how big would a difference have to be for us to detect it at all?
  L04 - which kinds of episode does it catch, and which does it miss?
  N02 - is the regime block redundant, or just starved of data?
  N01 - can LIME be made stable, and what would that cost?
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import jsonio, paths, progress
from research.core.manifest import environment_snapshot
from research.data import dataset as ds
from research.evaluation import information as info
from research.evaluation import temporal_analysis as ta
from research.limitations import registry as reg
from research.statistics import power as pw
from research.xai import methods as xm
from research.xai import sanity as xs

OUT = paths.ARTIFACTS / "research_angles"
EXP_DIR = paths.ARTIFACTS / "experiments"

# The four kinds of evidence the system combines.
BLOCKS = ["market", "microstructure", "regime", "propagation"]

#: (block -> (only-arm, without-arm)) for the information decomposition.
# PLAIN ENGLISH: to work out what one kind of evidence contributes, you need two experiments:
# one with ONLY that evidence, and one with everything EXCEPT it.
# If "only" scores well, the block carries real signal.
# If removing it changes nothing, it was telling you what the others already had.
BLOCK_ARMS = {
    "market": ("MARKET_ONLY", "NO_MARKET"),
    "microstructure": ("MICRO_ONLY", "NO_MICROSTRUCTURE"),
    "regime": ("REGIME_ONLY", "NO_REGIME"),
    "propagation": ("PROPAGATION_ONLY", "NO_PROPAGATION"),
}

# Filled in as each experiment finishes.
results: dict[str, dict] = {}


def _load_arms() -> dict[str, pd.DataFrame]:
    arms = {}
    # Read whatever score files exist, keyed by arm name. Nothing is assumed to be present --
    # each experiment below checks for what it needs.
    for p in sorted(EXP_DIR.glob("per_row_*.parquet")):
        arms[p.stem.replace("per_row_", "")] = pd.read_parquet(p)
    return arms


def _cluster(df: pd.DataFrame) -> pd.Series:
    # THE CLUSTERING RULE, defined once and used by every test in the file.
    # Rows in the same episode belong together; rows in no episode group by company.
    # See run_experiments.py for the full explanation of why this matters so much.
    return np.where(df["episode_id"].astype(str) != "",
                    df["episode_id"].astype(str),
                    "sym_" + df["symbol"].astype(str))


# -- EXP-N03-1: lead-time / precision frontier and block lead-lag --------------------

def exp_n03(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION: does the model spot anything BEFORE the episode, or only once it is
    # already obvious? A detector that fires on day three of a five-day event is describing
    # the present, not warning about the future.
    full = arms["FULL"]
    # THE FRONTIER: every possible alarm threshold, and the trade-off it buys. A low bar
    # gives more warning time but more false alarms. A high bar is precise but late.
    frontier = ta.lead_time_frontier(full)
    frontier.to_csv(OUT / "exp_n03_lead_time_frontier.csv", index=False)

    # Which kind of evidence moves FIRST -- does microstructure stir before price does?
    lead_lag = ta.block_lead_lag(full, BLOCKS)
    curves = {r["block"]: {"lags": r.get("_curve_lags"),
                              "values": r.get("_curve_values")}
              for _, r in lead_lag.iterrows() if r.get("status") == "OK"}
    jsonio.write(OUT / "exp_n03_lead_lag_curves.json", curves, indent=1)
    # Columns starting with "_" are the bulky internals, saved to the JSON above and dropped
    # from the readable CSV.
    lead_lag.drop(columns=[c for c in lead_lag.columns if c.startswith("_")]) \
        .to_csv(OUT / "exp_n03_block_lead_lag.csv", index=False)

    # How the score behaves at the start, the peak and the end of an episode.
    lifecycle = ta.onset_peak_resolution_scores(full)
    jsonio.write(OUT / "exp_n03_lifecycle.json", lifecycle)

    ok = frontier[frontier.get("status") == "OK"] if "status" in frontier else frontier
    # POSITIVE lead time means the alarm came BEFORE the episode. That is the whole question.
    positive = ok[ok["median_lead_time"] > 0] if len(ok) else ok
    best_positive = None
    if len(positive):
        # The most precise of the operating points that genuinely warn in advance.
        row = positive.sort_values("window_precision", ascending=False).iloc[0]
        best_positive = {"entry_threshold": float(row["entry_threshold"]),
                         "median_lead_time": float(row["median_lead_time"]),
                         "window_precision": float(row["window_precision"]),
                         "detection_rate": float(row["detection_rate"])}
    return {
        "experiment": "EXP-N03-1",
        "status": "MEASURED",
        "n_thresholds": int(len(ok)),
        # A PLAIN YES/NO to the question that matters -- and it can legitimately be False.
        "any_positive_lead_operating_point": best_positive is not None,
        "best_positive_lead_point": best_positive,
        # THE FULL RANGE, not just the best point. So a reader can see the whole trade-off
        # curve rather than the single most flattering spot on it.
        "frontier_range": {
            "median_lead_time_min": float(ok["median_lead_time"].min()) if len(ok)
            else None,
            "median_lead_time_max": float(ok["median_lead_time"].max()) if len(ok)
            else None,
            "window_precision_min": float(ok["window_precision"].min()) if len(ok)
            else None,
            "window_precision_max": float(ok["window_precision"].max()) if len(ok)
            else None,
        },
        "block_lead_lag": lead_lag.drop(
            columns=[c for c in lead_lag.columns if c.startswith("_")]
        ).to_dict(orient="records"),
        "lifecycle": lifecycle,
    }


# -- EXP-L10-1: calibration under coverage and disagreement ----------------------------

def exp_l10(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION: CALIBRATION means "when the model says 70%, is it right about 70% of the
    # time?" A model can rank things beautifully and still be wildly overconfident.
    # This asks whether calibration falls apart exactly where evidence is thin -- which is
    # where a user most needs to be able to trust the number.
    full = arms["FULL"].copy()
    by_cov = info.calibration_by_bucket(full, "coverage")
    by_unc = info.calibration_by_bucket(full, "uncertainty")
    by_cov.to_csv(OUT / "exp_l10_calibration_by_coverage.csv", index=False)
    by_unc.to_csv(OUT / "exp_l10_calibration_by_uncertainty.csv", index=False)

    def _trend(d: pd.DataFrame) -> float | None:
        """Slope of ECE against the bucket midpoint, or None when unmeasurable.

        Returning None matters: `coverage` takes only five distinct values in this
        dataset, so a fitted slope there would describe the binning rather than the
        data."""
        # PLAIN ENGLISH: a beautiful piece of restraint. You CAN fit a line through five
        # points and get a number. But with only five distinct values, that line describes
        # how the buckets were drawn, not anything about the data.
        # So the function returns None -- "this is not measurable here" -- rather than a
        # number that would be reported, quoted and believed.
        ok = d[d["status"] == "OK"] if "status" in d.columns else d
        ok = ok.dropna(subset=["ece"])
        # Fewer than three points: no trend.
        if len(ok) < 3:
            return None
        x = ((ok["bucket_low"] + ok["bucket_high"]) / 2).to_numpy(float)
        # AND FEWER THAN THREE DISTINCT x VALUES: still no trend, even if there are many rows.
        if len(np.unique(x)) < 3:
            return None
        # `polyfit(..., 1)` fits a straight line; `[0]` is its slope.
        return float(np.polyfit(x, ok["ece"].to_numpy(float), 1)[0])

    return {
        "experiment": "EXP-L10-1",
        "status": "MEASURED",
        "ece_slope_vs_coverage": _trend(by_cov),
        # AN EXPLICIT FLAG for whether this half of the question could be answered at all.
        "coverage_measurable": _trend(by_cov) is not None,
        "coverage_note": (
            # NOT MEASURABLE, in capitals, with the reason AND the condition under which it
            # would become measurable. A gap in the evidence, described precisely enough that
            # somebody could close it.
            "Coverage takes only five distinct values on this dataset (median 1.0), so "
            "the ECE-versus-coverage relationship is NOT MEASURABLE here. It becomes "
            "measurable once blocks are genuinely absent for a meaningful share of "
            "rows."),
        "ece_slope_vs_uncertainty": _trend(by_unc),
        "by_coverage": by_cov.to_dict(orient="records"),
        "by_uncertainty": by_unc.to_dict(orient="records"),
        "interpretation_rule": (
            # HOW TO READ THE RESULT, WRITTEN ALONGSIDE IT -- and note it says the "expected
            # and desirable" pattern, so a bad-sounding number is not mistaken for a problem.
            # A model whose calibration degrades where it SAYS it is unsure is behaving
            # correctly: its uncertainty estimate is doing its job.
            "A positive slope against uncertainty means calibration degrades exactly "
            "where the model says it is unsure, which is the expected and desirable "
            "pattern. A flat slope against coverage means the uncertainty estimate is "
            "already absorbing missingness."),
    }


# -- EXP-N04-1: selective risk for the uncertainty-weighted rule -------------------------

def exp_n04(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION: if the model is allowed to say "I do not know" and skip the hardest cases,
    # does the uncertainty-aware version make better use of that permission?
    a = arms.get("COMBINER_STATIC")
    b = arms.get("COMBINER_UNCERTAINTY")
    if a is None or b is None:
        # BLOCKED, with the reason. Not a fabricated comparison.
        return {"experiment": "EXP-N04-1", "status": "BLOCKED",
                "reason": "required arms missing"}
    # SELECTIVE RISK: how wrong you are on the cases you chose to answer, at each level of
    # how many you chose to answer.
    sa = info.selective_risk(a["is_episode"].to_numpy(int),
                             a["integrity_risk"].to_numpy(float),
                             a["uncertainty"].to_numpy(float))
    sb = info.selective_risk(b["is_episode"].to_numpy(int),
                             b["integrity_risk"].to_numpy(float),
                             b["uncertainty"].to_numpy(float))
    sa["arm"] = "COMBINER_STATIC"
    sb["arm"] = "COMBINER_UNCERTAINTY"
    both = pd.concat([sa, sb], ignore_index=True)
    both.to_csv(OUT / "exp_n04_selective_risk.csv", index=False)

    # Line the two up at the same coverage levels and subtract -- negative means the
    # uncertainty arm made fewer mistakes.
    merged = sa.merge(sb, on="coverage", suffixes=("_static", "_unc"))
    merged["risk_delta"] = (merged["selective_risk_unc"]
                            - merged["selective_risk_static"])
    wins = int((merged["risk_delta"] < 0).sum())
    return {
        "experiment": "EXP-N04-1",
        "status": "MEASURED",
        "coverage_levels": int(len(merged)),
        "levels_where_uncertainty_arm_better": wins,
        "mean_risk_delta": float(merged["risk_delta"].mean()),
        # "DOMINATES" means better at EVERY level, not on average. A far stronger claim, and
        # it is only made when it is literally true.
        "dominates": bool(wins == len(merged)),
        "table": merged[["coverage", "selective_risk_static", "selective_risk_unc",
                         "risk_delta"]].to_dict(orient="records"),
        "note": (
            # THE CATCH, DECLARED BY THE PEOPLE WHO RAN THE TEST.
            # Each arm ranks rows by ITS OWN uncertainty. So an arm whose uncertainty is
            # merely internally consistent -- confidently wrong in a tidy pattern -- can score
            # well here without being better calibrated at all.
            # Hence: read this alongside the ECE comparison, "not instead of it."
            "Selective risk uses each arm's own uncertainty to rank rows, so an arm "
            "whose uncertainty is merely self-consistent can look good here. Read "
            "alongside the ECE comparison, not instead of it."),
    }


# -- EXP-L12-1: power curve and minimum detectable effect ------------------------------

def exp_l12(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION THAT RESCUES EVERY NULL RESULT. "We found no significant difference" could
    # mean there is none -- or that this study was far too small to see one.
    # POWER ANALYSIS separates those two. It says: with this much data, the smallest
    # difference we could reliably detect was X.
    full = arms["FULL"]
    out: dict = {"experiment": "EXP-L12-1", "status": "MEASURED", "comparisons": []}
    # THREE COMPARISONS CHOSEN TO SPAN THE RANGE, and each labelled with what was previously
    # concluded about it. Including the one where nothing was found -- which is precisely the
    # case this analysis exists to interrogate.
    targets = [("NO_MICROSTRUCTURE", "not significant at 5% FDR"),
               ("NO_PROPAGATION", "significant but negligible"),
               ("NO_AFFECTIVE", "significant and large")]
    curves = []
    for arm_name, label in targets:
        other = arms.get(arm_name)
        if other is None:
            continue
        # Match row for row, by company and date.
        merged = full[["symbol", "date", "is_episode", "episode_id",
                       "integrity_risk"]].merge(
            other[["symbol", "date", "integrity_risk"]], on=["symbol", "date"],
            suffixes=("_full", "_arm"))
        merged["cluster"] = _cluster(merged)
        # THE POWER CURVE: repeat the comparison at 30%, 50%, 100% of the data, and watch how
        # detectability improves as the sample grows.
        curve = pw.power_curve(merged, "cluster", "integrity_risk_full",
                               "integrity_risk_arm", b=250)
        curve["comparison"] = "FULL vs %s" % arm_name
        curves.append(curve)
        mde = pw.minimum_detectable_effect(merged, "cluster", "integrity_risk_full",
                                           "integrity_risk_arm", b=400)
        # AND THE PRACTICAL ANSWER: how much more data would be needed to detect a difference
        # of 0.002. Which turns "we could not tell" into "here is what it would take".
        need = pw.required_clusters_for_effect(curve, target_effect=0.002)
        out["comparisons"].append({
            "arm": arm_name, "prior_label": label,
            "minimum_detectable_effect": mde.get("minimum_detectable_effect"),
            # The MDE AND the difference actually seen, side by side. If the observed
            # difference is smaller than the MDE, the null result was uninformative.
            "observed_difference": mde.get("observed_difference"),
            "informative": mde.get("informative"),
            "scaling_exponent": need.get("scaling_exponent"),
            "clusters_needed_for_0.002": need.get("required_clusters"),
            # "MULTIPLE OF CURRENT" is the honest headline: 40x means this is not a matter of
            # collecting a bit more data.
            "multiple_of_current": need.get("multiple_of_current"),
        })
    if curves:
        pd.concat(curves, ignore_index=True).to_csv(
            OUT / "exp_l12_power_curves.csv", index=False)
    return out


# -- EXP-L04-2: which episode properties drive detection -------------------------------

def exp_l04(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION: WHICH episodes get caught? Only the huge obvious ones, or the subtle ones
    # too? An average detection rate hides this completely.
    full = arms["FULL"]
    labels_path = paths.PANEL / "episode_labels.parquet"
    if not labels_path.exists():
        return {"experiment": "EXP-L04-2", "status": "BLOCKED",
                "reason": "episode_labels.parquet absent"}
    labels = pd.read_parquet(labels_path)
    ep = full[full["episode_id"].astype(str) != ""]
    if ep.empty:
        # A DIFFERENT STATUS from BLOCKED: the file exists, but this slice has no episodes in
        # it. Two distinct situations, two distinct words.
        return {"experiment": "EXP-L04-2", "status": "NOT MEASURED",
                "reason": "no episode rows in the evaluation split"}

    # One row per episode: how strong it was, whether it was cut off by the window edge, and
    # how many days it lasted.
    props = (labels.groupby("episode_id")
             .agg(peak_intensity=("peak_intensity", "first"),
                  censored=("censored", "first"),
                  duration=("date", "count"))
             .reset_index())
    # And how the model scored each one.
    per_ep = (ep.groupby("episode_id")
              .agg(max_score=("integrity_risk", "max"),
                   mean_score=("integrity_risk", "mean"),
                   n_rows=("integrity_risk", "size"))
              .reset_index())
    d = per_ep.merge(props, on="episode_id", how="inner")
    if len(d) < 8:
        # FEWER THAN EIGHT EPISODES -> INSUFFICIENT, and the count is reported. A correlation
        # over six points is not a finding.
        return {"experiment": "EXP-L04-2", "status": "INSUFFICIENT",
                "n_episodes": int(len(d))}

    from scipy.stats import spearmanr
    d["detected"] = (d["max_score"] >= 0.55).astype(int)
    d.to_csv(OUT / "exp_l04_episode_properties.csv", index=False)

    # Split into the weakest quarter and the strongest quarter of episodes.
    q = d["peak_intensity"].quantile([0.25, 0.75])
    low = d[d["peak_intensity"] <= q.iloc[0]]
    high = d[d["peak_intensity"] >= q.iloc[1]]
    return {
        "experiment": "EXP-L04-2",
        "status": "MEASURED",
        "n_episodes": int(len(d)),
        # SPEARMAN correlates RANKS rather than values, so it is not thrown off by one
        # enormous outlier.
        "spearman_intensity_vs_max_score": float(
            spearmanr(d["peak_intensity"], d["max_score"]).statistic),
        "spearman_duration_vs_max_score": float(
            spearmanr(d["duration"], d["max_score"]).statistic),
        # THE TWO NUMBERS THAT MATTER, kept separate rather than averaged into one.
        "detection_rate_low_intensity_quartile": float(low["detected"].mean())
        if len(low) else None,
        "detection_rate_high_intensity_quartile": float(high["detected"].mean())
        if len(high) else None,
        "intensity_floor_note": (
            # AND THE PROJECT DISCOUNTS ITS OWN BEST-LOOKING NUMBER.
            # "Peak intensity is a generator parameter" -- the project DECIDED how strong each
            # synthetic episode would be. So of course stronger ones score higher; that is
            # nearly true by construction, not a discovery.
            # THE INFORMATIVE QUANTITY is the detection rate in the WEAKEST quarter, because
            # that bounds how small an event this architecture could see at all.
            # Pointing away from your impressive correlation and towards your least flattering
            # number is exactly the right instinct.
            "Peak intensity is a generator parameter, so a positive correlation is "
            "partly definitional. The informative quantity is the detection rate in the "
            "lowest quartile: it bounds the magnitude of event this architecture could "
            "see at all."),
    }


# -- EXP-N02-1: regime gap versus episodes per regime ----------------------------------

def exp_n02(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION, and it is a genuine fork with two very different answers.
    # The regime-aware version performs worse than the simple one. Why?
    #   (a) It is starved -- per-regime parameters split the data thinly, so each is estimated
    #       from too few episodes. More data would fix it.
    #   (b) It is redundant -- regime information is already in the market block. More data
    #       would fix nothing.
    # The test: does the gap SHRINK as the sample grows? Shrinking points to (a). Flat points
    # to (b).
    a = arms.get("COMBINER_STATIC")
    b = arms.get("COMBINER_REGIME_CORRECTED")
    if a is None or b is None:
        return {"experiment": "EXP-N02-1", "status": "BLOCKED",
                "reason": "required arms missing"}
    merged = a[["symbol", "date", "is_episode", "episode_id", "integrity_risk"]].merge(
        b[["symbol", "date", "integrity_risk"]], on=["symbol", "date"],
        suffixes=("_static", "_regime"))
    merged["cluster"] = _cluster(merged)
    # Measure the gap at five different sample sizes.
    curve = pw.power_curve(merged, "cluster", "integrity_risk_regime",
                           "integrity_risk_static",
                           fractions=(0.3, 0.5, 0.7, 0.85, 1.0), b=250)
    curve.to_csv(OUT / "exp_n02_regime_gap_vs_sample.csv", index=False)
    ok = curve[curve.get("status") == "OK"] if "status" in curve.columns else curve

    trend = None
    if len(ok) >= 3:
        # The slope of the gap against sample size.
        trend = float(np.polyfit(ok["n_clusters"].to_numpy(float),
                                 ok["mean_difference"].to_numpy(float), 1)[0])

    # Episodes available per regime, which is the quantity the variance-inflation
    # explanation depends on.
    # PLAIN ENGLISH: the direct evidence for explanation (a). If one regime has three episodes
    # in it, its parameters CANNOT be estimated well, and the count says so plainly.
    per_regime = None
    dpath = paths.PANEL / "market_dataset.parquet"
    if dpath.exists():
        dd = pd.read_parquet(dpath, columns=["regime_id", "episode_id", "split"])
        val = dd[dd["split"] == "validation"]
        per_regime = (val[val["episode_id"].astype(str) != ""]
                      .groupby("regime_id")["episode_id"].nunique().to_dict())
        # Keys converted to strings, because JSON keys must be text.
        per_regime = {str(int(k)): int(v) for k, v in per_regime.items()}

    return {
        "experiment": "EXP-N02-1",
        "status": "MEASURED",
        "gap_trend_per_cluster": trend,
        "gap_shrinks_with_sample": (trend is not None and trend > 0),
        "episodes_per_regime_validation": per_regime,
        "curve": ok.to_dict(orient="records"),
        "interpretation_rule": (
            # BOTH READINGS WRITTEN DOWN IN ADVANCE, so whichever way the number falls, the
            # conclusion was decided before the result was seen. This is what stops a
            # disappointing outcome being reinterpreted into a pleasing one.
            "A gap that closes as clusters increase supports variance inflation from "
            "per-regime parameters. A flat gap points instead to redundancy between the "
            "regime block and the market block."),
    }


# -- EXP-N01-1: LIME stability versus perturbation count -------------------------------

def exp_n01() -> dict:
    # THE FOLLOW-UP TO THE FAILED SANITY CHECK. LIME's sign consistency came in at 0.780
    # against a bar of 0.80 -- a FAIL, published in red on the project's own XAI page.
    # This asks the obvious next question: is LIME simply under-sampled? Throw more
    # perturbations at it and does it stabilise? And if so, is it still cheaper than the
    # method it was supposed to be cheaper than?
    dpath = paths.PANEL / "market_dataset.parquet"
    if not dpath.exists():
        return {"experiment": "EXP-N01-1", "status": "BLOCKED",
                "reason": "dataset absent"}
    data = pd.read_parquet(dpath)
    train = data[data["split"] == "train"]
    evald = data[data["split"] == "validation"]
    # Every feature from every block, keeping only columns that exist and are not entirely
    # empty.
    cols = [c for m in BLOCKS for c in ds.FEATURE_BLOCKS[m]
            if c in data.columns]
    cols = [c for c in cols if data[c].notna().any()]
    # `nan_to_num` replaces missing values with 0 -- acceptable here because this is a
    # side-experiment about explanation stability, not a reported model result.
    Xtr = np.nan_to_num(train[cols].to_numpy(float), nan=0.0)
    Xev = np.nan_to_num(evald[cols].to_numpy(float), nan=0.0)
    y_tr = train["is_episode"].to_numpy(int)

    from sklearn.ensemble import HistGradientBoostingClassifier
    # A fixed random_state, so this whole experiment reproduces exactly.
    m = HistGradientBoostingClassifier(max_iter=180, max_depth=4, learning_rate=0.06,
                                       random_state=20260818)
    m.fit(Xtr, y_tr)
    # A tiny function the explanation methods can call: give it rows, get back scores.
    # `[:, 1]` takes the probability of the positive class.
    predict = lambda Z: m.predict_proba(np.nan_to_num(Z, nan=0.0))[:, 1]  # noqa: E731
    # Explain the single highest-scoring row -- the most interesting case.
    row = int(np.argmax(predict(Xev)))
    # A background sample, for "what would a typical row look like".
    bg = Xtr[np.random.default_rng(0).choice(len(Xtr), min(200, len(Xtr)),
                                             replace=False)]
    # OCCLUSION IS THE REFERENCE. It is slower but trustworthy: cover a feature and see how
    # much the score moves. LIME's answers are compared against it.
    ref = xm.occlusion(predict, Xev, row, cols, bg)

    rows = []
    # Doubling each time: 400, 800, 1600, 3200, 6400 perturbations.
    for n_samples in (400, 800, 1600, 3200, 6400):
        t0 = time.perf_counter()
        # THREE RUNS WITH THREE DIFFERENT SEEDS. That is the whole test -- do three runs of
        # the same method on the same row agree with each other?
        runs = [xm.lime(predict, Xev, row, cols, bg, n_samples=n_samples, seed=s)
                for s in (1, 2, 3)]
        elapsed = (time.perf_counter() - t0) / 3.0
        # Do the three runs at least agree on the DIRECTION of each feature's effect? A method
        # that cannot manage that is not explaining anything.
        sc = xs.sign_consistency(runs)
        from scipy.stats import spearmanr
        # AND SEPARATELY: does LIME agree with the trustworthy method? Stability and
        # correctness are different properties -- something can be reliably wrong.
        rho = float(spearmanr(runs[0].values, ref.values).statistic)
        rows.append({"n_perturbations": n_samples,
                     "sign_consistency": float(sc.statistic),
                     "passes_threshold": bool(sc.passed),
                     "spearman_vs_occlusion": rho,
                     # AND THE COST, recorded at every level. The trade-off is the finding.
                     "seconds_per_run": float(elapsed)})
        progress.log("    LIME n=%5d  sign_consistency=%.3f  rho_vs_occlusion=%+.3f  "
                     "%.2fs" % (n_samples, sc.statistic, rho, elapsed))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "exp_n01_lime_stability.csv", index=False)
    crossing = df[df["passes_threshold"]]
    return {
        "experiment": "EXP-N01-1",
        "status": "MEASURED",
        "occlusion_seconds": float(ref.seconds),
        # Where it first passes -- None if it never does, which is an honest answer.
        "crosses_threshold_at": int(crossing["n_perturbations"].min())
        if len(crossing) else None,
        "cost_at_crossing_seconds": float(
            crossing.sort_values("n_perturbations").iloc[0]["seconds_per_run"])
        if len(crossing) else None,
        # THE QUESTION THAT DECIDES IT. LIME's entire selling point is speed. If it only
        # becomes trustworthy at a sample size where it is SLOWER than the method it was
        # meant to replace, then there is no reason to use it -- and this boolean says so.
        "cheaper_than_occlusion_at_crossing": bool(
            len(crossing) and crossing.sort_values("n_perturbations")
            .iloc[0]["seconds_per_run"] < ref.seconds),
        "table": rows,
    }


# -- block information decomposition (research-angle section 28) --------------------

def block_matrix(arms: dict[str, pd.DataFrame]) -> dict:
    # THE QUESTION: what does each kind of evidence actually contribute?
    # UNIQUE  = signal only this block has.
    # REDUNDANT = signal it shares with the others.
    # A block whose contribution is entirely redundant is decoration.
    cov = {}
    dpath = paths.PANEL / "market_dataset.parquet"
    if dpath.exists():
        flags = list(ds.COVERAGE_FLAGS)
        d = pd.read_parquet(dpath, columns=flags + ["split"])
        d = d[d["split"] == "validation"]
        for flag in flags:
            # "cov_micro" -> "microstructure", so the names match BLOCK_ARMS above.
            mod = flag.replace("cov_", "").replace("micro", "microstructure")
            # How often this block's data was actually present.
            cov[mod] = float(d[flag].mean())
    # Only blocks whose required arms were actually run.
    usable = {m: (a, b) for m, (a, b) in BLOCK_ARMS.items()
              if b in arms and (a is None or a in arms)}
    matrix = info.decomposition(arms, "FULL",
                                {m: (a, b) for m, (a, b) in usable.items()
                                 if a is not None},
                                coverage=cov)
    # Blocks that have no stand-alone arm still have a measurable unique contribution.
    # PLAIN ENGLISH: without an "only this block" arm you cannot split unique from redundant.
    # But you CAN still measure "how much worse is everything without it". So that much is
    # reported, and every quantity that genuinely cannot be computed is set to NaN rather
    # than to a guess.
    extra = []
    for m, (a, b) in usable.items():
        if a is not None:
            continue
        without = arms[b]
        auprc_full = info._auprc(arms["FULL"]["is_episode"].to_numpy(int),
                                 arms["FULL"]["integrity_risk"].to_numpy(float))
        auprc_wo = info._auprc(without["is_episode"].to_numpy(int),
                               without["integrity_risk"].to_numpy(float))
        # NaN everywhere the quantity is genuinely unavailable. A zero here would read as
        # "measured, and it contributes nothing" -- a completely different claim.
        extra.append({"block": m, "total_auprc": np.nan,
                      "unique": auprc_full - auprc_wo, "redundant": np.nan,
                      "redundant_raw": np.nan, "conflict_rate": np.nan,
                      "missing_rate": 1.0 - cov.get(m, np.nan),
                      "auprc_full": auprc_full, "auprc_without": auprc_wo})
    if extra:
        matrix = pd.concat([matrix, pd.DataFrame(extra)], ignore_index=True)
    # Most uniquely useful block first.
    matrix = matrix.sort_values("unique", ascending=False).reset_index(drop=True)
    matrix.to_csv(OUT / "block_information_matrix.csv", index=False)
    return {"analysis": "block_information_decomposition", "status": "MEASURED",
            "rows": matrix.to_dict(orient="records"),
            "caveat": (
                # TWO ADMISSIONS IN ONE CAVEAT.
                # 1. This is a practical decomposition in AUPRC, NOT the formal
                #    information-theoretic one that shares the name. Claiming the formal
                #    version would be a much stronger and unearned claim.
                # 2. The regime and propagation blocks are DERIVED FROM THE SAME PRICE SERIES
                #    the market block reads. So a low uniqueness for either is expected by
                #    construction -- it says something about how the features were built, not
                #    about whether that kind of evidence is useful in principle.
                "Operational decomposition in AUPRC, not a formal partial "
                "information decomposition. The regime and propagation blocks are "
                "derived from the same price series the market block reads, so a "
                "low uniqueness for either is expected by construction.")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    progress.log("running research angles that need no external data")
    arms = _load_arms()
    progress.log("  loaded %d per-arm score frames" % len(arms))
    if "FULL" not in arms:
        # A clear stop with the exact command to fix it, rather than a confusing failure
        # further down.
        raise SystemExit("per_row_FULL.parquet missing: run scripts/run_experiments.py")

    # `lambda:` wraps each call so it is not executed while the list is being built -- the
    # list holds instructions, and the loop below runs them one at a time.
    steps = [
        ("block_information", lambda: block_matrix(arms)),
        ("EXP-N03-1 lead-time frontier", lambda: exp_n03(arms)),
        ("EXP-L10-1 calibration buckets", lambda: exp_l10(arms)),
        ("EXP-N04-1 selective risk", lambda: exp_n04(arms)),
        ("EXP-L12-1 power analysis", lambda: exp_l12(arms)),
        ("EXP-L04-2 episode properties", lambda: exp_l04(arms)),
        ("EXP-N02-1 regime gap vs sample", lambda: exp_n02(arms)),
        ("EXP-N01-1 LIME stability", exp_n01),
    ]
    for name, fn in steps:
        progress.log("  %s" % name)
        try:
            r = fn()
            results[r.get("experiment", r.get("analysis", name))] = r
        except Exception as exc:
            # ONE EXPERIMENT FAILING DOES NOT KILL THE RUN -- and the failure is RECORDED in
            # the results with its exact error, rather than leaving a silent gap where a
            # result should be.
            progress.log("    FAILED: %s: %s" % (type(exc).__name__, exc))
            results[name] = {"status": "FAILED",
                             "error": "%s: %s" % (type(exc).__name__, exc)}

    payload = {
        "run_at": datetime.now(UTC).isoformat(),
        "registry_version": reg.REGISTRY_VERSION,
        # WHAT WAS RUNNABLE, and separately WHAT REMAINS BLOCKED -- with the data each blocked
        # one is waiting on. So the output records both what was done and what could not be.
        "runnable_specs": [e.id for e in reg.runnable_now()],
        "blocked_specs": [{"id": e.id, "required_data": e.required_data}
                          for e in reg.blocked()],
        "results": results,
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "research_angles.json", payload)
    # The registry is rewritten so its result slots now point at these findings -- the
    # limitations pages pick them up automatically, with no number typed by hand.
    reg.write(paths.MANIFESTS / "limitations_registry.json")
    progress.log("done in %.1fs -> %s" % (time.time() - t0, OUT))

    # A final summary on screen: every experiment and its status, INCLUDING the failures,
    # the blocked ones and the not-measurable ones.
    for k, v in results.items():
        print("%-34s %s" % (k, v.get("status")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
