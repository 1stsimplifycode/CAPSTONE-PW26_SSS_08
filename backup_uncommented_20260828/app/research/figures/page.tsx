import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { getFigures } from '@/lib/data';
import { getFigureIndex, listModules, modulesCitingFigure } from '@/lib/modules';
import type { ModuleFigure, ResearchModule } from '@/lib/modules';
import type { FigureRecord } from '@/lib/types';

export const dynamic = 'force-static';

export const metadata = {
  title: 'Figures — AEGIS-Market',
  description:
    'Every generated figure with its caption, the artifact it was drawn from, and the ' +
    'modules and claims that cite it.',
};

/**
 * The figure explorer.
 *
 * Shows the figures rather than describing them. Each is the file the paper package
 * carries — copied, not re-rendered — so what a reviewer sees here and what a reviewer
 * sees in the paper are the same bytes. Beside each is the artifact it was drawn from and
 * the modules that cite it, which is what makes a figure traceable in both directions.
 */
function FigureGrid({
  figures,
  modules,
}: {
  figures: ModuleFigure[];
  modules: ResearchModule[];
}) {
  if (figures.length === 0) {
    return <p className="muted small">None in the current artifact set.</p>;
  }
  return (
    <div className="figures">
      {figures.map((f) => {
        const citing = modulesCitingFigure(modules, f.figure);
        return (
          <figure key={f.figure} id={f.figure} className="figures__item">
            {f.available && f.url ? (
              <a href={f.url} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={f.url} alt={f.caption ?? f.figure} loading="lazy" />
              </a>
            ) : (
              <div className="figures__missing">Not present in this build.</div>
            )}
            <figcaption>
              <span className="mono">{f.figure}</span>
              <span>{f.caption}</span>
              {f.source_data ? (
                <span className="muted mono small">source: {f.source_data}</span>
              ) : null}
              {citing.length ? (
                <span className="small">
                  cited by{' '}
                  {citing.map((m) => (
                    <Link
                      key={m.id}
                      href={`${m.route}?mode=research`}
                      style={{ marginRight: 8 }}
                    >
                      {m.id}
                    </Link>
                  ))}
                </span>
              ) : null}
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}

/** The paper manifest's own records, which carry the experiment and run identifiers. */
function ManifestList({ list }: { list: FigureRecord[] }) {
  if (list.length === 0) {
    return <p className="muted small">None in the current artifact set.</p>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Figure</th>
            <th>Caption</th>
            <th>Experiment</th>
            <th>Source data</th>
          </tr>
        </thead>
        <tbody>
          {list.map((f) => (
            <tr key={f.figureId}>
              <td className="mono small">
                {f.number ? `${f.number}. ` : ''}
                {f.figureId}
              </td>
              <td className="small">{f.caption}</td>
              <td className="mono small">
                {f.experimentId} · run {f.runId}
              </td>
              <td className="mono small muted">{f.sourceData}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function FiguresPage() {
  const index = await getFigureIndex();
  const modules = await listModules();
  const manifest = await getFigures();

  const consolidated = index.rows.filter((f) => f.figure.startsWith('figC'));
  const research = index.rows.filter((f) => f.figure.startsWith('figR'));
  const affective = index.rows.filter((f) => f.figure.startsWith('figHA'));
  const named = new Set([...consolidated, ...research, ...affective].map((f) => f.figure));
  const paper = index.rows.filter((f) => !named.has(f.figure));

  const main = manifest.rows.filter((f) => f.placement === 'MAIN');
  const supp = manifest.rows.filter((f) => f.placement === 'SUPPLEMENTARY');

  return (
    <>
      <h1>Figures</h1>
      <p className="lede">
        Every figure in the artifact set, shown as the file the paper package carries.
        Each is regenerable from the recorded dataset version, configuration and seed by a
        single command, and each names the artifact it was drawn from.
      </p>

      {!index.dataAvailable ? (
        <NoData
          what="Figure index"
          note="Run python scripts/export_modules.py to copy the generated figures into public/figures/."
        />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Figures" value={String(index.rows.length)} />
            <StatCard
              label="Consolidated"
              value={String(consolidated.length)}
              note="one figure per whole result"
            />
            <StatCard label="Statistics and research angles" value={String(research.length)} />
            <StatCard label="Human affective" value={String(affective.length)} />
          </div>

          <h2>Consolidated figures</h2>
          <p className="muted small">
            Each of these carries a whole result rather than one panel of one: the
            measurement, the diagnostics that rule out the obvious explanations, and the
            mechanism that survives.
          </p>
          <FigureGrid figures={consolidated} modules={modules} />

          <h2>Statistics and research angles</h2>
          <FigureGrid figures={research} modules={modules} />

          <h2>Human affective computing</h2>
          <FigureGrid figures={affective} modules={modules} />

          <h2>Stream A paper figures</h2>
          <FigureGrid figures={paper} modules={modules} />
        </>
      )}

      {manifest.dataAvailable ? (
        <>
          <h2>Paper manifest</h2>
          <p className="muted small">
            The manifest records placement, experiment identifier and run identifier for
            each figure the paper carries.
          </p>
          <h3>Main paper</h3>
          <ManifestList list={main} />
          <h3>Supplementary</h3>
          <ManifestList list={supp} />
        </>
      ) : null}

      <section className="boundary">
        <h3>What is not here</h3>
        <p style={{ margin: 0 }}>
          Figures whose input artifact was missing are recorded as NOT GENERATED in the
          artifact manifest together with the reason. Nothing is drawn from data that does
          not exist, and no figure is a screenshot of this interface.
        </p>
      </section>
    </>
  );
}
