<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-06 — Dependence and propagation statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | `EXP-N05-1` |
| Limitations | `L-07` |

## Purpose

Structure of the statistical co-movement graph: edge counts, degree distribution and neighbour counts per instrument-day.

## Research question

> What dependence structure exists between instruments, and how far can it be read without a causal identification strategy?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:dependence_propagation`

Canonical implementation:

- `research/propagation/graph.py::correlation_graph`
- `research/propagation/graph.py::PROPAGATION_FEATURES`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/06_dependence_propagation/graph_summary.json`

## Dependencies

- `STATS-01`

## How to run

```bat
REM from anywhere
STATS\06_dependence_propagation\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-06
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-06 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_06.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Statistical co-movement, never causal propagation (L-07). The propagation block's contribution is a measured near-null (N-05).

See `docs/LIMITATIONS.md` for **L-07**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
