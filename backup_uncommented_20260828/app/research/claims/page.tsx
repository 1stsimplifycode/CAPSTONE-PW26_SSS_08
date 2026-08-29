import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { getClaims, getLimitations } from '@/lib/data';
import { SCOPE_LABEL, type ResearchStatus } from '@/lib/types';

export const dynamic = 'force-static';

/**
 * The claim ledger (research-angle section 35).
 *
 * Each claim carries the scope it is entitled to. The scope label is not decoration: an
 * automated guard refuses text that asserts more than its scope supports, and the build
 * fails rather than shipping an overclaim. The rejected phrasings are shown next to each
 * claim so the boundary is visible rather than implied.
 */
export default async function ClaimsPage() {
  const claims = await getClaims();
  const limitations = await getLimitations();
  const scopeNote = new Map(limitations.rows.map((l) => [l.id, l.scope_note]));

  const byStatus = (s: string) => claims.rows.filter((c) => c.status === s).length;

  return (
    <>
      <h1>Claim ledger</h1>
      <p className="lede">
        Every substantive statement this project makes, with its evidence, the experiment
        that produced it, and the scope it is entitled to. No claim is stated at
        out-of-sample scope, because the holdout is frozen and unevaluated.
      </p>

      {!claims.dataAvailable ? (
        <NoData what="Claim ledger" note={claims.note} />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Claims" value={String(claims.rows.length)} />
            <StatCard label="Supported" value={String(byStatus('SUPPORTED'))} />
            <StatCard label="Partial" value={String(byStatus('PARTIAL'))} />
            <StatCard label="Not supported" value={String(byStatus('NOT_SUPPORTED'))} />
            <StatCard
              label="Out-of-sample claims"
              value="0"
              note="the holdout is frozen"
            />
          </div>

          {claims.rows.map((c) => (
            <article key={c.id} id={c.id} className="card" style={{ marginTop: 14 }}>
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
                  {c.id}
                </span>
                <StatusChip status={c.status as ResearchStatus} />
                <span className="chip">{SCOPE_LABEL[c.scope] ?? c.scope}</span>
              </div>

              <p style={{ margin: '0 0 8px', fontSize: 15 }}>{c.claim}</p>

              <div className="tableWrap">
                <table>
                  <tbody>
                    <tr>
                      <th style={{ width: 150 }}>Evidence</th>
                      <td>{c.evidence}</td>
                    </tr>
                    <tr>
                      <th>Dataset</th>
                      <td className="small">{c.dataset}</td>
                    </tr>
                    <tr>
                      <th>Experiment</th>
                      <td className="small mono">{c.experiment}</td>
                    </tr>
                    <tr>
                      <th>Bounded by</th>
                      <td className="small">
                        {c.limitations.length === 0 ? (
                          <span className="muted">
                            none — this claim does not depend on the dataset
                          </span>
                        ) : (
                          c.limitations.map((l) => (
                            <span key={l} style={{ marginRight: 10 }}>
                              <Link href={`/research/limitations/${l}`}>{l}</Link>{' '}
                              <span className="muted">{scopeNote.get(l) ?? ''}</span>
                            </span>
                          ))
                        )}
                      </td>
                    </tr>
                    {c.figure_ids.length ? (
                      <tr>
                        <th>Figures</th>
                        <td className="small mono">{c.figure_ids.join(', ')}</td>
                      </tr>
                    ) : null}
                    {c.note ? (
                      <tr>
                        <th>Note</th>
                        <td className="small">{c.note}</td>
                      </tr>
                    ) : null}
                    <tr>
                      <th>Blocked compressions</th>
                      <td className="small muted">
                        The claim guard rejects these restatements:{' '}
                        {c.overclaim_examples.map((o) => (
                          <em key={o} style={{ display: 'block' }}>
                            “{o}”
                          </em>
                        ))}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </article>
          ))}

          <section className="boundary">
            <h3>How the guard works</h3>
            <p style={{ margin: 0 }}>
              Claim text is checked against pattern families for real-world assertions,
              generalisation beyond the evaluated split, universal statements in either
              direction, advisory phrasing, readiness claims and assertions of
              anticipation. The ledger is checked against its own rule on every test run,
              and each claim carries example restatements that the guard must catch — so a
              guard that stops working fails a test rather than passing silently.
            </p>
          </section>
        </>
      )}
    </>
  );
}
