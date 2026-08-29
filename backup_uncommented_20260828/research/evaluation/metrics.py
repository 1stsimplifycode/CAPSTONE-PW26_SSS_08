"""Metrics (spec section 73).

Detection, calibration, temporal and operational metrics. Everything is computed from
arrays the caller already has; nothing is estimated from a model that is not shown.

Two choices worth flagging because they change conclusions:

* **AUPRC is the headline detection metric, not AUROC.** Episode days are a small
  minority of rows, and AUROC is optimistic under class imbalance. Both are reported;
  AUPRC is the one the abstract should quote, together with the positive rate, since
  AUPRC has no fixed chance baseline.
* **ECE uses equal-*mass* bins, not equal-width.** Equal-width bins leave the high
  confidence bins nearly empty on an imbalanced problem and produce an ECE dominated by
  a handful of points.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

METRICS_VERSION = "metrics-v2"


# -- detection ------------------------------------------------------------------------

def detection_metrics(y: np.ndarray, p: np.ndarray,
                      threshold: float | None = None) -> dict[str, float]:
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        precision_recall_fscore_support,
        roc_auc_score,
    )
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    y, p = y[ok], p[ok]
    out: dict[str, float] = {"n": float(len(y)), "positive_rate": float(y.mean())
                             if len(y) else np.nan}
    if len(np.unique(y)) < 2:
        out.update(dict.fromkeys(
            ("auprc", "auroc", "precision", "recall", "f1", "brier", "ece",
             "threshold"), np.nan))
        out["status"] = np.nan
        return out
    out["auprc"] = float(average_precision_score(y, p))
    out["auroc"] = float(roc_auc_score(y, p))
    out["brier"] = float(brier_score_loss(y, p))
    out["ece"] = expected_calibration_error(y, p)
    thr = threshold if threshold is not None else best_f1_threshold(y, p)
    out["threshold"] = float(thr)
    pr, rc, f1, _ = precision_recall_fscore_support(y, (p >= thr).astype(int),
                                                    average="binary", zero_division=0)
    out["precision"], out["recall"], out["f1"] = float(pr), float(rc), float(f1)
    #: AUPRC relative to the no-skill baseline (the positive rate). >1 means better than
    #: chance; the raw AUPRC alone is not comparable across splits with different rates.
    out["auprc_lift"] = float(out["auprc"] / max(1e-12, y.mean()))
    return out


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import precision_recall_curve
    pr, rc, th = precision_recall_curve(y, p)
    f1 = 2 * pr * rc / np.clip(pr + rc, 1e-12, None)
    if len(th) == 0:
        return 0.5
    return float(th[int(np.nanargmax(f1[:-1]))])


def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Equal-mass-binned ECE."""
    y = np.asarray(y).astype(float)
    p = np.asarray(p, dtype=float)
    if len(y) < n_bins:
        return float("nan")
    order = np.argsort(p)
    y, p = y[order], p[order]
    bins = np.array_split(np.arange(len(y)), n_bins)
    ece = 0.0
    for b in bins:
        if len(b) == 0:
            continue
        ece += len(b) / len(y) * abs(p[b].mean() - y[b].mean())
    return float(ece)


