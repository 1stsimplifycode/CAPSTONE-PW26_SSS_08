import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { SubjectRegistrar } from '@/components/ui/SubjectRegistrar';
import { fmt, getClaims, getExperiments, getLimitations, getUniverse } from '@/lib/data';
import { SCOPE_LABEL, type ResearchStatus } from '@/lib/types';

export const dynamic = 'force-static';

/**
 * Research overview: an honest picture before a flattering one.
 *
 * The four groups are ordered so a reviewer sees what is supported, what is not, what is
 * open and what is blocked — in that order — rather than a dashboard of green numbers.
 */
export default async function ResearchOverview({
  searchParams,
}: {
  searchParams: Promise<{ instrument?: string; event?: string; date?: string }>;
}) {
  const sp = await searchParams;
  const claims = await getClaims();
  const limitations = await getLimitations();
  const experiments = await getExperiments();
  const universe = await getUniverse();

  const supported = claims.rows.filter((c) => c.status === 'SUPPORTED');
  const notSupported = claims.rows.filter((c) => c.status === 'NOT_SUPPORTED');
  const partial = claims.rows.filter((c) => c.status === 'PARTIAL');

  const specs = limitations.rows.flatMap((l) =>
    l.research_questions.flatMap((r) => r.experiments),
  );
  const runnable = specs.filter((s) => s.required_data.length === 0);
  const blocked = specs.filter((s) => s.required_data.length > 0);
  const ranArms = experiments.rows.filter((e) => e.status === 'OK');

  return (
    <>
      <SubjectRegistrar
        instrument={sp.instrument}
        event={sp.event}
        date={sp.date}
        showBridge={false}
      />

      <h1>Research overview</h1>
      <p className="lede">
        What the current evidence supports, what it does not, what remains open, and what
        is waiting on data that does not exist yet. Nothing here is stated at a scope its
        evidence has not earned.
      </p>

      {sp.instrument ? (
        <section className="boundary">
          <h3>Carried context</h3>
          <p style={{ margin: 0 }}>
            You arrived from <strong>{sp.instrument}</strong>
            {sp.date ? ` (${sp.date})` : ''}. Its assessment comes from the arms and
            attributions below.{' '}
            <Link href={`/instruments/${encodeURIComponent(sp.instrument)}`}>
              Back to the instrument →
            </Link>
          </p>
        </section>
      ) : null}

      <div className="grid">
        <StatCard
          label="Supported claims"
          value={String(supported.length)}
          href="/research/claims"
        />
        <StatCard
          label="Not supported"
          value={String(notSupported.length)}
          note="reported, not buried"
          href="/research/claims"
        />
        <StatCard label="Partial" value={String(partial.length)} href="/research/claims" />
        <StatCard
          label="Open questions"
          value={String(runnable.length)}
          note="runnable with data on hand"
          href="/research/limitations"
        />
        <StatCard
          label="Blocked by data"
          value={String(blocked.length)}
          note="specified, not executed"
          href="/research/limitations"
        />
        <StatCard
          label="Ablation arms executed"
          value={String(ranArms.length)}
          href="/research/ablations"
        />
      </div>

      <section className="boundary">
        <h3>Standing scope</h3>
        <ul>
          <li>Universe: {universe.name}. Not an index.</li>
          <li>
            Labels: synthetic episodes injected into real NSE price data. No result here
            is evidence about real-world market-integrity incidents.
          </li>
          <li>
            Split: validation. The holdout is frozen and has not been evaluated, so no
            claim is stated at out-of-sample scope.
          </li>
        </ul>
      </section>

      <h2>Claims</h2>
      {!claims.dataAvailable ? (
        <NoData what="Claim ledger" note={claims.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Scope</th>
                <th>Claim</th>
                <th>Bounded by</th>
              </tr>
            </thead>
            <tbody>
              {claims.rows.map((c) => (
                <tr key={c.id}>
                  <td className="mono">
                    <Link href={`/research/claims#${c.id}`}>{c.id}</Link>
                  </td>
                  <td>
                    <StatusChip status={c.status as ResearchStatus} />
                  </td>
                  <td className="small muted">{SCOPE_LABEL[c.scope] ?? c.scope}</td>
                  <td>{c.claim}</td>
                  <td className="mono small">{c.limitations.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Where to go next</h2>
      <div className="grid grid--wide">
        <Link href="/research/limitations" className="card">
          <div className="card__label">Limitations &amp; opportunities</div>
          <div className="card__value" style={{ fontSize: 18 }}>
            {limitations.rows.length} boundaries
          </div>
          <div className="card__note">
            Each one mapped to the research question it creates and the experiment that
            would resolve it.
          </div>
        </Link>
        <Link href="/research/ablations" className="card">
          <div className="card__label">Ablations</div>
          <div className="card__value" style={{ fontSize: 18 }}>
            {ranArms.length} arms
          </div>
          <div className="card__note">
            Every component removed in turn, with cluster-bootstrap intervals and FDR
            control.
          </div>
        </Link>
        <Link href="/research/xai" className="card">
          <div className="card__label">XAI lab</div>
          <div className="card__value" style={{ fontSize: 18 }}>
            4 methods
          </div>
          <div className="card__note">
            Faithfulness, agreement and sanity checks — including the one that fails.
          </div>
        </Link>
        <Link href="/research/paper-lab" className="card">
          <div className="card__label">Paper lab</div>
          <div className="card__value" style={{ fontSize: 18 }}>
            figures &amp; tables
          </div>
          <div className="card__note">
            Every artifact traceable to an experiment, run, dataset, seed and commit.
          </div>
        </Link>
      </div>

      <h2>Headline numbers</h2>
      <p className="small muted">
        Full-stack AUPRC {fmt(ranArms.find((e) => e.arm === 'FULL')?.auprc)} on the
        validation split against a 0.244 positive rate. Read every number on this page
        together with the standing scope above.
      </p>
    </>
  );
}
