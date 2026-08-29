import type { Metadata } from 'next';
import Link from 'next/link';
// Shows the standard "not found" page.
import { notFound } from 'next/navigation';

// The building blocks this page assembles. Almost nothing is drawn here directly -- the page
// is mostly an ORDER, and the order is the argument.
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

// Built fresh on every visit, because prices change.
export const dynamic = 'force-dynamic';

/** Whole days between an ISO session date and today, or null if unparseable. */
// PLAIN ENGLISH: how many days old is this data? Everything is done in UTC -- the world's
// single reference clock -- so the answer does not change depending on which country the
// server happens to be in.
function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const then = new Date(`${iso}T00:00:00Z`);
  // Unreadable date -> null, meaning "unknown". NOT zero, which would mean "up to date".
  if (Number.isNaN(then.getTime())) return null;
  const now = new Date();
  // Today at midnight UTC, so the comparison is day-to-day rather than moment-to-moment.
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  // 86,400,000 is the number of milliseconds in a day: 24 x 60 x 60 x 1000.
  return Math.round((today - then.getTime()) / 86400000);
}

/**
 * `2026-08-14` as `14 Aug 2026`, in a fixed locale and timezone.
 *
 * Rendered on the server and hydrated on the client, so it must not depend on either
 * machine's locale: a date that reads differently in two places is a date a reader cannot
 * quote back. An unparseable value is returned unchanged rather than replaced.
 */
// PLAIN ENGLISH: the date is written once on the server and again in the browser, and the two
// must match exactly. If the server said "8/14/2026" and the browser said "14/08/2026",
// React would notice the mismatch AND -- worse -- a reader could not reliably quote the date
// back to anyone. So the format and timezone are both nailed down: 'en-GB' and UTC.
// And note the last line: something unparseable is returned AS IT WAS, not replaced with a
// dash. Better to show the reader the odd raw value than to hide that anything was wrong.
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

// Build one page per company in the sample, at build time.
export async function generateStaticParams() {
  const symbols = await listInstrumentSymbols();
  return symbols.map((symbol) => ({ symbol }));
}

// The browser-tab title and the description search engines and link previews show.
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
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * ONE COMPANY'S PAGE, BUILT IN THREE LAYERS OF DEPTH.
 *
 * THE ANSWER, at the top: the price, the move, and ONE WORD for what the evidence showed.
 * Somebody who came to find out whether anything is going on gets their answer without
 * scrolling and without needing a glossary.
 *
 * THE EVIDENCE, behind a click: which kinds of evidence carried the signal, whether they
 * agreed with each other, and how much of the picture was even present.
 *
 * THE RESEARCH, as a link rather than a section. And the reason given is exactly right:
 * experiment ids, confidence intervals and random seeds are "the right answer to 'how do we
 * know', and the wrong answer to anything asked before it."
 * They are not hidden -- they are one click away. But putting them on the front page would
 * mean every visitor wades through them to reach the answer they came for.
 *
 * AND THE LAST PARAGRAPH IS THE MOST IMPORTANT ONE:
 * THE TWO PROVENANCES ARE NEVER MERGED.
 * The PRICE is a real observation from the last trading session.
 * The SIGNAL is a stored model result covering some earlier stretch of sessions.
 * They are different things, of different ages, with different standing. Put them side by
 * side with no labels and the layout ITSELF makes the false claim that both are equally
 * current. So each carries its own "where this came from" line.
 */
