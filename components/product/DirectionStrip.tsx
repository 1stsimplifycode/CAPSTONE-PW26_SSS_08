// Runs in the browser: it shows a live clock, which only exists once somebody is looking.
'use client';

/**
 * Direction of observed price movement, plus the two clocks that matter.
 *
 * Two timestamps sit side by side here on purpose, because collapsing them is the
 * mistake this strip exists to prevent:
 *
 * *Observed to* is the last session the data contains. It is the date every number on
 * this page belongs to.
 *
 * *Viewed* is the reader's own clock, updated live. It is the time right now, and it is
 * labelled as the page's clock rather than a market time — a page that shows only "now"
 * next to a price invites the reading that the price is from now.
 *
 * The direction label is a count, not an opinion: four independent readings are taken
 * from the same closes and the label reports which way most of them point, with the
 * tally shown so a reader can check it. It describes what the price did up to the
 * observed-to date and says nothing about what happens next.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * TWO CLOCKS, SIDE BY SIDE, AND WHY THAT MATTERS ENORMOUSLY.
 *
 * Nearly every financial page shows a price and, somewhere near it, the current time. And
 * the reader inevitably concludes the price is from now. Usually it is not -- it is
 * yesterday's close, or last Friday's.
 *
 * So this strip shows BOTH, labelled:
 *   OBSERVED TO -- the last trading day the data actually covers. Every number on the page
 *     belongs to this date.
 *   VIEWED -- the time on YOUR clock, ticking. Labelled "your clock, not a market time",
 *     which is about as unambiguous as it is possible to be.
 * A reader who sees the two dates differ has learned something true in a fraction of a
 * second. A reader shown only one of them would have learned something false.
 *
 * AND THE DIRECTION LABEL, which is careful in two separate ways.
 *
 * FIRST: it is a COUNT, NOT AN OPINION. Four separate readings are taken from the same
 * prices, and the label reports which way most of them point -- with the tally shown, so
 * you can check the arithmetic yourself. "Advancing, 3 of 4 readings" is a fact you can
 * verify. "Bullish" would be an opinion you would have to accept.
 *
 * SECOND: "it says nothing about what happens next." It describes what the price DID. It
 * is not a forecast, and it is not advice. Which is exactly what the whole project keeps
 * insisting on, applied here to a single small strip at the top of a page.
 */
import { useEffect, useState } from 'react';

export interface DirectionBlock {
  available: boolean;
  // And when unavailable, the reason.
  why?: string;
  // Note the vocabulary: advancing, declining, mixed. Observational words. Not "bullish",
  // not "strong", not "weak" -- none of which describe a price, only a feeling about one.
  state?: 'advancing' | 'declining' | 'mixed';
  label?: string;
  // The individual readings, so the verdict can be taken apart.
  readings?: { name: string; detail: string; points: string }[];
  // HOW MANY AGREED, out of how many. The tally that makes it checkable.
  agreeing?: number;
  total_readings?: number;
  summary?: string;
  observed_to?: string | null;
  session_change_pct?: number | null;
  basis?: string;
  scope_note?: string;
}

/** The viewer's own clock, in their timezone, refreshed once a second. */
function useNow(): Date | null {
  // Starts as null, NOT as the current time. That is deliberate: the server has no idea
  // what time it is where you are, so the first version of the page must contain no time at
  // all. Filling it in immediately would produce a mismatch between the server's version
  // and the browser's, which React reports as an error.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    // Once the page is safely up, set the time...
    setNow(new Date());
    // ...and update it every second.
    const id = setInterval(() => setNow(new Date()), 1000);
    // And this cleanup runs when the component goes away. Without it, the timer would keep
    // firing forever after the page had gone -- a "memory leak", and a slow one.
    return () => clearInterval(id);
  }, []);
  return now;
}

export function DirectionStrip({
  direction,
  observedTo,
}: {
  direction?: DirectionBlock;
  observedTo: string;
}) {
  const now = useNow();
  // The visitor's own timezone, asked of the browser -- so the clock can be labelled with
  // where it is, rather than leaving them to assume.
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="direction" data-state={direction?.state ?? 'unknown'}>
      <div className="direction__verdict">
        <span className="direction__label">Observed price direction</span>
        <span className="direction__state">
          {/* "INSUFFICIENT DATA" when there is not enough to judge -- not a guess, and not
              a blank space that would read as "no movement". */}
          {direction?.available ? direction.label : 'INSUFFICIENT DATA'}
        </span>
        <span className="direction__tally">
          {/* Either the tally, or the reason there is none. Something informative in both
              cases. */}
          {direction?.available ? direction.summary : direction?.why}
        </span>
      </div>

      {direction?.available && direction.readings ? (
        // THE FOUR READINGS, LISTED INDIVIDUALLY. This is what turns the verdict from a
        // pronouncement into something a reader can audit -- they can see each reading and
        // count for themselves.
        <ul className="direction__readings">
          {direction.readings.map((r) => (
            <li key={r.name} data-points={r.points}>
              <span className="direction__readingName">{r.name}</span>
              <span className="direction__readingDetail">{r.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="direction__clocks">
        <div>
          {/* CLOCK ONE: the date the data belongs to. */}
          <span className="direction__clockLabel">Observed to</span>
          <span className="direction__clockValue">{observedTo}</span>
          {/* And a note saying exactly what that date means. */}
          <span className="direction__clockNote">last session in the data</span>
        </div>
        <div>
          {/* CLOCK TWO: right now. */}
          <span className="direction__clockLabel">Viewed</span>
          {/* `suppressHydrationWarning` tells React not to complain that the server and the
              browser disagree here. They inevitably do -- the time changes between the two --
              and this is one of the very few places where that is correct rather than a bug. */}
          <span className="direction__clockValue" suppressHydrationWarning>
            {now
              ? `${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} · ${now.toLocaleTimeString('en-GB', { hour12: false })}`
              // An em-dash for the split second before the clock starts, rather than a
              // flash of some wrong time.
              : '—'}
          </span>
          <span className="direction__clockNote">
            {/* THE SENTENCE THAT DOES THE WORK: "your clock, not a market time". Six words
                that prevent the misreading this entire component exists to prevent. And the
                timezone is named, so there is no ambiguity about whose clock it is. */}
            your clock{tz ? ` · ${tz}` : ''}, not a market time
          </span>
        </div>
      </div>

      {direction?.scope_note ? (
        // Any further caveat, shown if there is one.
        <p className="direction__scope">{direction.scope_note}</p>
      ) : null}
    </div>
  );
}
