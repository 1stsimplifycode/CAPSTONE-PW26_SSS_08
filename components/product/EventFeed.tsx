/**
 * Recent exchange events for one issuer: announcements and corporate actions, merged.
 *
 * The point of this panel is the question "what happened recently, and when exactly" —
 * which the rest of the page cannot answer without the reader hunting. So each row leads
 * with its date, and where the corporate-announcements feed supplied a dissemination
 * instant, the time is shown to the minute beside it. Where it did not, the row says the
 * time is unavailable rather than quietly showing the session date as though it were one.
 *
 * **No impact badge.** Nothing in this project scores an individual announcement, so
 * nothing here labels one as material, positive or negative. A coloured chip would be a
 * claim the system cannot support, and it is the sort of claim a reader would carry away
 * from the page whether or not the rest of it was hedged.
 *
 * Corporate actions do carry a status, because that one is computed: a price factor was
 * either reconciled against the panel's own returns or it was not, and CONFIRMED versus
 * NO_PRICE_EFFECT is the outcome of that check.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * WHAT HAPPENED RECENTLY, AND EXACTLY WHEN.
 *
 * THE SECOND PARAGRAPH IS THE MOST IMPORTANT THING IN THIS FILE, and it is a decision
 * about what NOT to build.
 *
 * Every financial site puts a coloured badge next to an announcement: "positive",
 * "material", "high impact". They are enormously useful-looking and they are the first
 * thing a reader's eye goes to.
 *
 * This project does not have one. Why? Because nothing in it actually scores an individual
 * announcement. To add the badge, somebody would have to invent the scoring.
 *
 * And the reasoning about consequences is exactly right: a coloured chip is the thing a
 * reader CARRIES AWAY. They will forget the careful hedging elsewhere on the page. They
 * will remember that the system called this announcement negative. So an unsupported badge
 * does more damage than an unsupported sentence, because it travels further.
 *
 * THE CONTRAST WITH CORPORATE ACTIONS makes the principle clear rather than absolute.
 * Those DO carry a status -- because that status was genuinely computed. The system checked
 * whether the stated price factor matched what the prices actually did. "Confirmed" is the
 * result of a real check, so it is shown.
 * The rule is not "never label anything". It is "label only what you actually measured".
 *
 * AND ONE MORE PIECE OF CARE, in the first paragraph: where the feed gave no publication
 * time, the row SAYS SO -- rather than showing the trading date as though it were a time.
 */
import type { CorporateActionContext } from '@/lib/product';

// One announcement.
export interface AnnouncementItem {
  session: string;
  subject: string | null;
  title: string;
  // Whether the title had to be taken from the body text -- because some filings have no
  // title at all. Recorded so the row can say so, rather than presenting a made-up title as
  // though the company had written it.
  title_from_body: boolean;
  layout: string;
  body: string;
  disseminated_at: string | null;
  // Whether an actual publication time was supplied. Kept SEPARATE from the time itself, so
  // "no time given" and "time is midnight" cannot be confused.
  publication_time_available: boolean;
  source: string;
}

export interface AnnouncementsBlock {
  available: boolean;
  why?: string;
  count?: number;
  // How many exist in total, so the page can say "12 of 340" rather than implying these are
  // all of them.
  total_for_symbol?: number;
  items?: AnnouncementItem[];
  corpus_coverage?: string;
  basis?: string;
  // An explicit flag saying impact is NOT scored, and a note explaining that. The absence
  // of the badge is recorded as data rather than being left as a silence.
  impact_scored?: boolean;
  impact_note?: string;
}

// Pull "14:32" out of a full timestamp.
function timeOf(iso: string | null): string | null {
  if (!iso) return null;
  const m = iso.match(/\d{2}:\d{2}/);
  // Null when there is no time in it -- so the caller shows the "not published" wording
  // rather than an empty string that would read as a missing value.
  return m ? m[0] : null;
}

