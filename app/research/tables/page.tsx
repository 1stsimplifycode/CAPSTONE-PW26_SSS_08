import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { getTableIndex, listModules, modulesCitingTable } from '@/lib/modules';

export const dynamic = 'force-static';

export const metadata = {
  title: 'Tables — AEGIS-Market',
  description:
    'Every generated table, the artifact it was computed from, and the modules and ' +
    'claims that cite it.',
};

/**
 * The table explorer.
 *
 * Each row names the artifact the table was computed from, so a reviewer can go from a
 * number in the paper to the file that produced it without asking. The reverse direction
 * matters as much: the modules and claims that cite a table are listed beside it, which
 * is how a reader finds out whether a table is load-bearing or decorative.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * EVERY TABLE THE PROJECT PRODUCED, AND THE LINKS IN BOTH DIRECTIONS.
 *
 * FORWARDS: from a table, which file produced it. So a reviewer who sees a number in the
 * paper can find the exact source "without asking" -- which is the difference between
 * reproducible and merely well-intentioned.
 *
 * BACKWARDS, AND THIS IS THE CLEVERER HALF: which modules CITE this table.
 * That answers a question nobody usually thinks to ask -- is this table load-bearing, or
 * decorative? A table nothing cites may still be interesting, but nothing depends on it.
 * A table three claims rest on matters a great deal more.
 */
export default async function TablesPage() {
  const tables = await getTableIndex();
  const modules = await listModules();

  // Split by where they live: the consolidated set destined for the paper, and the working
  // research set. Two different purposes, so two sections rather than one long list.
  const paper = tables.rows.filter((t) => t.source?.startsWith('outputs/'));
  const streamA = tables.rows.filter((t) => !t.source?.startsWith('outputs/'));

  return (
    <>
      <h1>Tables</h1>
      <p className="lede">
        {/* AND THE SAME PRINCIPLE AGAIN, applied to tables this time: a table whose source
            was missing is recorded as NOT GENERATED rather than written out empty --
            "an empty table in a paper directory reads as a result of zero."
            Somebody opening the paper package would find a table of nothing and conclude
            the measurement came out at zero. */}
        Every table the pipeline generated, with the artifact it was computed from and the
        modules and claims that cite it. A table whose source artifact was missing is
        recorded as NOT GENERATED in the table manifest rather than emitted empty: an
        empty table in a paper directory reads as a result of zero.
      </p>

      {!tables.dataAvailable ? (
        <NoData what="Table index" note={tables.note} />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Tables" value={String(tables.rows.length)} />
            {/* The two sets counted separately, each naming the folder it lives in -- so a
                reader can go and find them. */}
            <StatCard
              label="Consolidated paper set"
              value={String(paper.length)}
              note="outputs/paper_tables"
            />
            <StatCard
              label="Stream A set"
              value={String(streamA.length)}
              note="research_artifacts/tables"
            />
            <StatCard
              // HOW MANY ARE ACTUALLY CITED. A revealing number: the gap between this and
              // the total is the number of tables nothing depends on.
              label="Cited by a module"
              value={String(
                tables.rows.filter((t) => modulesCitingTable(modules, t.table).length)
                  .length,
              )}
            />
          </div>

          {/* Both sections rendered by the same code, so they cannot present the same
              information differently. `as const` keeps the types precise through the loop. */}
          {[
            ['Consolidated paper tables', paper] as const,
            ['Stream A tables', streamA] as const,
          ].map(([title, list]) => (
            <section key={title}>
              <h2>{title}</h2>
              {list.length === 0 ? (
                // An empty section says so rather than vanishing -- so a reader knows the
                // category exists and is currently empty, rather than never noticing it.
                <p className="muted small">None in the current artifact set.</p>
              ) : (
                list.map((t) => {
                  const citing = modulesCitingTable(modules, t.table);
                  return (
                    // `id` on the article means another page can link straight to one table
                    // with a #anchor.
                    <article key={t.table} id={t.table} className="explorer__item">
                      <h3 className="mono">{t.table}</h3>
                      {/* A missing caption says so rather than leaving a blank paragraph. */}
                      <p>{t.caption ?? 'No caption recorded for this table.'}</p>
                      <dl className="explorer__meta">
                        <div>
                          <dt>Rows</dt>
                          {/* "not recorded" throughout, rather than dashes -- so an absent
                              fact is distinguishable from a fact that is genuinely empty. */}
                          <dd>{t.rows ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Columns</dt>
                          <dd className="mono small">
                            {t.columns?.join(', ') || 'not recorded'}
                          </dd>
                        </div>
                        <div>
                          {/* THE FORWARD LINK: which file produced this table. */}
                          <dt>Computed from</dt>
                          <dd className="mono small">{t.source ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          <dt>File</dt>
                          <dd className="mono small">{t.path ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          {/* The code version it was made at -- so a table can be matched to
                              the exact state of the project that produced it. */}
                          <dt>Revision</dt>
                          <dd className="mono small">
                            {t.git_commit?.slice(0, 8) ?? 'not stamped'}
                          </dd>
                        </div>
                        <div>
                          {/* THE BACKWARD LINK: which modules depend on this table, each one
                              a link. And "no module" written out where nothing does -- which
                              is itself a finding about that table. */}
                          <dt>Cited by</dt>
                          <dd>
                            {citing.length
                              ? citing.map((m) => (
                                  <Link
                                    key={m.id}
                                    href={`${m.route}?mode=research`}
                                    style={{ marginRight: 10 }}
                                  >
                                    {m.id}
                                  </Link>
                                ))
                              : 'no module'}
                          </dd>
                        </div>
                      </dl>
                    </article>
                  );
                })
              )}
            </section>
          ))}
        </>
      )}

      <section className="boundary">
        {/* A SHARP CLOSING DISTINCTION, and one very rarely made.
            A table is a faithful copy of a result file. That is ALL it is.
            It is not evidence that the file answers the question the reader has in mind --
            and a well-formatted table is enormously persuasive regardless of whether it is
            about the right thing.
            So the page points at the claim ledger, which is where a number is actually tied
            to a claim, a scope and the limitations bounding it. */}
        <h3>What a table does not tell you</h3>
        <p style={{ margin: 0 }}>
          A generated table is a faithful rendering of an artifact. It is not evidence
          that the artifact answers the question a reader has in mind. The claim ledger is
          where a number is tied to a claim, a scope and the limitations that bound it.
        </p>
      </section>
    </>
  );
}
