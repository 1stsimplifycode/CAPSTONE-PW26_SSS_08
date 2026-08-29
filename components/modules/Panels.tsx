/**
 * The panels both module experiences are assembled from.
 *
 * Product mode and Research mode use the *same* panels wherever the content is the same
 * thing at two depths — a metric is a metric — and different panels only where research
 * mode adds a layer that has no product equivalent, such as the artifact provenance
 * table. That is deliberate: two component trees would be two places for the number to
 * drift.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE BUILDING BLOCKS OF A MODULE PAGE.
 *
 * AND THE RULE IS: SHARE A PANEL WHENEVER THE CONTENT IS THE SAME THING.
 * A metric is a metric. The simple view and the detailed view show it with different
 * amounts of surrounding detail -- but it is ONE component, so the number cannot come out
 * differently in the two.
 * Separate panels exist only where research mode genuinely adds something with no simple
 * equivalent, such as the file-provenance table.
 * The reason is stated plainly: two component trees would be "two places for the number to
 * drift".
 */
import Link from 'next/link';

import type {
  ModuleClaim,
  ModuleFigure,
  ModuleInput,
  ModuleLimitation,
  ModuleMetric,
  ModuleRun,
  ModuleTable,
  ResearchModule,
} from '@/lib/moduleTypes';
import { CONFIDENCE_COPY, CONFIDENCE_TONE, PRODUCT_STATUS_COPY } from '@/lib/moduleTypes';

/* -- metrics ------------------------------------------------------------------------- */

// One number, as a card.
export function MetricCard({
  metric,
  // Research mode switches this on to reveal where the number came from.
  showExpression = false,
}: {
  metric: ModuleMetric;
  showExpression?: boolean;
}) {
  return (
    <div className="card metricCard">
      <div className="card__label">{metric.label}</div>
      {metric.unavailable ? (
        <>
          {/* NOT AVAILABLE, WITH THE REASON. Muted styling so it does not shout, but the
              card still occupies its place -- a missing number is visible rather than an
              absence in the grid. */}
          <div className="card__value card__value--muted">not available</div>
          <div className="card__note">{metric.unavailable}</div>
        </>
      ) : (
        <>
          <div className="card__value">{metric.display}</div>
          {metric.note ? <div className="card__note">{metric.note}</div> : null}
        </>
      )}
      {showExpression ? (
        // THE FILE AND THE EXACT LOOKUP. So a researcher can go and find this number
        // themselves rather than trusting the card. `'no artifact'` where the value was
        // computed rather than read.
        <div className="metricCard__source mono">
          {metric.source ?? 'no artifact'}
          <span className="metricCard__expr">{metric.expression}</span>
        </div>
      ) : null}
    </div>
  );
}

// A grid of numbers.
export function MetricGrid({
  metrics,
  showExpression = false,
}: {
  metrics: ModuleMetric[];
  showExpression?: boolean;
}) {
  if (metrics.length === 0) {
    // "Reports no scalar metric" -- a statement about what this module produces, not a
    // failure. Some modules genuinely produce charts rather than a single number.
    return <p className="muted small">This module reports no scalar metric.</p>;
  }
  return (
    <div className="grid">
      {metrics.map((m) => (
        <MetricCard key={m.label} metric={m} showExpression={showExpression} />
      ))}
    </div>
  );
}

