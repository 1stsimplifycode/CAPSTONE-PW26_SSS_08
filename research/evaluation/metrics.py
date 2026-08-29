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

PLAIN ENGLISH -- what this whole file is about:

HOW DO YOU SCORE THE SCORER? This file holds the measuring tapes.

THE FIRST BIG CHOICE, and it changes the headline number.

Imagine testing a machine that spots a rare disease affecting 1 person in 100.
A machine that says "healthy" to absolutely everybody is right 99% of the time. It is
also completely worthless -- it has never found a single sick person.

That is the trap of RARE events, and it is exactly this project's situation: trouble
happens on a small minority of days. So the measure you choose matters enormously.

  AUROC is the popular measure. On rare-event problems it flatters -- it can look
    impressive while the system is finding almost nothing.
  AUPRC concentrates on the rare cases and is far harder to fool.

This project quotes AUPRC as its headline, which is the harder, less flattering choice.
And it always quotes the POSITIVE RATE alongside -- because AUPRC has no fixed "chance"
level: 0.3 is superb when trouble is 1% of days and dreadful when it is 40%. Giving the
number without the rate would be uninterpretable.

THE SECOND BIG CHOICE, about measuring honesty.

When the model says "70% chance", does trouble really follow about 70% of the time? The
measure of that is called ECE, and it works by grouping predictions into bins.
  EQUAL-WIDTH bins split the range 0-1 into ten equal slices. On a rare-event problem,
    the top slices end up nearly EMPTY -- so the score gets decided by a handful of
    points and jumps about wildly.
  EQUAL-MASS bins put the same NUMBER of predictions in each bin. Every bin then carries
    real weight.
The second is used here. Again the less convenient, more correct choice.

AND THE RULE THAT RUNS THROUGH THE MIDDLE SECTION: when a measurement cannot be computed,
this file reports "not defined" rather than zero. That distinction is explained at length
below, and it matters more than it sounds.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version of the measurements.
METRICS_VERSION = "metrics-v2"


# -- detection ------------------------------------------------------------------------

# How well does the score separate trouble from calm?
def detection_metrics(y: np.ndarray, p: np.ndarray,
                      threshold: float | None = None) -> dict[str, float]:
    from sklearn.metrics import (
        # AUPRC -- the rare-event-friendly measure.
        average_precision_score,
        # How far the probabilities were from the truth, squared.
        brier_score_loss,
        # The at-a-threshold measures.
        precision_recall_fscore_support,
        # AUROC -- the popular one.
        roc_auc_score,
    )
    # `y` is the truth (1 for trouble, 0 for calm); `p` is the model's score.
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    # Drop rows with no usable score.
    ok = np.isfinite(p)
    y, p = y[ok], p[ok]
    # Always report how much data, and how often trouble occurred. The positive rate is not
    # decoration -- without it, AUPRC below cannot be interpreted at all.
    out: dict[str, float] = {"n": float(len(y)), "positive_rate": float(y.mean())
                             if len(y) else np.nan}
    # Only one kind of answer present? Every measure below is undefined. Report all of them
    # as unknown rather than computing something meaningless that would look real.
    if len(np.unique(y)) < 2:
        out.update(dict.fromkeys(
            ("auprc", "auroc", "precision", "recall", "f1", "brier", "ece",
             "threshold"), np.nan))
        out["status"] = np.nan
        return out
    # THE HEADLINE, and the honest one.
    out["auprc"] = float(average_precision_score(y, p))
    # The flattering one, reported alongside for comparison rather than suppressed.
    out["auroc"] = float(roc_auc_score(y, p))
    # How far off the probabilities were. Lower is better.
    out["brier"] = float(brier_score_loss(y, p))
    # How honest the probabilities were.
    out["ece"] = expected_calibration_error(y, p)
    # A cut-off for turning scores into yes/no answers.
    thr = threshold if threshold is not None else best_f1_threshold(y, p)
    out["threshold"] = float(thr)
    # Precision: of the days we flagged, how many were really trouble.
    # Recall: of the real trouble, how much we caught.
    # F1: a single number balancing the two.
    pr, rc, f1, _ = precision_recall_fscore_support(y, (p >= thr).astype(int),
                                                    average="binary", zero_division=0)
    out["precision"], out["recall"], out["f1"] = float(pr), float(rc), float(f1)
    #: AUPRC relative to the no-skill baseline (the positive rate). >1 means better than
    #: chance; the raw AUPRC alone is not comparable across splits with different rates.
    # PLAIN ENGLISH: this solves the interpretation problem directly. Divide the AUPRC by
    # the rate at which trouble actually occurs, and you get "how many times better than
    # guessing". A lift of 5 means five times better than chance -- and unlike raw AUPRC,
    # that number means the same thing on every dataset, so two splits become comparable.
    out["auprc_lift"] = float(out["auprc"] / max(1e-12, y.mean()))
    return out


