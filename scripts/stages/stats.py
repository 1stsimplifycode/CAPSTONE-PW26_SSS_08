"""STATS module adapters (STATS-01 .. STATS-16).

Each function wraps canonical code. Read the manifest entry beside a function to see which
implementation it calls; nothing here reimplements a statistic.

Three of the sixteen are ``INFRASTRUCTURE_ONLY`` because the science genuinely does not
exist in the repository yet — verified by inspection, not assumed. Those return NOT YET
EXECUTED and write nothing.

PLAIN ENGLISH -- what this whole file is about:

THE SIXTEEN ANALYSES, EACH IN TWO VERSIONS.

This is the biggest file in the project, and it has a very simple shape once you see it.
Every one of the sixteen STATS modules appears TWICE:

  1. THE REGENERATING VERSION (the first half of the file). Runs over the whole dataset and
     WRITES result files to disk. Run deliberately, from a command line.

  2. THE LIVE VERSION (the second half, all named `analyse_*`). Runs over whatever slice
     somebody picked on the website -- these dates, these companies -- and WRITES NOTHING.

And crucially, BOTH CALL THE SAME UNDERLYING CODE. The website cannot show you a number
computed differently from the number in the paper, because there is only one implementation
of each calculation and both halves call it.

THE RULE OF THIS FILE, from the docstring: "nothing here reimplements a statistic."
Every function is a wrapper. It finds real code elsewhere, calls it, and packages the
answer. If a calculation were duplicated here it would eventually disagree with the
original, and nobody would notice.

AND WHERE THE SCIENCE DOES NOT EXIST YET, the module says so and writes nothing --
"verified by inspection, not assumed", which means somebody actually went and looked rather
than guessing.

THINGS TO WATCH FOR AS YOU READ:
  * every live function refuses a slice that is too small, with a REMEDY;
  * every result carries an `uncertainty` block saying how to read it;
  * every result carries a `provenance` block naming the code it called;
  * `wrote_nothing: True` appears on every single live result.
"""
from __future__ import annotations

import json
# subprocess runs another program; sys.executable is the exact Python running right now.
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.core import jsonio, paths
from scripts.stages import (
    OK,
    AnalysisResult,
    StageResult,
    insufficient,
    metric,
    require,
    series,
)

DATASET = paths.PANEL / "market_dataset.parquet"
PER_ROW = paths.ARTIFACTS / "experiments" / "per_row_FULL.parquet"

#: How many instruments STATS-06 will correlate at once. Pairs grow quadratically, and an
#: unbounded request over the whole universe is minutes of work for a table nobody reads.
# PLAIN ENGLISH: correlating 40 companies means 780 pairs. 400 companies would be 79,800 --
# a hundred times the work for ten times the companies. That is what "quadratically" means,
# and it is why there is a cap.
MAX_CORRELATED = 40


def _out(slug: str) -> Path:
    # Each module's output folder, created if it does not exist.
    d = paths.REPO_ROOT / "outputs" / "stats" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------- STATS-01 ----

