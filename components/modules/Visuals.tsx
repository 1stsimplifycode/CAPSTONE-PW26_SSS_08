/**
 * Primary visualisations for the module pages.
 *
 * Every chart here is drawn from an artifact the research pipeline wrote: either a
 * bounded preview of the module's own output table, or the resolved metrics the exporter
 * looked up. Nothing is simulated, and a module whose artifact is absent renders a
 * statement to that effect rather than an empty axis — an empty chart reads as a result
 * of zero, which is a different claim from "not available".
 *
 * The `visual` key in the manifest picks the shape. Column names are resolved by the
 * spec below rather than declared per module, because the artifacts already have stable
 * column vocabularies and repeating them 32 times in the manifest would be 32 chances to
 * drift.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE CHART-DRAWING MACHINERY FOR EVERY MODULE PAGE.
 *
 * IDEA 1: EVERY CHART COMES FROM A REAL RESULT FILE. Nothing is simulated, nothing is
 * generated for display. And a module with no result file shows a SENTENCE rather than an
 * empty chart -- for the reason stated: "an empty chart reads as a result of zero".
 *
 * IDEA 2, AND IT IS AN ELEGANT PIECE OF DESIGN: each module says only WHAT SHAPE of chart
 * it wants -- "bars", "line", "matrix". It does not say which columns to use.
 * Why not? Because the result files already use consistent column names. Making each of
 * the 32 modules repeat those names would be "32 chances to drift" -- 32 places where a
 * renamed column would silently break one chart.
 * So the column-picking rules live in ONE table below, and each module names a shape.
 */
import type { ModuleMetric, ModulePreview, ResearchModule } from '@/lib/moduleTypes';

// The description of one chart shape.
interface VisualSpec {
  /** Column holding the row label. First non-numeric column when absent. */
  // Sensible fallbacks throughout, so a spec need only say what is unusual about it.
  label?: string;
  /** Candidate value columns, in preference order. First numeric column when none hit. */
  // A LIST, in preference order -- so one spec can serve several files whose column is
  // named slightly differently, without needing a spec each.
  value?: string[];
  kind: 'bars' | 'line' | 'matrix' | 'split-metrics' | 'table' | 'metrics';
  /** Second series, drawn as a paler bar behind the first. */
  compare?: string[];
  // Whether the numbers are fractions (shown as percentages) or raw values.
  unit?: 'fraction' | 'raw';
  sort?: 'value' | 'none';
  /** Keep only rows where this column equals this value. */
  filter?: { column: string; value: string };
  /** Build the row label by joining these columns, when one alone repeats. */
  // For a file where the same name appears on several rows -- joining two columns makes
  // each label unique rather than showing four bars all called "gaussian".
  labelJoin?: string[];
}

