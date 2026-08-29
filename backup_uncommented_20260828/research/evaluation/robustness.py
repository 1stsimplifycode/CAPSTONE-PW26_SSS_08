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
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.data import dataset as ds
from research.evaluation import experiment as ex

ROBUSTNESS_VERSION = "robustness-v1"

#: Splits this harness is allowed to read. The holdout is deliberately absent.
ALLOWED_SPLITS = ("train", "validation")

#: Perturbation severities, as a fraction of each feature's own standard deviation (for
#: noise) or as a fraction of affected values (for the others).
SEVERITIES = (0.05, 0.10, 0.25, 0.50)

#: Training-set fractions for the learning curve, sampled by symbol rather than by row.
TRAIN_FRACTIONS = (0.10, 0.25, 0.50, 0.75, 1.00)


class HoldoutTouched(RuntimeError):
    """Raised when a frame carrying frozen-holdout rows reaches a model."""


def assert_no_holdout(frame: pd.DataFrame, where: str) -> None:
    """Refuse to proceed if any frozen-holdout row is present.

    Checked by value rather than by convention. A cross-period experiment naturally wants
    the most recent data, and the most recent data is the holdout; an assertion is cheaper
    than the retraction.
    """
    if "split" not in frame.columns:
        return
    n = int((frame["split"] == "holdout").sum())
    if n:
        raise HoldoutTouched(
            "%s received %d frozen-holdout rows; STATS-15 may only use %s"
            % (where, n, " and ".join(ALLOWED_SPLITS)))


def working_set(data: pd.DataFrame) -> pd.DataFrame:
    """Train and validation only, sorted by date."""
    out = data[data["split"].isin(ALLOWED_SPLITS)].copy()
    assert_no_holdout(out, "working_set")
    return out.sort_values(["date", "symbol"]).reset_index(drop=True)


def block_columns(frame: pd.DataFrame, block: str) -> list[str]:
    return [c for c in ds.FEATURE_BLOCKS.get(block, []) if c in frame.columns]