export default async function InstrumentPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const sourced = await getInstrument(symbol);
  const data = sourced.data;
  // No such company -> the proper 404 page.
  if (!data) notFound();

  // Unpack the six parts of the payload in one line.
  const { market, risk, observations, foundation, liquidity, announcements } = data;

  // Every displayed date and count is derived from what the service actually returned.
  // The fallbacks exist for an older exported bundle that predates the recency fields;
  // they fall back to a value the payload already carries, never to a literal date.
  // PLAIN ENGLISH: `??` means "use the left one, unless it is missing, then the right".
  // The chains here always end at ANOTHER REAL FIELD FROM THE DATA -- never at a hard-coded
  // date. A made-up fallback date would be an invented fact.
  const latestSession = market.latest_session ?? market.last_session;
  const coverageFrom = market.coverage_from ?? market.history_from;
  const windowFrom = market.window_from ?? market.series[0]?.date ?? null;
  // Turn the raw price rows into candlesticks -- dropping any session with broken
  // open/high/low/close.
  const candles = toCandles(market.series);
  const sessionCount = candles.length || market.window_sessions || market.sessions;
  // HOW MANY WERE DROPPED. `Math.max(..., 0)` guards against a negative, which cannot happen
  // but would print absurdly if it did.
  const droppedSessions = Math.max(market.series.length - candles.length, 0);

  // Staleness is never assumed to be zero. An older exported bundle carries no recency
  // fields, and defaulting that to "up to date" would assert currency the payload does
  // not support — the precise failure this section exists to prevent. So when the service
  // did not supply the figure, it is computed here from the latest session it did supply.
  // PLAIN ENGLISH: the tempting shortcut is `?? 0` -- "if we do not know how stale it is,
  // call it zero". That is a LIE dressed as a default: it claims the data is current on
  // exactly the occasions when nobody knows whether it is.
  // So instead: use the reported figure, or work it out from the date. And if even that is
  // impossible, keep null and SAY "recency not reported" further down.
  const daysBehind =
    market.days_since_latest_session ?? daysSince(latestSession);
  const isStale = daysBehind === null ? false : daysBehind > 0;
  // A separate flag for "we do not know", kept apart from "it is current".
  const recencyKnown = daysBehind !== null;
  // "Latest AVAILABLE market data" when behind -- one word doing a lot of work.
  const recencyLabel =
    market.recency_label ?? (isStale ? 'Latest available market data' : 'Latest market data');

  return (
    <div className="instrument">
      {/* Remembers which company is being read, so switching to research mode carries it. */}
      <SubjectRegistrar instrument={data.symbol} />

      {/* Breadcrumbs -- the trail back up. The `›` is decorative, so it is hidden from screen
          readers, which would otherwise announce a meaningless character. */}
      <nav className="crumbs">
        <Link href="/markets">Markets</Link>
        <span aria-hidden="true">›</span>
        <span>{data.symbol}</span>
      </nav>

      <header className="instrument__head">
        <div className="instrument__identity">
          <h1>{data.symbol}</h1>
          <div className="instrument__price">
            {/* THE ANSWER, LAYER ONE: price, move, and the session it is from -- the date
                attached to the number rather than left to be assumed. */}
            <span className="instrument__close">{inr(market.close)}</span>
            <Change value={market.change_pct} />
            <span className="instrument__session">on {latestSession}</span>
          </div>
          <WatchButton symbol={data.symbol} label={data.symbol} />
          <div className="instrument__tags">
            {/* IS THIS COMPANY EVEN IN THE STUDIED SAMPLE? Answered right at the top, because
                everything below means something different if it is not. */}
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
              // "Not analysed" -- NOT "no risk". A crucial difference: nothing was looked at,
              // which is not the same as having looked and found nothing.
              <span className="tag tag--quiet">Not analysed</span>
            )}
          </div>
        </div>

        {risk.available ? (
          <div className="instrument__verdict">
            {/* "EVIDENCE SIGNAL" rather than "risk score" -- describing what was seen rather
                than predicting what will happen. */}
            <span className="instrument__verdictLabel">Evidence signal</span>
            <SignalBadge
              label={risk.state_label ?? 'Normal'}
              tone={risk.state_tone ?? 'calm'}
              // The badge carries its own MEANING, so colour never has to be decoded.
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
        {/* PLAIN ENGLISH: two questions people constantly confuse.
            COVERAGE: how far back does the history go? (2015 onwards)
            RECENCY: how up to date is it? (last session was three days ago)
            A page proudly showing "data from 2015" says nothing about whether it includes
            yesterday. Here they are shown as separate things, with separate labels. */}
        <DirectionStrip direction={market.direction} observedTo={prettyDate(latestSession)} />

        {/* `data-stale` lets the styling react -- but every fact below is also in WORDS, so
            nothing depends on noticing a colour. */}
        <div className="recency" data-stale={isStale ? 'true' : 'false'}>
          <span className="recency__label">{recencyLabel}</span>
          <span className="recency__date">{prettyDate(latestSession)}</span>
          {windowFrom ? (
            // The exact span drawn on the chart: from this date to that one.
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
            {/* THREE OUTCOMES, NOT TWO -- and the first is the one that matters.
                1. We do not know how current this is, and we say so.
                2. It is N days behind today.
                3. It is the latest trading day.
                Collapsing 1 into 3 is precisely the failure the code above avoided. */}
            {!recencyKnown
              ? 'recency not reported by this source'
              : isStale
                ? `${daysBehind} day${daysBehind === 1 ? '' : 's'} behind today`
                : 'latest trading day'}
          </span>
          <p className="recency__note">
            {/* AND THE SENTENCE THAT CLOSES THE DOOR: "Nothing newer is claimed."
                Without it, a reader looking at a three-day-old price might reasonably assume
                nothing happened since. This says: we are not telling you that. */}
            {market.recency_note ??
              (isStale
                ? `No session later than ${latestSession} is present in this snapshot. Nothing newer is claimed.`
                : `This is the most recent session present in the data.`)}
          </p>
        </div>

        {droppedSessions > 0 ? (
          // BROKEN SESSIONS ARE COUNTED AND DECLARED, not silently skipped. A chart with an
          // unexplained gap invites the reader to invent a reason for it.
          // "They are omitted rather than repaired" is the principle: guessing a plausible
          // price to fill the hole would put an invented number on a price chart.
          <p className="small muted">
            {droppedSessions} session{droppedSessions === 1 ? '' : 's'} in this window had
            incomplete or inconsistent open/high/low/close and {droppedSessions === 1 ? 'is' : 'are'}{' '}
            not drawn. They are omitted rather than repaired.
          </p>
        ) : null}

        {candles.length >= 2 ? (
          // Enough good sessions -> the full candlestick chart.
          <TerminalChart candles={candles} indicators={market.indicators} />
        ) : (
          <>
            {/* NOT ENOUGH -> the simpler line chart, AND an explicit statement that it is a
                different thing. "it is not a candlestick and is not presented as one."
                A line chart shown where a candle chart was expected, without a word, would let
                a reader believe they were seeing highs and lows that are not there. */}
            <p className="small muted">
              Open, high and low are not present for these sessions, so no candles are
              drawn. The close-only series is shown instead — it is not a candlestick and
              is not presented as one.
            </p>
            <PriceChart points={market.series} />
          </>
        )}

        <div className="cardRow instrument__stats">
          {/* Four figures, and EVERY ONE carries its own qualifying line beneath it. */}
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
            // `.slice(0, 4)` takes the year out of "2015-01-01".
            value={coverageFrom.slice(0, 4)}
            // AND THE DISTINCTION SPELLED OUT AGAIN, right on the card: "coverage, not
            // recency". It is repeated because it is the confusion people actually make.
            sub={`Panel covers ${coverageFrom} onwards — coverage, not recency`}
          />
        </div>
        {/* PROVENANCE ONE: where the PRICE data came from. */}
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

      {/* Announcements and corporate actions, on the same timeline as the chart window. */}
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
            {/* PAST TENSE, DELIBERATELY: "What the evidence SHOWED". Not what will happen. */}
            <h2>What the evidence showed</h2>
            <span className="home__asof">
              {/* THE EXACT SESSIONS ASSESSED, in the heading. This is the second provenance,
                  and it is a different date range from the price above. */}
              {risk.sessions_scored} sessions assessed · {risk.scored_from} to {risk.scored_to}
            </span>
          </div>

          <div className="cardRow">
            <article className="tile">
              <span className="tile__label">Signal</span>
              <span className="tile__value">{risk.state_label}</span>
              {/* The meaning travels with the label, always. */}
              <span className="tile__note">{risk.state_meaning}</span>
            </article>
            <article className="tile">
              {/* "AGREEMENT ACROSS EVIDENCE" -- the plain-English name for what the model
                  calls uncertainty. */}
              <span className="tile__label">Agreement across evidence</span>
              <span className="tile__value">
                {/* Note the direction: LOW uncertainty means HIGH agreement. Turning the raw
                    number into High/Moderate/Low avoids every reader having to remember that
                    the scale runs backwards. */}
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
              {/* "EVIDENCE PRESENT" -- how much of the picture even existed. A confident
                  signal built on a third of the evidence is a different proposition from the
                  same signal built on all of it. */}
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

          {/* LAYER TWO, behind a click. The summary text is an invitation in ordinary words:
              "Understand why -- which evidence carried this". */}
          <Disclosure summary="Understand why — which evidence carried this">
            <p className="small muted" style={{ marginTop: 0 }}>
              {/* AND IMMEDIATELY, THE MISREADING PRE-EMPTED. A long bar means the signal
                  RESTED on that evidence -- not that that evidence is more trustworthy.
                  Exactly the conclusion a reader would otherwise draw from a big bar. */}
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
                // The raw number, with its direction explained so it cannot be read backwards.
                sub="Higher means the kinds of evidence pointed different ways"
              />
              <Figure
                label="Score"
                value={risk.score !== undefined ? risk.score.toFixed(3) : '—'}
                // FIVE WORDS THAT PREVENT THE COMMONEST ERROR OF ALL. A score of 0.850 looks
                // exactly like "an 85% chance". It is not. It only says this session ranks
                // above one scoring 0.400 -- nothing about how likely anything is.
                sub="A ranking, not a probability"
              />
            </div>

            {/* THE BOUNDING PARAGRAPH. Three limits, in escalating importance. */}
            <p className="instrument__bound">
              {/* 1. It covers those sessions and NO OTHERS.
                  2. It ranks; it is not a chance of anything.
                  3. AND THE BIG ONE: the patterns these models learned to spot were BUILT BY
                     THIS PROJECT, not observed in real markets. So the signal describes
                     behaviour resembling a construction of ours. It is not evidence that
                     anything improper occurred.
                  This appears on the ordinary product page, not buried in the research
                  section -- which is the whole point. */}
              This assessment covers the sessions listed above and no others. The score
              ranks sessions against each other; it is not the chance of anything
              happening. The episodes these models were trained to recognise were
              constructed by this project rather than observed in the market, so the
              assessment describes behaviour that resembles that construction.
            </p>

            {/* LAYER THREE: a link, and the link carries the company along so the research
                page opens already filtered to it. */}
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

          {/* PROVENANCE TWO, and it is deliberately DIFFERENT from the price one above:
              source 'snapshot', dated to when the scoring ended -- not to today, and not to
              the last price session. The two ages are kept visibly apart. */}
          <SourceLine of={{ ...sourced, source: 'snapshot', asOf: risk.scored_to ?? null }} />
        </section>
      ) : (
        <section className="instrument__block">
          {/* NOT ANALYSED. And the note draws the line explicitly: the price history above is
              real, and nothing has been assessed. Not "no risk found" -- nothing looked. */}
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
            {/* Decorative symbols, hidden from screen readers. */}
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
              {/* The company's own name in the blurb, turning an abstract page into a
                  question about the thing the reader is actually looking at. */}
              What {data.symbol} would have to do to raise an alarm, and why that line sits
              where it does.
            </span>
          </Link>
        </div>
      </section>
    </div>
  );
}
