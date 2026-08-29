// Runs in the browser: it follows the mouse pointer.
'use client';

/**
 * The charting workspace for one security: candles, volume, RSI and MACD under a shared
 * crosshair.
 *
 * **One hover index drives every panel.** The pointer position is converted to a session
 * index once, and all four panels draw their guide at that same index. This is what makes
 * the panels readable together: the RSI value under the cursor is the RSI *of the candle
 * under the cursor*, and a reader can see that rather than having to trust it.
 *
 * **The tooltip shows stored values, never interpolated ones.** The index is snapped to a
 * real session, so every figure in the tooltip is a number that exists in the payload. A
 * session with no indicator yet — the RSI warm-up — reports that it has none rather than
 * borrowing the neighbouring value.
 *
 * **Timeframes offered are only those the data supports.** The window arrives from the
 * backend already bounded; the buttons slice that window and a range longer than what was
 * fetched is not offered, because a button that silently returns the same 120 sessions
 * under four different labels is lying about the range.
 *
 * Nothing here is an instruction. The panels are labelled as evidence, the RSI reference
 * lines are labelled as reference levels, and there is no control that proposes an action.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE FOUR-PANEL PRICE CHART, WITH A SHARED CROSSHAIR.
 *
 * FOUR DECISIONS, and each one prevents a specific way of misleading a reader.
 *
 * 1. ONE POSITION DRIVES ALL FOUR PANELS.
 *    Move the pointer and every panel draws its line at the SAME day. So the RSI you are
 *    reading is genuinely the RSI of the candle you are pointing at -- and you can SEE that
 *    the lines align, rather than having to take it on trust. Four panels each tracking the
 *    pointer separately would drift by a pixel and quietly pair up the wrong days.
 *
 * 2. THE TOOLTIP SHOWS STORED NUMBERS, NEVER INVENTED ONES.
 *    The pointer snaps to a real trading day, so every figure shown exists in the data.
 *    And where an indicator has no value yet -- the first days, before it has enough
 *    history -- it says "no value yet" rather than borrowing yesterday's. A borrowed value
 *    looks exactly like a real one.
 *
 * 3. ONLY OFFER TIMEFRAMES THE DATA CAN SUPPORT.
 *    If only 120 days were fetched, there is no "1 year" button. The reasoning is blunt and
 *    right: a button that returns the same 120 days under four different labels "is lying
 *    about the range". The reader would believe they had seen a year.
 *
 * 4. NOTHING HERE PROPOSES AN ACTION.
 *    The panels are labelled "evidence". The RSI lines are labelled "reference levels" --
 *    not "overbought" and "oversold", which are the conventional names and which read as
 *    instructions. There is no buy line, no signal, no alert.
 */
import { useCallback, useMemo, useRef, useState } from 'react';

import type { IndicatorSeries } from '@/lib/product';

import type { Candle } from './Bits';

// The timeframes, in trading days. 21 is about a month, 252 about a year.
const RANGES = [
  { key: '1M', sessions: 21 },
  { key: '3M', sessions: 63 },
  { key: '6M', sessions: 126 },
  { key: '1Y', sessions: 252 },
  // Infinity meaning "everything we have".
  { key: 'MAX', sessions: Number.POSITIVE_INFINITY },
] as const;

type RangeKey = (typeof RANGES)[number]['key'];

// Money, Indian-style.
const inr = (n: number) =>
  `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Volumes at readable scale: crore, lakh, or thousands.
const vol = (n: number) =>
  n >= 1e7 ? `${(n / 1e7).toFixed(2)}Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(2)}L` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`;

// A readable date.
const pretty = (iso: string) => {
  // `T00:00:00Z` forces it to be read as UTC. Without that, a date near midnight could shift
  // by a day depending on where the reader is -- and the chart would label the wrong day.
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    // An unreadable date shows as it was stored, rather than as "Invalid Date".
    ? iso
    : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(d);
};

// Build a line, leaving gaps where there is no value.
function path(values: (number | null)[], lo: number, hi: number, slot: number) {
  const span = hi - lo || 1;
  const out: string[] = [];
  let open = false;
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      // A missing value BREAKS the line. The next real value starts a new segment rather
      // than being joined across the gap -- so the chart never draws a confident line
      // through a period where nothing was known.
      open = false;
      return;
    }
    const x = i * slot + slot / 2;
    const y = 100 - ((v - lo) / span) * 100;
    // `M` starts a new segment, `L` continues one.
    out.push(`${open ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`);
    open = true;
  });
  return out.join(' ');
}