def reliability_curve(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    order = np.argsort(p)
    y, p = np.asarray(y)[order], np.asarray(p)[order]
    rows = []
    for b in np.array_split(np.arange(len(y)), n_bins):
        if len(b) == 0:
            continue
        rows.append({"mean_pred": float(p[b].mean()),
                     "observed": float(y[b].mean()), "n": int(len(b))})
    return pd.DataFrame(rows)



# -- classification / verification ----------------------------------------------------
#
# Added alongside the detection metrics above, not in place of them. ``detection_metrics``
# answers "how well does the score rank?"; this section answers "at the operating point we
# actually use, what does the classifier do, and how are its mistakes distributed?".
#
# **Denominator conventions.** Every rate below names its denominator explicitly, because
# the common failure is not a wrong formula but a right formula applied to an empty
# denominator and silently reported as 0.
#
#   precision           TP / (TP + FP)      over rows *predicted* positive
#   recall = TPR = sens TP / (TP + FN)      over rows *actually* positive
#   specificity = TNR   TN / (TN + FP)      over rows *actually* negative
#   FPR                 FP / (FP + TN)      = 1 - specificity
#   FNR                 FN / (FN + TP)      = 1 - recall
#   accuracy            (TP + TN) / n       over all rows
#   balanced accuracy   (recall + specificity) / 2
#   F1                  2PR / (P + R)
#   MCC                 (TP*TN - FP*FN) / sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN))
#
# **Undefined is reported as NaN, not as zero.** This deliberately differs from scikit
# learn's ``zero_division=0`` default, which ``detection_metrics`` keeps. A precision of
# 0.0 asserts that every positive call was wrong; when the model made no positive calls at
# all, that assertion is false and the honest value is "not defined on this sample". The
# exception is MCC, which follows the standard convention of 0.0 for a zero denominator
# because that case means "no better than chance", and it is flagged in
# ``mcc_denominator_zero`` so a reader can tell the two situations apart.
#
# ``tests/unit/test_classification_metrics.py`` checks every formula against hand-computed
# values, cross-checks the counts against scikit-learn, and asserts that this section and
# ``detection_metrics`` agree wherever both are defined.

#: Class label -> human name, used for the per-class breakdown. The problem is binary:
#: an instrument-session either falls inside a labelled integrity-risk episode or it does
#: not.
CLASS_NAMES = {0: "no_episode", 1: "episode"}


def _safe_ratio(numerator: float, denominator: float) -> float:
    """``numerator / denominator``, or NaN when the denominator is empty."""
    return float(numerator) / float(denominator) if denominator else float("nan")


def _finite_pair(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop rows whose score is not finite, mirroring ``detection_metrics``."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    return y[ok], p[ok]


def confusion_counts(y: np.ndarray, y_pred: np.ndarray) -> dict[str, int]:
    """TP, TN, FP and FN from two hard 0/1 label arrays.

    Computed directly rather than by indexing a library confusion matrix, because that
    indexing silently changes meaning when a class is absent from the sample and the
    matrix comes back 1x1.
    """
    y = np.asarray(y).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    if y.shape != y_pred.shape:
        raise ValueError("y and y_pred have different shapes: %s vs %s"
                         % (y.shape, y_pred.shape))
    return {
        "tp": int(np.sum((y == 1) & (y_pred == 1))),
        "tn": int(np.sum((y == 0) & (y_pred == 0))),
        "fp": int(np.sum((y == 0) & (y_pred == 1))),
        "fn": int(np.sum((y == 1) & (y_pred == 0))),
    }


def classification_metrics(y: np.ndarray, p: np.ndarray,
                           threshold: float) -> dict[str, float]:
    """Full verification suite at a *given* operating threshold.

    ``threshold`` is required rather than optional on purpose. Choosing it from the same
    data the metrics are computed on is threshold-provenance leakage (leakage test L6);
    the caller must pass the value that was selected on the training split.
    """
    y, p = _finite_pair(y, p)
    n = int(len(y))
    if n == 0:
        return {"n": 0, "status": "NOT MEASURABLE: no finite rows"}

    y_pred = (p >= float(threshold)).astype(int)
    c = confusion_counts(y, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]

    n_pos, n_neg = tp + fn, tn + fp
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, n_pos)
    specificity = _safe_ratio(tn, n_neg)

    # F1 is 0.0, not NaN, when the model made calls but got no true positive: that is a
    # real score of zero. It is NaN only when there is nothing at all to score.
    if tp + fp + fn == 0:
        f1 = float("nan")
    elif tp == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    mcc_den = np.sqrt(float(tp + fp) * float(tp + fn)
                      * float(tn + fp) * float(tn + fn))
    mcc = 0.0 if mcc_den == 0 else float((tp * tn - fp * fn) / mcc_den)

    ba = ((recall + specificity) / 2.0
          if (recall == recall and specificity == specificity) else float("nan"))

    return {
        "n": n,
        "threshold": float(threshold),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "n_positive": int(n_pos), "n_negative": int(n_neg),
        "n_predicted_positive": int(tp + fp),
        "positive_rate": _safe_ratio(n_pos, n),
        "predicted_positive_rate": _safe_ratio(tp + fp, n),
        "accuracy": _safe_ratio(tp + tn, n),
        "balanced_accuracy": ba,
        "precision": precision,
        "recall": recall,
        "sensitivity": recall,
        "specificity": specificity,
        "f1": f1,
        "mcc": mcc,
        "mcc_denominator_zero": bool(mcc_den == 0),
        "fpr": _safe_ratio(fp, n_neg),
        "fnr": _safe_ratio(fn, n_pos),
        "status": "OK",
    }


def confusion_matrix_frame(y: np.ndarray, p: np.ndarray,
                           threshold: float) -> pd.DataFrame:
    """The 2x2 confusion matrix as a labelled frame: rows actual, columns predicted."""
    y, p = _finite_pair(y, p)
    c = confusion_counts(y, (p >= float(threshold)).astype(int))
    return pd.DataFrame(
        [[c["tn"], c["fp"]], [c["fn"], c["tp"]]],
        index=pd.Index(["actual_%s" % CLASS_NAMES[0], "actual_%s" % CLASS_NAMES[1]],
                       name="actual"),
        columns=pd.Index(["predicted_%s" % CLASS_NAMES[0],
                          "predicted_%s" % CLASS_NAMES[1]], name="predicted"),
    )


def per_class_report(y: np.ndarray, p: np.ndarray, threshold: float) -> pd.DataFrame:
    """Precision, recall, F1 and support for each class, plus macro and weighted F1.

    The negative class is reported as well as the positive one because a detector on an
    imbalanced problem can look strong on the majority class while failing the minority
    class that the research is actually about.
    """
    y, p = _finite_pair(y, p)
    y_pred = (p >= float(threshold)).astype(int)
    c = confusion_counts(y, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]

    # For the negative class the roles swap: a "true positive" for class 0 is a TN.
    per_class = {
        1: {"tp": tp, "fp": fp, "fn": fn},
        0: {"tp": tn, "fp": fn, "fn": fp},
    }
    rows = []
    for label in (0, 1):
        v = per_class[label]
        pr = _safe_ratio(v["tp"], v["tp"] + v["fp"])
        rc = _safe_ratio(v["tp"], v["tp"] + v["fn"])
        if v["tp"] + v["fp"] + v["fn"] == 0:
            f1 = float("nan")
        elif v["tp"] == 0:
            f1 = 0.0
        else:
            f1 = 2 * pr * rc / (pr + rc)
        rows.append({"class": label, "class_name": CLASS_NAMES[label],
                     "support": int(v["tp"] + v["fn"]),
                     "precision": pr, "recall": rc, "f1": f1})

    tbl = pd.DataFrame(rows)
    support = tbl["support"].to_numpy(float)
    f1s = tbl["f1"].to_numpy(float)
    macro = float(np.nanmean(f1s)) if np.isfinite(f1s).any() else float("nan")
    weighted = (float(np.nansum(f1s * support) / support.sum())
                if support.sum() else float("nan"))
    tbl.attrs["macro_f1"] = macro
    tbl.attrs["weighted_f1"] = weighted
    return tbl


def verification_report(y: np.ndarray, p: np.ndarray,
                        threshold: float) -> dict[str, object]:
    """Everything in this section in one record, for an artifact writer to serialise."""
    per_class = per_class_report(y, p, threshold)
    return {
        "metrics": classification_metrics(y, p, threshold),
        "confusion_matrix": confusion_matrix_frame(y, p, threshold).to_dict(),
        "per_class": per_class.to_dict(orient="records"),
        "macro_f1": per_class.attrs["macro_f1"],
        "weighted_f1": per_class.attrs["weighted_f1"],
        "threshold_provenance": (
            "The threshold must be supplied by the caller and must have been selected on "
            "the training split. Choosing it on the evaluation split would be threshold "
            "provenance leakage (L6)."),
    }


# -- temporal -------------------------------------------------------------------------

def lead_time(true_entry: pd.Timestamp, pred_entry: pd.Timestamp | None,
              sessions: pd.Series) -> float:
    """Sessions between predicted and true entry. Positive = detected early.

    Counted in *trading sessions*, not calendar days, so a long weekend is not credited
    as three days of lead.
    """
    if pred_entry is None or pd.isna(true_entry):
        return np.nan
    s = pd.Series(pd.to_datetime(sessions.to_numpy())).sort_values().reset_index(
        drop=True)
    i_true = int(s.searchsorted(pd.Timestamp(true_entry)))
    i_pred = int(s.searchsorted(pd.Timestamp(pred_entry)))
    return float(i_true - i_pred)


def temporal_iou(a_start, a_end, b_start, b_end) -> float:
    """Intersection over union of two closed intervals, in days."""
    if any(pd.isna(x) for x in (a_start, b_start)):
        return np.nan
    a_end = a_end if not pd.isna(a_end) else a_start
    b_end = b_end if not pd.isna(b_end) else b_start
    a0, a1 = pd.Timestamp(a_start), pd.Timestamp(a_end)
    b0, b1 = pd.Timestamp(b_start), pd.Timestamp(b_end)
    inter = (min(a1, b1) - max(a0, b0)).days + 1
    if inter <= 0:
        return 0.0
    union = (max(a1, b1) - min(a0, b0)).days + 1
    return float(inter / union) if union > 0 else 0.0


def temporal_metrics(true_windows: pd.DataFrame, pred_windows: pd.DataFrame,
                     sessions: pd.Series, match_tolerance_days: int = 20) -> dict:
    """Match predicted windows to true windows and summarise the timing errors.

    Matching is greedy on temporal overlap within a symbol, with a tolerance so that a
    prediction which starts shortly before the true entry still counts as a detection.
    Unmatched true windows are misses; unmatched predictions are false alarms.
    """
    rows = []
    used: set[int] = set()
    for _, t in true_windows.iterrows():
        cands = pred_windows[pred_windows["symbol"] == t["symbol"]]
        best, best_i = None, None
        for i, c in cands.iterrows():
            if i in used:
                continue
            gap = abs((pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days)
            if gap > match_tolerance_days:
                continue
            iou = temporal_iou(t["t_entry"], t["t_exit"], c["t_entry"], c["t_exit"])
            if best is None or iou > best[0]:
                best, best_i = (iou, c), i
        if best is None:
            rows.append({"symbol": t["symbol"], "matched": False,
                         "lead_time": np.nan, "onset_error": np.nan,
                         "resolution_error": np.nan, "iou": 0.0,
                         "duration_error": np.nan})
            continue
        used.add(best_i)
        iou, c = best
        onset = (pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days
        if pd.isna(t["t_exit"]) or pd.isna(c["t_exit"]):
            res = np.nan
            dur = np.nan
        else:
            res = (pd.Timestamp(c["t_exit"]) - pd.Timestamp(t["t_exit"])).days
            dur = ((pd.Timestamp(c["t_exit"]) - pd.Timestamp(c["t_entry"])).days
                   - (pd.Timestamp(t["t_exit"]) - pd.Timestamp(t["t_entry"])).days)
        rows.append({"symbol": t["symbol"], "matched": True,
                     "lead_time": lead_time(t["t_entry"], c["t_entry"], sessions),
                     "onset_error": float(onset), "resolution_error": res,
                     "iou": float(iou), "duration_error": dur})
    d = pd.DataFrame(rows)
    n_true = len(true_windows)
    n_pred = len(pred_windows)
    matched = int(d["matched"].sum()) if len(d) else 0
    m = d[d["matched"]] if len(d) else d
    return {
        "n_true_windows": n_true, "n_pred_windows": n_pred,
        "n_matched": matched,
        "detection_rate": float(matched / n_true) if n_true else np.nan,
        "false_alarm_windows": int(n_pred - matched),
        "mean_lead_time": float(m["lead_time"].mean()) if len(m) else np.nan,
        "median_lead_time": float(m["lead_time"].median()) if len(m) else np.nan,
        "mean_onset_error": float(m["onset_error"].mean()) if len(m) else np.nan,
        "mean_abs_onset_error": float(m["onset_error"].abs().mean())
        if len(m) else np.nan,
        "mean_resolution_error": float(m["resolution_error"].mean())
        if len(m) else np.nan,
        "mean_temporal_iou": float(m["iou"].mean()) if len(m) else np.nan,
        "mean_duration_error": float(m["duration_error"].mean())
        if len(m) else np.nan,
        "premature_resolution_rate": float((m["resolution_error"] < -2).mean())
        if len(m) else np.nan,
        "delayed_resolution_rate": float((m["resolution_error"] > 2).mean())
        if len(m) else np.nan,
        "per_window": d,
    }


# -- error taxonomy -------------------------------------------------------------------

ERROR_CLASSES = ["FALSE_POSITIVE", "FALSE_NEGATIVE", "EARLY_DETECTION",
                 "LATE_DETECTION", "FALSE_RESOLUTION", "PERSISTENT_ALERT",
                 "MISSING_EVIDENCE", "CONFLICTING_EVIDENCE", "DATA_QUALITY",
                 "MODEL_FAILURE"]


def classify_errors(df: pd.DataFrame, threshold: float,
                    score_col: str = "integrity_risk") -> pd.DataFrame:
    """Assign one error class per row (or ``CORRECT``).

    The taxonomy is deliberately ordered: data problems are diagnosed before model
    problems, because a row with no evidence is not a model failure.
    """
    out = df.copy()
    pred = (out[score_col] >= threshold).astype(int)
    truth = out["is_episode"].astype(int)
    cov = out[[c for c in ("cov_market", "cov_micro", "cov_regime",
                           "cov_propagation") if c in out.columns]]
    coverage = cov.mean(axis=1) if len(cov.columns) else pd.Series(1.0,
                                                                   index=out.index)
    disagree = out["uncertainty"] if "uncertainty" in out.columns else pd.Series(
        0.0, index=out.index)

    cls = pd.Series("CORRECT", index=out.index, dtype=object)
    cls[(pred == 1) & (truth == 0)] = "FALSE_POSITIVE"
    cls[(pred == 0) & (truth == 1)] = "FALSE_NEGATIVE"
    cls[(coverage < 0.5)] = "MISSING_EVIDENCE"
    cls[(pred != truth) & (disagree > 0.6)] = "CONFLICTING_EVIDENCE"
    if "cov_market" in out.columns:
        cls[out["cov_market"] < 0.5] = "DATA_QUALITY"
    out["error_class"] = cls
    return out


# -- operational ----------------------------------------------------------------------

def operational_metrics(fit_seconds: float, predict_seconds: float, n_rows: int,
                        peak_memory_mb: float | None = None) -> dict:
    return {
        "fit_seconds": float(fit_seconds),
        "predict_seconds": float(predict_seconds),
        "rows": int(n_rows),
        "throughput_rows_per_s": float(n_rows / predict_seconds)
        if predict_seconds > 0 else np.nan,
        "latency_ms_per_row": float(1000.0 * predict_seconds / n_rows)
        if n_rows else np.nan,
        "peak_memory_mb": peak_memory_mb,
    }