# Find the cut-off that balances precision and recall best.
def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import precision_recall_curve
    # Every possible cut-off, with the precision and recall each would give.
    pr, rc, th = precision_recall_curve(y, p)
    # F1 at each: the "harmonic mean", which unlike a plain average punishes being
    # lopsided. Scoring brilliantly on one and terribly on the other gives a poor F1, which
    # is exactly what you want from a balance measure.
    f1 = 2 * pr * rc / np.clip(pr + rc, 1e-12, None)
    # No thresholds at all: fall back to the neutral middle.
    if len(th) == 0:
        return 0.5
    # `f1[:-1]` drops the last entry, which has no matching threshold -- a quirk of how the
    # curve is returned. `nanargmax` finds the best while ignoring unknowns.
    return float(th[int(np.nanargmax(f1[:-1]))])


# How honest are the probabilities?
def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Equal-mass-binned ECE."""
    # PLAIN ENGLISH: take all the days where the model said "about 70%", and check what
    # fraction really had trouble. If it is 70%, perfect. If it is 40%, the model is
    # overconfident. ECE averages that gap across all the bins, weighted by bin size.
    y = np.asarray(y).astype(float)
    p = np.asarray(p, dtype=float)
    # Fewer rows than bins: cannot bin meaningfully.
    if len(y) < n_bins:
        return float("nan")
    # Sort by the model's score, so similar predictions sit together.
    order = np.argsort(p)
    y, p = y[order], p[order]
    # THE EQUAL-MASS CHOICE: `array_split` cuts the sorted list into ten pieces of the SAME
    # SIZE. Not ten equal slices of the 0-1 range -- ten equal groups of predictions. This
    # single line is the design decision flagged at the top of the file.
    bins = np.array_split(np.arange(len(y)), n_bins)
    ece = 0.0
    for b in bins:
        if len(b) == 0:
            continue
        # For each bin: how far the average prediction was from the actual rate, weighted by
        # what share of the data this bin holds.
        ece += len(b) / len(y) * abs(p[b].mean() - y[b].mean())
    return float(ece)


# The same information as a table, for drawing a calibration chart.
def reliability_curve(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    order = np.argsort(p)
    y, p = np.asarray(y)[order], np.asarray(p)[order]
    rows = []
    for b in np.array_split(np.arange(len(y)), n_bins):
        if len(b) == 0:
            continue
        # Plotted against each other, a perfect model gives a straight diagonal line.
        # `n` is included so a reader can see which points rest on plenty of data.
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
#
# PLAIN ENGLISH for this whole section:
#
# The section above asked "does the score put the right things at the top?". This section
# asks a different question: "once we draw a line and start actually saying yes or no,
# what happens, and what kind of mistakes do we make?"
#
# FOUR OUTCOMES ARE POSSIBLE, and everything here is built from them:
#   TP -- true positive:  we said trouble, and there was trouble.       Right.
#   TN -- true negative:  we said calm, and it was calm.                Right.
#   FP -- false positive: we said trouble, and there was none.          A false alarm.
#   FN -- false negative: we said calm, and there was trouble.          A miss.
#
# THE "UNDEFINED IS NOT ZERO" RULE deserves the space it gets, because it is subtle and it
# genuinely misleads people.
# Suppose the model flagged NOTHING all year. What is its precision -- the share of its
# alarms that were right? There were no alarms. There is no share. The question has no
# answer.
# The popular libraries answer 0.0, which reads as "every alarm it raised was wrong". That
# is a factual claim, and it is FALSE -- it raised none. Worse, a 0.0 sits quietly in a
# results table looking like a measurement, and gets averaged in with real ones.
# So this file says "not defined on this sample". Less tidy, and true.
# The one exception is MCC, where 0.0 is the accepted convention for "no better than
# chance" -- and even there a separate flag records that the denominator was empty, so the
# two situations can still be told apart.

#: Class label -> human name, used for the per-class breakdown. The problem is binary:
#: an instrument-session either falls inside a labelled integrity-risk episode or it does
#: not.
CLASS_NAMES = {0: "no_episode", 1: "episode"}


# Divide safely, saying "unknown" instead of crashing on an empty denominator.
def _safe_ratio(numerator: float, denominator: float) -> float:
    """``numerator / denominator``, or NaN when the denominator is empty."""
    # `if denominator` is false for 0, so an empty denominator hands back NaN. This one tiny
    # helper is what implements the rule described above, everywhere it applies.
    return float(numerator) / float(denominator) if denominator else float("nan")


# Drop rows with no usable score, exactly as the section above does.
def _finite_pair(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop rows whose score is not finite, mirroring ``detection_metrics``."""
    # "Mirroring" is the point: both sections must throw away the same rows, or their
    # numbers would silently be about different datasets and could not be compared.
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    return y[ok], p[ok]


