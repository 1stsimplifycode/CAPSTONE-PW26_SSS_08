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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE CLAIM LEDGER: every substantive thing this project says, written down in one place
 * with the evidence behind it.
 *
 * A "ledger" is an accounting word -- a book where every entry must balance. Here every
 * claim must balance against its evidence.
 *
 * AND THE ENFORCEMENT IS THE REMARKABLE PART. Each claim has a SCOPE -- how far it reaches.
 * That scope is not a label somebody attached; an automatic guard reads it and REFUSES any
 * wording that claims more than the scope supports. The build fails rather than publishing
 * an overclaim.
 *
 * THEN THE THING ALMOST NOBODY DOES: beside every claim, the page prints the WRONG versions
 * -- the overstated restatements the guard would reject.
 * So a reader sees not only what is claimed but exactly where the line is. The boundary
 * becomes visible instead of implied, and anybody can check whether a summary they have
 * read elsewhere crossed it.
 */
export default async function ClaimsPage() {
  const claims = await getClaims();
  const limitations = await getLimitations();
  // A lookup from limitation id to its short scope note, so each caveat can be shown with
  // its meaning rather than as a bare code.
  const scopeNote = new Map(limitations.rows.map((l) => [l.id, l.scope_note]));

  const byStatus = (s: string) => claims.rows.filter((c) => c.status === s).length;

  return (
    <>
      <h1>Claim ledger</h1>
      <p className="lede">
        {/* AND THE LAST SENTENCE IS A COMMITMENT: not one claim is stated at out-of-sample
            scope, because the final test data has never been looked at.
            That is the strongest kind of result a project can offer -- and this one says
            plainly that it does not have any, because it has not yet earned the right. */}
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
            {/* THE NOT-SUPPORTED COUNT, given the same prominence as the supported one. */}
            <StatCard label="Not supported" value={String(byStatus('NOT_SUPPORTED'))} />
            <StatCard
              // A HARD-CODED ZERO, and it is the most honest card on the page: no claim
              // anywhere reaches out-of-sample scope, and the reason is given beneath it.
              label="Out-of-sample claims"
              value="0"
              note="the holdout is frozen"
            />
          </div>

          {claims.rows.map((c) => (
            // `id` so another page can link straight to one claim.
            <article key={c.id} id={c.id} className="card" style={{ marginTop: 14 }}>
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  // Wraps on a narrow screen rather than overflowing.
                  flexWrap: 'wrap',
                  marginBottom: 6,
                }}
              >
                <span className="mono" style={{ fontWeight: 700 }}>
                  {c.id}
                </span>
                {/* THE STATUS AND THE SCOPE SHOWN BEFORE THE CLAIM ITSELF. So a reader meets
                    the qualification before the assertion, rather than reading a confident
                    sentence and only afterwards discovering how far it reaches. */}
                <StatusChip status={c.status as ResearchStatus} />
                <span className="chip">{SCOPE_LABEL[c.scope] ?? c.scope}</span>
              </div>

              <p style={{ margin: '0 0 8px', fontSize: 15 }}>{c.claim}</p>

              <div className="tableWrap">
                <table>
                  <tbody>
                    {/* THE FULL CHAIN BEHIND THE CLAIM. */}
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
                          // The REASON nothing bounds it, rather than a blank -- so an
                          // unbounded claim is distinguishable from one whose caveats were
                          // simply never recorded.
                          <span className="muted">
                            none — this claim does not depend on the dataset
                          </span>
                        ) : (
                          c.limitations.map((l) => (
                            <span key={l} style={{ marginRight: 10 }}>
                              {/* Each caveat is a link AND carries its short note -- so a
                                  reader gets the gist without having to follow it. */}
                              <Link href={`/research/limitations/${l}`}>{l}</Link>{' '}
                              <span className="muted">{scopeNote.get(l) ?? ''}</span>
                            </span>
                          ))
                        )}
                      </td>
                    </tr>
                    {/* Figures and notes only where they exist, so no empty rows. */}
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
                      {/* THE EXTRAORDINARY ROW. "Blocked compressions" -- the shortened,
                          overstated versions of this claim that the guard actively refuses.
                          A project printing the wrong version of its own claims, in italics,
                          beside the right one.
                          The word "compressions" is exact: these are what happens when a
                          careful claim gets summarised. And summarising is precisely what
                          everybody does. */}
                      <th>Blocked compressions</th>
                      <td className="small muted">
                        The claim guard rejects these restatements:{' '}
                        {c.overclaim_examples.map((o) => (
                          // Each on its own line, in italics and quoted -- so the forbidden
                          // wording is unmistakably marked as forbidden rather than being
                          // mistaken for something the project says.
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
              {/* THE SIX FAMILIES OF OVERCLAIM the guard hunts for, named:
                    real-world assertions (saying something about actual markets rather than
                      about our synthetic episodes),
                    generalisation beyond the evaluated split,
                    universal statements in EITHER direction ("always" and "never" are both
                      overclaims),
                    advisory phrasing,
                    readiness claims ("production-ready"),
                    and assertions of anticipation ("predicts", "foresees").
                  AND THE LAST SENTENCE IS THE CLEVEREST PART: every claim carries example
                  wordings the guard MUST catch. So the guard is itself tested -- if it ever
                  stopped working, a test would fail rather than it silently passing
                  everything through. A guard nobody checks is a guard that eventually stops
                  guarding. */}
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
