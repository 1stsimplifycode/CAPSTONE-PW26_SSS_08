import Link from 'next/link';
import { notFound } from 'next/navigation';

import { NoData, StatusChip } from '@/components/ui/Primitives';
import { getLimitation, getLimitations } from '@/lib/data';
import type { ExperimentSpec, ResearchStatus } from '@/lib/types';

export const dynamic = 'force-static';

export async function generateStaticParams() {
  const b = await getLimitations();
  return b.rows.map((l) => ({ id: l.id }));
}

function SpecCard({ s }: { s: ExperimentSpec }) {
  const runnable = s.required_data.length === 0;
  return (
    <article className="card" style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontWeight: 700 }}>
          {s.id}
        </span>
        <StatusChip status={s.status as ResearchStatus} />
        <span className={runnable ? 'chip chip--good' : 'chip'}>
          {runnable ? 'runnable now' : 'blocked by data'}
        </span>
      </div>

      <p style={{ margin: '8px 0' }}>
        <strong>Hypothesis.</strong> {s.hypothesis}
      </p>

      <div className="tableWrap">
        <table>
          <tbody>
            <tr>
              <th>Independent variable</th>
              <td>{s.independent_variable}</td>
            </tr>
            <tr>
              <th>Dependent variable</th>
              <td>{s.dependent_variable}</td>
            </tr>
            <tr>
              <th>Control</th>
              <td>{s.control}</td>
            </tr>
            <tr>
              <th>Treatment</th>
              <td>{s.treatment}</td>
            </tr>
            <tr>
              <th>Dataset</th>
              <td>{s.dataset}</td>
            </tr>
            <tr>
              <th>Evaluation period</th>
              <td>{s.evaluation_period}</td>
            </tr>
            <tr>
              <th>Metrics</th>
              <td className="mono small">{s.metrics.join(', ')}</td>
            </tr>
            <tr>
              <th>Statistical test</th>
              <td>{s.statistical_test}</td>
            </tr>
            <tr>
              <th>Expected interpretation</th>
              <td>{s.expected_interpretation}</td>
            </tr>
            <tr>
              <th>Threats to validity</th>
              <td>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {s.threats_to_validity.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </td>
            </tr>
            {s.required_data.length ? (
              <tr>
                <th>Required data</th>
                <td>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {s.required_data.map((d) => (
                      <li key={d}>{d}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            ) : null}
            <tr>
              <th>Result</th>
              <td>
                {s.result_artifact ? (
                  <span className="mono small">{s.result_artifact}</span>
                ) : (
                  <span className="muted">
                    Not executed. No result exists for this specification.
                  </span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  );
}

export default async function LimitationDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const l = await getLimitation(id);
  if (!l) {
    const anyData = await getLimitation('L-01');
    if (!anyData) {
      return (
        <>
          <h1>{id.toUpperCase()}</h1>
          <NoData what="Limitations registry" />
        </>
      );
    }
    notFound();
  }

  return (
    <>
      <p className="small muted">
        <Link href="/research/limitations">← Limitations &amp; opportunities</Link>
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontWeight: 700, fontSize: 15 }}>
          {l.id}
        </span>
        <span className="chip">{l.category.replace(/_/g, ' ').toLowerCase()}</span>
        <StatusChip status={l.current_status as ResearchStatus} />
      </div>
      <h1 style={{ marginTop: 6 }}>{l.title}</h1>

      <h2>The boundary</h2>
      <p>{l.description}</p>

      <h2>Why it exists</h2>
      <p>{l.why_it_exists}</p>

      {l.current_substitute ? (
        <>
          <h2>What is used instead</h2>
          <p>{l.current_substitute}</p>
        </>
      ) : null}

      <h2>What this invalidates</h2>
      <ul>
        {l.invalidated_claims.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      <h2>What can still be concluded</h2>
      <ul>
        {l.still_valid.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      <h2>Research questions this creates</h2>
      {l.research_questions.length === 0 ? (
        <p className="muted small">No research question has been derived yet.</p>
      ) : (
        l.research_questions.map((rq) => (
          <section key={rq.id} style={{ marginTop: 18 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="mono" style={{ fontWeight: 700 }}>
                {rq.id}
              </span>
              <StatusChip status={rq.status as ResearchStatus} />
            </div>
            <p style={{ margin: '6px 0' }}>{rq.question}</p>
            {rq.current_evidence ? (
              <p className="small">
                <strong>Current evidence.</strong> {rq.current_evidence}
              </p>
            ) : null}
            {rq.what_remains_unresolved ? (
              <p className="small">
                <strong>Unresolved.</strong> {rq.what_remains_unresolved}
              </p>
            ) : null}
            {rq.experiments.map((s) => (
              <SpecCard key={s.id} s={s} />
            ))}
          </section>
        ))
      )}

      {l.required_data.length ? (
        <>
          <h2>Data required to resolve this</h2>
          <ul>
            {l.required_data.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </>
      ) : null}

      <h2>Future validation</h2>
      <p>{l.future_validation || 'Not yet specified.'}</p>

      <section className="boundary">
        <h3>Scope note attached to every result depending on this</h3>
        <p style={{ margin: 0 }}>{l.scope_note || 'None.'}</p>
        {l.forbidden_phrasings.length ? (
          <p className="small muted" style={{ margin: '8px 0 0' }}>
            Phrasings blocked by the claim guard:{' '}
            {l.forbidden_phrasings.map((f) => (
              <code key={f} style={{ marginRight: 6 }}>
                {f}
              </code>
            ))}
          </p>
        ) : null}
      </section>
    </>
  );
}
