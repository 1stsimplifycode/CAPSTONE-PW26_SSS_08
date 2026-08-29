import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { Caveat, NoData, StatCard } from '@/components/ui/Primitives';

export const dynamic = 'force-static';

export const metadata = {
  title: 'Risk thresholds — AEGIS-Statistics',
  description:
    'Every threshold that turns a number into a decision, what it is set to, and the ' +
    'rule that set it.',
};

/**
 * Where each threshold in the system comes from.
 *
 * This page computes nothing. `public/data/thresholds.json` is assembled from artifacts
 * that already exist — the Week 2 conformal fit, the FULL experiment bundle, the STATS-12
 * provenance log, the count-event summary and the `GatePolicy` dataclass defaults — and
 * every row carries the file it was read from. If a number here is wrong, it is wrong in
 * the artifact, and the `source` line says which one to open.
 *
 * Read with `readFile` rather than through `lib/data`'s `getBundle`, following the
 * pattern in `lib/capabilities.ts`: this bundle's payload is an object per row, not the
 * flat record list `getBundle` narrows to.
 */
interface Comparison {
  label: string;
  threshold: number | null;
  realised_rate: number | null;
  note: string;
}

interface ThresholdRow {
  id: string;
  name: string;
  kind: string;
  value: number | null;
  direction: string;
  method: string;
  distribution_free: boolean | null;
  how_defined: string;
  source: string;
  defined_in: string;
  budget_alpha?: number;
  budget_rationale?: string;
  budget_declared_first?: boolean;
  n_calibration?: number;
  order_statistic_index?: number;
  realised_false_alarm_rate?: number;
  coverage?: number;
  comparison?: Comparison;
  z?: number;
  false_alarm_reduction?: number;
  events_detected?: number;
  poisson_would_have_raised?: number;
  full_allowance_below?: number;
  zero_allowance_above?: number;
  floor?: number;
  uncertainty_penalty?: number;
}

interface Rejected {
  method: string;
  why_not: string;
}

interface Bundle {
  meta?: {
    thresholds_version?: string;
    n?: number;
    budget_declared_before_fitting?: boolean;
    false_alarm_budget?: { alpha: number; rationale: string; min_calibration: number };
    rejected_alternatives?: Rejected[];
  };
  rows?: ThresholdRow[];
}

async function getThresholds(): Promise<Bundle | null> {
  try {
    const raw = await readFile(
      join(process.cwd(), 'public', 'data', 'thresholds.json'),
      'utf-8',
    );
    return JSON.parse(raw) as Bundle;
  } catch {
    return null;
  }
}

/**
 * These values span 1e-3 to 1e2, so one fixed decimal count cannot serve them all:
 * `toFixed(4)` renders a realised-variance threshold of 0.0013337 as "0.0013", which
 * rounds away the digits that distinguish it. Anything below 0.01 is shown in
 * exponential form so a threshold is never displayed at lower precision than it was set.
 */
function num(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  if (v !== 0 && Math.abs(v) < 0.01) return v.toExponential(4);
  return v.toFixed(digits);
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return `${(v * 100).toFixed(digits)}%`;
}

