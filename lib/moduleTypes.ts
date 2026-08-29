/**
 * Module types and the copy that names them, with no filesystem dependency.
 *
 * Split out from `lib/modules.ts` because the client components — the sidebar, the
 * module card, the shell that switches between the two experiences — need these types
 * and these labels, and importing them from the data module would drag `node:fs` into
 * the browser bundle. Nothing here reads anything; `lib/modules.ts` does the reading and
 * re-exports this file so a server component still has one import.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SHAPE OF A MODULE, AND ALL THE WORDS USED TO DESCRIBE ONE.
 *
 * WHY IT IS A SEPARATE FILE, explained plainly: the visitor's browser needs to know what a
 * module looks like, because it draws them. The browser must NOT be given the file-reading
 * tools, which cannot work there anyway.
 * Put both in one file and the packaging tool would try to send the file-reading machinery
 * to every visitor. Splitting them means the browser gets the descriptions and the words,
 * and the server keeps the reading -- and `lib/modules.ts` passes this file straight
 * through, so a server component still writes only one import line.
 *
 * THE OTHER HALF OF THIS FILE is all the wording -- the labels, and what each one MEANS.
 * Every label below comes with an explanation, because a word like "moderate confidence"
 * means whatever the reader assumes it means unless you say.
 */

// The two families of module.
export type ModuleCategory = 'STATS' | 'SCENARIO';

/** Product vocabulary. Says what a reader can do with the module. */
// Note this is about USABILITY, not correctness.
export type ProductStatus = 'VERIFIED' | 'EXPERIMENTAL' | 'LIMITED' | 'UNAVAILABLE';

/** How far the evidence goes, which is a different question from whether it ran. */
// PLAIN ENGLISH: and this is about STRENGTH OF EVIDENCE. Two separate questions, kept
// apart on purpose: a module can run perfectly and still produce weak evidence, and
// squashing both into one word would hide that.
export type Confidence = 'HIGH' | 'MODERATE' | 'LOW' | 'UNRESOLVED';

// One number a module reports.
export interface ModuleMetric {
  label: string;
  format: string;
  note: string | null;
  /** The declared lookup into an artifact. Shown in Research mode so a reader can check. */
  // PLAIN ENGLISH: this records exactly WHERE in which file the number was fetched from --
  // and it is shown on screen in research mode. So a reader is not asked to trust the
  // number; they are handed the instructions to go and find it themselves.
  expression: string;
  value: number | string | null;
  display: string | null;
  source: string | null;
  /** Set when the artifact does not contain what the expression names. */
  // AND WHEN IT COULD NOT BE FOUND, THE REASON. So a blank on screen says why it is blank,
  // rather than leaving a reader to wonder whether the value is zero or missing.
  unavailable: string | null;
}

// One chart.
export interface ModuleFigure {
  figure: string;
  // Whether the file is actually present in this build. So a page can show "chart not
  // available in this build" rather than a broken image.
  available: boolean;
  url?: string | null;
  caption: string | null;
  // Which data made it, and at which code version -- traceability carried to the screen.
  source_data?: string | null;
  source_dir?: string;
  git_commit?: string | null;
  bytes?: number;
}

// One table.
export interface ModuleTable {
  table: string;
  available: boolean;
  caption: string | null;
  source: string | null;
  rows: number | null;
  path?: string;
  git_commit?: string | null;
  columns?: string[];
}

// One setting a module accepts.
export interface ModuleInput {
  kind: string;
  label: string;
  note: string;
}

// One limitation bounding a module.
export interface ModuleLimitation {
  id: string;
  title: string;
  // The short warning label that gets attached to results.
  scope_note: string;
  status: string;
  description: string;
}

// One claim, with everything needed to check it.
export interface ModuleClaim {
  id: string;
  claim: string;
  status: string;
  scope: string;
  // The full chain: the evidence, the test, the number, the data, the experiment, the
  // files, and the caveats. Seven fields, so a claim can never appear as a bare assertion.
  evidence: string;
  statistical_test: string;
  metric: string;
  dataset: string;
  experiment: string;
  artifacts: string[];
  limitations: string[];
}

// A sample of a data file.
export interface ModulePreview {
  columns: string[];
  rows: (string | number | null)[][];
  // How many rows there really are, and whether this is only part. So a shortened preview
  // announces itself instead of passing as the whole table.
  total_rows: number;
  truncated: boolean;
  path: string;
}

// The record of a module's last run.
export interface ModuleRun {
  at: string | null;
  status: string | null;
  message: string | null;
  elapsed_s: number | null;
  git_commit: string | null;
  runs_recorded: number;
}

