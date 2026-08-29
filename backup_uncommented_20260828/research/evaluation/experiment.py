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
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.core import paths
from research.core.manifest import ReproducibilityManifest
from research.data import dataset as ds
from research.detection import state as st
from research.evaluation import metrics as mx
from research.models.risk_model import AegisRiskModel

EXPERIMENT_VERSION = "experiment-v1"


@dataclass
class ExperimentSpec:
    experiment_id: str
    hypothesis: str
    arm: str
    blocks: list[str]
    combination_rule: str = "regime_corrected"
    dataset_path: str = ""
    train_split: str = "train"
    eval_split: str = "validation"
    seed: int = 20260818
    baseline: str | None = None
    metrics: list[str] = field(default_factory=lambda: ["auprc", "auroc", "f1",
                                                        "brier", "ece"])
    state_config: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def key(self) -> str:
        return "%s__%s" % (self.experiment_id, self.arm)


@dataclass
class ExperimentResult:
    spec: ExperimentSpec
    status: str
    run_id: str
    detection: dict[str, float] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    operational: dict[str, Any] = field(default_factory=dict)
    per_row: pd.DataFrame | None = None
    model_summary: pd.DataFrame | None = None
    failure_reason: str | None = None
    artifact_dir: str | None = None

    def to_record(self) -> dict:
        d = {"experiment_id": self.spec.experiment_id, "arm": self.spec.arm,
             "status": self.status, "run_id": self.run_id,
             "combiner": self.spec.combination_rule,
             "blocks": ",".join(self.spec.blocks)}
        d.update({k: v for k, v in self.detection.items()
                  if isinstance(v, (int, float))})
        d.update({("temporal_" + k): v for k, v in self.temporal.items()
                  if isinstance(v, (int, float))})
        return d


def _drop_blocks(df: pd.DataFrame, drop: list[str]) -> pd.DataFrame:
    """Remove a block's columns *and* zero its coverage flag.

    Zeroing coverage matters: the combination layer excludes zero-coverage blocks, so an
    ablation that only deleted the columns would still let the block vote through a
    stale flag.
    """
    out = df.copy()
    for m in drop:
        for c in ds.FEATURE_BLOCKS.get(m, []):
            if c in out.columns:
                out[c] = np.nan
        key = {"microstructure": "cov_micro"}.get(m, "cov_%s" % m)
        if key in out.columns:
            out[key] = 0.0
    return out


