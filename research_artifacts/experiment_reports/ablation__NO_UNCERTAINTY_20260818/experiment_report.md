# Experiment report: ablation__NO_UNCERTAINTY_20260818

**Hypothesis.** uncertainty-aware weighting reduces false positives (RQ8)

**Arm.** `NO_UNCERTAINTY` | blocks: market, microstructure, regime, propagation | combiner: `static_attention`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.9480 |
| auroc | 0.9673 |
| brier | 0.1043 |
| ece | 0.1934 |
| threshold | 0.3026 |
| precision | 0.9455 |
| recall | 0.8681 |
| f1 | 0.9052 |
| auprc_lift | 3.8879 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 42 |
| n_matched | 17 |
| detection_rate | 0.4722 |
| false_alarm_windows | 25 |
| mean_lead_time | -8.1176 |
| median_lead_time | -8.0000 |
| mean_onset_error | 12.2353 |
| mean_abs_onset_error | 13.0588 |
| mean_resolution_error | -0.1429 |
| mean_temporal_iou | 0.4292 |
| mean_duration_error | -12.3571 |
| premature_resolution_rate | 0.2353 |
| delayed_resolution_rate | 0.5294 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 13.3897 |
| predict_seconds | 0.7199 |
| rows | 3855 |
| throughput_rows_per_s | 5354.5407 |
| latency_ms_per_row | 0.1868 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:07:21.509239+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.