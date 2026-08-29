/**
 * The backend response contract, in TypeScript.
 *
 * A mirror of `backend/contract.py` and `backend/registry.py`. It is a mirror rather than
 * a generated file because there are two of them and one round of drift would be caught
 * by `tsc` immediately; a code generator would be more machinery than the problem needs.
 *
 * No filesystem access here, deliberately: the run panel is a client component, and the
 * types and copy it needs must not drag `node:fs` into the browser bundle. `lib/weeks.ts`
 * does the reading and re-exports this file.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE WEBSITE'S COPY OF THE AGREEMENT WITH THE SERVER.
 *
 * The server replies in a particular shape (defined in `backend/contract.py`). This file
 * writes that same shape down again in the website's language, so the website knows what
 * to expect.
 *
 * "A MIRROR RATHER THAN A GENERATED FILE" is an interesting decision worth understanding.
 * Two hand-written copies of one thing can drift apart -- that is normally a serious
 * worry. The usual fix is a tool that generates one from the other automatically.
 * The argument here is that the automatic tool is not worth it, for two reasons:
 *   there are only TWO copies, not twenty; and
 *   the type checker catches any drift IMMEDIATELY -- the moment the server adds a field
 *   the website does not know about, the build fails.
 * So the risk is already caught by machinery that exists, and adding a code generator
 * would be more machinery than the problem deserves. That is a judgement call, and it is
 * argued rather than assumed.
 */

// The two honest labels, one more time.
export type RunMode = 'LIVE_COMPUTATION' | 'VERIFIED_ARTIFACT';

/**
 * Statuses the backend returns. `OK` is the only success; the rest are refusals a reader
 * is owed an explanation for, and the panel renders each of them as an explanation rather
 * than as an empty state.
 */
// PLAIN ENGLISH: "a reader is owed an explanation" is the design in six words. Nothing on
// this list ever produces a blank panel or a spinner that never stops. Every single one
// results in a sentence saying what happened and what to do about it.
export type RunStatus =
  | 'OK'
  | 'FAILED'
  | 'BLOCKED'
  | 'INPUTS_MISSING'
  | 'INSUFFICIENT_DATA'
  | 'PROTECTED'
  | 'NOT_YET_EXECUTED'
  | 'INVALID_INPUT'
  | 'UNKNOWN_MODULE'
  | 'UNKNOWN_ROUTE'
  | 'UNKNOWN_WEEK'
  | 'TIMEOUT'
  // This one exists only on the website's side: the server could not be reached at all.
  | 'BACKEND_UNAVAILABLE'
  | 'FORBIDDEN_ORIGIN'
  | 'UNAUTHORISED'
  | 'METHOD_NOT_ALLOWED'
  | 'PARTIAL';

// One number in a reply.
export interface RunMetric {
  key: string;
  label: string;
  value: number | string | boolean | null;
  // Already formatted by the server, so two pages cannot round the same number differently.
  display: string;
  format: string;
  note: string;
  /** Repository-relative artifact the value was read from. Empty for a live computation. */
  // An empty value here is itself a statement: it means the number was computed fresh.
  source: string;
}

// One set of numbers for a chart.
export interface RunSeries {
  key: string;
  label: string;
  columns: string[];
  rows: (number | string | boolean | null)[][];
  note: string;
  // Whether it was cut short, and how many rows there really are -- so a shortened chart
  // says so instead of quietly passing as complete.
  truncated: boolean;
  total_rows: number | null;
}

// An error, always with a way forward.
export interface RunError {
  code: RunStatus | string;
  reason: string;
  // Never absent. An error with no remedy is a dead end.
  remedy: string;
  detail?: Record<string, unknown>;
}

// A caveat travelling with a result.
export interface RunLimitation {
  id: string;
  title: string;
  scope_note: string;
  status: string;
}

// THE WHOLE REPLY. The exact mirror of the Python shape.
export interface RunResponse {
  backend_version: string;
  module_id: string;
  week: number | null;
  category: string;
  name: string;
  status: RunStatus;
  mode: RunMode;
  // The mode arrives three ways -- code, label and full explanation -- so the website can
  // display and explain it without needing to know anything itself.
  mode_label: string;
  mode_meaning: string;
  experiment_id: string | null;
  dataset: Record<string, unknown>;
  inputs: Record<string, unknown>;
  metrics: RunMetric[];
  series: RunSeries[];
  uncertainty: Record<string, unknown>;
  observations: string[];
  figures: { figure?: string; url?: string | null; caption?: string | null }[];
  tables: { table?: string; caption?: string | null }[];
  // Where it came from, and what bounds it. Both required, both reaching the screen.
  provenance: Record<string, unknown>;
  limitations: RunLimitation[];
  message: string;
  elapsed_s: number;
  error: RunError | null;
}