def run(spec: ExperimentSpec, data: pd.DataFrame,
        write: bool = True) -> ExperimentResult:
    run_id = "%s_%d" % (spec.key(), spec.seed)
    t_fit0 = time.perf_counter()
    train = data[data["split"] == spec.train_split]
    evald = data[data["split"] == spec.eval_split]
    if train.empty or evald.empty:
        return ExperimentResult(spec, "FAILED", run_id,
                                failure_reason="empty train or eval split")

    all_blocks = list(ds.FEATURE_BLOCKS)
    drop = [m for m in all_blocks if m not in spec.blocks]
    train_x = _drop_blocks(train, drop)
    eval_x = _drop_blocks(evald, drop)

    y_tr = train_x["is_episode"].to_numpy(int)
    y_ev = eval_x["is_episode"].to_numpy(int)

    try:
        model = AegisRiskModel(blocks=list(spec.blocks),
                               combination_rule=spec.combination_rule,
                               seed=spec.seed)
        model.fit(train_x, y_tr)
    except Exception as exc:
        return ExperimentResult(spec, "FAILED", run_id,
                                failure_reason="fit failed: %s: %s"
                                               % (type(exc).__name__, exc))
    fit_s = time.perf_counter() - t_fit0

    t_pred0 = time.perf_counter()
    pred = model.predict(eval_x)
    pred_s = time.perf_counter() - t_pred0

    # Threshold is chosen on the *training* split and applied unchanged to eval. Choosing
    # it on eval would leak the evaluation labels into the operating point (leakage L6).
    tr_pred = model.predict(train_x)
    thr = mx.best_f1_threshold(y_tr, tr_pred["integrity_risk"])

    det = mx.detection_metrics(y_ev, pred["integrity_risk"], threshold=thr)

    scored = evald[["symbol", "date", "is_episode", "episode_id", "t_entry", "t_exit",
                    "state", "intensity"]].copy()
    scored["integrity_risk"] = pred["integrity_risk"]
    scored["uncertainty"] = pred["uncertainty"]
    scored["coverage"] = pred["coverage"]
    for i, m in enumerate(pred["block_names"]):
        scored["score_%s" % m] = pred["block_scores"][:, i]
        scored["weight_%s" % m] = pred["block_weights"][:, i]
        scored["contrib_%s" % m] = pred["block_contribution"][:, i]

    cfg = st.StateConfig(**spec.state_config) if spec.state_config else st.StateConfig()
    scored = st.apply_to_frame(scored, "integrity_risk", cfg)
    pred_windows = st.windows_from_frame(scored, "integrity_risk", cfg)
    pw = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry, "t_exit": w.t_exit,
                        "t_peak": w.t_peak, "peak_score": w.peak_score,
                        "censored": w.censored} for w in pred_windows])
    tw = (scored[scored["is_episode"] == 1]
          .groupby(["symbol", "episode_id"])
          .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
          .reset_index())
    temporal = mx.temporal_metrics(tw, pw, scored["date"].drop_duplicates()) \
        if len(tw) and len(pw) else {"n_true_windows": int(len(tw)),
                                     "n_pred_windows": int(len(pw)),
                                     "note": "no matchable windows"}
    per_window = temporal.pop("per_window", None)

    res = ExperimentResult(
        spec, "OK", run_id, detection=det, temporal=temporal,
        operational=mx.operational_metrics(fit_s, pred_s, len(eval_x)),
        per_row=scored, model_summary=model.summary())

    if write:
        res.artifact_dir = str(_write_bundle(res, per_window))
    return res


def _write_bundle(res: ExperimentResult, per_window: pd.DataFrame | None) -> Path:
    d = paths.REPORTS / res.run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(
        json.dumps(asdict(res.spec), indent=2, default=str), encoding="utf-8")
    (d / "metrics.json").write_text(
        json.dumps({"detection": res.detection, "temporal": res.temporal,
                    "operational": res.operational, "status": res.status},
                   indent=2, default=str), encoding="utf-8")
    pd.DataFrame([res.to_record()]).to_csv(d / "metrics.csv", index=False)
    if res.per_row is not None:
        res.per_row.to_parquet(d / "per_row.parquet", index=False)
    if res.model_summary is not None:
        res.model_summary.to_csv(d / "model_summary.csv", index=False)
    if per_window is not None and len(per_window):
        per_window.to_csv(d / "per_window.csv", index=False)
    ReproducibilityManifest(
        experiment_id=res.spec.experiment_id, run_id=res.run_id, seed=res.spec.seed,
        config=asdict(res.spec), feature_version=ds.DATASET_VERSION,
        model_versions={"risk_model": "aegis-risk-v1"},
    ).write(d / "reproducibility_manifest.json")

    lines = [
        "# Experiment report: %s" % res.run_id,
        "",
        "**Hypothesis.** %s" % res.spec.hypothesis,
        "",
        "**Arm.** `%s` | blocks: %s | combiner: `%s`"
        % (res.spec.arm, ", ".join(res.spec.blocks) or "none",
           res.spec.combination_rule),
        "",
        "**Status.** %s" % res.status,
        "",
        "## Detection", "",
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
    lines += ["", "---", "",
              "Generated %s. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` "
              "L-04." % datetime.now(UTC).isoformat()]
    (d / "experiment_report.md").write_text("\n".join(lines), encoding="utf-8")
    return d


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return "NaN" if v != v else "%.4f" % v
    return str(v)


def results_table(results: list[ExperimentResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_record() for r in results])
