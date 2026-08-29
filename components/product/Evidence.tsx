import Link from 'next/link';

import type { EvidenceSource, EvidenceSummary, Sourced } from '@/lib/product';

import { SourceLine } from './Bits';
import { Disclosure } from './Disclosure';

/**
 * "What evidence does AEGIS actually have for this market period?"
 *
 * One component family, used everywhere that question is asked, so the answer cannot
 * differ between two pages. Each piece renders a status the backend computed for one
 * specific pair — the alignment layer is consulted, never reimplemented, and no threshold
 * or session count is written into this file.
 *
 * The registers are separated by CSS rather than by branching. Product mode sees a mark,
 * a verdict and a sentence; research mode sees the sessions, the ratio and the windows.
 * Both are in the prerendered HTML, so switching depth changes what is shown and never
 * what is true.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * "WHAT EVIDENCE DO WE ACTUALLY HAVE FOR THIS PERIOD?"
 *
 * The alignment idea, brought to the screen. If our index data covers 2015-2020 and our
 * news data covers 2021-2024, they overlap not at all, and anything said about both would
 * be about nothing. This shows the reader which sources genuinely cover the period they
 * are looking at.
 *
 * "CONSULTED, NEVER REIMPLEMENTED" is the rule this file follows to the letter. It contains
 * no threshold, no session count and no verdict of its own. Every judgement was computed by
 * the alignment layer and is displayed here.
 * If it recalculated anything, there would be two versions of the rule -- and one day they
 * would disagree, with the screen showing one answer and the research another.
 *
 * AND THE SHARPEST IDEA IS RIGHT AT THE BOTTOM, in the disclosure:
 *
 *     "available evidence is not used evidence."
 *
 * A source can cover exactly the right period -- and no experiment may ever have used it.
 * Those are entirely different claims, and a page showing a row of green ticks would let a
 * reader assume the stronger one.
 * So the page says both: here is what is AVAILABLE, and here -- separately, and honestly --
 * is how much of it has actually been USED. Today the answer is none.
 * Publishing that distinction, unprompted, is unusual.
 */

// The marks. A symbol as well as a colour, so the verdict survives greyscale printing and
// colour-blindness.
const MARKS: Record<string, string> = {
  check: '✓',
  partial: '◑',
  cross: '○',
  unknown: '?',
};

/** The verdict alone: a mark, a word, a colour. */
export function EvidenceStatusBadge({
  mark,
  badge,
  tone,
}: {
  mark: string;
  badge: string;
  tone: string;
}) {
  return (
    <span className="evBadge" data-tone={tone}>
      {/* The symbol is decoration -- hidden from screen readers, because the WORD beside it
          carries the meaning and a listener does not need "check mark" read out first. */}
      <span className="evBadge__mark" aria-hidden="true">
        {MARKS[mark] ?? '·'}
      </span>
      {badge}
    </span>
  );
}

/**
 * One source, as a card: what it is, when it covers, how much it shares, and the verdict.
 */
