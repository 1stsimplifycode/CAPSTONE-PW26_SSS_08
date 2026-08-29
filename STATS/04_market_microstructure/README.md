<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-04 — Market and microstructure-proxy statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | `L-02` |

## Purpose

Coverage and behaviour of the 18 market features and the 4 microstructure proxies, together with the explicit register of microstructure quantities that are NOT MEASURED because daily bhavcopy cannot support them.

## Research question

> How much microstructure information do daily proxies retain relative to genuine order-book data, and what is provably absent?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:market_microstructure`

Canonical implementation:

- `research/market/features.py::MARKET_FEATURES`
- `research/market/features.py::MICROSTRUCTURE_PROXIES`
- `research/market/features.py::MICROSTRUCTURE_NOT_MEASURED`
- `research/market/features.py::coverage_report`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/04_market_microstructure/market_coverage.csv`
- `outputs/stats/04_market_microstructure/not_measured.json`

## Dependencies

- `STATS-01`

## How to run

```bat
REM from anywhere
STATS\04_market_microstructure\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-04
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-04 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_04.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Daily-bar proxies must never be described as true order-book microstructure (L-02).

See `docs/LIMITATIONS.md` for **L-02**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