// THE ONE TABLE. Every chart shape in the project, described once.
const VISUAL_SPEC: Record<string, VisualSpec> = {
  coverage_bars: {
    label: 'block',
    value: ['mean_non_null_fraction'],
    kind: 'bars',
    // A fraction, so it displays as a percentage.
    unit: 'fraction',
    // Sorted so the best-covered block leads.
    sort: 'value',
  },
  feature_table: { kind: 'table' },
  regime_bars: {
    label: 'regime_id',
    value: ['share'],
    // Two series: how common each mood is, against how often trouble occurred in it.
    compare: ['positive_rate'],
    kind: 'bars',
    unit: 'fraction',
  },
  baseline_bars: { label: 'model', value: ['auprc'], kind: 'bars', sort: 'value' },
  ablation_bars: { label: 'arm', value: ['auprc'], kind: 'bars', sort: 'value' },
  // The artifact holds several families at once, and the input-degradation family is
  // the one this module leads with; the rest are reachable in the research tables.
  // PLAIN ENGLISH: the robustness file contains several unrelated experiments. Charting
  // them together would invite a comparison between things that are not comparable, so the
  // chart shows one family -- and the note says where the rest are, so nothing is hidden.
  robustness_lines: {
    label: 'corruption',
    // Joined with the severity, so "gaussian" at four severities gives four distinct labels
    // rather than four bars with the same name.
    labelJoin: ['corruption', 'severity'],
    value: ['auprc'],
    kind: 'bars',
    // NOT sorted -- because severity has a natural order and sorting by value would
    // scramble the very progression the chart exists to show.
    sort: 'none',
    filter: { column: 'family', value: 'input' },
  },
  alignment_curve: {
    label: 'offset_sessions',
    value: ['auprc'],
    kind: 'line',
    // Again unsorted: the delay is the axis, and reordering it would destroy the curve.
    sort: 'none',
  },
  seed_spread: { label: 'arm', value: ['mean'], kind: 'bars', sort: 'value' },
  information_matrix: {
    label: 'block',
    // Unique contribution against total -- so the gap between them is visible, which is
    // exactly the redundancy story from the information decomposition.
    value: ['unique'],
    compare: ['total_auprc'],
    kind: 'bars',
    sort: 'value',
  },
  confusion: { kind: 'matrix' },
  reliability: { label: 'mean_pred', value: ['observed'], kind: 'line' },
  // The error taxonomy artifact is one row per scored instrument-day, so the split is
  // drawn from the resolved counts rather than from that row table.
  // PLAIN ENGLISH: that file has one row per day, which is far too many to chart. So this
  // shape draws from the counted totals instead -- an explicit exception, with its reason.
  error_split: { kind: 'split-metrics' },
  // These modules produce numbers rather than series, and say so rather than being forced
  // into a chart shape that would misrepresent them.
  combiner_compare: { kind: 'metrics' },
  attribution: { kind: 'metrics' },
  episode_stats: { kind: 'metrics' },
  tail_stats: { kind: 'metrics' },
  stat_row: { kind: 'metrics' },
  gate: { kind: 'metrics' },
  provenance: { kind: 'metrics' },
  media_gallery: { kind: 'metrics' },
  affect_distribution: {
    label: 'dimension',
    // The average with the spread behind it -- so a mean is never shown without some
    // indication of how much it varies.
    value: ['mean'],
    compare: ['std'],
    kind: 'bars',
  },
  not_measured: { kind: 'metrics' },

  // Scenario Lab. A scenario table is one row per condition, so the label column is the
  // scenario id in every case and only the value column differs.
  scenario_bars: {
    label: 'scenario_id',
    value: ['risk_mean'],
    kind: 'bars',
    sort: 'none',
  },
  // Filtered to the market family: the transaction rows in the same artifact are a
  // different quantity on a different corpus, and charting them together would invite a
  // comparison that means nothing.
  // PLAIN ENGLISH: the same file holds two kinds of number measured on two different
  // datasets. Drawing them on one axis would put them side by side as though they could be
  // compared. They cannot, so only one family is charted.
  scenario_money: {
    label: 'scenario_id',
    value: ['amount_inr'],
    kind: 'bars',
    sort: 'value',
    filter: { column: 'family', value: 'market' },
  },
  uncertainty_intervals: {
    label: 'scenario_id',
    value: ['estimate'],
    kind: 'bars',
    sort: 'value',
  },
  scenario_ablation: {
    label: 'scenario_id',
    labelJoin: ['subset', 'scenario_id'],
    value: ['delta_risk_mean'],
    kind: 'bars',
    sort: 'none',
  },
  scenario_robustness: {
    label: 'scenario_id',
    value: ['delta_mean'],
    kind: 'bars',
    sort: 'value',
  },
};

// A pattern matching a number, including scientific notation like "1.2e-5".
const NUMERIC = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;

// Is this a number? Values arrive from files as either real numbers or text, so both are
// accepted -- but text is checked strictly rather than being coerced hopefully.
function isNumeric(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v);
  return typeof v === 'string' && v.trim() !== '' && NUMERIC.test(v.trim());
}

// Turn a value into a number, or null.
function num(v: unknown): number | null {
  // Infinity and NaN become null rather than being drawn as monstrous bars.
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && NUMERIC.test(v.trim())) return Number(v);
  return null;
}

// Find a column by name.
function columnIndex(preview: ModulePreview, name?: string): number {
  if (!name) return -1;
  return preview.columns.findIndex((c) => c === name);
}

/** Pick the value column: the first named candidate present, else the widest numeric. */
function pickValue(preview: ModulePreview, candidates?: string[]): number {
  // The named preferences first, in order.
  for (const c of candidates ?? []) {
    const i = columnIndex(preview, c);
    if (i >= 0) return i;
  }
  // And a sensible fallback: the first column that contains numbers at all. So a file with
  // an unexpected column name still charts something rather than nothing.
  for (let i = 0; i < preview.columns.length; i += 1) {
    if (preview.rows.some((r) => isNumeric(r[i]))) return i;
  }
  return -1;
}

