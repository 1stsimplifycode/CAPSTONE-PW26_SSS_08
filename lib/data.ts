/**
 * Data access for both experiences.
 *
 * The deployed app never runs the research pipeline. It reads JSON bundles that
 * `scripts/export_app_data.py` wrote, which is what guarantees the product cannot display
 * a number the research pipeline did not produce.
 *
 * Every accessor degrades to an empty result carrying `dataAvailable: false` and a note
 * saying how to produce the missing artifact. A dashboard that renders nothing and says
 * why is honest; one that renders a plausible placeholder is not.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * WHERE THE WEBSITE GETS ITS NUMBERS FROM.
 *
 * And the first rule is about where it does NOT get them: the website never runs the
 * research itself. It only ever reads results that were computed earlier and saved to
 * files.
 *
 * Why does that matter so much? Because it makes it IMPOSSIBLE for the website to show a
 * number the research never produced. If the website could compute things, then one day
 * it would compute something slightly differently from the paper, and the two would
 * disagree with nobody able to say which was right. Reading from files means there is only
 * ever one set of numbers.
 *
 * THE SECOND RULE, and it runs through every function below:
 *
 *     "A dashboard that renders nothing and says why is honest;
 *      one that renders a plausible placeholder is not."
 *
 * When a file is missing, the tempting thing is to show something -- zeros, a dash, some
 * example data so the page does not look broken. That is exactly wrong. A chart of zeros
 * looks like a real chart of a quiet market. Nobody can tell it apart from a finding.
 * So instead every function hands back an empty result carrying a flag saying "there is no
 * data here", plus the exact command to produce it. The page then says, plainly, that it
 * has nothing to show and what would fix that.
 */
// `fs` is the file system -- the tools for reading files from disk. `promises` is the
// version that does not freeze everything while it waits.
import { promises as fs } from 'node:fs';
// Tools for building file paths correctly on any operating system.
import path from 'node:path';

// The SHAPES of everything read below. `import type` means these are used only for
// checking correctness while the code is being written -- they vanish entirely from the
// program that actually runs, so they cost nothing.
import type {
  BlockInfoRow,
  ClaimRecord,
  ClusterInfo,
  CoverageSummary,
  EvidenceItem,
  ExperimentRecord,
  FigureRecord,
  LifecycleTrajectory,
  LimitationRecord,
  ProvenanceRow,
  RiskAssessment,
  RiskWindow,
  StatisticRecord,
  UniverseInfo,
} from './types';

// The one folder every exported result lives in. `process.cwd()` is the folder the program
// was started from, so this works wherever the project is installed.
const DATA_DIR = path.join(process.cwd(), 'public', 'data');

// The shape every read returns. The `<T>` means "this works for any kind of row" -- one
// definition serving every different sort of result.
export interface Bundle<T> {
  // WAS THERE ANY DATA? The flag everything else depends on.
  dataAvailable: boolean;
  // When the file was produced, so a page can show how fresh it is.
  generatedAt: string | null;
  // The rows themselves.
  rows: T[];
  // Any extra information the file carried.
  meta?: Record<string, unknown>;
  // And, when there is no data, WHY -- and what to do about it.
  note?: string;
}

// Read one exported file.
async function readJson<T>(file: string): Promise<Bundle<T>> {
  try {
    // Read the file as text, in the utf8 alphabet so any language survives.
    const raw = await fs.readFile(path.join(DATA_DIR, file), 'utf8');
    // Turn the text back into structured information. The `as` tells the type checker to
    // expect either a wrapped object or a bare list -- both forms are handled below.
    const parsed = JSON.parse(raw) as
      | { generated_at?: string; rows?: T[]; meta?: Record<string, unknown> }
      | T[];
    // Some files are just a plain list of rows with no wrapper.
    if (Array.isArray(parsed)) {
      return { dataAvailable: true, generatedAt: null, rows: parsed };
    }
    // Others carry a wrapper with a timestamp and extra details.
    return {
      dataAvailable: true,
      // `??` means "use the left side unless it is missing, then use the right". So a file
      // with no timestamp reports null rather than undefined.
      generatedAt: parsed.generated_at ?? null,
      rows: parsed.rows ?? [],
      meta: parsed.meta,
    };
  } catch {
    // THE HONEST FAILURE. Missing file, unreadable file, malformed file -- all end here.
    return {
      // The flag that tells every page there is genuinely nothing.
      dataAvailable: false,
      generatedAt: null,
      // An EMPTY list. Not example data, not zeros. Nothing.
      rows: [],
      // And the exact commands to fix it, naming the missing file. Somebody hitting a blank
      // page is told precisely what to run, rather than being left to guess.
      note:
        `No exported artifact ${file}. Run the research pipeline, then ` +
        `python scripts/export_app_data.py to populate public/data/.`,
    };
  }
}

