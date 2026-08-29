<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-05 — Regime statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | `EXP-N02-1` |
| Limitations | — |

## Purpose

Occupancy, persistence and transition structure of the detected market regimes as they appear in the assembled dataset.

## Research question

> Are the detected regimes stable and well-populated enough for regime-conditioned results to be interpretable?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:regime_statistics`

Canonical implementation:

- `research/regime/detection.py::index_descriptors`
- `research/regime/detection.py::select_order`
- `research/regime/detection.py::bootstrap_stability`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/05_regime_statistics/regime_occupancy.csv`

## Dependencies

- `STATS-01`

## How to run

```bat
REM from anywhere
STATS\05_regime_statistics\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-05
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-05 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_05.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Regime-conditioned combination is a measured negative result (N-02); this module reports the regime structure, not the combination outcome.

## Status

`WRAPS_EXISTING` / `PARTIAL`
