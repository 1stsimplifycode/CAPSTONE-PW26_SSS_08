import Link from 'next/link';

import {
  RISK_STATE_COLOR,
  RISK_STATE_COPY,
  STATUS_TONE,
  type ResearchStatus,
  type RiskState,
} from '@/lib/types';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SMALL REUSABLE PIECES THE WHOLE SITE IS BUILT FROM.
 *
 * A stat card, a coloured pill, a status chip, a score bar, a "no data" block, a caveat
 * box. Each defined ONCE here and used everywhere.
 *
 * Why that matters beyond tidiness: if every page drew its own "no data" message, they
 * would slowly diverge, and eventually one of them would say something weaker than the
 * others. One definition means one behaviour, everywhere, forever.
 *
 * And two of these -- `StatePill` and `NoData` -- carry design decisions worth reading in
 * full. They are commented at length below.
 */

// A labelled number in a box, optionally clickable.
export function StatCard({
  label,
  value,
  note,
  href,
}: {
  label: string;
  value: string;
  note?: string;
  href?: string;
}) {
  // The contents built once, then wrapped either in a link or a plain box -- so the two
  // versions cannot drift apart in appearance.
  const body = (
    <>
      <div className="card__label">{label}</div>
      <div className="card__value">{value}</div>
      {/* The note only if there is one, so an unexplained card does not leave a gap. */}
      {note ? <div className="card__note">{note}</div> : null}
    </>
  );
  return href ? (
    <Link href={href} className="card">
      {body}
    </Link>
  ) : (
    <div className="card">{body}</div>
  );
}

/**
 * A risk state, with a shape cue as well as colour.
 *
 * Colour alone would fail anyone with a colour-vision deficiency and anyone printing in
 * greyscale, so the label carries the meaning and the dot carries only emphasis.
 */
// PLAIN ENGLISH: an accessibility decision, and an important one.
// Roughly one man in twelve cannot reliably distinguish red from green. And anybody who
// prints the page gets grey.
// So the colour is DECORATION. The actual meaning is in the WORD -- "Escalating", "Peak".
// A reader who cannot see the colour at all loses nothing whatever.
// The rule is: colour may reinforce information, never carry it alone.
export function StatePill({ state }: { state: RiskState }) {
  // `?? {label: state, ...}` falls back to showing the raw state name for anything
  // unrecognised -- so an unexpected value appears visibly rather than as a blank pill.
  const copy = RISK_STATE_COPY[state] ?? { label: state, meaning: '' };
  return (
    <span
      className="pill"
      style={{ background: RISK_STATE_COLOR[state] ?? '#666' }}
      // The full meaning on hover, so the short label always has its explanation within
      // reach.
      title={copy.meaning}
    >
      {/* THE WORD. This is what carries the meaning. */}
      {copy.label}
    </span>
  );
}

// A small coloured chip for a research status.
export function StatusChip({ status }: { status: ResearchStatus | string }) {
  const tone = STATUS_TONE[status as ResearchStatus] ?? 'neutral';
  const cls =
    tone === 'good'
      ? 'chip chip--good'
      : tone === 'warn'
        ? 'chip chip--warn'
        : tone === 'bad'
          ? 'chip chip--bad'
          // Neutral for anything unrecognised -- the cautious default, since guessing a
          // colour for an unknown status could imply good or bad news that was never meant.
          : 'chip';
  // Underscores turned into spaces, so "NOT_MEASURED" reads as "NOT MEASURED".
  return <span className={cls}>{String(status).replace(/_/g, ' ')}</span>;
}

// A little bar showing a score from 0 to 1.
export function ScoreBar({ value }: { value: number | null | undefined }) {
  // No value: the word "n/a". NOT an empty bar, which would look exactly like a score of
  // zero -- a confident claim about something we do not know.
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="muted">n/a</span>;
  }
  // Force it into 0-to-1, so a stray out-of-range value cannot draw a bar off the edge of
  // its container.
  const clamped = Math.max(0, Math.min(1, value));
  return (
    // `role="img"` with a label means screen-reader software announces the actual number.
    // Without it, a listening reader would get nothing at all from a purely visual bar.
    <div className="bar" role="img" aria-label={`score ${clamped.toFixed(3)}`}>
      <div className="bar__fill" style={{ width: `${clamped * 100}%` }} />
    </div>
  );
}

