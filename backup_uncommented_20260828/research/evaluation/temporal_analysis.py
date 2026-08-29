"""Temporal analyses that turn the late-detection negative into a measurement.

Two questions the headline lead-time number cannot answer:

1. **Is late detection a choice or a limit?** The state machine trades latency for
   precision through its entry threshold. Sweeping that threshold traces the achievable
   frontier, which distinguishes "the detector is tuned conservatively" from "the
   evidence itself arrives late".

2. **Do blocks carry evidence at different lags?** Cross-correlating each block's
   own score against the episode indicator over a range of lags shows whether text leads
   market, or whether everything moves together because everything derives from the same
   series (L-09).

Both operate on artifacts already on disk. Neither requires new data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.detection import state as st
from research.evaluation import metrics as mx

TEMPORAL_VERSION = "temporal-analysis-v1"


def lead_time_frontier(scored: pd.DataFrame,
                       thresholds: tuple[float, ...] = (0.20, 0.25, 0.30, 0.35, 0.40,
                                                        0.45, 0.50, 0.55, 0.60, 0.65,
                                                        0.70, 0.80, 0.90),
                       exit_gap: float = 0.15) -> pd.DataFrame:
    """Sweep the state-machine entry threshold and record the timing/precision pair.

    ``exit_gap`` keeps the exit threshold a fixed distance below entry so the hysteresis
    structure is preserved as the operating point moves; without that the sweep would
    conflate two changes.
    """
    truth = (scored[scored["is_episode"] == 1]
             .groupby(["symbol", "episode_id"])
             .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
             .reset_index())
    sessions = scored["date"].drop_duplicates()
    rows = []
    for thr in thresholds:
        cfg = st.StateConfig(enter_threshold=thr,
                             exit_threshold=max(0.05, thr - exit_gap),
                             early_warning_threshold=max(0.03, thr - exit_gap - 0.05))
        wins = st.windows_from_frame(scored, "integrity_risk", cfg)
        pred = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry,
                              "t_exit": w.t_exit, "censored": w.censored}
                             for w in wins])
        if pred.empty or truth.empty:
            rows.append({"entry_threshold": thr, "n_pred_windows": int(len(pred)),
                         "status": "NO WINDOWS"})
            continue
        tm = mx.temporal_metrics(truth, pred, sessions)
        per = tm.pop("per_window")
        matched = int(tm["n_matched"])
        n_pred = int(tm["n_pred_windows"])
        rows.append({
            "entry_threshold": thr,
            "n_pred_windows": n_pred,
            "n_matched": matched,
            "detection_rate": tm["detection_rate"],
            "window_precision": float(matched / n_pred) if n_pred else np.nan,
            "false_alarm_windows": tm["false_alarm_windows"],
            "median_lead_time": tm["median_lead_time"],
            "mean_lead_time": tm["mean_lead_time"],
            "mean_temporal_iou": tm["mean_temporal_iou"],
            "positive_lead_fraction": float(np.mean(
                per["lead_time"].dropna() > 0)) if per["lead_time"].notna().any()
            else np.nan,
            "status": "OK",
        })
    return pd.DataFrame(rows)


def block_lead_lag(scored: pd.DataFrame, blocks: list[str],
                      max_lag: int = 20) -> pd.DataFrame:
    """Cross-correlation of each block score against the episode indicator.

    Positive lag means the block score moves *before* the episode indicator, i.e. the
    block leads. Correlations are computed per instrument and averaged across
    instruments, so a single long series cannot dominate.
    """
    rows = []
    for mod in blocks:
        col = "score_%s" % mod
        if col not in scored.columns:
            rows.append({"block": mod, "status": "ABSENT"})
            continue
        per_sym = []
        for _sym, g in scored.sort_values(["symbol", "date"]).groupby("symbol"):
            s = g[col].to_numpy(float)
            y = g["is_episode"].to_numpy(float)
            if len(s) < 3 * max_lag or np.nanstd(s) == 0 or np.nanstd(y) == 0:
                continue
            s = (s - np.nanmean(s)) / np.nanstd(s)
            y = (y - np.nanmean(y)) / np.nanstd(y)
            cors = []
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    a, b = s[-lag:], y[:len(y) + lag]
                elif lag > 0:
                    a, b = s[:len(s) - lag], y[lag:]
                else:
                    a, b = s, y
                if len(a) < 30:
                    cors.append(np.nan)
                    continue
                cors.append(float(np.nanmean(a * b)))
            per_sym.append(cors)
        if not per_sym:
            rows.append({"block": mod, "status": "INSUFFICIENT DATA"})
            continue
        mean_cor = np.nanmean(np.vstack(per_sym), axis=0)
        lags = np.arange(-max_lag, max_lag + 1)
        best = int(np.nanargmax(mean_cor))
        rows.append({
            "block": mod,
            "peak_lag_sessions": int(lags[best]),
            "peak_correlation": float(mean_cor[best]),
            "correlation_at_zero": float(mean_cor[max_lag]),
            "n_instruments": len(per_sym),
            "status": "OK",
            "interpretation": ("leads the episode indicator"
                               if lags[best] > 0 else
                               "lags the episode indicator" if lags[best] < 0
                               else "coincident"),
            "_curve_lags": lags.tolist(),
            "_curve_values": [float(v) for v in mean_cor],
        })
    return pd.DataFrame(rows)


def onset_peak_resolution_scores(scored: pd.DataFrame,
                                 cfg: st.StateConfig | None = None) -> dict:
    """Score the three lifecycle sub-tasks separately (research-angle section 26).

    Treating detection as one scalar hides that onset, peak and resolution are different
    problems with different difficulty. Each is scored against the injected ground truth.
    """
    cfg = cfg or st.StateConfig()
    truth = (scored[scored["is_episode"] == 1]
             .groupby(["symbol", "episode_id"])
             .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
             .reset_index())
    if truth.empty:
        return {"status": "NO EPISODES"}
    wins = st.windows_from_frame(scored, "integrity_risk", cfg)
    pred = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry, "t_exit": w.t_exit,
                          "t_peak": w.t_peak, "censored": w.censored} for w in wins])
    if pred.empty:
        return {"status": "NO PREDICTED WINDOWS"}

    onset_err, resolution_err, matched = [], [], 0
    used: set[int] = set()
    for _, t in truth.iterrows():
        cands = pred[pred["symbol"] == t["symbol"]]
        best_i, best_gap = None, None
        for i, c in cands.iterrows():
            if i in used:
                continue
            gap = abs((pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days)
            if gap <= 20 and (best_gap is None or gap < best_gap):
                best_i, best_gap = i, gap
        if best_i is None:
            continue
        used.add(best_i)
        matched += 1
        c = pred.loc[best_i]
        onset_err.append((pd.Timestamp(c["t_entry"])
                          - pd.Timestamp(t["t_entry"])).days)
        if not pd.isna(t["t_exit"]) and c["t_exit"] is not None \
                and not pd.isna(c["t_exit"]):
            resolution_err.append((pd.Timestamp(c["t_exit"])
                                   - pd.Timestamp(t["t_exit"])).days)

    def _s(v, name):
        v = np.asarray(v, dtype=float)
        if v.size == 0:
            return {"task": name, "n": 0, "status": "NOT MEASURED"}
        return {"task": name, "n": int(v.size), "mean_error_days": float(v.mean()),
                "median_error_days": float(np.median(v)),
                "mean_abs_error_days": float(np.abs(v).mean()),
                "within_3_days": float(np.mean(np.abs(v) <= 3)),
                "status": "OK"}

    return {
        "status": "OK",
        "n_true": int(len(truth)),
        "n_pred": int(len(pred)),
        "n_matched": matched,
        "onset": _s(onset_err, "onset"),
        "resolution": _s(resolution_err, "resolution"),
        "note": ("Peak timing is not scored separately: the injected schedule places a "
                 "peak phase but the detector's peak is the argmax of a noisy score, so "
                 "a peak-timing error would mostly measure score noise."),
    }


def asynchrony_sensitivity(data: pd.DataFrame, model, block: str,
                           block_columns: list[str],
                           offsets: tuple[int, ...] = (0, 1, 3, 5, 10, 20),
                           y_col: str = "is_episode") -> pd.DataFrame:
    """Shift one block's features forward in time and measure the damage.

    Simulates cross-block temporal misalignment: evidence that arrives *later* than the
    system assumes. Shifting forward (not backward) is the realistic direction, since
    a real feed is delayed relative to market data, never early.
    """
    rows = []
    base = data.copy()
    for off in offsets:
        d = base.copy()
        if off > 0:
            d = d.sort_values(["symbol", "date"])
            shifted = d.groupby("symbol")[block_columns].shift(off)
            for c in block_columns:
                d[c] = shifted[c]
        try:
            p = model.predict(d)["integrity_risk"]
            m = mx.detection_metrics(d[y_col].to_numpy(int), p)
            rows.append({"block": block, "offset_sessions": off,
                         "auprc": m["auprc"], "auroc": m["auroc"], "ece": m["ece"],
                         "status": "OK"})
        except Exception as exc:
            rows.append({"block": block, "offset_sessions": off,
                         "status": "FAILED: %s" % type(exc).__name__})
    return pd.DataFrame(rows)
