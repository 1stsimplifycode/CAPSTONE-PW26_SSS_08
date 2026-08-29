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

PLAIN ENGLISH -- what this whole file is about:

TURNING A DISAPPOINTING RESULT INTO A USEFUL ONE.

This project found something it did not want to find: the system spots trouble LATE, not
early. It is a detector, not an early-warning system. That is negative finding N-03, and
it is published rather than buried.

But a finding like that raises an obvious follow-up question, and this file exists to
answer it:

    IS THE LATENESS A CHOICE, OR A LIMIT?

Those are completely different situations:
  A CHOICE -- we set the alarm cautiously, waiting for strong evidence before shouting. We
    could shout sooner, and we would then get more false alarms. The lateness is a dial we
    chose a setting for.
  A LIMIT -- the evidence genuinely does not exist any earlier. Turn the dial as far as you
    like; there is nothing there to find. No amount of tuning will help.

HOW TO TELL: turn the dial all the way through its range and watch what happens. If being
more sensitive buys real earliness at a reasonable cost in false alarms, it was a choice.
If being more sensitive just produces a flood of false alarms with no improvement in
timing, it is a limit. Either way you now KNOW, and you can say which in the paper.

THE SECOND QUESTION: do the different families of evidence arrive at different times? If
one of them consistently moves BEFORE trouble shows up, that family is where any real
early warning would have to come from. And if they all move at exactly the same moment,
that is itself informative and slightly deflating -- it suggests they are all really
derived from the same underlying price series, and the apparent variety is an illusion.

AND A QUIET VIRTUE IN THE LAST LINE: both analyses run on results already saved to disk.
No new data, no new experiments. This is a project squeezing more understanding out of
what it already has, rather than asking for more.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The state machine that turns scores into episodes.
from research.detection import state as st
# The measuring tapes.
from research.evaluation import metrics as mx

# A label for this version.
TEMPORAL_VERSION = "temporal-analysis-v1"


