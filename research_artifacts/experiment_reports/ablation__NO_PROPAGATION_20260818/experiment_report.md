# Experiment report: ablation__NO_PROPAGATION_20260818

**Hypothesis.** cross-instrument propagation improves early detection (RQ7)

**Arm.** `NO_PROPAGATION` | blocks: text, image, audio, video, market, microstructure, regime | combiner: `regime_corrected`

**Status.** OK

## Detection

| metric | value |
|---|---|
| n | 3855.0000 |
| positive_rate | 0.2438 |
| auprc | 0.9407 |
| auroc | 0.9648 |
| brier | 0.0698 |
| ece | 0.1178 |
| threshold | 0.3531 |
| precision | 0.9394 |
| recall | 0.8734 |
| f1 | 0.9052 |
| auprc_lift | 3.8577 |

## Temporal

| metric | value |
|---|---|
| n_true_windows | 36 |
| n_pred_windows | 57 |
| n_matched | 33 |
| detection_rate | 0.9167 |
| false_alarm_windows | 24 |
| mean_lead_time | -8.3636 |
| median_lead_time | -10.0000 |
| mean_onset_error | 12.1818 |
| mean_abs_onset_error | 12.9697 |
| mean_resolution_error | 4.1364 |
| mean_temporal_iou | 0.4105 |
| mean_duration_error | -6.4545 |
| premature_resolution_rate | 0.0303 |
| delayed_resolution_rate | 0.6061 |

## Operational

| metric | value |
|---|---|
| fit_seconds | 11.7833 |
| predict_seconds | 0.6474 |
| rows | 3855 |
| throughput_rows_per_s | 5954.9288 |
| latency_ms_per_row | 0.1679 |
| peak_memory_mb | None |

---

Generated 2026-08-18T18:07:36.322992+00:00. Synthetic-episode evaluation; see `docs/LIMITATIONS.md` L-04.