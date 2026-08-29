/**
 * The non-advisory notice (spec section 3).
 *
 * The exact wording is asserted by `tests/unit/test_non_advisory.py`, which also scans
 * every page for the presence of this component. Do not paraphrase it: the test compares
 * the string literally, and a paraphrase would silently disable the guarantee.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE LEGAL NOTICE, AND THE MACHINERY THAT MAKES SURE IT IS ACTUALLY THERE.
 *
 * This project analyses shares. Telling people what to buy or sell is a regulated activity
 * requiring licences this project does not have -- and, quite apart from the law, this
 * system genuinely does not know what anybody should do. So it says so, on every page.
 *
 * BUT A NOTICE IS ONLY WORTH ANYTHING IF IT IS ACTUALLY PRESENT. So there is an automatic
 * test that does two things:
 *   1. Checks every single page includes this component.
 *   2. Checks the wording matches EXACTLY, character for character.
 *
 * And hence the warning: DO NOT REWORD IT. Somebody tidying the sentence -- shortening it,
 * making it flow better -- would break the test, or worse, would produce a notice that
 * passes a looser check while no longer saying the thing that matters.
 * The instruction "do not paraphrase" is not fussiness. It is what keeps an automatic
 * guarantee from being quietly turned into a manual promise.
 */
// The exact wording. Defined once, used everywhere, checked by a test.
export const NON_ADVISORY_TEXT =
  // Note what it does: says what the project IS ("research-oriented market-integrity risk
  // analysis"), then names the three things it is not ("buy, sell, or hold"). Naming all
  // three closes the gap where somebody might argue a "hold" suggestion was not covered.
  'AEGIS-Market provides research-oriented market-integrity risk analysis and ' +
  'does not provide financial advice or recommendations to buy, sell, or hold securities.';

export function NonAdvisoryNotice({ compact = false }: { compact?: boolean }) {
  return (
    // `role="note"` and the label tell screen-reader software what this block is, so
    // somebody listening to the page hears it announced as a notice rather than as stray
    // text in the middle of the content.
    <aside
      role="note"
      aria-label="Non-advisory notice"
      // A compact version for tighter spaces. Note only the STYLING changes -- the wording
      // is identical in both, so the notice can never be shortened to fit.
      className={compact ? 'notice notice--compact' : 'notice'}
    >
      <div className="notice__inner">
        <span className="notice__badge">Research use only</span>
        {/* The text drawn from the one constant, never typed out here. */}
        <p className="notice__text">{NON_ADVISORY_TEXT}</p>
      </div>
    </aside>
  );
}

export default NonAdvisoryNotice;

/**
 * The canonical scope denial for the position-lifecycle surfaces.
 *
 * It has to name the things it rules out, or it says nothing a reader can check. But
 * naming them is exactly what the lifecycle scan in `tests/unit/test_non_advisory.py`
 * forbids, so the enumeration lives here once and the scan strips this literal string.
 * Any other occurrence of these words anywhere in the app is therefore a real finding.
 * Do not paraphrase it and do not inline it: a copy would trip the scan, and a
 * paraphrase would leave the scan with nothing to strip.
 *
 * PLAIN ENGLISH -- a genuinely clever solution to an awkward problem.
 *
 * THE PROBLEM. There is an automatic scanner hunting the whole site for advice-like words:
 * "entry price", "target", "position size", "allocation". Find any of them and the build
 * fails. Excellent.
 *
 * BUT this notice needs to SAY those very words -- because "we produce no advice" is vague
 * and unfalsifiable, while "we produce no entry price, exit price, target, position size or
 * allocation" is specific and checkable. A reader can hold us to the second.
 *
 * So the notice must contain exactly the words the scanner forbids.
 *
 * THE SOLUTION. The forbidden list appears in ONE place -- this string -- and the scanner
 * is told to cut this exact string out of the page before it looks. So:
 *   * this notice may say the words, and
 *   * ANY OTHER occurrence of them anywhere is a genuine problem the scanner will catch.
 *
 * And hence the two warnings. Copy this text somewhere else and the scanner sees the words
 * outside the one place it strips -- build fails. Reword it and the scanner's cut-out no
 * longer matches, so it strips nothing and the notice itself trips the alarm.
 * One exception, made explicit and made narrow.
 */
export const LIFECYCLE_SCOPE_TEXT =
  // "Observational" is the key word: we watch, we do not instruct.
  // And the final clause is the strongest part: "and none is derivable from it" -- closing
  // off the argument that you could work out a target price from what we do publish.
  'This framework is observational. It produces no entry price, exit price, target, ' +
  'position size or allocation, and none is derivable from it.';

export function LifecycleScopeNotice() {
  return (
    <aside role="note" aria-label="Lifecycle scope notice" className="notice notice--compact">
      <span className="notice__badge">Scope</span>
      {/* Again drawn from the one constant -- which is what keeps the scanner's exception
          matching exactly one piece of text. */}
      <p className="notice__text">{LIFECYCLE_SCOPE_TEXT}</p>
    </aside>
  );
}
