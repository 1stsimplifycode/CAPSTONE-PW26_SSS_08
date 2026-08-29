<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-15 — Robustness and generalization

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | `L-11` |

## Purpose

Performance under feature noise, input corruption, induced missingness and reduced training data, and transfer across time periods and across disjoint instrument sets.

## Research question

> Where does the detector stop being reliable, and does it transfer beyond the instruments and period it was fitted on?

## Inputs

- `data/panel/market_dataset.parquet`

## Processing

Adapter: `scripts.stages.stats:robustness_generalization`

Canonical implementation:

- `research/evaluation/robustness.py`
- `scripts/run_robustness_generalization.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/15_robustness_generalization/robustness.csv`
- `outputs/stats/15_robustness_generalization/generalization.csv`
- `outputs/stats/15_robustness_generalization/run.json`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\15_robustness_generalization\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-15
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-15 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_15.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Five axes execute: additive noise, value dropout, stale feed, outlier injection and per-block blackout on the evaluation inputs; a symbol-level training-size curve; expanding-window transfer forward in time; and transfer to disjoint tickers. The model is fitted once on clean data for the input-degradation axis, because refitting on corrupted data measures whether the learner adapts, which is an easier and different question than what a deployed model does when its feed degrades. Training subsampling drops whole symbols rather than random rows: rows from one instrument are serially dependent, so row-level dropping leaves nearly every instrument represented and understates how much the model depends on breadth. The frozen holdout is never read -- assert_no_holdout() raises on any frame carrying holdout rows and every fit passes through it. Cross-dataset transfer remains BLOCKED and is reported as such, because only one dataset exists. Adversarial robustness is NOT RUN: every corruption here is random, and an adversarial claim needs a threat model.

See `docs/LIMITATIONS.md` for **L-11**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