# Turn the sensitivity dial through its whole range and record what happens.
def lead_time_frontier(scored: pd.DataFrame,
                       # The settings to try, from very sensitive (0.20) to very cautious
                       # (0.90). Closely spaced in the middle where the interesting
                       # behaviour lives, and sparser at the extremes.
                       thresholds: tuple[float, ...] = (0.20, 0.25, 0.30, 0.35, 0.40,
                                                        0.45, 0.50, 0.55, 0.60, 0.65,
                                                        0.70, 0.80, 0.90),
                       exit_gap: float = 0.15) -> pd.DataFrame:
    """Sweep the state-machine entry threshold and record the timing/precision pair.

    ``exit_gap`` keeps the exit threshold a fixed distance below entry so the hysteresis
    structure is preserved as the operating point moves; without that the sweep would
    conflate two changes.
    """
    # PLAIN ENGLISH: recall the thermostat trick -- the alarm switches on at one level and
    # off at a lower one, and that gap is what stops it flickering.
    # If we moved only the switch-on level, the gap would shrink as we went, and eventually
    # vanish. We would then be changing TWO things at once -- the sensitivity AND the
    # anti-flicker protection -- and could never say which caused what we saw.
    # Keeping the gap fixed at 0.15 means exactly one thing varies across the whole sweep.

    # The real episodes, one row each. `"first"` takes the first value in each group, which
    # is right because every row of one episode carries the same start and end.
    truth = (scored[scored["is_episode"] == 1]
             .groupby(["symbol", "episode_id"])
             .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
             .reset_index())
    sessions = scored["date"].drop_duplicates()
    rows = []
    for thr in thresholds:
        # Build a state machine at this sensitivity, keeping the gaps fixed.
        cfg = st.StateConfig(enter_threshold=thr,
                             # `max(0.05, ...)` stops the exit level going below zero at the
                             # most sensitive settings, which would make it impossible ever
                             # to declare an episode over.
                             exit_threshold=max(0.05, thr - exit_gap),
                             early_warning_threshold=max(0.03, thr - exit_gap - 0.05))
        # Find the episodes this setting would have produced.
        wins = st.windows_from_frame(scored, "integrity_risk", cfg)
        pred = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry,
                              "t_exit": w.t_exit, "censored": w.censored}
                             for w in wins])
        # Nothing detected at all -- perfectly possible at the most cautious settings.
        # Recorded as a row with a status, so the sweep shows where detection dies out
        # rather than that setting silently vanishing from the chart.
        if pred.empty or truth.empty:
            rows.append({"entry_threshold": thr, "n_pred_windows": int(len(pred)),
                         "status": "NO WINDOWS"})
            continue
        # Score the timing and matching at this setting.
        tm = mx.temporal_metrics(truth, pred, sessions)
        # `.pop` takes the per-episode detail out and keeps it aside -- too big for the
        # summary table, but needed for the calculation below.
        per = tm.pop("per_window")
        matched = int(tm["n_matched"])
        n_pred = int(tm["n_pred_windows"])
        rows.append({
            "entry_threshold": thr,
            # How many alarms, how many were real.
            "n_pred_windows": n_pred,
            "n_matched": matched,
            # What share of real episodes we caught.
            "detection_rate": tm["detection_rate"],
            # And what share of our alarms were real. THE TRADE-OFF, in two numbers: as one
            # rises the other falls, and the sweep traces that curve.
            "window_precision": float(matched / n_pred) if n_pred else np.nan,
            "false_alarm_windows": tm["false_alarm_windows"],
            # How early we were, typically and on average.
            "median_lead_time": tm["median_lead_time"],
            "mean_lead_time": tm["mean_lead_time"],
            "mean_temporal_iou": tm["mean_temporal_iou"],
            # THE NUMBER THAT ANSWERS THE QUESTION: what fraction of detections were
            # genuinely EARLY? An average lead time of zero could mean "always exactly on
            # time" or "half wildly early, half wildly late" -- this tells those apart.
            "positive_lead_fraction": float(np.mean(
                per["lead_time"].dropna() > 0)) if per["lead_time"].notna().any()
            else np.nan,
            "status": "OK",
        })
    return pd.DataFrame(rows)