export function EventFeed({
  announcements,
  corporateActions,
  windowFrom,
}: {
  announcements?: AnnouncementsBlock;
  corporateActions?: CorporateActionContext;
  windowFrom?: string | null;
}) {
  const items = announcements?.items ?? [];
  const actions = (corporateActions?.actions ?? []).slice(0, 8);

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>Recent exchange events</h2>
        <span className="home__asof">
          {/* "12 of 340 announcements" -- so a reader knows they are seeing a sample, and
              how small a sample it is. */}
          {announcements?.available
            ? `${items.length} of ${announcements.total_for_symbol} announcements`
            : 'announcements not available'}
        </span>
      </div>

      <div className="eventFeed">
        <div className="eventFeed__col">
          <h3 className="eventFeed__title">Announcements</h3>
          {announcements?.available && items.length ? (
            <>
              {/* An ordered list, because these are in a sequence and the order carries
                  meaning. */}
              <ol className="eventFeed__list">
                {items.slice(0, 12).map((it, i) => (
                  <li className="eventFeed__item" key={`${it.session}-${i}`}>
                    <div className="eventFeed__when">
                      {/* THE DATE LEADS, because "when exactly" is the question this panel
                          exists to answer. */}
                      <span className="eventFeed__date">{it.session}</span>
                      <span className="eventFeed__time">
                        {/* THE HONEST TIME. Either the real minute with its timezone, or
                            "time not published" -- never the date dressed up as a time. */}
                        {it.publication_time_available
                          ? `${timeOf(it.disseminated_at)} IST`
                          : 'time not published'}
                      </span>
                    </div>
                    <div className="eventFeed__what">
                      {/* The headline -- and NOTHING ELSE. No badge, no colour, no score.
                          The absence here is the design. */}
                      <p className="eventFeed__headline">{it.title}</p>
                      <span className="eventFeed__meta">
                        {it.source}
                        {/* And when the title was extracted from the body rather than
                            supplied, it says so -- so a slightly odd-looking headline is
                            explained rather than looking like a mistake. */}
                        {it.title_from_body ? ' · title taken from the body text' : ''}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="eventFeed__note">
                {/* The note explaining that impact is not scored, plus what period the
                    announcement corpus covers -- so a reader knows whether an empty stretch
                    means nothing happened or means we hold nothing for that period. */}
                {announcements.impact_note}
                {announcements.corpus_coverage
                  ? ` Corpus covers ${announcements.corpus_coverage}.`
                  : ''}
              </p>
            </>
          ) : (
            // No announcements: the reason, or an honest default.
            <p className="small muted">
              {announcements?.why ?? 'No announcement corpus is available.'}
            </p>
          )}
        </div>

        <div className="eventFeed__col">
          <h3 className="eventFeed__title">Corporate actions</h3>
          {corporateActions?.available && actions.length ? (
            <>
              <table className="eventFeed__table">
                <thead>
                  <tr>
                    <th>Ex-date</th>
                    <th>Action</th>
                    <th>Factor</th>
                    {/* The column that carries the COMPUTED status -- the one label on this
                        panel that is earned. */}
                    <th>Reconciliation</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((a) => (
                    <tr key={`${a.ex_date}-${a.action_type}`}>
                      <td>
                        {a.ex_date}
                        {windowFrom && a.ex_date >= windowFrom ? (
                          // A dot marking actions that fall inside the period being charted
                          // above -- so a reader can connect a jump in the chart to the
                          // event that caused it, without cross-referencing dates by hand.
                          <span className="eventFeed__inWindow" title="Falls inside the charted window">
                            {' '}
                            •
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className="eventFeed__type">{a.action_type}</span>
                        <span className="eventFeed__subject">{a.subject}</span>
                      </td>
                      <td className="num">
                        {/* Four decimal places, because a split factor of 1.0001 and one of
                            1.0 mean genuinely different things. */}
                        {a.price_factor !== null ? a.price_factor.toFixed(4) : '—'}
                      </td>
                      <td>
                        {/* THE EARNED LABEL. `data-status` lets the styling colour it, and
                            the underscores are turned into readable words. */}
                        <span className="eventFeed__status" data-status={a.status}>
                          {a.status.replace(/_/g, ' ').toLowerCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="eventFeed__note">
                {/* The totals, with correct singular and plural, and -- importantly -- how
                    many actually CHANGED A PRICE. Most corporate actions do not, and
                    without that number the count would overstate how eventful the history
                    was. And the dot is explained, so a mysterious mark is not left
                    unaccounted for. */}
                {corporateActions.count} action{corporateActions.count === 1 ? '' : 's'} on
                record, {corporateActions.price_affecting} of which change a price factor.
                A dot marks an ex-date inside the charted window.
              </p>
            </>
          ) : (
            <p className="small muted">
              {corporateActions?.why ?? 'No corporate actions on record.'}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