/**
 * Read any exported bundle by filename.
 *
 * Exposed so the module layer can add bundles without this file growing an accessor per
 * file, while every bundle still degrades the same way when its artifact is absent.
 */
// PLAIN ENGLISH: an escape hatch, deliberately provided. Without it, every new result file
// would need another line added here forever. With it, other code can read any bundle it
// likes -- and crucially, still gets the same honest missing-file behaviour, because it is
// the same function underneath rather than a second implementation.
export const getBundle = readJson;

// Named shortcuts for the common files. Each one pins down what shape its rows have, so a
// mistake -- reading assessments and treating them as figures -- is caught while writing
// the code rather than by a visitor.
// The risk scores for each company on each day.
export const getAssessments = () => readJson<RiskAssessment>('assessments.json');
// The episodes of trouble.
export const getWindows = () => readJson<RiskWindow>('windows.json');
// The evidence behind them.
export const getEvidence = () => readJson<EvidenceItem>('evidence.json');
// The experiments and their results.
export const getExperiments = () => readJson<ExperimentRecord>('experiments.json');
export const getStatistics = () => readJson<StatisticRecord>('statistics.json');
export const getFigures = () => readJson<FigureRecord>('figures.json');
// Where everything came from.
export const getProvenance = () => readJson<ProvenanceRow>('provenance.json');
// How complete the evidence was.
export const getCoverage = () => readJson<CoverageSummary>('coverage.json');
// The known gaps -- so the caveats reach the screen.
export const getLimitations = () => readJson<LimitationRecord>('limitations.json');
// And the claims the project makes, each tied back to its evidence.
export const getClaims = () => readJson<ClaimRecord>('claims.json');
export const getBlockInfo = () => readJson<BlockInfoRow>('block_info.json');

// Which companies move together.
export const getClusters = () => readJson<ClusterInfo>('clusters.json');
export const getPropagationEdges = () =>
  readJson<{ source: string; target: string; weight: number }>('propagation.json');
export const getResearchAngles = () =>
  readJson<Record<string, unknown>>('research_angles.json');
export const getReproducibility = () =>
  readJson<Record<string, unknown>>('reproducibility.json');

/** The active research universe and its provenance (spec section 8). */
export async function getUniverse(): Promise<UniverseInfo> {
  const b = await readJson<UniverseInfo>('universe.json');
  if (b.rows.length) return b.rows[0];
  // THE FALLBACK, and look carefully at what it does. It does NOT invent a plausible
  // universe. Every field says "unknown", the member count is zero, and the flag saying
  // "this is index membership" is explicitly false.
  return {
    id: 'unknown',
    name: 'Universe not exported',
    kind: 'point_in_time_proxy',
    effectiveDate: null,
    datasetVersion: 'unknown',
    memberCount: 0,
    distinctMembersEver: null,
    rebalances: null,
    meanEntriesPerRebalance: null,
    // Set to false deliberately: with no manifest we cannot claim this is any index, and
    // the safe answer is the one that claims less.
    isIndexMembership: false,
    // And a warning written in full, telling the reader not to attribute anything on the
    // page to any index. The caveat survives even total absence of data.
    caveat:
      'No universe manifest was exported. The active universe is unknown, so nothing ' +
      'on this page should be attributed to any index.',
  };
}

