// Runs in the browser: it needs to know the current mode.
'use client';

/**
 * A module in a list.
 *
 * The card carries the same status pair the module page shows, so nothing about a
 * module's standing is discovered only by opening it. The link preserves the current
 * mode, because someone browsing in research mode wants the research view of whatever
 * they open next.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * ONE MODULE, SHOWN AS A CARD IN A LIST.
 *
 * THE KEY PRINCIPLE is in the first sentence, and it is about honesty in summaries:
 *
 *     "nothing about a module's standing is discovered only by opening it."
 *
 * The card shows the same status and the same confidence level the full page shows. So a
 * module with a serious caveat looks caveated in the list too.
 * The alternative -- clean, uniform cards with the qualifications only inside -- would
 * quietly mislead anybody who scanned the list without opening every item. Which is
 * everybody.
 */
import Link from 'next/link';

import { useMode } from '@/lib/mode';
import type { ResearchModule } from '@/lib/moduleTypes';
import { CONFIDENCE_COPY, CONFIDENCE_TONE, PRODUCT_STATUS_COPY } from '@/lib/moduleTypes';

// Turn a stored timestamp into something readable.
function formatRun(at: string | null | undefined): string {
  // Never run: says so plainly. Not a blank, and not today's date as a fallback.
  if (!at) return 'not recorded';
  const d = new Date(at);
  return Number.isNaN(d.getTime())
    // Unreadable date: show the raw text rather than "Invalid Date". At least a reader can
    // see what was stored and report it.
    ? at
    // "5 Mar 2026" -- unambiguous, unlike the numeric forms that different countries read
    // in different orders.
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function ModuleCard({ module: mod }: { module: ResearchModule }) {
  const { mode } = useMode();
  // The first number that IS available. A module whose headline figure could not be
  // computed falls through to the next one rather than showing a blank.
  const headline = mod.product.metrics.find((m) => !m.unavailable);
  const tone = CONFIDENCE_TONE[mod.product.confidence];

  return (
    // The whole card is one link -- so the entire area is clickable, rather than a small
    // target somewhere inside it.
    <Link href={`${mod.route}?mode=${mode}`} className="moduleCard">
      <div className="moduleCard__top">
        {/* Decorative icon, hidden from screen readers so a listener is not read an emoji. */}
        <span className="moduleCard__icon" aria-hidden="true">
          {mod.icon}
        </span>
        {/* The formal identifier, shown ONLY in research mode. `modeOnly--research` is the
            styling that hides it otherwise. A product reader does not need "STATS-11"; a
            researcher does. Both are in the page, and the mode chooses. */}
        <span className="mono moduleCard__id modeOnly modeOnly--inline modeOnly--research">{mod.id}</span>
        <span
          className={`chip chip--${
            // Green for verified, red for unavailable, amber for everything in between.
            mod.product.status === 'VERIFIED'
              ? 'good'
              : mod.product.status === 'UNAVAILABLE'
                ? 'bad'
                : 'warn'
          }`}
          // The full explanation on hover -- so the short badge always has its meaning
          // available rather than being a word a reader has to guess at.
          title={PRODUCT_STATUS_COPY[mod.product.status]}
        >
          {mod.product.status}
        </span>
      </div>

      <h3 className="moduleCard__name">
        {/* BOTH NAMES ARE IN THE PAGE, and the mode decides which is visible. The friendly
            one for a general reader, the formal one for a researcher. Neither has to stand
            in for the other, and switching mode needs no new page load. */}
        <span className="modeOnly modeOnly--inline modeOnly--product">{mod.product_name}</span>
        <span className="modeOnly modeOnly--inline modeOnly--research">{mod.name}</span>
      </h3>
      <p className="moduleCard__desc">{mod.product.headline}</p>

      {headline ? (
        <div className="moduleCard__metric">
          {/* The pre-formatted display value from the server, so two cards can never round
              the same number differently. */}
          <span className="moduleCard__metricValue">{headline.display}</span>
          <span className="moduleCard__metricLabel">{headline.label}</span>
        </div>
      ) : (
        // NO NUMBER AVAILABLE -- and it says "no scalar result" rather than showing a dash
        // or leaving a gap. Some modules genuinely produce charts rather than a single
        // number, and that is a fact about the module, not a failure.
        <div className="moduleCard__metric moduleCard__metric--none">
          <span className="moduleCard__metricLabel">no scalar result</span>
        </div>
      )}

      <dl className="moduleCard__facts">
        <div>
          <dt>Last run</dt>
          <dd>{formatRun(mod.research.last_run?.at)}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>
            {/* How many result files exist. A count of evidence, right there on the card. */}
            {mod.research.outputs.length} artifact
            {/* Correct singular and plural -- "1 artifact", "3 artifacts". A small courtesy
                that stops the card reading like a machine. */}
            {mod.research.outputs.length === 1 ? '' : 's'}
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          {/* THE HONESTY, ON THE CARD. Colour-coded, so a low-confidence module looks
              low-confidence in the list -- which is the principle from the top of the file. */}
          <dd className={`moduleCard__conf moduleCard__conf--${tone}`}>
            {CONFIDENCE_COPY[mod.product.confidence].label}
          </dd>
        </div>
      </dl>

      <span className="moduleCard__cta">
        {/* The call to action names which view you will get, so clicking holds no surprise. */}
        Open in {mode === 'research' ? 'research' : 'product'} mode →
      </span>
    </Link>
  );
}
