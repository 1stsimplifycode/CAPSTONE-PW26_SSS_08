# Experiment report: ablation__FULL_20260818

**Hypothesis.** the complete evidence stack detects injected integrity episodes better than any subset

**Arm.** `FULL` | blocks: market, microstructure, regime, propagation | combiner: `regime_corrected`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.9412 |
| auroc | 0.9651 |
| brier | 0.0713 |
| ece | 0.1227 |
| threshold | 0.3510 |
| precision | 0.9394 |
| recall | 0.8734 |
| f1 | 0.9052 |
| auprc_lift | 3.8598 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 56 |
| n_matched | 33 |
| detection_rate | 0.9167 |
| false_alarm_windows | 23 |
| mean_lead_time | -8.4545 |
| median_lead_time | -10.0000 |
| mean_onset_error | 12.3939 |
| mean_abs_onset_error | 13.1818 |
| mean_resolution_error | 4.0476 |
| mean_temporal_iou | 0.3913 |
| mean_duration_error | -6.6190 |
| premature_resolution_rate | 0.0303 |
| delayed_resolution_rate | 0.5758 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 30.1375 |
| predict_seconds | 1.4520 |
| rows | 3855 |
| throughput_rows_per_s | 2654.8963 |
| latency_ms_per_row | 0.3767 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:02:48.530131+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.