# Count the four outcomes.
def confusion_counts(y: np.ndarray, y_pred: np.ndarray) -> dict[str, int]:
    """TP, TN, FP and FN from two hard 0/1 label arrays.

    Computed directly rather than by indexing a library confusion matrix, because that
    indexing silently changes meaning when a class is absent from the sample and the
    matrix comes back 1x1.
    """
    # PLAIN ENGLISH: a real trap avoided. The library function normally returns a 2x2 grid,
    # and you read the corners by position. But if the sample contains only one kind of
    # answer, it returns a 1x1 grid instead -- and the position you were reading now means
    # something completely different. No error, no warning, just wrong numbers.
    # Counting directly cannot go wrong that way.
    y = np.asarray(y).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    # Mismatched lengths would silently compare the wrong pairs, so refuse outright.
    if y.shape != y_pred.shape:
        raise ValueError("y and y_pred have different shapes: %s vs %s"
                         % (y.shape, y_pred.shape))
    # `&` means "and", applied to every row at once. `.sum()` counts the Trues.
    return {
        # Said trouble, was trouble.
        "tp": int(np.sum((y == 1) & (y_pred == 1))),
        # Said calm, was calm.
        "tn": int(np.sum((y == 0) & (y_pred == 0))),
        # Said trouble, was calm -- a false alarm.
        "fp": int(np.sum((y == 0) & (y_pred == 1))),
        # Said calm, was trouble -- a miss.
        "fn": int(np.sum((y == 1) & (y_pred == 0))),
    }


