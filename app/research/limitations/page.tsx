import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { getLimitations } from '@/lib/data';
import type { LimitationRecord, ResearchStatus } from '@/lib/types';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE LIMITATIONS PAGE, AND ITS CENTRAL REFRAMING:
 *
 *     "A limitation here is not an apology and not a failure; it is a stated edge with a
 *      designed experiment attached, and a status saying whether that experiment has been
 *      run."
 *
 * That turns a limitations section from the place where a project says sorry into the
 * place where it says what it would do next -- and whether it has done it.
 *
 * The page also does something almost nobody does: it gives NEGATIVE RESULTS their own
 * section, ABOVE the ordinary limitations, described as "first-class results".
 * And it ends with a priority order for what would unblock the whole programme.
 */

export const dynamic = 'force-static';

// The machine categories turned into readable words.
const CATEGORY_COPY: Record<string, string> = {
  ENGINEERING: 'Engineering',
  DATA: 'Data',
  LICENSING: 'Licensing',
  COMPUTATIONAL: 'Computational',
  METHODOLOGICAL: 'Methodological',
  EVALUATION: 'Evaluation',
  SCIENTIFIC_OPEN_QUESTION: 'Open question',
  UNRESOLVED_NEGATIVE_RESULT: 'Unresolved negative result',
};

// One limitation, as a card.
function LimitationCard({ l }: { l: LimitationRecord }) {
  const specs = l.research_questions.flatMap((r) => r.experiments);
  // The uncomfortable split again: how many need nothing, and how many are genuinely stuck.
  const runnable = specs.filter((s) => s.required_data.length === 0).length;
  const blocked = specs.length - runnable;
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
          {l.id}
        </span>
        {/* FOUR CHIPS: the id, the kind, the status, and the SEVERITY. Together they tell a
            reader how far this one reaches before they read a word of the description. */}
        <span className="chip">{CATEGORY_COPY[l.category] ?? l.category}</span>
        <StatusChip status={l.current_status as ResearchStatus} />
        <span className="chip">{l.severity.replace(/_/g, ' ').toLowerCase()}</span>
      </div>

      <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>
        <Link href={`/research/limitations/${l.id}`}>{l.title}</Link>
      </h3>
      <p className="small" style={{ margin: '0 0 8px' }}>
        {l.description}
      </p>

      {l.current_substitute ? (
        // WHAT WE USED INSTEAD, where anything was used. Shown on the card, so a reader
        // knows immediately whether a gap was papered over or simply left open.
        <p className="small muted" style={{ margin: '0 0 8px' }}>
          <strong>Current substitute:</strong> {l.current_substitute}
        </p>
      ) : null}

      {l.research_questions.length ? (
        // THE QUESTION THIS GAP OPENS UP -- which is what turns a limitation into a
        // direction rather than a dead end.
        <div className="small" style={{ marginTop: 6 }}>
          <strong>Research question:</strong> {l.research_questions[0].question}
        </div>
      ) : null}

      <p className="small muted" style={{ margin: '8px 0 0' }}>
        {/* How many experiments are designed, how many could run today, and how many are
            stuck. Correct singular and plural, and each clause only appears if it applies --
            so the line never reads "0 runnable now". */}
        {specs.length} experiment {specs.length === 1 ? 'specification' : 'specifications'}
        {runnable ? ` · ${runnable} runnable now` : ''}
        {blocked ? ` · ${blocked} blocked by data` : ''} ·{' '}
        <Link href={`/research/limitations/${l.id}`}>Open →</Link>
      </p>
    </article>
  );
}

