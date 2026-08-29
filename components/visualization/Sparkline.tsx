/**
 * Server-rendered inline SVG charts.
 *
 * No charting library and no client JavaScript: these render on the server, ship as
 * markup, and cost nothing at request time. That matters because the product surface must
 * stay inside a Vercel request budget while the research pipeline does the heavy work
 * elsewhere.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * CHARTS, DRAWN BY HAND, WITH NO CHARTING LIBRARY AT ALL.
 *
 * Every chart here is built from raw SVG -- lines, rectangles and text -- computed on the
 * server and sent as finished markup.
 *
 * WHY NOT USE A CHARTING LIBRARY? Three reasons, and only the third is about money:
 *   1. A library is a large download for every visitor, before a single chart appears.
 *   2. It runs in the browser, so charts appear only after the JavaScript loads -- and not
 *      at all for anybody who has it switched off, or for a printer, or a search engine.
 *   3. Doing it on the server costs nothing per request, which keeps the site inside its
 *      hosting budget while the heavy research runs elsewhere.
 *
 * SVG means "Scalable Vector Graphics": a picture described as instructions -- "draw a line
 * from here to here" -- rather than as a grid of pixels. So it stays perfectly sharp at any
 * size, and it is just text, which is why it can be sent as part of the page.
 */

// A shaded region of the chart, marking a period of interest.
export interface Band {
  from: string;
  // `null` means "to the end" -- for a period that had not finished when the data did.
  to: string | null;
  label?: string;
  color?: string;
}

// A vertical line marking one moment.
export interface Marker {
  at: string;
  label?: string;
  color?: string;
  dash?: string;
}

interface TraceProps {
  dates: string[];
  // Values may be null -- and the drawing below leaves a GAP rather than joining across
  // them, which is the whole reason the type allows null.
  values: (number | null)[];
  /** Optional half-width band drawn around the value, e.g. uncertainty. */
  // THE UNCERTAINTY, DRAWN. A shaded ribbon around the line showing how sure we are.
  spread?: (number | null)[];
  bands?: Band[];
  markers?: Marker[];
  height?: number;
  yMin?: number;
  yMax?: number;
  color?: string;
  label?: string;
  /** Horizontal reference lines, e.g. entry and exit thresholds. */
  hlines?: { at: number; label?: string }[];
}

// The drawing area. A fixed internal width with the picture scaled to fit its container --
// so the maths below is simple and the result still fills any screen.
const W = 720;
// Room for the axis labels. More on the left, because the numbers go there.
const PAD = { top: 10, right: 8, bottom: 22, left: 34 };

