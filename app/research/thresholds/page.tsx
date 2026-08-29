// Reading a file from disk, and joining path pieces together safely.
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { Caveat, NoData, StatCard } from '@/components/ui/Primitives';

// Built once, at build time. This page reads a file that does not change between visits.
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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE PAGE THAT SHOWS EVERY "LINE IN THE SAND", AND WHO DREW IT.
 *
 * A THRESHOLD is the moment a measurement becomes a decision. The number 0.0013 is just a
 * number -- until somebody says "above this, raise an alarm". Then it decides things.
 * Six such numbers exist in this whole system, and this page lists all six.
 *
 * THE IMPORTANT WORD IS "BUDGET, BEFORE THE DATA".
 * The dishonest way to pick a threshold: run everything, look at the results, and choose the
 * cutoff that makes them look best. Then afterwards report the false-alarm rate you happened
 * to get, as though it had been your target all along.
 * The page names that exactly: "not a budget, it is a rationalisation."
 * Here the allowed false-alarm rate was written down FIRST, and the artifact records
 * `budget_declared_before_fitting: true` as proof.
 *
 * AND "DISTRIBUTION-FREE" is the other big idea. Most statistical cutoffs assume the data
 * has a nice familiar shape -- a bell curve. Market data does not; it has fat tails, where
 * extreme events happen far more often than a bell curve predicts. So instead of assuming a
 * shape, this method just SORTS the past values and counts to the right position. That works
 * whatever shape the data turns out to have.
 */
// The shape of one "if we had done it the other way" comparison.
interface Comparison {
  label: string;
  threshold: number | null;
  realised_rate: number | null;
  note: string;
}

// One threshold, and everything known about it.
interface ThresholdRow {
  id: string;
  name: string;
  kind: string;
  value: number | null;
  // Which side raises the alarm -- above the line, or below it.
  direction: string;
  method: string;
  distribution_free: boolean | null;
  how_defined: string;
  // The file it was read from, and the code that defines it. Both, always.
  source: string;
  defined_in: string;
  // Everything below is optional with `?`, because the six thresholds are set by three
  // different methods and each carries different evidence. A conformal cutoff has a
  // calibration sample; a z-score cutoff does not.
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

// A method that was considered and turned down -- with the reason.
interface Rejected {
  method: string;
  why_not: string;
}

// The whole file: a header of shared facts, plus the list of thresholds.
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
    // Missing or unreadable -> null, and the page shows a proper "no data" block rather
    // than crashing or, worse, showing an empty list that reads as "no thresholds exist".
    return null;
  }
}

/**
 * These values span 1e-3 to 1e2, so one fixed decimal count cannot serve them all:
 * `toFixed(4)` renders a realised-variance threshold of 0.0013337 as "0.0013", which
 * rounds away the digits that distinguish it. Anything below 0.01 is shown in
 * exponential form so a threshold is never displayed at lower precision than it was set.
 */
// PLAIN ENGLISH: a genuinely careful little detail. These six numbers range from about
// 0.001 to about 100 -- five orders of magnitude apart. Round them all to four decimals and
// the tiny ones become "0.0013", throwing away the digits that make two different thresholds
// distinguishable. So very small numbers switch to scientific notation instead.
// The principle: NEVER SHOW A THRESHOLD AT LOWER PRECISION THAN IT WAS SET AT.
function num(v: number | null | undefined, digits = 4): string {
  // Missing, or not a number at all -> the honest "n/a" rather than a misleading 0.
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  // Small but not zero -> exponential form, keeping all the meaningful digits.
  if (v !== 0 && Math.abs(v) < 0.01) return v.toExponential(4);
  return v.toFixed(digits);
}

// A proportion as a percentage -- 0.01 becomes "1.00%".
function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return `${(v * 100).toFixed(digits)}%`;
}

