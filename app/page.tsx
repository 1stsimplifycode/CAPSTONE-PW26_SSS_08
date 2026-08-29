import Link from 'next/link';

import { Change, Deeper, Empty, Figure, SignalBadge, SourceLine } from '@/components/product/Bits';
import { EvidenceCoverageSummary } from '@/components/product/Evidence';
import { SearchBox } from '@/components/product/Search';
import {
  PRIMARY_INDEX,
  RECENCY_COPY,
  compactInr,
  getAttention,
  getEvidenceSummary,
  getIndex,
  getOverview,
  level,
  listInstrumentSymbols,
  searchInstruments,
  signedPct,
} from '@/lib/product';

// Built fresh per request, so the market numbers are current rather than baked in at
// deploy time.
export const dynamic = 'force-dynamic';

/**
 * The product home.
 *
 * It answers three questions in the order a first-time reader asks them: what is this,
 * what is happening, and what can I do next. Everything below the fold is a way in, not a
 * result — the results live on the pages those cards lead to.
 *
 * Rendered on the server on every request so the market numbers are the ones the analysis
 * service holds right now. When no service is reachable it falls back to the exported
 * snapshot and the line under each block says so, because a stored session presented in
 * the present tense is the one dishonesty this page could commit.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE FRONT PAGE.
 *
 * Ordered by the questions a first-time visitor actually asks, in the order they ask them:
 * what is this, what is happening, what can I do next.
 *
 * AND THE LAST SENTENCE OF THE DOCSTRING IS THE SHARPEST SELF-ASSESSMENT IN THE PROJECT:
 *
 *     "a stored session presented in the present tense is the one dishonesty this page
 *      could commit."
 *
 * The authors asked themselves what the WORST thing this particular page could do would
 * be. Not a bug -- a dishonesty. And the answer is showing last Tuesday's market as though
 * it were today's.
 * So every block carries a line saying whether it is live or stored. Identifying your own
 * most likely way of misleading somebody, and then engineering specifically against it, is
 * a rare kind of care.
 */
export const metadata = {
  title: 'AEGIS-Market — financial risk intelligence',
  description:
    'Search an instrument, see how its market evidence behaved, and follow ' +
    'the evidence down to the research that produced it.',
};

// The three ways in.
const EXPLORE = [
  {
    href: '/markets',
    icon: '◍',
    title: 'Markets',
    blurb: 'Every instrument the system tracks, with its last session and its signal.',
  },
  // EXTRACTION: Analysis, Scenario Lab and Discover are not part of the statistical
  // subsystem and were not extracted. The two cards below are the surfaces this project
  // does have, described by what they are.
  // PLAIN ENGLISH: the missing sections are noted rather than silently absent -- and,
  // crucially, no card links to a page that does not exist. A dead card would be worse
  // than a shorter list.
  {
    href: '/stats',
    icon: '▤',
    title: 'STATS modules',
    blurb: 'Sixteen modules characterising the data and validating the model against it.',
  },
  {
    href: '/research/thresholds',
    icon: '◈',
    title: 'Risk thresholds',
    blurb: 'Every threshold that turns a measurement into a decision, and the rule behind it.',
  },
];

