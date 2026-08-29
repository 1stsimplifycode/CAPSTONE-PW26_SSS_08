<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-11 — Calibration and uncertainty

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | `EXP-L10-1` |
| Limitations | `L-10` |

## Purpose

Reliability curve, expected calibration error, Brier score, calibration conditioned on uncertainty and on coverage, and the selective-risk curve.

## Research question

> Is the risk score interpretable as a probability, and does the model's own uncertainty identify the rows where it should not be trusted?

## Inputs

- `research_artifacts/experiments/per_row_FULL.parquet`

## Processing

Adapter: `scripts.stages.stats:calibration_uncertainty`

Canonical implementation:

- `research/evaluation/metrics.py::expected_calibration_error`
- `research/evaluation/metrics.py::reliability_curve`
- `research/evaluation/information.py::selective_risk`
- `research/evaluation/information.py::calibration_by_bucket`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/11_calibration_uncertainty/reliability.csv`
- `outputs/stats/11_calibration_uncertainty/calibration.json`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\11_calibration_uncertainty\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-11
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-11 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_11.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

The risk score is not a calibrated probability and is never described as one (L-10).

See `docs/LIMITATIONS.md` for **L-10**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
