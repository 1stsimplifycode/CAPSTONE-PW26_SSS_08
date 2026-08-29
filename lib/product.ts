/**
 * The product's data layer: backend first, stored snapshot second, and it says which.
 *
 * Two sources, one shape. `backend/product.py` builds these read models from the panels
 * directly; `scripts/export_product.py` writes the same models to `public/data/market.json`
 * at export time. A page asks this module and gets whichever is available, together with
 * a `source` that says what it got — because "the market" from a live service and "the
 * market" from a snapshot taken last Tuesday are different claims, and only one of them
 * is entitled to the present tense.
 *
 * Nothing here computes a market number. If a value is on the screen, a panel produced it.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * WHERE THE MARKET PAGES GET THEIR NUMBERS, AND HOW THEY SAY SO.
 *
 * There are two possible sources:
 *   LIVE     -- ask the analysis service running right now.
 *   SNAPSHOT -- read a file saved earlier.
 * Try the live one; fall back to the file. Perfectly ordinary.
 *
 * WHAT IS NOT ORDINARY is the sentence that follows, and it is the heart of this file:
 *
 *     "'the market' from a live service and 'the market' from a snapshot taken last
 *      Tuesday are different claims, and only one of them is entitled to the present
 *      tense."
 *
 * Most systems fall back silently. The page looks identical either way, and a visitor
 * reading "the market is calm" has no idea whether that means TODAY or LAST TUESDAY.
 * Those are completely different statements. One is a report; the other is history
 * wearing the present tense.
 * So EVERY answer here carries a `source` saying which it is -- and where it came from a
 * file, when that file was made. The page then says so, out loud.
 *
 * AND THE LAST LINE IS THE USUAL RULE: this file computes nothing. Every number on screen
 * was produced by the research pipeline. This layer only fetches and labels.
 */
// The shapes of two display blocks, imported so the data can be typed to match them.
import type { DirectionBlock } from '@/components/product/DirectionStrip';
import type { AnnouncementsBlock } from '@/components/product/EventFeed';

import { getBundle } from './data';

// How worrying something is, used to pick a colour.
export type Tone = 'calm' | 'watch' | 'elevated' | 'high';
// THE THREE HONEST ANSWERS to "where did this come from?".
export type ProductSource = 'live' | 'snapshot' | 'unavailable';

// One day's prices.
export interface PricePoint {
  date: string;
  close: number;
  /**
   * Real OHLC from the panel, optional only because an older exported bundle may predate
   * these fields. They are never synthesised from `close`: a candle needs a genuine open,
   * high and low or it is not drawn.
   */
  // PLAIN ENGLISH: OHLC means Open, High, Low, Close -- the four prices that make up one
  // bar on a candlestick chart. "Never synthesised from close" is the discipline: if we only
  // have the closing price, we do NOT invent an open and a high to make the chart look
  // complete. We draw no candle. A made-up candle is a picture of something that never
  // happened, and it would be indistinguishable from a real one.
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  turnover?: number | null;
}

// One day's risk score.
export interface RiskPoint {
  date: string;
  risk: number;
  // Always paired with the score. Never separable.
  uncertainty: number;
}

// How much one family of evidence contributed.
export interface BlockShare {
  block: string;
  label: string;
  contribution: number;
  weight: number | null;
  share: number;
}

// Everything about one company's market activity.
export interface MarketBlock {
  available: boolean;
  last_session: string;
  close: number;
  change: number | null;
  change_pct: number | null;
  window_change_pct: number | null;
  sessions: number;
  volume: number;
  turnover: number;
  history_from: string;
  source: string;
  series: PricePoint[];

  /**
   * Recency, kept deliberately separate from coverage.
   *
   * `coverage_from` is where the history begins; `latest_session` is when the most recent
   * observation happened. Conflating them lets a page imply it is current when it is not,
   * so `recency_label` switches to "Latest available market data" whenever the panel is
   * behind today, and `days_since_latest_session` says by how much.
   */
  // PLAIN ENGLISH: two different questions that are easy to confuse.
  //   COVERAGE -- how far back does the history go?
  //   RECENCY  -- how up to date is the most recent entry?
  // A page showing five years of data with the last entry three weeks old could easily
  // read as current. So when the data is behind, the label CHANGES -- to "latest available"
  // rather than anything implying today -- and the exact number of days behind is given.
  latest_session?: string;
  previous_session?: string | null;
  window_from?: string;
  window_to?: string;
  window_sessions?: number;
  coverage_from?: string;
  coverage_sessions?: number;
  checked_at?: string;
  // The two fields that make staleness impossible to miss.
  days_since_latest_session?: number;
  is_current_as_of_today?: boolean;
  recency_label?: string;
  recency_note?: string;
  ohlc_source?: string;
  // Whether real open/high/low were available, so a chart knows whether it may draw candles.
  ohlc_complete?: boolean;

  /** Indicators DERIVED from these closes. The exchange publishes none of them. */
  // A necessary clarification: RSI and MACD are OUR calculations from the prices, not
  // official figures the exchange publishes. Saying so prevents them being read as
  // authoritative market data.
  indicators?: IndicatorSeries;
  /** Which way the observed price moved, as a tally of independent readings. */
  direction?: DirectionBlock;
}