def block_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per-block feature presence and mean fill, over whatever rows are handed in.

    Shared by the regenerating adapter and the live analysis so the two cannot compute
    coverage differently. It takes a frame rather than reading one, which is the whole
    reason the same function can serve a full-panel regeneration and a user-selected
    slice.
    """
    # PLAIN ENGLISH: the small design decision that makes the whole file work.
    # This function does NOT read a file. It is HANDED rows. So the exact same function can
    # be given the whole dataset (regenerating) or the twelve rows somebody picked on the
    # website (live) -- and the two can never compute coverage differently, because they are
    # literally the same code.
    from research.data import dataset as ds

    rows = []
    for block, cols in ds.FEATURE_BLOCKS.items():
        present = [c for c in cols if c in df.columns]
        rows.append({
            "block": block,
            # DECLARED vs PRESENT, side by side. If 20 features were designed and 12 exist,
            # both numbers are visible rather than only the 12.
            "declared_features": len(cols),
            "present_in_dataset": len(present),
            # The average share of rows that actually carry a value.
            "mean_non_null_fraction": float(df[present].notna().mean().mean())
            if present and len(df) else 0.0,
        })
    return pd.DataFrame(rows)


def integrity_profile(df: pd.DataFrame) -> dict:
    """Structural profile of a frame: counts, key uniqueness, splits, class balance."""
    from research.market import features as mf

    # The pair that should uniquely identify a row: one company, one day.
    key = ["symbol", "date"]
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "instruments": int(df["symbol"].nunique()),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())]
        if len(df) else [None, None],
        # DUPLICATE KEYS SHOULD BE ZERO. The same company on the same day appearing twice
        # means something went wrong upstream, and would double-count that day's evidence.
        "duplicate_keys": int(df.duplicated(subset=key).sum()),
        "split_sizes": {str(k): int(v) for k, v in df["split"].value_counts().items()}
        # "NOT PRESENT" rather than an empty dict -- the column being absent is a different
        # fact from there being no splits.
        if "split" in df.columns else "NOT PRESENT",
        "positive_rate": float(df["is_episode"].mean())
        if "is_episode" in df.columns and len(df) else None,
        # Columns that are entirely empty. Worth knowing before wondering why a feature
        # contributes nothing.
        "all_null_columns": sorted(c for c in df.columns if df[c].isna().all()),
        "coverage_report_available": hasattr(mf, "coverage_report"),
    }


def data_integrity_profile(force: bool = False) -> StageResult:
    """Wraps research.market.features.coverage_report + the block definitions."""
    # The walrus `:=` assigns and tests in one step: if `require` returns a problem, return
    # it immediately.
    if (r := require([DATASET])):
        return r
    df = pd.read_parquet(DATASET)
    out = _out("01_data_integrity_profile")

    cov = block_coverage(df)
    cov.to_csv(out / "block_coverage.csv", index=False)
    profile = integrity_profile(df)
    jsonio.write(out / "profile.json", profile)
    return StageResult(OK, "%d rows x %d cols, %d instruments, %d duplicate keys"
                       % (profile["rows"], profile["columns"],
                          profile["instruments"], profile["duplicate_keys"]),
                       outputs=[str(out / "profile.json"),
                                str(out / "block_coverage.csv")],
                       detail=profile)


# ------------------------------------------------------------------- STATS-02 ----

def universe_survivorship(force: bool = False) -> StageResult:
    """Wraps research.data.universe (membership table already built)."""
    # SURVIVORSHIP BIAS is one of the great traps in finance. Study "today's top 50
    # companies" over the last decade and you have quietly selected for the ones that
    # SURVIVED -- excluding every company that failed, was delisted, or fell out. Your
    # results look wonderful because the losers were never in the sample.
    # The fix is a POINT-IN-TIME universe: a company is in the January 2019 sample because
    # it qualified in January 2019, whatever happened to it afterwards.
    upath = paths.PANEL / "universe.parquet"
    if (r := require([upath])):
        return r
    out = _out("02_universe_survivorship")
    members = pd.read_parquet(upath)

    date_col = ("rebalance_date" if "rebalance_date" in members.columns
                else members.columns[0])
    per_rebalance = members.groupby(date_col)["symbol"].nunique()
    prev, entries, exits = None, [], []
    for _d, grp in members.groupby(date_col):
        cur = set(grp["symbol"])
        if prev is not None:
            # Set arithmetic: what is in the new list but not the old (joined), and what was
            # in the old but not the new (left).
            entries.append(len(cur - prev))
            exits.append(len(prev - cur))
        prev = cur
    churn = pd.DataFrame({"entries": entries, "exits": exits})
    churn.to_csv(out / "churn.csv", index=False)

    summary = {
        "rebalances": int(members[date_col].nunique()),
        # HOW MANY COMPANIES WERE EVER IN IT, which is larger than how many are in it now --
        # and that difference is precisely what survivorship bias would have thrown away.
        "distinct_members_ever": int(members["symbol"].nunique()),
        "members_per_rebalance_mean": float(per_rebalance.mean()),
        "mean_entries_per_rebalance": float(np.mean(entries)) if entries else None,
        "mean_exits_per_rebalance": float(np.mean(exits)) if exits else None,
        # AN EXPLICIT False, stored in the output file. Somebody could easily assume a list
        # of large Indian companies IS the Nifty 50. It is not, and the file says so.
        "is_index_membership": False,
        "caveat": "Point-in-time liquidity-proxy universe. Never the Nifty 50 (L-01).",
    }
    jsonio.write(out / "universe_summary.json", summary)
    return StageResult(OK, "%d rebalances, %d distinct ever, %.2f entries/rebalance"
                       % (summary["rebalances"], summary["distinct_members_ever"],
                          summary["mean_entries_per_rebalance"] or float("nan")),
                       outputs=[str(out / "universe_summary.json"),
                                str(out / "churn.csv")], detail=summary)


# ------------------------------------------------------------------- STATS-03 ----

def descriptive_distributions(force: bool = False) -> StageResult:
    """Wraps the block definitions; descriptive statistics via pandas."""
    if (r := require([DATASET])):
        return r
    from research.data import dataset as ds

    df = pd.read_parquet(DATASET)
    out = _out("03_descriptive_distributions")
    # A reverse lookup: feature name -> which block it belongs to.
    block_of = {c: b for b, cols in ds.FEATURE_BLOCKS.items() for c in cols}

    rows = []
    for c in ds.ALL_FEATURES:
        if c not in df.columns:
            continue
        # `errors="coerce"` turns anything unparseable into NaN rather than crashing.
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({
            "feature": c, "block": block_of.get(c, "?"),
            "non_null_fraction": float(s.notna().mean()),
            "n_distinct": int(s.nunique(dropna=True)),
            "mean": float(s.mean()), "std": float(s.std()),
            # Min, median and max -- so the shape is visible, not just the average.
            "min": float(s.min()), "p50": float(s.median()), "max": float(s.max()),
        })
    tbl = pd.DataFrame(rows)
    tbl.to_csv(out / "feature_summary.csv", index=False)

    # A feature with one distinct value cannot inform anything; one with a zero standard
    # deviation is the same condition seen from the other side. Both are surfaced rather
    # than left to be discovered as an unexplained zero importance later.
    # PLAIN ENGLISH: a feature that is 5 on every single row tells you nothing -- it cannot
    # separate anything from anything. It will show up later with zero importance, and
    # somebody will spend an afternoon wondering why. So it is flagged here, by name, in its
    # own file.
    degenerate = tbl[(tbl["n_distinct"] <= 1) | (tbl["std"].fillna(0) == 0)]
    degenerate.to_csv(out / "degenerate_features.csv", index=False)
    return StageResult(OK, "%d features profiled, %d degenerate"
                       % (len(tbl), len(degenerate)),
                       outputs=[str(out / "feature_summary.csv"),
                                str(out / "degenerate_features.csv")],
                       detail={"n_features": len(tbl), "n_degenerate": len(degenerate)})


# ------------------------------------------------------------------- STATS-04 ----

def market_microstructure(force: bool = False) -> StageResult:
    """Wraps research.market.features (feature lists + the NOT MEASURED register)."""
    # MICROSTRUCTURE means the fine detail of trading -- who bid what, at what moment, how
    # deep the order book was. This project only has DAILY summaries: open, high, low, close,
    # volume. From those you can build PROXIES -- rough stand-ins -- but not the real thing.
    # And the module keeps a register of exactly what daily bars CANNOT see.
    if (r := require([DATASET])):
        return r
    from research.market import features as mf

    df = pd.read_parquet(DATASET)
    out = _out("04_market_microstructure")
    rows = []
    for name, cols in (("market", mf.MARKET_FEATURES),
                       ("microstructure_proxy", mf.MICROSTRUCTURE_PROXIES)):
        for c in cols:
            if c not in df.columns:
                # Recorded as present=False rather than skipped -- so a declared feature that
                # went missing is visible in the output.
                rows.append({"group": name, "feature": c, "present": False})
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            rows.append({"group": name, "feature": c, "present": True,
                         "non_null_fraction": float(s.notna().mean()),
                         "std": float(s.std())})
    pd.DataFrame(rows).to_csv(out / "market_coverage.csv", index=False)
    # THE "NOT MEASURED" REGISTER, SAVED AS ITS OWN FILE. These are not missing values --
    # they are quantities this data source cannot express at all. A completely different
    # kind of absence, and it gets its own artifact.
    jsonio.write(out / "not_measured.json", {
        "not_measured": mf.MICROSTRUCTURE_NOT_MEASURED,
        "caveat": "Daily-bar proxies are not order-book microstructure (L-02).",
    })
    return StageResult(OK, "%d market + %d microstructure-proxy features; %d quantities "
                       "recorded NOT MEASURED"
                       % (len(mf.MARKET_FEATURES), len(mf.MICROSTRUCTURE_PROXIES),
                          len(mf.MICROSTRUCTURE_NOT_MEASURED)),
                       outputs=[str(out / "market_coverage.csv"),
                                str(out / "not_measured.json")])


# ------------------------------------------------------------------- STATS-05 ----

def regime_statistics(force: bool = False) -> StageResult:
    """Wraps the regime labels already assembled into the dataset."""
    # A REGIME is a market mood: calm, volatile, trending. The same behaviour means different
    # things in different regimes.
    if (r := require([DATASET])):
        return r
    df = pd.read_parquet(DATASET)
    if "regime_id" not in df.columns:
        # 4 is INPUTS_MISSING -- the code exists, the data does not.
        return StageResult(4, "regime_id absent from the dataset")
    out = _out("05_regime_statistics")

    occ = (df.groupby("regime_id").size().rename("rows").reset_index())
    occ["share"] = occ["rows"] / occ["rows"].sum()
    if "is_episode" in df.columns:
        # The episode rate per regime -- are episodes concentrated in one market mood?
        occ = occ.merge(df.groupby("regime_id")["is_episode"].mean()
                        .rename("positive_rate").reset_index(), on="regime_id")
    occ.to_csv(out / "regime_occupancy.csv", index=False)
    # THE LARGEST REGIME'S SHARE IN THE HEADLINE. If one regime holds 80% of the rows, then
    # "regime-aware" analysis is mostly analysis of that one regime.
    return StageResult(OK, "%d regimes, largest holds %.1f%% of rows"
                       % (len(occ), 100 * occ["share"].max()),
                       outputs=[str(out / "regime_occupancy.csv")])


# ------------------------------------------------------------------- STATS-06 ----

def dependence_propagation(force: bool = False) -> StageResult:
    """Wraps research.propagation.graph (feature register + assembled coverage)."""
    if (r := require([DATASET])):
        return r
    from research.propagation import graph as pg

    df = pd.read_parquet(DATASET)
    out = _out("06_dependence_propagation")
    present = [c for c in pg.PROPAGATION_FEATURES if c in df.columns]
    summary = {
        "propagation_features_declared": list(pg.PROPAGATION_FEATURES),
        "present_in_dataset": present,
        "mean_non_null_fraction": float(df[present].notna().mean().mean())
        if present else 0.0,
        "per_feature_mean": {c: float(pd.to_numeric(df[c], errors="coerce").mean())
                             for c in present},
        # THE CAVEAT THAT MATTERS MOST IN THIS MODULE, and it is the difference between two
        # very different claims.
        # CO-MOVEMENT: these two share prices tend to move together.
        # PROPAGATION: this one CAUSED that one to move.
        # The data supports the first and says nothing about the second. Two stocks moving
        # together may both be responding to a third thing entirely.
        "caveat": "Statistical co-movement, not causal propagation (L-07).",
    }
    jsonio.write(out / "graph_summary.json", summary)
    return StageResult(OK, "%d propagation features present, mean coverage %.3f"
                       % (len(present), summary["mean_non_null_fraction"]),
                       outputs=[str(out / "graph_summary.json")], detail=summary)


# ------------------------------------------------------------------- STATS-07 ----

def tail_extreme_risk(force: bool = False) -> StageResult:
    """Wraps research.risk.gate.tail_metrics.

    ``tail_metrics`` expects a **net return series**: it compounds its input with
    ``cumprod(1 + r)`` to build an equity curve. An earlier version of this adapter passed
    the integrity-risk score instead, which is bounded in [0, 1] and strictly positive, so
    the equity curve diverged and the record came back with ``total_return = Infinity``.
    The forward return is therefore built here exactly as the canonical
    capital-consequence path builds it in ``scripts/generate_paper_artifacts.py``:
    next-session percentage change in close, per instrument.
    """
    # PLAIN ENGLISH: A REAL BUG, WRITTEN DOWN IN THE CODE THAT FIXED IT.
    # `tail_metrics` wants RETURNS -- numbers like +0.02 and -0.015, which can be negative.
    # An earlier version handed it the RISK SCORE instead, which is always between 0 and 1
    # and always positive. Compounding a series that is never negative makes a value that
    # only ever grows, so the "total return" came back as INFINITY.
    # Keeping the story here means nobody repeats it, and a reader can see why the forward
    # return is constructed so carefully below.
    cash = paths.PANEL / "cash_panel.parquet"
    if (r := require([PER_ROW, cash])):
        return r
    from research.risk import gate

    scored = pd.read_parquet(PER_ROW)
    out = _out("07_tail_extreme_risk")

    panel = pd.read_parquet(cash, columns=["symbol", "date", "close"])
    fwd = panel.sort_values(["symbol", "date"]).copy()
    # `pct_change()` is today versus yesterday; `.shift(-1)` moves it back one row so each
    # row carries TOMORROW's move. `groupby("symbol")` keeps one company's last day from
    # being compared with the next company's first.
    fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
    merged = (scored.merge(fwd[["symbol", "date", "fwd_ret"]], on=["symbol", "date"],
                           how="left").dropna(subset=["fwd_ret"]))
    if len(merged) < 20:
        # REFUSES rather than computing tail statistics from 19 numbers.
        return StageResult(4, "only %d rows carry a forward return; tail_metrics needs "
                              "at least 20" % len(merged))

    net = merged["fwd_ret"].to_numpy(float)
    # `isfinite` drops any infinities or NaNs before the calculation.
    metrics = gate.tail_metrics(net[np.isfinite(net)])
    # WHAT THE SERIES ACTUALLY IS, in words, attached to the numbers.
    metrics["series"] = "next-session return of the scored instrument-days"
    # BOTH COUNTS: how many rows were scored, and how many had a forward return. If those
    # differ a lot, the reader can see it.
    metrics["n_scored_rows"] = int(len(scored))
    metrics["n_rows_with_forward_return"] = int(len(merged))
    metrics["note"] = ("Unconditional tail statistics of the realised return over the "
                       "scored rows. This is the input distribution the exposure gate "
                       # AND THE FLAT REFUSAL TO BE READ AS ADVICE: "no allocation or
                       # position size is produced anywhere in this module."
                       "acts on, not the result of applying it, and no allocation or "
                       "position size is produced anywhere in this module.")

    # Corporate-action diagnostic. The close series is not adjusted for splits and
    # bonuses, so a 10:1 split reads as a -90% session. One such row is enough to
    # dominate a drawdown statistic, and reporting max_drawdown without saying so would
    # be reporting a corporate action as a market loss. The metric is left untouched and
    # the contamination is reported beside it: see KI-06.
    # PLAIN ENGLISH: A SHARE SPLIT is when a company turns one 1000-rupee share into ten
    # 100-rupee shares. Nobody lost anything. But the raw price series shows the price
    # dropping from 1000 to 100 -- which looks like a 90% CRASH.
    # One such day would dominate any "worst drawdown" figure and turn a bookkeeping event
    # into an apparent catastrophe.
    # AND THE HANDLING IS THE INTERESTING PART: the metric is NOT quietly cleaned. It is
    # reported unmodified, with the suspect rows listed beside it and a clean version
    # alongside -- because silently altering it would make it incomparable with the other
    # path that builds returns the same way.
    extreme = merged.loc[merged["fwd_ret"].abs() > 0.5, ["symbol", "date", "fwd_ret"]]
    clean = merged.loc[merged["fwd_ret"].abs() <= 0.5, "fwd_ret"]
    metrics["corporate_action_suspects"] = {
        "threshold_abs_return": 0.5,
        "n_rows": int(len(extreme)),
        # EVERY SUSPECT ROW LISTED BY NAME AND DATE, so a reader can go and check whether it
        # really was a split.
        "rows": [{"symbol": str(r.symbol), "date": str(pd.Timestamp(r.date).date()),
                  "fwd_ret": float(r.fwd_ret)} for r in extreme.itertuples(index=False)],
        # AND THE CLEAN VERSION ALONGSIDE, so both readings are available.
        "worst_day_excluding_suspects": float(clean.min()) if len(clean) else None,
        "caveat": ("Prices are unadjusted for splits and bonuses. Rows above the "
                   "threshold are almost certainly corporate actions rather than "
                   "returns, and max_drawdown and worst_day above are contaminated by "
                   "them. Tracked as KI-06; the metric is reported unmodified so it "
                   "stays comparable with the existing capital-consequence path, which "
                   "builds its return series the same way."),
    }
    jsonio.write(out / "tail_metrics.json", metrics)
    return StageResult(OK, "tail metrics over %d of %d scored rows (CVaR %.5f)"
                       % (len(merged), len(scored), metrics["cvar"]),
                       outputs=[str(out / "tail_metrics.json")], detail=metrics)


# ------------------------------------------------------------------- STATS-08 ----

def episode_event_statistics(force: bool = False) -> StageResult:
    """Wraps the injected-episode labels produced by research.detection.episodes."""
    epath = paths.PANEL / "episode_labels.parquet"
    if (r := require([epath])):
        return r
    lab = pd.read_parquet(epath)
    out = _out("08_episode_event_statistics")
    summary: dict = {"rows": int(len(lab)), "columns": sorted(lab.columns)}
    # Every field guarded by an `if ... in columns` -- the summary describes whatever the
    # file actually contains rather than assuming a shape.
    if "episode_id" in lab.columns:
        summary["episodes"] = int(lab["episode_id"].nunique())
    if "symbol" in lab.columns:
        summary["instruments_with_episodes"] = int(lab["symbol"].nunique())
    for c in ("intensity", "duration", "n_sessions"):
        if c in lab.columns:
            s = pd.to_numeric(lab[c], errors="coerce")
            summary[c] = {"mean": float(s.mean()), "min": float(s.min()),
                          "max": float(s.max())}
    # THE CENTRAL HONESTY OF THE WHOLE PROJECT, in two sentences. The episodes were CREATED
    # by this project and injected into real price data. So every detection result measures
    # detection of a known construction -- and NO result from them describes real-world
    # manipulation. Stated in the artifact itself, not only on a web page.
    summary["caveat"] = ("Episodes are synthetic, injected into real price data (L-04). "
                         "No result from them describes real-world manipulation.")

    # Additive: the count-based event detector, which consumes the Week 2 arrival
    # dispersion. The synthetic-episode summary above is unchanged; this is a second,
    # independent view of the same week built on real exchange trade counts. If Week 2
    # has not published its result the block reports that rather than falling back to a
    # Poisson band this repository has measured to be wrong.
    # PLAIN ENGLISH: a SECOND view, built on REAL exchange trade counts rather than
    # synthetic labels.
    # AND THE REFUSAL AT THE END IS THE GOOD BIT: the fallback would be a Poisson band --
    # the "trades arrive like raindrops" assumption. This repository has MEASURED that
    # assumption and found it wrong. So rather than fall back to a method known to be
    # incorrect, it reports that the input is unavailable, and how to produce it.
    outputs = [str(out / "episode_summary.json")]
    try:
        from research.detection import count_events as ce

        detector = ce.CountEventDetector.from_week2()
        counts = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                                 columns=["symbol", "date", "trades"])
        uni = pd.read_parquet(paths.PANEL / "universe.parquet")
        members = set(uni[uni["rebalance_date"] == uni["rebalance_date"].max()]["symbol"])
        detected = detector.detect(counts[counts["symbol"].isin(members)])
        summary["count_events"] = ce.summary(detected, detector)
        jsonio.write(out / "count_event_summary.json", summary["count_events"])
        outputs.append(str(out / "count_event_summary.json"))
    except ce_missing_week2() as exc:            # noqa: F821 - resolved below
        # NOT AVAILABLE, WHY, AND THE EXACT COMMAND TO FIX IT. The three-part refusal used
        # everywhere in this project.
        summary["count_events"] = {
            "available": False,
            "why": str(exc),
            "remedy": "Run scripts/build_week2_foundation.py to publish the Week 2 "
                      "arrival-dispersion result.",
        }

    jsonio.write(out / "episode_summary.json", summary)
    return StageResult(OK, "%d label rows, %s episodes"
                       % (summary["rows"], summary.get("episodes", "?")),
                       outputs=outputs, detail=summary)


def ce_missing_week2():
    """The exception the count detector raises when Week 2 has not published.

    Resolved lazily so that importing this module does not require the Week 2 package to
    be importable, which keeps the existing STATS-08 path working on a checkout where the
    market foundation has not been built.
    """
    # PLAIN ENGLISH: an unusual little trick, for a good reason.
    # `except SomeError:` normally needs that error type to exist the moment the file loads.
    # If the Week 2 package is not built, that import would fail and this ENTIRE FILE would
    # become unimportable -- taking all sixteen modules down with it.
    # So the exception type is fetched by CALLING a function, at the moment it is needed.
    # A missing optional part stays optional.
    from research.detection.count_events import MissingWeek2Input
    return MissingWeek2Input


# ------------------------------------------------------------------- STATS-09 ----

def leakage_verification(force: bool = False) -> StageResult:
    """Wraps tests/leakage — the L1-L6 suite, run read-only."""
    # LEAKAGE is information from the future reaching a decision made in the past. It is the
    # single most damaging error possible here, because it does not look like an error -- it
    # looks like an excellent result.
    out = _out("09_leakage_verification")
    # Runs the real test suite, right now, as a separate program.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/leakage", "-q", "--no-header"],
        cwd=str(paths.REPO_ROOT), capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    report = {"returncode": proc.returncode, "summary": tail,
              "suite": "tests/leakage (L1-L6)",
              # THE CONSEQUENCE SPELLED OUT: a failure here does not mean "one test is
              # broken", it means EVERY DOWNSTREAM RESULT IS INVALID. Which is why the suite
              # blocks the build rather than merely warning.
              "interpretation": "A non-zero return code invalidates every downstream "
                                "result, which is why this suite is blocking in CI."}
    jsonio.write(out / "leakage_report.json", report)
    # The module's own status mirrors the suite's: if leakage tests fail, this module FAILS.
    return StageResult(OK if proc.returncode == 0 else 1,
                       tail or "pytest produced no summary",
                       outputs=[str(out / "leakage_report.json")], detail=report)


# ------------------------------------------------------------------- STATS-10 ----

def validation_verification(force: bool = False) -> StageResult:
    """Wraps research.evaluation.metrics.verification_report.

    The operating threshold is **read from the experiment bundle**, where it was selected
    on the training split. Recomputing it here from the evaluation scores would be
    threshold-provenance leakage (L6) and would quietly flatter every metric below.
    """
    # PLAIN ENGLISH: THE SUBTLE CHEAT THIS MODULE REFUSES TO COMMIT.
    # Picking the cutoff that makes your evaluation numbers look best is choosing the
    # question after seeing the answer. The metrics that follow are then not evidence about
    # unseen data -- they are a description of this data at its most flattering angle.
    # The word "quietly" is exact: nothing would break, no warning would appear, and every
    # number would simply be a little too good.
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import metrics as mx

    bundles = sorted((paths.REPORTS).glob("*FULL*/metrics.json"))
    if not bundles:
        # AND IT WOULD RATHER PRODUCE NOTHING THAN CHOOSE ONE ITSELF. The refusal message
        # says so outright: "this module will not choose one on the evaluation split."
        return StageResult(4, "no FULL experiment bundle under %s; the train-selected "
                              "threshold is unavailable and this module will not choose "
                              "one on the evaluation split" % paths.REPORTS)
    bundle = json.loads(bundles[0].read_text(encoding="utf-8"))
    threshold = bundle.get("detection", {}).get("threshold")
    if threshold is None:
        return StageResult(4, "the FULL bundle records no threshold")

    scored = pd.read_parquet(PER_ROW)
    out = _out("10_validation_verification")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)

    report = mx.verification_report(y, p, float(threshold))
    # WHERE THE THRESHOLD CAME FROM, recorded in the output. So the provenance claim above is
    # checkable rather than merely asserted.
    report["threshold_source"] = str(bundles[0].relative_to(paths.REPO_ROOT).as_posix())
    report["metrics_version"] = mx.METRICS_VERSION
    mx.confusion_matrix_frame(y, p, float(threshold)).to_csv(
        out / "confusion_matrix.csv")
    mx.per_class_report(y, p, float(threshold)).to_csv(
        out / "per_class.csv", index=False)
    jsonio.write(out / "verification_metrics.json", report)

    m = report["metrics"]
    # ALL FOUR CELLS OF THE CONFUSION MATRIX IN THE HEADLINE -- true and false, positive and
    # negative. A single accuracy figure would hide which kind of mistake it makes.
    return StageResult(OK, "n=%d thr=%.4f  TP=%d TN=%d FP=%d FN=%d  acc=%.4f "
                       "bal_acc=%.4f MCC=%.4f"
                       % (m["n"], m["threshold"], m["tp"], m["tn"], m["fp"], m["fn"],
                          m["accuracy"], m["balanced_accuracy"], m["mcc"]),
                       outputs=[str(out / "verification_metrics.json"),
                                str(out / "confusion_matrix.csv"),
                                str(out / "per_class.csv")],
                       detail=m)


# ------------------------------------------------------------------- STATS-11 ----

def calibration_uncertainty(force: bool = False) -> StageResult:
    """Wraps evaluation.metrics + information (reliability, ECE, selective risk)."""
    # CALIBRATION: when it says 0.7, does the thing happen 70% of the time?
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import information as inf
    from research.evaluation import metrics as mx

    scored = pd.read_parquet(PER_ROW)
    out = _out("11_calibration_uncertainty")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)

    # The reliability curve: predicted score against what actually happened, bin by bin.
    rel = mx.reliability_curve(y, p)
    rel.to_csv(out / "reliability.csv", index=False)
    payload = {
        # ECE: the average gap between what was predicted and what occurred.
        "ece": mx.expected_calibration_error(y, p),
        "detection": mx.detection_metrics(y, p),
        # AND THE CAVEAT THAT MATTERS: the score is a RANKING, not a probability. 0.7 does
        # not mean seven in ten. Stated in the artifact so it travels with the numbers.
        "caveat": "The risk score is not a calibrated probability (L-10).",
    }
    if "uncertainty" in scored.columns:
        sel = inf.selective_risk(y, p, scored["uncertainty"].to_numpy(float))
        sel.to_csv(out / "selective_risk.csv", index=False)
        payload["selective_risk_rows"] = int(len(sel))
    jsonio.write(out / "calibration.json", payload)
    return StageResult(OK, "ECE %.4f over %d rows" % (payload["ece"], len(scored)),
                       outputs=[str(out / "reliability.csv"),
                                str(out / "calibration.json")])


# ------------------------------------------------------------------- STATS-12 ----

def error_analysis(force: bool = False) -> StageResult:
    """Wraps research.evaluation.metrics.classify_errors."""
    # NOT how many mistakes, but WHAT KIND. A row scored wrongly because the evidence was
    # missing is a data problem; a row scored wrongly with full evidence is a model problem.
    # Treating them as one number sends the reader looking in the wrong place.
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import metrics as mx

    scored = pd.read_parquet(PER_ROW)
    out = _out("12_error_analysis")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)
    # NOTE: best_f1_threshold here. This is the module the thresholds page singles out -- it
    # uses the best-F1 cutoff ONLY to sort errors into buckets, and never to report a metric.
    # Bucketing is a legitimate use of it; quoting a score at it would not be.
    thr = mx.best_f1_threshold(y, p)
    tax = mx.classify_errors(scored, thr)
    tax.to_csv(out / "error_taxonomy.csv", index=False)
    return StageResult(OK, "error taxonomy at threshold %.3f (%d rows)" % (thr, len(tax)),
                       outputs=[str(out / "error_taxonomy.csv")],
                       detail={"threshold": float(thr)})


# ------------------------------------------------------------- STATS-13 / 14 ----

def _run_experiments(label: str) -> StageResult:
    """Both baseline comparison and the ablation study come from one runner.

    Kept as a single invocation deliberately: running it twice would fit the same arms
    twice and produce two artifact sets that could silently disagree.
    """
    # PLAIN ENGLISH: STATS-13 and STATS-14 are two questions with one answer file. Running
    # the experiment twice would fit the same models twice -- with different random draws --
    # and leave two sets of results that disagree slightly. Nobody would know which was
    # "the" result. So one run serves both.
    proc = subprocess.run([sys.executable, "scripts/run_experiments.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_experiments.py exited %d" % proc.returncode)
    return StageResult(OK, "%s regenerated via scripts/run_experiments.py" % label,
                       outputs=[str(paths.ARTIFACTS / "experiments")])


def baseline_comparison(force: bool = False) -> StageResult:
    return _run_experiments("baseline comparison")


def ablation_study(force: bool = False) -> StageResult:
    return _run_experiments("ablation study")


# ------------------------------------------------------------------- STATS-15 ----

def robustness_generalization(force: bool = False) -> StageResult:
    """Wraps scripts/run_robustness_generalization.py.

    Runs the whole sweep rather than reading a cached artifact, for the same reason
    STATS-13/14 does: a module that reports numbers it did not produce cannot tell a stale
    artifact from a current one.
    """
    # PLAIN ENGLISH: it would be far quicker to read yesterday's saved answer. But then the
    # module could not tell the difference between "these are the current numbers" and
    # "these are from before the last three code changes". So it runs the whole thing.
    out = paths.REPO_ROOT / "outputs" / "stats" / "15_robustness_generalization"
    proc = subprocess.run(
        [sys.executable, "scripts/run_robustness_generalization.py", "--all"],
        cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_robustness_generalization.py exited %d"
                           % proc.returncode)

    summary = json.loads((out / "run.json").read_text(encoding="utf-8"))
    # `or {}` so a missing section becomes an empty dict rather than crashing the summary
    # line below.
    worst = summary.get("worst_degradation") or {}
    period = summary.get("period_transfer") or {}
    instrument = summary.get("instrument_transfer") or {}
    return StageResult(
        OK,
        # THE HEADLINE LEADS WITH THE WORST DEGRADATION, not the best result. And it ends
        # with the count of holdout rows left untouched -- the promise, restated every run.
        "%d robustness rows, %d generalization rows; worst degradation %s at %.2f "
        "(auprc %.4f); period transfer auprc %.4f, instrument transfer auprc %.4f; "
        "%d holdout rows untouched"
        % (summary.get("robustness_rows", 0), summary.get("generalization_rows", 0),
           worst.get("corruption", "-"), worst.get("severity", 0.0),
           worst.get("auprc", float("nan")),
           period.get("auprc_mean", float("nan")),
           instrument.get("auprc_mean", float("nan")),
           summary.get("n_rows_frozen_and_unused", 0)),
        outputs=[str(out / "robustness.csv"), str(out / "generalization.csv"),
                 str(out / "run.json")],
        detail=summary)


# ------------------------------------------------------------------- STATS-16 ----

def multiseed_significance(force: bool = False) -> StageResult:
    """Wraps scripts/run_multiseed.py."""
    out = paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"
    proc = subprocess.run([sys.executable, "scripts/run_multiseed.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_multiseed.py exited %d" % proc.returncode)

    summary = json.loads((out / "significance.json").read_text(encoding="utf-8"))
    floor = summary.get("seed_noise_floor") or {}
    survives = summary.get("differences_surviving_correction") or []
    dissolves = summary.get("differences_within_seed_noise") or []
    return StageResult(
        OK,
        # AND THE HEADLINE REPORTS BOTH: how many differences survived, and how many
        # DISSOLVED INTO SEED VARIANCE. The disappointing half is in the summary line, not
        # hidden in a file.
        "%d arms x %d seeds (%d/%d fits OK); pooled seed sd %.5f, 95%% noise floor "
        "%.5f auprc; %d of %d arm differences survive Benjamini-Hochberg, %d dissolve "
        "into seed variance"
        % (summary.get("n_arms", 0), summary.get("n_seeds", 0),
           summary.get("n_fits_ok", 0), summary.get("n_fits", 0),
           floor.get("pooled_seed_sd", float("nan")),
           floor.get("noise_floor_95", float("nan")),
           len(survives), len(survives) + len(dissolves), len(dissolves)),
        outputs=[str(out / "seed_table.csv"), str(out / "significance.json"),
                 str(out / "seed_summary.csv"), str(out / "paired_tests.csv")],
        detail=summary)


# -- live analysis -------------------------------------------------------------------
#
# These run on request, over the slice the caller selected, and write nothing. They call
# the same functions the regenerating adapters above call; what differs is that a slice
# arrives as validated parameters and no artifact is touched.
#
# PLAIN ENGLISH: EVERYTHING BELOW IS THE INTERACTIVE HALF.
# Somebody on the website picks a date range and some companies, and presses a button.
# These functions answer -- computing for real, right now, over exactly those rows -- and
# WRITE NOTHING AT ALL.
#
# THE SHARED SHAPE OF EVERY ONE OF THEM:
#   1. slice the data to what was asked for;
#   2. REFUSE if the slice is too small, with a remedy;
#   3. compute, using the same canonical code the artifact half uses;
#   4. return metrics, tables, observations, an `uncertainty` block saying how to read it,
#      and a `provenance` block naming the code that was called;
#   5. `wrote_nothing: True`.
#
# Watch how consistently step 2 appears. It would be far easier to return a number over
# eleven rows and add a small footnote. Refusing is more work and better behaviour.


def analyse_data_integrity(date_from: str | None = None, date_to: str | None = None,
                           instruments: list[str] | None = None,
                           split: str = "all") -> AnalysisResult:
    """STATS-01 live: profile the slice the caller selected.

    Same block-coverage and structural-profile functions the regenerating adapter uses,
    over a filtered frame. A caller asking about January 2022 for three instruments gets
    the coverage of those rows, computed now, and not the whole-panel figure with a
    filter applied to the label.
    """
    # PLAIN ENGLISH: the last sentence names the fake that this avoids. A cheap
    # implementation would show the whole-dataset number and just change the caption to say
    # "January 2022, three instruments". The number would be a lie with an accurate label.
    # Here the number is genuinely recomputed over those rows.
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        # THE REFUSAL: what happened, why it is not enough, and how to fix it.
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for a coverage "
            "profile to mean anything" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    # THE SAME TWO FUNCTIONS THE ARTIFACT VERSION USES, at the top of this file.
    profile = integrity_profile(df)
    cov = block_coverage(df).sort_values("mean_non_null_fraction", ascending=False)
    thin = cov[cov["mean_non_null_fraction"] < 0.9]

    metrics = [
        # Every metric carries a plain-English note explaining what it is.
        metric("rows", "Rows in this slice", profile["rows"], "int",
               "instrument-days matching your selection"),
        metric("instruments", "Instruments", profile["instruments"], "int",
               "distinct symbols in the slice"),
        metric("columns", "Columns", profile["columns"], "int",
               "features plus metadata"),
        metric("duplicate_keys", "Duplicate keys", profile["duplicate_keys"], "int",
               # "zero is the only acceptable value" -- the note tells the reader how to
               # judge the number, not merely what it is.
               "symbol-date pairs appearing twice; zero is the only acceptable value"),
        metric("positive_rate", "Episode rate", profile["positive_rate"], "pct",
               # The synthetic-episode caveat, attached even to a simple count.
               "share of rows inside an injected episode (limitation L-04)"),
        metric("blocks_thin", "Blocks below 90% fill", int(len(thin)), "int",
               "feature blocks whose mean fill is under 0.9 on this slice"),
    ]
    observations = [
        # THE FIRST OBSERVATION IS ALWAYS THE SCOPE: computed on YOUR rows, not the panel.
        "Coverage was computed on the %d rows you selected, not on the whole panel."
        % profile["rows"],
        "Key uniqueness holds: %d duplicate symbol-date pairs."
        % profile["duplicate_keys"],
    ]
    if len(thin):
        observations.append(
            # Names the WORST block, rather than reporting a comforting average.
            "Thinnest block on this slice: %s at %.1f%% mean fill."
            % (thin.iloc[-1]["block"],
               100 * float(thin.iloc[-1]["mean_non_null_fraction"])))
    else:
        observations.append("Every feature block is at or above 90% mean fill here.")
    if profile["all_null_columns"]:
        observations.append(
            "%d column(s) are entirely empty on this slice: %s."
            % (len(profile["all_null_columns"]),
               ", ".join(profile["all_null_columns"][:6])))

    return AnalysisResult(
        dataset=live.describe_slice(
            df, "data/panel/market_dataset.parquet",
            date_from=date_from, date_to=date_to, instruments=instruments,
            split=split),
        metrics=metrics,
        series=[
            series("block_coverage", "Feature block coverage on this slice",
                   list(cov.columns), cov.values.tolist(),
                   "mean_non_null_fraction is the average fill across the block's "
                   "features on the selected rows"),
            series("split_sizes", "Rows per split in this slice",
                   ["split", "rows"],
                   [[k, v] for k, v in (profile["split_sizes"] or {}).items()]
                   if isinstance(profile["split_sizes"], dict) else [],
                   # The holdout is COUNTED and declared never scored -- so a reader is not
                   # left wondering whether those rows were quietly used.
                   "the frozen holdout is included in the count and is never scored"),
        ],
        observations=observations,
        uncertainty={
            # "none" -- and the reason is exactly right. These are COUNTS of what is there,
            # not estimates of anything. Attaching a confidence interval to a count would
            # imply an uncertainty that does not exist.
            "kind": "none",
            "reading": ("These are counts and fill rates over the rows you selected, "
                        "not estimates. They carry no sampling interval because nothing "
                        "was estimated."),
        },
        provenance={
            # THE EXACT FUNCTIONS THAT PRODUCED THIS. A reader can open them.
            "canonical_called": [
                "scripts.stages.stats:integrity_profile",
                "scripts.stages.stats:block_coverage",
                "research.data.dataset:FEATURE_BLOCKS",
            ],
            "rows_considered": profile["rows"],
            # THE PROMISE, ON EVERY LIVE RESULT.
            "wrote_nothing": True,
        },
        message="%d rows across %d instruments profiled live"
                % (profile["rows"], profile["instruments"]),
    )


# ------------------------------------------------------------------- STATS-02 ----

def analyse_universe(date_from: str | None = None,
                     date_to: str | None = None) -> AnalysisResult:
    """STATS-02 live: membership and churn over the rebalances in the chosen window.

    Survivorship is a property of a window, not of a dataset, so asking about one window
    is the only way the question has an answer. A universe that looks stable over eleven
    years can be turbulent over one of them.
    """
    # PLAIN ENGLISH: a genuinely good insight. "How much does this list churn?" has no single
    # answer -- it depends entirely on WHEN you ask. Eleven years of gentle averages can hide
    # one violent year. So the question is only answerable for a window, and the window is
    # the caller's to choose.
    from scripts.stages import live

    members = live.universe()
    date_col = ("rebalance_date" if "rebalance_date" in members.columns
                else members.columns[0])
    sel = members
    if date_from:
        sel = sel[sel[date_col] >= pd.Timestamp(date_from)]
    if date_to:
        sel = sel[sel[date_col] <= pd.Timestamp(date_to)]
    rebalances = sorted(sel[date_col].unique())
    if len(rebalances) < 2:
        # CHURN IS A CHANGE, so it needs at least two moments to compare. One rebalance
        # cannot show any.
        return insufficient(
            "the selected window contains %d rebalance date(s); churn needs at least two"
            % len(rebalances),
            "Widen the date range so it spans more than one rebalance.")

    rows, prev = [], None
    for d in rebalances:
        cur = set(sel.loc[sel[date_col] == d, "symbol"])
        rows.append({
            "rebalance_date": str(pd.Timestamp(d).date()),
            "members": len(cur),
            # None for the first row -- there is nothing before it to compare against. Not
            # zero, which would claim "nothing changed".
            "entries": len(cur - prev) if prev is not None else None,
            "exits": len(prev - cur) if prev is not None else None,
        })
        prev = cur
    churn = pd.DataFrame(rows)
    entries = churn["entries"].dropna()
    exits = churn["exits"].dropna()
    # EVER a member: the union across all rebalances.
    ever = int(sel["symbol"].nunique())
    # ALWAYS a member: the intersection -- present at every single one. `*[...]` spreads the
    # list of sets into separate arguments for `set.intersection`.
    always = len(set.intersection(*[
        set(sel.loc[sel[date_col] == d, "symbol"]) for d in rebalances]))

    metrics = [
        metric("rebalances", "Rebalances in this window", len(rebalances), "int",
               "reconstitution dates covered by your selection"),
        metric("ever", "Instruments ever a member", ever, "int",
               "the union across those rebalances"),
        metric("always", "Members at every rebalance", always, "int",
               # THE SURVIVORSHIP GAP, NAMED. The difference between "ever" and "always" is
               # exactly the set of companies a naive study would have deleted.
               "the intersection; the difference from the union is the survivorship gap"),
        metric("members_mean", "Members per rebalance",
               float(churn["members"].mean()), "float2"),
        metric("entries_mean", "Entries per rebalance",
               float(entries.mean()) if len(entries) else 0.0, "float2"),
        metric("exits_mean", "Exits per rebalance",
               float(exits.mean()) if len(exits) else 0.0, "float2"),
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/universe.parquet",
                 "rows": int(len(sel)),
                 "date_from": str(pd.Timestamp(rebalances[0]).date()),
                 "date_to": str(pd.Timestamp(rebalances[-1]).date()),
                 "selection": {"date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("churn", "Membership at each rebalance",
                       list(churn.columns), churn.values.tolist(),
                       # The note explains why the first row is blank, rather than leaving a
                       # reader to wonder.
                       "entries and exits are relative to the previous rebalance in "
                       "this window, so the first row has none")],
        observations=[
            "%d instruments appear at some point and %d appear at every rebalance; the "
            "gap between them is what a survivorship-free sample has to carry."
            % (ever, always),
            # THE POINT-IN-TIME PRINCIPLE IN ONE SENTENCE: "it qualified then, not because it
            # qualifies now."
            "Membership is reconstructed point in time: a row belongs to a rebalance "
            "because it qualified then, not because it qualifies now.",
            "This is a liquidity-proxy universe reconstructed by this project. It is not "
            "the Nifty 50 and does not reproduce index membership (L-01).",
        ],
        uncertainty={"kind": "none",
                     "reading": "Counts over the reconstructed membership table. "
                                "Nothing here is estimated."},
        provenance={"canonical_called": ["research.data.universe"],
                    "rebalances_considered": len(rebalances),
                    "wrote_nothing": True},
        message="%d rebalances, %d instruments ever a member" % (len(rebalances), ever),
    )


# ------------------------------------------------------------------- STATS-03 ----

def analyse_distributions(date_from: str | None = None, date_to: str | None = None,
                          instruments: list[str] | None = None,
                          block: str = "all", split: str = "all") -> AnalysisResult:
    """STATS-03 live: descriptive statistics of the features on the selected rows.

    Degenerate features are reported alongside, because a feature with one distinct value
    on the slice being looked at cannot inform anything computed from that slice, however
    informative it is elsewhere.
    """
    # PLAIN ENGLISH: "however informative it is elsewhere" is the careful bit. A feature can
    # be genuinely useful across the whole dataset and still be a flat constant inside the
    # three weeks somebody selected. On THAT slice it can separate nothing -- and this says
    # so, without implying the feature is useless in general.
    from research.data import dataset as ds
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for a distribution "
            "to describe anything" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    block_of = {c: b for b, cols in ds.FEATURE_BLOCKS.items() for c in cols}
    # Either everything, or just the one block asked for.
    wanted = (list(ds.ALL_FEATURES) if block in ("", "all")
              else list(ds.FEATURE_BLOCKS.get(block, [])))
    rows = []
    for c in wanted:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({"feature": c, "block": block_of.get(c, "?"),
                     "non_null_fraction": float(s.notna().mean()),
                     "n_distinct": int(s.nunique(dropna=True)),
                     "mean": float(s.mean()), "std": float(s.std()),
                     "min": float(s.min()), "p50": float(s.median()),
                     "max": float(s.max())})
    tbl = pd.DataFrame(rows)
    if tbl.empty:
        # A DIFFERENT refusal from "too few rows" -- this one is "that block does not exist
        # here" -- and it gets its own message and remedy.
        return insufficient(
            "no features of block %r are present in the panel" % block,
            "Choose a different block, or all.")
    degenerate = tbl[(tbl["n_distinct"] <= 1) | (tbl["std"].fillna(0) == 0)]

    metrics = [
        metric("rows", "Rows described", int(len(df)), "int"),
        metric("features", "Features described", int(len(tbl)), "int",
               "numeric features present on these rows"),
        metric("degenerate", "Degenerate here", int(len(degenerate)), "int",
               # "on this slice" -- the qualification is in the note itself.
               "one distinct value or zero variance on this slice"),
        metric("mean_fill", "Mean fill",
               float(tbl["non_null_fraction"].mean()), "pct",
               "average share of rows carrying a value"),
        metric("thinnest", "Thinnest feature fill",
               # The WORST fill as well as the average -- an average of 95% can still hide a
               # feature that is empty.
               float(tbl["non_null_fraction"].min()), "pct"),
    ]
    observations = [
        "Described %d features over the %d rows you selected." % (len(tbl), len(df)),
    ]
    if len(degenerate):
        observations.append(
            # NAMES THE FIRST FIVE, so it is actionable rather than merely a count.
            "%d feature(s) are constant on this slice and cannot separate anything "
            "computed from it: %s."
            % (len(degenerate), ", ".join(degenerate["feature"].head(5))))
    else:
        observations.append("Every described feature varies on this slice.")

    # Only the 40 widest-spread features are sent -- but the true total goes with them.
    top = tbl.sort_values("std", ascending=False).head(40)
    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/market_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, block=block, split=split),
        metrics=metrics,
        series=[series("features", "Feature summary on this slice (widest first)",
                       list(top.columns), top.values.tolist(),
                       "ordered by standard deviation; at most 40 rows shown",
                       # `total_rows` is what makes the table declare itself truncated.
                       total_rows=int(len(tbl)))],
        observations=observations,
        uncertainty={"kind": "none",
                     # A precise distinction: these describe THESE ROWS. They are not
                     # estimates of some wider population, so they carry no sampling error.
                     "reading": "Sample moments of the selected rows. They describe "
                                "this slice and are not estimates of a population."},
        provenance={"canonical_called": ["research.data.dataset:FEATURE_BLOCKS",
                                         "research.data.dataset:ALL_FEATURES"],
                    "features_considered": int(len(tbl)), "wrote_nothing": True},
        message="%d features described over %d rows" % (len(tbl), len(df)),
    )


# ------------------------------------------------------------------- STATS-04 ----

def analyse_microstructure(date_from: str | None = None, date_to: str | None = None,
                           instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-04 live: the market and microstructure-proxy blocks on the selected rows.

    The register of quantities recorded NOT MEASURED travels with the numbers. A proxy
    computed from daily bars is a proxy whether or not the reader remembers that, and the
    list of what daily bars cannot see is the boundary of everything below.
    """
    # PLAIN ENGLISH: "whether or not the reader remembers that" is the whole design
    # philosophy of this project in nine words. The caveat is not stated once at the top and
    # then relied upon -- it is SENT WITH THE NUMBERS, every time, so it cannot be scrolled
    # past and forgotten.
    from research.market import features as mf
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed to describe the "
            "market blocks" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    rows = []
    for name, cols in (("market", mf.MARKET_FEATURES),
                       ("microstructure_proxy", mf.MICROSTRUCTURE_PROXIES)):
        for c in cols:
            if c not in df.columns:
                # Absent features listed with present=False rather than dropped, so the
                # declared set and the actual set can be compared.
                rows.append({"group": name, "feature": c, "present": False,
                             "non_null_fraction": 0.0, "mean": None, "std": None})
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            rows.append({"group": name, "feature": c, "present": True,
                         "non_null_fraction": float(s.notna().mean()),
                         "mean": float(s.mean()), "std": float(s.std())})
    tbl = pd.DataFrame(rows)
    present = tbl[tbl["present"]]

    metrics = [
        metric("rows", "Rows described", int(len(df)), "int"),
        metric("market_features", "Market features",
               int((tbl["group"] == "market").sum()), "int"),
        metric("proxy_features", "Microstructure proxies",
               int((tbl["group"] == "microstructure_proxy").sum()), "int"),
        metric("mean_fill", "Mean fill on this slice",
               float(present["non_null_fraction"].mean()) if len(present) else 0.0,
               "pct"),
        metric("not_measured", "Quantities recorded NOT MEASURED",
               len(mf.MICROSTRUCTURE_NOT_MEASURED), "int",
               # A METRIC WHOSE VALUE IS A COUNT OF WHAT CANNOT BE MEASURED. Given the same
               # visual weight as every other number on the panel.
               "order-book quantities daily bars cannot express"),
    ]
    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/market_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments),
        metrics=metrics,
        series=[
            series("coverage", "Market and proxy features on this slice",
                   list(tbl.columns), tbl.values.tolist(),
                   # Two different questions distinguished in one note: does the column
                   # EXIST, and how full is it on these rows.
                   "present is whether the column exists at all; fill is over the "
                   "selected rows"),
            series("not_measured", "Recorded NOT MEASURED", ["quantity"],
                   [[q] for q in mf.MICROSTRUCTURE_NOT_MEASURED],
                   # THE SHARPEST NOTE IN THE FILE: "these are not missing values; they are
                   # quantities this data source cannot express at all."
                   # A missing value might be filled in tomorrow. These never will be, from
                   # this data, at any price.
                   "these are not missing values; they are quantities this data source "
                   "cannot express at all"),
        ],
        observations=[
            "Every quantity above is derived from daily bars. Daily-bar proxies are not "
            "order-book microstructure, and the register beside them lists what is out "
            "of reach rather than merely absent (L-02).",
            "Fill is measured on the %d rows you selected." % len(df),
        ],
        uncertainty={"kind": "none",
                     "reading": "Coverage and sample moments of the selected rows."},
        provenance={"canonical_called": ["research.market.features:MARKET_FEATURES",
                                         "research.market.features:MICROSTRUCTURE_PROXIES",
                                         "research.market.features:"
                                         "MICROSTRUCTURE_NOT_MEASURED"],
                    "wrote_nothing": True},
        message="%d market and proxy features over %d rows" % (len(tbl), len(df)),
    )


