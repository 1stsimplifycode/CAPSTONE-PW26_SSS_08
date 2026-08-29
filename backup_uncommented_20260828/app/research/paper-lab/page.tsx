import Link from 'next/link';

import { NoData, StatCard } from '@/components/ui/Primitives';
import { getClaims, getFigures, getLimitations } from '@/lib/data';

export const dynamic = 'force-static';

/**
 * Paper lab (spec sections 68, 143).
 *
 * Downloads are intentionally described rather than offered as buttons: the deployed app
 * serves exported JSON, not the 6.8 MB artifact bundle, and a download control that
 * silently fails would be worse than an accurate instruction. The paper package is
 * produced by one command and lives in the repository.
 */
export default async function PaperLabPage() {
  const figures = await getFigures();
  const claims = await getClaims();
  const limitations = await getLimitations();

  const main = figures.rows.filter((f) => f.placement === 'MAIN').length;
  const supp = figures.rows.filter((f) => f.placement === 'SUPPLEMENTARY').length;
  const specs = limitations.rows.flatMap((l) =>
    l.research_questions.flatMap((r) => r.experiments),
  );

  return (
    <>
      <h1>Paper lab</h1>
      <p className="lede">
        The assembled publication package: figures, tables, captions, statistics,
        supplementary material and reproducibility manifests. Every asset regenerates from
        one command, and every asset traces back to an experiment, a run, a dataset
        version, a seed and a commit.
      </p>

      <div className="grid">
        <StatCard label="Main figures" value={String(main)} href="/research/figures" />
        <StatCard label="Supplementary figures" value={String(supp)} />
        <StatCard label="Claims" value={String(claims.rows.length)} href="/research/claims" />
        <StatCard
          label="Experiment specifications"
          value={String(specs.length)}
          href="/research/limitations"
        />
      </div>

      <h2>Regenerating the package</h2>
      <div className="card">
        <pre
          className="mono"
          style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}
        >{`python scripts/build_panel.py            # NSE panel + point-in-time universe
python scripts/build_dataset.py          # assembled market panel
python scripts/run_experiments.py        # 28 ablation arms + statistics
python scripts/run_research_angles.py    # the runnable research angles
python scripts/generate_paper_artifacts.py
python scripts/export_app_data.py        # what this application reads`}</pre>
      </div>
      <p className="small muted">
        The artifact generator writes <code>paper_package/</code> containing figures in
        png, pdf and svg; tables in csv, json, markdown and LaTeX; per-figure captions in
        markdown and LaTeX; statistics; and the reproducibility manifests. A full re-run
        reproduced all 8 arms and 7 statistical tests to a maximum absolute difference
        of 0.000e+00.
      </p>

      <h2>Contents</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Directory</th>
              <th>Contents</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="mono">figures/</td>
              <td>main-paper figures, three formats each</td>
            </tr>
            <tr>
              <td className="mono">supplementary/</td>
              <td>supplementary figures</td>
            </tr>
            <tr>
              <td className="mono">tables/</td>
              <td>every table as csv, json, markdown and LaTeX</td>
            </tr>
            <tr>
              <td className="mono">captions/</td>
              <td>per-figure caption, LaTeX snippet and metadata</td>
            </tr>
            <tr>
              <td className="mono">statistics/</td>
              <td>the numeric outputs backing every claim</td>
            </tr>
            <tr>
              <td className="mono">reproducibility/</td>
              <td>commit, seeds, package versions, dataset hashes</td>
            </tr>
            <tr>
              <td className="mono">latex/</td>
              <td>ready-to-include figure and table snippets</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Standing caveats carried into the package</h2>
      <ul className="small">
        <li>Episode labels are synthetic, injected into real NSE price data.</li>
        <li>The universe is a point-in-time liquidity proxy, not an index.</li>
        <li>True microstructure is NOT MEASURED; only daily proxies exist.</li>
        <li>The exposure policy is a research instrument, not advice.</li>
        <li>The final holdout has not been evaluated.</li>
      </ul>
      <p className="small">
        <Link href="/research/limitations">
          Every caveat, its research question and its experiment →
        </Link>
      </p>

      {!figures.dataAvailable ? <NoData what="Figure manifest" note={figures.note} /> : null}
    </>
  );
}
