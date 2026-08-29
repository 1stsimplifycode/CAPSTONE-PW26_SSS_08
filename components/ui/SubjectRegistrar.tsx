// Runs in the browser: it needs to know the current mode, which is a per-visitor thing.
'use client';

import Link from 'next/link';

import { useMode, useSubject } from '@/lib/mode';

/**
 * Registers what the page is about so a mode switch carries it (spec sections 60, 127).
 *
 * Rendered by server components that know their subject. Renders nothing itself, except
 * the "verify this" affordance, which is the intended bridge from Product to Research:
 * a user who wants to know *how we know* should not have to find the research section
 * and navigate back to the same instrument.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * TWO SMALL JOBS, ONE OF WHICH IS INVISIBLE.
 *
 * JOB 1 (INVISIBLE): tell the rest of the site what this page is about.
 * A page says "I am about Reliance, on the 5th of March". That is remembered -- and it is
 * what lets the mode switch keep your place, instead of dumping you back at the front page
 * when you ask for more depth.
 *
 * JOB 2 (VISIBLE): a link that says "How do we know this?"
 * This is the bridge, and the docstring explains exactly why it exists. Without it, a
 * curious reader would have to: leave the page, find the research section, work out how it
 * is organised, and navigate all the way back to the same company. Most people would give
 * up -- and the evidence, however carefully assembled, would go unread.
 * One link removes every one of those steps.
 *
 * The word "affordance" is a design term for something whose appearance tells you what you
 * can do with it. A door handle affords pulling. This link affords checking.
 */
export function SubjectRegistrar({
  instrument,
  event,
  date,
  showBridge = true,
}: {
  instrument?: string;
  event?: string;
  date?: string;
  // A page can suppress the link where it would not make sense -- while still doing job 1.
  showBridge?: boolean;
}) {
  // JOB 1: register the subject. This happens on every page that uses this component,
  // whether or not the link is shown.
  useSubject({ instrument, event, date });
  const { mode } = useMode();

  // The link is shown ONLY in product mode -- because in research mode you are already
  // looking at the evidence, and "how do we know this?" would be a link to where you are.
  if (!showBridge || mode !== 'product') return null;

  // Pack the current subject into the link, so the research page opens ON THIS COMPANY
  // rather than at its own front page.
  const params = new URLSearchParams();
  if (instrument) params.set('instrument', instrument);
  if (event) params.set('event', event);
  if (date) params.set('date', date);

  return (
    <p className="small" style={{ marginTop: 14 }}>
      <Link href={`/research?${params.toString()}`}>
        {/* The wording is the invitation. Not "research view" or "more info" -- the actual
            question a reader is asking, in their own words. And it says what will happen:
            the workspace opens with this instrument already in context, so nobody has to
            wonder whether they will lose their place. */}
        How do we know this? Open the research workspace with this instrument in context →
      </Link>
    </p>
  );
}

export default SubjectRegistrar;
