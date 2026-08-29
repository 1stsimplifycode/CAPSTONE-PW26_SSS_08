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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * EVERY CHART THE PROJECT PRODUCED, SHOWN RATHER THAN DESCRIBED.
 *
 * AND THE PHRASE THAT MATTERS IS "copied, not re-rendered ... the same bytes".
 * The image on this page is the identical file that goes into the paper. Not a version
 * redrawn for the web, not a recompressed copy -- the same bytes.
 * So a reviewer comparing the website against the paper is comparing a thing with itself.
 * Any re-rendering, however faithful, would introduce the possibility of a difference.
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
        // WHICH MODULES CITE THIS FIGURE -- the backward link, which tells a reader whether
        // anything actually depends on it.
        const citing = modulesCitingFigure(modules, f.figure);
        return (
          // `id` so another page can link straight to one figure.
          <figure key={f.figure} id={f.figure} className="figures__item">
            {f.available && f.url ? (
              <a href={f.url} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {/* A plain image tag on purpose -- the optimised component would recompress
                    the file, and then it would no longer be the same bytes as the paper's. */}
                <img src={f.url} alt={f.caption ?? f.figure} loading="lazy" />
              </a>
            ) : (
              // Missing: says so plainly rather than showing a broken image.
              <div className="figures__missing">Not present in this build.</div>
            )}
            <figcaption>
              {/* THE FULL TRACE, under every figure: its identifier, its caption, the data it
                  was drawn from, and everything that cites it. */}
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
// A second, separate view -- the manifest's own record of each figure, which carries the
// experiment and run that produced it. The picture and its provenance kept as two views of
// the same thing, so neither has to be crowded into the other.
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
                {/* The paper's figure number where it has one -- so a reader holding the
                    paper can find the same figure here. */}
                {f.number ? `${f.number}. ` : ''}
                {f.figureId}
              </td>
              <td className="small">{f.caption}</td>
              <td className="mono small">
                {/* THE EXPERIMENT AND THE RUN. So a figure can be traced to the exact
                    execution that produced it, not merely to a script. */}
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

  // Sorted into families by their filename prefix -- consolidated, research, affective --
  // so the page reads as sections rather than one undifferentiated wall of images.
  const consolidated = index.rows.filter((f) => f.figure.startsWith('figC'));
  const research = index.rows.filter((f) => f.figure.startsWith('figR'));
  const affective = index.rows.filter((f) => f.figure.startsWith('figHA'));
  // And whatever is left over. Building the "rest" from what was NOT already named means a
  // new figure family cannot silently disappear from the page.
  const named = new Set([...consolidated, ...research, ...affective].map((f) => f.figure));
  const paper = index.rows.filter((f) => !named.has(f.figure));

  const main = manifest.rows.filter((f) => f.placement === 'MAIN');
  const supp = manifest.rows.filter((f) => f.placement === 'SUPPLEMENTARY');

  return (
    <>
      <h1>Figures</h1>
      <p className="lede">
        {/* The reproducibility promise, applied to pictures: each is regenerable from the
            recorded dataset version, configuration and seed by ONE command -- and each names
            the file it was drawn from. */}
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
            {/* A DESCRIPTION OF WHAT A GOOD FIGURE CONTAINS, and it is a high standard:
                the measurement, the DIAGNOSTICS THAT RULE OUT THE OBVIOUS EXPLANATIONS, and
                the mechanism that survives.
                A figure that shows only the result, without the checks that eliminate the
                boring explanations, is asking to be believed rather than examined. */}
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
          {/* Main paper and supplementary kept apart, because where a figure sits changes how
              much weight a reader should give it. */}
          <h3>Main paper</h3>
          <ManifestList list={main} />
          <h3>Supplementary</h3>
          <ManifestList list={supp} />
        </>
      ) : null}

      <section className="boundary">
        {/* TWO CLOSING GUARANTEES, and the second is unusual enough to be worth noticing.
            1. A figure whose input was missing is recorded as NOT GENERATED, with the reason.
               Nothing is drawn from data that does not exist.
            2. "no figure is a screenshot of this interface" -- meaning every figure came out
               of the research pipeline, not out of somebody photographing a web page. A
               screenshot would look identical and would have no provenance whatsoever. */}
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