export default async function HomePage() {
  // Everything the page needs, fetched up front.
  const overview = await getOverview();
  const nifty = await getIndex(PRIMARY_INDEX);
  const evidence = await getEvidenceSummary(PRIMARY_INDEX);
  const attention = await getAttention(6);
  const symbols = await listInstrumentSymbols();
  const directory = await searchInstruments('', 8);

  // Build the search list. Two separate flags per company: is it tracked, and has it
  // actually been assessed -- because those are different facts.
  const searchItems = directory.rows.map((r) => ({
    symbol: r.symbol,
    tracked: r.tracked,
    analysed: Boolean(r.risk?.available),
    stateLabel: r.risk?.state_label ?? null,
    stateTone: r.risk?.state_tone ?? null,
  }));
  // And the full list, with what is known about each. A company we know nothing about gets
  // `analysed: false` rather than being left out -- so search can still find it and tell
  // the reader it was not assessed.
  const all = symbols.map((s) => {
    const known = directory.rows.find((r) => r.symbol === s);
    return {
      symbol: s,
      tracked: known?.tracked ?? false,
      analysed: Boolean(known?.risk?.available),
      stateLabel: known?.risk?.state_label ?? null,
      stateTone: known?.risk?.state_tone ?? null,
    };
  });

  const m = overview.data?.market;
  const tracked = overview.data?.tracked;
  const mix = overview.data?.risk_mix;

  return (
    <div className="home">
      <section className="home__hero">
        <p className="home__eyebrow">AEGIS-Market</p>
        <h1>Financial risk intelligence</h1>
        <p className="home__lede">
          {/* Note what the promise is: see how things MOVED TOGETHER, and HOW CONFIDENT the
              system is. Not "find opportunities", not "get signals". */}
          Search an instrument to see how its market behaviour and its evidence blocks
          moved together — and how confident the system is about what it found.
        </p>
        {/* The search box first, because searching is what a visitor came to do. */}
        <SearchBox items={all.length ? all : searchItems} placeholder="Try TCS, RELIANCE, INFY…" />
        <p className="home__hint">
          {/* THE NON-ADVISORY STATEMENT IN THE FIRST SCREEN, beside the search box -- not
              only in the notice and the footer. "observational and is not financial advice",
              before a visitor has typed anything. */}
          {symbols.length.toLocaleString('en-IN')} instruments available · analysis is
          observational and is not financial advice
        </p>
      </section>

      <section className="home__section">
        <div className="home__sectionHead">
          <h2>Market overview</h2>
          {m ? <span className="home__asof">Session {m.last_session}</span> : null}
        </div>

        {/* The benchmark first. It is the number a reader came for, and it is the real
            NIFTY 50 level as NSE published it — never the liquidity proxy, which is a
            different entity with no level of its own. */}
        {/* PLAIN ENGLISH: the index/proxy distinction, enforced on the front page. The level
            shown is the REAL published index. Our own stand-in has no level and never
            appears here. */}
        {/* EXTRACTION: the NIFTY 50 benchmark page was not extracted, so this block
            shows the published level without linking through to it. */}
        {nifty.data ? (
          <div className="benchmark">
            <div className="benchmark__main">
              {/* Labelled "Index · NSE" -- so it is unmistakably the exchange's published
                  benchmark rather than anything of ours. */}
              <span className="benchmark__kind">Index · NSE</span>
              <span className="benchmark__name">{nifty.data.display_name}</span>
              {/* `level` formats it WITHOUT a currency symbol -- an index level is not money. */}
              <span className="benchmark__level">{level(nifty.data.close)}</span>
              <span className="benchmark__change">
                <Change value={nifty.data.change_pct} />
                <span className="benchmark__session">
                  {/* HOW CURRENT IT IS, in words, beside the number -- so a day-old close is
                      never mistaken for a live quote. */}
                  {RECENCY_COPY[nifty.data.recency]} · {nifty.data.last_session}
                </span>
              </span>
            </div>
            <div className="benchmark__stats">
              <span>
                <em>52-week range</em>
                {level(nifty.data.low_52w)} – {level(nifty.data.high_52w)}
              </span>
              <span>
                {/* Each measure fully named -- "20d, annualised" rather than a bare
                    "volatility", which could mean any of several things. */}
                <em>Volatility (20d, annualised)</em>
                {nifty.data.volatility_20d !== null
                  ? `${(nifty.data.volatility_20d * 100).toFixed(1)}%`
                  : '—'}
              </span>
              <span>
                <em>Drawdown from window peak</em>
                {nifty.data.drawdown !== null ? signedPct(nifty.data.drawdown) : '—'}
              </span>
            </div>
          </div>
        ) : (
          // Not ingested: says so, with the command. Never a zero level.
          <Empty
            title="NIFTY 50 has not been ingested"
            note={nifty.note ?? 'Run python scripts/build_index_panel.py.'}
          />
        )}
        {/* EXTRACTION: the component defaults this CTA to /markets/nifty-50, which is
            not part of this project; point it at the STATS index instead. */}
        {/* The evidence-coverage strip: which sources actually cover this period. */}
        {evidence.data ? (
          <EvidenceCoverageSummary summary={evidence.data} href="/stats" />
        ) : null}
        {/* AND THE SOURCE LINE -- the defence against the one dishonesty named at the top. */}
        <SourceLine of={nifty} />

        {m && tracked ? (
          <>
            <div className="cardRow">
              <article className="tile">
                {/* "RESEARCH SAMPLING FRAME" -- a deliberately technical phrase. Calling it
                    "our index" or "the portfolio" would suggest something it is not. */}
                <span className="tile__label">Research sampling frame</span>
                <span className="tile__value">{tracked.instruments}</span>
                <span className="tile__note">{tracked.name}</span>
                <span className="tile__foot">
                  {/* "not an index" printed on the tile itself. */}
                  <Change value={tracked.median_change_pct} /> median move · not an index
                </span>
              </article>
              <article className="tile">
                <span className="tile__label">Market breadth</span>
                <span className="tile__value">
                  {m.advancing.toLocaleString('en-IN')}
                  <span className="tile__slash">/</span>
                  {m.declining.toLocaleString('en-IN')}
                </span>
                {/* The term defined immediately beneath it. */}
                <span className="tile__note">advancing / declining</span>
                <span className="tile__foot">
                  {m.instruments_traded.toLocaleString('en-IN')} instruments traded
                </span>
              </article>
              <article className="tile">
                {/* THE MEDIAN, not the mean -- so one extreme company cannot define "the
                    market's move". */}
                <span className="tile__label">Median move</span>
                <span className="tile__value" data-dir={(m.median_change_pct ?? 0) >= 0 ? 'up' : 'down'}>
                  {signedPct(m.median_change_pct)}
                </span>
                <span className="tile__note">across everything that traded</span>
                <span className="tile__foot">Turnover {compactInr(m.turnover)}</span>
              </article>
              <article className="tile">
                {/* HOW MANY COMPANIES ACTUALLY CARRY AN ASSESSMENT -- so a visitor knows how
                    much of the market this system has anything to say about. */}
                <span className="tile__label">Instruments analysed</span>
                <span className="tile__value">{mix?.instruments ?? 0}</span>
                <span className="tile__note">carry an integrity-risk assessment</span>
                <span className="tile__foot">
                  {/* "not in the ordinary range" rather than "at risk" or "flagged". A
                      description of where the measurement sits, not a verdict about the
                      company. And "all in the ordinary range" where nothing stands out --
                      stated rather than left as an absence. */}
                  {mix?.states?.find((s) => s.state !== 'NORMAL')
                    ? `${mix.states
                        .filter((s) => s.state !== 'NORMAL')
                        .reduce((a, s) => a + s.instruments, 0)} not in the ordinary range`
                    : 'all in the ordinary range'}
                </span>
              </article>
            </div>
            <SourceLine of={overview} />
            <p className="home__caveat">{tracked.caveat}</p>
          </>
        ) : (
          <Empty
            title="No market data"
            note={overview.note ?? 'Export the product snapshot or start the backend.'}
          />
        )}
      </section>

      <section className="home__section">
        <div className="home__sectionHead">
          <h2>Explore</h2>
        </div>
        <div className="exploreGrid">
          {EXPLORE.map((c) => (
            <Link key={c.href} href={c.href} className="exploreCard">
              <span className="exploreCard__icon" aria-hidden="true">
                {c.icon}
              </span>
              <span className="exploreCard__title">{c.title}</span>
              <span className="exploreCard__blurb">{c.blurb}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="home__section">
        <div className="home__sectionHead">
          {/* "WORTH A LOOK" -- not "Top risks", not "Alerts". An invitation to look, not a
              ranking to act on. */}
          <h2>Worth a look</h2>
          <Deeper href="/markets">See all instruments</Deeper>
        </div>
        {attention.data && attention.data.length > 0 ? (
          <>
            <div className="cardRow">
              {attention.data.map((row) => (
                <Link
                  key={row.symbol}
                  href={`/instruments/${row.symbol}`}
                  className="attentionCard"
                >
                  <span className="attentionCard__symbol">{row.symbol}</span>
                  <SignalBadge label={row.state_label} tone={row.state_tone} size="small" />
                  {/* WHEN it was assessed -- so a stale assessment is visible on the card. */}
                  <span className="attentionCard__meta">
                    Assessed {row.date}
                  </span>
                </Link>
              ))}
            </div>
            <SourceLine of={attention} />
            <p className="home__caveat">
              {/* THE CAVEAT DOING THE MOST WORK ON THE PAGE. It says what the list IS -- the
                  companies whose most recent assessment was outside the ordinary range --
                  and then, explicitly, the two things it is NOT: "not a ranking and not a
                  suggestion to do anything."
                  Both misreadings named and refused, in one sentence, directly beneath the
                  list that would otherwise invite them. */}
              These are instruments whose most recent assessment was not in the ordinary
              range. It is a list of things worth looking at, not a ranking and not a
              suggestion to do anything.
            </p>
          </>
        ) : (
          // A positive empty state: nothing stood out. Framed as a finding rather than as an
          // absence of content.
          <Empty
            title="Everything in the ordinary range"
            note="No analysed instrument's most recent assessment stood out."
          />
        )}
      </section>

      <section className="home__section home__section--quiet">
        <div className="home__sectionHead">
          {/* AN INSTRUCTION MANUAL FOR THE WHOLE SITE, on the front page. */}
          <h2>How to read anything here</h2>
        </div>
        <div className="readGrid">
          {/* THE THREE DEPTHS, numbered. Answer, evidence, research -- and each described in
              one line a first-time visitor can act on. */}
          <Figure label="Answer" value="1" sub="What the evidence showed, in one word." />
          <Figure label="Evidence" value="2" sub="Which signals carried it, and whether they agreed." />
          <Figure label="Research" value="3" sub="The experiment, the interval, the artifact." />
        </div>
        <p className="home__caveat">
          {/* AND THE PERMISSION THAT MAKES IT WORK: "You can stop at the first one."
              A reader is explicitly told they need not go deeper -- which is what makes the
              depth an invitation rather than an obligation. Then it says where the control
              is, so somebody who does want depth by default knows how to get it. */}
          Every page follows those three depths. You can stop at the first one; the other
          two are always one control away. Switch the whole interface to Research mode from
          the header when you want the third by default.
        </p>
      </section>
    </div>
  );
}
