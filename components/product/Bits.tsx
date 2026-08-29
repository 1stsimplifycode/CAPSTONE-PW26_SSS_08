/**
 * The product's vocabulary, as components.
 *
 * Every piece here is built for the same job: say the answer, in the fewest words that
 * remain true, and put the way to go deeper next to it rather than the depth itself.
 * A reader who wants the number gets the number; a reader who wants to know where it came
 * from finds a control, not a paragraph.
 *
 * These are server components. Only `Disclosure` and the search box need the client, and
 * they live apart for that reason.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SMALL PIECES THE PRODUCT PAGES ARE BUILT FROM.
 *
 * AND THE DESIGN RULE IS IN THE FIRST PARAGRAPH, worth reading twice:
 *
 *     "say the answer, in the fewest words that remain true"
 *
 * Note the last three words. Not simply the fewest words -- the fewest that are STILL TRUE.
 * That is the whole balancing act of this project in one phrase: brevity is a goal, and
 * accuracy is a constraint on it rather than a competing goal.
 *
 * And the second half: put the WAY to go deeper beside the answer, not the depth itself.
 * A reader who wants the number gets the number. A reader who wants to know where it came
 * from finds a link -- not three paragraphs they did not ask for.
 */
import Link from 'next/link';

import type { BlockShare, Sourced, Tone } from '@/lib/product';
import { direction, signedPct, sourceNote } from '@/lib/product';

/** The headline verdict: one word, one colour, one sentence of meaning. */
export function SignalBadge({
  label,
  tone,
  meaning,
  size = 'large',
}: {
  label: string;
  tone: Tone;
  meaning?: string;
  size?: 'large' | 'small';
}) {
  return (
    <div className={`signal signal--${size}`} data-tone={tone}>
      {/* The coloured dot is decoration and is hidden from screen readers -- the word
          beside it carries the meaning. */}
      <span className="signal__dot" aria-hidden="true" />
      <span className="signal__label">{label}</span>
      {/* The explanation appears at large size only. On a small badge there is no room, and
          a truncated explanation would be worse than none. */}
      {meaning && size === 'large' ? (
        <span className="signal__meaning">{meaning}</span>
      ) : null}
    </div>
  );
}

/** A number with its name under it. The number is the point, so it is the large thing. */
export function Figure({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'up' | 'down' | 'flat';
}) {
  return (
    // The VALUE first and largest, the label beneath. The visual hierarchy matches what the
    // reader is looking for.
    <div className="figure" data-tone={tone ?? 'flat'}>
      <span className="figure__value">{value}</span>
      <span className="figure__label">{label}</span>
      {sub ? <span className="figure__sub">{sub}</span> : null}
    </div>
  );
}

// A percentage change, coloured by direction.
export function Change({ value }: { value: number | null | undefined }) {
  return (
    <span className="change" data-dir={direction(value)}>
      {/* `signedPct` always shows the sign, and shows an em-dash for a missing value --
          never a zero. */}
      {signedPct(value)}
    </span>
  );
}

/**
 * How much each kind of evidence carried, as bars.
 *
 * Shares, not scores. A reader comparing "financial text 0.62" against "price and volume
 * 0.31" would be comparing two numbers on scales they have no way to know; the share of
 * the total is the comparison they actually mean, and it is the one that can be drawn.
 */
// PLAIN ENGLISH: two raw scores from two different measurements are not comparable -- they
// may be on completely different scales, and the reader has no way to know. Turning them
// into SHARES OF THE TOTAL gives the comparison a reader is actually trying to make, and it
// is the only one the picture can honestly show.
/**
 * A share, written so a measured value never reads as an unmeasured one.
 *
 * `toFixed(0)` turned every share under half a percent into "0%", and the thinnest blocks
 * sat there. Each had been measured, each had a positive contribution, and the chart said
 * they added nothing — which is a different finding from the one the experiment produced,
 * and the more damaging one, because it reads as "this evidence is worthless" rather than
 * "this evidence is largely redundant".
 *
 * So the precision follows the magnitude: small numbers get the digits that distinguish
 * them from zero, large ones do not carry noise they have not earned.
 */