/** Research mode: the same numbers with their lookup, so a reader can check them. */
// "The SAME numbers" -- not recomputed, not reformatted. The same values, in a table that
// adds two columns: where each came from, and how it was fetched.
export function ResearchMetricTable({ metrics }: { metrics: ModuleMetric[] }) {
  if (metrics.length === 0) {
    return <p className="muted small">No research metric is declared for this module.</p>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Quantity</th>
            <th className="num">Value</th>
            {/* THE TWO COLUMNS THAT MAKE IT CHECKABLE: which file, and which lookup inside it. */}
            <th>Artifact</th>
            <th>Lookup</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.label}>
              <td>{m.label}</td>
              <td className="num">{m.unavailable ? '—' : m.display}</td>
              <td className="small mono">{m.source ?? '—'}</td>
              <td className="small mono muted">
                {/* For an unavailable value, the REASON occupies the lookup column -- so the
                    row explains itself rather than showing two dashes.
                    `.split('#')[1]` takes the part after the hash, which is the lookup
                    itself without the file path repeated from the previous column. */}
                {m.unavailable ? m.unavailable : m.expression.split('#')[1]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -- product-mode framing ------------------------------------------------------------ */

// How far the result goes.
export function UncertaintyCard({ module: mod }: { module: ResearchModule }) {
  const conf = CONFIDENCE_COPY[mod.product.confidence];
  const tone = CONFIDENCE_TONE[mod.product.confidence];
  return (
    <section className={`uncertainty uncertainty--${tone}`}>
      {/* The reader's own question as the heading. */}
      <h3>How far this goes</h3>
      {/* Three lines: the level, what that level MEANS, and what it puts at risk. The
          middle one is what stops "moderate confidence" being a phrase the reader has to
          interpret for themselves. */}
      <p className="uncertainty__level">{conf.label}</p>
      <p className="uncertainty__meaning">{conf.meaning}</p>
      <p className="uncertainty__risk">{mod.product.risk}</p>
    </section>
  );
}

// What evidence lies behind this module.
export function EvidenceCard({
  module: mod,
  researchHref,
}: {
  module: ResearchModule;
  researchHref: string;
}) {
  const artifacts = mod.research.outputs;
  return (
    <section className="boundary">
      <h3>Evidence used</h3>
      <ul>
        <li>
          {/* How many result files, and which code wrote them. Correct plural throughout. */}
          {artifacts.length} artifact{artifacts.length === 1 ? '' : 's'} written by{' '}
          <code>{mod.research.adapter}</code>
        </li>
        <li>
          {/* Only the AVAILABLE figures and tables are counted -- so the number reflects what
              a reader can actually go and look at, not what was declared. */}
          {mod.figures.filter((f) => f.available).length} figure(s) and{' '}
          {mod.tables.filter((t) => t.available).length} table(s) drawn from it
        </li>
        <li>
          {/* HOW MANY PUBLISHED CLAIMS DEPEND ON THIS. A striking thing to put on a card:
              it tells a reader what is at stake if this module is wrong. */}
          {mod.research.claims.length} claim(s) in the ledger rest on this module&apos;s
          evidence
        </li>
        {mod.research.last_run?.at ? (
          <li>Last executed {new Date(mod.research.last_run.at).toUTCString()}</li>
        ) : (
          // No log: says so, rather than omitting the line and leaving the freshness unstated.
          <li>No execution log is present in this build</li>
        )}
      </ul>
      <p style={{ margin: '8px 0 0' }}>
        {/* The link phrased as the reader's own question, then what they will get. */}
        <Link href={researchHref}>Why am I seeing this? View the evidence →</Link>
      </p>
    </section>
  );
}

// What a reader can do with this module.
export function ActionList({ actions }: { actions: string[] }) {
  if (actions.length === 0) return null;
  return (
    <section className="actions">
      {/* "What YOU can do here" -- addressed to the reader, and about examining evidence
          rather than about acting on markets. */}
      <h3>What you can do here</h3>
      <ul>
        {actions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </section>
  );
}

// What this module takes as input.
export function InputPanel({ inputs }: { inputs: ModuleInput[] }) {
  if (inputs.length === 0) return null;
  return (
    <section className="inputs">
      <h3>Inputs</h3>
      <dl>
        {inputs.map((i) => (
          <div key={i.kind} className="inputs__row">
            <dt>
              {i.label} <span className="chip">{i.kind}</span>
            </dt>
            <dd>{i.note}</dd>
          </div>
        ))}
      </dl>
      <p className="muted small" style={{ margin: '6px 0 0' }}>
        {/* AN IMPORTANT GUARANTEE, stated to the reader: nothing you type here can end up in
            a research result. You are selecting among things already computed.
            That is what keeps the provenance chain intact -- a visitor cannot introduce data
            that then appears in a published artifact. */}
        Every input selects among values the pipeline already produced. No data supplied
        here can enter a research artifact, which is what keeps provenance intact.
      </p>
    </section>
  );
}

/* -- research-mode panels ------------------------------------------------------------ */

// The full experimental record.
export function ExperimentMetadata({
  module: mod,
  run,
}: {
  module: ResearchModule;
  run: ModuleRun | null;
}) {
  return (
    <div className="tableWrap">
      <table>
        <tbody>
          <tr>
            {/* A fixed label width, so several of these tables line up with one another. */}
            <th style={{ width: 190 }}>Module</th>
            <td className="mono">{mod.id}</td>
          </tr>
          <tr>
            <th>Experiment</th>
            <td className="mono">{mod.research.experiment_id ?? '—'}</td>
          </tr>
          <tr>
            {/* The question the module exists to answer, given a row of its own. */}
            <th>Research question</th>
            <td>{mod.research.research_question}</td>
          </tr>
          <tr>
            <th>Research status</th>
            <td className="mono">{mod.research.status}</td>
          </tr>
          <tr>
            <th>Wrapper status</th>
            <td className="mono">{mod.research.wrapper_status}</td>
          </tr>
          <tr>
            <th>Adapter</th>
            <td className="mono small">{mod.research.adapter}</td>
          </tr>
          <tr>
            {/* THE TRACEABILITY LINK: which research code this module is a front for. So a
                reader can go from a web page to the exact source that produced the number. */}
            <th>Canonical implementation</th>
            <td className="mono small">
              {mod.research.canonical.length
                // One line per file, so several are readable rather than run together.
                ? mod.research.canonical.map((c) => <div key={c}>{c}</div>)
                : '—'}
            </td>
          </tr>
          <tr>
            <th>Depends on</th>
            {/* "nothing" written out, rather than a blank -- so no dependency is a stated
                fact rather than a gap in the table. */}
            <td className="mono small">
              {mod.research.depends_on.join(', ') || 'nothing'}
            </td>
          </tr>
          <tr>
            <th>Last run</th>
            <td className="small">
              {run?.at ? (
                <>
                  {/* WHEN, WITH WHAT OUTCOME, HOW LONG IT TOOK, AT WHICH CODE VERSION, AND
                      HOW MANY TIMES IT HAS EVER RUN. Five facts in one line -- everything
                      needed to place this result in its history. */}
                  {run.at} · <span className="mono">{run.status}</span> ·{' '}
                  {run.elapsed_s}s · commit{' '}
                  {/* The first eight characters of the commit -- the conventional short
                      form, unique in practice and far more readable than all forty. */}
                  <span className="mono">{run.git_commit?.slice(0, 8) ?? 'n/a'}</span> ·{' '}
                  {run.runs_recorded} run(s) recorded
                </>
              ) : (
                'no execution log in this build'
              )}
            </td>
          </tr>
          <tr>
            <th>Notes</th>
            <td className="small">{mod.research.notes || '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// What this module reads and what it writes.
export function ProvenancePanel({ module: mod }: { module: ResearchModule }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Direction</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          {/* Inputs and outputs in one table, distinguished by a chip -- so the whole data
              flow through this module is visible at a glance. */}
          {mod.research.inputs.map((i) => (
            <tr key={`in-${i}`}>
              <td>
                <span className="chip">input</span>
              </td>
              <td className="mono small">{i}</td>
            </tr>
          ))}
          {mod.research.outputs.map((o) => (
            <tr key={`out-${o}`}>
              <td>
                <span className="chip chip--good">output</span>
              </td>
              <td className="mono small">{o}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small" style={{ margin: '8px 0 0' }}>
        {/* THE EXACT COMMANDS, IN ORDER -- and then the guarantee that matters:
            "The interface never runs the module: it reads what that command wrote."
            So a reader knows that what they are looking at came from a command they could
            run themselves, not from something the website computed on the fly. */}
        Regenerate with <code>python scripts/run_module.py --module {mod.id}</code>, then{' '}
        <code>python scripts/export_modules.py</code>. The interface never runs the
        module: it reads what that command wrote.
      </p>
    </div>
  );
}

// The caveats bounding this module.
export function LimitationPanel({
  limitations,
}: {
  limitations: ModuleLimitation[];
}) {
  if (limitations.length === 0) {
    return (
      // AN OUTSTANDING SENTENCE, and a rare one to find in any product:
      // "That means none has been identified, not that none exists."
      // A module with no recorded limitations is not a module without limitations. Most
      // interfaces would show a reassuring "no known issues" and stop.
      <p className="muted small">
        No limitation is registered against this module. That means none has been
        identified, not that none exists.
      </p>
    );
  }
  return (
    <div className="limitations">
      {limitations.map((l) => (
        <article key={l.id} className="limitations__item">
          <h4>
            {/* The id links to the full entry, so a summary is never the end of the trail. */}
            <Link href={`/research/limitations/${l.id}`}>{l.id}</Link> — {l.title}{' '}
            <span className="chip">{l.status.replace(/_/g, ' ')}</span>
          </h4>
          <p>{l.description}</p>
          {/* And the scope note -- the short warning that attaches to any result touched by
              this gap. */}
          {l.scope_note ? <p className="limitations__scope">{l.scope_note}</p> : null}
        </article>
      ))}
    </div>
  );
}

// The published claims that depend on this module.
export function ClaimPanel({ claims }: { claims: ModuleClaim[] }) {
  if (claims.length === 0) {
    return (
      <p className="muted small">
        No claim in the ledger currently rests on this module&apos;s evidence.
      </p>
    );
  }
  return (
    <div className="claims">
      {claims.map((c) => (
        <article key={c.id} className="claims__item">
          <div className="claims__head">
            <Link href={`/research/claims#${c.id}`} className="mono">
              {c.id}
            </Link>
            {/* Its status and its SCOPE -- how far it reaches. Both shown before the claim
                itself, so a reader meets the qualification before the assertion. */}
            <span className="chip">{c.status.replace(/_/g, ' ')}</span>
            <span className="chip">{c.scope}</span>
          </div>
          <p className="claims__text">{c.claim}</p>
          <dl className="claims__meta">
            {/* THE COMPLETE CHAIN BEHIND ONE CLAIM: the evidence, the metric, the test, the
                data, the files, and the caveats. Six fields, so a claim can never appear as
                a bare assertion. */}
            <div>
              <dt>Evidence</dt>
              <dd>{c.evidence}</dd>
            </div>
            <div>
              <dt>Metric</dt>
              <dd>{c.metric}</dd>
            </div>
            <div>
              <dt>Statistical test</dt>
              <dd>{c.statistical_test}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>{c.dataset}</dd>
            </div>
            <div>
              <dt>Artifacts</dt>
              <dd className="mono small">{c.artifacts.join(', ') || '—'}</dd>
            </div>
            <div>
              {/* "BOUNDED BY" -- and each caveat is a link, so a reader can follow it. */}
              <dt>Bounded by</dt>
              <dd>
                {c.limitations.length
                  ? c.limitations.map((l) => (
                      <Link
                        key={l}
                        href={`/research/limitations/${l}`}
                        style={{ marginRight: 8 }}
                      >
                        {l}
                      </Link>
                    ))
                  // And where nothing bounds it, the REASON is given rather than a blank:
                  // this claim does not depend on the dataset at all. That distinguishes an
                  // unbounded claim from one whose caveats were simply never recorded.
                  : 'nothing — this claim does not depend on the dataset'}
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

/* -- figures and tables -------------------------------------------------------------- */

// The charts.
export function FigureViewer({
  figures,
  compact = false,
}: {
  figures: ModuleFigure[];
  compact?: boolean;
}) {
  if (figures.length === 0) {
    return <p className="muted small">This module cites no figure.</p>;
  }
  return (
    <div className={compact ? 'figures figures--compact' : 'figures'}>
      {figures.map((f) => (
        <figure key={f.figure} className="figures__item">
          {f.available && f.url ? (
            // Opens full size in a new tab. `rel="noreferrer"` is the standard safety
            // measure for any link opening a new tab.
            <a href={f.url} target="_blank" rel="noreferrer">
              {/* Deliberately a plain <img>: these are pre-rendered research figures of
                  known provenance served from this origin, and next/image would
                  re-encode an artifact the paper cites. */}
              {/* PLAIN ENGLISH: an excellent reason for going against the framework's
                  recommendation. The optimised image component would RE-ENCODE the picture
                  -- recompressing it for the web. That is normally a good thing.
                  But these are research figures the paper cites. Re-encoding would mean the
                  image on screen is not byte-for-byte the artifact that was published. For
                  an ordinary photograph that would not matter; for a cited figure it does. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {/* `loading="lazy"` so a page of figures does not download them all at once. */}
              <img src={f.url} alt={f.caption ?? f.figure} loading="lazy" />
            </a>
          ) : (
            // MISSING FIGURE: says so, and gives the command to produce it. Never a broken
            // image icon.
            <div className="figures__missing">
              Not present in this build. Regenerate with{' '}
              <code>python scripts/generate_research_figures.py</code>.
            </div>
          )}
          <figcaption>
            {/* The identifier, the caption, and the data it was drawn from -- so a figure
                is always traceable back to its source. */}
            <span className="mono">{f.figure}</span>
            <span>{f.caption}</span>
            {f.source_data ? (
              <span className="muted mono small">source: {f.source_data}</span>
            ) : null}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

// The paper tables.
export function TableList({ tables }: { tables: ModuleTable[] }) {
  if (tables.length === 0) {
    return <p className="muted small">This module cites no table.</p>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Table</th>
            <th className="num">Rows</th>
            <th>Caption</th>
            {/* Again the source column -- every artifact traceable to what produced it. */}
            <th>Source artifact</th>
          </tr>
        </thead>
        <tbody>
          {tables.map((t) => (
            <tr key={t.table}>
              <td className="mono">
                <Link href={`/research/tables#${t.table}`}>{t.table}</Link>
              </td>
              <td className="num">{t.rows ?? '—'}</td>
              <td className="small">{t.caption ?? '—'}</td>
              <td className="small mono muted">{t.source ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -- shared header pieces ------------------------------------------------------------ */

// The two chips at the top of every module page.
export function StatusPair({ module: mod }: { module: ResearchModule }) {
  return (
    // TWO SEPARATE FACTS, side by side: did it run properly, and how strong is the evidence.
    // A module can be perfectly VERIFIED and still carry LOW confidence, and squashing the
    // two into one badge would hide exactly that combination.
    <div className="statusPair">
      <span
        className={`chip chip--${
          mod.product.status === 'VERIFIED'
            ? 'good'
            : mod.product.status === 'UNAVAILABLE'
              ? 'bad'
              : 'warn'
        }`}
        // The full meaning on hover, so a short badge always has its explanation available.
        title={PRODUCT_STATUS_COPY[mod.product.status]}
      >
        {mod.product.status}
      </span>
      <span
        className={`chip chip--${CONFIDENCE_TONE[mod.product.confidence] === 'good' ? 'good' : 'warn'}`}
        title={CONFIDENCE_COPY[mod.product.confidence].meaning}
      >
        {CONFIDENCE_COPY[mod.product.confidence].label}
      </span>
    </div>
  );
}
