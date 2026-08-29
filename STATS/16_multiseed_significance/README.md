<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-16 — Multi-seed and statistical significance

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-12` |

## Purpose

Repeat the stochastic parts of the pipeline across seeds and report mean, standard deviation, minimum, maximum and 95% confidence interval, then apply the existing cluster bootstrap, paired permutation, Benjamini-Hochberg correction and power analysis to the repeated measurements.

## Research question

> How much of the reported difference between arms is seed variance rather than signal?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:multiseed_significance`

Canonical implementation:

- `research/evaluation/multiseed.py`
- `scripts/run_multiseed.py`
- `research/statistics/tests.py`
- `research/statistics/power.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/16_multiseed_significance/seed_table.csv`
- `outputs/stats/16_multiseed_significance/significance.json`
- `outputs/stats/16_multiseed_significance/seed_summary.csv`
- `outputs/stats/16_multiseed_significance/paired_tests.csv`

## Dependencies

- `STATS-13`
- `STATS-14`

## How to run

```bat
REM from anywhere
STATS\16_multiseed_significance\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-16
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-16 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_16.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Every ablation arm is refitted across a declared seed ladder and the repeated measurements are handed to the machinery that already existed: cluster bootstrap, paired sign-flip permutation and Benjamini-Hochberg. Two sources of variation are kept apart, because conflating them is how a seed study overstates its own precision -- spread across seeds on one fixed evaluation set is seed variance, and the cluster bootstrap interval within one run is sampling variance of the evaluation set. A pooled seed noise floor is reported, and an arm difference smaller than that floor is recorded as not established however it looked in a single run. Differences that dissolve are listed alongside the ones that survive rather than filtered out. Validation only: repeating a measurement on the frozen holdout across ten seeds would be ten looks at the data the freeze exists to protect.

See `docs/LIMITATIONS.md` for **L-12**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