// The technical indicators.
export interface IndicatorSeries {
  indicators_version: string;
  // The exact conventions used, so a reader can reproduce them rather than guessing which
  // of several common variants was chosen.
  conventions: Record<string, unknown>;
  dates: string[];
  /** Aligned point-for-point with `dates`; leading entries are null, never back-filled. */
  // PLAIN ENGLISH: these indicators need a run-up of past days before they mean anything.
  // The first few entries are therefore null. "Never back-filled" means we do not quietly
  // fill them with the first computable value -- which would draw a flat line at the start
  // of the chart that looks like real, calm data and is entirely invented.
  rsi: (number | null)[];
  macd: (number | null)[];
  macd_signal: (number | null)[];
  macd_histogram: (number | null)[];
  rsi_latest: number | null;
  // A plain-English reading of what the indicator currently says.
  rsi_observation: string;
  rsi_reference_levels: number[];
  macd_latest: number | null;
  macd_signal_latest: number | null;
  macd_histogram_latest: number | null;
  macd_observation: string;
  available: boolean;
  // And when unavailable, the reason -- so a blank chart explains itself.
  why_unavailable: string | null;
}

// One company's risk assessment.
export interface RiskBlock {
  available: boolean;
  // The reason, whenever it is not available.
  why?: string;
  state?: string;
  state_label?: string;
  state_tone?: Tone;
  // What the stage MEANS, in words -- so a label never appears without its explanation.
  state_meaning?: string;
  score?: number;
  uncertainty?: number;
  coverage?: number | null;
  sessions_scored?: number;
  scored_from?: string;
  scored_to?: string;
  // The full working: each family's contribution, the day-by-day series, and where it came
  // from. So the headline number can be taken apart on screen.
  blocks?: BlockShare[];
  series?: RiskPoint[];
  provenance?: Record<string, unknown>;
}

/**
 * The Week 1 market-intelligence foundation for one instrument.
 *
 * Every field here is served from an artifact the C1-C7 test suite asserts against, so a
 * value rendered on the page is one the research layer stands behind. Anything the
 * exchange does not publish arrives as `available: false` with a `why`, and is rendered
 * as an explicit "not available" rather than omitted -- a blank field reads as "nothing
 * to report", which is a different claim.
 */
// PLAIN ENGLISH: the final sentence is the principle this whole project keeps returning to.
// Leave a field out and the reader concludes "there is nothing to report here".
// Show it marked "not available, because the exchange does not publish it" and the reader
// learns something true.
// Those are different claims, and only one of them is honest about what we do not know.
export interface SecurityStatus {
  available: boolean;
  why?: string;
  state?: string;
  state_label?: string;
  meaning?: string;
  // WHAT THIS IS BASED ON. Whether it is an exchange fact or our own observation.
  basis?: string;
  first_observed_session?: string;
  last_observed_session?: string;
  sessions_observed?: number;
  listing_date?: string | null;
  // And how we know the listing date -- since "the exchange says so" and "the first day we
  // have data for" are very different things wearing the same shape.
  listing_date_basis?: string;
  in_current_roster?: boolean;
  trade_for_trade_sessions?: number;
  delisted_on?: string | null;
  suspended_on?: string | null;
  date_note?: string;
}

// The daily price limits.
export interface PriceBand {
  available: boolean;
  why?: string;
  band?: string | null;
  band_label?: string;
  series?: string;
  surveillance_remark?: string | null;
  basis?: string;
  source?: string;
  // WHICH PERIOD this information covers. The distinction from availability again: a
  // current snapshot is genuinely obtained and useless for a question about 2015.
  temporal_coverage?: string;
}

// One share split, bonus or dividend.
export interface CorporateAction {
  ex_date: string;
  subject: string;
  action_type: string;
  price_factor: number | null;
  status: string;
  // BOTH the raw return and the adjusted one. Showing both lets a reader see the mechanical
  // jump the adjustment removed, rather than taking the correction on trust.
  raw_return: number | null;
  adjusted_return: number | null;
}

export interface CorporateActionContext {
  available: boolean;
  why?: string;
  count?: number;
  price_affecting?: number;
  actions?: CorporateAction[];
  basis?: string;
  source?: string;
  note?: string;
}

// What was knowable at a given moment -- the point-in-time discipline, on screen.
export interface PointInTimeView {
  available: boolean;
  why?: string;
  as_of?: { decision_time: string; knowledge_cutoff: string };
  strict?: boolean;
  visible_sessions?: number;
  latest_visible_session?: string | null;
  latest_visible_close?: number | null;
  // HOW MUCH WAS DELIBERATELY HIDDEN. A lovely field: it lets the page show the reader
  // that data was withheld, and how much -- turning an invisible discipline into something
  // demonstrable.
  withheld_by_knowledge_bound?: number;
  explanation?: string;
  read_path?: string;
}

export interface InstrumentFoundation {
  week1_version: string;
  symbol: string;
  status: SecurityStatus;
  corporate_actions: CorporateActionContext;
  price_band: PriceBand;
  point_in_time: PointInTimeView;
}

// The shape every liquidity measure shares: available, or a reason.
export interface LiquidityMetric {
  available: boolean;
  why?: string;
}