// The reply for a whole week.
export interface WeekRunResponse {
  backend_version: string;
  week: number;
  title: string;
  question: string;
  summary: string;
  stats_module: string;
  status: RunStatus;
  // Which modules computed and which replayed, so a mixture is visible at a glance.
  modes: Record<string, RunMode>;
  results: Record<string, RunResponse>;
  elapsed_s: number;
  // A plain-English explanation of what a week is, supplied by the server.
  reading: string;
  error?: RunError | null;
}

/** One declared parameter, exactly as `backend/registry.py` will validate it. */
// PLAIN ENGLISH: "exactly as the backend will validate it" -- this is what makes the form
// and the checking one thing. The boxes drawn from this description accept precisely what
// the server accepts, so the website can never offer something the server would reject.
export interface InputSpec {
  name: string;
  kind:
    | 'date'
    | 'int'
    | 'float'
    | 'bool'
    | 'select'
    | 'multiselect'
    | 'symbols'
    | 'text'
    /** Text with a file picker beside it. The service validates it as text. */
    // The distinction is purely about how the box LOOKS. The checking is identical, which
    // is exactly the point made on the Python side: an upload that skipped a check would be
    // an upload that skipped validation.
    | 'document';
  label: string;
  default: unknown;
  note: string;
  options: string[];
  // The allowed range, so the form can stop an impossible value before it is even sent.
  minimum: number | string | null;
  maximum: number | string | null;
  max_items: number | null;
  required: boolean;
}

// How a module can be run.
export interface ExecutionSpec {
  mode: 'LIVE' | 'ARTIFACT';
  is_live: boolean;
  // Whether it is frozen, so the page can explain the refusal before anybody clicks.
  protected: boolean;
  // Roughly how long -- so a slow one can warn first rather than appearing to hang.
  typical_seconds: number;
  artifact_reason: string;
}

// One module, as a week describes it.
export interface WeekModule {
  module_id: string;
  index: number;
  category: string;
  name: string;
  /** What the product calls it. The identifier stays the identifier. */
  product_name: string;
  purpose: string;
  research_question: string;
  route: string;
  icon: string;
  status: string;
  wrapper_status: string;
  experiment_id: string | null;
  limitations: string[];
  outputs: string[];
  // Which research code it is a front for -- traceability all the way to the browser.
  canonical: string[];
  adapter: string;
  protected: boolean;
  analysis: {
    mode: 'LIVE' | 'ARTIFACT';
    is_live: boolean;
    typical_seconds: number;
    summary: string;
    inputs: InputSpec[];
    artifact_reason: string;
  };
}

/**
 * What a week *shows*, declared in the manifest beside the modules it describes.
 *
 * Which figures lead and which series is the picture is a product decision, and putting
 * it here rather than inside a component is what makes it checkable: a test runs each
 * module and asserts every declared key is one the module actually returns.
 */
// PLAIN ENGLISH: this is the "no empty cards" guarantee, and it is genuinely clever.
// A page could simply decide for itself which number to feature. Then if a module stopped
// producing that number, the page would show an empty box -- no error, no warning, and the
// first person to notice would be a visitor.
// Declaring it as DATA means a test can run every module and check that every featured
// number is one the module really returns. The mismatch fails a build instead of appearing
// on a page.
export interface WeekFeatureSpec {
  product_question?: string;
  story?: string;
  headline?: { module: string; metric: string; label: string }[];
  primary_visual?: WeekVisualSpec;
  secondary_visual?: WeekVisualSpec;
}

// How to draw one chart.
export interface WeekVisualSpec {
  module: string;
  series: string;
  // Which columns to use for the labels and the values -- so the chart is described as
  // data rather than being wired up by hand in a component.
  label_column: string;
  value_column: string;
  kind: 'bars' | 'line';
  caption?: string;
}

// Everything about one week.
export interface WeekRecord {
  week: number;
  title: string;
  question: string;
  summary: string;
  feature?: WeekFeatureSpec;
  stats_module: string;
  route: string;
  // The web addresses, built from the module names rather than typed out separately.
  backend_routes: {
    week: string;
    run_week: string;
    modules: Record<string, string>;
    run_module: Record<string, string>;
  };
  input_schema: Record<string, InputSpec[]>;
  output_schema: string[];
  product_view: Record<string, string>;
  research_view: Record<string, string>;
  artifact_sources: Record<string, string[]>;
  execution: Record<string, ExecutionSpec>;
  modules: WeekModule[];
}