export function EvidenceAlignmentCard({ source }: { source: EvidenceSource }) {
  const aligned = source.status === 'ALIGNED';
  return (
    <article className="evCard" data-status={source.status}>
      <header className="evCard__head">
        <span className="evCard__title">{source.product_label}</span>
        <EvidenceStatusBadge
          mark={source.mark}
          badge={source.badge}
          tone={source.tone}
        />
      </header>

      <p className="evCard__blurb">{source.product_blurb}</p>

      <dl className="evCard__facts">
        <div>
          <dt>Period</dt>
          <dd>{source.period}</dd>
        </div>
        <div>
          <dt>Shared sessions</dt>
          <dd>
            {/* THE NUMBER THAT MATTERS, shown as a fraction: how many sessions are shared,
                out of how many the benchmark covers. "40 / 1,200" tells a reader instantly
                that the overlap is tiny -- which the word "partial" alone would not. */}
            {source.shared_sessions.toLocaleString('en-IN')}
            <span className="evCard__of">
              {' / '}
              {source.index_sessions.toLocaleString('en-IN')}
            </span>
          </dd>
        </div>
      </dl>

      {/* THE SAME VERDICT, IN TWO REGISTERS. Both in the page; the mode chooses. The simple
          sentence for a general reader, the technical summary for a researcher -- and
          neither is a softened version of the other, because both came from the same
          computed result. */}
      <p className="evCard__status modeOnly modeOnly--product">
        {source.product_status}
      </p>
      <p className="evCard__status modeOnly modeOnly--research">{source.summary}</p>

      <div className="modeOnly modeOnly--research evCard__research">
        <dl className="evCard__facts">
          <div>
            <dt>Coverage ratio</dt>
            <dd>{(source.coverage_ratio * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Source window</dt>
            {/* Monospaced, so a column of dates lines up and can be compared by eye. */}
            <dd className="mono">
              {source.period_from} → {source.period_to}
            </dd>
          </div>
          {source.overlap_from ? (
            <div>
              <dt>Overlap</dt>
              <dd className="mono">
                {source.overlap_from} → {source.overlap_to}
              </dd>
            </div>
          ) : null}
          <div>
            {/* THE ACTIONABLE CONSEQUENCE: may these two be analysed together, yes or no.
                Not a ratio for the reader to interpret -- the answer itself. */}
            <dt>Combined analysis</dt>
            <dd>{source.permits.combined_analysis ? 'permitted' : 'not permitted'}</dd>
          </div>
        </dl>
        <p className="small muted">{source.source_note}</p>
      </div>

      <Link className="evCard__link" href={aligned ? source.href : '/research/alignment'}>
        {/* THE LINK CHANGES WITH THE VERDICT. Aligned: go and look at the evidence.
            Not aligned: "Why?" -- taking the reader to the explanation instead. The card
            never offers a door into evidence that cannot be used. */}
        {aligned ? 'View evidence' : 'Why?'} <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

/**
 * The compact form, for a card that already has a job.
 *
 * Three marks and three words. It exists so the home page can answer the question at a
 * glance without becoming a second alignment panel.
 */
// PLAIN ENGLISH: the home page should mention this without turning into a full alignment
// report. Three symbols and three labels is the entire budget -- enough to be honest,
// small enough not to take over a page that is about something else.
export function EvidenceCoverageSummary({
  summary,
  href = '/markets/nifty-50',
}: {
  summary: EvidenceSummary;
  href?: string;
}) {
  return (
    <div className="evSummary">
      <span className="evSummary__label">Evidence available</span>
      <ul className="evSummary__list">
        {summary.sources.map((s) => (
          <li key={s.source_id} data-tone={s.tone}>
            <span className="evSummary__mark" aria-hidden="true">
              {MARKS[s.mark] ?? '·'}
            </span>
            {s.product_label}
          </li>
        ))}
      </ul>
      <Link className="evSummary__cta" href={href}>
        Explore <span aria-hidden="true">→</span>
      </Link>
    </div>
  );
}

/** A one-line form for a page that is showing a week or a scenario. */
// The smallest form of all -- one line -- for pages where even the compact version would be
// too much. The same information at three different sizes, all from one source of truth.
export function EvidenceStrip({ summary }: { summary: EvidenceSummary }) {
  return (
    <p className="evStrip">
      <span className="evStrip__label">Evidence for this market period</span>
      {summary.sources.map((s) => (
        <span className="evStrip__item" key={s.source_id} data-tone={s.tone}>
          <span aria-hidden="true">{MARKS[s.mark] ?? '·'}</span> {s.product_label}
        </span>
      ))}
      <Link className="evStrip__cta" href="/research/alignment">
        Understand evidence <span aria-hidden="true">→</span>
      </Link>
    </p>
  );
}

/**
 * The full section: the cards, the headline, and the detail behind a disclosure.
 *
 * The disclosure carries the distinction that is easiest to lose — an aligned source
 * covers the same sessions, which is not the same as an experiment having used it. That
 * sentence is the difference between "evidence is available" and "evidence was used", and
 * the product would be overclaiming without it.
 */
export function EvidenceSection({
  evidence,
  title = 'Market evidence',
}: {
  evidence: Sourced<EvidenceSummary>;
  title?: string;
}) {
  const e = evidence.data;
  if (!e) {
    // Not computed: says so, with the note explaining what to run. Never an empty grid of
    // cards, which would read as "no evidence exists".
    return (
      <div className="productEmpty">
        <h3>Evidence not computed</h3>
        <p>{evidence.note}</p>
      </div>
    );
  }
  return (
    <section className="home__section">
      <div className="home__sectionHead">
        <h2>{title}</h2>
        <span className="home__asof">
          {e.index_period} · {e.index_sessions.toLocaleString('en-IN')} sessions
        </span>
      </div>

      <p className="evHeadline">{e.headline}</p>

      <div className="evGrid">
        {e.sources.map((s) => (
          <EvidenceAlignmentCard key={s.source_id} source={s} />
        ))}
      </div>

      {/* Where this came from -- live or snapshot -- since even the evidence summary must
          say which. */}
      <SourceLine of={evidence} />

      {/* THE MOST IMPORTANT PART OF THE PAGE, and note the summary text itself carries the
          distinction: "available evidence is not used evidence". A reader who never opens
          the box has still been told. */}
      <Disclosure summary="Understand why — available evidence is not used evidence">
        {/* Both registers again, both in the page. */}
        <p style={{ marginTop: 0 }} className="modeOnly modeOnly--product">
          {e.experiments_using_index.product_note}
        </p>
        <p style={{ marginTop: 0 }} className="modeOnly modeOnly--research">
          {e.experiments_using_index.research_note}
        </p>
        <p>
          {/* THE FULL EXPLANATION, and it is worth reading closely. It grants what the ticks
              DO mean -- a result about both would at least be about a real period -- then
              draws the line: whether any analysis has actually been run that way is a
              separate question. And it answers that question with the actual count, which
              today is zero.
              A project publishing "none of our experiments use this" beside a row of green
              ticks is doing something most would not. */}
          A source marked aligned covers the same sessions as the benchmark, so a result
          about both would at least be about a real period. Whether any analysis has
          actually been run that way is a separate question, and the answer today is no:{' '}
          {e.experiments_using_index.count} experiments in this project take the index as
          an input.
        </p>
        <p className="instrument__deeper">
          <Link href="/research/alignment">See the full alignment matrix →</Link>
          {/* And the link says exactly what is behind it -- including the THRESHOLD that
              produced the verdict, so a reader can disagree with the standard rather than
              only with the conclusion. */}
          <span className="small muted">
            Every pair, with its windows, overlap, coverage ratio and the threshold that
            produced the verdict.
          </span>
        </p>
      </Disclosure>
    </section>
  );
}
