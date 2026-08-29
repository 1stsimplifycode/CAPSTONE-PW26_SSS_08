import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import {
  Change,
  Empty,
  Figure,
  PriceChart,
  SignalBadge,
  SignalBars,
  SourceLine,
  toCandles,
} from '@/components/product/Bits';
import { TerminalChart } from '@/components/product/TerminalChart';
import { DirectionStrip } from '@/components/product/DirectionStrip';
import { Disclosure } from '@/components/product/Disclosure';
import { EventFeed } from '@/components/product/EventFeed';
import { FinancialHealth } from '@/components/product/FinancialHealth';
import { Foundation } from '@/components/product/Foundation';
import { Liquidity } from '@/components/product/Liquidity';
import { RiskHeader } from '@/components/product/RiskHeader';
import { RiskProfile } from '@/components/product/RiskProfile';
import { WatchButton } from '@/components/product/WatchButton';
import { SubjectRegistrar } from '@/components/ui/SubjectRegistrar';
import {
  compactInr,
  getInstrument,
  inr,
  listInstrumentSymbols,
  signedPct,
} from '@/lib/product';

export const dynamic = 'force-dynamic';

/** Whole days between an ISO session date and today, or null if unparseable. */
function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const then = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(then.getTime())) return null;
  const now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((today - then.getTime()) / 86400000);
}

/**
 * `2026-08-14` as `14 Aug 2026`, in a fixed locale and timezone.
 *
 * Rendered on the server and hydrated on the client, so it must not depend on either
 * machine's locale: a date that reads differently in two places is a date a reader cannot
 * quote back. An unparseable value is returned unchanged rather than replaced.
 */
function prettyDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(d);
}

