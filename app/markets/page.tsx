import type { Metadata } from 'next';
import Link from 'next/link';

import { Change, Empty, SourceLine, Spark } from '@/components/product/Bits';
import {
  compactInr,
  getOverview,
  inr,
  searchInstruments,
  signedPct,
} from '@/lib/product';

// "force-dynamic": built fresh per request rather than in advance -- because this page
// shows the latest market data, and a page built at deploy time would go stale.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Markets — AEGIS-Market',
  description:
    'Every instrument the system follows, with its last session and its evidence signal.',
};

/**
 * The market, as a list you can scan.
 *
 * Ordered by traded value rather than by signal. Ordering by signal would put the two
 * instruments whose evidence stood out at the top of every visit and quietly turn a
 * directory into a leaderboard — which is the shape that invites a reader to treat it as
 * a list of things to act on.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE LIST OF EVERY COMPANY, AND A SORTING DECISION THAT MATTERS MORE THAN IT LOOKS.
 *
 * The obvious way to order a risk product is by risk -- most alarming first. It is what
 * everybody does, and it is what a reader expects.
 *
 * This page orders by TRADED VALUE instead, and the docstring explains why:
 *
 *     "quietly turn a directory into a leaderboard — which is the shape that invites a
 *      reader to treat it as a list of things to act on."
 *
 * A list ordered by risk reads as a ranking. A ranking reads as a recommendation. And the
 * two companies at the top would be at the top on every visit, acquiring a significance
 * nobody ever claimed for them.
 * Ordering by size makes it a DIRECTORY -- a place to look things up -- which is what it
 * is. The risk is still shown on every row; it simply does not decide the order.
 */
export default async function MarketsPage() {
  const overview = await getOverview();
  const all = await searchInstruments('', 400);
  // Split into the studied sample and everything else -- two genuinely different things,
  // and the note under each table says so.
  const tracked = all.rows.filter((r) => r.tracked);
  const rest = all.rows.filter((r) => !r.tracked);
  const m = overview.data?.market;
  const t = overview.data?.tracked;

  return (
    <div className="home">
      <section className="home__hero">
        <h1>Markets</h1>
        <p className="home__lede">
          {t?.name ?? 'The tracked sample'} — plus every other instrument in the panel the
          system can open.
        </p>
      </section>

      {m && t ? (
        <section className="home__section">
          <div className="home__sectionHead">
            <h2>Last session</h2>
            {/* The date the figures belong to, right beside the heading. */}
            <span className="home__asof">{m.last_session}</span>
          </div>
          <div className="cardRow">
            <article className="tile">
              <span className="tile__label">Traded</span>
              <span className="tile__value">
                {m.instruments_traded.toLocaleString('en-IN')}
              </span>
              <span className="tile__note">instruments with a session</span>
            </article>
            <article className="tile">
              <span className="tile__label">Advancing</span>
              <span className="tile__value" data-dir="up">
                {m.advancing.toLocaleString('en-IN')}
              </span>
              {/* EVERY TILE DEFINES ITS OWN TERM. "Advancing" is not left as a word a reader
                  must already know -- it says "closed above the previous close". */}
              <span className="tile__note">closed above the previous close</span>
            </article>
            <article className="tile">
              <span className="tile__label">Declining</span>
              <span className="tile__value" data-dir="down">
                {m.declining.toLocaleString('en-IN')}
              </span>
              <span className="tile__note">closed below it</span>
            </article>
            <article className="tile">
              <span className="tile__label">Turnover</span>
              {/* At Indian scale -- "₹10.5 lakh cr" rather than a wall of digits. */}
              <span className="tile__value">{compactInr(m.turnover)}</span>
              <span className="tile__note">across the whole session</span>
            </article>
          </div>
          {/* Live or snapshot, always stated. */}
          <SourceLine of={overview} />
          {/* And the caveat about the tracked sample, carried from the data rather than
              written here -- so it says the same thing on every page that shows it. */}
          <p className="home__caveat">{t.caveat}</p>
        </section>
      ) : (
        <Empty title="No market data" note={overview.note ?? 'Export the snapshot.'} />
      )}

      {/* THE TWO TABLES, each with a note explaining exactly what it contains. */}
      <MarketTable
        title="Tracked sample"
        // The note repeats what the sample IS -- a liquidity proxy, ordered by traded value
        // -- so a reader landing here without having read the footer still learns it.
        note="The point-in-time liquidity proxy, by traded value at the last reconstitution."
        rows={tracked}
      />
      <MarketTable
        title="Also in the panel"
        // AND THE CRUCIAL DISTINCTION: these companies have PRICE HISTORY ONLY. They were
        // not part of the evaluation. So a reader does not assume the absence of a risk
        // signal means an absence of risk.
        note="Instruments outside the tracked sample. Price history only unless they were part of the evaluation sample."
        rows={rest.slice(0, 60)}
        // The real total passed separately, so the table can say "60 of 1,847".
        total={rest.length}
      />
    </div>
  );
}

