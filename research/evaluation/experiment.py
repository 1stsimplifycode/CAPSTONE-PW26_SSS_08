"""Reproducible experiment engine (spec sections 35, 82, 83).

An experiment is a declaration, not a script. :class:`ExperimentSpec` names the
hypothesis, the data, the arm, the seed, the baseline and the metrics; :func:`run`
executes it and writes a self-contained artifact bundle. Nothing downstream -- figures,
tables, statistics, the paper package -- reads anything other than these bundles, which is
what makes "regenerate every paper asset from one command" true rather than aspirational.

Every arm reports its own failures. An arm whose learner could not be fitted returns
``status = "FAILED"`` with the reason and NaN metrics; it is never dropped silently and
never back-filled, because a quietly missing ablation arm is how an ablation table comes
to overstate a result.

PLAIN ENGLISH -- what this whole file is about:

THE MACHINE THAT RUNS ONE EXPERIMENT AND WRITES DOWN EVERYTHING ABOUT IT.

IDEA 1: "AN EXPERIMENT IS A DECLARATION, NOT A SCRIPT."
Most research code is scripts -- a file of instructions that does things. The trouble with
a script is that it can be edited a little each time it is run, and afterwards nobody can
say precisely what produced any given number.
Here an experiment is a FORM you fill in: what am I claiming, which data, which settings,
which seed, what am I comparing against. Then one engine executes the form. The form is
saved with the results, so what ran is a permanent record rather than a memory.

IDEA 2: THE SEALED BOX.
Each run writes a folder containing everything: the form, the results, every row's score,
a summary of the model, a readable report, and a full receipt naming every software
version and the exact code snapshot.
And then the crucial rule: NOTHING downstream reads anything else. Every chart, every
table, every number in the paper comes out of these folders. That is what makes
"regenerate the entire paper with one command" a true statement rather than a hope. If a
figure could quietly read some other file, one such file would eventually go stale and the
paper would be describing a run that no longer exists.

IDEA 3, AND THE MOST IMPORTANT ONE: FAILURES STAY IN THE TABLE.
Suppose one of twenty experiments crashes. The tempting, tidy behaviour is to skip it.
Now consider what that does. Your results table has nineteen rows. It looks complete. And
the missing one might have been the arm that undermined your conclusion -- nobody can
tell, because there is no row saying it ever existed.
So a failed run stays in the table, marked FAILED, with the actual error message and
blanks for its numbers. Untidy, obvious, and honest. The docstring names the failure mode
exactly: "a quietly missing ablation arm is how an ablation table comes to overstate a
result."
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For writing JSON.
import json
# For timing how long things take.
import time
# Record-building tools.
from dataclasses import asdict, dataclass, field
# The world clock and the tool for reading the time.
from datetime import UTC, datetime
# A safe way to talk about places on the disk.
from pathlib import Path
# "any kind of value at all".
from typing import Any

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The project's address book.
from research.core import paths
# The receipt that records every version and setting.
from research.core.manifest import ReproducibilityManifest
# The table-assembly module, for its list of which measurements belong to which family.
from research.data import dataset as ds
# The state machine that turns scores into episodes.
from research.detection import state as st
# The measuring tapes.
from research.evaluation import metrics as mx
# The model itself.
from research.models.risk_model import AegisRiskModel

# A label for this version of the engine.
EXPERIMENT_VERSION = "experiment-v1"


@dataclass
# THE FORM. Everything needed to define one experiment.
class ExperimentSpec:
    # What this experiment is called.
    experiment_id: str
    # WHAT IS BEING CLAIMED. First field after the name, because it is the point of the
    # whole exercise -- an experiment with no hypothesis is just a computation.
    hypothesis: str
    # Which variation is being run.
    arm: str
    # Which families of evidence it may use.
    blocks: list[str]
    # Which combining rule.
    combination_rule: str = "regime_corrected"
    # Which data file.
    dataset_path: str = ""
    # Which portion to learn from, and which to be judged on. Named separately and
    # explicitly, so the separation between them is part of the record.
    train_split: str = "train"
    eval_split: str = "validation"
    # The starting point for randomness, so this exact run can be repeated.
    seed: int = 20260818
    # What it is being compared against.
    baseline: str | None = None
    # Which measures decide the outcome -- fixed in advance, so nobody can pick the
    # flattering one after seeing the numbers.
    metrics: list[str] = field(default_factory=lambda: ["auprc", "auroc", "f1",
                                                        "brier", "ece"])
    # Any special settings for the state machine.
    state_config: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # A short unique name for this run, used for its folder.
    def key(self) -> str:
        return "%s__%s" % (self.experiment_id, self.arm)


@dataclass
# What comes back from one run.
class ExperimentResult:
    # The form that produced it, kept attached so results and settings can never be
    # separated.
    spec: ExperimentSpec
    # OK or FAILED.
    status: str
    run_id: str
    # How well it detected trouble.
    detection: dict[str, float] = field(default_factory=dict)
    # How well it got the TIMING right.
    temporal: dict[str, Any] = field(default_factory=dict)
    # How fast and how heavy it was.
    operational: dict[str, Any] = field(default_factory=dict)
    # Every individual row's score, for later analysis.
    per_row: pd.DataFrame | None = None
    # How the model's training went.
    model_summary: pd.DataFrame | None = None
    # If it failed, exactly why -- in words a person can act on.
    failure_reason: str | None = None
    artifact_dir: str | None = None

    # Flatten this result into one row of a results table.
    def to_record(self) -> dict:
        d = {"experiment_id": self.spec.experiment_id, "arm": self.spec.arm,
             "status": self.status, "run_id": self.run_id,
             "combiner": self.spec.combination_rule,
             "blocks": ",".join(self.spec.blocks)}
        # Only numeric measures go into the table; text fields would break a numeric column.
        d.update({k: v for k, v in self.detection.items()
                  if isinstance(v, (int, float))})
        # Timing measures get a prefix so they cannot collide with a detection measure of
        # the same name and silently overwrite it.
        d.update({("temporal_" + k): v for k, v in self.temporal.items()
                  if isinstance(v, (int, float))})
        return d


# Remove a family of evidence properly.
def _drop_blocks(df: pd.DataFrame, drop: list[str]) -> pd.DataFrame:
    """Remove a block's columns *and* zero its coverage flag.

    Zeroing coverage matters: the combination layer excludes zero-coverage blocks, so an
    ablation that only deleted the columns would still let the block vote through a
    stale flag.
    """
    # PLAIN ENGLISH: a subtle bug avoided, and one that would have been very hard to spot.
    # Two things describe a family: its measurements, and a flag saying "we have this
    # family's evidence". Blank the measurements but leave the flag saying 1, and the
    # combining layer still gives that specialist a vote -- a specialist now holding no
    # information at all, quietly diluting everybody else's opinion.
    # The experiment would run, produce plausible numbers, and be measuring something other
    # than what it claimed. Both must be cleared together.
    out = df.copy()
    for m in drop:
        # Blank every measurement in this family.
        for c in ds.FEATURE_BLOCKS.get(m, []):
            if c in out.columns:
                out[c] = np.nan
        # AND set its coverage flag to zero, so the combining layer genuinely excludes it.
        # The little dictionary handles the one family whose column name was shortened.
        key = {"microstructure": "cov_micro"}.get(m, "cov_%s" % m)
        if key in out.columns:
            out[key] = 0.0
    return out


# RUN ONE EXPERIMENT.
def run(spec: ExperimentSpec, data: pd.DataFrame,
        write: bool = True) -> ExperimentResult:
    run_id = "%s_%d" % (spec.key(), spec.seed)
    t_fit0 = time.perf_counter()
    # Split the data into the part to learn from and the part to be judged on.
    train = data[data["split"] == spec.train_split]
    evald = data[data["split"] == spec.eval_split]
    # Either half empty means no valid experiment. Return a FAILED result with the reason --
    # note it RETURNS rather than crashing, so the sweep carries on and this failure appears
    # in the table.
    if train.empty or evald.empty:
        return ExperimentResult(spec, "FAILED", run_id,
                                failure_reason="empty train or eval split")

    # Work out which families this arm is NOT allowed, and remove them properly from both
    # halves -- the same treatment on each, or the model would be trained and judged on
    # different information.
    all_blocks = list(ds.FEATURE_BLOCKS)
    drop = [m for m in all_blocks if m not in spec.blocks]
    train_x = _drop_blocks(train, drop)
    eval_x = _drop_blocks(evald, drop)

    # The right answers for each half.
    y_tr = train_x["is_episode"].to_numpy(int)
    y_ev = eval_x["is_episode"].to_numpy(int)

    try:
        model = AegisRiskModel(blocks=list(spec.blocks),
                               combination_rule=spec.combination_rule,
                               seed=spec.seed)
        # LEARNING USES THE TRAINING HALF ONLY.
        model.fit(train_x, y_tr)
    except Exception as exc:
        # Training failed. Return FAILED with the actual error type and message, so whoever
        # reads the results table can diagnose it without rerunning anything.
        return ExperimentResult(spec, "FAILED", run_id,
                                failure_reason="fit failed: %s: %s"
                                               % (type(exc).__name__, exc))
    fit_s = time.perf_counter() - t_fit0

    # Now score the evaluation half, timing it separately -- training cost and scoring cost
    # are different practical questions.
    t_pred0 = time.perf_counter()
    pred = model.predict(eval_x)
    pred_s = time.perf_counter() - t_pred0

    # Threshold is chosen on the *training* split and applied unchanged to eval. Choosing
    # it on eval would leak the evaluation labels into the operating point (leakage L6).
    # PLAIN ENGLISH: the cut-off between "trouble" and "calm" is itself a decision that has
    # to be learned -- and learning it from the exam paper is cheating just as surely as
    # training on it. So the model scores the TRAINING data, the best cut-off is found there,
    # and that value is then applied to the evaluation data unchanged, however it performs.
    tr_pred = model.predict(train_x)
    thr = mx.best_f1_threshold(y_tr, tr_pred["integrity_risk"])

    # Score the evaluation half at that pre-chosen cut-off.
    det = mx.detection_metrics(y_ev, pred["integrity_risk"], threshold=thr)

    # Build the per-row record: the truth alongside what the model said.
    scored = evald[["symbol", "date", "is_episode", "episode_id", "t_entry", "t_exit",
                    "state", "intensity"]].copy()
    scored["integrity_risk"] = pred["integrity_risk"]
    scored["uncertainty"] = pred["uncertainty"]
    scored["coverage"] = pred["coverage"]
    # And each specialist's opinion, its weight, and its contribution -- so the final number
    # can be taken apart completely and checked by anybody.
    for i, m in enumerate(pred["block_names"]):
        scored["score_%s" % m] = pred["block_scores"][:, i]
        scored["weight_%s" % m] = pred["block_weights"][:, i]
        scored["contrib_%s" % m] = pred["block_contribution"][:, i]

    # Turn the day-by-day scores into named episodes.
    cfg = st.StateConfig(**spec.state_config) if spec.state_config else st.StateConfig()
    scored = st.apply_to_frame(scored, "integrity_risk", cfg)
    pred_windows = st.windows_from_frame(scored, "integrity_risk", cfg)
    pw = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry, "t_exit": w.t_exit,
                        "t_peak": w.t_peak, "peak_score": w.peak_score,
                        "censored": w.censored} for w in pred_windows])
    # And the real episodes, for comparison.
    tw = (scored[scored["is_episode"] == 1]
          .groupby(["symbol", "episode_id"])
          .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
          .reset_index())
    # Score the timing -- but only if there is anything to match on either side. Otherwise
    # record the counts and a note, rather than a table of misleading zeros.
    temporal = mx.temporal_metrics(tw, pw, scored["date"].drop_duplicates()) \
        if len(tw) and len(pw) else {"n_true_windows": int(len(tw)),
                                     "n_pred_windows": int(len(pw)),
                                     "note": "no matchable windows"}
    # Take the bulky per-episode detail out of the summary; it is saved separately.
    per_window = temporal.pop("per_window", None)

    res = ExperimentResult(
        spec, "OK", run_id, detection=det, temporal=temporal,
        # Speed and cost recorded alongside quality.
        operational=mx.operational_metrics(fit_s, pred_s, len(eval_x)),
        per_row=scored, model_summary=model.summary())

    # Save the sealed box, unless the caller only wanted the numbers.
    if write:
        res.artifact_dir = str(_write_bundle(res, per_window))
    return res


# Write everything about one run into its own folder.
def _write_bundle(res: ExperimentResult, per_window: pd.DataFrame | None) -> Path:
    d = paths.REPORTS / res.run_id
    d.mkdir(parents=True, exist_ok=True)
    # 1. THE FORM -- exactly what was asked for.
    (d / "config.json").write_text(
        json.dumps(asdict(res.spec), indent=2, default=str), encoding="utf-8")
    # 2. THE RESULTS, as JSON for programs...
    (d / "metrics.json").write_text(
        json.dumps({"detection": res.detection, "temporal": res.temporal,
                    "operational": res.operational, "status": res.status},
                   indent=2, default=str), encoding="utf-8")
    # ...and as a spreadsheet row, so results from many runs can simply be stacked up.
    pd.DataFrame([res.to_record()]).to_csv(d / "metrics.csv", index=False)
    # 3. EVERY ROW'S SCORE. Parquet is a compact, fast format for large tables -- it would
    # be wasteful as text.
    if res.per_row is not None:
        res.per_row.to_parquet(d / "per_row.parquet", index=False)
    # 4. How the model's training went.
    if res.model_summary is not None:
        res.model_summary.to_csv(d / "model_summary.csv", index=False)
    # 5. The per-episode timing detail.
    if per_window is not None and len(per_window):
        per_window.to_csv(d / "per_window.csv", index=False)
    # 6. THE RECEIPT: every software version, the code snapshot, the machine, the moment.
    # This is what makes the run reproducible by somebody else, years later.
    ReproducibilityManifest(
        experiment_id=res.spec.experiment_id, run_id=res.run_id, seed=res.spec.seed,
        config=asdict(res.spec), feature_version=ds.DATASET_VERSION,
        model_versions={"risk_model": "aegis-risk-v1"},
    ).write(d / "reproducibility_manifest.json")

    # 7. AND A REPORT A HUMAN CAN READ, built as Markdown -- plain text that displays as a
    # formatted document. Somebody can open the folder and understand the run without any
    # tools at all.
    lines = [
        "# Experiment report: %s" % res.run_id,
        "",
        # The hypothesis first, as it should be.
        "**Hypothesis.** %s" % res.spec.hypothesis,
        "",
        "**Arm.** `%s` | blocks: %s | combiner: `%s`"
        # `or "none"` so an arm with no evidence families reads sensibly rather than blank.
        % (res.spec.arm, ", ".join(res.spec.blocks) or "none",
           res.spec.combination_rule),
        "",
        "**Status.** %s" % res.status,
        "",
        "## Detection", "",
        # A Markdown table: header row, then the separator that makes it a table.
        "| metric | value |", "|---|---|",
    ]
    for k, v in res.detection.items():
        lines.append("| %s | %s |" % (k, _fmt(v)))
    lines += ["", "## Temporal", "", "| metric | value |", "|---|---|"]
    for k, v in res.temporal.items():
        lines.append("| %s | %s |" % (k, _fmt(v)))
    lines += ["", "## Operational", "", "| metric | value |", "|---|---|"]
    for k, v in res.operational.items():
        lines.append("| %s | %s |" % (k, _fmt(v)))
    # And every report ends with the same warning: these results are about SYNTHETIC
    # episodes. Attached automatically, to every single run, so it can never be forgotten on
    # the one report that ends up being circulated.
    lines += ["", "---", "",
              "Generated %s. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` "
              "L-04." % datetime.now(UTC).isoformat()]
    (d / "experiment_report.md").write_text("\n".join(lines), encoding="utf-8")
    return d


# Format a value for the readable report.
def _fmt(v: Any) -> str:
    if isinstance(v, float):
        # `v != v` is the NaN check -- only NaN is unequal to itself. Unknowns print as the
        # word "NaN" rather than as an ugly machine value, so the report stays readable.
        return "NaN" if v != v else "%.4f" % v
    return str(v)


# Stack many results into one comparison table.
def results_table(results: list[ExperimentResult]) -> pd.DataFrame:
    # Note this includes FAILED runs, because `to_record` puts their status in. That is the
    # whole point from the top of the file: the failures stay visible in the table.
    return pd.DataFrame([r.to_record() for r in results])
