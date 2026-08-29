import Link from 'next/link';
import type { ReactNode } from 'react';

import type { ResearchModule } from '@/lib/moduleTypes';
import { CATEGORY_COPY, CONFIDENCE_COPY } from '@/lib/moduleTypes';

import {
  ActionList,
  ClaimPanel,
  EvidenceCard,
  ExperimentMetadata,
  FigureViewer,
  InputPanel,
  LimitationPanel,
  MetricGrid,
  ProvenancePanel,
  ResearchMetricTable,
  StatusPair,
  TableList,
  UncertaintyCard,
} from './Panels';
import {
  hasChart,
  BlockStrip,
  ModuleVisual,
  TablePreview,
} from './Visuals';

/**
 * One module, two experiences, one set of numbers.
 *
 * Both views are rendered into the page and one is hidden by CSS keyed on the
 * `data-mode` attribute the boot script sets before first paint. Three consequences,
 * each of which is why it is done this way rather than by branching in JavaScript:
 *
 * * **No flash.** A `?mode=research` link paints research mode directly instead of
 *   painting product mode and swapping after hydration.
 * * **No JavaScript requirement.** Both experiences are in the prerendered HTML, so the
 *   page is complete before any script runs, and the research evidence is reachable by
 *   anything that reads HTML.
 * * **They cannot disagree.** Both views read the same record in the same render. There
 *   is one number and two depths of presentation, which is the whole design.
 *
 * Product mode never states more than research mode supports. Where research mode says a
 * difference is inside the seed noise floor, product mode says the comparison is
 * unresolved: it simplifies the language and never the meaning.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE MODULE PAGE, HOLDING BOTH VIEWS AT ONCE.
 *
 * THE UNUSUAL TECHNIQUE: both the simple view AND the detailed view are written into the
 * page, and the STYLING hides one of them. Not JavaScript choosing which to build --
 * both are built, and one is invisible.
 *
 * That sounds wasteful. It buys three things, and each is worth having:
 *
 * 1. NO FLASH. Follow a research link and you see research mode immediately. The other
 *    way, the page would paint the simple view first, then swap once the JavaScript ran --
 *    a visible flicker of the wrong content on every single visit.
 *
 * 2. NO JAVASCRIPT REQUIRED. Everything is in the page from the start. So the evidence is
 *    reachable by anything that reads a web page: a browser with scripting off, a screen
 *    reader, a printer, a search engine, an archive. The research is not locked behind a
 *    working script.
 *
 * 3. AND THE BEST ONE: THEY CANNOT DISAGREE. Both views are built from the SAME record in
 *    the SAME render. It is physically impossible for the simple view to show one number
 *    and the detailed view another.
 *
 * THE LAST PARAGRAPH IS THE GOVERNING RULE OF THE WHOLE PROJECT, in one sentence:
 *
 *     "it simplifies the language and never the meaning."
 *
 * With a worked example. Where the research says a difference is smaller than the noise the
 * pipeline generates on its own, the simple view does not round that up to "our method is
 * better". It says the comparison is unresolved -- in plainer words, but with exactly the
 * same meaning.
 * That is the difference between simplifying and overclaiming, and it is easy to say and
 * hard to hold to.
 */
export function ModuleShell({
  module: mod,
  runner,
}: {
  module: ResearchModule;
  /**
   * The interactive run panel, when the module declares one. Rendered once, outside the
   * two mode blocks, so switching depth mid-session keeps the result on screen: the panel
   * holds client state, and rendering it inside each block would give the two modes two
   * separate panels that disagree about what has been run.
   */
  // PLAIN ENGLISH: a real bug avoided, and a consequence of the both-views technique.
  // If the run panel were inside each view, there would be TWO of them. Run something in
  // the simple view, switch to detailed, and the result would vanish -- because you would
  // now be looking at the other panel, which had never been run.
  // Putting it ONCE, outside both, means one panel, one result, and switching depth keeps
  // what you ran on the screen.
  runner?: ReactNode;
}) {
  const category = CATEGORY_COPY[mod.category];

  return (
    <article className="module" data-module={mod.id}>
      <header className="module__head">
        <div className="module__crumbs">
          <Link href={category.base}>{category.label}</Link>
          <span aria-hidden="true">›</span>
          {/* Even the breadcrumb differs by mode: the formal id for a researcher, the
              friendly name for everybody else. */}
          <span className="modeOnly modeOnly--inline modeOnly--research mono">{mod.id}</span>
          <span className="modeOnly modeOnly--inline modeOnly--product">{mod.product_name}</span>
        </div>
        <div className="module__title">
          <span className="module__icon" aria-hidden="true">
            {mod.icon}
          </span>
          <div>
            {/* One heading, two names. The identifier is precise and unreadable; the
                product name is readable and uncitable. Each mode gets the one it needs
                and neither has to stand in for the other. */}
            {/* PLAIN ENGLISH: "precise and unreadable" versus "readable and uncitable" --
                a perfect summary of why one name could never serve both purposes. */}
            <h1 className="modeOnly modeOnly--product">{mod.product_name}</h1>
            <h1 className="modeOnly modeOnly--research">{mod.name}</h1>
            <p className="module__sub">{mod.product.headline}</p>
          </div>
        </div>
        {/* The status and confidence pair, shown in BOTH modes -- because a caveat must not
            be something only the detailed view mentions. */}
        <StatusPair module={mod} />
      </header>

      {/* The run panel, once, outside both views. */}
      {runner ? <div className="module__runner">{runner}</div> : null}

      {/* BOTH VIEWS, BOTH IN THE PAGE. The styling shows one. */}
      <div className="modeOnly modeOnly--product">
        <ProductView module={mod} />
      </div>
      <div className="modeOnly modeOnly--research">
        <ResearchView module={mod} />
      </div>
    </article>
  );
}