export function Trace({
  dates,
  values,
  spread,
  bands = [],
  markers = [],
  height = 170,
  yMin = 0,
  yMax = 1,
  color = 'var(--accent)',
  label,
  hlines = [],
}: TraceProps) {
  const n = dates.length;
  // Fewer than two points is not a line. Say so rather than drawing a dot and calling it a
  // chart.
  if (n < 2) {
    return <p className="muted">Not enough observations to draw a trace.</p>;
  }
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;

  // Turn a position in the list into an across-the-page coordinate.
  const x = (i: number) => PAD.left + (i / (n - 1)) * innerW;
  // And a value into an up-the-page one. Note `innerH -` : SVG counts downwards from the
  // top, so this flips it so that bigger values are higher, as a reader expects.
  // The `Math.max(1e-9, ...)` prevents a divide by zero when every value is identical.
  const y = (v: number) =>
    PAD.top + innerH - ((v - yMin) / Math.max(1e-9, yMax - yMin)) * innerH;

  // Find where a date sits in the list.
  const indexOf = (d: string) => {
    const i = dates.indexOf(d);
    if (i >= 0) return i;
    // Nearest preceding date, so a marker on a non-trading day still lands sensibly.
    // PLAIN ENGLISH: an event on a Sunday has no trading day of its own. Rather than
    // silently dropping the marker, it is placed on the last trading day before it -- which
    // is where a reader would expect to see it.
    let best = -1;
    for (let k = 0; k < n; k += 1) if (dates[k] <= d) best = k;
    return best;
  };

  // BUILD THE LINE. An SVG path is a string of instructions: M means "move here without
  // drawing", L means "draw a line to here".
  const path = values
    // First turn each value into a coordinate, or null where there is no value.
    .map((v, i) => (v === null || Number.isNaN(v) ? null : `${x(i)},${y(v)}`))
    .reduce<string[]>((acc, pt, i) => {
      // Skip the gaps entirely.
      if (pt === null) return acc;
      // AND HERE IS THE IMPORTANT BIT: use M (move, no line) rather than L (draw a line)
      // whenever this is the first point OR the previous value was missing.
      // So a gap in the data becomes a GAP IN THE LINE, rather than a straight segment
      // drawn confidently across a period where we knew nothing.
      acc.push(`${acc.length === 0 || values[i - 1] === null ? 'M' : 'L'}${pt}`);
      return acc;
    }, [])
    .join(' ');

  // BUILD THE UNCERTAINTY RIBBON.
  let bandPath = '';
  if (spread) {
    const upper: string[] = [];
    const lower: string[] = [];
    values.forEach((v, i) => {
      const s = spread[i];
      if (v === null || s === null || s === undefined) return;
      // The top edge, clamped so a wide interval cannot run off the chart.
      upper.push(`${x(i)},${y(Math.min(yMax, v + s / 2))}`);
      // The bottom edge, built BACKWARDS (`unshift` adds to the front) -- because a filled
      // shape must be traced along the top and back along the bottom to close properly.
      lower.unshift(`${x(i)},${y(Math.max(yMin, v - s / 2))}`);
    });
    // `Z` closes the shape so it can be filled.
    if (upper.length > 1) bandPath = `M${upper.join(' L')} L${lower.join(' L')} Z`;
  }

  // Three gridlines: bottom, middle, top. Enough to read values against, few enough not to
  // clutter a small chart.
  const ticks = [yMin, (yMin + yMax) / 2, yMax];

  return (
    <figure style={{ margin: '8px 0 0' }}>
      <svg
        // `viewBox` with `width="100%"` is what makes it scale to any screen while the
        // internal coordinates stay simple.
        viewBox={`0 0 ${W} ${height}`}
        width="100%"
        height={height}
        // Announced to screen-reader software as an image with a description -- so a
        // listening reader is told what the chart shows rather than meeting silence.
        role="img"
        aria-label={label ?? 'time series'}
        style={{ overflow: 'visible' }}
      >
        {/* SHADED PERIODS FIRST, so everything else draws on top of them. Order matters in
            SVG: later things cover earlier ones. */}
        {bands.map((b, i) => {
          const i0 = indexOf(b.from);
          const i1 = b.to ? indexOf(b.to) : n - 1;
          if (i0 < 0) return null;
          return (
            <rect
              key={`band-${i}`}
              x={x(i0)}
              y={PAD.top}
              // `Math.max(1, ...)` guarantees at least one pixel, so a single-day period is
              // still visible rather than vanishing.
              width={Math.max(1, x(Math.max(i1, i0)) - x(i0))}
              height={innerH}
              fill={b.color ?? '#d55e00'}
              // Very faint, so it tints the background without competing with the line.
              opacity={0.13}
            />
          );
        })}

        {/* THE GRIDLINES AND THEIR LABELS. */}
        {ticks.map((t) => (
          <g key={`t-${t}`}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--border)"
              // Very thin, so they guide the eye without drawing it.
              strokeWidth={0.6}
            />
            <text x={PAD.left - 5} y={y(t) + 3} textAnchor="end" fontSize={9}
                  fill="var(--muted)">
              {t.toFixed(1)}
            </text>
          </g>
        ))}

        {/* REFERENCE LINES -- the alarm thresholds. Dashed, so they are visibly a rule
            rather than another data series. */}
        {hlines.map((h) => (
          <g key={`h-${h.at}`}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(h.at)}
              y2={y(h.at)}
              stroke="var(--muted)"
              strokeWidth={0.7}
              strokeDasharray="3 3"
            />
            {h.label ? (
              <text x={W - PAD.right} y={y(h.at) - 3} textAnchor="end" fontSize={8.5}
                    fill="var(--muted)">
                {h.label}
              </text>
            ) : null}
          </g>
        ))}

        {/* THE UNCERTAINTY RIBBON, drawn UNDER the line -- so the value stays clearly
            readable and the uncertainty surrounds it rather than obscuring it. */}
        {bandPath ? <path d={bandPath} fill={color} opacity={0.16} /> : null}
        {/* AND THE LINE ITSELF, on top. `fill="none"` because a line is a stroke, not a
            shape -- without it SVG would fill the area underneath. */}
        <path d={path} fill="none" stroke={color} strokeWidth={1.6} />

        {/* EVENT MARKERS: vertical dashed lines at particular moments. */}
        {markers.map((m, i) => {
          const idx = indexOf(m.at);
          if (idx < 0) return null;
          return (
            <g key={`m-${i}`}>
              <line
                x1={x(idx)}
                x2={x(idx)}
                y1={PAD.top}
                y2={PAD.top + innerH}
                stroke={m.color ?? '#009e73'}
                strokeWidth={1.1}
                strokeDasharray={m.dash ?? '4 2'}
              />
              {m.label ? (
                // The label sits just to the right of its line and in the same colour, so
                // several markers stay individually identifiable.
                <text x={x(idx) + 3} y={PAD.top + 9} fontSize={8.5}
                      fill={m.color ?? '#009e73'}>
                  {m.label}
                </text>
              ) : null}
            </g>
          );
        })}

        {/* THE FIRST AND LAST DATES. Just two -- enough to bound the period, and far less
            cluttered than a full date axis on a small chart. */}
        <text x={PAD.left} y={height - 6} fontSize={9} fill="var(--muted)">
          {dates[0]}
        </text>
        <text x={W - PAD.right} y={height - 6} fontSize={9} fill="var(--muted)"
              textAnchor="end">
          {dates[n - 1]}
        </text>
      </svg>
      {label ? (
        // `<figcaption>` is the proper element for a caption, so the description is
        // formally tied to the picture rather than being loose text beneath it.
        <figcaption className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          {label}
        </figcaption>
      ) : null}
    </figure>
  );
}