// Pick the label column.
function pickLabel(preview: ModulePreview, named?: string, avoid = -1): number {
  const i = columnIndex(preview, named);
  if (i >= 0) return i;
  // The fallback: the first column that is NOT entirely numeric -- because a column of
  // numbers makes poor labels. And `avoid` keeps it from picking the value column itself.
  for (let j = 0; j < preview.columns.length; j += 1) {
    if (j === avoid) continue;
    if (!preview.rows.every((r) => isNumeric(r[j]))) return j;
  }
  return 0;
}

// Format a number for display.
function fmt(v: number, unit?: 'fraction' | 'raw'): string {
  // A fraction becomes a percentage.
  if (unit === 'fraction') return `${(v * 100).toFixed(1)}%`;
  // PRECISION FOLLOWING MAGNITUDE, the same principle as the share labels: big numbers get
  // no decimals, ordinary ones three, small ones four -- so a tiny value is not rounded
  // away to zero and a large one does not carry meaningless digits.
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

// The "nothing here" block.
export function NotAvailable({ what, why }: { what: string; why?: string }) {
  return (
    <div className="viz viz--empty">
      <strong>{what} is not available in this build.</strong>
      <p>
        {why ??
          // The default explanation restates the project's promise: nothing is generated on
          // request, so a missing file genuinely means a missing result -- and it is shown
          // as absent "rather than drawn from nothing".
          'This view renders exported artifacts only. Nothing is generated at request ' +
            'time, so an absent artifact is shown as absent rather than drawn from ' +
            'nothing.'}
      </p>
    </div>
  );
}

/* -- primitives ---------------------------------------------------------------------- */

// One row of a chart.
interface Row {
  label: string;
  value: number;
  compare: number | null;
}

// Turn a data preview into chart rows, following the spec.
function rowsFrom(preview: ModulePreview, spec: VisualSpec, limit = 14): Row[] {
  const vi = pickValue(preview, spec.value);
  // No numeric column at all: no chart. The caller falls back to showing the numbers.
  if (vi < 0) return [];
  const li = pickLabel(preview, spec.label, vi);
  const ci = spec.compare ? pickValue(preview, spec.compare) : -1;
  const fi = spec.filter ? columnIndex(preview, spec.filter.column) : -1;
  const joinIdx = (spec.labelJoin ?? [])
    .map((c) => columnIndex(preview, c))
    // Only the columns that actually exist, so a missing one degrades the label rather
    // than producing "undefined · gaussian".
    .filter((i) => i >= 0);

  const rows: Row[] = [];
  for (const r of preview.rows) {
    // The filter, where the spec has one.
    if (fi >= 0 && String(r[fi]) !== spec.filter!.value) continue;
    const v = num(r[vi]);
    // A row with no usable value is SKIPPED, not drawn as zero.
    if (v === null) continue;
    rows.push({
      label: joinIdx.length
        // Joined with a middle dot, which reads clearly and cannot be confused with a
        // minus sign or a decimal point.
        ? joinIdx.map((i) => String(r[i] ?? '')).join(' · ')
        : String(r[li] ?? ''),
      value: v,
      // `ci !== vi` prevents the same column being drawn twice as its own comparison.
      compare: ci >= 0 && ci !== vi ? num(r[ci]) : null,
    });
  }
  if (spec.sort === 'value') rows.sort((a, b) => b.value - a.value);
  // A cap, so one enormous file cannot produce a chart with four hundred bars.
  return rows.slice(0, limit);
}

// Horizontal bars.
export function BarChart({
  rows,
  unit,
  valueLabel,
  compareLabel,
}: {
  rows: Row[];
  unit?: 'fraction' | 'raw';
  valueLabel: string;
  compareLabel?: string;
}) {
  // The scale spans both series, so the two are directly comparable. And zero is always
  // included, so a chart of values between 0.80 and 0.82 does not exaggerate the difference
  // into something dramatic.
  const max = Math.max(...rows.map((r) => Math.max(r.value, r.compare ?? 0)), 0);
  const min = Math.min(...rows.map((r) => Math.min(r.value, r.compare ?? 0)), 0);
  const span = max - min || 1;
  return (
    <div className="viz">
      {/* A LEGEND NAMING THE ACTUAL COLUMNS -- so a reader knows exactly which quantity each
          bar represents, rather than being left to infer it. */}
      <div className="viz__legend">
        <span className="viz__key viz__key--primary" /> {valueLabel}
        {compareLabel ? (
          <>
            <span className="viz__key viz__key--compare" /> {compareLabel}
          </>
        ) : null}
      </div>
      <ul className="vizBars">
        {rows.map((r) => (
          <li key={`${r.label}-${r.value}`} className="vizBars__row">
            {/* `title` gives the full label on hover, for one too long to fit. */}
            <span className="vizBars__label" title={r.label}>
              {r.label}
            </span>
            <span className="vizBars__track">
              {/* The comparison bar drawn FIRST, so it sits behind the primary one. */}
              {r.compare !== null ? (
                <span
                  className="vizBars__fill vizBars__fill--compare"
                  style={{ width: `${(Math.abs(r.compare - min) / span) * 100}%` }}
                />
              ) : null}
              <span
                className="vizBars__fill"
                style={{ width: `${(Math.abs(r.value - min) / span) * 100}%` }}
              />
            </span>
            {/* And the number printed, so the chart is never only an impression. */}
            <span className="vizBars__value">{fmt(r.value, unit)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// A line chart.
export function LineChart({
  rows,
  valueLabel,
}: {
  rows: Row[];
  valueLabel: string;
}) {
  // A "line" through one point is not a line. Fall back to bars rather than drawing a
  // single dot and calling it a trend.
  if (rows.length < 2) return <BarChart rows={rows} valueLabel={valueLabel} />;
  const w = 640;
  const h = 200;
  const pad = 28;
  const values = rows.map((r) => r.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (rows.length - 1)) * (w - pad * 2);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const path = rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r.value)}`).join(' ');

  return (
    <div className="viz">
      <div className="viz__legend">
        <span className="viz__key viz__key--primary" /> {valueLabel}
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="vizLine"
        role="img"
        // A description including the count, so a listening reader learns the shape of the
        // chart rather than merely that one exists.
        aria-label={`${valueLabel} across ${rows.length} conditions`}
      >
        {/* Both axes drawn, so the chart has a frame to read against. */}
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="vizLine__axis" />
        <line x1={pad} y1={pad} x2={pad} y2={h - pad} className="vizLine__axis" />
        <path d={path} className="vizLine__path" />
        {rows.map((r, i) => (
          // A dot at every real data point -- so it is visible where the measurements
          // actually are, rather than only the line between them.
          <circle key={`${r.label}-${i}`} cx={x(i)} cy={y(r.value)} r={3.5}>
            {/* The browser's own hover text, giving the label and value with no JavaScript. */}
            <title>{`${r.label}: ${fmt(r.value)}`}</title>
          </circle>
        ))}
        {/* The top and bottom values labelled, so the vertical scale is readable. */}
        <text x={pad} y={pad - 8} className="vizLine__tick">
          {fmt(max)}
        </text>
        <text x={pad} y={h - pad + 16} className="vizLine__tick">
          {fmt(min)}
        </text>
      </svg>
      {/* And the first and last labels beneath, bounding the horizontal axis. */}
      <div className="viz__axis">
        <span>{rows[0].label}</span>
        <span>{rows[rows.length - 1].label}</span>
      </div>
    </div>
  );
}

// A grid of numbers, shaded by size -- a "heat map".
export function MatrixGrid({ preview }: { preview: ModulePreview }) {
  // Every column that contains numbers.
  const numericCols = preview.columns
    .map((c, i) => ({ c, i }))
    .filter(({ i }) => preview.rows.some((r) => isNumeric(r[i])));
  const labelIdx = pickLabel(preview, undefined, numericCols[0]?.i ?? -1);
  // One shared scale across the WHOLE grid, so a cell's shade means the same thing
  // wherever it appears. Shading each column separately would make a small value in one
  // column look as dark as a large one in another.
  const all = preview.rows.flatMap((r) =>
    numericCols.map(({ i }) => num(r[i]) ?? 0),
  );
  const max = Math.max(...all, 1);

  return (
    <div className="viz">
      <div className="tableWrap">
        <table className="vizMatrix">
          <thead>
            <tr>
              {/* An empty corner cell above the row labels. */}
              <th />
              {numericCols.map(({ c }) => (
                <th key={c} className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.slice(0, 12).map((r, ri) => (
              <tr key={`${String(r[labelIdx])}-${ri}`}>
                {/* `scope="row"` so screen-reader software pairs each value with its row
                    name -- essential in a grid, where a bare number means nothing. */}
                <th scope="row">{String(r[labelIdx] ?? '')}</th>
                {numericCols.map(({ i, c }) => {
                  const v = num(r[i]) ?? 0;
                  return (
                    <td
                      key={c}
                      className="num vizMatrix__cell"
                      // A custom property carrying the shade, so the styling can colour the
                      // cell without any of the colour logic living in this file.
                      style={{ ['--cell' as string]: String(Math.abs(v) / max) }}
                    >
                      {/* THE NUMBER IS ALWAYS PRINTED, not only the shade. So the grid is
                          readable in greyscale, when printed, and by anybody who cannot
                          distinguish the colours. */}
                      {fmt(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// A single bar divided into parts.
export function SplitBar({ rows }: { rows: Row[] }) {
  // `|| 1` guards against everything being zero, which would divide by nothing.
  const total = rows.reduce((s, r) => s + r.value, 0) || 1;
  return (
    <div className="viz">
      <div className="vizSplit">
        {rows.map((r, i) => (
          <span
            key={r.label}
            className="vizSplit__seg"
            data-seg={i}
            style={{ width: `${(r.value / total) * 100}%` }}
            // Hover text on each segment, so a thin one can still be identified.
            title={`${r.label}: ${fmt(r.value)}`}
          />
        ))}
      </div>
      <ul className="vizSplit__legend">
        {rows.map((r, i) => (
          <li key={r.label}>
            {/* THE LEGEND CARRIES BOTH the raw count and the percentage. A reader who wants
                the proportion gets it; one who wants the actual number gets that too. */}
            <span className="viz__key" data-seg={i} /> {r.label}{' '}
            <strong>{fmt(r.value)}</strong>{' '}
            <span className="muted">{((r.value / total) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// A sample of a raw data file.
export function TablePreview({
  preview,
  limit = 12,
}: {
  preview: ModulePreview;
  limit?: number;
}) {
  return (
    <div className="viz">
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              {preview.columns.map((c) => (
                // Columns whose names suggest identifiers are left-aligned; everything else
                // is treated as numeric and right-aligned, so figures line up.
                <th key={c} className={c.match(/id|name|class|feature|arm/) ? '' : 'num'}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.slice(0, limit).map((r, ri) => (
              <tr key={ri}>
                {r.map((cell, ci) => (
                  <td key={ci} className={isNumeric(cell) ? 'num' : ''}>
                    {/* Numbers are formatted consistently; anything else is shown as it is,
                        with `?? ''` turning a missing cell into a blank rather than the
                        word "null". */}
                    {isNumeric(cell) ? fmt(num(cell)!) : String(cell ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="viz__note muted small">
        {/* THE TRUNCATION ANNOUNCED WITH THE REAL TOTAL, and the FILE PATH given -- so a
            reader knows they are seeing a sample, how large the whole thing is, and exactly
            where to find it. */}
        {preview.truncated
          ? `First ${Math.min(limit, preview.rows.length)} of ${preview.total_rows.toLocaleString()} rows`
          : `${preview.total_rows.toLocaleString()} rows`}{' '}
        from <code>{preview.path}</code>
      </p>
    </div>
  );
}

/** Metrics as a chart when a metric page is the honest primary visualisation. */
export function MetricBars({ metrics }: { metrics: ModuleMetric[] }) {
  const rows = metrics
    .filter((m) => typeof m.value === 'number' && m.value !== null)
    .map((m) => ({
      label: m.label,
      // Sized by magnitude, so a negative value still draws a visible bar...
      value: Math.abs(m.value as number),
      compare: null,
      // ...while the DISPLAY keeps its sign, so the reader sees the true value.
      display: m.display ?? '',
    }));
  if (rows.length === 0) {
    return (
      <NotAvailable
        what="A chartable value"
        // A precise explanation: this module reports text and status rather than numbers.
        // That is a fact about the module, not a failure -- and the note points the reader
        // to where everything it did produce can be found.
        why="This module reports text and status rather than a numeric series. The
        research view carries every field it produced."
      />
    );
  }
  const max = Math.max(...rows.map((r) => r.value)) || 1;
  return (
    <div className="viz">
      <ul className="vizBars">
        {rows.map((r) => (
          <li key={r.label} className="vizBars__row">
            <span className="vizBars__label" title={r.label}>
              {r.label}
            </span>
            <span className="vizBars__track">
              <span
                className="vizBars__fill"
                style={{ width: `${(r.value / max) * 100}%` }}
              />
            </span>
            {/* The pre-formatted display value, complete with its sign and units. */}
            <span className="vizBars__value">{r.display}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* -- feature-block strip -------------------------------------------------------------- */

/** Order the block strip reads in: raw descriptors first, then what is derived from them. */
// A meaningful order rather than alphabetical: the raw observations first, then the things
// built on top of them. So the strip reads as a story rather than a list.
const BLOCK_ORDER = ['market', 'microstructure', 'regime', 'propagation'];

/**
 * The feature-block strip: which blocks this module touches, how much each contributes,
 * and how often each disagrees with the combined decision.
 *
 * Drawn only when the module's own artifacts carry a per-block row. A strip invented for
 * modules that do not measure one would make the interface look like it had measured
 * something it did not.
 */
// PLAIN ENGLISH: the strip appears only where the module genuinely measured per-block
// contributions. Drawing an empty one everywhere else would make the interface look as
// though it had measured something it never did -- the same principle as the empty chart,
// applied to a whole component.
export function BlockStrip({ module: mod }: { module: ResearchModule }) {
  // Find a result file that actually has a per-block breakdown.
  const preview = mod.research.previews.find((p) => p.columns.includes('block'));
  // No such file: no strip at all.
  if (!preview) return null;

  const keyIdx = preview.columns.indexOf('block');
  // Three possible contribution columns, in preference order -- so one component serves
  // several different result files.
  const contribIdx = ['unique', 'mean_non_null_fraction', 'total_auprc'].reduce(
    (found, c) => (found >= 0 ? found : preview.columns.indexOf(c)),
    -1,
  );
  const conflictIdx = preview.columns.indexOf('conflict_rate');
  if (keyIdx < 0 || contribIdx < 0) return null;

  const rows = preview.rows
    .map((r) => ({
      name: String(r[keyIdx] ?? ''),
      contribution: num(r[contribIdx]) ?? 0,
      // The disagreement rate, where the file carries one.
      conflict: conflictIdx >= 0 ? num(r[conflictIdx]) : null,
    }))
    .sort((a, b) => {
      // Sorted into the meaningful order above. An unrecognised block gets 99, so it sorts
      // to the end rather than crashing or jumping to the front.
      const ia = BLOCK_ORDER.indexOf(a.name);
      const ib = BLOCK_ORDER.indexOf(b.name);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  if (rows.length === 0) return null;

  const maxContribution = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9);
  const contributionLabel = preview.columns[contribIdx];

  return (
    <section className="blockStrip">
      <h3>Evidence blocks in play</h3>
      <ul className="blockStrip__list">
        {rows.map((r) => (
          <li key={r.name} className="blockStrip__row">
            <span className="blockStrip__name">{r.name}</span>
            {/* Hover text naming the actual column, so the bar's meaning is always reachable. */}
            <span className="blockStrip__track" title={`${contributionLabel}: ${fmt(r.contribution)}`}>
              <span
                className="blockStrip__fill"
                style={{
                  width: `${(Math.abs(r.contribution) / maxContribution) * 100}%`,
                }}
              />
            </span>
            <span className="blockStrip__value">{fmt(r.contribution)}</span>
            {r.conflict !== null ? (
              // THE DISAGREEMENT RATE, shown right beside the contribution. So a block that
              // contributes a lot AND frequently disagrees with the final verdict is visible
              // as such -- which is exactly the situation worth investigating.
              <span className="blockStrip__conflict" title="rate of disagreement with the combined decision">
                disagrees {(r.conflict * 100).toFixed(1)}%
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="viz__note muted small">
        {/* THE NOTE NAMES THE COLUMN AND THE FILE, then defines the disagreement rate
            precisely: the share of rows where that block's own score falls on the opposite
            side of the threshold from the combined score. A definition a reader could check
            for themselves, rather than a term they have to accept. */}
        Bar length is <code>{contributionLabel}</code> from{' '}
        <code>{preview.path}</code>. Where a disagreement rate is shown it is the share of
        rows on which that block&apos;s own score falls on the opposite side of the
        operating threshold from the combined score.
      </p>
    </section>
  );
}

/* -- dispatch ------------------------------------------------------------------------ */

/**
 * The module's own generated figure is preferred over a redrawn chart wherever one
 * exists: it is the artifact the paper cites, and redrawing it in the browser would
 * create a second rendering of the same numbers that could drift from the first.
 */
// PLAIN ENGLISH: where the research pipeline produced a real figure, THAT is shown -- not a
// browser-drawn version of the same numbers. Because the pipeline's figure is the one the
// paper cites, and a second rendering would be a second thing that could drift.
/**
 * Whether this module has a chart, or only numbers.
 *
 * The caller uses it to avoid rendering the same figures twice: a module whose primary
 * visual falls back to bars-of-its-own-metrics would otherwise show the metric grid and a
 * bar chart of the identical values one above the other, which reads as two results.
 */
// The observation from the module shell again: the same numbers drawn twice reads as two
// pieces of evidence. This is the check that prevents it.
export function hasChart(mod: ResearchModule): boolean {
  const spec = VISUAL_SPEC[mod.product.visual];
  // No spec, or a numbers-only module: no chart.
  if (!spec || spec.kind === 'metrics') return false;
  if (spec.kind === 'split-metrics') {
    // A split bar needs more than one positive part -- a single segment filling the whole
    // bar shows nothing that the number alone did not.
    return mod.product.metrics.filter(
      (m) => typeof m.value === 'number' && (m.value as number) > 0,
    ).length > 1;
  }
  return mod.research.previews.length > 0;
}

// THE DISPATCHER: pick and draw the right chart for a module.
export function ModuleVisual({ module: mod }: { module: ResearchModule }) {
  // An unknown shape falls back to showing the numbers -- never to nothing.
  const spec = VISUAL_SPEC[mod.product.visual] ?? { kind: 'metrics' as const };

  if (spec.kind === 'split-metrics') {
    const rows = mod.product.metrics
      .filter((m) => typeof m.value === 'number' && (m.value as number) > 0)
      .slice(1) // the first metric is the total these parts divide
      // PLAIN ENGLISH: the first number is the TOTAL. Including it would draw a segment
      // equal to the whole bar alongside the parts that make it up -- double-counting the
      // total as though it were one of its own components.
      .map((m) => ({ label: m.label, value: m.value as number, compare: null }));
    return rows.length ? (
      <SplitBar rows={rows} />
    ) : (
      <MetricBars metrics={mod.product.metrics} />
    );
  }

  // A module's outputs are often several tables at different grains. Prefer the one that
  // actually carries the columns this visual asks for; falling through to the first
  // output would chart the raw per-row table where a summary was meant.
  // PLAIN ENGLISH: a module may write several files -- one summary, one with every row.
  // Taking the first would sometimes chart ten thousand raw rows where a four-row summary
  // was intended. So it looks for the file that HAS the columns this chart needs.
  const previews = mod.research.previews;
  const preview =
    previews.find(
      // First choice: a file with BOTH the label column and a value column.
      (p) =>
        (!spec.label || p.columns.includes(spec.label)) &&
        (spec.value ?? []).some((v) => p.columns.includes(v)),
    ) ??
    // Second choice: at least a value column.
    previews.find((p) => (spec.value ?? []).some((v) => p.columns.includes(v))) ??
    // Last resort: whatever there is.
    previews[0];

  // No usable file: show the numbers.
  if (spec.kind === 'metrics' || !preview) {
    return <MetricBars metrics={mod.product.metrics} />;
  }
  if (spec.kind === 'table') return <TablePreview preview={preview} />;
  if (spec.kind === 'matrix') return <MatrixGrid preview={preview} />;

  // A line chart can carry more points than a bar chart, since lines stay readable where
  // forty labelled bars would not.
  const rows = rowsFrom(preview, spec, spec.kind === 'line' ? 40 : 14);
  // Nothing usable came out: fall back to the numbers rather than an empty chart.
  if (rows.length === 0) return <MetricBars metrics={mod.product.metrics} />;

  // The legend labels taken from the ACTUAL column names -- so the legend can never
  // describe a different column from the one drawn.
  const vi = pickValue(preview, spec.value);
  const valueLabel = preview.columns[vi] ?? 'value';
  const ci = spec.compare ? pickValue(preview, spec.compare) : -1;
  const compareLabel = ci >= 0 && ci !== vi ? preview.columns[ci] : undefined;

  if (spec.kind === 'line') return <LineChart rows={rows} valueLabel={valueLabel} />;
  return (
    <BarChart
      rows={rows}
      unit={spec.unit}
      valueLabel={valueLabel}
      compareLabel={compareLabel}
    />
  );
}