/** Week 2 estimators for one security. Every value is read from the built artifacts. */
export interface InstrumentLiquidity {
  week2_version: string;
  symbol: string;
  // `&` combines two shapes: every measure has the available/why pair PLUS its own fields.
  // So the honesty is structural -- no measure can exist without the ability to say it is
  // unavailable and why.
  realised_variance: LiquidityMetric & {
    annualised_volatility?: number;
    sampling_minutes?: number;
    n_returns?: number;
    // How precise the estimate is -- carried beside it, as always.
    relative_standard_error?: number;
    sessions?: number;
  };
  price_impact: LiquidityMetric & {
    lambda?: number;
    // The full statistical detail: the error, the test statistic, how many observations,
    // how much was explained, and whether it was significant. Enough for a reader to judge
    // the estimate rather than just read it.
    standard_error?: number;
    t_stat?: number;
    n_obs?: number;
    r_squared?: number;
    significant?: boolean;
  };
  arrival: LiquidityMetric & {
    mean_daily_trades?: number;
    // The burstiness factor and which model won -- the Week 2 result the detector consumes.
    fano_factor?: number;
    model_selected?: string;
    overdispersed?: boolean;
  };
  liquidity_state: LiquidityMetric & {
    stress_score?: number;
    stress_gate_fired?: boolean;
    latest_session?: string;
    sessions?: number;
    sessions_stressed?: number;
    // WHICH measure caused the alarm, and each one's share of the blame -- the honest
    // attribution, carried through to the screen.
    primary_driver?: string;
    attribution?: Record<string, number>;
    // And each component's raw value AND standardised score, so a reader sees both the real
    // measurement and how unusual it was.
    components?: Record<
      string,
      { value: number | null; robust_z: number | null; label: string }
    >;
  };
}

// Everything about one company.
export interface Instrument {
  found: boolean;
  symbol: string;
  tracked: boolean;
  tracked_rank: number | null;
  market: MarketBlock;
  risk: RiskBlock;
  announcements?: AnnouncementsBlock;
  foundation?: InstrumentFoundation;
  liquidity?: InstrumentLiquidity;
  // Plain-English notes about what was found.
  observations: string[];
}

// The whole market at a glance.
export interface MarketOverview {
  market: {
    available: boolean;
    last_session: string;
    instruments_traded: number;
    // How many rose, fell and were unchanged.
    advancing: number;
    declining: number;
    unchanged: number;
    // The MEDIAN change, not the mean -- so one extreme company cannot define "the market".
    median_change_pct: number | null;
    turnover: number;
    source: string;
    note: string;
  };
  tracked: {
    // The subset this project actually studies, reported SEPARATELY from the whole market
    // -- so nobody mistakes our fifty companies for the market as a whole.
    name: string;
    instruments: number;
    advancing: number;
    declining: number;
    median_change_pct: number | null;
    // And a caveat attached, as a required field.
    caveat: string;
  };
  risk_mix: {
    available: boolean;
    states: { state: string; label: string; tone: Tone; instruments: number }[];
    instruments: number;
    note: string;
    provenance?: Record<string, unknown>;
  };
}

// One row of the "worth a look" list.
export interface AttentionRow {
  symbol: string;
  state: string;
  state_label: string;
  state_tone: Tone;
  score: number;
  // The uncertainty travels even into a compact list row.
  uncertainty: number;
  date: string;
}

// One search result.
export interface SearchRow {
  symbol: string;
  // Two separate flags: is it in our studied set, and has it actually been assessed? A
  // company can be tracked without having been scored, and the two are not the same fact.
  tracked: boolean;
  analysed: boolean;
  state: string | null;
  state_label: string | null;
  state_tone: Tone | null;
  change_pct: number | null;
  turnover: number;
}

// THE WRAPPER THAT MAKES THE WHOLE FILE HONEST.
export interface Sourced<T> {
  // Live, snapshot, or nothing at all.
  source: ProductSource;
  /** The session the numbers describe. Present whether live or from a snapshot. */
  asOf: string | null;
  /** When a snapshot was taken. Null for a live read. */
  // Two DIFFERENT dates, and the distinction matters: `asOf` is which trading day the
  // numbers describe; `snapshotAt` is when we saved them. A file made on Friday about
  // Tuesday's trading has different values in each.
  snapshotAt?: string | null;
  data: T | null;
  note?: string;
}

// The shape of the saved snapshot file.
interface MarketBundleMeta {
  last_session: string;
  n_instruments: number;
  snapshot_window: number;
  overview: MarketOverview;
  attention: { available: boolean; rows: AttentionRow[]; total: number; scored: number };
  directory: { results: SearchRow[] };
  note: string;
}

// How long to wait for the live service before giving up. Configurable, defaulting to
// eight seconds.
const TIMEOUT_MS = Number(process.env.AEGIS_BACKEND_TIMEOUT_MS ?? 8000);

// Where the live service is, if it is configured at all.
function backendBase(): string | null {
  const raw = process.env.AEGIS_BACKEND_URL?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    // ONLY http and https are accepted. A security check: without it, a mistyped or
    // malicious setting could point this at a local file or another protocol entirely.
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null;
  } catch {
    // Not a valid address at all. Treated as "no service configured" rather than crashing
    // the whole site at startup.
    return null;
  }
}

/**
 * Ask the analysis service, or return null.
 *
 * A short timeout on purpose. This runs while a page is rendering, and a reader waiting
 * eight seconds for a home page has already formed an opinion about the product; the
 * stored snapshot beneath it is a better answer than a slow one.
 */
