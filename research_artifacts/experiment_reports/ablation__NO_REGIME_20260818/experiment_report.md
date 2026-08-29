# Experiment report: ablation__NO_REGIME_20260818

**Hypothesis.** regime conditioning improves combination (RQ9)

**Arm.** `NO_REGIME` | blocks: text, image, audio, video, market, microstructure, propagation | combiner: `static_attention`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.9471 |
| auroc | 0.9671 |
| brier | 0.0929 |
| ece | 0.1745 |
| threshold | 0.3105 |
| precision | 0.9372 |
| recall | 0.8734 |
| f1 | 0.9042 |
| auprc_lift | 3.8843 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 44 |
| n_matched | 26 |
| detection_rate | 0.7222 |
| false_alarm_windows | 18 |
| mean_lead_time | -8.6154 |
| median_lead_time | -10.0000 |
| mean_onset_error | 12.6923 |
| mean_abs_onset_error | 13.2308 |
| mean_resolution_error | 3.5263 |
| mean_temporal_iou | 0.4403 |
| mean_duration_error | -8.2632 |
| premature_resolution_rate | 0.0385 |
| delayed_resolution_rate | 0.6538 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 12.4709 |
| predict_seconds | 0.6928 |
| rows | 3855 |
| throughput_rows_per_s | 5564.7291 |
| latency_ms_per_row | 0.1797 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:07:05.329329+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.