# ------------------------------------------------------------------- STATS-05 ----

def analyse_regimes(date_from: str | None = None, date_to: str | None = None,
                    instruments: list[str] | None = None,
                    split: str = "all") -> AnalysisResult:
    """STATS-05 live: how the selected rows distribute across regimes."""
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if "regime_id" not in df.columns:
        # A structural refusal, with the fix: rebuild the dataset with regimes enabled.
        return insufficient("the panel carries no regime_id column",
                            "Rebuild the dataset with the regime block enabled.")
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for an occupancy "
            "profile" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    occ = df.groupby("regime_id").size().rename("rows").reset_index()
    occ["share"] = occ["rows"] / occ["rows"].sum()
    if "is_episode" in df.columns:
        occ = occ.merge(df.groupby("regime_id")["is_episode"].mean()
                        .rename("episode_rate").reset_index(), on="regime_id")
    occ = occ.sort_values("rows", ascending=False)
    largest = occ.iloc[0]

    metrics = [
        metric("rows", "Rows in this slice", int(len(df)), "int"),
        metric("regimes", "Regimes present", int(len(occ)), "int"),
        metric("largest_share", "Largest regime share", float(occ["share"].max()),
               "pct", "share of the slice held by regime %s" % largest["regime_id"]),
        metric("smallest_rows", "Smallest regime, rows", int(occ["rows"].min()), "int",
               # BOTH ENDS SHOWN, and the note explains why the small end matters: anything
               # conditioned on a thin regime rests on almost nothing.
               "a regime with few rows supports little on its own"),
    ]
    observations = [
        "Regime %s holds %.1f%% of the %d rows you selected."
        % (largest["regime_id"], 100 * float(largest["share"]), len(df)),
    ]
    if "episode_rate" in occ.columns:
        hot = occ.sort_values("episode_rate", ascending=False).iloc[0]
        observations.append(
            # THE CRUCIAL REFRAMING. "Episodes cluster in regime 3" sounds like a discovery
            # about markets. It is not -- the project CHOSE where to put them. So the
            # sentence says what the number actually describes: where they were placed.
            "The highest episode rate on this slice is %.1f%% in regime %s. Episodes are "
            "injected by this project, so this describes where they were placed (L-04)."
            % (100 * float(hot["episode_rate"]), hot["regime_id"]))
    thin = occ[occ["rows"] < 30]
    if len(thin):
        observations.append(
            "%d regime(s) hold fewer than 30 rows here; anything conditioned on them "
            "rests on very little." % len(thin))

    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/market_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, split=split),
        metrics=metrics,
        series=[series("occupancy", "Regime occupancy on this slice",
                       list(occ.columns), occ.values.tolist(),
                       "share sums to one over the selected rows")],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "Counts and rates over the selected rows."},
        provenance={"canonical_called": ["research.regime"],
                    "wrote_nothing": True},
        message="%d regimes over %d rows" % (len(occ), len(df)),
    )