/** Latest assessment per instrument, most elevated first. */
export async function getMarketOverview(): Promise<Bundle<RiskAssessment>> {
  const all = await getAssessments();
  // Pass the missing-data result straight through, so the flag and the note survive
  // intact rather than being replaced by a cheerful empty list.
  if (!all.dataAvailable) return all;
  // A Map remembers one entry per company.
  const latest = new Map<string, RiskAssessment>();
  for (const r of all.rows) {
    const prev = latest.get(r.instrument);
    // Keep this row if it is the first for that company, or more recent than the one held.
    // Comparing dates as text works because they are written YYYY-MM-DD, which sorts
    // correctly alphabetically -- one of the quiet benefits of that spelling.
    if (!prev || r.date > prev.date) latest.set(r.instrument, r);
  }
  // Sort with the highest risk first, since that is what a reader is looking for.
  const rows = [...latest.values()].sort((a, b) => b.integrityRisk - a.integrityRisk);
  // `...all` copies the flag, timestamp and note across, and only the rows are replaced.
  return { ...all, rows };
}

// One company's history, in date order.
export async function getInstrumentSeries(
  symbol: string,
): Promise<Bundle<RiskAssessment>> {
  const all = await getAssessments();
  if (!all.dataAvailable) return all;
  const rows = all.rows
    .filter((r) => r.instrument === symbol)
    // `localeCompare` compares two pieces of text properly, giving oldest first.
    .sort((a, b) => a.date.localeCompare(b.date));
  return { ...all, rows };
}

// Every company we have, in alphabetical order.
export async function listInstruments(): Promise<string[]> {
  const all = await getAssessments();
  // `new Set(...)` removes duplicates, and `[...]` turns it back into a list.
  return [...new Set(all.rows.map((r) => r.instrument))].sort();
}

// Look up one limitation by its name.
export async function getLimitation(id: string): Promise<LimitationRecord | null> {
  const b = await getLimitations();
  // `.toUpperCase()` on both sides makes the lookup case-insensitive, so a link written
  // "l-04" still finds "L-04". `?? null` hands back a clean null when there is no match.
  return b.rows.find((l) => l.id.toUpperCase() === id.toUpperCase()) ?? null;
}

/** Most recent risk windows across all instruments, newest first. */
export async function getRecentEvents(limit = 60): Promise<Bundle<RiskWindow>> {
  const b = await getWindows();
  if (!b.dataAvailable) return b;
  // `[...b.rows]` copies before sorting -- sorting in place would rearrange the original,
  // which another part of the page might still be relying on.
  const rows = [...b.rows]
    // Newest first, so `b2` and `a` are the other way round from the ascending version.
    .sort((a, b2) => b2.tEntry.localeCompare(a.tEntry))
    // Only the most recent 60, so a page cannot try to draw ten thousand items.
    .slice(0, limit);
  return { ...b, rows };
}

// Format a number for display.
export function fmt(value: number | null | undefined, digits = 3): string {
  // THREE ways a number can be absent, and all three become the SAME visible "n/a".
  // NaN is the result of a broken sum, null is a deliberate blank, undefined is a missing
  // field. A reader does not need to know which -- they need to know it is not a number.
  // What matters is that none of them ever reaches the screen as "0".
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  return value.toFixed(digits);
}

// Format a fraction as a percentage.
export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  // 0.85 becomes "85.0%".
  return `${(value * 100).toFixed(digits)}%`;
}

// Format a number with its sign always shown.
export function signed(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  // The `+` is added by hand for positive numbers, since a minus sign appears on its own
  // but a plus does not. It matters for a difference: "+0.02" and "0.02" read differently,
  // and the first makes clear it is a change rather than a level.
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

// The remaining bundles, each read the same honest way.
export const getLifecycle = () => readJson<Record<string, unknown>>('lifecycle.json');
export const getLifecycleTrajectories = () =>
  readJson<LifecycleTrajectory>('lifecycle_trajectories.json');

/** One instrument's trajectory, or null when the instrument is outside the cohort. */
export async function getTrajectory(
  symbol: string,
): Promise<LifecycleTrajectory | null> {
  const b = await getLifecycleTrajectories();
  // null means "this company is not in this study" -- a real and different answer from
  // "this company had no trouble", and the page can word the two differently.
  return b.rows.find((t) => t.symbol === symbol) ?? null;
}

export const getTrust = () => readJson<Record<string, unknown>>('trust.json');

export const getAffectiveLab = () =>
  readJson<Record<string, unknown>>('affective_lab.json');

export const getRobustnessLab = () =>
  readJson<Record<string, unknown>>('robustness_lab.json');
