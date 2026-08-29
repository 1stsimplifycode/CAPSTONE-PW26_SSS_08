// Runs in the visitor's browser, because opening and closing is something a person does.
'use client';

/**
 * Progressive disclosure, as one component used everywhere.
 *
 * The product shows an answer. Underneath it, closed, sits the evidence that produced the
 * answer; underneath that, a link into research mode. Three depths, and a reader chooses
 * how far down to go rather than being handed all three at once.
 *
 * It is a `<details>` element, deliberately. The content is in the page whether or not
 * JavaScript runs, it is reachable by keyboard and by find-in-page, and a reader who
 * prints the page gets everything. A custom toggle would have cost all three.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE "SHOW ME MORE" BOX.
 *
 * The idea is called PROGRESSIVE DISCLOSURE, and it solves a real tension. The evidence
 * behind an answer must be available -- otherwise the answer is unaccountable. But showing
 * all of it at once buries the answer in detail nobody asked for.
 * So there are three depths: the answer, then the evidence folded away beneath it, then a
 * link to the full research view. The reader decides how far to go.
 *
 * NOW THE PART WORTH ADMIRING: it is built from `<details>`, a plain feature of the web
 * browser itself, rather than being written by hand.
 *
 * Writing your own would take perhaps twenty lines and would look identical. It would also
 * quietly cost four things:
 *   1. WITHOUT JAVASCRIPT it would not open at all -- the evidence would simply be gone.
 *      With `<details>`, the browser handles it and the content is always there.
 *   2. KEYBOARD USERS could not open it unless somebody remembered to add that, and it is
 *      exactly the sort of thing that gets forgotten.
 *   3. FIND-IN-PAGE would not look inside a closed hand-made box. Modern browsers DO search
 *      inside a closed `<details>` and open it for you.
 *   4. PRINTING would lose the hidden content entirely.
 * All four come free from using the browser's own element. That is a decision made by
 * thinking about who is reading, not about what is easiest to write.
 */
import type { ReactNode } from 'react';

export function Disclosure({
  summary,
  children,
  tone = 'default',
}: {
  /** The invitation, phrased as what the reader will learn. Not "details". */
  // PLAIN ENGLISH: a small instruction with a big effect. The label should say what you
  // will FIND -- "See the four measurements behind this" -- not "Details" or "More".
  // "Details" tells a reader nothing and gives them no reason to click. Naming the content
  // lets them decide whether they want it.
  summary: string;
  children: ReactNode;
  // A quieter styling option, for a disclosure that should not compete with the answer.
  tone?: 'default' | 'quiet';
}) {
  return (
    // `<details>` is the browser's own collapsible element -- the source of all four
    // benefits above.
    <details className="disclosure" data-tone={tone}>
      {/* `<summary>` is the part that is always visible and can be clicked. The browser
          makes it keyboard-reachable automatically. */}
      <summary>
        <span className="disclosure__label">{summary}</span>
        {/* The little arrow. `aria-hidden` hides it from screen readers -- it is pure
            decoration, and reading "triangle" aloud would only get in the way of somebody
            listening to the page. */}
        <span className="disclosure__chevron" aria-hidden="true" />
      </summary>
      {/* Whatever was put inside. `children` means this box can hold anything at all,
          which is why one component serves the whole site. */}
      <div className="disclosure__body">{children}</div>
    </details>
  );
}
