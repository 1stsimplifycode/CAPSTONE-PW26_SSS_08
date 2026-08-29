<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-09 — Leakage and split verification

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Execute the L1-L6 leakage suite: randomised as-of, future shift, restatement, survivorship, coverage substitution and threshold provenance.

## Research question

> Can any information unavailable at decision time reach a historical prediction?

## Inputs

- `tests/leakage`

## Processing

Adapter: `scripts.stages.stats:leakage_verification`

Canonical implementation:

- `tests/leakage/test_leakage_suite.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/09_leakage_verification/leakage_report.json`

## Dependencies

- none

## How to run

```bat
REM from anywhere
STATS\09_leakage_verification\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-09
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-09 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_09.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

This suite is blocking in CI and decides whether any other result may be believed. It runs read-only and writes no research artifact.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