export function TerminalChart({
  candles,
  indicators,
}: {
  candles: Candle[];
  indicators?: IndicatorSeries;
}) {
  const [range, setRange] = useState<RangeKey>('MAX');
  // THE ONE POSITION that drives all four panels -- decision 1, in a single variable.
  const [hover, setHover] = useState<number | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const wrap = useRef<HTMLDivElement | null>(null);

  const total = candles.length;
  // DECISION 3: only offer timeframes the data actually covers. MAX is always offered,
  // because "everything" is always a truthful label.
  const available = useMemo(
    () => RANGES.filter((r) => r.sessions <= total || r.key === 'MAX'),
    [total],
  );

  // Slice the data to the chosen timeframe.
  const view = useMemo(() => {
    const spec = RANGES.find((r) => r.key === range) ?? RANGES[RANGES.length - 1];
    const n = Math.min(spec.sessions === Number.POSITIVE_INFINITY ? total : spec.sessions, total);
    // Take from the END, so a timeframe always means the most recent period.
    const start = total - n;
    // The indicators are used only if they line up exactly with the candles. A length
    // mismatch means they cannot be trusted to pair correctly, so they are dropped entirely
    // rather than drawn a day out -- which would be invisible and wrong.
    const ind = indicators && indicators.dates.length === total ? indicators : undefined;
    return {
      candles: candles.slice(start),
      rsi: ind ? ind.rsi.slice(start) : null,
      macd: ind ? ind.macd.slice(start) : null,
      signal: ind ? ind.macd_signal.slice(start) : null,
      hist: ind ? ind.macd_histogram.slice(start) : null,
      refs: ind?.rsi_reference_levels ?? [30, 70],
    };
  }, [candles, indicators, range, total]);

  const n = view.candles.length;
  // How wide each day's slot is, as a percentage of the chart.
  const slot = 100 / Math.max(n, 1);

  // The price range, with a little padding so candles do not touch the edges.
  const price = useMemo(() => {
    const lows = view.candles.map((c) => c.low);
    const highs = view.candles.map((c) => c.high);
    const lo = Math.min(...lows);
    const hi = Math.max(...highs);
    // 5% breathing room. `|| 1` handles a completely flat price, where the range is zero.
    const pad = (hi - lo || 1) * 0.05;
    return { lo: lo - pad, hi: hi + pad };
  }, [view.candles]);

  const maxVol = useMemo(
    () => Math.max(...view.candles.map((c) => (typeof c.volume === 'number' ? c.volume : 0)), 1),
    [view.candles],
  );

  // The MACD range, across all three of its series so they share one scale.
  const macdBounds = useMemo(() => {
    const all = [...(view.macd ?? []), ...(view.signal ?? []), ...(view.hist ?? [])].filter(
      (v): v is number => typeof v === 'number' && Number.isFinite(v),
    );
    // Null when there is nothing -- and the panel below shows "unavailable" rather than an
    // empty axis.
    if (!all.length) return null;
    return { lo: Math.min(...all), hi: Math.max(...all) };
  }, [view.macd, view.signal, view.hist]);

  // Turn a pointer position into a day.
  const onMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = wrap.current;
      if (!el || n === 0) return;
      const r = el.getBoundingClientRect();
      // How far across, as a fraction.
      const frac = (e.clientX - r.left) / r.width;
      // SNAPPED TO A REAL DAY -- decision 2. `Math.floor` picks a whole day, and the min and
      // max keep it inside the chart even if the pointer strays past the edge.
      const idx = Math.min(n - 1, Math.max(0, Math.floor(frac * n)));
      setHover(idx);
      setCursor({ x: e.clientX - r.left, y: e.clientY - r.top });
    },
    [n],
  );

  const leave = useCallback(() => setHover(null), []);

  // Fewer than two days is not a chart. Say so, naming the actual requirement (complete
  // OHLC), so a reader knows what is missing.
  if (n < 2) {
    return <p className="small muted">Not enough sessions with complete OHLC to draw the workspace.</p>;
  }

  const c = hover !== null ? view.candles[hover] : null;
  // THE SHARED CROSSHAIR POSITION, computed once.
  const guideX = hover !== null ? hover * slot + slot / 2 : null;
  const yPrice = (v: number) => ((price.hi - v) / (price.hi - price.lo || 1)) * 100;

  // The vertical guide line, defined once and drawn in every panel -- which is what
  // guarantees all four line up exactly.
  const Guide = () =>
    guideX === null ? null : (
      // `vectorEffect="non-scaling-stroke"` keeps the line one pixel wide however the chart
      // is stretched. Without it, the squashed coordinate system would make it a fat blur.
      <line className="term__guide" x1={guideX} x2={guideX} y1="0" y2="100" vectorEffect="non-scaling-stroke" />
    );

  return (
    <div className="term">
      <div className="term__toolbar">
        <div className="term__ranges" role="group" aria-label="Timeframe">
          {/* Only the timeframes the data supports -- decision 3. */}
          {available.map((r) => (
            <button
              key={r.key}
              type="button"
              className="term__range"
              data-active={range === r.key}
              onClick={() => setRange(r.key)}
            >
              {r.key}
            </button>
          ))}
        </div>
        {/* THE ACTUAL PERIOD SHOWN, in sessions and dates. So the label on the button is
            never the only claim about the range -- the real span is printed beside it. */}
        <span className="term__span">
          {n} sessions · {view.candles[0].date} → {view.candles[n - 1].date}
        </span>
      </div>

      {/* All four panels share one pointer handler on their common wrapper -- which is how
          one position can drive all of them. */}
      <div className="term__panels" ref={wrap} onPointerMove={onMove} onPointerLeave={leave}>
        {/* ---------------------------------------------------------- price */}
        <div className="term__panel term__panel--price">
          {/* Three price labels: top, middle, bottom. Enough to read against. */}
          <div className="term__axisLabel">
            <span>{price.hi.toFixed(2)}</span>
            <span>{((price.hi + price.lo) / 2).toFixed(2)}</span>
            <span>{price.lo.toFixed(2)}</span>
          </div>
          {/* `preserveAspectRatio="none"` lets the chart stretch to fill its container --
              right for a chart, where the shape is set by the container rather than the data. */}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Candlestick price chart">
            {view.candles.map((cd, i) => {
              const up = cd.close >= cd.open;
              const top = yPrice(Math.max(cd.open, cd.close));
              const bottom = yPrice(Math.min(cd.open, cd.close));
              const x = i * slot + slot / 2;
              const w = Math.max(slot * 0.6, 0.08);
              return (
                <g key={cd.date} data-dir={up ? 'up' : 'down'} className="term__candle">
                  {/* The wick: the full high-to-low range. */}
                  <line className="term__wick" x1={x} x2={x} y1={yPrice(cd.high)} y2={yPrice(cd.low)} vectorEffect="non-scaling-stroke" />
                  {/* The body: open to close. `Math.max(..., 0.3)` guarantees a visible line
                      even on a day that opened and closed at the same price -- which would
                      otherwise vanish entirely and look like missing data. */}
                  <rect className="term__body" x={x - w / 2} y={top} width={w} height={Math.max(bottom - top, 0.3)} />
                </g>
              );
            })}
            <Guide />
          </svg>
        </div>

        {/* --------------------------------------------------------- volume */}
        <div className="term__panel term__panel--vol">
          <span className="term__panelTag">Volume</span>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Volume">
            {view.candles.map((cd, i) => {
              const v = typeof cd.volume === 'number' ? cd.volume : 0;
              const h = (v / maxVol) * 100;
              const w = Math.max(slot * 0.6, 0.08);
              return (
                <rect
                  key={cd.date}
                  className="term__volBar"
                  // Coloured to match its candle, so heavy trading on a down day is
                  // immediately distinguishable from heavy trading on an up day.
                  data-dir={cd.close >= cd.open ? 'up' : 'down'}
                  x={i * slot + slot / 2 - w / 2}
                  y={100 - h}
                  width={w}
                  height={Math.max(h, 0.3)}
                />
              );
            })}
            <Guide />
          </svg>
        </div>

        {/* ------------------------------------------------------------ RSI */}
        <div className="term__panel term__panel--rsi">
          {/* LABELLED "momentum EVIDENCE" -- decision 4. Not "signal", not "indicator to
              trade on". */}
          <span className="term__panelTag">RSI · momentum evidence</span>
          {view.rsi ? (
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Relative strength index">
              {view.refs.map((r) => (
                <line key={r} className="term__ref" x1="0" x2="100" y1={100 - r} y2={100 - r} vectorEffect="non-scaling-stroke" />
              ))}
              {/* Fixed 0-100 scale, because that is RSI's own range -- so the same level
                  always sits at the same height across every company. */}
              <path className="term__line" d={path(view.rsi, 0, 100, slot)} vectorEffect="non-scaling-stroke" />
              <Guide />
            </svg>
          ) : (
            <p className="small muted term__none">RSI unavailable for this window.</p>
          )}
          {view.rsi ? (
            <>
              {/* THE WORD "REFERENCE", NOT "OVERBOUGHT" OR "OVERSOLD". The conventional names
                  are effectively instructions -- "overbought" means "sell" to most readers.
                  "Reference" describes a level and proposes nothing. Decision 4 again, in a
                  single word. */}
              <span className="term__refTag" style={{ top: `${100 - view.refs[1]}%` }}>{view.refs[1]} reference</span>
              <span className="term__refTag" style={{ top: `${100 - view.refs[0]}%` }}>{view.refs[0]} reference</span>
            </>
          ) : null}
        </div>

        {/* ----------------------------------------------------------- MACD */}
        <div className="term__panel term__panel--macd">
          <span className="term__panelTag">MACD · trend and momentum evidence</span>
          {macdBounds && view.macd && view.signal && view.hist ? (
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="MACD">
              {/* An inline function, so the scale can be computed once and used by everything
                  inside rather than being recalculated per bar. */}
              {(() => {
                const { lo, hi } = macdBounds;
                const span = hi - lo || 1;
                // Where zero falls -- which for MACD is the meaningful line, since crossing
                // it is the whole point of the indicator.
                const zero = 100 - ((0 - lo) / span) * 100;
                const w = Math.max(slot * 0.5, 0.06);
                return (
                  <>
                    <line className="term__zero" x1="0" x2="100" y1={zero} y2={zero} vectorEffect="non-scaling-stroke" />
                    {view.hist!.map((v, i) =>
                      // Missing values draw nothing at all rather than a zero-height bar,
                      // which would sit on the line and read as a real value of zero.
                      v === null || !Number.isFinite(v) ? null : (
                        <rect
                          key={i}
                          className="term__histBar"
                          data-dir={v >= 0 ? 'up' : 'down'}
                          x={i * slot + slot / 2 - w / 2}
                          // Bars grow from the zero line in both directions, so `Math.min`
                          // picks whichever end is uppermost.
                          y={Math.min(100 - ((v - lo) / span) * 100, zero)}
                          width={w}
                          height={Math.max(Math.abs(zero - (100 - ((v - lo) / span) * 100)), 0.2)}
                        />
                      ),
                    )}
                    {/* The two lines, sharing one scale so their crossings are meaningful. */}
                    <path className="term__line" d={path(view.macd!, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
                    <path className="term__line term__line--signal" d={path(view.signal!, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
                    <Guide />
                  </>
                );
              })()}
            </svg>
          ) : (
            <p className="small muted term__none">MACD unavailable for this window.</p>
          )}
        </div>

        {/* -------------------------------------------------------- tooltip */}
        {c ? (
          <div
            className="term__tip"
            style={{
              // Kept on screen: at least 8 pixels from the left edge, at most 640 from it,
              // so the tooltip never runs off the side and becomes unreadable.
              left: `${Math.min(Math.max(cursor.x + 14, 8), 640)}px`,
              top: `${Math.max(cursor.y - 10, 8)}px`,
            }}
            // `role="status"` so assistive software announces the values as the pointer
            // moves, rather than a listener getting nothing from a purely visual tooltip.
            role="status"
          >
            <div className="term__tipDate">{pretty(c.date)}</div>
            <dl className="term__tipGrid">
              {/* Open, high, low, close -- the four stored prices, all real. */}
              <div><dt>O</dt><dd>{inr(c.open)}</dd></div>
              <div><dt>H</dt><dd>{inr(c.high)}</dd></div>
              <div><dt>L</dt><dd>{inr(c.low)}</dd></div>
              {/* The close coloured by direction, since it is the one people look at. */}
              <div><dt>C</dt><dd className={c.close >= c.open ? 'up' : 'down'}>{inr(c.close)}</dd></div>
              {/* Volume and turnover only where they exist -- no invented zeros. */}
              {typeof c.volume === 'number' ? (
                <div><dt>Vol</dt><dd>{vol(c.volume)}</dd></div>
              ) : null}
              {typeof c.turnover === 'number' ? (
                <div><dt>Value</dt><dd>{`₹${vol(c.turnover)}`}</dd></div>
              ) : null}
            </dl>
            {view.rsi ? (
              <div className="term__tipRow">
                <span>RSI</span>
                {/* DECISION 2, VISIBLE: "no value yet" during the warm-up. Not a borrowed
                    number, not a blank -- an explicit statement that this day has none. */}
                <span>{view.rsi[hover!] === null ? 'no value yet' : view.rsi[hover!]!.toFixed(2)}</span>
              </div>
            ) : null}
            {view.macd ? (
              <div className="term__tipRow">
                <span>MACD</span>
                <span>
                  {view.macd[hover!] === null
                    ? 'no value yet'
                    // All three MACD numbers together, since they are only meaningful in
                    // relation to one another.
                    : `${view.macd[hover!]!.toFixed(2)} · sig ${view.signal![hover!]?.toFixed(2) ?? '—'} · hist ${view.hist![hover!]?.toFixed(2) ?? '—'}`}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <p className="term__foot">
        {/* THE CLOSING NOTE, and it does three things in three sentences:
            1. Says these indicators are OURS, derived from the prices -- the exchange
               publishes neither.
            2. Says what they are: evidence about observed behaviour.
            3. Says what they are NOT: "neither proposes an action."
            Then it tells the reader they can hover to read the stored values -- so the
            interaction is discoverable rather than something you have to guess at. */}
        RSI and MACD are derived from the closing prices shown above; the exchange publishes
        neither. Both are evidence about observed price behaviour and neither proposes an
        action. Hover any session to read its stored values.
      </p>
    </div>
  );
}
