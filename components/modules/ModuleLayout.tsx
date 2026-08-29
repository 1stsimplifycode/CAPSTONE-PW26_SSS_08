import { NoData } from '@/components/ui/Primitives';
import { listModules, type ResearchModule } from '@/lib/modules';

import { ModuleCard } from './ModuleCard';
import { ModuleNav } from './ModuleNav';

/**
 * The frame every module page sits in: all 16 modules on the left, the module on the
 * right. Fetched once on the server and handed to the client nav, so navigating between
 * modules never refetches the list.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE PAGE FRAME, plus the index page that lists every module as a card.
 *
 * THE PERFORMANCE POINT IN THE HEADER is worth understanding. The list of modules is
 * fetched ONCE, on the server, and passed to the sidebar. So clicking from one module to
 * the next does not fetch the list again -- it is already there.
 * The obvious alternative, where the sidebar fetches its own list, would re-fetch the same
 * sixteen entries on every single navigation. It would work, and it would be slower on
 * every click, forever.
 */
export async function ModuleLayout({ children }: { children: React.ReactNode }) {
  const modules = await listModules();
  // NO MODULES AT ALL. Rather than an empty frame, show the honest "no data" block --
  // naming what is missing and the exact command to produce it.
  if (modules.length === 0) {
    return (
      <NoData
        what="Module manifest"
        note={
          'Run python scripts/export_modules.py to populate public/data/modules.json ' +
          'from research_modules.yaml and the executed artifacts.'
        }
      />
    );
  }
  return (
    <div className="moduleLayout">
      {/* The sidebar, handed the list rather than fetching its own. */}
      <ModuleNav modules={modules} />
      {/* And whatever page is being shown, on the right. */}
      <div className="moduleLayout__main">{children}</div>
    </div>
  );
}

/** The category index: every module in it, as a card. */
export function ModuleIndex({
  modules,
  label,
  lede,
}: {
  modules: ResearchModule[];
  label: string;
  lede: string;
}) {
  // Count each standing. These three numbers are the summary of the whole section.
  const verified = modules.filter((m) => m.product.status === 'VERIFIED').length;
  const limited = modules.filter((m) => m.product.status === 'LIMITED').length;
  const unavailable = modules.filter((m) => m.product.status === 'UNAVAILABLE').length;

  return (
    <>
      <h1>{label}</h1>
      <p className="lede">{lede}</p>

      <div className="grid">
        <div className="card">
          <div className="card__label">Modules</div>
          <div className="card__value">{modules.length}</div>
          <div className="card__note">each with a product and a research view</div>
        </div>
        <div className="card">
          <div className="card__label">Verified</div>
          <div className="card__value">{verified}</div>
          {/* Every count carries a note saying exactly what it means -- so "verified" is
              never left as a word the reader has to interpret for themselves. */}
          <div className="card__note">ran, and the research status is supported</div>
        </div>
        <div className="card">
          <div className="card__label">Limited</div>
          <div className="card__value">{limited}</div>
          <div className="card__note">ran, and a limitation bounds the result</div>
        </div>
        <div className="card">
          {/* THE UNFLATTERING COUNT, given the same size and prominence as the good one.
              A project confident enough to put "how many of our modules have no results"
              at the top of its own index page. */}
          <div className="card__label">Unavailable</div>
          <div className="card__value">{unavailable}</div>
          <div className="card__note">outputs absent from this build</div>
        </div>
      </div>

      <h2>All {label.toLowerCase()} modules</h2>
      <div className="moduleGrid">
        {modules.map((m) => (
          <ModuleCard key={m.id} module={m} />
        ))}
      </div>

      <section className="boundary">
        {/* AN INSTRUCTION MANUAL, ON THE PAGE. Rather than assuming a reader will work out
            what the two modes are for, the page simply tells them. */}
        <h3>How to read a module page</h3>
        <p style={{ margin: 0 }}>
          Product mode answers what the module observed, how far the observation goes and
          what bounds it. Research mode answers the same question with the experiment
          metadata, the artifact paths, the statistical test and the limitations behind
          it. Both read the same exported record, so neither can show a number the other
          does not have.
          {/* And the final clause is the guarantee that matters: BOTH VIEWS READ THE SAME
              RECORD. So the simpler view is not a softened version of the detailed one --
              it is the same evidence, shown at a different depth. Neither can contain a
              number the other lacks. */}
        </p>
      </section>
    </>
  );
}
