# helper.md — what every file in this folder is

**AEGIS-MARKET-STATISTICS** is the statistics-only carve-out of the AEGIS market-integrity
project: sixteen STATS modules that characterise the data, validate the risk model against
it, and report how much of any difference between configurations is real. It ships a
Python research pipeline, a small HTTP backend that executes modules on a slice you choose,
and a Next.js interface that reads both stored results and live runs.

The panel carries four evidence blocks — **market**, **microstructure**, **regime**,
**propagation** — and the vocabulary is the same everywhere: a *feature block*, one learner
per block, and a combination layer that weighs their calibrated scores.

> **Read this before trusting a stored number.** Every result under `outputs/`,
> `research_artifacts/` and `public/data/` was measured on the earlier 119-column panel and
> then filtered down to the rows that survive on the current 50-column one. The surviving
> values are the ones the original run produced and were not recomputed. Re-run the
> pipeline (`scripts/run_experiments.py`, then the STATS modules) before quoting any of them
> as a property of the four-block configuration. Live runs through the backend are computed
> on the current panel and are unaffected.

---

## Top level

| File | What it is |
|---|---|
| `helper.md` | This file. |
| `research_modules.yaml` | The single source of truth for all 16 STATS modules and the 16-week programme. `STATS/`, every `run.bat` and every module `README.md` are generated from it. Declares each module's canonical implementation, adapter, inputs, outputs, UI schema and status. |
| `package.json` | Frontend manifest: Next.js 15, React 19, the `dev`/`build`/`lint` scripts. |
| `package-lock.json` | Locked npm dependency tree. |
| `next.config.mjs` | Next.js configuration: static export behaviour and the backend proxy origin. |
| `next-env.d.ts` | Generated Next.js type shims. Do not edit. |
| `tsconfig.json` | TypeScript configuration and the `@/*` path alias. |
| `tsconfig.tsbuildinfo` | TypeScript incremental build cache. Regenerated; not source. |
| `eslint.config.mjs` | ESLint flat config for the frontend. |
| `pyproject.toml` | Python project metadata plus ruff/pytest configuration. |
| `requirements.txt` | Pinned Python dependencies (pandas, numpy, scikit-learn, pyarrow, duckdb …). |
| `run_dev.bat` | Starts the Python backend and the Next.js dev server together. |
| `run-demo-stats.bat` | Guided demonstration runner: checks the panel exists, then walks the STATS modules in order. |

## `research/` — the canonical implementations

No adapter, script or route reimplements a statistic. Everything numeric lives here.

### `research/core/`
| File | What it is |
|---|---|
| `contracts.py` | The bitemporal evidence contract: `EvidenceBlock`, `EvidenceRecord`, `Provenance`, `BitemporalStore`, `get_evidence`, `LeakageError`. Enforces that a query as of an earlier cutoff can never see later knowledge. |
| `jsonio.py` | Strict JSON writing for every published artifact — deterministic key order, no NaN. |
| `licensing.py` | Licence gates for data sources. An unverifiable licence defaults to UNKNOWN and is excluded from redistributable artifacts. |
| `manifest.py` | Reproducibility manifests: the versions, seeds and inputs a run must record to be repeatable. |
| `paths.py` | Canonical filesystem locations. The only place a path is hardcoded. |
| `progress.py` | Stage timing and the `Ticker` that survives a buffered pipe. |

### `research/data/`
| File | What it is |
|---|---|
| `dataset.py` | Panel assembly. Declares `FEATURE_BLOCKS`, `COVERAGE_FLAGS` and `ALL_FEATURES`; `build()` produces one row per (instrument, decision time) with every block attached; `attach_propagation()` merges the neighbour-stress block. |
| `pit.py` | Point-in-time record construction from the cash panel, stamped with event and knowledge times. |
| `universe.py` | Research universe construction, membership history and the survivorship guard that refuses a forward-looking list for a historical date. |

### `research/market/`
| File | What it is |
|---|---|
| `features.py` | `MARKET_FEATURES` and `MICROSTRUCTURE_PROXIES`, plus `coverage_report` and the register of quantities this source cannot express at all. |
| `returns.py` | The one return convention, enforced by a test rather than a comment. |
| `liquidity.py` | The liquidity state vector, its stress gate, and what the gate blames when it fires. |
| `arrival.py` | Trade-arrival intensity and whether a Poisson process can describe it. |
| `thresholds.py` | Distribution-free anomaly thresholds, set from a false-alarm budget declared before the data is seen. |