# The full at-a-threshold report.
def classification_metrics(y: np.ndarray, p: np.ndarray,
                           threshold: float) -> dict[str, float]:
    """Full verification suite at a *given* operating threshold.

    ``threshold`` is required rather than optional on purpose. Choosing it from the same
    data the metrics are computed on is threshold-provenance leakage (leakage test L6);
    the caller must pass the value that was selected on the training split.
    """
    # PLAIN ENGLISH: another leak, and a sneaky one. If you pick the cut-off that works best
    # on the test data and then report how well that cut-off does on the test data, you have
    # tuned on the exam paper. Your score will be flattering and unreproducible.
    # The fix is structural: the cut-off is a REQUIRED argument with no default. There is no
    # way to call this function without having chosen one somewhere else -- ideally on the
    # practice data. Making it required is what closes the door.
    y, p = _finite_pair(y, p)
    n = int(len(y))
    # No usable rows: say so in words, rather than returning a table of zeros.
    if n == 0:
        return {"n": 0, "status": "NOT MEASURABLE: no finite rows"}

    # Turn scores into yes/no answers at the given cut-off.
    y_pred = (p >= float(threshold)).astype(int)
    c = confusion_counts(y, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]

    # How many were really trouble, and how many really calm.
    n_pos, n_neg = tp + fn, tn + fp
    # Of our alarms, how many were right.
    precision = _safe_ratio(tp, tp + fp)
    # Of the real trouble, how much we caught.
    recall = _safe_ratio(tp, n_pos)
    # Of the real calm, how much we correctly left alone.
    specificity = _safe_ratio(tn, n_neg)

    # F1 is 0.0, not NaN, when the model made calls but got no true positive: that is a
    # real score of zero. It is NaN only when there is nothing at all to score.
    # PLAIN ENGLISH: the distinction applied carefully. "It tried and got everything wrong"
    # genuinely deserves a zero. "There was nothing to try" deserves "not defined". Same
    # blank-looking situation on the surface; completely different meanings underneath.
    if tp + fp + fn == 0:
        f1 = float("nan")
    elif tp == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    # MCC -- the Matthews Correlation Coefficient. It uses all four outcomes at once, which
    # makes it the most trustworthy single number on an imbalanced problem: unlike accuracy,
    # it cannot be fooled by a model that simply always says "calm".
    # +1 perfect, 0 no better than chance, -1 perfectly wrong.
    mcc_den = np.sqrt(float(tp + fp) * float(tp + fn)
                      * float(tn + fp) * float(tn + fn))
    mcc = 0.0 if mcc_den == 0 else float((tp * tn - fp * fn) / mcc_den)

    # Balanced accuracy: the average of how well we do on each class SEPARATELY. That is
    # what stops the rare class being drowned out, as it is in plain accuracy.
    # `recall == recall` is the quick NaN check -- only NaN fails to equal itself.
    ba = ((recall + specificity) / 2.0
          if (recall == recall and specificity == specificity) else float("nan"))

    return {
        "n": n,
        "threshold": float(threshold),
        # The four raw counts, so a reader can recompute anything below from scratch.
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "n_positive": int(n_pos), "n_negative": int(n_neg),
        "n_predicted_positive": int(tp + fp),
        # How often trouble occurred, and how often we called it.
        "positive_rate": _safe_ratio(n_pos, n),
        "predicted_positive_rate": _safe_ratio(tp + fp, n),
        # Plain accuracy -- reported, but never the headline, for the reason at the top.
        "accuracy": _safe_ratio(tp + tn, n),
        "balanced_accuracy": ba,
        "precision": precision,
        "recall": recall,
        # Same number, second name. Different fields call it different things, and offering
        # both spares a reader having to know they are the same.
        "sensitivity": recall,
        "specificity": specificity,
        "f1": f1,
        "mcc": mcc,
        # The flag that lets a reader tell "no better than chance" from "could not compute".
        "mcc_denominator_zero": bool(mcc_den == 0),
        # False alarm rate and miss rate -- the same information as specificity and recall,
        # stated the way an operator thinks about it.
        "fpr": _safe_ratio(fp, n_neg),
        "fnr": _safe_ratio(fn, n_pos),
        "status": "OK",
    }


