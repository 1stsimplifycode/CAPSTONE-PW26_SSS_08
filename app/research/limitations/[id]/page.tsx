import Link from 'next/link';
import { notFound } from 'next/navigation';

import { NoData, StatusChip } from '@/components/ui/Primitives';
import { getLimitation, getLimitations } from '@/lib/data';
import type { ExperimentSpec, ResearchStatus } from '@/lib/types';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * ONE LIMITATION IN FULL, WITH EVERYTHING THAT FOLLOWS FROM IT.
 *
 * The page walks through, in order:
 *   what the boundary is;
 *   why it exists;
 *   what we used instead;
 *   WHAT IT INVALIDATES -- the things this project therefore may not say;
 *   WHAT CAN STILL BE CONCLUDED -- because listing only the damage is its own distortion;
 *   the research questions it opens up, each with a complete experiment;
 *   what data would resolve it;
 *   and the exact phrasings the automatic guard blocks because of it.
 *
 * Both sides -- what is lost and what survives -- given equal space. A page that listed only
 * the invalidations would leave a reader unable to tell what remains standing.
 */

export const dynamic = 'force-static';

// Build one page per limitation, at build time, from the register itself. So the set of
// pages is the set of limitations, and cannot drift from it.
export async function generateStaticParams() {
  const b = await getLimitations();
  return b.rows.map((l) => ({ id: l.id }));
}

// One designed experiment, in full.
function SpecCard({ s }: { s: ExperimentSpec }) {
  const runnable = s.required_data.length === 0;
  return (
    <article className="card" style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontWeight: 700 }}>
          {s.id}
        </span>
        <StatusChip status={s.status as ResearchStatus} />
        {/* "runnable now" or "blocked by data" -- stated on every card, so an experiment
            that has no excuse is visibly distinguishable from one that is genuinely stuck. */}
        <span className={runnable ? 'chip chip--good' : 'chip'}>
          {runnable ? 'runnable now' : 'blocked by data'}
        </span>
      </div>

      <p style={{ margin: '8px 0' }}>
        {/* THE HYPOTHESIS FIRST -- what is being claimed, stated so it could be false. */}
        <strong>Hypothesis.</strong> {s.hypothesis}
      </p>

      <div className="tableWrap">
        <table>
          <tbody>
            {/* THE COMPLETE EXPERIMENTAL DESIGN. Every field of the compulsory form,
                published for a reader to inspect. */}
            <tr>
              <th>Independent variable</th>
              <td>{s.independent_variable}</td>
            </tr>
            <tr>
              <th>Dependent variable</th>
              <td>{s.dependent_variable}</td>
            </tr>
            {/* Control and treatment named separately, so the comparison is explicit rather
                than a before-and-after with nothing to compare against. */}
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
              {/* The metrics and the test, FIXED IN ADVANCE -- so nobody can choose the
                  flattering measure after seeing the numbers. */}
              <th>Metrics</th>
              <td className="mono small">{s.metrics.join(', ')}</td>
            </tr>
            <tr>
              <th>Statistical test</th>
              <td>{s.statistical_test}</td>
            </tr>
            <tr>
              {/* WHAT WE WILL CONCLUDE FROM THE RESULT -- written before running. This is
                  what makes it impossible to look at an outcome and construct a story to fit. */}
              <th>Expected interpretation</th>
              <td>{s.expected_interpretation}</td>
            </tr>
            <tr>
              {/* AND THE WAYS IT COULD STILL MISLEAD US, listed by the people who designed
                  it. Publishing your own experiment's weaknesses alongside its design is
                  rare and is exactly what makes the design checkable. */}
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
                  // THE CRUCIAL LINE. After a full page of rigorous experimental design -- a
                  // page persuasive enough that a reader could easily assume it had been run --
                  // this says plainly: "Not executed. No result exists for this specification."
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
    // A CAREFUL DISTINCTION between two different failures.
    // Try to fetch a limitation that certainly exists. If that also fails, the whole
    // register is missing -- so show the "no data" block with instructions.
    const anyData = await getLimitation('L-01');
    if (!anyData) {
      return (
        <>
          <h1>{id.toUpperCase()}</h1>
          <NoData what="Limitations registry" />
        </>
      );
    }
    // But if the register loaded fine and this particular id is not in it, then the address
    // is genuinely wrong -- a proper 404.
    // Telling those apart matters: "the data is missing" and "you typed the wrong thing"
    // call for completely different responses from the reader.
    notFound();
  }

  return (
    <>
      {/* A way back, at the top. */}
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

      {/* "The boundary" rather than "The problem" -- the reframing from the index page,
          carried into the section headings. */}
      <h2>The boundary</h2>
      <p>{l.description}</p>

      <h2>Why it exists</h2>
      {/* So a reader can judge whether it was avoidable, rather than only that it exists. */}
      <p>{l.why_it_exists}</p>

      {l.current_substitute ? (
        <>
          <h2>What is used instead</h2>
          <p>{l.current_substitute}</p>
        </>
      ) : null}

      {/* THE TWO SECTIONS THAT MATTER MOST, and they are deliberately adjacent. */}
      <h2>What this invalidates</h2>
      <ul>
        {l.invalidated_claims.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      <h2>What can still be concluded</h2>
      {/* The second half, and it is not consolation. Listing only the damage would leave a
          reader unable to tell what survives -- which is its own kind of distortion, and an
          unhelpful one. */}
      <ul>
        {l.still_valid.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      <h2>Research questions this creates</h2>
      {l.research_questions.length === 0 ? (
        // "has been derived YET" -- leaving the door open, rather than implying none exists.
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
              // KEPT SEPARATE FROM THE EVIDENCE. So partial progress never reads as a
              // finished answer -- the two are different paragraphs with different headings.
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
      {/* "Not yet specified" rather than a blank -- an honest admission that this gap has no
          plan attached yet. */}
      <p>{l.future_validation || 'Not yet specified.'}</p>

      <section className="boundary">
        {/* THE SCOPE NOTE -- the short warning attached to every result touched by this gap.
            Shown here so a reader can see exactly what wording travels with those results. */}
        <h3>Scope note attached to every result depending on this</h3>
        <p style={{ margin: 0 }}>{l.scope_note || 'None.'}</p>
        {l.forbidden_phrasings.length ? (
          <p className="small muted" style={{ margin: '8px 0 0' }}>
            {/* AND THE ACTUAL BLOCKED PHRASES, printed as code. So a reader can see precisely
                which wordings the automatic guard refuses -- and check whether a summary they
                have read elsewhere used one of them. */}
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
