<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-10 — Validation and verification metrics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-04`, `L-11` |

## Purpose

The full classification verification suite the current metrics module lacks: confusion matrix with TP/TN/FP/FN, accuracy, balanced accuracy, specificity, Matthews correlation coefficient, false-positive and false-negative rates, and per-class performance.

## Research question

> Beyond ranking quality, how does the detector behave at its operating point, and how is that behaviour distributed across the error types?

## Inputs

- `research_artifacts/experiments/per_row_FULL.parquet`

## Processing

Adapter: `scripts.stages.stats:validation_verification`

Canonical implementation:

- `research/evaluation/metrics.py::classification_metrics`
- `research/evaluation/metrics.py::confusion_counts`
- `research/evaluation/metrics.py::confusion_matrix_frame`
- `research/evaluation/metrics.py::per_class_report`
- `research/evaluation/metrics.py::verification_report`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/10_validation_verification/confusion_matrix.csv`
- `outputs/stats/10_validation_verification/per_class.csv`
- `outputs/stats/10_validation_verification/verification_metrics.json`

## Dependencies

- `STATS-13`

## How to run

```bat
REM from anywhere
STATS\10_validation_verification\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-10
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-10 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_10.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Implemented in the metrics commit. The suite lives in the canonical metrics module alongside the detection metrics, not in a parallel framework, and reproduces the precision, recall and F1 already recorded in the FULL experiment bundle to within 1e-12. The operating threshold is read from that bundle, where it was chosen on the training split: recomputing it from the evaluation scores would be threshold provenance leakage (L6). Results describe synthetic episodes on the validation split; the holdout remains frozen (L-11).

See `docs/LIMITATIONS.md` for **L-04**, **L-11**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