# The four counts as a labelled grid.
def confusion_matrix_frame(y: np.ndarray, p: np.ndarray,
                           threshold: float) -> pd.DataFrame:
    """The 2x2 confusion matrix as a labelled frame: rows actual, columns predicted."""
    # PLAIN ENGLISH: the rows and columns are LABELLED with words, not left as bare numbers.
    # Confusing which axis is which is one of the most common mistakes in reading these
    # grids, and naming them removes the guesswork entirely.
    y, p = _finite_pair(y, p)
    c = confusion_counts(y, (p >= float(threshold)).astype(int))
    return pd.DataFrame(
        # Top row: really calm. Bottom row: really trouble.
        [[c["tn"], c["fp"]], [c["fn"], c["tp"]]],
        index=pd.Index(["actual_%s" % CLASS_NAMES[0], "actual_%s" % CLASS_NAMES[1]],
                       name="actual"),
        columns=pd.Index(["predicted_%s" % CLASS_NAMES[0],
                          "predicted_%s" % CLASS_NAMES[1]], name="predicted"),
    )


# The scores broken down by class.
def per_class_report(y: np.ndarray, p: np.ndarray, threshold: float) -> pd.DataFrame:
    """Precision, recall, F1 and support for each class, plus macro and weighted F1.

    The negative class is reported as well as the positive one because a detector on an
    imbalanced problem can look strong on the majority class while failing the minority
    class that the research is actually about.
    """
    # PLAIN ENGLISH: the disease example from the top of the file, made into a report. A
    # system can score beautifully on "calm days" -- there are thousands of them and they are
    # easy -- while completely failing on the rare trouble days, which are the entire point.
    # Splitting the report by class makes that impossible to hide behind an overall figure.
    y, p = _finite_pair(y, p)
    y_pred = (p >= float(threshold)).astype(int)
    c = confusion_counts(y, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]

    # For the negative class the roles swap: a "true positive" for class 0 is a TN.
    # PLAIN ENGLISH: to score "how well did we identify CALM days", correctly-spotted calm
    # days become the successes, and the two error types trade places. Rather than writing
    # the whole calculation twice, we swap the labels and run it once.
    per_class = {
        1: {"tp": tp, "fp": fp, "fn": fn},
        0: {"tp": tn, "fp": fn, "fn": fp},
    }
    rows = []
    for label in (0, 1):
        v = per_class[label]
        pr = _safe_ratio(v["tp"], v["tp"] + v["fp"])
        rc = _safe_ratio(v["tp"], v["tp"] + v["fn"])
        # The same "zero versus undefined" care as before.
        if v["tp"] + v["fp"] + v["fn"] == 0:
            f1 = float("nan")
        elif v["tp"] == 0:
            f1 = 0.0
        else:
            f1 = 2 * pr * rc / (pr + rc)
        rows.append({"class": label, "class_name": CLASS_NAMES[label],
                     # "Support" means how many examples of this class there were -- context
                     # for how much weight to put on the row.
                     "support": int(v["tp"] + v["fn"]),
                     "precision": pr, "recall": rc, "f1": f1})

    tbl = pd.DataFrame(rows)
    support = tbl["support"].to_numpy(float)
    f1s = tbl["f1"].to_numpy(float)
    # MACRO: the plain average of the two classes' scores, treating both as equally
    # important. This is the one that exposes failure on the rare class.
    macro = float(np.nanmean(f1s)) if np.isfinite(f1s).any() else float("nan")
    # WEIGHTED: the average weighted by how common each class is. This one is dominated by
    # the common class, and is exactly the figure that can look reassuring while the rare
    # class is being missed entirely. Both are reported, so the gap between them is visible.
    weighted = (float(np.nansum(f1s * support) / support.sum())
                if support.sum() else float("nan"))
    tbl.attrs["macro_f1"] = macro
    tbl.attrs["weighted_f1"] = weighted
    return tbl


