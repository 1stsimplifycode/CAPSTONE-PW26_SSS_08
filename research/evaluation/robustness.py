"""Robustness and generalization harness (STATS-15).

Two questions, kept apart because they fail differently.

**Robustness** asks what happens when the *inputs* degrade: noise on the features, a stale
feed, values dropping out, a whole block going dark, or simply less training data. The
model is unchanged; the signal reaching it is not.

**Generalization** asks whether a model fitted on one slice of the world works on another:
a later time period, or a disjoint set of instruments. Nothing about the input is degraded
-- the world is just different from the one that was fitted.

The frozen holdout is never touched. Every split here is carved out of ``train`` and
``validation`` only, and :func:`assert_no_holdout` enforces that on every frame that
reaches a model. That guard is not decorative: cross-period transfer is exactly the
experiment where reaching for "the latest data" would be most tempting, and the holdout is
the latest data.

Cross-*dataset* transfer stays BLOCKED and is reported as such: there is one dataset, so
there is nothing to transfer to. Reporting it as a passing result would be a fabrication.

PLAIN ENGLISH -- what this whole file is about:

TWO DIFFERENT WAYS FOR A SYSTEM TO FALL OVER IN REAL LIFE.

ROBUSTNESS -- "what if the data gets worse?"
In a laboratory the data is clean. In the real world a feed goes down, numbers arrive
three days late, somebody's decimal point moves. Does the system cope, or collapse?

GENERALISATION -- "what if the world is different?"
The data is perfectly clean. It is just about different companies, or a different year.
Did the system learn something general about markets, or did it memorise these particular
companies in this particular period?

They are kept separate because they break differently and are fixed differently.

THE FOUR WAYS DATA GOES WRONG, and note the third one especially:
  GAUSSIAN -- random noise on every value. Measurement error.
  DROPOUT  -- values simply missing. A partial outage.
  STALE    -- values are yesterday's, not today's. A DELAYED FEED. This is the nastiest
              of the four, because nothing looks wrong. Every number is present and
              plausible. It is simply out of date, and no check for missing values will
              ever notice.
  OUTLIERS -- some values multiplied by ten. The shape of a units mix-up upstream.

THE FROZEN HOLDOUT, and why the guard here is not decorative.
Some data has been locked away, untouched, for the final test. You get to use it ONCE --
look at it more than that and you start, unavoidably, tuning towards it.
Now notice the trap this file is walking into. The most natural robustness experiment is
"train on the past, test on the future". And what is the most recent data available? The
holdout. So this is the exact experiment where somebody would innocently reach for it.
Hence a check that runs on EVERY table before it reaches a model, and refuses. The
docstring's line is worth keeping: "an assertion is cheaper than the retraction".

AND ONE MORE HONEST REFUSAL, at the very bottom. Testing on a completely different dataset
would be the strongest possible evidence of generalisation. There IS no second dataset. So
that test is reported as BLOCKED, with the reason -- because an empty row in a table reads
as "not tested yet", and a fabricated one would be far worse.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The list of which measurements belong to which family.
from research.data import dataset as ds
# The experiment engine, reused so these runs are identical to the headline ones.
from research.evaluation import experiment as ex

# A label for this version.
ROBUSTNESS_VERSION = "robustness-v1"

#: Splits this harness is allowed to read. The holdout is deliberately absent.
# The whole guard rests on this one line: the locked-away data is simply not on the list.
ALLOWED_SPLITS = ("train", "validation")

#: Perturbation severities, as a fraction of each feature's own standard deviation (for
#: noise) or as a fraction of affected values (for the others).
# From mild (5%) to severe (50%), so the result is a CURVE rather than a single pass/fail.
# A curve tells you where things start to break; a single point does not.
SEVERITIES = (0.05, 0.10, 0.25, 0.50)

#: Training-set fractions for the learning curve, sampled by symbol rather than by row.
# How much training data to use, from a tenth up to all of it.
TRAIN_FRACTIONS = (0.10, 0.25, 0.50, 0.75, 1.00)


# A new kind of error, for when the locked-away data is touched.
class HoldoutTouched(RuntimeError):
    """Raised when a frame carrying frozen-holdout rows reaches a model."""


# THE GUARD.
def assert_no_holdout(frame: pd.DataFrame, where: str) -> None:
    """Refuse to proceed if any frozen-holdout row is present.

    Checked by value rather than by convention. A cross-period experiment naturally wants
    the most recent data, and the most recent data is the holdout; an assertion is cheaper
    than the retraction.
    """
    # PLAIN ENGLISH: "checked by value rather than by convention" means we do not trust
    # anybody to have remembered -- we look at the actual rows, every time, and count.
    # And "cheaper than the retraction" is the argument in five words: an annoying error
    # message today, or withdrawing a published paper next year.
    if "split" not in frame.columns:
        return
    n = int((frame["split"] == "holdout").sum())
    if n:
        # Refuse, saying WHERE it happened, HOW MANY rows, and what IS allowed.
        raise HoldoutTouched(
            "%s received %d frozen-holdout rows; STATS-15 may only use %s"
            % (where, n, " and ".join(ALLOWED_SPLITS)))


# Take only the data this harness may use.
def working_set(data: pd.DataFrame) -> pd.DataFrame:
    """Train and validation only, sorted by date."""
    out = data[data["split"].isin(ALLOWED_SPLITS)].copy()
    # Filtered AND then checked. Belt and braces: the filter should make this impossible,
    # and the check proves it rather than assuming it.
    assert_no_holdout(out, "working_set")
    return out.sort_values(["date", "symbol"]).reset_index(drop=True)


# Which columns belong to one family.
def block_columns(frame: pd.DataFrame, block: str) -> list[str]:
    return [c for c in ds.FEATURE_BLOCKS.get(block, []) if c in frame.columns]


# Every measurement column, in a fixed order with no duplicates.
def feature_columns(frame: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for m in ds.FEATURE_BLOCKS:
        cols.extend(block_columns(frame, m))
    # `dict.fromkeys` removes repeats while preserving order.
    return list(dict.fromkeys(cols))


# ------------------------------------------------------------- perturbations ----

# Break the data in one specific, named way.
def perturb(frame: pd.DataFrame, cols: list[str], kind: str, severity: float,
            seed: int) -> pd.DataFrame:
    """Degrade ``cols`` in place on a copy, one named failure mode at a time.

    ``gaussian``   additive noise at ``severity`` x each column's own standard deviation,
                   so a column measured in basis points and one measured in counts are
                   degraded comparably rather than the first being destroyed.
    ``dropout``    a fraction of individual values become missing, the way a partial feed
                   outage looks.
    ``stale``      a fraction of rows carry the previous observation for that symbol
                   instead of the current one: a delayed feed, which is a far more common
                   production failure than noise and is invisible to a null check.
    ``outliers``   a fraction of values are multiplied by ten, the shape of a unit or
                   decimal-point error upstream.
    """
    # PLAIN ENGLISH on the gaussian note: adding a fixed amount of noise would be
    # meaningless, because the columns are on wildly different scales. A noise of 0.5 would
    # obliterate a column whose values run from 0 to 1 and be invisible in one measured in
    # millions. Scaling the noise to each column's OWN spread degrades them comparably.
    rng = np.random.default_rng(seed)
    out = frame.copy()
    if not cols or severity <= 0:
        return out

    block = out[cols].to_numpy(float)
    # Which values to affect -- roughly `severity` of them, chosen at random.
    mask = rng.random(block.shape) < severity

    if kind == "gaussian":
        # Each column's own spread. Any column with no spread gets 1.0 as a safe stand-in.
        sd = np.nanstd(block, axis=0)
        sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
        block = block + rng.normal(0.0, 1.0, block.shape) * sd * severity
    elif kind == "dropout":
        # Simply blank the chosen values.
        block = np.where(mask, np.nan, block)
    elif kind == "outliers":
        # Multiply the chosen values by ten -- exactly what a units or decimal error does.
        block = np.where(mask, block * 10.0, block)
    elif kind == "stale":
        # Shift each symbol's history forward by one observation, then apply that stale
        # copy to the selected rows only.
        # PLAIN ENGLISH: the nastiest failure, and the one worth understanding. Every value
        # is present, plausible, and of the right size. It is simply YESTERDAY'S. No check
        # for missing data catches it, no check for silly values catches it. Grouped by
        # company so one firm's numbers never leak into another's.
        stale = out.groupby("symbol", sort=False)[cols].shift(1).to_numpy(float)
        # Note this mask is per ROW, not per value: a delayed feed makes a whole row stale,
        # not scattered individual cells. Getting that shape right is what makes the
        # simulation realistic.
        row_mask = (rng.random(len(out)) < severity)[:, None]
        block = np.where(row_mask & np.isfinite(stale), stale, block)
    else:
        # An unrecognised failure mode is a programming mistake. Refuse rather than quietly
        # returning undamaged data, which would silently report a robustness the test never
        # actually measured.
        raise ValueError("unknown corruption kind: %s" % kind)

    out[cols] = block
    return out


# Take a whole family of evidence offline.
def blackout_block(frame: pd.DataFrame, block: str,
                      fraction: float, seed: int) -> pd.DataFrame:
    """Take a block offline for a fraction of rows, coverage flag included.

    Blanking the columns alone is not enough: the combination layer reads a coverage flag, so a
    block whose columns are NaN but whose flag still reads 1.0 keeps voting. That
    asymmetry is precisely how an induced-missingness result comes out too optimistic.
    """
    # PLAIN ENGLISH: the same two-part removal as in the experiment engine. Blank the
    # measurements AND clear the flag. Miss the flag and a specialist with no information
    # keeps voting, diluting everyone else -- and the test would report the system coping
    # better with an outage than it really does.
    rng = np.random.default_rng(seed)
    out = frame.copy()
    cols = block_columns(out, block)
    if not cols:
        return out
    rows = rng.random(len(out)) < fraction
    out.loc[rows, cols] = np.nan
    key = {"microstructure": "cov_micro"}.get(block, "cov_%s" % block)
    if key in out.columns:
        out.loc[rows, key] = 0.0
    return out


# ------------------------------------------------------------------ scoring ----

@dataclass
# One fitted run and how it scored.
class Fit:
    """One fitted arm and the metrics it produced on a given evaluation frame."""
    status: str
    metrics: dict
    reason: str | None = None


# Build the experiment form.
def _spec(seed: int, arm: str, blocks: list[str], note: str) -> ex.ExperimentSpec:
    return ex.ExperimentSpec(
        experiment_id="stats15", hypothesis=note, arm=arm,
        blocks=list(blocks), seed=seed, eval_split="validation",
        notes=[note])


# Train on one table, score on another.
def fit_and_score(train: pd.DataFrame, evald: pd.DataFrame, blocks: list[str],
                  seed: int, arm: str, note: str) -> Fit:
    """Fit on ``train``, score on ``evald``, with the holdout guard on both."""
    # The guard on BOTH halves, every time. Not once at the start -- every single fit.
    assert_no_holdout(train, "fit_and_score(train)")
    assert_no_holdout(evald, "fit_and_score(eval)")
    # Refuse a split that cannot produce a meaningful answer, and say exactly which of the
    # three conditions failed and by how much.
    if train.empty or evald.empty or evald["is_episode"].nunique() < 2:
        return Fit("FAILED", {}, "degenerate split: %d train, %d eval, %d classes"
                   % (len(train), len(evald), evald["is_episode"].nunique()))

    # ExperimentSpec selects by split label, so relabel the two frames the harness is
    # meant to see. This is the whole point of routing through the same runner the
    # headline results use: the model, threshold rule and metrics are identical.
    # PLAIN ENGLISH: a small piece of plumbing with a big purpose. The engine picks its data
    # by a label, so we relabel our custom split to match. Slightly awkward -- and it means
    # every robustness run uses EXACTLY the same model, the same cut-off rule and the same
    # measurements as the headline results. Had we written a separate scoring path here, any
    # difference we measured might have come from the harness rather than the corruption.
    tr = train.copy()
    tr["split"] = "train"
    ev = evald.copy()
    ev["split"] = "validation"
    combined = pd.concat([tr, ev], ignore_index=True)

    res = ex.run(_spec(seed, arm, blocks, note), combined, write=False)
    if res.status != "OK":
        return Fit("FAILED", {}, res.failure_reason)
    return Fit("OK", {k: v for k, v in res.detection.items()
                      if isinstance(v, (int, float))})


# A tiny helper: `_row(a=1, b=2)` builds `{"a": 1, "b": 2}`, which keeps the calls below
# readable.
def _row(**kw) -> dict:
    return kw


# --------------------------------------------------------------- robustness ----

# TEST 1: what if the incoming data degrades?
def input_robustness(data: pd.DataFrame, seed: int = 20260818,
                     severities: tuple[float, ...] = SEVERITIES,
                     blocks: list[str] | None = None,
                     log=None) -> pd.DataFrame:
    """Degrade the evaluation inputs only; the model is fitted once on clean data.

    Fitting once is the point. Refitting on corrupted data would measure whether the
    learner can adapt to a new noise regime, which is a different and easier question than
    what happens to a deployed model when its feed degrades.
    """
    # PLAIN ENGLISH: a crucial and easily-missed distinction. If we RETRAINED on the noisy
    # data, we would be asking "can this method learn despite noise?" -- an easier question,
    # and not the one that matters. A model already deployed cannot retrain itself when a
    # feed degrades on a Tuesday. So the model is trained ONCE on clean data and then fed
    # progressively worse input, which is exactly the real situation.
    work = working_set(data)
    mods = blocks or list(ds.FEATURE_BLOCKS)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    cols = feature_columns(work)

    # The undamaged reference. Everything else is measured against this.
    clean = fit_and_score(train, evald, mods, seed, "clean", "undegraded reference")
    rows = [_row(family="input", corruption="none", target="all", severity=0.0,
                 status=clean.status, **clean.metrics)]
    base = clean.metrics.get("auprc", np.nan)
    if log:
        log("      clean reference auprc %.4f" % base)

    # Every failure mode at every severity -- so the output is a full grid, not one number.
    for kind in ("gaussian", "dropout", "stale", "outliers"):
        for sev in severities:
            degraded = perturb(evald, cols, kind, sev, seed)
            fit = fit_and_score(train, degraded, mods, seed, "%s@%.2f" % (kind, sev),
                                "evaluation inputs degraded")
            rows.append(_row(family="input", corruption=kind, target="all",
                             severity=float(sev), status=fit.status,
                             # How much worse than clean. The headline number of the test.
                             degradation=float(base - fit.metrics.get("auprc", np.nan)),
                             **fit.metrics))
            if log:
                log("        %-9s sev %.2f  auprc %.4f  (%+.4f)"
                    % (kind, sev, fit.metrics.get("auprc", np.nan),
                       fit.metrics.get("auprc", np.nan) - base))
    return pd.DataFrame(rows)


# TEST 2: what if a whole source of evidence goes dark?
def missingness_robustness(data: pd.DataFrame, seed: int = 20260818,
                           fractions: tuple[float, ...] = (0.25, 0.50, 1.00),
                           log=None) -> pd.DataFrame:
    """Take each block offline for a fraction of evaluation rows."""
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]

    clean = fit_and_score(train, evald, mods, seed, "clean", "undegraded reference")
    base = clean.metrics.get("auprc", np.nan)
    rows = []
    # Each family, taken offline for a quarter, half, and all of the rows.
    for block in mods:
        for frac in fractions:
            degraded = blackout_block(evald, block, frac, seed)
            fit = fit_and_score(train, degraded, mods, seed,
                                "%s_out@%.2f" % (block, frac),
                                "block offline at evaluation time")
            rows.append(_row(family="missingness", corruption="block_offline",
                             target=block, severity=float(frac),
                             status=fit.status,
                             degradation=float(base - fit.metrics.get("auprc", np.nan)),
                             **fit.metrics))
        if log:
            worst = rows[-1]
            log("        %-15s offline 100%%  auprc %.4f  (%+.4f)"
                % (block, worst.get("auprc", np.nan), -worst.get("degradation", 0.0)))
    return pd.DataFrame(rows)


# TEST 3: how much training data does it actually need?
def training_size_curve(data: pd.DataFrame, seed: int = 20260818,
                        fractions: tuple[float, ...] = TRAIN_FRACTIONS,
                        n_repeats: int = 3, log=None) -> pd.DataFrame:
    """Learning curve over training-set size, subsampled by **symbol**.

    Symbols, not rows: rows from one instrument are serially dependent, so dropping random
    rows leaves almost every instrument represented and understates how much the model
    depends on breadth. Dropping whole symbols is the honest version of "less data".
    """
    # PLAIN ENGLISH: the dependence rule once more, in a new guise. Drop 90% of the ROWS and
    # you still have every company represented -- just with gaps. The model barely notices.
    # Drop 90% of the COMPANIES and it has genuinely never seen those firms. That is what
    # "less data" actually means in practice, and it is a far harder and more honest test.
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    symbols = np.array(sorted(train["symbol"].unique()))

    rows = []
    for frac in fractions:
        # Repeat the smaller fractions three times, because WHICH companies you happen to
        # keep matters a great deal when you only keep a few. At 100% there is only one
        # possible selection, so repeating would be pointless -- hence the `if`.
        for rep in range(n_repeats if frac < 1.0 else 1):
            rng = np.random.default_rng(seed + rep)
            k = max(2, int(round(len(symbols) * frac)))
            keep = rng.choice(symbols, size=k, replace=False)
            sub = train[train["symbol"].isin(keep)]
            fit = fit_and_score(sub, evald, mods, seed, "train@%.2f_r%d" % (frac, rep),
                                "reduced training set, symbol-level subsample")
            rows.append(_row(family="training_size", corruption="fewer_symbols",
                             target="train", severity=float(frac), repeat=rep,
                             # Both counts recorded, so a reader can see how many companies
                             # AND how many rows the result rests on.
                             n_train_symbols=int(k), n_train_rows=int(len(sub)),
                             status=fit.status, **fit.metrics))
        if log:
            got = [r for r in rows if r["severity"] == float(frac)
                   and r["status"] == "OK"]
            if got:
                log("        %3d%% of symbols (%d)  auprc %.4f"
                    % (round(frac * 100), got[-1]["n_train_symbols"],
                       float(np.mean([g.get("auprc", np.nan) for g in got]))))
    return pd.DataFrame(rows)


# ------------------------------------------------------------ generalization ----

# TEST 4: does yesterday's model work on tomorrow?
def period_transfer(data: pd.DataFrame, seed: int = 20260818, n_folds: int = 4,
                    log=None) -> pd.DataFrame:
    """Expanding-window transfer forward in time, inside train and validation only.

    Each fold fits on everything before a cut date and scores the next block. This is the
    question a deployed detector actually faces -- yesterday's fit against tomorrow's
    market -- and it is not answered by a random split, which lets the model see the
    future of the very period it is scored on.
    """
    # PLAIN ENGLISH: a random split is the standard approach and it is WRONG for time-series
    # data. Shuffle days at random and the model trains on Wednesday and Friday, then gets
    # tested on Thursday -- surrounded on both sides by days it has already seen. It scores
    # brilliantly and tells you nothing about the future.
    # An "expanding window" is honest: train on everything up to a date, test on what comes
    # next. Then extend and repeat. That is exactly the situation a live system faces.
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    dates = np.array(sorted(work["date"].unique()))
    # Not enough distinct dates to split meaningfully. Report the shortage rather than
    # producing folds of five days each.
    if len(dates) < (n_folds + 1) * 5:
        return pd.DataFrame([_row(family="period", status="INSUFFICIENT DATA",
                                  note="only %d distinct dates" % len(dates))])

    # Cut the timeline into five consecutive chunks.
    bounds = np.array_split(dates, n_folds + 1)
    rows = []
    for i in range(n_folds):
        cut = bounds[i][-1]
        nxt = bounds[i + 1]
        # Train on EVERYTHING up to the cut...
        tr = work[work["date"] <= cut]
        # ...and test on the chunk that follows. Strictly after: `>` not `>=`.
        ev = work[(work["date"] > cut) & (work["date"] <= nxt[-1])]
        fit = fit_and_score(tr, ev, mods, seed, "period_fold%d" % (i + 1),
                            "fit on history, scored on the following period")
        rows.append(_row(family="period", fold=i + 1,
                         # The actual dates are recorded, so a reader can see exactly which
                         # period each fold covers rather than trusting the fold number.
                         train_end=str(pd.Timestamp(cut).date()),
                         eval_start=str(pd.Timestamp(nxt[0]).date()),
                         eval_end=str(pd.Timestamp(nxt[-1]).date()),
                         n_train=int(len(tr)), n_eval=int(len(ev)),
                         # How much trouble occurred in this period. Essential context: a
                         # fold covering a calm stretch is a completely different test from
                         # one covering a crisis, and the scores are not comparable without it.
                         eval_positive_rate=float(ev["is_episode"].mean())
                         if len(ev) else np.nan,
                         status=fit.status, reason=fit.reason, **fit.metrics))
        if log:
            log("        fold %d  train<=%s  eval %s..%s  auprc %.4f"
                % (i + 1, rows[-1]["train_end"], rows[-1]["eval_start"],
                   rows[-1]["eval_end"], rows[-1].get("auprc", np.nan)))
    return pd.DataFrame(rows)


# TEST 5: does it work on companies it has never seen?
def instrument_transfer(data: pd.DataFrame, seed: int = 20260818, n_groups: int = 4,
                        log=None) -> pd.DataFrame:
    """Fit on one disjoint set of instruments, score on the rest.

    No symbol appears on both sides, so this measures whether the detector learned
    something about market behaviour or something about these particular tickers.
    """
    # PLAIN ENGLISH: THE question, put as sharply as it can be. Did the system learn what
    # trouble LOOKS like, or did it learn that these specific companies have trouble? The
    # only way to find out is to show it companies it has genuinely never encountered.
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    symbols = np.array(sorted(work["symbol"].unique()))
    rng = np.random.default_rng(seed)
    # Shuffle and cut into four groups. Sorting before shuffling makes the split repeatable.
    shuffled = rng.permutation(symbols)
    groups = np.array_split(shuffled, n_groups)

    rows = []
    for i, held in enumerate(groups, 1):
        held_set = set(held)
        # Train on everyone NOT in this group...
        tr = work[~work["symbol"].isin(held_set)]
        # ...and test only on this group.
        ev = work[work["symbol"].isin(held_set)]
        # And PROVE the two sides share no company. `set(a) & set(b)` is what they have in
        # common; it must be empty. Checking rather than assuming, because if this ever
        # failed the results would look excellent and mean nothing.
        assert not (set(tr["symbol"]) & set(ev["symbol"])), "instrument groups overlap"
        fit = fit_and_score(tr, ev, mods, seed, "instrument_group%d" % i,
                            "fit on disjoint instruments, scored on held-out tickers")
        rows.append(_row(family="instrument", group=i,
                         n_held_symbols=int(len(held)),
                         n_train=int(len(tr)), n_eval=int(len(ev)),
                         eval_positive_rate=float(ev["is_episode"].mean())
                         if len(ev) else np.nan,
                         status=fit.status, reason=fit.reason, **fit.metrics))
        if log:
            log("        group %d  %d held-out symbols  auprc %.4f"
                % (i, len(held), rows[-1].get("auprc", np.nan)))
    return pd.DataFrame(rows)


# TEST 6: the one that cannot be run, reported rather than omitted.
def dataset_transfer_status() -> dict:
    """Cross-dataset transfer, reported as blocked rather than skipped."""
    # PLAIN ENGLISH: the strongest possible test of generalisation would be a completely
    # different dataset -- a different exchange, different companies, different years. There
    # is not one. So rather than leaving the row out, it appears marked BLOCKED, with the
    # reason and with exactly what would unblock it.
    return {
        "status": "BLOCKED",
        # And the reasoning spelled out, including the crucial argument for why an absent
        # row would have been worse: it reads as "not yet tested" rather than "cannot be".
        "reason": ("Only one dataset exists in this project, so there is no second "
                   "dataset to transfer to. This is reported rather than omitted: an "
                   "absent row in a generalization table reads as an untested axis, and "
                   "a fabricated one would be worse."),
        # A concrete specification of what would fix it, so somebody could actually go and
        # do it rather than being left with a vague gap.
        "what_would_unblock_it": (
            "A second panel built by the same feature pipeline over a different venue or "
            "instrument universe, with its own episode labels."),
    }
