import type { InstrumentFoundation } from '@/lib/product';

/**
 * The Week 1 market-intelligence foundation, as the instrument page shows it.
 *
 * Two rules govern everything here, and both exist because the alternative misleads:
 *
 * 1. An unavailable value is *rendered*, not hidden. "Circuit band — not available,
 *    because NSE publishes no historical band series" is information; an absent row
 *    reads as "there is nothing to say", which is a different and false claim.
 * 2. Every value carries its basis. A number NSE published and a number this project
 *    assumed look identical on a screen, so the difference is written next to them.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE OFFICIAL FACTS ABOUT ONE COMPANY, AND WHERE EACH ONE CAME FROM.
 *
 * RULE 1: SHOW THE GAPS.
 * The same principle as the Financial Health block. A missing row reads as "nothing to
 * report here". A row saying "not available, because the exchange publishes no historical
 * series" teaches the reader something true.
 * One is a silence the reader will fill in wrongly. The other is a fact.
 *
 * RULE 2 IS THE STRIKING ONE, and it is the whole reason the little `Basis` tag exists:
 *
 *     "A number NSE published and a number this project assumed look identical on a
 *      screen."
 *
 * That is the problem in one sentence. On a page, "20%" looks exactly like "20%" whether
 * the exchange stated it or we worked it out ourselves. The reader cannot tell, and will
 * naturally assume the stronger of the two.
 * So every single value carries a small tag saying which it is. The distinction that the
 * research layer worked so hard to preserve survives all the way to the last pixel.
 */

// The little tag saying where a value's authority comes from.
function Basis({ value }: { value?: string }) {
  if (!value) return null;
  const exchange = value === 'EXCHANGE_PUBLISHED';
  return (
    // Two different styles, so exchange facts and our own derivations are visually
    // distinct at a glance rather than needing to be read.
    <span className={`basis ${exchange ? 'basis--exchange' : 'basis--derived'}`}>
      {exchange
        ? 'Exchange-published'
        // Anything else has its underscores turned into spaces and is lower-cased, so
        // "DERIVED_FROM_EXCHANGE_DATA" reads as "derived from exchange data" rather than
        // shouting in machine language at the reader.
        : value.replace(/_/g, ' ').toLowerCase()}
    </span>
  );
}

// The tile shown when something is not available.
function Unavailable({ what, why }: { what: string; why?: string }) {
  return (
    // A tile of the SAME SHAPE as a real one -- so it takes its proper place in the row
    // rather than leaving a hole. Muted styling, so it does not shout, but present.
    <article className="tile tile--muted">
      <span className="tile__label">{what}</span>
      <span className="tile__value">Not available</span>
      {/* AND THE REASON, in the position a value's note would occupy. */}
      <span className="tile__note">{why}</span>
    </article>
  );
}