### `research/models/`
| File | What it is |
|---|---|
| `risk_model.py` | `AegisRiskModel`: one calibrated `BlockLearner` per feature block plus a combination layer. Also implements the early rule, where a single learner sees the union of the features. |
| `combiner.py` | `BlockCombiner`: the combination rules (`late`, `static_attention`, `uncertainty`, `regime_inherited`, `regime_corrected`, `early`) and the uncertainty calculation. Enforces that a zero-coverage block gets zero weight and that no evidence yields score 0.5 / uncertainty 1.0. **Reconstructed rather than carried over** — see the *Provenance note* below. |
| `baselines.py` | The honest comparison set: an unlearned z-score composite plus one learner per block. |

### `research/evaluation/`
| File | What it is |
|---|---|
| `ablations.py` | The 28 ablation arms as data: block arms, component arms and combination-rule arms, each with its hypothesis. |
| `experiment.py` | `ExperimentSpec` / `ExperimentResult` and `run()`: fit an arm, score it, write its report bundle. Blanks a removed block's columns *and* zeroes its coverage flag. |
| `metrics.py` | Detection, calibration and threshold metrics, the confusion matrix, and the error taxonomy that diagnoses missing evidence before model error. |
| `information.py` | Block information decomposition — unique against redundant contribution — and selective-risk analysis. |
| `robustness.py` | Perturbation families: noise, dropout, stale feeds, outliers and taking a block offline. |
| `temporal_analysis.py` | Lead-time frontier, per-block lead/lag, onset/peak/resolution scoring. |
| `multiseed.py` | Repeats arms across seeds and derives the noise floor a difference must clear. |

### The rest of `research/`
| File | What it is |
|---|---|
| `detection/episodes.py` | The synthetic episode generator (L-04) and the generator/detector separation that keeps its parameters invisible to any model. |
| `detection/state.py` | The temporal integrity-risk state machine. |
| `detection/count_events.py` | Count-based event detection and its dependency on the arrival model. |
| `regime/detection.py` | Market regime detection and its validation. |
| `propagation/graph.py` | Cross-instrument correlation graph and the `PROPAGATION_FEATURES` stress block. |
| `risk/gate.py` | The integrity risk gate and capital-consequence measurement. |
| `scenario/money.py` | Currency values, and the only form in which this project may state one. |
| `statistics/tests.py` | Cluster bootstraps, paired tests, multiple-comparison correction. |
| `statistics/power.py` | Empirical power analysis for clustered rare-event comparisons (L-12). |
| `xai/methods.py` | Permutation importance, occlusion, KernelSHAP, LIME, counterfactuals, integrated gradients, PDP/ICE/ALE — with each method's validity scope stated. |
| `xai/sanity.py` | XAI sanity checks: sparsity, model randomisation, cross-seed sign agreement. |
| `limitations/registry.py` | The limitations register: 15 limitations and 7 negative findings, each with its invalidated claims, forbidden phrasings and follow-up research questions. |
| `reference/__init__.py` | Namespace package for reference data helpers. |
| `*/__init__.py` | Package markers; `research/scenario/__init__.py` also carries the non-advisory notice. |

## `scripts/` — runners and adapters

| File | What it is |
|---|---|
| `run_module.py` | The dispatcher every `run.bat` calls. Resolves a module id to its adapter, enforces the protected-artifact guard (`--force`), writes a JSONL log and returns the documented exit code. |
| `run_experiments.py` | Runs every ablation arm end to end and writes the per-arm report bundles. |
| `run_multiseed.py` | Repeats arms across seeds for the significance analysis. |
| `run_robustness_generalization.py` | Runs the perturbation and generalisation grid. |
| `run_research_angles.py` | The runnable research angles: lead/lag, block information decomposition, lifecycle analysis. |
| `stages/__init__.py` | Shared adapter vocabulary: exit codes, `AnalysisResult`, `StageResult`, `metric`, `series`, `require`, `insufficient`. |
| `stages/live.py` | Cached readers for the panel, cash panel and universe, plus the slice helpers every live analysis shares. |
| `stages/stats.py` | The sixteen STATS adapters, in both their regenerating and live-analysis forms. Every function wraps canonical code; none reimplements a statistic. |

## `backend/` — the execution service

