<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-12 — Error analysis

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | — |

## Purpose

Classify predictions at the operating threshold into true and false positives and negatives, and describe how the errors are distributed across instruments, regimes, coverage levels and time.

## Research question

> Where does the detector fail, and what characterises those failures?

## Inputs

- `research_artifacts/experiments/per_row_FULL.parquet`

## Processing

Adapter: `scripts.stages.stats:error_analysis`

Canonical implementation:

- `research/evaluation/metrics.py::classify_errors`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/12_error_analysis/error_taxonomy.csv`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\12_error_analysis\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-12
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-12 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_12.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Descriptive only. Nothing here supports a causal statement about why an error occurred.

## Status

`WRAPS_EXISTING` / `PARTIAL`
