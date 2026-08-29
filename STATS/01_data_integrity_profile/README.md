<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-01 — Data and integrity profile

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | `L-12` |

## Purpose

Report what the assembled dataset actually contains before any result is computed from it: row and column counts, per-block coverage, missing values, duplicate keys, class balance and the train/validation/holdout split sizes.

## Research question

> Does the dataset satisfy the structural preconditions every downstream claim assumes, and where is coverage thin enough to bound a conclusion?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:data_integrity_profile`

Canonical implementation:

- `research/market/features.py::coverage_report`
- `research/data/dataset.py::FEATURE_BLOCKS`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/01_data_integrity_profile/profile.json`
- `outputs/stats/01_data_integrity_profile/block_coverage.csv`

## Dependencies

- none

## How to run

```bat
REM from anywhere
STATS\01_data_integrity_profile\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-01
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-01 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_01.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Reports counts and coverage only. Formal leakage verification is STATS-09; the confusion-matrix-level validation suite is STATS-10 and is not implemented yet.

See `docs/LIMITATIONS.md` for **L-12**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