# Does any family of evidence move BEFORE the trouble?
def block_lead_lag(scored: pd.DataFrame, blocks: list[str],
                      max_lag: int = 20) -> pd.DataFrame:
    """Cross-correlation of each block score against the episode indicator.

    Positive lag means the block score moves *before* the episode indicator, i.e. the
    block leads. Correlations are computed per instrument and averaged across
    instruments, so a single long series cannot dominate.
    """
    # PLAIN ENGLISH: slide one line back and forth against the other and see which
    # alignment matches best. If a family's score lines up best when shifted five days
    # EARLIER, then that family is picking something up five days ahead of the trouble.
    # And the per-company averaging matters: one company with fifteen years of data would
    # otherwise drown out fifty companies with two years each, and the answer would really
    # be about that one company.
    rows = []
    for mod in blocks:
        col = "score_%s" % mod
        # Family not present in this data. Recorded as ABSENT rather than skipped, so the
        # table still has a row for it and the gap is visible.
        if col not in scored.columns:
            rows.append({"block": mod, "status": "ABSENT"})
            continue
        per_sym = []
        for _sym, g in scored.sort_values(["symbol", "date"]).groupby("symbol"):
            s = g[col].to_numpy(float)
            y = g["is_episode"].to_numpy(float)
            # Skip companies with too little history to slide 20 days either way, and any
            # whose series never varies -- correlation with a flat line is undefined.
            if len(s) < 3 * max_lag or np.nanstd(s) == 0 or np.nanstd(y) == 0:
                continue
            # Standardise both to average 0 and spread 1, so the multiplication below is a
            # correlation rather than being dominated by whichever series has bigger numbers.
            s = (s - np.nanmean(s)) / np.nanstd(s)
            y = (y - np.nanmean(y)) / np.nanstd(y)
            cors = []
            # Try every shift from 20 days behind to 20 days ahead.
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    # Negative: the score is chopped at the front, so it is compared against
                    # EARLIER trouble -- testing whether the score lags.
                    a, b = s[-lag:], y[:len(y) + lag]
                elif lag > 0:
                    # Positive: trouble is chopped at the front, so the score is compared
                    # against LATER trouble -- testing whether the score leads.
                    a, b = s[:len(s) - lag], y[lag:]
                else:
                    a, b = s, y
                # Too little overlap left for the number to mean anything.
                if len(a) < 30:
                    cors.append(np.nan)
                    continue
                # With both series standardised, the average of their product IS the
                # correlation. `nanmean` ignores any gaps.
                cors.append(float(np.nanmean(a * b)))
            per_sym.append(cors)
        if not per_sym:
            rows.append({"block": mod, "status": "INSUFFICIENT DATA"})
            continue
        # Average the curve across companies, so each company counts once regardless of
        # how long its history is.
        mean_cor = np.nanmean(np.vstack(per_sym), axis=0)
        lags = np.arange(-max_lag, max_lag + 1)
        # Which shift matched best.
        best = int(np.nanargmax(mean_cor))
        rows.append({
            "block": mod,
            # The answer: positive means it leads, negative means it lags, zero means they
            # move together.
            "peak_lag_sessions": int(lags[best]),
            "peak_correlation": float(mean_cor[best]),
            # The correlation with no shift at all, for comparison. If the peak is barely
            # better than this, the "lead" is not a real effect.
            "correlation_at_zero": float(mean_cor[max_lag]),
            # How many companies the answer rests on.
            "n_instruments": len(per_sym),
            "status": "OK",
            # And the answer in plain words, so nobody has to remember which sign means what.
            "interpretation": ("leads the episode indicator"
                               if lags[best] > 0 else
                               "lags the episode indicator" if lags[best] < 0
                               else "coincident"),
            # The whole curve is kept too, so it can be plotted. The leading underscores mark
            # these as detail rather than headline columns.
            "_curve_lags": lags.tolist(),
            "_curve_values": [float(v) for v in mean_cor],
        })
    return pd.DataFrame(rows)