# Everything from this section in one record.
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
        # The leakage warning travels WITH the numbers, so anybody reading the saved report
        # is told the rule without having to go and find the code.
        "threshold_provenance": (
            "The threshold must be supplied by the caller and must have been selected on "
            "the training split. Choosing it on the evaluation split would be threshold "
            "provenance leakage (L6)."),
    }


# -- temporal -------------------------------------------------------------------------
# PLAIN ENGLISH: the measures so far ask "was it right?". These ask "was it right AT THE
# RIGHT TIME?" -- which for a warning system is very nearly the whole point.

# How early did we spot it?
def lead_time(true_entry: pd.Timestamp, pred_entry: pd.Timestamp | None,
              sessions: pd.Series) -> float:
    """Sessions between predicted and true entry. Positive = detected early.

    Counted in *trading sessions*, not calendar days, so a long weekend is not credited
    as three days of lead.
    """
    # PLAIN ENGLISH: a small, sharp piece of honesty. Spotting something on Friday that
    # happens on Monday is THREE calendar days of warning -- and nobody could have acted on
    # it, because the market was shut for two of them. Counting only trading sessions gives
    # one day, which is the truth.
    if pred_entry is None or pd.isna(true_entry):
        return np.nan
    # A clean, sorted list of trading days to count against.
    s = pd.Series(pd.to_datetime(sessions.to_numpy())).sort_values().reset_index(
        drop=True)
    # Where each date sits in that list.
    i_true = int(s.searchsorted(pd.Timestamp(true_entry)))
    i_pred = int(s.searchsorted(pd.Timestamp(pred_entry)))
    # The gap, in trading days. Positive means we spotted it first.
    return float(i_true - i_pred)


# How much do two time windows overlap?
def temporal_iou(a_start, a_end, b_start, b_end) -> float:
    """Intersection over union of two closed intervals, in days."""
    # PLAIN ENGLISH: "intersection over union" -- the days both windows cover, divided by the
    # days either covers. 1.0 means identical; 0 means no overlap at all. It is the standard
    # way of scoring "did you get roughly the right stretch of time?", and it fairly punishes
    # both a window that is too short and one that is far too long.
    if any(pd.isna(x) for x in (a_start, b_start)):
        return np.nan
    # A window with no end (one that never resolved) is treated as a single day, which is the
    # conservative reading -- it claims no more coverage than we can actually demonstrate.
    a_end = a_end if not pd.isna(a_end) else a_start
    b_end = b_end if not pd.isna(b_end) else b_start
    a0, a1 = pd.Timestamp(a_start), pd.Timestamp(a_end)
    b0, b1 = pd.Timestamp(b_start), pd.Timestamp(b_end)
    # The overlap: from the later start to the earlier end. `+ 1` because both ends are
    # included -- a window from Monday to Monday is one day, not zero.
    inter = (min(a1, b1) - max(a0, b0)).days + 1
    if inter <= 0:
        return 0.0
    # The total span covered by either.
    union = (max(a1, b1) - min(a0, b0)).days + 1
    return float(inter / union) if union > 0 else 0.0


