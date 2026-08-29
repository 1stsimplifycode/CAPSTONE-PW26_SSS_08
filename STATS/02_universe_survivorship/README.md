<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-02 — Universe and survivorship statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-01` |

## Purpose

Characterise the point-in-time liquidity-proxy universe: membership over time, churn per rebalance, distinct members ever selected, and the turnover statistics that make the construction survivorship-safe.

## Research question

> How much does the research universe turn over, and what does that imply for any result read as applying to a stable large-cap index?

## Inputs

- `data/panel/universe.parquet`

## Processing

Adapter: `scripts.stages.stats:universe_survivorship`

Canonical implementation:

- `research/data/universe.py::LiquidityProxyUniverse.churn`
- `research/data/universe.py::LiquidityProxyUniverse.turnover_stats`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/02_universe_survivorship/universe_summary.json`
- `outputs/stats/02_universe_survivorship/churn.csv`

## Dependencies

- none

## How to run

```bat
REM from anywhere
STATS\02_universe_survivorship\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-02
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-02 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_02.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

The universe is a liquidity proxy, never the Nifty 50. L-01 records why licence-clear point-in-time index membership was not obtainable.

See `docs/LIMITATIONS.md` for **L-01**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
