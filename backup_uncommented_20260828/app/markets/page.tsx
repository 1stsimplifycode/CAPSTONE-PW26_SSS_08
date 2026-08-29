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
 */
export default async function MarketsPage() {
  const overview = await getOverview();
  const all = await searchInstruments('', 400);
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
              <span className="tile__value">{compactInr(m.turnover)}</span>
              <span className="tile__note">across the whole session</span>
            </article>
          </div>
          <SourceLine of={overview} />
          <p className="home__caveat">{t.caveat}</p>
        </section>
      ) : (
        <Empty title="No market data" note={overview.note ?? 'Export the snapshot.'} />
      )}

      <MarketTable
        title="Tracked sample"
        note="The point-in-time liquidity proxy, by traded value at the last reconstitution."
        rows={tracked}
      />
      <MarketTable
        title="Also in the panel"
        note="Instruments outside the tracked sample. Price history only unless they were part of the evaluation sample."
        rows={rest.slice(0, 60)}
        total={rest.length}
      />
    </div>
  );
}

function MarketTable({
  title,
  note,
  rows,
  total,
}: {
  title: string;
  note: string;
  rows: Awaited<ReturnType<typeof searchInstruments>>['rows'];
  total?: number;
}) {
  if (!rows.length) return null;
  return (
    <section className="home__section">
      <div className="home__sectionHead">
        <h2>{title}</h2>
        <span className="home__asof">
          {total ? `${rows.length} of ${total}` : `${rows.length} instruments`}
        </span>
      </div>
      <div className="tableWrap">
        <table className="marketTable">
          <thead>
            <tr>
              <th scope="col">Instrument</th>
              <th scope="col">Last</th>
              <th scope="col">Session</th>
              <th scope="col">90 sessions</th>
              <th scope="col">Shape</th>
              <th scope="col">Signal</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol}>
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
                    data-dir={(r.market.window_change_pct ?? 0) >= 0 ? 'up' : 'down'}
                  >
                    {signedPct(r.market.window_change_pct)}
                  </span>
                </td>
                <td className="marketTable__spark">
                  <Spark points={r.market.series.slice(-40)} height={26} />
                </td>
                <td>
                  {r.risk?.available ? (
                    <span className="tag" data-tone={r.risk.state_tone}>
                      {r.risk.state_label}
                    </span>
                  ) : (
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