// PLAIN ENGLISH: A REAL BUG, CAUGHT, AND WORTH UNDERSTANDING.
// Rounding to whole percentages turned every contribution under 0.5% into "0%". Those blocks
// HAD been measured. They HAD contributed something. And the chart said they contributed
// nothing.
// The comment identifies precisely why that is worse than a rounding error: "0%" reads as
// "this evidence is worthless", when the truth was "this evidence is largely redundant".
// Those are different findings, and the chart was publishing the wrong one.
// The fix is elegant: MORE decimal places for smaller numbers, fewer for larger. So a tiny
// contribution is visibly small rather than invisibly zero -- and a large one does not carry
// decimal places it has not earned.
export function shareLabel(share: number): string {
  // A genuine zero or an unusable value is honestly "0%".
  if (!Number.isFinite(share) || share <= 0) return '0%';
  const pct = share * 100;
  // Under 1%: two decimals, so 0.4% shows as "0.40%" rather than vanishing.
  if (pct < 1) return `${pct.toFixed(2)}%`;
  // Under 10%: one decimal.
  if (pct < 10) return `${pct.toFixed(1)}%`;
  // Above that, whole percentages -- more precision would be noise.
  return `${pct.toFixed(0)}%`;
}

export function SignalBars({
  blocks,
  limit = 6,
}: {
  blocks: BlockShare[];
  limit?: number;
}) {
  const shown = blocks.slice(0, limit);
  // Scaled to the LARGEST bar rather than to 100%, so small differences between the blocks
  // are still visible rather than all being squashed against the left edge.
  const widest = Math.max(...shown.map((m) => m.share), 0.0001);
  return (
    <ul className="bars">
      {shown.map((m) => (
        <li className="bars__row" key={m.block}>
          <span className="bars__label">{m.label}</span>
          <span className="bars__track">
            <span
              className="bars__fill"
              // A minimum width of 2%, so a tiny contribution is a visible sliver rather
              // than nothing at all -- the same reasoning as the label above, applied to the
              // bar itself.
              style={{ width: `${Math.max(2, (m.share / widest) * 100)}%` }}
            />
          </span>
          {/* And the number printed too, so the bar is never the only information. */}
          <span className="bars__value">{shareLabel(m.share)}</span>
        </li>
      ))}
    </ul>
  );
}