// One threshold's card.
function ThresholdCard({ t }: { t: ThresholdRow }) {
  // Does this one have a declared false-alarm budget? If so it is a conformal threshold and
  // has a whole extra body of evidence to show.
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
        {/* The green badge for "assumes no particular shape of data" -- the strongest kind. */}
        {t.distribution_free ? (
          <span className="chip chip--good">distribution-free</span>
        ) : null}
        {/* WHICH SIDE FIRES, in words. "alarms on the upper tail" leaves nothing to guess. */}
        <span className="chip">alarms on the {t.direction} tail</span>
      </div>

      <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>{t.name}</h3>

      <p style={{ margin: '0 0 8px' }}>
        {/* The number large, and the method that produced it immediately beside it -- so the
            value never appears without its justification. */}
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
                  {/* ALPHA: the share of false alarms we agreed in advance to accept. */}
                  <td>False-alarm budget (alpha)</td>
                  <td className="num">{num(t.budget_alpha, 3)}</td>
                </tr>
                <tr>
                  {/* How many past observations the cutoff was read off. */}
                  <td>Calibration sample</td>
                  <td className="num">{t.n_calibration?.toLocaleString() ?? 'n/a'}</td>
                </tr>
                <tr>
                  {/* WHICH position in the sorted list was taken -- so the reader could
                      literally recount it themselves. */}
                  <td>Conformal order statistic</td>
                  <td className="num">
                    {t.order_statistic_index?.toLocaleString() ?? 'n/a'}
                  </td>
                </tr>
                <tr>
                  {/* AND WHAT ACTUALLY HAPPENED, against what was promised. */}
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
          {/* The green "budget honoured" line appears ONLY if the promise was actually kept.
              Both `!== undefined` checks first, so a missing value can never be silently
              treated as a pass. */}
          {t.realised_false_alarm_rate !== undefined &&
          t.budget_alpha !== undefined &&
          t.realised_false_alarm_rate <= t.budget_alpha ? (
            <p className="small" style={{ marginTop: 6 }}>
              <span className="chip chip--good">budget honoured</span>{' '}
              <span className="muted">
                {/* "declared before fitting" repeated here, where the good news is -- so the
                    claim of success carries the condition that makes it meaningful. */}
                realised {pct(t.realised_false_alarm_rate)} is at or under the{' '}
                {pct(t.budget_alpha)} that was declared before fitting.
              </span>
            </p>
          ) : null}
          {t.comparison ? (
            // THE ROAD NOT TAKEN, quantified. "The usual textbook method would have given
            // this number, and would have produced this many false alarms" -- so the choice
            // of method is shown to matter rather than merely asserted to.
            <p className="small muted" style={{ marginTop: 6 }}>
              {t.comparison.label}: <span className="num">{num(t.comparison.threshold)}</span>{' '}
              would have realised{' '}
              <span className="num">{pct(t.comparison.realised_rate)}</span> — against a
              budget of {pct(t.budget_alpha)}. {t.comparison.note}
            </p>
          ) : null}
        </>
      ) : null}

      {/* The second kind of threshold: a z-score cutoff, with its own evidence. */}
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
                {/* THE COMPARISON THAT JUSTIFIES THE EXTRA WORK. A simple Poisson band -- the
                    "trades arrive like raindrops" assumption -- would have raised this many.
                    Printing both side by side shows what the more careful method bought. */}
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

      {/* The third kind: the gate policy, which does not raise alarms but shrinks an
          allowance as risk rises. */}
      {t.zero_allowance_above !== undefined ? (
        <div className="tableWrap">
          <table>
            <tbody>
              <tr>
                {/* Below this risk, the full allowance. */}
                <td>Full allowance at or below risk</td>
                <td className="num">{num(t.full_allowance_below, 2)}</td>
              </tr>
              <tr>
                {/* Above this risk, none at all. Between the two it slides down smoothly. */}
                <td>Zero allowance at or above risk</td>
                <td className="num">{num(t.zero_allowance_above, 2)}</td>
              </tr>
              <tr>
                <td>Floor</td>
                <td className="num">{num(t.floor, 2)}</td>
              </tr>
              <tr>
                {/* The extra reduction applied when the estimate itself is uncertain --
                    less confident means more cautious, not less. */}
                <td>Uncertainty penalty</td>
                <td className="num">{num(t.uncertainty_penalty, 2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}

      {/* EVERY CARD ENDS THE SAME WAY: the code that defines it, and the file it was read
          from. Two lines that make every number on this page checkable. */}
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
  // `?? []` and `?.` throughout, so a missing file produces an empty page rather than a
  // crash.
  const rows = bundle?.rows ?? [];
  const meta = bundle?.meta;
  const budget = meta?.false_alarm_budget;

  return (
    <>
      <h1>Risk thresholds</h1>
      <p className="lede">
        {/* "turn a measurement into a decision" -- the clearest one-line definition of what a
            threshold IS. And the closing sentence removes any suspicion that the page is
            doing its own arithmetic: every value is read from a named artifact. */}
        Six numbers in this system turn a measurement into a decision. This page lists
        every one of them, what it is currently set to, and the rule that set it. Nothing
        here is computed for the page: each value is read from the artifact named beneath
        it.
      </p>

      {rows.length === 0 ? (
        // Not a blank page. The note names EVERY file the registry is built from, so a
        // reader knows precisely what to go and generate.
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
              // The ordering claim, on the card itself.
              note="declared before any threshold was fitted"
            />
            <StatCard
              label="Distribution-free"
              // "4 of 6" rather than just "4" -- so a reader sees the ones that are NOT.
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
              {/* THE HEADING IS THE ARGUMENT: "The budget comes before the data." */}
              <h3>The budget comes before the data</h3>
              <p className="small">{budget.rationale}</p>
              <p className="small muted">
                {/* AND THE REFUSAL. Below 1/alpha observations the required position in the
                    sorted list simply does not exist -- so the fit REFUSES rather than
                    returning a plausible-looking number it cannot justify.
                    Wanting 1-in-100 confidence from 50 observations is asking for the 50.5th
                    largest of 50 things. There is no such thing. */}
                Minimum calibration sample: {budget.min_calibration.toLocaleString()}{' '}
                observations. Below 1/alpha the required order statistic does not exist, so
                the fit refuses with <span className="mono">InsufficientCalibration</span>{' '}
                rather than returning a threshold it cannot stand behind.
                {meta?.budget_declared_before_fitting ? (
                  <>
                    {' '}
                    {/* THE MACHINE-CHECKABLE PROOF, printed as code. Not "we promise we did
                        it in that order" but a flag stored in the artifact at fit time. */}
                    The artifact records{' '}
                    <span className="mono">budget_declared_before_fitting: true</span>.
                  </>
                ) : null}
              </p>
              <Caveat>
                {/* THE SHARPEST SENTENCE ON THE PAGE, and it is aimed at the project's own
                    method: a threshold picked to flatter the results and then described by
                    the false-alarm rate it happened to produce "is not a budget, it is a
                    rationalisation."
                    Then the reason the flag above exists: THE ORDERING IS THE CRITERION. The
                    same number is honest or dishonest depending purely on when it was chosen
                    -- which is why the order is recorded rather than remembered. */}
                A threshold chosen to make results look good and then described by its
                realised false-alarm rate is not a budget, it is a rationalisation. The
                ordering is the criterion, which is why it is recorded in the artifact.
              </Caveat>
            </section>
          ) : null}

          <section style={{ marginTop: 16 }}>
            <h2>How a distribution-free threshold is set</h2>
            <p className="small">
              {/* The whole method in one sentence: sort the past values, count to a
                  particular position, use that value. */}
              The threshold is the empirical quantile of the calibration sample, taken at
              the conformal order statistic:
            </p>
            <p className="mono" style={{ margin: '8px 0' }}>
              {/* THE FORMULA ITSELF, so nothing is taken on trust. `<sub>` makes the (k) a
                  small subscript, as in a textbook. */}
              tau = s<sub>(k)</sub>, k = ceil((n + 1)(1 - alpha))
            </p>
            <p className="small">
              {/* AND WHY THE "+1". This is the beautiful bit of the method.
                  You are trying to bound how often a FUTURE observation will exceed the
                  cutoff. So you count that future observation into the total -- n past
                  values plus the one to come. That single extra 1 is what turns "roughly,
                  probably" into a guarantee that holds exactly, at any sample size, for any
                  shape of data.
                  Which is exactly what market data needs: heavy tails and skew break the
                  bell-curve assumption, and this method never made it. */}
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
              {/* THE REJECTED METHODS, published. Showing what you turned down and why is
                  what makes the method you chose a decision rather than a habit. */}
              <h2>What was not used, and why</h2>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Method</th>
                      {/* "Why it fails HERE" -- not "why it is bad". These are good methods
                          that do not suit this particular data. */}
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
            {/* All six cards, in the order the registry lists them. */}
            {rows.map((t) => (
              <ThresholdCard key={t.id} t={t} />
            ))}
          </section>

          <section className="boundary" style={{ marginTop: 16 }}>
            {/* THE MOST SUBTLE TRAP IN THE WHOLE PROJECT, given its own closing section. */}
            <h3>Two thresholds that look alike and are not</h3>
            <p className="small">
              {/* Two numbers a few thousandths apart, and using the wrong one silently
                  invalidates every result quoted at it.
                  THE OPERATING THRESHOLD was chosen on the TRAINING data and carried over
                  untouched -- it never saw the evaluation scores.
                  THE BEST-F1 THRESHOLD is whatever cutoff makes the evaluation scores look
                  best. Quoting a result at it means having peeked at the answers before
                  choosing the question. The project names that: threshold-provenance
                  leakage, tracked as limitation L6.
                  AND THEN WHAT IS ACTUALLY DONE ABOUT IT: STATS-12 uses the best-F1 number
                  only to sort errors into buckets, never to report a metric; STATS-10 will
                  not recompute a threshold at all and reads the train-selected one back out
                  of the stored bundle. The temptation is removed rather than resisted. */}
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
