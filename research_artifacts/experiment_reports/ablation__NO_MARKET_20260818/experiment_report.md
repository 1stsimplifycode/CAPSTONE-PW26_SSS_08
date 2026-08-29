# Experiment report: ablation__NO_MARKET_20260818

**Hypothesis.** removing market degrades detection

**Arm.** `NO_MARKET` | blocks: text, image, audio, video, microstructure, regime, propagation | combiner: `regime_corrected`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.8281 |
| auroc | 0.8720 |
| brier | 0.0944 |
| ece | 0.0910 |
| threshold | 0.2392 |
| precision | 0.8458 |
| recall | 0.6883 |
| f1 | 0.7589 |
| auprc_lift | 3.3960 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 72 |
| n_matched | 35 |
| detection_rate | 0.9722 |
| false_alarm_windows | 37 |
| mean_lead_time | -2.0286 |
| median_lead_time | -1.0000 |
| mean_onset_error | 2.9714 |
| mean_abs_onset_error | 2.9714 |
| mean_resolution_error | -3.9032 |
| mean_temporal_iou | 0.6688 |
| mean_duration_error | -7.1935 |
| premature_resolution_rate | 0.4000 |
| delayed_resolution_rate | 0.3143 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 10.4563 |
| predict_seconds | 0.6835 |
| rows | 3855 |
| throughput_rows_per_s | 5640.3246 |
| latency_ms_per_row | 0.1773 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:06:19.868010+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.