# Score the three parts of an episode separately.
def onset_peak_resolution_scores(scored: pd.DataFrame,
                                 cfg: st.StateConfig | None = None) -> dict:
    """Score the three lifecycle sub-tasks separately (research-angle section 26).

    Treating detection as one scalar hides that onset, peak and resolution are different
    problems with different difficulty. Each is scored against the injected ground truth.
    """
    # PLAIN ENGLISH: spotting that trouble is STARTING, spotting when it is WORST, and
    # spotting when it is OVER are three genuinely different jobs of three different
    # difficulties. One combined score averages them into a number that describes none of
    # them, and hides which part is actually failing.
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
    # Match each real episode to its closest prediction.
    for _, t in truth.iterrows():
        cands = pred[pred["symbol"] == t["symbol"]]
        best_i, best_gap = None, None
        for i, c in cands.iterrows():
            # Each prediction may only be claimed once.
            if i in used:
                continue
            gap = abs((pd.Timestamp(c["t_entry"]) - pd.Timestamp(t["t_entry"])).days)
            # Within 20 days, and closer than anything found so far.
            if gap <= 20 and (best_gap is None or gap < best_gap):
                best_i, best_gap = i, gap
        if best_i is None:
            continue
        used.add(best_i)
        matched += 1
        c = pred.loc[best_i]
        # How far out the START was.
        onset_err.append((pd.Timestamp(c["t_entry"])
                          - pd.Timestamp(t["t_entry"])).days)
        # And the END -- but only when both actually have one. An episode that never
        # resolved has no end to be wrong about.
        if not pd.isna(t["t_exit"]) and c["t_exit"] is not None \
                and not pd.isna(c["t_exit"]):
            resolution_err.append((pd.Timestamp(c["t_exit"])
                                   - pd.Timestamp(t["t_exit"])).days)

    # A small helper that summarises a list of timing errors.
    def _s(v, name):
        v = np.asarray(v, dtype=float)
        # Nothing to summarise: say NOT MEASURED rather than reporting zeros.
        if v.size == 0:
            return {"task": name, "n": 0, "status": "NOT MEASURED"}
        return {"task": name, "n": int(v.size),
                # The average error, which can be misleadingly small if early and late
                # mistakes cancel out...
                "mean_error_days": float(v.mean()),
                "median_error_days": float(np.median(v)),
                # ...so the average SIZE of the error is given too, where they cannot cancel.
                "mean_abs_error_days": float(np.abs(v).mean()),
                # And the most practically meaningful figure of all: what fraction were
                # within three days. Far easier to act on than an average.
                "within_3_days": float(np.mean(np.abs(v) <= 3)),
                "status": "OK"}

    return {
        "status": "OK",
        "n_true": int(len(truth)),
        "n_pred": int(len(pred)),
        "n_matched": matched,
        "onset": _s(onset_err, "onset"),
        "resolution": _s(resolution_err, "resolution"),
        # PLAIN ENGLISH: and here is why the THIRD task is deliberately not scored. The
        # detector's "peak" is simply the highest point of a noisy line -- and the highest
        # point of a noisy line jumps about from day to day for reasons that have nothing to
        # do with the underlying event. So a peak-timing score would mostly be measuring the
        # noise, and would look like a real measurement while being nearly meaningless.
        # Declining to report it, and saying exactly why, is better than reporting it.
        "note": ("Peak timing is not scored separately: the injected schedule places a "
                 "peak phase but the detector's peak is the argmax of a noisy score, so "
                 "a peak-timing error would mostly measure score noise."),
    }


# What if one family's evidence arrived late?
def asynchrony_sensitivity(data: pd.DataFrame, model, block: str,
                           block_columns: list[str],
                           offsets: tuple[int, ...] = (0, 1, 3, 5, 10, 20),
                           y_col: str = "is_episode") -> pd.DataFrame:
    """Shift one block's features forward in time and measure the damage.

    Simulates cross-block temporal misalignment: evidence that arrives *later* than the
    system assumes. Shifting forward (not backward) is the realistic direction, since
    a real feed is delayed relative to market data, never early.
    """
    # PLAIN ENGLISH: in real life, data feeds are late. One supplier delivers on time,
    # another is three days behind. How much does that break things?
    # Note the careful choice of direction: we only ever simulate evidence arriving LATE,
    # never EARLY. Early would be a fantasy -- no feed delivers tomorrow's news today -- and
    # testing against a fantasy would produce a comfortingly wrong answer.
    rows = []
    base = data.copy()
    for off in offsets:
        d = base.copy()
        if off > 0:
            d = d.sort_values(["symbol", "date"])
            # `.shift(off)` moves this family's values down by that many rows, so each row
            # now sees values from `off` days ago -- exactly what a delayed feed looks like.
            # Grouped by company so one firm's data cannot bleed into the next.
            shifted = d.groupby("symbol")[block_columns].shift(off)
            for c in block_columns:
                d[c] = shifted[c]
        try:
            # Score with the delayed evidence and see how much worse it is.
            p = model.predict(d)["integrity_risk"]
            m = mx.detection_metrics(d[y_col].to_numpy(int), p)
            rows.append({"block": block, "offset_sessions": off,
                         "auprc": m["auprc"], "auroc": m["auroc"], "ece": m["ece"],
                         "status": "OK"})
        except Exception as exc:
            # A failure at one delay is recorded with its cause and the sweep continues, so
            # one bad point cannot wipe out the whole curve -- and the failure stays visible
            # in the results rather than becoming a missing row.
            rows.append({"block": block, "offset_sessions": off,
                         "status": "FAILED: %s" % type(exc).__name__})
    return pd.DataFrame(rows)