/* -- product ------------------------------------------------------------------------- */

// THE SIMPLE VIEW: what was found, and how far it goes.
function ProductView({ module: mod }: { module: ResearchModule }) {
  const researchHref = `${mod.route}?mode=research`;
  return (
    <div className="module__body">
      <section className="module__lead">
        {/* The question first, then what was observed. Question before answer, so a reader
            knows what they are about to be told. */}
        <h2 className="module__question">{mod.product.question}</h2>
        <p className="module__observation">{mod.product.observation}</p>
      </section>

      <section className="module__primary">
        <h3>From the last full pipeline run</h3>
        <p className="module__storedNote">
          {/* Says plainly that these are STORED values, and invites the reader to compute
              fresh ones. So nobody mistakes an old result for a live one. */}
          These are the values the research pipeline last wrote for this capability. Run
          it above to compute the same analysis on a slice you choose.
        </p>
        {/* A module without a chartable series shows its numbers as the primary view
            rather than as a bar chart of the same values beneath a metric grid: the same
            result rendered twice reads as two results. */}
        {/* PLAIN ENGLISH: a genuinely subtle observation. Showing the same numbers twice --
            once as tiles and once as a chart of those same tiles -- makes a reader think
            they are looking at two pieces of evidence. They are looking at one, drawn
            twice. So a module with no real chart shows its numbers ONCE. */}
        {hasChart(mod) ? (
          <ModuleVisual module={mod} />
        ) : (
          <MetricGrid metrics={mod.product.metrics} />
        )}
      </section>

      <BlockStrip module={mod} />

      {/* And only where there IS a genuine chart does the number grid appear as well --
          because then they are two different things rather than one thing twice. */}
      {hasChart(mod) ? (
        <section>
          <h3>Current result</h3>
          <MetricGrid metrics={mod.product.metrics} />
        </section>
      ) : null}

      <div className="split">
        <div>
          {/* What a reader can do with this, and what it takes as input. */}
          <ActionList actions={mod.product.actions} />
          <InputPanel inputs={mod.product.inputs} />
        </div>
        <div>
          {/* THE UNCERTAINTY AND THE EVIDENCE, in the simple view. Not hidden behind the
              research toggle -- present here, with a link deeper for anybody who wants it. */}
          <UncertaintyCard module={mod} />
          <EvidenceCard module={mod} researchHref={researchHref} />
        </div>
      </div>
    </div>
  );
}

/* -- research ------------------------------------------------------------------------ */

// THE DETAILED VIEW: the same result, with everything behind it.
function ResearchView({ module: mod }: { module: ResearchModule }) {
  const productHref = `${mod.route}?mode=product`;
  const conf = CONFIDENCE_COPY[mod.product.confidence];
  return (
    <div className="module__body">
      <section className="module__lead">
        {/* The formal research question and purpose. */}
        <h2 className="module__question">{mod.research.research_question}</h2>
        <p>{mod.research.purpose}</p>
        <p className="muted small">
          {/* A LOVELY TOUCH: the research view QUOTES what the simple view says, word for
              word, and links to it. So a researcher can check that the simplification is
              honest -- without leaving the page. The claim "it simplifies the language and
              never the meaning" is made checkable right here. */}
          The product view of this module states the same result as{' '}
          <em>“{mod.product.observation}”</em> and its confidence as{' '}
          <em>{conf.label.toLowerCase()}</em>.{' '}
          <Link href={productHref}>See the product view →</Link>
        </p>
      </section>

      {/* And then everything, in order: how it was run, every number with the file it came
          from, the raw tables, the charts, the paper tables, the claims resting on it, the
          limitations bounding it, and the full provenance. */}
      <section>
        <h3>Experiment metadata</h3>
        <ExperimentMetadata module={mod} run={mod.research.last_run} />
      </section>

      <section>
        {/* The heading itself makes the promise: every metric WITH the artifact it was read
            from. Not "metrics" but "metrics, and where each came from". */}
        <h3>Metrics, with the artifact each was read from</h3>
        <ResearchMetricTable
          // Both sets combined, so the research view is a superset of the product view and
          // can never be missing a number the simpler view shows.
          metrics={[...mod.product.metrics, ...mod.research.metrics]}
        />
      </section>

      {mod.research.previews.length ? (
        <section>
          <h3>Result tables</h3>
          {mod.research.previews.map((p) => (
            <TablePreview key={p.path} preview={p} limit={14} />
          ))}
        </section>
      ) : null}

      <section>
        <h3>Figures</h3>
        <FigureViewer figures={mod.figures} />
      </section>

      <section>
        <h3>Paper tables</h3>
        <TableList tables={mod.tables} />
      </section>

      <section>
        {/* "Claims resting on this evidence" -- the chain from evidence to claim, made
            visible from the evidence end. */}
        <h3>Claims resting on this evidence</h3>
        <ClaimPanel claims={mod.research.claims} />
      </section>

      <section>
        {/* And the limitations given their own section, at the same level as the results. */}
        <h3>Limitations</h3>
        <LimitationPanel limitations={mod.research.limitations} />
      </section>

      <section>
        <h3>Artifact provenance</h3>
        <ProvenancePanel module={mod} />
      </section>
    </div>
  );
}