function ThresholdCard({ t }: { t: ThresholdRow }) {
  const conformal = t.budget_alpha !== undefined;
  return (
    <article className="card" style={{ marginTop: 12 }}>
      <div
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: 6,
        }}
      >
        <span className="mono" style={{ fontWeight: 700 }}>
          {t.id}
        </span>
        <span className="chip">{t.kind}</span>
        {t.distribution_free ? (
          <span className="chip chip--good">distribution-free</span>
        ) : null}
        <span className="chip">alarms on the {t.direction} tail</span>
      </div>

      <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>{t.name}</h3>

      <p style={{ margin: '0 0 8px' }}>
        <span className="num" style={{ fontSize: 22, fontWeight: 700 }}>
          {num(t.value)}
        </span>{' '}
        <span className="small muted">by {t.method}</span>
      </p>

      <p className="small" style={{ margin: '0 0 8px' }}>
        {t.how_defined}
      </p>

      {conformal ? (
        <>
          <div className="tableWrap">
            <table>
              <tbody>
                <tr>
                  <td>False-alarm budget (alpha)</td>
                  <td className="num">{num(t.budget_alpha, 3)}</td>
                </tr>
                <tr>
                  <td>Calibration sample</td>
                  <td className="num">{t.n_calibration?.toLocaleString() ?? 'n/a'}</td>
                </tr>
                <tr>
                  <td>Conformal order statistic</td>
                  <td className="num">
                    {t.order_statistic_index?.toLocaleString() ?? 'n/a'}
                  </td>
                </tr>
                <tr>
                  <td>Realised false-alarm rate</td>
                  <td className="num">{pct(t.realised_false_alarm_rate)}</td>
                </tr>
                <tr>
                  <td>Coverage</td>
                  <td className="num">{pct(t.coverage)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {t.realised_false_alarm_rate !== undefined &&
          t.budget_alpha !== undefined &&
          t.realised_false_alarm_rate <= t.budget_alpha ? (
            <p className="small" style={{ marginTop: 6 }}>
              <span className="chip chip--good">budget honoured</span>{' '}
              <span className="muted">
                realised {pct(t.realised_false_alarm_rate)} is at or under the{' '}
                {pct(t.budget_alpha)} that was declared before fitting.
              </span>
            </p>
          ) : null}
          {t.comparison ? (
            <p className="small muted" style={{ marginTop: 6 }}>
              {t.comparison.label}: <span className="num">{num(t.comparison.threshold)}</span>{' '}
              would have realised{' '}
              <span className="num">{pct(t.comparison.realised_rate)}</span> — against a
              budget of {pct(t.budget_alpha)}. {t.comparison.note}
            </p>
          ) : null}
        </>
      ) : null}

      {t.z !== undefined ? (
        <div className="tableWrap">
          <table>
            <tbody>
              <tr>
                <td>z</td>
                <td className="num">{num(t.z, 1)}</td>
              </tr>
              <tr>
                <td>Events raised</td>
                <td className="num">{t.events_detected?.toLocaleString() ?? 'n/a'}</td>
              </tr>
              <tr>
                <td>A Poisson band would have raised</td>
                <td className="num">
                  {t.poisson_would_have_raised?.toLocaleString() ?? 'n/a'}
                </td>
              </tr>
              <tr>
                <td>False alarms removed</td>
                <td className="num">{pct(t.false_alarm_reduction)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}

      {t.zero_allowance_above !== undefined ? (
        <div className="tableWrap">
          <table>
            <tbody>
              <tr>
                <td>Full allowance at or below risk</td>
                <td className="num">{num(t.full_allowance_below, 2)}</td>
              </tr>
              <tr>
                <td>Zero allowance at or above risk</td>
                <td className="num">{num(t.zero_allowance_above, 2)}</td>
              </tr>
              <tr>
                <td>Floor</td>
                <td className="num">{num(t.floor, 2)}</td>
              </tr>
              <tr>
                <td>Uncertainty penalty</td>
                <td className="num">{num(t.uncertainty_penalty, 2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}

      <p className="small mono muted" style={{ marginTop: 8 }}>
        defined in {t.defined_in}
        <br />
        read from {t.source}
      </p>
    </article>
  );
}

export default async function ThresholdsPage() {
  const bundle = await getThresholds();
  const rows = bundle?.rows ?? [];
  const meta = bundle?.meta;
  const budget = meta?.false_alarm_budget;

  return (
    <>
      <h1>Risk thresholds</h1>
      <p className="lede">
        Six numbers in this system turn a measurement into a decision. This page lists
        every one of them, what it is currently set to, and the rule that set it. Nothing
        here is computed for the page: each value is read from the artifact named beneath
        it.
      </p>

      {rows.length === 0 ? (
        <NoData
          what="Threshold registry"
          note="No public/data/thresholds.json. It is assembled from data/reference/week2_thresholds.json, the FULL experiment bundle, logs/stats/stats_12.jsonl and the count-event summary."
        />
      ) : (
        <>
          <section className="grid">
            <StatCard label="Thresholds in force" value={String(rows.length)} />
            <StatCard
              label="False-alarm budget"
              value={budget ? pct(budget.alpha, 0) : 'n/a'}
              note="declared before any threshold was fitted"
            />
            <StatCard
              label="Distribution-free"
              value={`${rows.filter((r) => r.distribution_free).length} of ${rows.length}`}
              note="conformal, no distributional assumption"
            />
            <StatCard
              label="Registry version"
              value={meta?.thresholds_version ?? 'n/a'}
            />
          </section>

          {budget ? (
            <section className="boundary" style={{ marginTop: 16 }}>
              <h3>The budget comes before the data</h3>
              <p className="small">{budget.rationale}</p>
              <p className="small muted">
                Minimum calibration sample: {budget.min_calibration.toLocaleString()}{' '}
                observations. Below 1/alpha the required order statistic does not exist, so
                the fit refuses with <span className="mono">InsufficientCalibration</span>{' '}
                rather than returning a threshold it cannot stand behind.
                {meta?.budget_declared_before_fitting ? (
                  <>
                    {' '}
                    The artifact records{' '}
                    <span className="mono">budget_declared_before_fitting: true</span>.
                  </>
                ) : null}
              </p>
              <Caveat>
                A threshold chosen to make results look good and then described by its
                realised false-alarm rate is not a budget, it is a rationalisation. The
                ordering is the criterion, which is why it is recorded in the artifact.
              </Caveat>
            </section>
          ) : null}

          <section style={{ marginTop: 16 }}>
            <h2>How a distribution-free threshold is set</h2>
            <p className="small">
              The threshold is the empirical quantile of the calibration sample, taken at
              the conformal order statistic:
            </p>
            <p className="mono" style={{ margin: '8px 0' }}>
              tau = s<sub>(k)</sub>, k = ceil((n + 1)(1 - alpha))
            </p>
            <p className="small">
              The <span className="mono">n + 1</span> accounts for the future observation
              itself. That is what upgrades the statement from approximate to a
              finite-sample guarantee: for exchangeable scores, the probability that a
              fresh observation exceeds tau is at most alpha for <em>any</em> underlying
              distribution. No density is assumed and no moments are needed, so the
              guarantee survives the heavy tails and skew these features actually have.
            </p>
          </section>

          {meta?.rejected_alternatives?.length ? (
            <section style={{ marginTop: 16 }}>
              <h2>What was not used, and why</h2>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th>Why it fails here</th>
                    </tr>
                  </thead>
                  <tbody>
                    {meta.rejected_alternatives.map((r) => (
                      <tr key={r.method}>
                        <td className="mono">{r.method}</td>
                        <td className="small">{r.why_not}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <section style={{ marginTop: 16 }}>
            <h2>The thresholds</h2>
            {rows.map((t) => (
              <ThresholdCard key={t.id} t={t} />
            ))}
          </section>

          <section className="boundary" style={{ marginTop: 16 }}>
            <h3>Two thresholds that look alike and are not</h3>
            <p className="small">
              The operating threshold and the best-F1 threshold sit within a few
              thousandths of each other, and only one of them may be used to report a
              result. The operating threshold was selected on the <strong>training</strong>{' '}
              split and carried to evaluation unchanged. The best-F1 threshold is the
              argmax of F1 on the scores being evaluated, so quoting a metric at it would
              be selecting the threshold on the split then reported — threshold-provenance
              leakage, tracked as L6. STATS-12 uses it to bucket errors and nothing else;
              STATS-10 refuses to recompute a threshold at all and reads the train-selected
              one back from the experiment bundle.
            </p>
          </section>
        </>
      )}
    </>
  );
}