# ------------------------------------------------------------------- STATS-06 ----

def analyse_dependence(date_from: str | None = None, date_to: str | None = None,
                       instruments: list[str] | None = None,
                       top_n: int = 15) -> AnalysisResult:
    """STATS-06 live: co-movement across the selected instruments, and the propagation
    feature block that summarises it.

    Everything below is contemporaneous association. Nothing here identifies a direction,
    a mechanism or an origin, and the wording is chosen so that it cannot be read as if it
    did (L-07).
    """
    # PLAIN ENGLISH: CONTEMPORANEOUS means "at the same time". Two share prices moving
    # together tells you nothing about which moved first, why, or whether either caused the
    # other. They may both be reacting to something else entirely.
    # "the wording is chosen so that it cannot be read as if it did" -- the language of the
    # output is part of the method here, not decoration on top of it.
    from research.propagation import graph as pg
    from scripts.stages import live

    # Association is measured on the cash panel rather than on the modelling panel:
    # returns are the quantity a reader means by "these moved together", and the
    # modelling panel holds only the scored sessions, which are far too sparse per
    # instrument to correlate.
    # PLAIN ENGLISH: two reasons, both good. RETURNS are what anybody actually means by
    # "these moved together". And the modelling panel only holds the days that were scored,
    # which is far too patchy per company to correlate meaningfully.
    cash = live.slice_frame(live.cash_panel(), date_from, date_to, instruments)
    if len(cash) < 60:
        # A HIGHER BAR than the usual 30 -- correlation over a handful of days is noise.
        return insufficient(
            "the selected slice holds %d sessions, below the 60 needed to measure "
            "co-movement" % len(cash),
            "Widen the date range, or select more instruments.")
    panel = live.slice_frame(live.panel(), date_from, date_to, instruments)

    truncated = 0
    present = [c for c in pg.PROPAGATION_FEATURES if c in panel.columns]
    feat = pd.DataFrame({
        "feature": present,
        "non_null_fraction": [float(panel[c].notna().mean()) for c in present],
        "mean": [float(pd.to_numeric(panel[c], errors="coerce").mean())
                 for c in present],
        "std": [float(pd.to_numeric(panel[c], errors="coerce").std())
                for c in present],
    }) if len(panel) else pd.DataFrame(
        # An empty table WITH THE RIGHT COLUMNS, so downstream code behaves identically
        # whether or not there was data.
        columns=["feature", "non_null_fraction", "mean", "std"])

    pairs = pd.DataFrame(columns=["instrument_a", "instrument_b", "correlation",
                                  "sessions"])
    if len(cash):
        # `pivot_table` reshapes long data (one row per company-day) into wide (one column
        # per company, one row per day) -- the shape correlation needs.
        wide = (cash.pivot_table(index="date", columns="symbol", values="close")
                .sort_index())
        # Correlate RETURNS, not prices. Two rising share prices correlate almost perfectly
        # whatever they are doing; their day-to-day moves are the real question.
        rets = wide.pct_change().dropna(how="all")
        counts = rets.notna().sum()
        # At least 30 observed sessions before a company is eligible at all.
        usable = counts[counts >= 30].index.tolist()
        # Every pair among n instruments is n(n-1)/2 correlations, so an unfiltered
        # request over the whole universe is tens of thousands of them and minutes of
        # waiting. The most-observed instruments are kept and the truncation is reported
        # in the observations below, because a silently shortened table reads as a
        # complete one.
        # PLAIN ENGLISH: THE LAST CLAUSE IS THE PRINCIPLE. Cutting the list is fine.
        # Cutting it WITHOUT SAYING SO is not -- because a shortened table looks exactly like
        # a complete one, and the reader would conclude the missing pairs do not exist.
        truncated = 0
        if len(usable) > MAX_CORRELATED:
            truncated = len(usable) - MAX_CORRELATED
            # Keeps the companies with the MOST observed sessions -- the best-measured ones,
            # a defensible criterion rather than alphabetical order.
            usable = counts[usable].sort_values(ascending=False).head(
                MAX_CORRELATED).index.tolist()
        if len(usable) >= 2:
            corr = rets[usable].corr(min_periods=30)
            rows = []
            # `usable[i + 1:]` gives each pair once rather than twice.
            for i, a in enumerate(usable):
                for b in usable[i + 1:]:
                    value = corr.loc[a, b]
                    if pd.notna(value):
                        rows.append({"instrument_a": a, "instrument_b": b,
                                     "correlation": float(value),
                                     # HOW MANY SESSIONS THIS PARTICULAR PAIR SHARED. A
                                     # correlation over 30 days and one over 3000 are very
                                     # different claims, and the count travels with each.
                                     "sessions": int(min(counts[a], counts[b]))})
            if rows:
                # Sorted by ABSOLUTE correlation, so a strong negative relationship ranks as
                # highly as a strong positive one -- both are equally interesting.
                pairs = (pd.DataFrame(rows)
                         .reindex(pd.DataFrame(rows)["correlation"].abs()
                                  .sort_values(ascending=False).index))

    metrics = [
        metric("sessions", "Sessions in this slice", int(len(cash)), "int",
               "instrument-days of price history the correlations were measured on"),
        metric("propagation_features", "Propagation features present",
               len(present), "int",
               # PRESENT OUT OF DECLARED, so a shortfall is visible.
               "of %d declared" % len(pg.PROPAGATION_FEATURES)),
        metric("mean_fill", "Mean fill",
               float(feat["non_null_fraction"].mean()) if len(feat) else 0.0, "pct"),
        metric("pairs", "Instrument pairs measured", int(len(pairs)), "int",
               "pairs with at least 30 overlapping sessions"),
        metric("median_abs_corr", "Median absolute correlation",
               float(pairs["correlation"].abs().median()) if len(pairs) else float("nan"),
               "float4", "contemporaneous return correlation across those pairs"),
    ]
    observations = [
        "Correlations were computed on the sessions you selected, over %d instrument "
        "pairs with enough overlap to measure." % len(pairs),
        # THE ANTI-CAUSAL SENTENCE, stated plainly: these do not identify which moved first,
        # and nothing here supports a claim about one driving another.
        "These are contemporaneous associations between return series. They do not "
        "identify which instrument moved first, and nothing here supports a statement "
        "about one instrument driving another (L-07).",
    ]
    if truncated:
        observations.append(
            # THE TRUNCATION DECLARED: how many were dropped, why, which were kept, and how
            # to get a specific one included. A complete account of what was left out.
            "%d instrument(s) were left out: every pair among %d instruments is more "
            "correlations than this endpoint will compute, so the %d with the most "
            "observed sessions were kept. Name the instruments you want to be sure."
            % (truncated, truncated + MAX_CORRELATED, MAX_CORRELATED))
    if len(pairs):
        top = pairs.iloc[0]
        observations.append(
            # Even the headline finding carries its session count.
            "The strongest association on this slice is %s and %s at %.3f over %d "
            "sessions." % (top["instrument_a"], top["instrument_b"],
                           float(top["correlation"]), int(top["sessions"])))

    return AnalysisResult(
        dataset=live.describe_slice(cash, "data/panel/cash_panel.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, top_n=top_n),
        metrics=metrics,
        series=[
            series("pairs", "Strongest associations on this slice",
                   ["instrument_a", "instrument_b", "correlation", "sessions"],
                   pairs.head(max(1, int(top_n))).values.tolist(),
                   # "association only" repeated even in the table's own caption.
                   "ordered by absolute correlation; association only",
                   total_rows=int(len(pairs))),
            series("propagation_block", "Propagation feature block on this slice",
                   list(feat.columns), feat.values.tolist(),
                   "declared propagation features and their fill on the %d scored "
                   "rows in this window" % len(panel)),
        ],
        observations=observations,
        uncertainty={
            "kind": "sample",
            "n_pairs": int(len(pairs)),
            "reading": (
                # AND THE REASON THE PER-PAIR COUNT EXISTS, stated outright: pairs with few
                # sessions swing wildly from one window to the next. One number for the whole
                # table would hide which correlations are solid and which are noise.
                "Each correlation is a sample statistic over the overlapping "
                "sessions shown beside it. Pairs with few sessions move a great "
                "deal from one window to the next, which is why the session "
                "count is reported per pair rather than once for the table."),
        },
        provenance={"canonical_called": ["research.propagation.graph:"
                                         "PROPAGATION_FEATURES"],
                    "instrument_pairs": int(len(pairs)), "wrote_nothing": True},
        message="%d instrument pairs measured over %d sessions"
                % (len(pairs), len(cash)),
    )


# ------------------------------------------------------------------- STATS-07 ----

def analyse_tail_risk(date_from: str | None = None, date_to: str | None = None,
                      instruments: list[str] | None = None,
                      alpha: float = 0.05) -> AnalysisResult:
    """STATS-07 live: tail statistics of the realised next-session return on the slice.

    The same construction the regenerating adapter uses — next-session percentage change
    in close, per instrument — so the live figure and the artifact figure are the same
    quantity measured over different rows. The corporate-action diagnostic travels with
    it, because an unadjusted 10:1 split reads as a -90% session and one such row is
    enough to dominate a drawdown.
    """
    # PLAIN ENGLISH: "the same quantity measured over different rows" is the guarantee. The
    # website's number and the paper's number are not merely similar -- they are the same
    # calculation, differing only in which rows went into it.
    from research.risk import gate
    from scripts.stages import live

    cash = live.slice_frame(live.cash_panel(), date_from, date_to, instruments)
    if len(cash) < 60:
        return insufficient(
            "the selected slice holds %d sessions; tail statistics need at least 60"
            % len(cash),
            "Widen the date range, or select more instruments.")

    fwd = cash.sort_values(["symbol", "date"]).copy()
    fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
    net = fwd["fwd_ret"].to_numpy(float)
    net = net[np.isfinite(net)]
    if len(net) < 20:
        # A SECOND, DIFFERENT refusal: enough sessions overall, but not enough CONSECUTIVE
        # ones to produce next-day returns. The remedy addresses that specific problem.
        return insufficient(
            "only %d rows carry a next-session return" % len(net),
            "Widen the date range so each instrument has consecutive sessions.")

    stats = gate.tail_metrics(net, alpha=float(alpha))
    suspects = fwd.loc[fwd["fwd_ret"].abs() > 0.5, ["symbol", "date", "fwd_ret"]]
    clean = net[np.abs(net) <= 0.5]

    metrics = [
        metric("n", "Returns measured", int(stats["n"]), "int",
               "instrument-sessions with a next-session return in this slice"),
        # VaR: the loss level you would only exceed 5% of the time.
        metric("var", "VaR at %.0f%%" % (100 * alpha), stats["var"], "pct",
               "the quantile of the realised return distribution"),
        # CVaR: given that you are in that worst 5%, the AVERAGE loss. The more honest
        # measure, because VaR says nothing about how bad the bad days get.
        metric("cvar", "CVaR at %.0f%%" % (100 * alpha), stats["cvar"], "pct",
               "mean return in the tail beyond that quantile"),
        metric("vol_annual", "Annualised volatility", stats["vol_annual"], "pct"),
        metric("worst_day", "Worst session", stats["worst_day"], "pct",
               # THE CONTAMINATION WARNING ATTACHED TO THE METRIC ITSELF.
               "unadjusted for corporate actions; see the diagnostic below"),
        metric("max_drawdown", "Maximum drawdown", stats["max_drawdown"], "pct",
               "of the equal-weight compounded series over these rows"),
    ]
    observations = [
        "Measured over %d realised next-session returns in the slice you selected."
        % int(stats["n"]),
        # THE NON-ADVICE SENTENCE. This is the distribution the gate READS. It is not the
        # result of applying one, and no position size is produced anywhere.
        "This is the distribution the exposure gate reads. It is not the result of "
        "applying one, and no position size, allocation or exposure is produced here.",
    ]
    if len(suspects):
        observations.append(
            # THE SPLIT WARNING, IN PLAIN WORDS, with the clean figure right beside it.
            "%d session(s) move more than 50%%, which is almost certainly a split or "
            "bonus rather than a return: prices here are unadjusted. Worst session "
            "excluding them is %.2f%% (KI-06)."
            % (len(suspects),
               100 * float(clean.min()) if len(clean) else float("nan")))
    else:
        # AND WHEN THERE ARE NONE, IT SAYS SO. Silence would leave the reader unsure whether
        # the check ran. "not VISIBLY contaminated" is also carefully hedged -- a smaller
        # split could still be in there.
        observations.append(
            "No session in this slice moves more than 50%, so the drawdown figure is "
            "not visibly contaminated by an unadjusted corporate action.")

    table = pd.DataFrame([{"statistic": k, "value": v} for k, v in stats.items()])
    return AnalysisResult(
        dataset=live.describe_slice(cash, "data/panel/cash_panel.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, alpha=alpha),
        metrics=metrics,
        series=[
            series("tail", "Tail statistics on this slice",
                   list(table.columns), table.values.tolist(),
                   "computed by research.risk.gate.tail_metrics"),
            series("suspects", "Sessions above the corporate-action threshold",
                   ["symbol", "date", "fwd_ret"],
                   [[str(r.symbol), str(pd.Timestamp(r.date).date()), float(r.fwd_ret)]
                    for r in suspects.head(25).itertuples(index=False)],
                   # "reported, not removed" -- three words containing the whole policy.
                   "absolute move greater than 50%; reported, not removed",
                   total_rows=int(len(suspects))),
        ],
        observations=observations,
        uncertainty={
            "kind": "sample",
            "n": int(stats["n"]),
            "reading": (
                # THE MOST SELF-CRITICAL UNCERTAINTY NOTE IN THE PROJECT: "Tail statistics
                # are the least stable thing in this project."
                # And it explains WHY with arithmetic: CVaR at 5% is an average over the
                # worst twentieth of the data. Out of 1000 rows that is 50 numbers. A
                # different window can move it a long way.
                # Ending with the instruction: read it as a description of these rows, not
                # as a forecast.
                "Tail statistics are the least stable thing in this project: "
                "CVaR at 5%% is an average over roughly %d observations here, "
                "and a different window can move it substantially. Read it as a "
                "description of these rows, not as a forecast."
                % max(1, int(0.05 * stats["n"]))),
        },
        provenance={"canonical_called": ["research.risk.gate:tail_metrics"],
                    "alpha": float(alpha), "wrote_nothing": True},
        message="tail statistics over %d realised returns" % int(stats["n"]),
    )


# ------------------------------------------------------------------- STATS-08 ----

def analyse_episodes(date_from: str | None = None, date_to: str | None = None,
                     instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-08 live: the injected episodes overlapping the selected window."""
    from scripts.stages import live

    labels = pd.read_parquet(paths.PANEL / "episode_labels.parquet")
    # Synthetic episode ground truth, not market history: exempt by name in
    # live.NON_BITEMPORAL_FRAMES["episode_labels"].
    # PLAIN ENGLISH: the point-in-time check is switched off HERE ONLY, and the reason is
    # named in a registered list of exemptions rather than decided in passing. These labels
    # were constructed, not published, so there is no publication moment to respect.
    sel = live.slice_frame(labels, date_from, date_to, instruments,
                           require_point_in_time=False) \
        if "date" in labels.columns else labels
    if len(sel) < live.MIN_ROWS:
        return insufficient(
            "the selected window holds %d episode label rows, below the %d needed to "
            "summarise them" % (len(sel), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    n_episodes = int(sel["episode_id"].nunique()) if "episode_id" in sel.columns else 0
    rows = []
    for col in ("intensity", "duration", "n_sessions", "state"):
        if col not in sel.columns:
            continue
        s = sel[col]
        # Text columns get COUNTS; numeric columns get MEANS. Averaging a category name
        # would be meaningless, so the code checks the type rather than assuming.
        if s.dtype == object:
            counts = s.value_counts()
            for k, v in counts.items():
                rows.append({"quantity": "%s=%s" % (col, k), "value": int(v),
                             "kind": "count"})
        else:
            s = pd.to_numeric(s, errors="coerce")
            rows.append({"quantity": "%s mean" % col, "value": float(s.mean()),
                         "kind": "mean"})
            rows.append({"quantity": "%s max" % col, "value": float(s.max()),
                         "kind": "max"})
    table = pd.DataFrame(rows)

    metrics = [
        metric("label_rows", "Label rows in this window", int(len(sel)), "int"),
        metric("episodes", "Episodes", n_episodes, "int",
               "distinct injected episodes overlapping the window"),
        metric("instruments", "Instruments affected",
               int(sel["symbol"].nunique()) if "symbol" in sel.columns else 0, "int"),
    ]
    if "intensity" in sel.columns:
        metrics.append(metric("intensity", "Mean intensity",
                              float(pd.to_numeric(sel["intensity"],
                                                  errors="coerce").mean()), "float4",
                              # "a construction parameter" -- the note refuses to let this be
                              # read as an observation about markets. It is a dial this
                              # project set.
                              "the injected magnitude, a construction parameter"))

    return AnalysisResult(
        dataset=live.describe_slice(sel, "data/panel/episode_labels.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments),
        metrics=metrics,
        series=[series("episode_summary", "Episode label summary in this window",
                       list(table.columns), table.values.tolist(),
                       "counts for categorical columns, moments for numeric ones")]
        if len(table) else [],
        observations=[
            "%d episodes touch the window you selected, across %d instruments."
            % (n_episodes,
               int(sel["symbol"].nunique()) if "symbol" in sel.columns else 0),
            # THE SENTENCE THAT MUST NEVER BE OMITTED: these were injected by this project,
            # and no count here describes real-world manipulation.
            "These episodes were injected into real price series by this project. They "
            "are a construction with known parameters, and no count here describes "
            "real-world market manipulation (L-04).",
        ],
        uncertainty={"kind": "none",
                     # A LOVELY DOUBLE-EDGED SENTENCE: the labels are exact BECAUSE they were
                     # constructed -- which is what makes them usable as ground truth AND
                     # what bounds everything they can support. The same fact is the strength
                     # and the limit.
                     "reading": "Counts over the injected label table. The labels are "
                                "exact by construction, which is what makes them "
                                "usable as ground truth and also what bounds them."},
        provenance={"canonical_called": ["research.detection.episodes"],
                    "episodes": n_episodes, "wrote_nothing": True},
        message="%d episodes over %d label rows" % (n_episodes, len(sel)),
    )


# ------------------------------------------------------------------- STATS-09 ----

def analyse_leakage() -> AnalysisResult:
    """STATS-09 live: run the L1-L6 leakage suite now and report what it found.

    No parameters, deliberately. The suite is the canonical definition of the property
    and there is nothing about it a caller should be able to vary: a leakage check whose
    scope the requester can narrow is not a leakage check. The command is a fixed argument
    list with no value from the request in it.
    """
    # PLAIN ENGLISH: THE ONE FUNCTION IN THIS FILE THAT TAKES NO OPTIONS, and the reason is
    # both a principle and a security control.
    # THE PRINCIPLE: "a leakage check whose scope the requester can narrow is not a leakage
    # check." If you can ask it to skip the parts that fail, it is theatre.
    # THE SECURITY CONTROL: the last sentence. The command is a FIXED list with nothing from
    # the request in it -- so there is no way to smuggle an argument into a program this
    # server runs. Not guarded against; simply impossible.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/leakage", "-q", "--no-header",
         "--tb=no"],
        cwd=str(paths.REPO_ROOT), capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else "pytest produced no summary"
    passed = _count(tail, "passed")
    failed = _count(tail, "failed")

    metrics = [
        metric("passed", "Checks passed", passed, "int"),
        metric("failed", "Checks failed", failed, "int",
               "a single failure invalidates every downstream result"),
        metric("returncode", "Suite exit code", int(proc.returncode), "int",
               "zero is the only acceptable value"),
    ]
    ok = proc.returncode == 0
    observations = [
        # "this is not a stored report" -- the suite genuinely ran during this request.
        "The suite ran during this request; this is not a stored report.",
        ("All %d checks pass, so no test in the suite found information from after a "
         "decision time reaching a feature computed before it." % passed) if ok else
        ("%d check(s) failed. Every result computed downstream of the affected feature "
         "is invalid until the failure is resolved." % failed),
        # THE MOST IMPORTANT LINE, AND IT APPEARS EVEN WHEN EVERYTHING PASSES:
        # passing means the suite FOUND NOTHING. That is not the same as proving there is
        # nothing to find. The tests can only catch the failures somebody thought to write a
        # test for.
        "Passing means the suite found nothing, which is not the same as proving that "
        "nothing exists to find (L-11).",
    ]
    return AnalysisResult(
        ok=True,
        dataset={"source": "tests/leakage", "rows": passed + failed,
                 "selection": {}},
        metrics=metrics,
        series=[series("output", "Suite output", ["line"],
                       # The raw pytest output, so a reader can see it themselves rather than
                       # relying on the summary.
                       [[ln] for ln in lines[-12:]],
                       "the last lines pytest printed")],
        observations=observations,
        uncertainty={"kind": "none",
                     # A test result is a pass or a fail, not an estimate. What it BOUNDS is
                     # which failure modes were looked for -- a precise statement of what a
                     # green suite does and does not tell you.
                     "reading": "A test suite result is a pass or a fail, not an "
                                "estimate. What it bounds is which failure modes were "
                                "looked for."},
        provenance={"canonical_called": ["tests/leakage (L1-L6)"],
                    "returncode": int(proc.returncode), "wrote_nothing": True},
        message=tail,
    )


def _count(summary: str, word: str) -> int:
    # Pull a number out of pytest's summary line, e.g. "14 passed" -> 14.
    import re as _re
    m = _re.search(r"(\d+)\s+%s" % word, summary)
    # No match -> 0, so an unexpected output format cannot crash the response.
    return int(m.group(1)) if m else 0


# ------------------------------------------------------------------- STATS-10 ----

def _scored(arm: str, date_from: str | None, date_to: str | None,
            instruments: list[str] | None):
    """Per-row scores for one arm, filtered to the caller's slice."""
    # THREE DISTINCT REFUSALS, shared by every module that reads scores -- so the same
    # situation always produces the same explanation.
    from scripts.stages import live

    frame = live.per_row(arm)
    if frame is None:
        # 1. THAT ARM WAS NEVER RUN. And the remedy is the literal command.
        return None, ("no per-row scores exist for arm %s" % arm,
                      "Choose an arm that was executed, or run "
                      "`python scripts/run_experiments.py` at a terminal.")
    # Model scores from an executed arm, not market history: exempt by name in
    # live.NON_BITEMPORAL_FRAMES["per_row_scores"].
    sel = live.slice_frame(frame, date_from, date_to, instruments,
                           require_point_in_time=False)
    if len(sel) < live.MIN_ROWS:
        # 2. TOO FEW ROWS.
        return None, ("the selected slice holds %d scored rows, below the %d needed for "
                      "a metric to mean anything" % (len(sel), live.MIN_ROWS),
                      "Widen the date range, or select fewer instruments to exclude.")
    if sel["is_episode"].nunique() < 2:
        # 3. THE SUBTLE ONE, AND THE MOST IMPORTANT. Every row has the same label -- all
        # normal, or all episode. There is nothing to tell apart, so no ranking metric EXISTS
        # on this slice. Not a poor score; an undefined one.
        # Without this check, AUPRC would come back as some meaningless value that looks like
        # a result.
        return None, ("every row in this slice has the same label, so no ranking metric "
                      "is defined on it",
                      "Widen the window so it contains both episode and non-episode "
                      "rows.")
    return sel, None


def _train_threshold() -> tuple[float | None, str]:
    """The threshold selected on the training split, from the experiment bundle."""
    # Returns BOTH the number and the file it came from, so every use of it can name its
    # source.
    bundles = sorted(paths.REPORTS.glob("*FULL*/metrics.json"))
    if not bundles:
        return None, ""
    bundle = json.loads(bundles[0].read_text(encoding="utf-8"))
    return (bundle.get("detection", {}).get("threshold"),
            str(bundles[0].relative_to(paths.REPO_ROOT).as_posix()))


def analyse_validation(arm: str = "FULL", threshold: float | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-10 live: the confusion matrix and its metrics at a threshold you choose.

    The default is the threshold selected on the training split, read from the experiment
    bundle. A caller may override it — that is the point of an interactive panel — and
    when they do, the response says plainly that the threshold was chosen by hand and that
    picking the one that flatters a metric on the evaluation split is not a selection
    procedure (L6). The number is still computed correctly; what changes is what it is
    evidence of.
    """
    # PLAIN ENGLISH: THE FINEST PIECE OF JUDGEMENT IN THE WHOLE FILE, and its last sentence
    # is the key: "The number is still computed correctly; what changes is what it is
    # evidence of."
    #
    # There were three options here.
    #   1. Do not let people move the threshold. Safe, and useless -- moving it is exactly
    #      how you understand the trade-off between missed events and false alarms.
    #   2. Let them move it and say nothing. Then somebody finds the flattering cutoff,
    #      screenshots the result, and it circulates as a finding.
    #   3. Let them move it, AND SAY WHAT THE RESULTING NUMBER IS AND IS NOT.
    #
    # Option 3 is taken. The arithmetic is identical either way. What changes -- and what the
    # response states -- is whether the number is evidence about unseen data or merely a
    # description of this slice at a chosen angle.
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        # `*problem` unpacks the (message, remedy) pair into the two arguments.
        return insufficient(*problem)

    train_thr, source = _train_threshold()
    chosen_by_caller = threshold is not None
    # Three levels of fallback: what the caller asked for, else the train-selected value,
    # else best-F1 -- and the last case is declared in the observations below.
    thr = float(threshold) if chosen_by_caller else (
        float(train_thr) if train_thr is not None else mx.best_f1_threshold(
            sel["is_episode"].to_numpy(int), sel["integrity_risk"].to_numpy(float)))

    y = sel["is_episode"].to_numpy(int)
    p = sel["integrity_risk"].to_numpy(float)
    report = mx.verification_report(y, p, thr)
    m = report["metrics"]
    per_class = pd.DataFrame(report["per_class"])

    metrics = [
        metric("n", "Rows scored", int(m["n"]), "int"),
        metric("threshold", "Threshold applied", thr, "float4",
               # THE NOTE CHANGES WITH WHO CHOSE IT. "chosen by you" versus "selected on the
               # training split, not here" -- the provenance sits on the metric itself.
               "chosen by you" if chosen_by_caller
               else "selected on the training split, not here"),
        metric("balanced_accuracy", "Balanced accuracy", m["balanced_accuracy"],
               # BALANCED accuracy, because plain accuracy is meaningless when one class is
               # rare: predict "normal" every time and you score 97%.
               "float4", "accuracy corrected for the class imbalance"),
        metric("mcc", "Matthews correlation", m["mcc"], "float4",
               # MCC degrades when ANY cell of the matrix does -- it cannot be gamed by doing
               # well on three quarters of the table.
               "a single number that degrades when any cell of the matrix does"),
        # ALL FOUR CELLS, individually. So the reader sees which mistakes it makes.
        metric("tp", "True positives", m["tp"], "int"),
        metric("fp", "False positives", m["fp"], "int"),
        metric("fn", "False negatives", m["fn"], "int"),
        metric("tn", "True negatives", m["tn"], "int"),
    ]
    observations = [
        "Computed on the %d scored rows in your slice of arm %s." % (int(m["n"]), arm),
    ]
    if chosen_by_caller:
        observations.append(
            # THE HONEST WARNING, addressed directly to the person who moved the slider --
            # and it ends by TELLING THEM the training-selected value, so they can compare
            # rather than be left guessing.
            "You set this threshold. Choosing a threshold by looking at the evaluation "
            "metrics it produces is not a selection procedure, and a number obtained "
            "that way is a description of this slice rather than evidence about unseen "
            "data (L6). The training-selected threshold is %s."
            % ("%.4f" % train_thr if train_thr is not None else "unavailable"))
    else:
        observations.append(
            # AND WHEN THE DEFAULT WAS USED: which file it came from, and why recomputing it
            # here would flatter everything.
            "The threshold came from %s, where it was selected on the training split. "
            "Recomputing it here would flatter every metric above."
            % (source or "the best-F1 rule, because no experiment bundle was found"))
    observations.append(
        # The synthetic-label caveat, present on every detection result.
        "The episodes these labels describe are injected by this project, so this "
        "measures detection of a known construction (L-04).")

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "instruments": int(sel["symbol"].nunique()),
                 "selection": {"arm": arm, "threshold": thr,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("per_class", "Per-class report at this threshold",
                       list(per_class.columns), per_class.values.tolist(),
                       "precision, recall and support for each class")],
        observations=observations,
        uncertainty={
            "kind": "threshold",
            "threshold": thr,
            "threshold_selected_by": "caller" if chosen_by_caller else "training split",
            "reading": (
                # AND THE FINEST SENTENCE OF ALL, which turns the interactive control into
                # the lesson: "Change it and watch which cells trade against each other;
                # that trade is the actual result."
                # The single number at any one threshold is not the finding. The TRADE-OFF
                # -- catch more events and accept more false alarms -- is the finding, and
                # you can only see it by moving the control.
                "Every count above moves with the threshold, and the threshold "
                "is a choice rather than a property of the model. Change it and "
                "watch which cells trade against each other; that trade is the "
                "actual result."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:"
                                         "verification_report",
                                         "research.evaluation.metrics:per_class_report"],
                    "arm": arm, "threshold_source": source or "best-F1 fallback",
                    # PERMANENTLY RECORDED: did the caller pick this threshold themselves?
                    "threshold_chosen_by_caller": chosen_by_caller,
                    "metrics_version": mx.METRICS_VERSION,
                    "wrote_nothing": True},
        message="%d rows at threshold %.4f (balanced accuracy %.4f)"
                % (int(m["n"]), thr, m["balanced_accuracy"]),
    )


# ------------------------------------------------------------------- STATS-11 ----

def analyse_calibration(arm: str = "FULL", bins: int = 10,
                        date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-11 live: the reliability curve at a binning you choose.

    The bin count is exposed because expected calibration error depends on it, and a
    single ECE quoted without its binning is a number whose scale nobody can check. Move
    the slider and the figure moves; that sensitivity is the finding.
    """
    # PLAIN ENGLISH: the same idea as the threshold slider, applied to bins.
    # ECE is computed by grouping predictions into buckets and comparing each bucket's
    # average prediction with what actually happened. HOW MANY BUCKETS is a choice -- and the
    # answer changes with it. So an ECE quoted alone is uncheckable.
    # "that sensitivity is the finding": if the number swings wildly as you move the slider,
    # you have learned that no single ECE value should be trusted. The instability IS the
    # result.
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        return insufficient(*problem)

    y = sel["is_episode"].to_numpy(int)
    p = sel["integrity_risk"].to_numpy(float)
    # Clamped between 2 and 50 -- 1 bin measures nothing, and 500 bins would put one row in
    # each and produce pure noise.
    n_bins = max(2, min(int(bins), 50))
    rel = mx.reliability_curve(y, p, n_bins=n_bins)
    ece = mx.expected_calibration_error(y, p, n_bins=n_bins)
    detection = mx.detection_metrics(y, p)

    metrics = [
        metric("n", "Rows scored", int(len(sel)), "int"),
        metric("bins", "Bins", n_bins, "int",
               # THE NUMBER AND ITS BINNING, INSEPARABLE: "the ECE beside this is defined
               # only with respect to this binning."
               "the ECE beside this is defined only with respect to this binning"),
        metric("ece", "Expected calibration error", ece, "float4",
               "mean gap between predicted score and observed rate, weighted by bin"),
        metric("auprc", "AUPRC", detection["auprc"], "float4",
               # AN IMPORTANT DISTINCTION IN FIVE WORDS: "which calibration does not affect".
               # Ranking quality and calibration are separate properties. A model can order
               # things perfectly and still be badly overconfident about every one of them.
               "ranking quality, which calibration does not affect"),
        metric("positive_rate", "Episode rate in this slice",
               detection["positive_rate"], "pct"),
    ]
    # The bin where prediction and reality diverge most. The `.get` with a computed fallback
    # copes with a curve that does not carry a ready-made gap column.
    worst = rel.iloc[(rel.get("gap", (rel.iloc[:, 1] - rel.iloc[:, 2]).abs())
                      .abs()).idxmax()] if len(rel) else None

    observations = [
        "Reliability computed over %d scored rows at %d bins." % (len(sel), n_bins),
        # THE PLAINEST STATEMENT OF L-10 ANYWHERE IN THE PROJECT: "a score of 0.7 does not
        # mean seven episodes in ten." Anybody would assume it does.
        "The integrity-risk score is a ranking, not a calibrated probability: a score of "
        "0.7 does not mean seven episodes in ten (L-10). The curve below shows how far "
        "from that the score actually is.",
    ]
    if worst is not None:
        observations.append(
            # Names the WORST bin, not the average gap.
            "The widest gap between score and observed rate on this slice is in bin %s."
            % str(worst.iloc[0]))

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "selection": {"arm": arm, "bins": n_bins,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("reliability", "Reliability curve at %d bins" % n_bins,
                       list(rel.columns), rel.values.tolist(),
                       "one row per bin: mean predicted score against observed rate")],
        observations=observations,
        uncertainty={
            "kind": "binning",
            "bins": n_bins,
            "reading": (
                # BOTH FAILURE MODES EXPLAINED, and the admission that the control on the
                # page can reach either one.
                # TOO FEW BINS: real miscalibration hides inside a wide bucket, where good
                # and bad predictions average each other out.
                # TOO MANY BINS: each holds three rows and the curve is noise.
                # "Both failure modes are reachable from the control above" -- so the bin
                # count is reported WITH the number, every time.
                "Expected calibration error is a function of the binning as much "
                "as of the model. Fewer bins hide miscalibration inside them; "
                "more bins put very few rows in each and the curve becomes "
                "noise. Both failure modes are reachable from the control above, "
                "which is why the bin count is reported with the number."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:reliability_curve",
                                         "research.evaluation.metrics:"
                                         "expected_calibration_error"],
                    "arm": arm, "bins": n_bins, "wrote_nothing": True},
        message="ECE %.4f at %d bins over %d rows" % (ece, n_bins, len(sel)),
    )


# ------------------------------------------------------------------- STATS-12 ----

def analyse_errors(arm: str = "FULL", threshold: float | None = None,
                   segment_by: str = "error_class",
                   date_from: str | None = None, date_to: str | None = None,
                   instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-12 live: where the scoring goes wrong on the selected rows, and how.

    The taxonomy separates data problems from model problems, in that order: a row with
    no evidence under it is not a model failure, and counting it as one would send the
    reader looking in the wrong place.
    """
    # PLAIN ENGLISH: "in that order" matters. Ask FIRST whether the evidence was there.
    # If it was not, the model was not wrong -- it was blind, and the fix is a data fix.
    # Count that as a model failure and somebody spends a week retuning a model that was
    # working perfectly on nothing.
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        return insufficient(*problem)

    train_thr, source = _train_threshold()
    chosen_by_caller = threshold is not None
    thr = float(threshold) if chosen_by_caller else (
        float(train_thr) if train_thr is not None
        else mx.best_f1_threshold(sel["is_episode"].to_numpy(int),
                                  sel["integrity_risk"].to_numpy(float)))

    tax = mx.classify_errors(sel, thr)
    counts = (tax["error_class"].value_counts()
              .rename_axis("error_class").reset_index(name="rows"))
    counts["share"] = counts["rows"] / counts["rows"].sum()

    # Optionally cross-tabulate the failure modes by something else -- by company, by regime
    # -- to see whether the mistakes concentrate somewhere.
    if segment_by in tax.columns and segment_by != "error_class":
        cross = (tax.groupby([segment_by, "error_class"]).size()
                 .rename("rows").reset_index())
    else:
        cross = counts.copy()

    wrong = tax[tax["error_class"] != "CORRECT"]
    metrics = [
        metric("n", "Rows examined", int(len(tax)), "int"),
        metric("threshold", "Threshold applied", thr, "float4",
               "chosen by you" if chosen_by_caller else "selected on the training split"),
        metric("wrong", "Rows not classified correctly", int(len(wrong)), "int"),
        metric("error_rate", "Error rate",
               # `max(1, ...)` guards against dividing by zero on an empty table.
               float(len(wrong) / max(1, len(tax))), "pct"),
        metric("classes", "Distinct failure modes",
               # HOW MANY DIFFERENT WAYS it goes wrong -- not merely how often.
               int(counts[counts["error_class"] != "CORRECT"].shape[0]), "int"),
    ]
    observations = [
        "%d of %d rows in this slice are not classified correctly at threshold %.4f."
        % (len(wrong), len(tax), thr),
    ]
    if len(wrong):
        worst = (wrong["error_class"].value_counts().idxmax())
        observations.append(
            # AND THE READING INSTRUCTION: MISSING_EVIDENCE and DATA_QUALITY mean the
            # evidence was absent, NOT that the model reasoned badly. Spelled out so the
            # commonest failure class is not mistaken for a modelling defect.
            "The most common failure mode here is %s. The taxonomy diagnoses data "
            "problems before model problems, so a row counted as MISSING_EVIDENCE or "
            "DATA_QUALITY is one where the evidence was absent, not one where the model "
            "reasoned badly." % worst)
    if not chosen_by_caller and source:
        observations.append("The threshold came from %s." % source)

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "selection": {"arm": arm, "threshold": thr, "segment_by": segment_by,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[
            series("taxonomy", "Failure modes on this slice",
                   list(counts.columns), counts.values.tolist(),
                   # CORRECT is included, so the shares add to one and the errors are seen
                   # against the whole rather than alone.
                   "one row per class, including CORRECT"),
            series("segmented", "Failure modes by %s" % segment_by,
                   list(cross.columns), cross.head(60).values.tolist(),
                   "at most 60 rows shown", total_rows=int(len(cross))),
        ],
        observations=observations,
        uncertainty={
            "kind": "threshold",
            "threshold": thr,
            "reading": (
                # The same warning as STATS-10, in the form that fits here: this is the
                # COMPOSITION of the errors at ONE threshold, not a property of the model
                # everywhere.
                "Which rows are wrong depends entirely on the threshold. The "
                "counts above are the composition of the errors at this one, not "
                "a property of the model at every threshold."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:classify_errors"],
                    "arm": arm, "threshold_chosen_by_caller": chosen_by_caller,
                    "wrote_nothing": True},
        message="%d of %d rows misclassified at %.4f" % (len(wrong), len(tax), thr),
    )


# ------------------------------------------------------------------- STATS-14 ----

def analyse_ablation(arms: list[str] | None = None, reference: str = "FULL",
                     date_from: str | None = None,
                     date_to: str | None = None) -> AnalysisResult:
    """STATS-14 live: recompute each arm's detection metrics on the selected rows.

    The arms were fitted once, by the experiment runner, and their per-row scores are
    stored. What is recomputed here is the *metric* over the rows you chose — which is the
    honest interactive version of an ablation, because refitting on request would let a
    reader arrive at an arm ranking chosen after seeing the evaluation data.

    A difference smaller than the seed noise floor is not a finding. The floor is measured
    in STATS-16 and is not assumed here, so the gaps below are reported as gaps.
    """
    # PLAIN ENGLISH: A DELIBERATE LIMIT ON WHAT THE INTERACTIVE VERSION WILL DO.
    # The models are NOT retrained on request. Their stored scores are re-measured over the
    # rows you picked.
    # Why refuse to refit? Because a reader could then try window after window until one
    # produced the arm ranking they wanted -- choosing the result after seeing the data. So
    # the capability is simply not offered.
    # AND THE SECOND PARAGRAPH IS EQUALLY GOOD: the gaps are reported AS GAPS, with no claim
    # about which is better, because the scale needed to judge them lives in STATS-16 and is
    # not assumed here.
    from research.evaluation import metrics as mx
    from scripts.stages import live

    available = live.available_arms()
    wanted = [a for a in (arms or ["FULL", "NO_TEXT", "NO_MARKET", "TEXT_ONLY"])
              if a in available]
    # The reference arm is added if it was left out -- without it there is nothing to compare
    # against.
    if reference not in wanted and reference in available:
        wanted = [reference, *wanted]
    if len(wanted) < 2:
        # AND THE REMEDY LISTS THE ARMS THAT ACTUALLY EXIST, so the reader can choose one
        # rather than guess.
        return insufficient(
            "fewer than two of the requested arms have per-row scores on disk",
            "Choose arms from the executed set: %s." % ", ".join(available[:12]))

    rows, skipped = [], []
    for arm in wanted:
        sel, problem = _scored(arm, date_from, date_to, None)
        if sel is None:
            # SKIPPED ARMS ARE REMEMBERED WITH THEIR REASON, and reported below. An arm
            # vanishing silently would make the comparison look more complete than it is.
            skipped.append((arm, problem[0]))
            continue
        d = mx.detection_metrics(sel["is_episode"].to_numpy(int),
                                 sel["integrity_risk"].to_numpy(float))
        rows.append({"arm": arm, "n": int(d["n"]), "auprc": d["auprc"],
                     "auroc": d["auroc"], "brier": d["brier"],
                     "auprc_lift": d["auprc_lift"]})
    if len(rows) < 2:
        return insufficient(
            "only %d arm(s) could be scored on this slice" % len(rows),
            "Widen the date range so each arm has enough scored rows.")

    table = pd.DataFrame(rows).sort_values("auprc", ascending=False)
    ref_row = table[table["arm"] == reference]
    base = float(ref_row["auprc"].iloc[0]) if len(ref_row) else float(
        table["auprc"].max())
    table["delta_vs_reference"] = table["auprc"] - base
    best, worst = table.iloc[0], table.iloc[-1]

    metrics = [
        metric("arms", "Arms compared", int(len(table)), "int"),
        metric("reference_auprc", "%s AUPRC" % reference, base, "float4"),
        metric("best_auprc", "Best AUPRC here", float(best["auprc"]), "float4",
               "arm %s" % best["arm"]),
        metric("spread", "Spread across arms",
               # THE SPREAD IS THE MOST USEFUL NUMBER HERE. If every arm lands within 0.003
               # of every other, the ranking between them is meaningless whatever the order.
               float(table["auprc"].max() - table["auprc"].min()), "float4",
               "largest minus smallest AUPRC on this slice"),
        metric("rows", "Rows per arm", int(table["n"].iloc[0]), "int"),
    ]
    observations = [
        "Metrics were recomputed on the %d rows in your window; the arms themselves were "
        "fitted once by the experiment runner and are not refitted here."
        % int(table["n"].iloc[0]),
        "%s leads on this slice and %s trails, a gap of %.4f AUPRC."
        % (best["arm"], worst["arm"],
           float(best["auprc"] - worst["auprc"])),
        # AND IMMEDIATELY AFTER NAMING A WINNER, THE REFUSAL TO CALL IT ONE. A gap smaller
        # than the seed noise floor is not evidence that one arm is better -- it is the dice.
        # Announcing the leader and then declining to conclude anything from it, in
        # consecutive sentences, is the whole spirit of this project.
        "Whether a gap this size is a finding depends on the seed noise floor, which is "
        "measured separately in STATS-16. A gap smaller than the floor is not evidence "
        "that one arm is better.",
    ]
    if skipped:
        observations.append(
            "%d arm(s) could not be scored on this slice: %s."
            % (len(skipped), "; ".join("%s (%s)" % (a, r) for a, r in skipped[:3])))

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_*.parquet",
                 "rows": int(table["n"].sum()),
                 "selection": {"arms": wanted, "reference": reference,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("arms", "Detection metrics per arm on this slice",
                       list(table.columns), table.values.tolist(),
                       "delta_vs_reference is AUPRC minus the reference arm's AUPRC")],
        observations=observations,
        uncertainty={
            # "no_interval" -- an honest name for "these are bare points with no error bars".
            "kind": "no_interval",
            "reading": (
                # AND A CONCRETE RULE ANYBODY CAN APPLY: two arms differing in the THIRD
                # DECIMAL should be treated as UNRESOLVED. Not "close", not "tied" --
                # unresolved, which is the accurate word.
                "These are point estimates on one slice with no confidence "
                "interval attached. Two arms whose AUPRC differs in the third "
                "decimal should be treated as unresolved until the seed noise "
                "floor in STATS-16 says otherwise."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:"
                                         "detection_metrics"],
                    "arms": wanted, "reference": reference,
                    # RECORDED EXPLICITLY: nothing was refitted.
                    "refitted": False, "wrote_nothing": True},
        message="%d arms compared over %d rows each"
                % (len(table), int(table["n"].iloc[0])),
    )


# ------------------------------------------------------------------- STATS-15 ----

def analyse_robustness(corruption: str = "gaussian", severity: float = 0.10,
                       block: str = "all", seed: int = 20260818) -> AnalysisResult:
    """STATS-15 live: one perturbation condition, fitted clean and scored degraded.

    The model is fitted once on clean data and the *evaluation* inputs are degraded. That
    asymmetry is the point: refitting on corrupted data measures whether the learner can
    adapt to a new noise regime, which is an easier and different question from what
    happens to a deployed model when its feed degrades.

    The frozen holdout is never read; the canonical harness refuses a frame containing it.
    """
    # PLAIN ENGLISH: THE ASYMMETRY IS THE EXPERIMENT.
    # Train on clean data. Test on damaged data. Because that is the real situation: a model
    # was built when everything worked, and then a data feed degraded. The model cannot
    # adapt -- it has already been trained.
    # Retraining on the damaged data would answer a completely different and much easier
    # question: "could a model learn to cope with this noise if it knew about it?" Interesting,
    # but not the question anybody deploying a system needs answered.
    from research.evaluation import robustness as rb
    from scripts.stages import live

    if corruption not in ("gaussian", "dropout", "stale", "outliers"):
        # A CLOSED LIST, checked before anything runs -- and the remedy names every valid
        # option. Also means no arbitrary string from a request reaches the machinery below.
        return insufficient(
            "%r is not one of the implemented failure modes" % corruption,
            "Choose gaussian, dropout, stale or outliers.")

    data = live.panel()
    # `working_set` strips the frozen holdout out immediately.
    work = rb.working_set(data)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    cols = (rb.feature_columns(work) if block in ("", "all")
            else rb.block_columns(work, block))
    if not cols:
        return insufficient(
            "no feature columns for block %r are present" % block,
            "Choose all, or a feature block the panel actually carries.")

    # THE UNDAMAGED REFERENCE, measured first. Without it the degraded number would have
    # nothing to be worse than.
    clean = rb.fit_and_score(train, evald, list(rb.ds.FEATURE_BLOCKS), int(seed),
                             "clean", "undegraded reference")
    if clean.status != "OK":
        return insufficient(
            "the clean reference fit did not complete: %s" % clean.reason,
            # AND THE REMEDY IS HONEST ABOUT NOT BEING THE CALLER'S FAULT: "This is a
            # condition of the data, not of your selection." Nothing they change will help.
            "This is a condition of the data, not of your selection.")

    # Damage ONLY the evaluation frame. `train` is passed to both fits unchanged.
    degraded_frame = rb.perturb(evald, cols, corruption, float(severity), int(seed))
    degraded = rb.fit_and_score(train, degraded_frame, list(rb.ds.FEATURE_BLOCKS),
                                int(seed), "%s@%.2f" % (corruption, severity),
                                "evaluation inputs degraded")
    if degraded.status != "OK":
        return insufficient(
            "the degraded fit did not complete: %s" % degraded.reason,
            "Try a lower severity.")

    base = float(clean.metrics.get("auprc", float("nan")))
    hit = float(degraded.metrics.get("auprc", float("nan")))
    table = pd.DataFrame([
        {"condition": "clean", **dict(clean.metrics)},
        {"condition": "%s@%.2f" % (corruption, severity),
         **dict(degraded.metrics)},
    ])

    metrics = [
        metric("clean_auprc", "AUPRC, clean inputs", base, "float4"),
        metric("degraded_auprc", "AUPRC, degraded inputs", hit, "float4"),
        metric("degradation", "Loss in AUPRC", base - hit, "float4",
               # THE SIGN EXPLAINED, so nobody has to work out which direction is bad.
               "clean minus degraded; positive means the corruption hurt"),
        metric("relative", "Share of AUPRC lost",
               # BOTH ABSOLUTE AND RELATIVE. Losing 0.05 is trivial from 0.9 and
               # catastrophic from 0.06.
               (base - hit) / base if base else float("nan"), "pct"),
        metric("columns", "Columns degraded", len(cols), "int"),
        metric("eval_rows", "Evaluation rows", int(len(evald)), "int"),
    ]
    observations = [
        "One condition, run now: %s at severity %.2f applied to %d %s columns of the "
        "evaluation inputs." % (corruption, severity, len(cols),
                                "feature" if block in ("", "all") else block),
        "AUPRC moves from %.4f to %.4f, a loss of %.4f." % (base, hit, base - hit),
        # THE JUSTIFICATION FOR THE DESIGN, ADDRESSED TO THE READER: this is the situation a
        # deployed model is actually in when a feed degrades.
        "The model was fitted once on clean data and never saw the degradation, which is "
        "the situation a deployed model is in when a feed degrades.",
        # AND THE HOLDOUT PROMISE, RESTATED IN THE RESPONSE ITSELF.
        "The frozen holdout was not read: this ran on train and validation only.",
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/market_dataset.parquet",
                 "rows": int(len(work)),
                 "selection": {"corruption": corruption, "severity": float(severity),
                               "block": block, "seed": int(seed)}},
        metrics=metrics,
        series=[series("conditions", "Clean against degraded",
                       list(table.columns), table.values.tolist(),
                       # Both rows produced by the SAME path the regenerating harness uses --
                       # so the live comparison is the real comparison.
                       "both rows produced by the same fit-and-score path the "
                       "regenerating harness uses")],
        observations=observations,
        uncertainty={
            "kind": "single_seed",
            "seed": int(seed),
            "reading": (
                # THE HONEST DISCOUNT ON ITS OWN RESULT: part of the difference you are
                # looking at is not the corruption at all, it is seed variance. And it points
                # at the module that measures the scale to judge it by.
                "One condition at one seed. Part of the difference above is "
                "seed variance rather than the corruption: the noise floor "
                "measured in STATS-16 is the scale against which a loss this "
                "size should be read."),
        },
        provenance={"canonical_called": ["research.evaluation.robustness:perturb",
                                         "research.evaluation.robustness:fit_and_score",
                                         "research.evaluation.robustness:working_set"],
                    "corruption": corruption, "severity": float(severity),
                    # THREE CLAIMS RECORDED AS DATA: fitted on clean only, holdout not read,
                    # wrote nothing. Machine-checkable rather than merely promised in prose.
                    "seed": int(seed), "refitted_on_clean_only": True,
                    "holdout_read": False, "wrote_nothing": True},
        message="%s@%.2f costs %.4f AUPRC" % (corruption, severity, base - hit),
    )


# ------------------------------------------------------------------- STATS-16 ----

def analyse_seed_noise(arms: list[str] | None = None,
                       alpha: float = 0.05) -> AnalysisResult:
    """STATS-16 live: the seed noise floor over the arms you select.

    Re-derived from the stored seed table rather than refitted, because refitting sixteen
    arms across five seeds on request would take minutes and produce the same numbers. The
    computation that matters — pooling the within-arm seed variance into a floor, and
    testing arm differences against it with a multiplicity correction — runs now, on the
    arms you chose.

    The floor is the point. A difference between two arms that is smaller than it is not a
    small effect; it is not distinguishable from rerunning the same arm with a different
    seed.
    """
    # PLAIN ENGLISH: THE MODULE EVERY OTHER COMPARISON DEPENDS ON.
    # The NOISE FLOOR is how much a result moves when you change NOTHING but the random seed.
    # And the last paragraph makes the distinction that matters:
    #   a difference below the floor is NOT a small effect;
    #   it is not distinguishable from rerunning the same thing twice.
    # "Small but real" and "indistinguishable from noise" are completely different claims,
    # and only the second one is honest here.
    from research.statistics import tests as st

    path = (paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"
            / "seed_table.csv")
    if not path.exists():
        return insufficient(
            "the multi-seed table has not been produced",
            "Run `python scripts/run_module.py --module STATS-16` at a terminal.")

    table = pd.read_csv(path)
    table = table[table["status"] == "OK"]
    available = sorted(table["arm"].unique())
    wanted = [a for a in (arms or available) if a in available]
    if len(wanted) < 2:
        return insufficient(
            "fewer than two of the selected arms have completed seed fits",
            "Choose at least two of: %s." % ", ".join(available[:12]))

    sel = table[table["arm"].isin(wanted)]
    # An arm with one completed seed has no standard deviation, and asking numpy for one
    # produces a warning and a NaN. Reporting it as blank is the honest rendering: the
    # spread was not measured, rather than measured as zero.
    # PLAIN ENGLISH: you cannot measure the spread of a single number. Recording it as 0.0
    # would say "this arm is perfectly stable" -- the strongest possible claim -- on the
    # basis of no evidence whatsoever. So it stays blank.
    grouped = sel.groupby("arm")["auprc"]
    per_arm = pd.DataFrame({
        "arm": grouped.count().index,
        "seeds": grouped.count().to_numpy(int),
        "auprc_mean": grouped.mean().to_numpy(float),
        # `ddof=1` is the sample standard deviation; NaN when there is only one value.
        "auprc_sd": [float(g.std(ddof=1)) if len(g) > 1 else float("nan")
                     for _, g in sel.groupby("arm")["auprc"]],
    }).sort_values("auprc_mean", ascending=False)
    # Only arms with at least two completed seeds contribute a within-arm variance; an
    # arm with one is not a low-variance arm, it is an unmeasured one.
    # PLAIN ENGLISH: the same principle again, and it MATTERS MORE HERE -- letting a
    # single-seed arm contribute a "zero" spread would drag the pooled floor DOWNWARDS,
    # making every difference look more significant than it is. Excluding it protects every
    # comparison in the project.
    counts = sel.groupby("arm")["auprc"].count()
    within = (sel[sel["arm"].isin(counts[counts >= 2].index)]
              .groupby("arm")["auprc"].std(ddof=1).dropna())
    # Pool the per-arm spreads: square them, average, square-root. Variances add, standard
    # deviations do not, which is why it goes through the squares.
    pooled_sd = float(np.sqrt((within ** 2).mean())) if len(within) else float("nan")
    # 1.96 is the 95% figure; the sqrt(2) is because comparing TWO noisy numbers carries both
    # of their wobbles.
    floor = float(1.96 * pooled_sd * np.sqrt(2)) if np.isfinite(pooled_sd) else float(
        "nan")

    # Every pair, tested against the floor and then corrected for the number of tests.
    pairs = []
    arms_sorted = per_arm["arm"].tolist()
    for i, a in enumerate(arms_sorted):
        for b in arms_sorted[i + 1:]:
            xa = sel.loc[sel["arm"] == a, "auprc"].to_numpy(float)
            xb = sel.loc[sel["arm"] == b, "auprc"].to_numpy(float)
            n = min(len(xa), len(xb))
            if n < 2:
                continue
            # PAIRED on seed: seed 1 against seed 1, seed 2 against seed 2. The luck the two
            # shared cancels out.
            diff = xa[:n] - xb[:n]
            # A PERMUTATION TEST: shuffle the labels thousands of times and see how often
            # chance alone produces a difference this large. It assumes nothing about the
            # shape of the data.
            result = st.paired_permutation(diff, n_perm=2000, seed=20260818)
            pairs.append({"arm_a": a, "arm_b": b,
                          "difference": float(diff.mean()),
                          # BOTH TESTS RECORDED SEPARATELY.
                          "exceeds_noise_floor": bool(abs(diff.mean()) > floor),
                          "p_value": (float(result.p_value)
                                      if result.p_value is not None else float("nan")),
                          "pairs_tested": int(result.n)})
    pair_table = pd.DataFrame(pairs)
    survives = resolved = 0
    if len(pair_table):
        bh = st.benjamini_hochberg(pair_table["p_value"].tolist(), alpha=float(alpha))
        pair_table["adjusted_p"] = bh["adjusted_p"].to_numpy()
        pair_table["survives_correction"] = bh["reject"].to_numpy()
        # Both conditions, deliberately. Surviving the correction says the difference is
        # unlikely to be zero; exceeding the floor says it is larger than what reseeding
        # the same arm produces. A difference can pass the first and fail the second, and
        # such a pair is reliably small rather than reliably meaningful.
        # PLAIN ENGLISH: THE SHARPEST STATISTICAL POINT IN THE PROJECT.
        # STATISTICAL SIGNIFICANCE says "this difference is probably not exactly zero."
        # With enough data you can establish that about a difference of 0.0001.
        # THE NOISE FLOOR says "this difference is bigger than what rerunning the same thing
        # produces."
        # A difference can pass the first and fail the second -- reliably real, and reliably
        # too small to care about. So both are required, and the combination gets its own
        # name: RESOLVED.
        pair_table["resolved"] = (pair_table["survives_correction"]
                                  & pair_table["exceeds_noise_floor"])
        survives = int(pair_table["survives_correction"].sum())
        resolved = int(pair_table["resolved"].sum())

    metrics = [
        metric("arms", "Arms compared", len(wanted), "int"),
        # The MINIMUM seeds per arm, not the average -- the weakest link is what limits the
        # comparison.
        metric("seeds", "Seeds per arm", int(per_arm["seeds"].min()), "int"),
        metric("pooled_sd", "Pooled seed standard deviation", pooled_sd, "float5",
               "within-arm AUPRC variation across seeds"),
        metric("floor", "95% seed noise floor", floor, "float5",
               # The definition, in one clause anybody can act on.
               "an AUPRC gap smaller than this is not distinguishable from reseeding"),
        metric("pairs", "Pairs tested", int(len(pair_table)), "int"),
        metric("survives", "Pairs surviving correction", survives, "int",
               "after Benjamini-Hochberg at alpha %.2f" % alpha),
        metric("resolved", "Pairs resolved", resolved, "int",
               # THE STRICTER COUNT, and the one that actually means something.
               "both larger than the noise floor and surviving the correction"),
    ]
    within_floor = (int((~pair_table["exceeds_noise_floor"]).sum())
                    if len(pair_table) else 0)
    observations = [
        "The noise floor on these arms is %.5f AUPRC. Rerunning the same arm with a "
        "different seed moves it by about that much." % floor,
        # AND THE FINEST PHRASE IN THE FILE: "not close, not equal, simply not separable by
        # this evidence."
        # Three readings refused in one line. Not "nearly the same" -- that claims they are
        # similar. Not "the same" -- that claims they are equal. UNRESOLVED: this evidence
        # cannot tell them apart, and says nothing more.
        "%d of %d arm pairs differ by less than the floor and are unresolved: not close, "
        "not equal, simply not separable by this evidence."
        % (within_floor, len(pair_table)),
        # And the two counts distinguished one final time, with the reason.
        "%d pair(s) survive multiplicity correction at alpha %.2f, and %d of those are "
        "also larger than the floor. Only the second count is a resolved difference: a "
        "gap can be reliably non-zero and still be no larger than reseeding."
        % (survives, alpha, resolved),
    ]
    return AnalysisResult(
        dataset={"source": "outputs/stats/16_multiseed_significance/seed_table.csv",
                 "rows": int(len(sel)),
                 "selection": {"arms": wanted, "alpha": float(alpha)}},
        metrics=metrics,
        series=[
            series("per_arm", "AUPRC across seeds, per arm",
                   list(per_arm.columns), per_arm.values.tolist(),
                   "mean and standard deviation over the seeds that completed"),
            series("pairs", "Pairwise differences against the floor",
                   list(pair_table.columns), pair_table.values.tolist(),
                   # THE RULE, IN THE TABLE'S OWN CAPTION: below the floor is unresolved
                   # REGARDLESS of how impressive the p-value looks.
                   "a difference below the floor is unresolved regardless of its "
                   "p-value") if len(pair_table) else
            # And when no pair could be tested, a table saying exactly that -- rather than an
            # empty one, which would read as "no differences found".
            series("pairs", "Pairwise differences", ["note"],
                   [["not enough seeds per arm to test any pair"]], ""),
        ],
        observations=observations,
        uncertainty={
            "kind": "seed_variance",
            "pooled_sd": pooled_sd,
            "noise_floor_95": floor,
            "reading": (
                # THE MODULE DESCRIBING ITS OWN ROLE: this is the uncertainty every other
                # comparison in the project should be read against.
                # AND THEN IT BOUNDS ITSELF: the floor comes from the seeds actually run,
                # more seeds would tighten it, and it says nothing about variance from any
                # other source -- different data, different features, a different market.
                "This module measures the uncertainty every other comparison in "
                "the project should be read against. The floor is derived from "
                "the seeds that were actually run; more seeds would tighten it, "
                "and it is not an estimate of variance from any other source."),
        },
        provenance={"canonical_called": ["research.statistics.tests:paired_permutation",
                                         "research.statistics.tests:benjamini_hochberg"],
                    "arms": wanted, "refitted": False, "wrote_nothing": True},
        message="noise floor %.5f AUPRC over %d arms" % (floor, len(wanted)),
    )
