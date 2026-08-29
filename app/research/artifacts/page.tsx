import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { listModules } from '@/lib/modules';

export const dynamic = 'force-static';

export const metadata = {
  title: 'Artifacts — AEGIS-Market',
  description:
    'Every file the research pipeline wrote that a module reads, with the command that ' +
    'regenerates it and the modules that consume it.',
};

// One file, with the modules on either side of it.
interface ArtifactRow {
  path: string;
  // Which modules WRITE it, and which READ it. Both directions.
  producers: { id: string; route: string }[];
  consumers: { id: string; route: string }[];
  kind: string;
}

/**
 * The artifact explorer: the seam between the research pipeline and this interface.
 *
 * Two directions, both useful. Downward, from a module to the files it wrote. Upward,
 * from a file to every module that reads it — which is how someone finds out what a
 * regeneration would change before running it.
 *
 * No file contents are served here. The explorer lists paths, producers, consumers and
 * the command that rebuilds each; reading a raw artifact is a repository operation, not
 * a web one, and shipping arbitrary file contents through a public route would be a way
 * to leak something that was never meant to be published.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * EVERY RESULT FILE, AND WHO WRITES AND READS IT.
 *
 * THE UPWARD DIRECTION IS THE GENUINELY USEFUL ONE, and the reason is given: it tells you
 * "what a regeneration would change BEFORE running it".
 * You are about to rebuild one file. Which parts of the project depend on it? Without this
 * page you would find out afterwards, when something you did not expect had changed.
 *
 * AND THE SECURITY DECISION IN THE SECOND PARAGRAPH IS EXACTLY RIGHT.
 * The page lists file paths. It does not serve file CONTENTS. Adding a "view this file"
 * feature would be easy, useful, and would create a route through which any file could be
 * fetched -- which is a way to publish something nobody ever decided to publish.
 * Reading a file is described as "a repository operation, not a web one". The boundary is
 * drawn where it should be.
 */
export default async function ArtifactsPage() {
  const modules = await listModules();

  // Build the index by walking every module and noting what it touches.
  const index = new Map<string, ArtifactRow>();
  // A small helper: fetch the entry for a path, creating it if this is the first mention.
  const touch = (path: string, kind: string): ArtifactRow => {
    if (!index.has(path)) {
      index.set(path, { path, producers: [], consumers: [], kind });
    }
    return index.get(path)!;
  };

  for (const m of modules) {
    const ref = { id: m.id, route: m.route };
    // What it writes...
    for (const out of m.research.outputs) {
      // The kind taken from the file extension -- "json", "csv", "parquet".
      touch(out, out.split('.').pop() ?? 'file').producers.push(ref);
    }
    // ...and what it reads.
    for (const inp of m.research.inputs) {
      touch(inp, inp.split('.').pop() ?? 'file').consumers.push(ref);
    }
    // A metric expression names an artifact the module reads even when the manifest does
    // not declare it as an input, and those reads are exactly what the interface renders.
    // PLAIN ENGLISH: a thorough catch. A module may pull a single number out of a file
    // without that file being listed among its formal inputs. Those reads are precisely the
    // ones the website displays -- so missing them would leave the most visible dependencies
    // out of the dependency map.
    for (const metric of [...m.product.metrics, ...m.research.metrics]) {
      if (!metric.source) continue;
      const row = touch(metric.source, metric.source.split('.').pop() ?? 'file');
      // Only added if not already there, so a module reading five numbers from one file is
      // listed once rather than five times.
      if (!row.consumers.some((c) => c.id === m.id)) row.consumers.push(ref);
    }
  }

  // Alphabetical, so the list reads the same every time.
  const rows = [...index.values()].sort((a, b) => a.path.localeCompare(b.path));
  // Files nothing here writes -- inputs that came from further upstream.
  const orphans = rows.filter((r) => r.producers.length === 0);

  return (
    <>
      <h1>Artifacts</h1>
      <p className="lede">
        Every file the module layer produces or reads, with the modules on each side of
        it. Contents are not served: this page names paths and provenance, and reading a
        file is a repository operation.
      </p>

      {modules.length === 0 ? (
        <NoData
          what="Module manifest"
          note="Run python scripts/export_modules.py to populate public/data/modules.json."
        />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Artifacts" value={String(rows.length)} />
            <StatCard
              label="Produced by a module"
              value={String(rows.length - orphans.length)}
            />
            <StatCard
              // The upstream inputs, counted and EXPLAINED -- so a file with no producer
              // reads as "built earlier in the pipeline" rather than as a dangling reference.
              label="Read but not produced here"
              value={String(orphans.length)}
              note="upstream inputs, built by the dataset pipeline"
            />
            <StatCard label="Modules" value={String(modules.length)} />
          </div>

          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Artifact</th>
                  <th>Kind</th>
                  {/* Plain words rather than jargon: "Written by" and "Read by" instead of
                      "producers" and "consumers". */}
                  <th>Written by</th>
                  <th>Read by</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.path}>
                    <td className="mono small">{r.path}</td>
                    <td>
                      <span className="chip">{r.kind}</span>
                    </td>
                    <td className="small">
                      {r.producers.length
                        ? r.producers.map((p) => (
                            // Every module is a link straight to its research view.
                            <Link
                              key={p.id}
                              href={`${p.route}?mode=research`}
                              style={{ marginRight: 8 }}
                            >
                              {p.id}
                            </Link>
                          ))
                        // "— upstream" rather than a blank: it says WHY nothing here wrote
                        // this file.
                        : '— upstream'}
                    </td>
                    <td className="small">
                      {r.consumers.length
                        ? r.consumers.map((c) => (
                            <Link
                              key={c.id}
                              href={`${c.route}?mode=research`}
                              style={{ marginRight: 8 }}
                            >
                              {c.id}
                            </Link>
                          ))
                        // A file nothing reads. Worth knowing -- it may be dead weight.
                        : '— none'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <section className="boundary">
        <h3>Regenerating an artifact</h3>
        <p style={{ margin: 0 }}>
          {/* THE TWO COMMANDS -- rebuild, then re-export so it becomes visible here.
              AND THE PROTECTED-ARTIFACT RULE explained at the point a reader is most likely
              to try it: some modules refuse without `--force`, because regenerating them
              would overwrite results the claim ledger already cites.
              So the refusal is explained BEFORE somebody meets it, rather than as a
              frustrating error afterwards. */}
          <code>python scripts/run_module.py --module &lt;ID&gt;</code> rebuilds a
          module&apos;s outputs, and <code>python scripts/export_modules.py</code> makes
          them visible here. Modules whose wrapper status is
          <code>WRAPS_EXISTING_PROTECTED</code> refuse to run without <code>--force</code>,
          because regenerating them would overwrite artifacts the claim ledger already
          cites.
        </p>
      </section>
    </>
  );
}
