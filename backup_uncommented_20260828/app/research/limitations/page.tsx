import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { getLimitations } from '@/lib/data';
import type { LimitationRecord, ResearchStatus } from '@/lib/types';

export const dynamic = 'force-static';

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

function LimitationCard({ l }: { l: LimitationRecord }) {
  const specs = l.research_questions.flatMap((r) => r.experiments);
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
        <p className="small muted" style={{ margin: '0 0 8px' }}>
          <strong>Current substitute:</strong> {l.current_substitute}
        </p>
      ) : null}

      {l.research_questions.length ? (
        <div className="small" style={{ marginTop: 6 }}>
          <strong>Research question:</strong> {l.research_questions[0].question}
        </div>
      ) : null}

      <p className="small muted" style={{ margin: '8px 0 0' }}>
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

  const negatives = rows.filter(
    (l) => l.category === 'UNRESOLVED_NEGATIVE_RESULT',
  );
  const limitations = rows.filter((l) => l.category !== 'UNRESOLVED_NEGATIVE_RESULT');
  const specs = rows.flatMap((l) => l.research_questions.flatMap((r) => r.experiments));
  const runnable = specs.filter((s) => s.required_data.length === 0);
  const blocked = specs.filter((s) => s.required_data.length > 0);

  const requiredData = [...new Set(blocked.flatMap((s) => s.required_data))];

  return (
    <>
      <h1>Limitations &amp; research opportunities</h1>
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
              note="specified, never fabricated"
            />
          </div>

          <section className="boundary">
            <h3>How to read this page</h3>
            <ul>
              <li>
                <strong>NOT MEASURED</strong> means no measurement exists — not that the
                measurement was zero.
              </li>
              <li>
                <strong>NOT SUPPORTED</strong> means a hypothesis was tested and the
                evidence went the other way.
              </li>
              <li>
                <strong>BLOCKED</strong> means the experiment is designed and waiting on
                data that does not exist. No result is shown for it, ever.
              </li>
              <li>
                A designed experiment is not a finding. Nothing on this page claims a
                future experiment has been performed.
              </li>
            </ul>
          </section>

          <h2>Unresolved negative results</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
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
            {blocked.length} experiment specifications are complete and waiting on the
            following. Each is external: no amount of engineering here produces it.
          </p>
          <ul className="small">
            {requiredData.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>

          <h2>Priority order</h2>
          <ol className="small">
            <li>
              <strong>Adjudicated real incident labels.</strong> Without them every
              detection number stays a statement about injected episodes (L-04).
            </li>
            <li>
              <strong>Licence-clear point-in-time index membership.</strong> Turns the
              universe from a proxy into the thing the literature compares against (L-01).
            </li>
            <li>
              <strong>A true Level-2 sample.</strong> Calibrates the daily microstructure
              proxies (L-02).
            </li>
            <li>
              <strong>Tier-2 and Tier-3 model weights.</strong> Measures whether capacity
              justifies its cost (L-08).
            </li>
            <li>
              <strong>A completed freeze.</strong> Then the holdout may be evaluated,
              once (L-11).
            </li>
          </ol>
        </>
      )}
    </>
  );
}