/** A price line. Small, unlabelled, and there to show shape rather than to be read off. */
// An honest statement of purpose: this is for SHAPE, not for reading values off. Hence no
// axis and no labels -- adding them would invite a precision it cannot support.
export function Spark({
  points,
  height = 44,
}: {
  points: { close: number }[];
  height?: number;
}) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.close);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const step = 100 / (values.length - 1);
  const path = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(
      100 - ((v - low) / span) * 100
    ).toFixed(2)}`)
    .join(' ');
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg
      className="spark"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      height={height}
      // Hidden from screen readers entirely -- and correctly so. It carries no information
      // that is not already in the numbers beside it, so reading it out would be noise.
      aria-hidden="true"
      data-dir={rising ? 'up' : 'down'}
    >
      <path d={path} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** A larger price chart with a value axis, for the instrument page. */
/** One session's candle, with the real four prices. */
export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  turnover?: number | null;
}

/**
 * Keep only sessions that carry a genuine, self-consistent OHLC quartet.
 *
 * A row missing an open, or whose high sits below its close, is dropped rather than
 * repaired. Repairing it would put a candle on the screen that no exchange published, and
 * the count of drawn candles is reported so a gap is visible instead of silent.
 */
// PLAIN ENGLISH: "dropped rather than repaired" is the rule, and it is the right one.
// A row whose high is below its close is impossible -- the data is wrong. You COULD fix it
// by nudging the high up. Then the chart would show a candle that never existed, and it
// would be indistinguishable from all the real ones.
// So it is dropped, and the NUMBER DROPPED IS REPORTED on the chart -- so the gap is visible
// rather than silent.
export function toCandles(
  points: {
    date: string;
    close: number;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    volume?: number | null;
    turnover?: number | null;
  }[],
): Candle[] {
  const out: Candle[] = [];
  for (const p of points) {
    const { open, high, low, close } = p;
    // CHECK ONE: all four prices must be present and be real numbers.
    if (
      typeof open !== 'number' ||
      typeof high !== 'number' ||
      typeof low !== 'number' ||
      typeof close !== 'number' ||
      !Number.isFinite(open) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close)
    ) {
      continue;
    }
    // CHECK TWO: they must make sense together. The high must be the highest, the low the
    // lowest. A row failing this is corrupt, however plausible each number looks alone.
    if (high < Math.max(open, close) || low > Math.min(open, close) || high < low) {
      continue;
    }
    out.push({
      date: p.date,
      open,
      high,
      low,
      close,
      // Volume and turnover kept as null where absent, never as zero.
      volume: p.volume ?? null,
      turnover: p.turnover ?? null,
    });
  }
  return out;
}

// Large numbers at Indian scale.
const inrCompact = (n: number) =>
  n >= 1e7 ? `${(n / 1e7).toFixed(2)} Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(2)} L` : n.toFixed(0);

/**
 * An OHLC candlestick chart drawn from real sessions.
 *
 * Each candle is one trading session: a wick from low to high, a body between open and
 * close, green when the session closed at or above its open and red when it closed below.
 * Nothing is interpolated between sessions, so a market holiday leaves no candle rather
 * than a straight line implying a price nobody traded at.
 */
// PLAIN ENGLISH: the last clause is the important one. On a market holiday nothing traded.
// Drawing a line across the gap would imply prices on a day the market was shut. So there is
// simply no candle -- the gap is the truth.
export function CandleChart({
  candles,
  height = 260,
  droppedSessions = 0,
}: {
  candles: Candle[];
  height?: number;
  // How many rows failed the checks above -- so the omission can be reported.
  droppedSessions?: number;
}) {
  if (candles.length < 2) {
    return (
      // Names the actual requirement, so a reader knows what is missing rather than only
      // that something is.
      <p className="small muted">
        Not enough sessions with complete open/high/low/close to draw candles.
      </p>
    );
  }
  const low = Math.min(...candles.map((c) => c.low));
  const high = Math.max(...candles.map((c) => c.high));
  const span = high - low || 1;
  // 4% padding so candles do not touch the edges.
  const pad = span * 0.04;
  const yLow = low - pad;
  const ySpan = high + pad - yLow || 1;
  const y = (v: number) => ((high + pad - v) / ySpan) * 100;

  const slot = 100 / candles.length;
  const bodyW = Math.max(slot * 0.62, 0.12);
  const mid = (i: number) => i * slot + slot / 2;

  const first = candles[0];
  const last = candles[candles.length - 1];
  const rising = last.close >= first.open;
  const ticks = [high + pad, (high + pad + yLow) / 2, yLow];

  return (
    <figure className="candleChart" data-dir={rising ? 'up' : 'down'}>
      <div className="candleChart__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img"
             // A full description including the count and the date range -- so a listening
             // reader gets the shape of the chart rather than the word "chart".
             aria-label={`Candlestick chart, ${candles.length} sessions from ${first.date} to ${last.date}`}>
          {ticks.map((t, i) => (
            <line key={i} className="candleChart__grid" x1="0" x2="100"
                  y1={y(t).toFixed(2)} y2={y(t).toFixed(2)} vectorEffect="non-scaling-stroke" />
          ))}
          {candles.map((c, i) => {
            const up = c.close >= c.open;
            const top = y(Math.max(c.open, c.close));
            const bottom = y(Math.min(c.open, c.close));
            // A minimum height, so a day that opened and closed at the same price still
            // draws a visible line rather than disappearing.
            const h = Math.max(bottom - top, 0.35);
            const x = mid(i);
            return (
              <g key={c.date} className="candleChart__candle" data-dir={up ? 'up' : 'down'}>
                {/* `<title>` is the browser's own hover text -- so every candle gives its
                    four prices with no JavaScript at all, and it works for keyboard and
                    screen-reader users too. */}
                <title>
                  {`${c.date}\nOpen  ${c.open.toFixed(2)}\nHigh  ${c.high.toFixed(2)}\nLow   ${c.low.toFixed(2)}\nClose ${c.close.toFixed(2)}`}
                  {c.volume ? `\nVolume ${inrCompact(c.volume)}` : ''}
                  {c.turnover ? `\nTurnover Rs ${inrCompact(c.turnover)}` : ''}
                </title>
                {/* The wick: low to high. */}
                <line className="candleChart__wick" x1={x} x2={x}
                      y1={y(c.high).toFixed(2)} y2={y(c.low).toFixed(2)}
                      vectorEffect="non-scaling-stroke" />
                {/* The body: open to close. */}
                <rect className="candleChart__body" x={(x - bodyW / 2).toFixed(3)}
                      y={top.toFixed(2)} width={bodyW.toFixed(3)} height={h.toFixed(2)} />
              </g>
            );
          })}
        </svg>
        {/* Three price labels, so values can be read against the grid lines. */}
        <span className="candleChart__high">{high.toFixed(2)}</span>
        <span className="candleChart__mid">{((high + low) / 2).toFixed(2)}</span>
        <span className="candleChart__low">{low.toFixed(2)}</span>
      </div>
      <figcaption className="candleChart__axis">
        <span>{first.date}</span>
        <span className="candleChart__legend">
          {/* THE LEGEND STATES WHAT THE COLOURS MEAN, precisely: "close ≥ open" rather than
              "up". No assumption that the reader already knows the convention -- and note
              the ≥, which resolves what a flat day counts as. */}
          <i data-dir="up" /> close ≥ open
          <i data-dir="down" /> close &lt; open
          {/* AND THE DROPPED SESSIONS REPORTED, so the gaps are explained rather than
              being a silent absence a reader would never think to ask about. */}
          {droppedSessions > 0 ? ` · ${droppedSessions} session(s) without complete OHLC not drawn` : ''}
        </span>
        <span>{last.date}</span>
      </figcaption>
    </figure>
  );
}

// A simpler line chart, for where candles are more than is needed.
export function PriceChart({
  points,
  height = 200,
}: {
  points: { date: string; close: number }[];
  height?: number;
}) {
  if (points.length < 2) {
    return <p className="small muted">Not enough sessions to draw a chart.</p>;
  }
  const values = points.map((p) => p.close);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const step = 100 / (values.length - 1);
  const line = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(
      100 - ((v - low) / span) * 100
    ).toFixed(2)}`)
    .join(' ');
  // The shaded area: the line, then down to the bottom, across, and closed.
  const area = `${line} L100,100 L0,100 Z`;
  const rising = values[values.length - 1] >= values[0];

  return (
    <figure className="priceChart" data-dir={rising ? 'up' : 'down'}>
      <div className="priceChart__plot" style={{ height }}>
        {/* Hidden from screen readers because the dates and values are printed beneath. */}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path className="priceChart__area" d={area} />
          <path className="priceChart__line" d={line} vectorEffect="non-scaling-stroke" />
        </svg>
        <span className="priceChart__high">{high.toFixed(2)}</span>
        <span className="priceChart__low">{low.toFixed(2)}</span>
      </div>
      <figcaption className="priceChart__axis">
        <span>{points[0].date}</span>
        <span>{points[points.length - 1].date}</span>
      </figcaption>
    </figure>
  );
}