export async function generateStaticParams() {
  const symbols = await listInstrumentSymbols();
  return symbols.map((symbol) => ({ symbol }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>;
}): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} — AEGIS-Market`,
    description: `Market behaviour and integrity-risk evidence for ${symbol.toUpperCase()}.`,
  };
}

/**
 * One instrument, in three depths.
 *
 * **The answer** is the top of the page: the price, the move, and one word for what the
 * evidence showed. Someone who came to find out whether anything is going on has their
 * answer without scrolling and without a glossary.
 *
 * **The evidence** is the first disclosure: which kinds of evidence carried the signal,
 * whether they agreed, and how much of the picture was present. This is where a reader
 * goes when the one word was not enough.
 *
 * **The research** is a link, not a section. Experiment identifiers, intervals, seeds and
 * artifacts are the right answer to "how do we know", and the wrong answer to anything
 * asked before it — so they live in research mode and this page points at them.
 *
 * The two provenances are never merged. The price is an observation from the panel's last
 * session; the signal is a stored model result over the sessions it scored, and the page
 * says so beside each rather than letting the layout imply they are equally current.
 */
export default async function InstrumentPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const sourced = await getInstrument(symbol);
  const data = sourced.data;
  if (!data) notFound();

  const { market, risk, observations, foundation, liquidity, announcements } = data;

  // Every displayed date and count is derived from what the service actually returned.
  // The fallbacks exist for an older exported bundle that predates the recency fields;
  // they fall back to a value the payload already carries, never to a literal date.
  const latestSession = market.latest_session ?? market.last_session;
  const coverageFrom = market.coverage_from ?? market.history_from;
  const windowFrom = market.window_from ?? market.series[0]?.date ?? null;
  const candles = toCandles(market.series);
  const sessionCount = candles.length || market.window_sessions || market.sessions;
  const droppedSessions = Math.max(market.series.length - candles.length, 0);

  // Staleness is never assumed to be zero. An older exported bundle carries no recency
  // fields, and defaulting that to "up to date" would assert currency the payload does
  // not support — the precise failure this section exists to prevent. So when the service
  // did not supply the figure, it is computed here from the latest session it did supply.
  const daysBehind =
    market.days_since_latest_session ?? daysSince(latestSession);
  const isStale = daysBehind === null ? false : daysBehind > 0;
  const recencyKnown = daysBehind !== null;
  const recencyLabel =
    market.recency_label ?? (isStale ? 'Latest available market data' : 'Latest market data');

  return (
    <div className="instrument">
      <SubjectRegistrar instrument={data.symbol} />

      <nav className="crumbs">
        <Link href="/markets">Markets</Link>
        <span aria-hidden="true">›</span>
        <span>{data.symbol}</span>
      </nav>

      <header className="instrument__head">
        <div className="instrument__identity">
          <h1>{data.symbol}</h1>
          <div className="instrument__price">
            <span className="instrument__close">{inr(market.close)}</span>
            <Change value={market.change_pct} />
            <span className="instrument__session">on {latestSession}</span>
          </div>
          <WatchButton symbol={data.symbol} label={data.symbol} />
          <div className="instrument__tags">
            {data.tracked ? (
              <span className="tag">
                Tracked sample{data.tracked_rank ? ` · #${data.tracked_rank}` : ''}
              </span>
            ) : (
              <span className="tag tag--quiet">Outside the tracked sample</span>
            )}
            {risk.available ? (
              <span className="tag" data-tone={risk.state_tone}>
                {risk.state_label}
              </span>
            ) : (
              <span className="tag tag--quiet">Not analysed</span>
            )}
          </div>
        </div>

        {risk.available ? (
          <div className="instrument__verdict">
            <span className="instrument__verdictLabel">Evidence signal</span>
            <SignalBadge
              label={risk.state_label ?? 'Normal'}
              tone={risk.state_tone ?? 'calm'}
              meaning={risk.state_meaning}
            />
          </div>
        ) : null}
      </header>

      <div className="sec__workspace">
        <div className="sec__main">
      <section className="instrument__block">
        <div className="home__sectionHead">
          <h2>Price</h2>
          <span className="home__asof">
            {sessionCount} sessions · {signedPct(market.window_change_pct)} over the window
          </span>
        </div>

        {/*
          Recency and coverage are different claims and are shown as different things.
          The label says "Latest available" whenever the panel is behind today, so the
          page never implies it is current when it is not.
        */}
        <DirectionStrip direction={market.direction} observedTo={prettyDate(latestSession)} />

        <div className="recency" data-stale={isStale ? 'true' : 'false'}>
          <span className="recency__label">{recencyLabel}</span>
          <span className="recency__date">{prettyDate(latestSession)}</span>
          {windowFrom ? (
            <span className="recency__window">
              {sessionCount} sessions shown · {prettyDate(windowFrom)} → {prettyDate(latestSession)}
            </span>
          ) : null}
          {market.previous_session ? (
            <span className="recency__window">
              previous session {prettyDate(market.previous_session)}
            </span>
          ) : null}
          <span className="recency__flag">
            {!recencyKnown
              ? 'recency not reported by this source'
              : isStale
                ? `${daysBehind} day${daysBehind === 1 ? '' : 's'} behind today`
                : 'latest trading day'}
          </span>
          <p className="recency__note">
            {market.recency_note ??
              (isStale
                ? `No session later than ${latestSession} is present in this snapshot. Nothing newer is claimed.`
                : `This is the most recent session present in the data.`)}
          </p>
        </div>

        {droppedSessions > 0 ? (
          <p className="small muted">
            {droppedSessions} session{droppedSessions === 1 ? '' : 's'} in this window had
            incomplete or inconsistent open/high/low/close and {droppedSessions === 1 ? 'is' : 'are'}{' '}
            not drawn. They are omitted rather than repaired.
          </p>
        ) : null}

        {candles.length >= 2 ? (
          <TerminalChart candles={candles} indicators={market.indicators} />
        ) : (
          <>
            <p className="small muted">
              Open, high and low are not present for these sessions, so no candles are
              drawn. The close-only series is shown instead — it is not a candlestick and
              is not presented as one.
            </p>
            <PriceChart points={market.series} />
          </>
        )}

        <div className="cardRow instrument__stats">
          <Figure label="Last close" value={inr(market.close)} sub={`Session ${latestSession}`} />
          <Figure
            label="Session move"
            value={signedPct(market.change_pct)}
            tone={(market.change_pct ?? 0) >= 0 ? 'up' : 'down'}
            sub={market.change !== null ? `${inr(market.change)} per share` : undefined}
          />
          <Figure label="Turnover" value={compactInr(market.turnover)} sub="on the last session" />
          <Figure
            label="Historical coverage"
            value={coverageFrom.slice(0, 4)}
            sub={`Panel covers ${coverageFrom} onwards — coverage, not recency`}
          />
        </div>
        <SourceLine of={sourced} />
        </section>
        </div>

        <aside className="sec__aside">
          <RiskHeader
            symbol={data.symbol}
            market={market}
            risk={risk}
            liquidity={liquidity}
            foundation={foundation}
            dataThrough={prettyDate(latestSession)}
            variant="aside"
          />
        </aside>
      </div>

      <EventFeed
        announcements={announcements}
        corporateActions={foundation?.corporate_actions}
        windowFrom={windowFrom}
      />

      <RiskProfile market={market} risk={risk} liquidity={liquidity} />

      <FinancialHealth />

      <Foundation foundation={foundation} />

      <Liquidity liquidity={liquidity} />

      {risk.available ? (
        <section className="instrument__block">
          <div className="home__sectionHead">
            <h2>What the evidence showed</h2>
            <span className="home__asof">
              {risk.sessions_scored} sessions assessed · {risk.scored_from} to {risk.scored_to}
            </span>
          </div>

          <div className="cardRow">
            <article className="tile">
              <span className="tile__label">Signal</span>
              <span className="tile__value">{risk.state_label}</span>
              <span className="tile__note">{risk.state_meaning}</span>
            </article>
            <article className="tile">
              <span className="tile__label">Agreement across evidence</span>
              <span className="tile__value">
                {risk.uncertainty !== undefined
                  ? risk.uncertainty < 0.2
                    ? 'High'
                    : risk.uncertainty < 0.5
                      ? 'Moderate'
                      : 'Low'
                  : '—'}
              </span>
              <span className="tile__note">
                How much the different kinds of evidence pointed the same way
              </span>
            </article>
            <article className="tile">
              <span className="tile__label">Evidence present</span>
              <span className="tile__value">
                {risk.coverage !== null && risk.coverage !== undefined
                  ? `${Math.round(risk.coverage * 100)}%`
                  : '—'}
              </span>
              <span className="tile__note">
                Share of the evidence blocks that existed for these sessions
              </span>
            </article>
          </div>

          {observations.length > 0 ? (
            <ul className="observations">
              {observations.map((o, i) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          ) : null}

          <Disclosure summary="Understand why — which evidence carried this">
            <p className="small muted" style={{ marginTop: 0 }}>
              Each bar is that evidence block&rsquo;s share of the total contribution
              across the sessions assessed. A large share means the signal rested on it,
              not that it is more reliable than the others.
            </p>
            <SignalBars blocks={risk.blocks ?? []} />

            <div className="cardRow" style={{ marginTop: 18 }}>
              <Figure
                label="Sessions assessed"
                value={String(risk.sessions_scored ?? 0)}
                sub={`${risk.scored_from} to ${risk.scored_to}`}
              />
              <Figure
                label="Disagreement"
                value={risk.uncertainty !== undefined ? risk.uncertainty.toFixed(2) : '—'}
                sub="Higher means the kinds of evidence pointed different ways"
              />
              <Figure
                label="Score"
                value={risk.score !== undefined ? risk.score.toFixed(3) : '—'}
                sub="A ranking, not a probability"
              />
            </div>

            <p className="instrument__bound">
              This assessment covers the sessions listed above and no others. The score
              ranks sessions against each other; it is not the chance of anything
              happening. The episodes these models were trained to recognise were
              constructed by this project rather than observed in the market, so the
              assessment describes behaviour that resembles that construction.
            </p>

            <p className="instrument__deeper">
              <Link href={`/research/experiments?instrument=${data.symbol}`}>
                View research evidence →
              </Link>
              <span className="small muted">
                Experiment identifiers, intervals, calibration, ablations and the artifact
                each number was read from.
              </span>
            </p>
          </Disclosure>

          <SourceLine of={{ ...sourced, source: 'snapshot', asOf: risk.scored_to ?? null }} />
        </section>
      ) : (
        <section className="instrument__block">
          <Empty
            title="No assessment for this instrument"
            note={
              risk.why ??
              'This instrument is outside the scored evaluation sample. Its price history is above; nothing has been assessed.'
            }
          />
        </section>
      )}

      <section className="instrument__block">
        <div className="home__sectionHead">
          <h2>Go further</h2>
        </div>
        {/* EXTRACTION: the Scenario Lab, Analysis and Watchlist cards pointed at
            product surfaces this project does not contain. The two below are the
            statistical routes that answer the same "go deeper" question. */}
        <div className="exploreGrid">
          <Link href="/stats" className="exploreCard">
            <span className="exploreCard__icon" aria-hidden="true">
              ▤
            </span>
            <span className="exploreCard__title">STATS modules</span>
            <span className="exploreCard__blurb">
              How evidence behaves across the whole sample, not just this instrument.
            </span>
          </Link>
          <Link href="/research/thresholds" className="exploreCard">
            <span className="exploreCard__icon" aria-hidden="true">
              ◈
            </span>
            <span className="exploreCard__title">Risk thresholds</span>
            <span className="exploreCard__blurb">
              What {data.symbol} would have to do to raise an alarm, and why that line sits
              where it does.
            </span>
          </Link>
        </div>
      </section>
    </div>
  );
}
