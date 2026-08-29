import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { getCoverage, getProvenance, getUniverse, pct } from '@/lib/data';

export const dynamic = 'force-static';

const TIMESTAMPS: [string, string][] = [
  ['event_time', 'When the thing described actually happened.'],
  ['publication_time', 'When a publisher first made it public.'],
  ['knowledge_time', 'When this system could first have acted on this exact value.'],
  ['retrieval_time', 'When it was fetched.'],
];

export default async function DatasetsPage() {
  const provenance = await getProvenance();
  const coverage = await getCoverage();
  const universe = await getUniverse();

  return (
    <>
      <h1>Datasets</h1>
      <p className="lede">
        Every source, its licence, and whether it was used, referenced only, or not
        obtained. Sources that could not be obtained are listed as such rather than
        substituted with something that looks similar.
      </p>

      <div className="grid">
        <StatCard label="Universe" value={universe.name} note={universe.datasetVersion} />
        <StatCard label="Members" value={String(universe.memberCount)} />
        <StatCard
          label="Distinct members ever"
          value={universe.distinctMembersEver ? String(universe.distinctMembersEver) : 'n/a'}
        />
        <StatCard
          label="Index membership"
          value={universe.isIndexMembership ? 'yes' : 'no'}
          note={universe.isIndexMembership ? '' : 'liquidity proxy'}
        />
      </div>

      <h2>Sources</h2>
      {!provenance.dataAvailable ? (
        <NoData what="Provenance table" note={provenance.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Block</th>
                <th>Licence</th>
                <th>Coverage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {provenance.rows.map((p) => (
                <tr key={p.source}>
                  <td>{p.source}</td>
                  <td>{p.block}</td>
                  <td className="muted small">{p.licence}</td>
                  <td className="mono small">{p.coverage}</td>
                  <td className="small">{p.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Block coverage in the assembled dataset</h2>
      {!coverage.dataAvailable ? (
        <NoData what="Coverage summary" note={coverage.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Block</th>
                <th className="num">Coverage</th>
                <th>Status</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {coverage.rows.map((c) => (
                <tr key={String(c.block)}>
                  <td>{String(c.block)}</td>
                  <td className="num">
                    {c.status.startsWith('NOT MEASURED') ? '—' : pct(c.coverage)}
                  </td>
                  <td>{c.status}</td>
                  <td className="muted small">{c.note ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>The four timestamps</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Meaning</th>
            </tr>
          </thead>
          <tbody>
            {TIMESTAMPS.map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ maxWidth: '76ch' }}>
        A restated value shares its event time with the value it replaces but carries a
        later knowledge time. A query as of an earlier cutoff returns the original, not the
        restatement. That is enforced by a leakage test, not by convention — as are five
        further leakage properties covering as-of retrieval, future shift, survivorship,
        block substitution and threshold provenance.
      </p>

      <h2>Source licensing</h2>
      <p className="small">
        Every source passes a licence gate before a byte is processed. A source whose
        licence could not be verified defaults to UNKNOWN and is excluded from every
        redistributable artifact. Declaring an ingestible status without evidence raises an
        error rather than being accepted.
      </p>
      <p className="small">
        <Link href="/research/limitations/L-01">
          Why the universe is a proxy rather than an index →
        </Link>
      </p>
    </>
  );
}
