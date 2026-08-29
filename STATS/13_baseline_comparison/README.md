<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-13 — Baseline comparison

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING_PROTECTED` |
| Research status | `SUPPORTED` |
| Experiment | `EXP-BASE-1` |
| Limitations | `L-04`, `L-11` |

## Purpose

Six baselines under one protocol: statistical anomaly, sentiment-only, text-only, market-only, image-only, audio-only and video-only, evaluated against the proposed full-stack model on the same split with the same preprocessing.

## Research question

> Does the proposed model outperform simple, conventional and single-block baselines under a fair protocol?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:baseline_comparison`

Canonical implementation:

- `research/models/baselines.py::run_all`
- `scripts/run_experiments.py`

This module wraps existing code, but regenerating its outputs would overwrite artifacts that the claim ledger and documentation already cite. It refuses to run without `--force` and exits with code 5 instead.

## Outputs

- `research_artifacts/experiments/baseline_results.csv`
- `research_artifacts/experiments/per_row_FULL.parquet`

## Dependencies

- `STATS-01`

## How to run

```bat
REM from anywhere
STATS\13_baseline_comparison\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-13 --force
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-13 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_13.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Regenerating overwrites artifacts the claim ledger cites. Requires --force.

See `docs/LIMITATIONS.md` for **L-04**, **L-11**.

## Status

`WRAPS_EXISTING_PROTECTED` / `SUPPORTED`