export default async function LimitationsPage() {
  const b = await getLimitations();
  const rows = b.rows;

  // The negative results kept separate, and shown FIRST.
  const negatives = rows.filter(
    (l) => l.category === 'UNRESOLVED_NEGATIVE_RESULT',
  );
  const limitations = rows.filter((l) => l.category !== 'UNRESOLVED_NEGATIVE_RESULT');
  const specs = rows.flatMap((l) => l.research_questions.flatMap((r) => r.experiments));
  const runnable = specs.filter((s) => s.required_data.length === 0);
  const blocked = specs.filter((s) => s.required_data.length > 0);

  // Every distinct piece of missing data, gathered into one list. `new Set` removes the
  // duplicates where several experiments need the same thing.
  const requiredData = [...new Set(blocked.flatMap((s) => s.required_data))];

  return (
    <>
      <h1>Limitations &amp; research opportunities</h1>
      {/* Even the TITLE does the reframing: not "Limitations" but "Limitations AND research
          opportunities". The same facts, presented as directions rather than only as walls. */}
      <p className="lede">
        Every boundary defines what the current evidence can support — and what experiment
        comes next. A limitation here is not an apology and not a failure; it is a stated
        edge with a designed experiment attached, and a status saying whether that
        experiment has been run.
      </p>

      {!b.dataAvailable ? (
        <NoData what="Limitations registry" note={b.note} />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Limitations" value={String(limitations.length)} />
            <StatCard
              label="Unresolved negative results"
              value={String(negatives.length)}
              // "measured, reported, not buried" -- three words that describe exactly what
              // this project did with results it did not want.
              note="measured, reported, not buried"
            />
            <StatCard label="Research questions" value={String(rows.flatMap((l) => l.research_questions).length)} />
            <StatCard
              label="Runnable now"
              value={String(runnable.length)}
              note="no external data needed"
            />
            <StatCard
              label="Blocked by data"
              value={String(blocked.length)}
              // "specified, never fabricated" -- these experiments are fully designed, and
              // no result has been invented for any of them.
              note="specified, never fabricated"
            />
          </div>

          <section className="boundary">
            {/* AN INSTRUCTION MANUAL FOR THE PAGE, teaching the reader the vocabulary before
                they meet it. Four distinctions, each of which is routinely blurred elsewhere. */}
            <h3>How to read this page</h3>
            <ul>
              <li>
                {/* THE DISTINCTION THE WHOLE PROJECT RESTS ON, stated for a reader:
                    no measurement exists -- NOT that the measurement was zero. */}
                <strong>NOT MEASURED</strong> means no measurement exists — not that the
                measurement was zero.
              </li>
              <li>
                {/* And its opposite: we DID test it, and the evidence went the other way. */}
                <strong>NOT SUPPORTED</strong> means a hypothesis was tested and the
                evidence went the other way.
              </li>
              <li>
                {/* And the promise attached to BLOCKED: "No result is shown for it, ever."
                    An absolute commitment, in four words. */}
                <strong>BLOCKED</strong> means the experiment is designed and waiting on
                data that does not exist. No result is shown for it, ever.
              </li>
              <li>
                {/* THE MOST IMPORTANT LINE ON THE PAGE. A page full of well-specified
                    experiments is enormously persuasive, and a reader could easily come away
                    believing they had been run. This says plainly that they have not. */}
                A designed experiment is not a finding. Nothing on this page claims a
                future experiment has been performed.
              </li>
            </ul>
          </section>

          <h2>Unresolved negative results</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            {/* "FIRST-CLASS RESULTS" -- and the justification: each one bounds a claim and
                generates its own research question. So a failed hypothesis is not a hole in
                the work; it is a finding that constrains what else may be said.
                And they are placed ABOVE the ordinary limitations, which is a deliberate
                choice about what a reader meets first. */}
            Measured outcomes that went against the hypothesis. These are first-class
            results: each one bounds a claim and generates its own research question.
          </p>
          {negatives.map((l) => (
            <LimitationCard key={l.id} l={l} />
          ))}

          <h2>Limitations</h2>
          {limitations.map((l) => (
            <LimitationCard key={l.id} l={l} />
          ))}

          <h2>Data that would unblock this programme</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            {/* AND THE CRUCIAL QUALIFIER: "Each is external: no amount of engineering here
                produces it."
                That distinguishes a genuine blocker from an excuse. These are not things
                somebody could build with more effort -- they are data that would have to
                come from outside. */}
            {blocked.length} experiment specifications are complete and waiting on the
            following. Each is external: no amount of engineering here produces it.
          </p>
          <ul className="small">
            {requiredData.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>

          <h2>Priority order</h2>
          {/* A RANKED LIST OF WHAT WOULD HELP MOST, with the consequence of each spelled out.
              This is the project telling a future reader -- or a future version of itself --
              exactly where to start. */}
          <ol className="small">
            <li>
              {/* FIRST, AND IT IS THE BIGGEST ADMISSION ON THE PAGE: without real incident
                  labels, every detection number in the entire project remains a statement
                  about episodes they painted in themselves. Placed at number one. */}
              <strong>Adjudicated real incident labels.</strong> Without them every
              detection number stays a statement about injected episodes (L-04).
            </li>
            <li>
              {/* Second: real index membership would make the work comparable with published
                  literature, which the proxy cannot be. */}
              <strong>Licence-clear point-in-time index membership.</strong> Turns the
              universe from a proxy into the thing the literature compares against (L-01).
            </li>
            <li>
              <strong>A true Level-2 sample.</strong> Calibrates the daily microstructure
              proxies (L-02).
            </li>
            <li>
              {/* And an honest framing of bigger models: not "would improve results" but
                  "measures whether capacity justifies its cost". The question, not the
                  assumed answer. */}
              <strong>Tier-2 and Tier-3 model weights.</strong> Measures whether capacity
              justifies its cost (L-08).
            </li>
            <li>
              {/* And last, the one that needs no data at all -- only discipline. The holdout
                  may be evaluated ONCE, and the word "once" is doing a great deal of work:
                  look at it twice and it stops being a holdout. */}
              <strong>A completed freeze.</strong> Then the holdout may be evaluated,
              once (L-11).
            </li>
          </ol>
        </>
      )}
    </>
  );
}