/**
 * How each mode is described wherever a result appears.
 *
 * The two are never allowed to look alike. A replayed artifact is a real result and is
 * shown as one; what it is not is a computation that happened because someone pressed a
 * button, and a badge that read the same for both would erase exactly that difference.
 */
// PLAIN ENGLISH: read that second sentence carefully, because it is scrupulously fair in
// both directions. A replayed result is NOT second-rate -- it is a genuine result, shown as
// one. It simply is not a fresh computation, and a badge that read identically for both
// would erase a difference the reader is entitled to see.
export const MODE_COPY: Record<
  RunMode,
  { badge: string; tone: 'live' | 'artifact'; short: string }
> = {
  LIVE_COMPUTATION: {
    badge: 'Live computation',
    tone: 'live',
    short: 'Computed now, on the data you selected.',
  },
  VERIFIED_ARTIFACT: {
    // "Verified" -- a positive word, because it IS verified. Not "cached" or "stale".
    badge: 'Verified experiment result',
    tone: 'artifact',
    // And then perfectly clear about what it is not: "Nothing was computed now."
    short: 'Replayed from a stored, provenance-stamped run. Nothing was computed now.',
  },
};

/** Statuses that are a refusal to be explained rather than a failure to be reported. */
// The same list as the Python side, so the website and the server agree about which
// outcomes are alarming and which are simply the rules working.
export const REFUSALS: ReadonlySet<string> = new Set([
  'PROTECTED',
  'INPUTS_MISSING',
  'INSUFFICIENT_DATA',
  'NOT_YET_EXECUTED',
  'INVALID_INPUT',
  'BLOCKED',
  'BACKEND_UNAVAILABLE',
]);

// The wording for every status a reader might see.
export const STATUS_COPY: Record<string, { label: string; kind: 'ok' | 'refused' | 'failed' }> =
  {
    OK: { label: 'Completed', kind: 'ok' },
    PARTIAL: { label: 'Partly completed', kind: 'refused' },
    // Note the wording throughout. "Selection rejected" -- not "error". It tells the reader
    // what happened and implies the fix, without suggesting anything is broken.
    INVALID_INPUT: { label: 'Selection rejected', kind: 'refused' },
    // Especially good: it names the actual cause, so the reader immediately knows to widen
    // their date range rather than wondering whether the site is faulty.
    INSUFFICIENT_DATA: { label: 'Too little data in that selection', kind: 'refused' },
    INPUTS_MISSING: { label: 'Required data not present', kind: 'refused' },
    PROTECTED: { label: 'Protected artifact', kind: 'refused' },
    NOT_YET_EXECUTED: { label: 'Not yet executed', kind: 'refused' },
    BLOCKED: { label: 'Blocked', kind: 'refused' },
    // "Execution unavailable here" -- says the running is unavailable, not that the site is
    // down. A precise distinction for somebody looking at a page that still works.
    BACKEND_UNAVAILABLE: { label: 'Execution unavailable here', kind: 'refused' },
    // And only these last five are marked as genuine failures.
    UNKNOWN_MODULE: { label: 'No such module', kind: 'failed' },
    UNKNOWN_WEEK: { label: 'No such week', kind: 'failed' },
    UNKNOWN_ROUTE: { label: 'No such endpoint', kind: 'failed' },
    TIMEOUT: { label: 'Timed out', kind: 'failed' },
    FAILED: { label: 'Failed', kind: 'failed' },
  };

// Look up the wording, with a safe fallback.
export function statusCopy(status: string): { label: string; kind: 'ok' | 'refused' | 'failed' } {
  // An unrecognised status shows its own raw name and is treated as a failure. Both are the
  // cautious choice: the reader sees something rather than a blank, and an unknown outcome
  // is not quietly presented as a success.
  return STATUS_COPY[status] ?? { label: status, kind: 'failed' };
}

/** Default request body for a module, taken from its declared schema. */
export function defaultsFor(inputs: InputSpec[]): Record<string, unknown> {
  // PLAIN ENGLISH: fills the form's starting values from the same description the server
  // validates against -- so the default state of every form is guaranteed to be acceptable.
  const out: Record<string, unknown> = {};
  for (const i of inputs) {
    // Settings with no default are simply left out, rather than being sent as null or an
    // empty string, which the server would treat as a value deliberately supplied.
    if (i.default === null || i.default === undefined) continue;
    out[i.name] = i.default;
  }
  return out;
}
