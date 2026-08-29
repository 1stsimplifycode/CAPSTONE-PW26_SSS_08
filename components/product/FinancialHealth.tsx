/**
 * Financial health — rendered as the absence it is.
 *
 * A risk platform without company fundamentals has a real hole in it, and the honest way
 * to show a hole is to draw it rather than to fill it. This component exists so the
 * section appears in the page's information architecture, states plainly that the data is
 * not available, and says why and what it would take to change that.
 *
 * The alternative — deriving a revenue or leverage proxy from prices — is specifically
 * ruled out by the project's own limitation record: a price-derived stand-in for a
 * fundamental is a market signal wearing a fundamental label, and it would leak
 * look-ahead unless every figure carried its disclosure timestamp separately from its
 * financial period. No licence-clear source with that property was located.
 *
 * The metric names themselves are not written here. The limitation registry lists them as
 * forbidden phrasings precisely so that no surface can print them beside a number and
 * imply one exists.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THIS IS A COMPONENT WHOSE ENTIRE PURPOSE IS TO SAY "WE DO NOT HAVE THIS."
 *
 * It draws a section on the page, headed "Financial health", containing no data at all --
 * only an explanation of why there is none.
 *
 * WHY BUILD SUCH A THING? Because of the sentence in the first paragraph:
 *
 *     "the honest way to show a hole is to draw it rather than to fill it."
 *
 * A risk system that never mentions company accounts has an obvious gap. Two ways to
 * handle that:
 *   LEAVE THE SECTION OUT -- and every reader assumes the topic simply was not relevant.
 *   DRAW THE SECTION EMPTY -- and every reader learns something true about the system's
 *     limits.
 *
 * THE TEMPTING SHORTCUT, ruled out explicitly. You could estimate a company's financial
 * health from its share price -- prices do respond to accounts, after all. Two reasons not
 * to:
 *   1. IT WOULD BE MISLABELLED. It is a market signal with a financial name on it. A reader
 *      seeing "financial health" would believe we had looked at the accounts. We had not.
 *   2. IT WOULD LEAK THE FUTURE. Company results describe a quarter that ENDED in March,
 *      but are not PUBLISHED until May. Apply them from March and you have handed the
 *      system two months of information nobody had. You would need a source recording both
 *      dates separately -- and no such source was available.
 *
 * AND THE LAST PARAGRAPH IS THE SHARPEST TOUCH. The names of the missing measures are not
 * even written on this page. They are on the forbidden-words list, so no page anywhere can
 * print one beside a number and imply it exists. The absence is enforced, not just stated.
 */
export function FinancialHealth({ limitationId = 'L-13' }: { limitationId?: string }) {
  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        {/* The heading appears normally -- the section takes its proper place in the page,
            rather than being quietly missing from the layout. */}
        <h2>Financial health</h2>
        {/* And immediately beside it, where a date would normally go: "not available". */}
        <span className="home__asof">not available</span>
      </div>

      <div className="notAvailable">
        <p className="notAvailable__headline">
          {/* Stated plainly and in bold. No hedging, no "coming soon". */}
          Company fundamentals are <strong>not available</strong> in this system.
        </p>
        <p className="notAvailable__body">
          {/* THE REASON, explained so a non-specialist can follow it. Note how concrete it
              is: a quarter's figures applied from the quarter END rather than the FILING
              date "leaks weeks of future information into every historical decision".
              That is a specific, checkable claim, not a vague appeal to rigour. */}
          Point-in-time company financials with disclosure timestamps are required to use
          them without look-ahead: applying a quarter&rsquo;s figures from the quarter end
          rather than the filing date leaks weeks of future information into every
          historical decision. No licence-clear source carrying that property was located,
          so the block is absent rather than approximated.
        </p>
        <p className="notAvailable__body">
          {/* AND THE SECOND PARAGRAPH ANSWERS THE OBVIOUS FOLLOW-UP: "why not estimate it?"
              Pre-empting the question is what stops a reader assuming it was simply not
              thought of. */}
          No price-derived substitute is shown. A proxy built from market data would be a
          market signal presented under a financial label, which would misstate what the
          evidence is.
        </p>
        <dl className="notAvailable__meta">
          <div>
            <dt>Status</dt>
            {/* The precise word from the research vocabulary: NOT MEASURED. Not "failed",
                not "unavailable" -- we never measured it, and that is a different fact. */}
            <dd>NOT MEASURED</dd>
          </div>
          <div>
            <dt>Recorded limitation</dt>
            {/* The reference into the limitations register, so a reader can look up the
                full entry rather than taking this summary on trust. */}
            <dd>{limitationId}</dd>
          </div>
          <div>
            <dt>What would close it</dt>
            <dd>
              {/* And a precise specification of what would fix it. Not "better data" but
                  exactly which property that data would have to have. Somebody could act
                  on this. */}
              A licensed point-in-time fundamentals feed carrying the disclosure timestamp
              separately from the financial period.
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
