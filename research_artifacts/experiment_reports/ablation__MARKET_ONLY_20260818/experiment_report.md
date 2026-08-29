# Experiment report: ablation__MARKET_ONLY_20260818

**Hypothesis.** arm MARKET_ONLY vs FULL

**Arm.** `MARKET_ONLY` | blocks: market | combiner: `regime_corrected`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.8160 |
| auroc | 0.8699 |
| brier | 0.0903 |
| ece | 0.0216 |
| threshold | 0.2611 |
| precision | 0.7810 |
| recall | 0.6830 |
| f1 | 0.7287 |
| auprc_lift | 3.3463 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 75 |
| n_matched | 29 |
| detection_rate | 0.8056 |
| false_alarm_windows | 46 |
| mean_lead_time | -8.3103 |
| median_lead_time | -8.0000 |
| mean_onset_error | 12.2759 |
| mean_abs_onset_error | 13.1724 |
| mean_resolution_error | 3.0833 |
| mean_temporal_iou | 0.4737 |
| mean_duration_error | -8.7083 |
| premature_resolution_rate | 0.0690 |
| delayed_resolution_rate | 0.7586 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 2.4498 |
| predict_seconds | 0.1278 |
| rows | 3855 |
| throughput_rows_per_s | 30161.4872 |
| latency_ms_per_row | 0.0332 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:05:08.580610+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.