export function Foundation({ foundation }: { foundation?: InstrumentFoundation }) {
  if (!foundation) return null;
  // Unpack the four parts, renaming the long ones for readability.
  const { status, price_band: band, corporate_actions: actions, point_in_time: pit } =
    foundation;

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        {/* The heading is precise about whose statement this is: "What the exchange says".
            Not "Company information", which would blur our facts into theirs. */}
        <h2>What the exchange says about this security</h2>
        <span className="home__asof">Reference data, with its provenance</span>
      </div>

      <div className="cardRow">
        {/* THE PATTERN, repeated for each fact: show it with its basis, or show the gap
            with its reason. */}
        {status.available ? (
          <article className="tile">
            <span className="tile__label">Status</span>
            <span className="tile__value">{status.state_label}</span>
            <span className="tile__note">
              {/* What it means, then where it came from. */}
              {status.meaning} <Basis value={status.basis} />
            </span>
          </article>
        ) : (
          <Unavailable what="Status" why={status.why} />
        )}

        {band.available ? (
          <article className="tile">
            <span className="tile__label">Circuit band</span>
            <span className="tile__value">{band.band_label}</span>
            <span className="tile__note">
              {/* An em-dash where a series is unknown, rather than a blank. */}
              Series {band.series || '—'}
              {/* The surveillance remark only if there is one, with a separator. */}
              {band.surveillance_remark ? ` · ${band.surveillance_remark}` : ''}{' '}
              <Basis value={band.basis} />
            </span>
          </article>
        ) : (
          <Unavailable what="Circuit band" why={band.why} />
        )}

        <article className="tile">
          <span className="tile__label">Listed since</span>
          <span className="tile__value">{status.listing_date ?? '—'}</span>
          <span className="tile__note">
            {status.listing_date
              ? <>NSE listing roster <Basis value="EXCHANGE_PUBLISHED" /></>
              // And when there is no date, an explanation of what that means rather than
              // simply nothing: the company is not in the current roster.
              : 'Not in the current listing roster.'}
          </span>
        </article>

        <article className="tile">
          <span className="tile__label">Corporate actions</span>
          <span className="tile__value">{actions.count ?? 0}</span>
          <span className="tile__note">
            {/* How many actually MOVED THE PRICE -- the number that matters, since an
                ordinary dividend is a corporate action that changes nothing about the
                quoted price. */}
            {actions.price_affecting ?? 0} moved the quoted price{' '}
            <Basis value={actions.basis} />
          </span>
        </article>
      </div>

      {pit.available ? (
        <p className="instrument__pit">
          {/* THE POINT-IN-TIME DISCIPLINE, MADE VISIBLE TO A READER. */}
          <strong>Point in time.</strong> {pit.explanation} {pit.visible_sessions} sessions
          were knowable at that instant
          {pit.withheld_by_knowledge_bound
            // AND THE BEST SENTENCE ON THE PAGE: how many days had ALREADY HAPPENED and
            // were still withheld, because their data had not yet been published.
            // That single clause demonstrates the whole leakage discipline in a form
            // anybody can grasp -- and shows it was actually applied, not just claimed.
            ? `, and ${pit.withheld_by_knowledge_bound} that had already happened were not, because their data was not published yet`
            : ''}
          {/* And the exact code path that enforced it, so a technical reader can go and
              check the mechanism rather than trusting the sentence. */}
          . Read through <code>{pit.read_path}</code>.
        </p>
      ) : null}

      {actions.available && actions.actions && actions.actions.length > 0 ? (
        <div className="tableWrap">
          <table className="dataTable">
            {/* A caption that EXPLAINS THE COLUMN before the reader meets it -- including
                the specific case that would otherwise confuse: a factor of 1 means the
                action did not move the price, which is what an ordinary dividend looks
                like. Without that, a column of 1s would look like an error. */}
            <caption>
              Corporate actions NSE announced for this security. The price factor is the
              multiple by which the quoted price mechanically fell; a factor of 1 means the
              action did not move the price, which is the case for an ordinary dividend.
            </caption>
            <thead>
              <tr>
                {/* `scope="col"` tells screen-reader software these head their columns, so
                    a listener hears "Ex-date: 5 March" rather than a stream of bare values. */}
                <th scope="col">Ex-date</th>
                <th scope="col">Action</th>
                <th scope="col">Price factor</th>
                <th scope="col">Reconciliation</th>
              </tr>
            </thead>
            <tbody>
              {/* At most eight, so one company with a long history cannot swamp the page. */}
              {actions.actions.slice(0, 8).map((a) => (
                <tr key={`${a.ex_date}-${a.subject}`}>
                  <td>{a.ex_date}</td>
                  <td>{a.subject}</td>
                  <td>
                    {/* Show the factor only when it MEANINGFULLY differs from 1. The
                        `1e-6` tolerance is there because a stored 1.0000001 is really just
                        1, and printing "×1.00" would imply an adjustment that did nothing. */}
                    {a.price_factor && Math.abs(a.price_factor - 1) > 1e-6
                      ? `×${a.price_factor.toFixed(2)}`
                      : '—'}
                  </td>
                  {/* The status, tidied from machine shouting into readable words. */}
                  <td>{a.status.replace(/_/g, ' ').toLowerCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {status.available && !status.in_current_roster ? (
        <p className="instrument__note">
          {/* THE SURVIVORSHIP STORY, told to the reader at exactly the moment it is
              relevant: they are looking at a company that no longer exists on the exchange.
              Rather than a puzzling empty page, they are told the history is KEPT
              deliberately -- and that keeping it is precisely what makes the study honest. */}
          This security is no longer in NSE&rsquo;s listing roster, and its history is kept
          rather than removed &mdash; that is what makes the universe survivorship-free.
          {/* And why there is no delisting date, drawn from the data rather than guessed. */}
          No delisting date is shown: {status.date_note}
        </p>
      ) : null}
    </section>
  );
}