// PLAIN ENGLISH: an unusually clear-eyed piece of product reasoning. A visitor staring at a
// blank page for eight seconds has already decided the site is broken. So we do not wait
// indefinitely for the freshest possible answer -- we give up and serve the saved one,
// which is slightly older and arrives instantly.
// And crucially, the reader is TOLD it is the saved one. That is what makes the trade
// acceptable rather than a quiet degradation.
async function fromBackend<T>(path: string): Promise<T | null> {
  const base = backendBase();
  if (!base) return null;
  const headers: Record<string, string> = {};
  // The password, if one is configured.
  const token = process.env.AEGIS_BACKEND_TOKEN?.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const res = await fetch(`${base}/api/${path}`, {
      headers,
      // Never use a cached answer: "live" must genuinely mean live, or the label is a lie.
      cache: 'no-store',
      // And the timeout, which is what enforces the reasoning above.
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    // Any failure at all -- unreachable, too slow, malformed -- becomes a plain null, and
    // the caller falls back to the snapshot. The site stays up.
    return null;
  }
}

// Read the saved snapshot.
async function snapshot(): Promise<{
  meta: MarketBundleMeta | null;
  rows: Instrument[];
  generatedAt: string | null;
}> {
  const bundle = await getBundle<Instrument>('market.json');
  return {
    meta: (bundle.meta as unknown as MarketBundleMeta) ?? null,
    rows: bundle.rows,
    generatedAt: bundle.generatedAt,
  };
}

// The message shown when there is genuinely nothing -- naming both ways to fix it.
const MISSING =
  'No market snapshot has been exported and no analysis backend is reachable. Run ' +
  'python scripts/export_product.py, or start the backend with run_dev.bat.';

// THE PATTERN EVERY GETTER BELOW FOLLOWS: try live, fall back to the snapshot, and say
// which. Read this one and the rest are the same.
export async function getOverview(): Promise<Sourced<MarketOverview>> {
  // 1. Try live.
  const live = await fromBackend<MarketOverview>('market/overview');
  if (live?.market) {
    // Labelled 'live', with the session it describes.
    return { source: 'live', asOf: live.market.last_session, data: live };
  }
  // 2. Fall back to the saved file.
  const { meta, generatedAt } = await snapshot();
  if (meta?.overview) {
    return {
      // Labelled 'snapshot' -- AND carrying when the snapshot was taken, so the page can
      // say how old it is.
      source: 'snapshot',
      asOf: meta.last_session,
      snapshotAt: generatedAt,
      data: meta.overview,
    };
  }
  // 3. Nothing at all. Null data, and the instructions to fix it. Never invented numbers.
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

// The companies worth a look.
export async function getAttention(limit = 8): Promise<Sourced<AttentionRow[]>> {
  const live = await fromBackend<{ rows: AttentionRow[] }>(
    `market/attention?limit=${limit}`,
  );
  if (live?.rows) {
    // Even on the live path the snapshot is read, purely for the session date -- because a
    // result must always be able to say which trading day it describes.
    const { meta } = await snapshot();
    return { source: 'live', asOf: meta?.last_session ?? null, data: live.rows };
  }
  const { meta, generatedAt } = await snapshot();
  if (meta?.attention?.rows) {
    return {
      source: 'snapshot',
      asOf: meta.last_session,
      snapshotAt: generatedAt,
      data: meta.attention.rows.slice(0, limit),
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

// One company.
export async function getInstrument(symbol: string): Promise<Sourced<Instrument>> {
  const clean = symbol.toUpperCase().trim();
  // `encodeURIComponent` makes the name safe to put in a web address -- so a symbol
  // containing an awkward character cannot break the address or reach somewhere else.
  const live = await fromBackend<Instrument>(`instruments/${encodeURIComponent(clean)}`);
  if (live?.found) {
    return { source: 'live', asOf: live.market.last_session, data: live };
  }
  const { rows, meta, generatedAt } = await snapshot();
  const found = rows.find((r) => r.symbol === clean);
  if (found) {
    return {
      source: 'snapshot',
      asOf: meta?.last_session ?? found.market.last_session,
      snapshotAt: generatedAt,
      data: found,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

/** Every instrument the product can open, for the directory and for static params. */
export async function listInstrumentSymbols(): Promise<string[]> {
  const { rows } = await snapshot();
  return rows.map((r) => r.symbol).sort();
}

/**
 * Instruments matching a term.
 *
 * Served from the snapshot rather than the backend: this runs on a prerendered page and
 * the snapshot already holds every instrument the product can open. A search that reached
 * across the network would be slower and would find nothing extra.
 */
// PLAIN ENGLISH: a deliberate exception to the live-first rule, with the reasoning given.
// The saved file already contains every company the site can open. Asking the service would
// be slower and could not possibly find anything more. So it does not.
export async function searchInstruments(
  query: string,
  limit = 24,
): Promise<{ rows: Instrument[]; total: number; asOf: string | null }> {
  const { rows, meta } = await snapshot();
  const q = query.trim().toUpperCase();
  const matched = q
    ? rows.filter((r) => r.symbol.includes(q))
    // An empty search shows the tracked companies rather than nothing -- a useful default.
    : rows.filter((r) => r.tracked);
  matched.sort((a, b) => {
    // Companies whose name STARTS with what you typed come first -- typing "REL" should
    // surface RELIANCE above something that merely contains those letters.
    const starts = Number(b.symbol.startsWith(q)) - Number(a.symbol.startsWith(q));
    if (starts !== 0) return starts;
    // Then the most heavily traded, as a reasonable proxy for what you probably meant.
    return (b.market?.turnover ?? 0) - (a.market?.turnover ?? 0);
  });
  return {
    rows: matched.slice(0, limit),
    // The TOTAL is reported as well as the shown rows, so the page can say "24 of 137".
    total: matched.length,
    asOf: meta?.last_session ?? null,
  };
}

/* -- indices ---------------------------------------------------------------------- */

/**
 * An index is not an instrument and not a universe.
 *
 * The type is carried through from `research/data/instruments.py` so the distinction
 * survives the trip to the browser. A page that renders an `INDEX` is rendering a
 * published benchmark with a level; a page that renders a `UNIVERSE_PROXY` is rendering a
 * set of instruments this project selected, which has no level at all. Nothing in this
 * file lets one stand in for the other.
 */
// PLAIN ENGLISH: the survivorship-bias story from the research side, arriving at the
// browser intact.
//   An INDEX is an official published benchmark. It has a level -- "the Nifty is at 22,000".
//   A UNIVERSE_PROXY is a set of companies WE chose. It has no level at all; the question
//   does not even apply to it.
// Making them different types means the code physically cannot show one where the other
// belongs. The honesty is enforced by the language rather than by anybody remembering.
export type InstrumentKind = 'INDEX' | 'EQUITY' | 'UNIVERSE_PROXY' | 'MEDIA_EVENT';

/** How current a number is. An end-of-day report is not a live quote and never says so. */
// Four honest levels, so a day-old closing price can never be displayed as a live quote.
export type Recency = 'LIVE' | 'DELAYED' | 'LATEST_AVAILABLE_SESSION' | 'HISTORICAL';

// Where an index's data came from, and what may be done with it.
export interface IndexProvenance {
  source: string;
  source_url: string;
  // How we got it, and whether we may republish it. Two separate questions, as always.
  access_type: 'PUBLIC' | 'LICENSED' | 'DERIVED';
  redistribution_status: 'VERIFIED' | 'RESTRICTED' | 'UNKNOWN';
  license_note: string;
  frequency: string;
  field_note: string;
}

// What we hold for one index.
export interface IndexCoverage {
  index_id: string;
  available: boolean;
  display_name?: string;
  instrument_type?: string;
  sessions?: number;
  first_session?: string;
  last_session?: string;
  history_limit_note?: string;
  // Which fields are missing, each with its reason -- rather than simply being absent.
  unavailable_fields?: Record<string, string>;
  provenance?: IndexProvenance | null;
  index_version?: string;
  ingested_at?: string;
  why?: string;
}

// Which companies are in an index -- and the honest account of why we cannot say.
export interface IndexConstituents {
  available: boolean;
  count: number | null;
  // Not merely "unavailable" but four separate fields explaining the situation.
  why: string;
  // What would be needed to answer it.
  what_would_be_needed: string;
  // AND WHAT MUST NOT BE USED INSTEAD. Remarkable: the shape itself carries a warning
  // against substituting the liquidity proxy for real index membership.
  not_substituted_by: Record<string, string>;
  declared_unavailable_in_registry: boolean;
}

// Everything about one index.
export interface IndexDetail {
  available: boolean;
  instrument_id: string;
  instrument_type: InstrumentKind;
  display_name: string;
  description: string;
  last_session: string;
  close: number;
  change: number | null;
  change_pct: number | null;
  previous_close: number | null;
  volatility_20d: number | null;
  drawdown: number | null;
  high_52w: number | null;
  low_52w: number | null;
  window_sessions: number;
  window_change_pct: number | null;
  series: PricePoint[];
  coverage: IndexCoverage;
  provenance: IndexProvenance | null;
  // BOTH lists: what we have, and what we do not have with reasons for each.
  available_fields: string[];
  unavailable_fields: Record<string, string>;
  recency: Recency;
  recency_note: string;
  constituents: IndexConstituents;
  why?: string;
  remedy?: string;
}

// A compact index summary.
export interface IndexSummary {
  instrument_id: string;
  instrument_type: InstrumentKind;
  display_name: string;
  close: number;
  change_pct: number | null;
  last_session: string;
  series: PricePoint[];
}

interface IndexBundle {
  indices?: { available: boolean; rows: IndexSummary[]; primary: string };
  index_detail?: Record<string, IndexDetail>;
}

export const PRIMARY_INDEX = 'NIFTY50';

/** Everything a reader might type that means the benchmark. Never the proxy. */
// PLAIN ENGLISH: people write index names in many ways. All of these resolve to the real
// published index.
// And note the second sentence: "Never the proxy." Typing "NIFTY" gets you the actual Nifty
// index, never our liquidity stand-in. The distinction from the type definition above is
// enforced here too, in the lookup itself.
export const INDEX_ALIASES: Record<string, string> = {
  NIFTY: PRIMARY_INDEX,
  NIFTY50: PRIMARY_INDEX,
  'NIFTY 50': PRIMARY_INDEX,
  // Including the ticker symbols people copy from other financial sites.
  '^NSEI': PRIMARY_INDEX,
  NSEI: PRIMARY_INDEX,
  BANKNIFTY: 'NIFTYBANK',
  NIFTYBANK: 'NIFTYBANK',
  'NIFTY BANK': 'NIFTYBANK',
  FINNIFTY: 'NIFTYFINSERVICE',
  MIDCPNIFTY: 'NIFTYMIDCAP50',
  NIFTYNXT50: 'NIFTYNEXT50',
  'NIFTY NEXT 50': 'NIFTYNEXT50',
};

export function resolveIndexId(term: string): string | null {
  const key = term.trim().toUpperCase();
  // Two attempts: as typed, then with all spaces removed -- so "NIFTY 50" and "NIFTY50"
  // both work without needing a separate entry for every spacing variant.
  return INDEX_ALIASES[key] ?? INDEX_ALIASES[key.replace(/\s+/g, '')] ?? null;
}

// One index. The same live-then-snapshot-then-nothing pattern.
export async function getIndex(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexDetail>> {
  const live = await fromBackend<IndexDetail>(`indices/${encodeURIComponent(indexId)}`);
  if (live?.available) {
    return { source: 'live', asOf: live.last_session, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexBundle | null)?.index_detail?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.last_session,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    // The stored reason if there is one; otherwise the exact commands to fix it.
    note:
      stored?.why ??
      'No index panel has been built. Point AEGIS_NSE_ARCHIVE at a downloaded NSE ' +
        'archive and run python scripts/build_index_panel.py.',
  };
}

// Every index.
export async function getIndices(): Promise<Sourced<IndexSummary[]>> {
  const live = await fromBackend<{ rows: IndexSummary[] }>('indices');
  if (live?.rows?.length) {
    return { source: 'live', asOf: live.rows[0].last_session, data: live.rows };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexBundle | null)?.indices;
  if (stored?.rows?.length) {
    return {
      source: 'snapshot',
      asOf: stored.rows[0].last_session,
      snapshotAt: generatedAt,
      data: stored.rows,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index panel.' };
}

/** How a level should be written: an index level is not money and carries no symbol. */
// PLAIN ENGLISH: a small but precise distinction. A share price is money and gets a ₹ sign.
// An index level is not money at all -- the Nifty being "at 22,000" is a number on a scale,
// not 22,000 rupees of anything. So it is formatted WITHOUT a currency symbol.
export function level(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  // `en-IN` groups the digits the Indian way (22,000 rather than 22.000 or 22 000), which
  // is how the intended reader expects to see it.
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// The words for each level of freshness.
export const RECENCY_COPY: Record<Recency, string> = {
  LIVE: 'Live',
  DELAYED: 'Delayed',
  LATEST_AVAILABLE_SESSION: 'Latest available session',
  HISTORICAL: 'Historical',
};

// One point of an index's history.
export interface IndexSeriesPoint {
  date: string;
  close: number;
  return_pct: number | null;
  volatility_20d: number | null;
  drawdown: number | null;
}

// One way of viewing that history.
export interface IndexSeriesView {
  key: 'close' | 'return_pct' | 'volatility_20d' | 'drawdown';
  label: string;
  // The UNIT, so an axis is never unlabelled and a percentage is never read as points.
  unit: 'points' | 'percent';
  note: string;
}

export interface IndexSeries {
  available: boolean;
  instrument_id: string;
  display_name: string;
  sessions: number;
  // The window shown, AND the full range available -- so a page can say "showing 1 year of
  // 12 available" rather than implying this is everything there is.
  from: string;
  to: string;
  full_from: string;
  full_to: string;
  series: IndexSeriesPoint[];
  views: IndexSeriesView[];
  recency: Recency;
  why?: string;
}

// How an index's period relates to the evidence this project holds.
export interface IndexContext {
  available: boolean;
  instrument_id: string;
  display_name: string;
  window: { from: string; to: string; sessions: number };
  market_context: {
    level: string;
    documents: number;
    instruments_with_documents: number;
    by_kind: { doc_kind: string; documents: number }[];
    panel_sessions: number;
    panel_instruments: number;
    // A plain-English reading, so the counts arrive with their meaning attached.
    reading: string;
  };
  instrument_evidence: {
    level: string;
    assessed_from: string | null;
    assessed_to: string | null;
    assessed_rows: number;
    // HOW MANY SESSIONS ACTUALLY OVERLAP. The key number: without overlap the two cannot
    // honestly be discussed together at all.
    overlapping_sessions: number;
    reading: string;
  };
  coverage_note: string;
}

interface IndexExtras {
  index_series?: Record<string, IndexSeries>;
  index_context?: Record<string, IndexContext>;
}

// The history of one index.
export async function getIndexSeries(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexSeries>> {
  const live = await fromBackend<IndexSeries>(
    `indices/${encodeURIComponent(indexId)}/series`,
  );
  if (live?.available) return { source: 'live', asOf: live.to, data: live };
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexExtras | null)?.index_series?.[indexId];
  if (stored?.available) {
    return { source: 'snapshot', asOf: stored.to, snapshotAt: generatedAt, data: stored };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index series.' };
}

// And its context.
export async function getIndexContext(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexContext>> {
  const live = await fromBackend<IndexContext>(
    `indices/${encodeURIComponent(indexId)}/context`,
  );
  if (live?.available) return { source: 'live', asOf: live.window.to, data: live };
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexExtras | null)?.index_context?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.window.to,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index context.' };
}


/* -- evidence alignment ------------------------------------------------------------ */

/**
 * Whether two sources can be spoken about together.
 *
 * Computed by the backend on every request from the sessions each source holds — never
 * stored, never assumed. A pair reading NOT_ALIGNED today becomes ALIGNED on its own when
 * an overlapping source is ingested, and nothing in this file needs to change for that.
 */
// PLAIN ENGLISH: a genuinely important idea that most projects never even consider.
// You have index data covering 2015-2020, and news data covering 2021-2024. Can you say
// anything about how they relate? NO. They do not overlap at all. Any statement connecting
// them would be about nothing.
// So this measures the overlap and states plainly whether the two may be discussed together.
// And it is computed FRESH every time -- so when new data arrives that closes the gap, the
// verdict changes by itself, with no code to update and nobody to remember.
export type AlignmentStatus = 'ALIGNED' | 'PARTIAL' | 'NOT_ALIGNED' | 'UNKNOWN';

// What period one source covers.
export interface CoverageWindow {
  source_id: string;
  kind: string;
  label: string;
  // Nullable, because a source may hold nothing at all -- which is different from covering
  // a period of zero length.
  start: string | null;
  end: string | null;
  sessions: number;
  note: string;
}

// The relationship between two sources.
export interface AlignmentPair {
  alignment_version: string;
  source_a: CoverageWindow;
  source_b: CoverageWindow;
  index_start: string | null;
  index_end: string | null;
  evidence_start: string | null;
  evidence_end: string | null;
  // WHERE THEY OVERLAP, and by how much.
  overlap_start: string | null;
  overlap_end: string | null;
  overlap_sessions: number;
  coverage_ratio: number;
  alignment_status: AlignmentStatus;
  // The thresholds used to reach that verdict, published alongside it -- so a reader can
  // disagree with the standard rather than only with the conclusion.
  thresholds: { aligned_at: number; minimum_sessions: number };
  summary: string;
  // WHAT THIS PERMITS. Not a vague warning but a specific list of what may and may not be
  // done with the pair -- so the caveat is actionable rather than merely worrying.
  permits: {
    combined_analysis: boolean;
    combined_analysis_with_caveat: boolean;
    side_by_side_presentation: boolean;
    temporal_association: boolean;
    note: string;
  };
  coverage_ratio_note: string;
  why_it_matters?: string;
}

// Every pair, together.
export interface AlignmentMatrix {
  available: boolean;
  alignment_version: string;
  pairs: AlignmentPair[];
  headline: AlignmentPair | null;
  counts: { pairs: number; aligned: number; partial: number; not_aligned: number };
  sources: CoverageWindow[];
  reading: string;
  // What would need to happen for the picture to improve.
  future_path: string;
}

interface AlignmentBundle {
  alignment?: AlignmentMatrix;
}

// The wording for each verdict.
export const ALIGNMENT_COPY: Record<
  AlignmentStatus,
  { label: string; tone: Tone; product: string }
> = {
  ALIGNED: {
    label: 'Aligned',
    tone: 'calm',
    product: 'These cover the same sessions and can be read together.',
  },
  PARTIAL: {
    label: 'Partly aligned',
    tone: 'watch',
    // Precise about the consequence: anything combining them covers only the shared part.
    product: 'These share only part of their period, so anything combining them covers only the shared part.',
  },
  NOT_ALIGNED: {
    label: 'Not aligned',
    tone: 'elevated',
    // And the consequence again: results are shown SEPARATELY. Not combined with a caveat --
    // separately, because combining them would be meaningless.
    product: 'These cover different periods, so results are shown separately.',
  },
  UNKNOWN: {
    // "Not measured", not "unknown alignment" -- the same careful vocabulary as the
    // research register. We did not fail to align them; there was nothing to measure.
    label: 'Not measured',
    tone: 'watch',
    product: 'One of these holds no sessions yet, so the relationship cannot be measured.',
  },
};

export async function getAlignment(): Promise<Sourced<AlignmentMatrix>> {
  const live = await fromBackend<AlignmentMatrix>('alignment');
  if (live?.pairs?.length) {
    return { source: 'live', asOf: live.headline?.index_end ?? null, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as AlignmentBundle | null)?.alignment;
  if (stored?.pairs?.length) {
    return {
      source: 'snapshot',
      asOf: stored.headline?.index_end ?? null,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    note: 'Alignment has not been computed. Start the backend, or run ' +
      'python scripts/export_product.py.',
  };
}

/** The pair a caller cares about, by source identifiers, in either order. */
export function findPair(
  matrix: AlignmentMatrix | null,
  a: string,
  b: string,
): AlignmentPair | null {
  if (!matrix) return null;
  return (
    matrix.pairs.find(
      // BOTH orders checked. The relationship between A and B is the same as between B and
      // A, so a caller should not have to know which way round it happens to be stored.
      (p) =>
        (p.source_a.source_id === a && p.source_b.source_id === b) ||
        (p.source_a.source_id === b && p.source_b.source_id === a),
    ) ?? null
  );
}

/* -- evidence for a market period --------------------------------------------------- */

/**
 * What this project holds for the sessions an index covers, one card per source.
 *
 * A product read model over the alignment layer. Every status arrives computed for that
 * specific pair, so the file contains no threshold, no session count and no verdict of
 * its own — pointing it at a different dataset changes what it renders, not what it says.
 */
// PLAIN ENGLISH: the last clause is the design goal in one line. This file holds no numbers
// and no opinions of its own. Point the whole system at a completely different dataset and
// this file renders different values while saying exactly the same things -- because
// everything it displays was computed elsewhere and handed to it.
export interface EvidenceSource {
  source_id: string;
  // Two labels again: the friendly one and the precise one.
  product_label: string;
  research_label: string;
  product_blurb: string;
  href: string;
  kind: string;
  status: AlignmentStatus;
  badge: string;
  // A symbol as well as words and a colour -- so the verdict is legible without relying on
  // colour alone, which matters for readers who cannot distinguish the tones.
  mark: 'check' | 'partial' | 'cross' | 'unknown';
  tone: Tone;
  product_status: string;
  period: string;
  period_from: string | null;
  period_to: string | null;
  // The full arithmetic behind the verdict, so a reader can check it rather than trust it.
  source_sessions: number;
  index_sessions: number;
  shared_sessions: number;
  overlap_from: string | null;
  overlap_to: string | null;
  coverage_ratio: number;
  summary: string;
  permits: AlignmentPair['permits'];
  source_note: string;
}

export interface EvidenceSummary {
  available: boolean;
  index_id: string;
  index_label: string;
  index_from: string | null;
  index_to: string | null;
  index_sessions: number;
  index_period: string;
  sources: EvidenceSource[];
  counts: { aligned: number; partial: number; not_aligned: number; total: number };
  headline: string;
  // Whether any experiment actually used this index -- with a plain answer and two
  // explanations, one for each audience. An honest "no" where that is the truth.
  experiments_using_index: {
    count: number;
    answer: boolean;
    product_note: string;
    research_note: string;
  };
  why?: string;
  remedy?: string;
}

interface EvidenceBundle {
  evidence?: Record<string, EvidenceSummary>;
}

export async function getEvidenceSummary(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<EvidenceSummary>> {
  const live = await fromBackend<EvidenceSummary>(
    `evidence/${encodeURIComponent(indexId)}`,
  );
  if (live?.available) {
    return { source: 'live', asOf: live.index_to, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as EvidenceBundle | null)?.evidence?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.index_to,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    note:
      stored?.why ??
      'Evidence coverage has not been computed. Start the backend, or run ' +
        'python scripts/export_product.py.',
  };
}

/** One source's card, by identifier. Null when that source is not in the summary. */
export function findEvidence(
  summary: EvidenceSummary | null,
  sourceId: string,
): EvidenceSource | null {
  // `?.` throughout, so a missing summary hands back null rather than crashing.
  return summary?.sources.find((s) => s.source_id === sourceId) ?? null;
}

/* -- presentation helpers -------------------------------------------------------- */

// Money, written the Indian way.
export function inr(value: number | null | undefined): string {
  // The em-dash for a missing value -- visibly absent, and never confusable with zero.
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

/**
 * Rupees at the scale Indian markets actually quote them.
 *
 * A session's turnover runs to twelve digits, and `₹104976.4 cr` is a number nobody
 * reads — the scale it belongs to is lakh crore, which is how the exchange, the press and
 * anyone looking at this page would say it out loud.
 */
// PLAIN ENGLISH: a lovely piece of attention to the reader. The daily turnover of a whole
// market is an enormous number. Written in full it is a wall of digits nobody can take in.
// Written as "₹10.5 lakh cr" it is instantly graspable -- and, crucially, it is how the
// exchange itself, the newspapers and anybody in the room would actually say it.
export function compactInr(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const round = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  // Largest scale first, so each value lands on the biggest unit that suits it.
  // 1e12 is a lakh crore, 1e7 a crore, 1e5 a lakh.
  if (value >= 1e12) return `₹${round(value / 1e12)} lakh cr`;
  if (value >= 1e7) return `₹${round(value / 1e7)} cr`;
  if (value >= 1e5) return `₹${round(value / 1e5)} lakh`;
  // And anything smaller in plain rupees.
  return inr(value);
}

// A percentage with its sign always shown.
export function signedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const shown = (value * 100).toFixed(digits);
  // The plus added by hand, because a change of "+0.42%" reads unmistakably as a change,
  // where a bare "0.42%" could be read as a level.
  return `${value >= 0 ? '+' : ''}${shown}%`;
}

// Up, down, or flat.
export function direction(value: number | null | undefined): 'up' | 'down' | 'flat' {
  // Note that an unknown value returns 'flat', NOT 'down'. A missing number must never be
  // drawn as a fall -- that would be inventing bad news out of an absence.
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return 'flat';
  }
  return value > 0 ? 'up' : 'down';
}

/** How a sourced payload should describe itself, in one short clause. */
// THE SENTENCE THAT APPEARS ON THE PAGE, and the point of the whole file. Every number is
// accompanied by a clause saying where it came from and which trading day it describes.
export function sourceNote(s: Sourced<unknown>): string {
  if (s.source === 'live') return `Read from the analysis service · session ${s.asOf}`;
  if (s.source === 'snapshot') {
    // Says "stored snapshot" plainly. Not "cached", not silence -- the reader is told.
    return `Stored snapshot · session ${s.asOf}`;
  }
  return 'No data available';
}
