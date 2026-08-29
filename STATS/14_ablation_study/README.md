<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-14 — Ablation study

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING_PROTECTED` |
| Research status | `SUPPORTED` |
| Experiment | `EXP-ABL-1` |
| Limitations | `L-12` |

## Purpose

All 28 declared arms: single-block, pairwise, leave-one-out, component removal and the six combination rules, each with its own hypothesis and artifact bundle.

## Research question

> Which components of the proposed architecture actually contribute, and which are redundant or harmful?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:ablation_study`

Canonical implementation:

- `research/evaluation/ablations.py::all_arms`
- `research/evaluation/experiment.py::run`
- `scripts/run_experiments.py`

This module wraps existing code, but regenerating its outputs would overwrite artifacts that the claim ledger and documentation already cite. It refuses to run without `--force` and exits with code 5 instead.

## Outputs

- `research_artifacts/experiments/ablation_results.csv`
- `research_artifacts/experiments/ablation_statistics.csv`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\14_ablation_study\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-14 --force
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-14 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_14.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Shares one runner with STATS-13; both are produced by a single invocation of scripts/run_experiments.py. Requires --force.

See `docs/LIMITATIONS.md` for **L-12**.

## Status

`WRAPS_EXISTING_PROTECTED` / `SUPPORTED`
