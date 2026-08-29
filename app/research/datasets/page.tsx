import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { getCoverage, getProvenance, getUniverse, pct } from '@/lib/data';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * WHERE ALL THE DATA CAME FROM, AND WHAT IS MISSING.
 *
 * The introduction states the rule the whole page follows:
 *
 *     "Sources that could not be obtained are listed as such rather than substituted
 *      with something that looks similar."
 *
 * That last phrase is the important one -- "something that looks similar". The danger is
 * not a blank; it is a plausible stand-in that a reader accepts as the real thing.
 */

export const dynamic = 'force-static';

// THE FOUR TIMESTAMPS, and the plain-English meaning of each. This is the point-in-time
// discipline from the very heart of the research, explained on a page anybody can read.
const TIMESTAMPS: [string, string][] = [
  ['event_time', 'When the thing described actually happened.'],
  ['publication_time', 'When a publisher first made it public.'],
  // The crucial one, and the definition is exact: when THIS SYSTEM could first have acted
  // on THIS EXACT VALUE.
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
          // THE SURVIVORSHIP EVIDENCE, on the front of the page. If far more companies were
          // ever members than are members now, the list genuinely churned -- which is the
          // proof that failed companies were not quietly dropped.
          label="Distinct members ever"
          value={universe.distinctMembersEver ? String(universe.distinctMembersEver) : 'n/a'}
        />
        <StatCard
          // AND THE HONEST "no". A card whose entire purpose is to say this is not an index.
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
                {/* THE LICENCE COLUMN, given equal standing with the data itself. What we
                    are allowed to do with something is as much a property of it as what it
                    contains. */}
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
                  {/* Used, referenced only, or not obtained -- the three honest outcomes. */}
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
                    {/* A DASH FOR "NOT MEASURED", not 0%. The distinction the whole project
                        keeps insisting on: never measured, and measured as nothing, are
                        different facts. */}
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
        {/* THE RESTATEMENT RULE, EXPLAINED TO A READER. A corrected value shares its event
            time with the figure it replaces but was learned later -- so a question about an
            earlier date must return the ORIGINAL, wrong number.
            And the last clause is the one that matters: "enforced by a leakage test, not by
            convention". Six separate leakage properties are named, so a reader can see the
            discipline is machinery rather than good intentions.
            The `maxWidth: '76ch'` keeps the line length comfortable to read -- long lines of
            dense text are genuinely harder to follow. */}
        A restated value shares its event time with the value it replaces but carries a
        later knowledge time. A query as of an earlier cutoff returns the original, not the
        restatement. That is enforced by a leakage test, not by convention — as are five
        further leakage properties covering as-of retrieval, future shift, survivorship,
        block substitution and threshold provenance.
      </p>

      <h2>Source licensing</h2>
      <p className="small">
        {/* THE LICENCE GATE, described to a reader. Three facts:
            every source is checked BEFORE any of it is processed;
            an unverifiable licence defaults to UNKNOWN and is excluded from anything
              redistributable;
            and claiming a permissive status without evidence RAISES AN ERROR rather than
              being accepted -- so the override cannot be used casually. */}
        Every source passes a licence gate before a byte is processed. A source whose
        licence could not be verified defaults to UNKNOWN and is excluded from every
        redistributable artifact. Declaring an ingestible status without evidence raises an
        error rather than being accepted.
      </p>
      <p className="small">
        {/* A link straight to the limitation explaining the universe substitution -- so the
            "no" on the card above leads somewhere that explains it. */}
        <Link href="/research/limitations/L-01">
          Why the universe is a proxy rather than an index →
        </Link>
      </p>
    </>
  );
}
