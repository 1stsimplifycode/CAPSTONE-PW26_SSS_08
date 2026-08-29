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

interface ArtifactRow {
  path: string;
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
 */
export default async function ArtifactsPage() {
  const modules = await listModules();

  const index = new Map<string, ArtifactRow>();
  const touch = (path: string, kind: string): ArtifactRow => {
    if (!index.has(path)) {
      index.set(path, { path, producers: [], consumers: [], kind });
    }
    return index.get(path)!;
  };

  for (const m of modules) {
    const ref = { id: m.id, route: m.route };
    for (const out of m.research.outputs) {
      touch(out, out.split('.').pop() ?? 'file').producers.push(ref);
    }
    for (const inp of m.research.inputs) {
      touch(inp, inp.split('.').pop() ?? 'file').consumers.push(ref);
    }
    // A metric expression names an artifact the module reads even when the manifest does
    // not declare it as an input, and those reads are exactly what the interface renders.
    for (const metric of [...m.product.metrics, ...m.research.metrics]) {
      if (!metric.source) continue;
      const row = touch(metric.source, metric.source.split('.').pop() ?? 'file');
      if (!row.consumers.some((c) => c.id === m.id)) row.consumers.push(ref);
    }
  }

  const rows = [...index.values()].sort((a, b) => a.path.localeCompare(b.path));
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
                            <Link
                              key={p.id}
                              href={`${p.route}?mode=research`}
                              style={{ marginRight: 8 }}
                            >
                              {p.id}
                            </Link>
                          ))
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