/** Horizontal bars for a small labelled series, e.g. feature-block contribution. */
export function Bars({
  items,
  label,
  color = 'var(--accent)',
  negativeColor = 'var(--warn)',
}: {
  items: { name: string; value: number | null }[];
  label?: string;
  color?: string;
  negativeColor?: string;
}) {
  // Keep only the real values. The `as` afterwards tells the type checker that what
  // survives definitely has a number, which the filter has just guaranteed.
  const present = items.filter(
    (i) => i.value !== null && i.value !== undefined && !Number.isNaN(i.value),
  ) as { name: string; value: number }[];
  // Nothing to draw: say so, rather than an empty frame that would read as "all zero".
  if (present.length === 0) return <p className="muted">No values to plot.</p>;

  // The largest bar sets the scale. The tiny floor prevents a divide by zero when every
  // value is nought.
  const max = Math.max(...present.map((i) => Math.abs(i.value)), 1e-9);
  const rowH = 18;
  const height = present.length * rowH + 8;
  const labelW = 118;
  // WHERE ZERO SITS. If anything is negative, zero moves to the middle so bars can extend
  // both ways. If everything is positive, zero stays at the left and the full width is
  // available -- so a chart with no negatives is not squeezed into half the space for
  // nothing.
  const zero = present.some((i) => i.value < 0) ? labelW + (W - labelW) / 2 : labelW;
  const scale = (v: number) => (Math.abs(v) / max) * (W - zero - 12);

  return (
    <figure style={{ margin: '8px 0 0' }}>
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img"
           aria-label={label ?? 'bar chart'}>
        {present.map((it, i) => {
          const w = scale(it.value);
          const neg = it.value < 0;
          return (
            // `translate` moves each row down by its position, so the drawing inside can be
            // written as though every row were at the top.
            <g key={it.name} transform={`translate(0,${i * rowH + 4})`}>
              {/* The name, right-aligned against the bars so they all start level. */}
              <text x={labelW - 6} y={rowH * 0.62} textAnchor="end" fontSize={10}
                    fill="var(--text)">
                {it.name}
              </text>
              <rect
                // Negative bars start to the LEFT of zero and extend leftwards.
                x={neg ? zero - w : zero}
                y={3}
                // At least one pixel, so a very small value is still visible rather than
                // disappearing entirely -- which would read as "no value at all".
                width={Math.max(1, w)}
                height={rowH - 8}
                // A different colour for negative, so direction is visible before the
                // number is read.
                fill={neg ? negativeColor : color}
                opacity={0.82}
              />
              {/* THE ACTUAL NUMBER, printed at the end of each bar. So the chart is never
                  only an impression -- the value is always readable, and a reader never has
                  to estimate a length against an axis. */}
              <text x={(neg ? zero - w : zero + w) + (neg ? -4 : 4)} y={rowH * 0.62}
                    textAnchor={neg ? 'end' : 'start'} fontSize={9}
                    fill="var(--muted)">
                {it.value.toFixed(3)}
              </text>
            </g>
          );
        })}
        {/* The zero line, drawn last so it sits on top of the bars and stays visible. */}
        <line x1={zero} x2={zero} y1={0} y2={height} stroke="var(--border)"
              strokeWidth={0.8} />
      </svg>
      {label ? (
        <figcaption className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          {label}
        </figcaption>
      ) : null}
    </figure>
  );
}