/**
 * Shown wherever an artifact has not been exported. Names what is missing and how to
 * produce it rather than rendering a plausible-looking empty chart.
 */
// PLAIN ENGLISH: the principle from lib/data.ts, given a face.
// "Rather than rendering a plausible-looking empty chart" is the point. An empty chart
// looks like a chart. A reader glances at it and concludes the market was quiet.
// This block cannot be mistaken for a result -- and it tells them exactly what to run.
export function NoData({ what, note }: { what: string; note?: string }) {
  return (
    <div className="empty">
      {/* WHAT is missing, named specifically rather than a generic "no data". */}
      <strong>{what} not available.</strong>
      <p style={{ margin: '6px 0 0' }}>
        {note ??
          // The default explanation restates the project's core promise: this site only
          // ever displays exported research results, and computes nothing on request. So a
          // missing file genuinely does mean a missing result.
          'This view renders only exported research artifacts. Nothing is generated at request time.'}
      </p>
      <p style={{ margin: '6px 0 0' }}>
        {/* AND THE EXACT COMMANDS, IN ORDER. Not "run the pipeline" but the four specific
            commands, in the sequence they must be run. Somebody who has never seen this
            project before can follow it. */}
        Produce it with <code>python scripts/build_dataset.py</code>,{' '}
        <code>python scripts/run_experiments.py</code>,{' '}
        <code>python scripts/run_research_angles.py</code>, then{' '}
        <code>python scripts/export_app_data.py</code>.
      </p>
    </div>
  );
}

// A small caveat box.
export function Caveat({ children }: { children: React.ReactNode }) {
  return (
    <aside className="notice notice--compact">
      <span className="notice__badge">Caveat</span>
      <p className="notice__text">{children}</p>
    </aside>
  );
}

/**
 * The evidence boundary shown in Product mode (research-angle section 50).
 *
 * Product mode stays simple, but a user reading a risk state deserves to know what that
 * state rests on. Four short lines and a link is the whole budget; the depth lives one
 * click away in Research mode.
 */
// PLAIN ENGLISH: a nicely judged compromise. The simple view must stay simple -- that is
// its whole purpose. But a reader looking at a risk verdict is owed some idea of what it
// rests on.
// So: four short lines, and a link. Enough to be honest, little enough not to overwhelm,
// and the full depth is one click away for anybody who wants it.
export function EvidenceBoundary({
  items,
  href = '/research/limitations',
}: {
  items: string[];
  href?: string;
}) {
  return (
    <section className="boundary">
      <h3>Evidence boundary</h3>
      <ul>
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
      <p style={{ margin: '8px 0 0' }}>
        {/* The link wording says what you will find, in a reader's own terms: what this
            does and does NOT support. Both halves named. */}
        <Link href={href}>What this does and does not support →</Link>
      </p>
    </section>
  );
}

/** Product-mode explanation with an escape hatch into the research depth. */
export function WhyFlagged({
  reasons,
  researchHref,
}: {
  reasons: { label: string; value: string }[];
  researchHref: string;
}) {
  return (
    // The browser's own collapsible element again -- so the reasons are in the page whether
    // or not JavaScript runs, and a printed page carries them.
    <details className="disclosure">
      {/* The question a reader is actually asking, in their words. */}
      <summary>Why was this flagged?</summary>
      <table>
        <tbody>
          {reasons.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              {/* `className="num"` right-aligns the numbers, so a column of them lines up
                  and can be compared at a glance. */}
              <td className="num">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ margin: '10px 0 0' }}>
        {/* And the next depth down, again naming what is there rather than saying "more". */}
        <Link href={researchHref}>Technical explanation, methods and attributions →</Link>
      </p>
    </details>
  );
}
