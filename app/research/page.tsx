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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE RESEARCH FRONT PAGE, AND A DECISION ABOUT ORDER.
 *
 * "An honest picture before a flattering one" is the whole design in six words.
 *
 * The obvious layout is a row of encouraging green numbers -- claims supported, experiments
 * run, modules verified. Instead the cards run: supported, NOT supported, partial, open,
 * blocked.
 * So the second thing a reviewer sees is what did not work. And its card carries the note
 * "reported, not buried".
 *
 * Ordering is not a neutral choice. What comes first is what gets read, and what gets read
 * is what gets remembered.
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
      {/* Registers what the reader arrived looking at, so the mode switch can carry it. The
          bridge link is off, because this IS the research view. */}
      <SubjectRegistrar
        instrument={sp.instrument}
        event={sp.event}
        date={sp.date}
        showBridge={false}
      />

      <h1>Research overview</h1>
      <p className="lede">
        {/* FOUR THINGS IN ORDER: what it supports, what it does NOT, what is open, and what
            is waiting on data that does not exist.
            And the final sentence is the standard the whole page is written to: "Nothing here
            is stated at a scope its evidence has not earned." */}
        What the current evidence supports, what it does not, what remains open, and what
        is waiting on data that does not exist yet. Nothing here is stated at a scope its
        evidence has not earned.
      </p>

      {sp.instrument ? (
        // THE CARRIED CONTEXT, made visible. Somebody who clicked "how do we know this?"
        // from a company page is told, in words, that they arrived from there -- and given a
        // way straight back. Without this the switch would feel like being teleported.
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
        {/* THE ORDER IS THE POINT. Supported first, then immediately what is not. */}
        <StatCard
          label="Supported claims"
          value={String(supported.length)}
          href="/research/claims"
        />
        <StatCard
          label="Not supported"
          value={String(notSupported.length)}
          // "reported, not buried" -- three words explaining why this card exists at all.
          note="reported, not buried"
          href="/research/claims"
        />
        <StatCard label="Partial" value={String(partial.length)} href="/research/claims" />
        <StatCard
          // "Open questions ... runnable with data on hand" -- work with no excuse.
          label="Open questions"
          value={String(runnable.length)}
          note="runnable with data on hand"
          href="/research/limitations"
        />
        <StatCard
          label="Blocked by data"
          value={String(blocked.length)}
          // "specified, not executed" -- designed in full, and no result invented.
          note="specified, not executed"
          href="/research/limitations"
        />
        <StatCard
          label="Ablation arms executed"
          value={String(ranArms.length)}
          href="/research/ablations"
        />
        {/* Every card is a link, so each number leads to the evidence behind it rather than
            sitting on the page as a statistic to be taken on trust. */}
      </div>

      <section className="boundary">
        {/* THE STANDING SCOPE: three sentences that bound EVERY number on the page, placed
            above the numbers rather than beneath them. */}
        <h3>Standing scope</h3>
        <ul>
          {/* 1. It is not an index. Four words, unmissable. */}
          <li>Universe: {universe.name}. Not an index.</li>
          <li>
            {/* 2. The labels are synthetic -- and then the consequence spelled out in full:
                   NO result here is evidence about real-world incidents. Not softened, not
                   hedged. */}
            Labels: synthetic episodes injected into real NSE price data. No result here
            is evidence about real-world market-integrity incidents.
          </li>
          <li>
            {/* 3. And the holdout is frozen, so no claim reaches out-of-sample scope. The
                   strongest kind of result, and this project says plainly it has none. */}
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
                {/* STATUS AND SCOPE BEFORE THE CLAIM ITSELF -- so the reader's eye meets the
                    qualification before the assertion. */}
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
                  {/* AND THE CAVEATS IN THE SAME ROW. No claim appears in this table without
                      the limitations bounding it beside it. */}
                  <td className="mono small">{c.limitations.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Where to go next</h2>
      <div className="grid grid--wide">
        {/* Four routes onward, each naming what a reader will actually find there. */}
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
            {/* The method named in the description -- cluster bootstraps and FDR control --
                so a reader knows the rigour is there before they arrive. */}
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
            {/* "INCLUDING THE ONE THAT FAILS." Advertised on the card, as an invitation
                rather than a disclosure. */}
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
        {/* THE HEADLINE NUMBER, AND EVERYTHING NEEDED TO READ IT PROPERLY:
            the metric, the split it was measured on, and -- crucially -- the positive rate
            it should be judged against. Without that rate the AUPRC figure is
            uninterpretable, as this project's own metrics file insists.
            And the closing instruction: read every number here together with the standing
            scope above. */}
        Full-stack AUPRC {fmt(ranArms.find((e) => e.arm === 'FULL')?.auprc)} on the
        validation split against a 0.244 positive rate. Read every number on this page
        together with the standing scope above.
      </p>
    </>
  );
}
