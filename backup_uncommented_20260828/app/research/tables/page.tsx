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
 */
export default async function TablesPage() {
  const tables = await getTableIndex();
  const modules = await listModules();

  const paper = tables.rows.filter((t) => t.source?.startsWith('outputs/'));
  const streamA = tables.rows.filter((t) => !t.source?.startsWith('outputs/'));

  return (
    <>
      <h1>Tables</h1>
      <p className="lede">
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
              label="Cited by a module"
              value={String(
                tables.rows.filter((t) => modulesCitingTable(modules, t.table).length)
                  .length,
              )}
            />
          </div>

          {[
            ['Consolidated paper tables', paper] as const,
            ['Stream A tables', streamA] as const,
          ].map(([title, list]) => (
            <section key={title}>
              <h2>{title}</h2>
              {list.length === 0 ? (
                <p className="muted small">None in the current artifact set.</p>
              ) : (
                list.map((t) => {
                  const citing = modulesCitingTable(modules, t.table);
                  return (
                    <article key={t.table} id={t.table} className="explorer__item">
                      <h3 className="mono">{t.table}</h3>
                      <p>{t.caption ?? 'No caption recorded for this table.'}</p>
                      <dl className="explorer__meta">
                        <div>
                          <dt>Rows</dt>
                          <dd>{t.rows ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Columns</dt>
                          <dd className="mono small">
                            {t.columns?.join(', ') || 'not recorded'}
                          </dd>
                        </div>
                        <div>
                          <dt>Computed from</dt>
                          <dd className="mono small">{t.source ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          <dt>File</dt>
                          <dd className="mono small">{t.path ?? 'not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Revision</dt>
                          <dd className="mono small">
                            {t.git_commit?.slice(0, 8) ?? 'not stamped'}
                          </dd>
                        </div>
                        <div>
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