| File | What it is |
|---|---|
| `server.py` | The HTTP surface: a small explicit router with a body cap, origin and token checks. Run with `python -m backend.server`. |
| `service.py` | Orchestration: validates inputs against the declared schema, runs a module live or replays its stored artifact, and labels which of the two happened. |
| `registry.py` | Reads `research_modules.yaml` and derives every route, input schema, output schema and artifact source from the module it names. |
| `contract.py` | The response envelope every module endpoint returns, and the rules it must satisfy. |
| `__init__.py` | `BACKEND_VERSION`. |

## `STATS/` — the sixteen module directories

Each of `01_data_integrity_profile` … `16_multiseed_significance` holds:
- `README.md` — the module's question, canonical implementation, inputs, outputs and status.
- `run.bat` — a one-line call into `tools/aegis_module.bat`.

`STATS/run_all_stats.bat` runs them in order. All of it is generated from
`research_modules.yaml`; edit the manifest, not these files.

| Module | Question it answers |
|---|---|
| 01 data integrity profile | What does the assembled panel contain, and where is coverage thin? |
| 02 universe survivorship | Is the instrument universe point-in-time, and how did membership turn over? |
| 03 descriptive distributions | How do the features behave, and which are constant on this slice? |
| 04 market microstructure | What do the liquidity proxies show, and what is not measurable at all? |
| 05 regime statistics | How do sessions distribute across regimes? |
| 06 dependence propagation | How does movement propagate across instruments? |
| 07 tail extreme risk | How heavy are the tails, how deep the drawdowns? |
| 08 episode event statistics | How are the injected episodes distributed? |
| 09 leakage verification | Can information from after a decision time reach a feature? |
| 10 validation verification | What do the metrics say at a threshold you choose? |
| 11 calibration uncertainty | Are the scores calibrated at your chosen binning? |
| 12 error analysis | Where does the scoring fail, and what kind of failure is each? |
| 13 baseline comparison | Is this better than something simpler? |
| 14 ablation study | Which components carry the result? |
| 15 robustness generalization | What survives perturbation? |
| 16 multiseed significance | How much of a difference is seed noise? |

## `tools/`

| File | What it is |
|---|---|
| `aegis_module.bat` | The shared module runner every STATS `run.bat` delegates to: activates the venv, calls the dispatcher, maps the exit code to a readable outcome. |

## `app/` — Next.js routes

| File | What it is |
|---|---|
| `layout.tsx` | Root layout: chrome, mode script, the non-advisory footer. |
| `page.tsx` | Home: what the system does and what it covers. |
| `globals.css` | The entire stylesheet — tokens, layout, module surfaces, product surfaces, charts. |
| `markets/page.tsx` | Market overview across the tracked universe. |
| `instruments/[symbol]/page.tsx` | One security: price behaviour, risk assessment, evidence-block contributions, liquidity and foundation panels. |
| `stats/page.tsx` | The sixteen STATS modules as an index. |
| `stats/layout.tsx` | The module frame: navigation on the left, module on the right. |
| `stats/[slug]/page.tsx` | One module page. Resolves by route slug, index or module id. |
| `api/aegis/[...path]/route.ts` | Proxy to the Python backend, with a stored-artifact fallback that always says which it served. |
| `research/page.tsx` | Research-mode landing page and standing caveats. |
| `research/ablations/page.tsx` | Arms by AUPRC and the block information decomposition. |
| `research/artifacts/page.tsx` | The artifact inventory. |
| `research/claims/page.tsx` | The claim ledger, each claim with its evidence and scope. |
| `research/datasets/page.tsx` | Source provenance, block coverage and source licensing. |
| `research/experiments/page.tsx` | Research questions with their status, and the arm table. |
| `research/figures/page.tsx` | The figure explorer. |
| `research/limitations/page.tsx` | The limitations register. |
| `research/limitations/[id]/page.tsx` | One limitation in full, with its research questions. |
| `research/paper-lab/page.tsx` | How the paper package is produced and what it contains. |
| `research/reproducibility/page.tsx` | What reproduces bit-identically and what does not. |
| `research/statistics/page.tsx` | Calibration, significance and uncertainty sections. |
| `research/tables/page.tsx` | The generated table index. |
| `research/thresholds/page.tsx` | Every operating threshold and how it was derived. |
| `research/xai/page.tsx` | Explanation methods and their validity scopes. |

## `components/`