/**
 * Where a block of numbers came from and how current it is.
 *
 * Small, quiet, and always present. The product's whole claim to be trustworthy rests on
 * a reader being able to find this without going looking for it, and on it distinguishing
 * a live read from a stored one every single time.
 */
// PLAIN ENGLISH: the smallest component in the file, and the one carrying the most weight.
// "Small, quiet, and always present" -- it should never dominate a page, and it should never
// be absent from one. The trustworthiness of the whole product rests on a reader being able
// to find where a number came from WITHOUT going looking for it.
export function SourceLine({ of }: { of: Sourced<unknown> }) {
  return (
    <p className="sourceLine" data-source={of.source}>
      {sourceNote(of)}
    </p>
  );
}

/** The one primary action on a card: go deeper, in the product's own words. */
// "The ONE primary action" -- singular by design. A card with four links has no primary
// action, and a reader has to decide which one they want before they know what any of them
// contain.
export function Deeper({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link className="deeper" href={href}>
      {children} <span aria-hidden="true">→</span>
    </Link>
  );
}

// The empty state, with a title and an explanation. Never a blank space.
export function Empty({ title, note }: { title: string; note: string }) {
  return (
    <div className="productEmpty">
      <h3>{title}</h3>
      <p>{note}</p>
    </div>
  );
}