# Match up what we predicted with what really happened.
def temporal_metrics(true_windows: pd.DataFrame, pred_windows: pd.DataFrame,
                     sessions: pd.Series, match_tolerance_days: int = 20) -> dict:
    """Match predicted windows to true windows and summarise the timing errors.

    Matching is greedy on temporal overlap within a symbol, with a tolerance so that a
    prediction which starts shortly before the true entry still counts as a detection.
    Unmatched true windows are misses; unmatched predictions are false alarms.
    """
    # PLAIN ENGLISH: a prediction three days early should count as a good catch, not as one
    # miss plus one false alarm. So there is a 20-day tolerance for pairing them up. "Greedy"
    # means each true episode takes the best available match and that prediction is then used
    # up -- so one lucky prediction cannot be credited against several real episodes.
    rows = []
    # Predictions already claimed by an earlier match.
    used: set[int] = set()
    for _, t in true_windows.iterrows():
        # Only ever match within the same company.
        cands = pred_windows[pred_windows["symbol"] == t["symbol"]]
        best, best_i = None, None
        for i, c in cands.iterrows():
            if i in used:
                continue
            # How far apart the starts are.
            gap = abs((pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days)
            # Too far apart to be about the same event.
            if gap > match_tolerance_days:
                continue
            # Among the close-enough ones, keep whichever overlaps most.
            iou = temporal_iou(t["t_entry"], t["t_exit"], c["t_entry"], c["t_exit"])
            if best is None or iou > best[0]:
                best, best_i = (iou, c), i
        # Nothing matched: a MISS. Recorded as a row with `matched=False`, so it still
        # appears in the table rather than quietly vanishing from the count.
        if best is None:
            rows.append({"symbol": t["symbol"], "matched": False,
                         "lead_time": np.nan, "onset_error": np.nan,
                         "resolution_error": np.nan, "iou": 0.0,
                         "duration_error": np.nan})
            continue
        # Claim this prediction so nothing else can also use it.
        used.add(best_i)
        iou, c = best
        # How far out the START was. Negative means we were early.
        onset = (pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days
        # If either window never ended, the end-timing errors are genuinely unknown.
        if pd.isna(t["t_exit"]) or pd.isna(c["t_exit"]):
            res = np.nan
            dur = np.nan
        else:
            # How far out the END was, and how far out the total LENGTH was.
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
    # Timing statistics are computed over the MATCHED ones only -- there is no timing error
    # to speak of for an episode that was never detected.
    m = d[d["matched"]] if len(d) else d
    return {
        "n_true_windows": n_true, "n_pred_windows": n_pred,
        "n_matched": matched,
        # What share of real episodes we caught at all.
        "detection_rate": float(matched / n_true) if n_true else np.nan,
        # And how many alarms corresponded to nothing.
        "false_alarm_windows": int(n_pred - matched),
        # How early we were, on average and typically. The median is given as well as the
        # mean because one freakishly early catch can flatter the mean considerably.
        "mean_lead_time": float(m["lead_time"].mean()) if len(m) else np.nan,
        "median_lead_time": float(m["lead_time"].median()) if len(m) else np.nan,
        # How far out the start was, on average.
        "mean_onset_error": float(m["onset_error"].mean()) if len(m) else np.nan,
        # And the same ignoring direction. Both are needed: a system that is three days
        # early half the time and three days late the other half averages to a perfect zero,
        # while actually being wrong by three days every single time.
        "mean_abs_onset_error": float(m["onset_error"].abs().mean())
        if len(m) else np.nan,
        "mean_resolution_error": float(m["resolution_error"].mean())
        if len(m) else np.nan,
        "mean_temporal_iou": float(m["iou"].mean()) if len(m) else np.nan,
        "mean_duration_error": float(m["duration_error"].mean())
        if len(m) else np.nan,
        # How often we sounded the all-clear too soon -- the dangerous kind of error, since
        # somebody may act on it.
        "premature_resolution_rate": float((m["resolution_error"] < -2).mean())
        if len(m) else np.nan,
        # And how often we kept the alarm going long after it was over -- the annoying kind,
        # which trains people to ignore alarms.
        "delayed_resolution_rate": float((m["resolution_error"] > 2).mean())
        if len(m) else np.nan,
        # The full per-episode detail, so nothing has to be taken on trust.
        "per_window": d,
    }


# -- error taxonomy -------------------------------------------------------------------

# The kinds of mistake worth telling apart.
ERROR_CLASSES = ["FALSE_POSITIVE", "FALSE_NEGATIVE", "EARLY_DETECTION",
                 "LATE_DETECTION", "FALSE_RESOLUTION", "PERSISTENT_ALERT",
                 "MISSING_EVIDENCE", "CONFLICTING_EVIDENCE", "DATA_QUALITY",
                 "MODEL_FAILURE"]


# Label each row with what kind of mistake it was, if any.
def classify_errors(df: pd.DataFrame, threshold: float,
                    score_col: str = "integrity_risk") -> pd.DataFrame:
    """Assign one error class per row (or ``CORRECT``).

    The taxonomy is deliberately ordered: data problems are diagnosed before model
    problems, because a row with no evidence is not a model failure.
    """
    # PLAIN ENGLISH: the ordering is the clever part, and it is a diagnostic discipline. If
    # the model got a row wrong because it had almost no evidence to work with, that is NOT
    # a modelling failure -- it is a data failure, and the fix is completely different.
    # Diagnosing in the wrong order would send somebody off retuning a model when the real
    # problem was a missing data feed.
    out = df.copy()
    pred = (out[score_col] >= threshold).astype(int)
    truth = out["is_episode"].astype(int)
    # How much evidence each row actually had.
    cov = out[[c for c in ("cov_market", "cov_micro", "cov_regime",
                           "cov_propagation") if c in out.columns]]
    # Assume full coverage if the honesty columns are absent, rather than crashing.
    coverage = cov.mean(axis=1) if len(cov.columns) else pd.Series(1.0,
                                                                   index=out.index)
    disagree = out["uncertainty"] if "uncertainty" in out.columns else pd.Series(
        0.0, index=out.index)

    # Start by assuming everything was right, then overwrite. Note the ORDER: each later line
    # overwrites the earlier ones, so the LAST matching rule wins -- which is why the data
    # diagnoses come after the model ones.
    cls = pd.Series("CORRECT", index=out.index, dtype=object)
    # A false alarm, and a miss.
    cls[(pred == 1) & (truth == 0)] = "FALSE_POSITIVE"
    cls[(pred == 0) & (truth == 1)] = "FALSE_NEGATIVE"
    # But if less than half the evidence was present, the real story is missing evidence --
    # so this OVERWRITES the model verdict above.
    cls[(coverage < 0.5)] = "MISSING_EVIDENCE"
    # And if the model was wrong while its own sources were strongly disagreeing, that is a
    # different diagnosis again: the evidence itself was contradictory.
    cls[(pred != truth) & (disagree > 0.6)] = "CONFLICTING_EVIDENCE"
    # Finally, missing basic market data outranks everything -- without prices, nothing
    # downstream had a chance.
    if "cov_market" in out.columns:
        cls[out["cov_market"] < 0.5] = "DATA_QUALITY"
    out["error_class"] = cls
    return out


# -- operational ----------------------------------------------------------------------

# How fast and how heavy is it?
def operational_metrics(fit_seconds: float, predict_seconds: float, n_rows: int,
                        peak_memory_mb: float | None = None) -> dict:
    # PLAIN ENGLISH: accuracy is not the only thing that matters. A system that takes six
    # hours to score one day of data could never be used in practice, however clever it is.
    # Reporting the cost alongside the quality lets a reader judge whether the result is
    # usable as well as correct.
    return {
        # How long training took, and how long scoring took.
        "fit_seconds": float(fit_seconds),
        "predict_seconds": float(predict_seconds),
        "rows": int(n_rows),
        # How many rows per second -- the throughput.
        "throughput_rows_per_s": float(n_rows / predict_seconds)
        if predict_seconds > 0 else np.nan,
        # And the same fact from the other end: milliseconds per row. Both are given because
        # the two audiences think in different units -- batch processing cares about
        # throughput, live scoring cares about latency.
        "latency_ms_per_row": float(1000.0 * predict_seconds / n_rows)
        if n_rows else np.nan,
        # The most memory used at once. Passed straight through, including None, because an
        # unmeasured figure must stay unmeasured rather than becoming a zero.
        "peak_memory_mb": peak_memory_mb,
    }