def feature_columns(frame: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for m in ds.FEATURE_BLOCKS:
        cols.extend(block_columns(frame, m))
    return list(dict.fromkeys(cols))


# ------------------------------------------------------------- perturbations ----

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
    rng = np.random.default_rng(seed)
    out = frame.copy()
    if not cols or severity <= 0:
        return out

    block = out[cols].to_numpy(float)
    mask = rng.random(block.shape) < severity

    if kind == "gaussian":
        sd = np.nanstd(block, axis=0)
        sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
        block = block + rng.normal(0.0, 1.0, block.shape) * sd * severity
    elif kind == "dropout":
        block = np.where(mask, np.nan, block)
    elif kind == "outliers":
        block = np.where(mask, block * 10.0, block)
    elif kind == "stale":
        # Shift each symbol's history forward by one observation, then apply that stale
        # copy to the selected rows only.
        stale = out.groupby("symbol", sort=False)[cols].shift(1).to_numpy(float)
        row_mask = (rng.random(len(out)) < severity)[:, None]
        block = np.where(row_mask & np.isfinite(stale), stale, block)
    else:
        raise ValueError("unknown corruption kind: %s" % kind)

    out[cols] = block
    return out


def blackout_block(frame: pd.DataFrame, block: str,
                      fraction: float, seed: int) -> pd.DataFrame:
    """Take a block offline for a fraction of rows, coverage flag included.

    Blanking the columns alone is not enough: the combination layer reads a coverage flag, so a
    block whose columns are NaN but whose flag still reads 1.0 keeps voting. That
    asymmetry is precisely how an induced-missingness result comes out too optimistic.
    """
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
class Fit:
    """One fitted arm and the metrics it produced on a given evaluation frame."""
    status: str
    metrics: dict
    reason: str | None = None


def _spec(seed: int, arm: str, blocks: list[str], note: str) -> ex.ExperimentSpec:
    return ex.ExperimentSpec(
        experiment_id="stats15", hypothesis=note, arm=arm,
        blocks=list(blocks), seed=seed, eval_split="validation",
        notes=[note])


def fit_and_score(train: pd.DataFrame, evald: pd.DataFrame, blocks: list[str],
                  seed: int, arm: str, note: str) -> Fit:
    """Fit on ``train``, score on ``evald``, with the holdout guard on both."""
    assert_no_holdout(train, "fit_and_score(train)")
    assert_no_holdout(evald, "fit_and_score(eval)")
    if train.empty or evald.empty or evald["is_episode"].nunique() < 2:
        return Fit("FAILED", {}, "degenerate split: %d train, %d eval, %d classes"
                   % (len(train), len(evald), evald["is_episode"].nunique()))

    # ExperimentSpec selects by split label, so relabel the two frames the harness is
    # meant to see. This is the whole point of routing through the same runner the
    # headline results use: the model, threshold rule and metrics are identical.
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


def _row(**kw) -> dict:
    return kw


# --------------------------------------------------------------- robustness ----

def input_robustness(data: pd.DataFrame, seed: int = 20260818,
                     severities: tuple[float, ...] = SEVERITIES,
                     blocks: list[str] | None = None,
                     log=None) -> pd.DataFrame:
    """Degrade the evaluation inputs only; the model is fitted once on clean data.

    Fitting once is the point. Refitting on corrupted data would measure whether the
    learner can adapt to a new noise regime, which is a different and easier question than
    what happens to a deployed model when its feed degrades.
    """
    work = working_set(data)
    mods = blocks or list(ds.FEATURE_BLOCKS)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    cols = feature_columns(work)

    clean = fit_and_score(train, evald, mods, seed, "clean", "undegraded reference")
    rows = [_row(family="input", corruption="none", target="all", severity=0.0,
                 status=clean.status, **clean.metrics)]
    base = clean.metrics.get("auprc", np.nan)
    if log:
        log("      clean reference auprc %.4f" % base)

    for kind in ("gaussian", "dropout", "stale", "outliers"):
        for sev in severities:
            degraded = perturb(evald, cols, kind, sev, seed)
            fit = fit_and_score(train, degraded, mods, seed, "%s@%.2f" % (kind, sev),
                                "evaluation inputs degraded")
            rows.append(_row(family="input", corruption=kind, target="all",
                             severity=float(sev), status=fit.status,
                             degradation=float(base - fit.metrics.get("auprc", np.nan)),
                             **fit.metrics))
            if log:
                log("        %-9s sev %.2f  auprc %.4f  (%+.4f)"
                    % (kind, sev, fit.metrics.get("auprc", np.nan),
                       fit.metrics.get("auprc", np.nan) - base))
    return pd.DataFrame(rows)


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


def training_size_curve(data: pd.DataFrame, seed: int = 20260818,
                        fractions: tuple[float, ...] = TRAIN_FRACTIONS,
                        n_repeats: int = 3, log=None) -> pd.DataFrame:
    """Learning curve over training-set size, subsampled by **symbol**.

    Symbols, not rows: rows from one instrument are serially dependent, so dropping random
    rows leaves almost every instrument represented and understates how much the model
    depends on breadth. Dropping whole symbols is the honest version of "less data".
    """
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    symbols = np.array(sorted(train["symbol"].unique()))

    rows = []
    for frac in fractions:
        for rep in range(n_repeats if frac < 1.0 else 1):
            rng = np.random.default_rng(seed + rep)
            k = max(2, int(round(len(symbols) * frac)))
            keep = rng.choice(symbols, size=k, replace=False)
            sub = train[train["symbol"].isin(keep)]
            fit = fit_and_score(sub, evald, mods, seed, "train@%.2f_r%d" % (frac, rep),
                                "reduced training set, symbol-level subsample")
            rows.append(_row(family="training_size", corruption="fewer_symbols",
                             target="train", severity=float(frac), repeat=rep,
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

def period_transfer(data: pd.DataFrame, seed: int = 20260818, n_folds: int = 4,
                    log=None) -> pd.DataFrame:
    """Expanding-window transfer forward in time, inside train and validation only.

    Each fold fits on everything before a cut date and scores the next block. This is the
    question a deployed detector actually faces -- yesterday's fit against tomorrow's
    market -- and it is not answered by a random split, which lets the model see the
    future of the very period it is scored on.
    """
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    dates = np.array(sorted(work["date"].unique()))
    if len(dates) < (n_folds + 1) * 5:
        return pd.DataFrame([_row(family="period", status="INSUFFICIENT DATA",
                                  note="only %d distinct dates" % len(dates))])

    bounds = np.array_split(dates, n_folds + 1)
    rows = []
    for i in range(n_folds):
        cut = bounds[i][-1]
        nxt = bounds[i + 1]
        tr = work[work["date"] <= cut]
        ev = work[(work["date"] > cut) & (work["date"] <= nxt[-1])]
        fit = fit_and_score(tr, ev, mods, seed, "period_fold%d" % (i + 1),
                            "fit on history, scored on the following period")
        rows.append(_row(family="period", fold=i + 1,
                         train_end=str(pd.Timestamp(cut).date()),
                         eval_start=str(pd.Timestamp(nxt[0]).date()),
                         eval_end=str(pd.Timestamp(nxt[-1]).date()),
                         n_train=int(len(tr)), n_eval=int(len(ev)),
                         eval_positive_rate=float(ev["is_episode"].mean())
                         if len(ev) else np.nan,
                         status=fit.status, reason=fit.reason, **fit.metrics))
        if log:
            log("        fold %d  train<=%s  eval %s..%s  auprc %.4f"
                % (i + 1, rows[-1]["train_end"], rows[-1]["eval_start"],
                   rows[-1]["eval_end"], rows[-1].get("auprc", np.nan)))
    return pd.DataFrame(rows)


def instrument_transfer(data: pd.DataFrame, seed: int = 20260818, n_groups: int = 4,
                        log=None) -> pd.DataFrame:
    """Fit on one disjoint set of instruments, score on the rest.

    No symbol appears on both sides, so this measures whether the detector learned
    something about market behaviour or something about these particular tickers.
    """
    work = working_set(data)
    mods = list(ds.FEATURE_BLOCKS)
    symbols = np.array(sorted(work["symbol"].unique()))
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(symbols)
    groups = np.array_split(shuffled, n_groups)

    rows = []
    for i, held in enumerate(groups, 1):
        held_set = set(held)
        tr = work[~work["symbol"].isin(held_set)]
        ev = work[work["symbol"].isin(held_set)]
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


def dataset_transfer_status() -> dict:
    """Cross-dataset transfer, reported as blocked rather than skipped."""
    return {
        "status": "BLOCKED",
        "reason": ("Only one dataset exists in this project, so there is no second "
                   "dataset to transfer to. This is reported rather than omitted: an "
                   "absent row in a generalization table reads as an untested axis, and "
                   "a fabricated one would be worse."),
        "what_would_unblock_it": (
            "A second panel built by the same feature pipeline over a different venue or "
            "instrument universe, with its own episode labels."),
    }
