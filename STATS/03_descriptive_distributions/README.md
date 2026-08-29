<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-03 — Descriptive and distributional statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Per-feature descriptive statistics across all 99 features, grouped by feature block, with the fraction present and the number of distinct values so degenerate features are visible rather than silently averaged into a model.

## Research question

> Which features carry usable variation, and which are so degenerate that any importance attributed to them should be discounted?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:descriptive_distributions`

Canonical implementation:

- `research/data/dataset.py::FEATURE_BLOCKS`
- `research/data/dataset.py::ALL_FEATURES`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/03_descriptive_distributions/feature_summary.csv`
- `outputs/stats/03_descriptive_distributions/degenerate_features.csv`

## Dependencies

- `STATS-01`

## How to run

```bat
REM from anywhere
STATS\03_descriptive_distributions\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-03
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-03 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_03.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A degenerate entropy feature was found this way once before: quantile binning had pinned it near-constant. Reporting distinct-value counts keeps that failure visible.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
