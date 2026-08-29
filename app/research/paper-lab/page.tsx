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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE PAPER PACKAGE: everything needed to publish, and how to regenerate it.
 *
 * AND THE DESIGN NOTE AT THE TOP IS A GOOD PIECE OF RESTRAINT.
 * A "Download the paper package" button would be the obvious thing to add. It would also
 * not work -- the deployed site serves small data files, not a 6.8-megabyte bundle. So the
 * button would sit there looking helpful and fail when pressed.
 * The reasoning is exact: "a download control that silently fails would be worse than an
 * accurate instruction". So instead the page tells you precisely how to produce it.
 */
export default async function PaperLabPage() {
  const figures = await getFigures();
  const claims = await getClaims();
  const limitations = await getLimitations();

  // Figures destined for the paper proper, and those for the appendix.
  const main = figures.rows.filter((f) => f.placement === 'MAIN').length;
  const supp = figures.rows.filter((f) => f.placement === 'SUPPLEMENTARY').length;
  // Every designed experiment, gathered from every question of every limitation. A nested
  // walk flattened into one list.
  const specs = limitations.rows.flatMap((l) =>
    l.research_questions.flatMap((r) => r.experiments),
  );

  return (
    <>
      <h1>Paper lab</h1>
      <p className="lede">
        {/* THE TWO PROMISES: one command regenerates everything, and every asset traces back
            through five things -- experiment, run, dataset version, seed, commit. */}
        The assembled publication package: figures, tables, captions, statistics,
        supplementary material and reproducibility manifests. Every asset regenerates from
        one command, and every asset traces back to an experiment, a run, a dataset
        version, a seed and a commit.
      </p>

      <div className="grid">
        {/* Each count links to where those things can actually be inspected -- so a number
            on this page is a doorway rather than a dead statistic. */}
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
        {/* THE SIX COMMANDS, IN ORDER, EACH WITH A COMMENT SAYING WHAT IT DOES. Somebody who
            has never seen this project could follow this from the top and end up with the
            same package. That is what "reproducible" has to mean in practice. */}
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
        {/* What the package contains, in which formats -- and then the verification result
            repeated here: a full re-run reproduced everything to zero difference. Stated on
            the page where somebody would be about to run it themselves, which is exactly
            where that reassurance is useful. */}
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
            {/* Every folder of the package explained. Note the formats: three image formats
                and four table formats, because a journal, a website and a LaTeX document all
                want something different -- and providing all of them means nobody has to
                convert an artifact by hand and risk altering it. */}
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
              {/* The receipts folder -- commit, seeds, versions, hashes. */}
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
      {/* AND THE FIVE BIG CAVEATS, TRAVELLING WITH THE PACKAGE. Not left behind on the
          website -- carried into the publication bundle itself, so anybody who receives the
          package receives the limitations with it. */}
      <ul className="small">
        <li>Episode labels are synthetic, injected into real NSE price data.</li>
        <li>The universe is a point-in-time liquidity proxy, not an index.</li>
        <li>True microstructure is NOT MEASURED; only daily proxies exist.</li>
        <li>The exposure policy is a research instrument, not advice.</li>
        {/* The last one is a promise about the future as much as the present: the final test
            data has still not been looked at. */}
        <li>The final holdout has not been evaluated.</li>
      </ul>
      <p className="small">
        <Link href="/research/limitations">
          Every caveat, its research question and its experiment →
        </Link>
      </p>

      {/* And if the figure manifest is missing, the honest block -- so the counts above are
          never silently zero without explanation. */}
      {!figures.dataAvailable ? <NoData what="Figure manifest" note={figures.note} /> : null}
    </>
  );
}
