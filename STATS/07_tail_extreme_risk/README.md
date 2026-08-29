<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-07 — Tail and extreme-risk statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | — |

## Purpose

Tail behaviour of the exposure-gate research instrument: CVaR, maximum drawdown and the distribution of the net series it produces.

## Research question

> What are the tail characteristics of the research exposure policy, treated strictly as a measurement instrument rather than as a strategy?

## Inputs

- `research_artifacts/experiments/per_row_FULL.parquet`

## Processing

Adapter: `scripts.stages.stats:tail_extreme_risk`

Canonical implementation:

- `research/risk/gate.py::tail_metrics`
- `research/risk/gate.py::capital_consequence`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/07_tail_extreme_risk/tail_metrics.json`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\07_tail_extreme_risk\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-07
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-07 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_07.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

The exposure policy is a research instrument and is never an allocation. Nothing in this module produces a position size.

## Status

`WRAPS_EXISTING` / `PARTIAL`
