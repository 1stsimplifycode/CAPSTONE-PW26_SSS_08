<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# STATS-08 — Episode and event statistics

| | |
|---|---|
| Category | `STATS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-04`, `L-12` |

## Purpose

Counts, durations, intensities and per-instrument distribution of the injected integrity-risk episodes that every detection result is measured against.

## Research question

> What is the effective sample of episodes, and is it large enough to support the effect sizes being claimed?

## Inputs

- `data/panel/episode_labels.parquet`

## Processing

Adapter: `scripts.stages.stats:episode_event_statistics`

Canonical implementation:

- `research/detection/episodes.py::GeneratorConfig`
- `research/detection/state.py::windows_from_frame`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/stats/08_episode_event_statistics/episode_summary.json`

## Dependencies

- none

## How to run

```bat
REM from anywhere
STATS\08_episode_event_statistics\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module STATS-08
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module STATS-08 --check
```

## Reproducibility

Every run appends a record to `logs/stats/stats_08.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Episodes are synthetic and injected into real price data (L-04). No result from them may be described as real-world manipulation detection.

See `docs/LIMITATIONS.md` for **L-04**, **L-12**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