| File | What it is |
|---|---|
| `modules/ModuleLayout.tsx` | The frame every module page sits in, plus the module index list. |
| `modules/ModuleNav.tsx` | Left-hand navigation over all 16 modules and the research lab. |
| `modules/ModuleCard.tsx` | A module as a card in a list. |
| `modules/ModuleShell.tsx` | Assembles one module page: header, panels, block strip, figures, tables. |
| `modules/Panels.tsx` | The panels both experiences are assembled from. |
| `modules/Visuals.tsx` | Visual specs per series, the redraw fallbacks, and `BlockStrip` — which blocks a module touches and how much each contributes. |
| `run/ModuleRunner.tsx` | The interactive half of a module page: choose a slice, run it, read the result. |
| `run/Controls.tsx` | Renders the controls a module declares, from the schema the backend validates against. |
| `run/Result.tsx` | One backend response, rendered in both experiences. |
| `run/useRun.ts` | The request half of the run panel: state, POST, and the four outcomes. |
| `product/Bits.tsx` | Small shared pieces: `SignalBars`, `shareLabel`, figures, tones. |
| `product/RiskHeader.tsx` | The risk headline and its evidence dimensions. |
| `product/RiskProfile.tsx` | The risk-dimension strip and the evidence balance beneath it. |
| `product/DirectionStrip.tsx` | Observed price direction and the two clocks that matter. |
| `product/EventFeed.tsx` | Announcements and corporate actions for one issuer, merged. |
| `product/Evidence.tsx` | Evidence coverage and alignment summaries. |
| `product/Foundation.tsx` | The market-intelligence foundation panel. |
| `product/Liquidity.tsx` | The liquidity estimators panel. |
| `product/FinancialHealth.tsx` | Financial health, rendered as the absence it is. |
| `product/TerminalChart.tsx` | Candles, volume, RSI and MACD on a shared time axis. |
| `product/Search.tsx` | Instrument search. |
| `product/WatchButton.tsx` | Follow something for analysis. |
| `product/Disclosure.tsx` | Progressive disclosure, as one component used everywhere. |
| `research/AngleSections.tsx` | Renders the research-angle results, including block lead and lag. |
| `visualization/Sparkline.tsx` | Server-rendered SVG traces, bands, markers and horizontal bars. |
| `ui/Chrome.tsx` | Masthead, mode toggle, theme control, mode-aware navigation. |
| `ui/Primitives.tsx` | `StatCard`, `ScoreBar`, `NoData`, `Empty`, state colours. |
| `ui/NonAdvisoryNotice.tsx` | The non-advisory notice. |
| `ui/SubjectRegistrar.tsx` | Registers what a page is about so a mode switch carries it. |

## `lib/`

| File | What it is |
|---|---|
| `types.ts` | Core domain types: `FeatureBlock`, `RiskAssessment`, `EvidenceItem`, `CoverageSummary`, `BlockInfoRow`, claim and limitation records. |
| `moduleTypes.ts` | Module manifest types shared by server and client, and `CATEGORY_COPY`. |
| `modules.ts` | Server-only readers over the module bundles, and route-slug resolution. |
| `runTypes.ts` | Types for the run request and response envelope. |
| `data.ts` | Bundle readers for every `public/data/*.json` the interface consumes. |
| `product.ts` | The product data layer: backend first, stored snapshot second, and it says which. |
| `weeks.ts` | The weekly registry, read from the exported bundle. |
| `capabilities.ts` | Which capability each week unlocks. |
| `mode.tsx` | PRODUCT / RESEARCH mode context and the module-route pattern. |

## `tests/`

| File | What it is |
|---|---|
| `leakage/test_leakage_suite.py` | L1–L6: as-of retrieval, future shift, restatement, survivorship, coverage substitution (an absent block is excluded, never imputed), threshold provenance. A failure here invalidates dependent claims. |
| `week2/test_c4_thresholds.py` | Threshold-derivation tests. |
| `week2/conftest.py` | Fixtures for the week-2 tests. |

Run everything with `.venv/Scripts/python.exe -m pytest tests/ -q` — currently 25 passing.

## `data/` — inputs

| Path | What it is |
|---|---|
| `panel/market_dataset.{parquet,csv}` | **The modelling panel.** 16,558 rows × 50 columns: keys, decision and knowledge times, the four feature blocks, their coverage flags, episode labels and the split column. |
| `panel/cash_panel.{parquet,csv}` | The NSE daily cash panel: OHLC, volume, turnover, trades, with event and knowledge times. |
| `panel/episode_labels.{parquet,csv}` | The injected episode ground truth: state, phase, intensity, entry and exit. |
| `panel/universe.{parquet,csv}` | Point-in-time universe membership and its rebalance history. |
| `reference/liquidity_state.*` | The liquidity state vector per instrument-session. |
| `reference/realised_variance.*` | Realised variance reference series. |
| `reference/week2_thresholds.*`, `week2_overdispersion.*` | Frozen threshold and overdispersion references the week-2 tests check against. |