// THE FULL SHAPE OF ONE MODULE.
export interface ResearchModule {
  id: string;
  category: ModuleCategory;
  index: number;
  slug: string;
  /** The research name, used wherever the module is cited. */
  name: string;
  /**
   * The name the product experience shows.
   *
   * `STATS-11` is a precise identifier and a useless label; "How confident the signal is"
   * is the reverse. Both are declared in the manifest so they cannot drift, and each is
   * shown where it belongs rather than one standing in for the other.
   */
  // PLAIN ENGLISH: this is exactly right, and it is a mistake nearly every project makes.
  // "STATS-11" is unambiguous and tells a reader nothing.
  // "How confident the signal is" is instantly clear and useless for citing.
  // Rather than compromising on a name that is mediocre at both jobs, there are two names,
  // each perfect at one -- and both declared in one place so they cannot drift apart.
  product_name: string;
  route: string;
  icon: string;
  // THE TWO EXPERIENCES, side by side in one record. The same module, described twice --
  // which is what lets one page carry both without loading anything extra when you switch.
  product: {
    // The plain-reader version.
    headline: string;
    question: string;
    actions: string[];
    observation: string;
    risk: string;
    confidence: Confidence;
    status: ProductStatus;
    visual: string;
    metrics: ModuleMetric[];
    inputs: ModuleInput[];
  };
  research: {
    // The full-detail version: the status, the purpose, the question, the code it fronts,
    // what it reads and writes, what it depends on, its numbers, its data previews, its
    // limitations, its claims and its last run.
    status: string;
    wrapper_status: string;
    purpose: string;
    research_question: string;
    notes: string;
    experiment_id: string | null;
    adapter: string;
    canonical: string[];
    inputs: string[];
    outputs: string[];
    depends_on: string[];
    metrics: ModuleMetric[];
    previews: ModulePreview[];
    limitations: ModuleLimitation[];
    claims: ModuleClaim[];
    last_run: ModuleRun | null;
  };
  figures: ModuleFigure[];
  tables: ModuleTable[];
  // AND THE NUMBERS THAT COULD NOT BE FOUND, each with its reason. Listed explicitly rather
  // than being silently absent -- a missing number is visible, and explained.
  unavailable_metrics: { label: string; reason: string; expression: string }[];
}

// How each family of modules is introduced.
export const CATEGORY_COPY: Record<
  ModuleCategory,
  { label: string; base: string; lede: string }
> = {
  STATS: {
    label: 'Statistics',
    base: '/stats',
    // Note the three verbs, in order: characterise the data, validate against it, and say
    // how much of the difference is real. The third is the one most projects skip.
    lede:
      'Sixteen modules that characterise the data, validate the model against it, and ' +
      'say how much of any difference is real.',
  },
  SCENARIO: {
    label: 'Scenario Lab',
    base: '/scenario',
    // And the caveat is built into the introduction itself: "a counterfactual is not an
    // event". A reader is told what these results are NOT before they read a single one.
    lede:
      'Eight modules that put the fitted models under stated conditions and compare ' +
      'the outcomes. Every condition declares its baseline, its assumption and how its ' +
      'rows were obtained, because a counterfactual is not an event.',
  },
};

// What each confidence level actually MEANS.
export const CONFIDENCE_COPY: Record<Confidence, { label: string; meaning: string }> = {
  HIGH: {
    label: 'High confidence',
    // "stable across seeds" -- the multi-seed check from the research side, surfaced right
    // here in the label's meaning.
    meaning: 'Measured directly, and the measurement is stable across seeds.',
  },
  MODERATE: {
    label: 'Moderate confidence',
    meaning: 'Measured, and bounded by a limitation that changes how far it reaches.',
  },
  LOW: {
    label: 'Low confidence',
    // Precise about WHY it is low: not that the measurement is shaky, but that how the data
    // was built limits what the number can be taken to mean.
    meaning:
      'Measured on data whose construction bounds what the number can be read to mean.',
  },
  UNRESOLVED: {
    label: 'Unresolved',
    // THE BEST SENTENCE ON THIS PAGE: "That is a result, not a gap."
    // The experiment ran properly and could not tell the alternatives apart. That is a
    // genuine finding about the world -- and without this wording a reader would file it
    // under "they did not finish".
    meaning:
      'The experiment ran and did not separate the alternatives. That is a result, ' +
      'not a gap.',
  },
};

// What each product status means -- each one describing exactly what happened.
export const PRODUCT_STATUS_COPY: Record<ProductStatus, string> = {
  VERIFIED: 'Ran, produced its declared outputs, and its research status is supported.',
  EXPERIMENTAL: 'Ran, and its research position is still an open question.',
  LIMITED: 'Ran, and a documented limitation bounds what its result covers.',
  // Note the careful wording: "not present in this build" -- not "broken", not "failed".
  UNAVAILABLE: 'Its outputs are not present in this build.',
};

// The colour tone for each confidence level.
export const CONFIDENCE_TONE: Record<Confidence, 'good' | 'warn' | 'bad' | 'neutral'> = {
  HIGH: 'good',
  // Grey rather than green: moderate is not a warning, and it is not a triumph either.
  MODERATE: 'neutral',
  LOW: 'warn',
  // Amber, not red. An unresolved result is a real finding, and colouring it red would
  // contradict the careful wording above.
  UNRESOLVED: 'warn',
};

// And the tone for each product status.
export const PRODUCT_STATUS_TONE: Record<
  ProductStatus,
  'good' | 'warn' | 'bad' | 'neutral'
> = {
  VERIFIED: 'good',
  EXPERIMENTAL: 'neutral',
  LIMITED: 'warn',
  // The only red on this list -- reserved for "there is genuinely nothing here to show".
  UNAVAILABLE: 'bad',
};
