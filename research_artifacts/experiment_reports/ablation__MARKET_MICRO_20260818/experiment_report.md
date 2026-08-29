# Experiment report: ablation__MARKET_MICRO_20260818

**Hypothesis.** arm MARKET_MICRO vs FULL

**Arm.** `MARKET_MICRO` | blocks: market, microstructure | combiner: `regime_corrected`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.8168 |
| auroc | 0.8703 |
| brier | 0.0903 |
| ece | 0.0220 |
| threshold | 0.2557 |
| precision | 0.7722 |
| recall | 0.6851 |
| f1 | 0.7260 |
| auprc_lift | 3.3496 |

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
| fit_seconds | 2.8351 |
| predict_seconds | 0.1645 |
| rows | 3855 |
| throughput_rows_per_s | 23431.1465 |
| latency_ms_per_row | 0.0427 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:05:12.466434+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.