## Generated output

| Path | What it is |
|---|---|
| `outputs/stats/NN_*/` | Each STATS module's regenerated artifacts (CSV + JSON). 14 of 16 have stored output. |
| `outputs/stats/*.log` | Run logs for the longer modules. |
| `outputs/week2/` | Week-2 foundation summary. |
| `research_artifacts/experiments/` | `arm_definitions.csv`, `ablation_results.csv`, confidence intervals, statistics, and `per_row_<ARM>.{csv,parquet}` for the 8 surviving arms. |
| `research_artifacts/experiment_reports/ablation__<ARM>_<date>/` | Per-arm bundle: config, metrics, model summary, per-row scores, reproducibility manifest, and a markdown report. |
| `research_artifacts/statistics/` | Cross-cutting statistical artifacts: capital consequence, global importance, regime degeneracy, coverage and uncertainty bins, XAI sanity. |
| `research_artifacts/manifests/progress.log` | Pipeline progress log. |
| `logs/stats/stats_NN.jsonl` | One JSONL record per module run: status, exit code, message, outputs. |
| `public/data/*.json` | The bundles the interface reads: `modules`, `module_index`, `weeks`, `week_titles`, `market`, `universe`, `coverage`, `provenance`, `block_info`, `experiments`, `statistics`, `claims`, `limitations`, `figures`, `figures_index`, `tables_index`, `thresholds`, `reproducibility`, `research_angles`. |
| `public/data/*.csv` | Flat CSV mirrors of the same bundles (`<name>.csv` key/value, `<name>__rows.csv` the row table). |
| `public/figures/*.png` | The 40 generated figures the interface and paper package cite. Eleven were regenerated on the four-block panel (see *Figure provenance* below) and eleven more were removed because their subject was a block this project no longer carries. |

## Build and cache directories

`.next/` (Next.js build output), `.venv/` (the Python environment), `node_modules/`,
`.pytest_cache/` and any `__pycache__/` are all regenerated. None of them are source.

---

## Figure provenance

Figures are not just filtered by title: the stored PNGs were inspected, and every one whose
plotted content named a removed block was dealt with.

* **Regenerated from the cleaned artifacts** — `fig13_precision_recall`,
  `fig22_global_importance`, `figR07_seed_variability`, `figS_component_ablation`. The
  numbers are the ones the original runs produced for the arms and features that survive.
* **Redrawn** — `fig01_architecture`, which is a diagram rather than a measurement.
* **Recomputed live on the current panel** — `fig12b_regime_degeneracy` and the four
  `fig23_local_*` explanations. Their per-run inputs no longer exist, so the model was
  refitted on `market_dataset.parquet` and the figures redrawn from that fit. Their numbers
  therefore differ from the stored tables, which still describe the earlier run.
* **Deleted, with every citation removed** — `figL12_power_curve`,
  `figLC4_stage_importance`, `figLC5_signal_order`, `figR02_design_effect`,
  `figR11_sample_size_ladder` and `figS01`–`figS06`. Each plotted a quantity measured over
  media channels or corpora this project does not contain, and no clean source data
  remained from which to redraw them.

Recomputing `fig12b` doubled as a check on the reconstructed combiner: the inherited rule
reproduces a maximum weight difference against static attention of exactly 0.0, matching
the "verified below 1e-12" claim the ledger makes.

## Provenance note on `research/models/combiner.py`

This module is a **reimplementation**, not a file carried over from the parent AEGIS-MARKET
repository. It was rebuilt from its call sites and from the invariants the leakage suite
asserts. It satisfies every test in `tests/leakage/test_leakage_suite.py`, including both
L5 properties, and its API matches what `risk_model.py` and the ablation runner call — but
its weighting arithmetic was derived, not copied. If you need the parent repository's exact
arithmetic, compare against the combination layer there before relying on numbers this
version produces.

## Getting started

```bash
# Python side
.venv/Scripts/python.exe -m pytest tests/ -q          # 25 tests
.venv/Scripts/python.exe scripts/run_module.py --list # every module and its status
.venv/Scripts/python.exe scripts/run_module.py --module STATS-01
.venv/Scripts/python.exe -m backend.server            # the execution service

# Frontend
npm run build                                         # typecheck + static build
run_dev.bat                                           # backend + dev server together
```