// One table of companies. Written once and used twice, so the two cannot differ.
function MarketTable({
  title,
  note,
  rows,
  total,
}: {
  title: string;
  note: string;
  // The type derived from what `searchInstruments` returns, so it cannot drift out of step
  // with the function that supplies it.
  rows: Awaited<ReturnType<typeof searchInstruments>>['rows'];
  total?: number;
}) {
  if (!rows.length) return null;
  return (
    <section className="home__section">
      <div className="home__sectionHead">
        <h2>{title}</h2>
        <span className="home__asof">
          {/* "60 of 1,847" where the list is shortened, so a truncated table announces
              itself rather than passing as complete. */}
          {total ? `${rows.length} of ${total}` : `${rows.length} instruments`}
        </span>
      </div>
      <div className="tableWrap">
        <table className="marketTable">
          <thead>
            <tr>
              {/* `scope="col"` so screen-reader software pairs each value with its heading. */}
              <th scope="col">Instrument</th>
              <th scope="col">Last</th>
              <th scope="col">Session</th>
              <th scope="col">90 sessions</th>
              <th scope="col">Shape</th>
              {/* "Signal" -- not "Rating", not "Score". A word that describes evidence
                  rather than a verdict. */}
              <th scope="col">Signal</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol}>
                {/* `<th scope="row">` for the company name: it labels its row, so a listening
                    reader hears "RELIANCE, last, 1,402" rather than a stream of bare numbers. */}
                <th scope="row">
                  <Link href={`/instruments/${r.symbol}`}>{r.symbol}</Link>
                </th>
                <td className="mono">{inr(r.market.close)}</td>
                <td>
                  <Change value={r.market.change_pct} />
                </td>
                <td>
                  <span
                    className="change"
                    // `?? 0` so a missing value shows as flat rather than crashing the sort.
                    data-dir={(r.market.window_change_pct ?? 0) >= 0 ? 'up' : 'down'}
                  >
                    {signedPct(r.market.window_change_pct)}
                  </span>
                </td>
                <td className="marketTable__spark">
                  {/* A tiny line showing the recent shape. `slice(-40)` takes the last forty
                      sessions -- enough for a shape, small enough for a table cell. */}
                  <Spark points={r.market.series.slice(-40)} height={26} />
                </td>
                <td>
                  {r.risk?.available ? (
                    <span className="tag" data-tone={r.risk.state_tone}>
                      {r.risk.state_label}
                    </span>
                  ) : (
                    // "NOT ASSESSED", not a blank and not "calm". The distinction the whole
                    // project rests on, appearing here in a single table cell: we did not
                    // look at this one, which is not the same as having looked and found
                    // nothing.
                    <span className="tag tag--quiet">Not assessed</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="home__caveat">{note}</p>
    </section>
  );
}
