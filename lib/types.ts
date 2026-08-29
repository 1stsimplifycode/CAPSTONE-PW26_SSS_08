/** Shared types. These mirror the Python contracts under `research/`.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SHAPES. This file describes what every piece of information LOOKS LIKE.
 *
 * It contains no calculations and does nothing when the program runs. It is a set of
 * descriptions: "a risk assessment has a company name, a date, a risk number..." and so on.
 *
 * WHY BOTHER? Because the computer can then CHECK. If somewhere in the site a piece of code
 * asks for `assessment.instrumnet` (a typo), or treats the date as a number, that mistake
 * is caught the moment it is written -- not by a visitor months later staring at a blank box.
 *
 * "THESE MIRROR THE PYTHON CONTRACTS" is the important half of the first line. The research
 * half of this project is written in Python; the website in TypeScript. Two different
 * languages that must agree exactly about the shape of everything passing between them.
 * These descriptions are the website's copy of that agreement, deliberately kept in step
 * with the Python originals -- so if the research adds a field, the website is told.
 */

// The stages of trouble. Exactly the same eight as the Python state machine, and in the
// same order.
export type RiskState =
  | 'NORMAL'
  | 'EARLY_WARNING'
  | 'EMERGING'
  | 'ACTIVE'
  | 'ESCALATING'
  | 'PEAK'
  | 'RESOLVING'
  | 'RESOLVED';

// The same list again, but as an ORDERED list rather than a set of choices -- so a chart or
// a legend can walk through them in the right sequence rather than inventing an order.
export const RISK_STATE_ORDER: RiskState[] = [
  'NORMAL',
  'EARLY_WARNING',
  'EMERGING',
  'ACTIVE',
  'ESCALATING',
  'PEAK',
  'RESOLVING',
  'RESOLVED',
];

/**
 * Product-facing wording for each state. The lifecycle is described in the vocabulary of
 * observation — onset, escalation, peak, resolution — and never in the vocabulary of
 * transactions. A state is a statement about evidence over time, not an instruction.
 */
// PLAIN ENGLISH: read every phrase below and notice what is absent. Not one of them says
// "sell", "avoid", "risky investment" or anything a person could act on directly.
// They all describe EVIDENCE: what was observed, and how it changed. That is the difference
// between "here is what we can see" and "here is what you should do", and the whole project
// stays on the first side of it -- right down to the words in a coloured label.
export const RISK_STATE_COPY: Record<RiskState, { label: string; meaning: string }> = {
  NORMAL: { label: 'Normal', meaning: 'No elevated integrity-risk evidence.' },
  EARLY_WARNING: {
    // Called "Watch" rather than "Warning" -- a smaller word for a smaller claim.
    label: 'Watch',
    meaning: 'Evidence is above background but has not persisted.',
  },
  EMERGING: {
    label: 'Emerging',
    // Note it describes the RULE that fired ("persisted long enough"), not a conclusion.
    meaning: 'Evidence has persisted long enough to open a risk window.',
  },
  ACTIVE: { label: 'Active', meaning: 'The risk window is open and stable.' },
  ESCALATING: { label: 'Escalating', meaning: 'Evidence is strengthening.' },
  PEAK: { label: 'Peak', meaning: 'The strongest point of this risk window.' },
  RESOLVING: { label: 'Resolving', meaning: 'Evidence is receding.' },
  RESOLVED: { label: 'Resolved', meaning: 'The risk window has closed.' },
};

// The colour for each stage.
export const RISK_STATE_COLOR: Record<RiskState, string> = {
  // Grey for normal, blue for a mild watch, then amber through to progressively deeper reds
  // as things worsen -- so the seriousness is legible before anybody reads a word.
  NORMAL: '#4d4d4d',
  EARLY_WARNING: '#56b4e9',
  EMERGING: '#e69f00',
  ACTIVE: '#d55e00',
  ESCALATING: '#b22222',
  // The darkest red for the worst point.
  PEAK: '#7a0000',
  // And greens and blues for recovery.
  RESOLVING: '#009e73',
  RESOLVED: '#0072b2',
  // These particular shades are a well-known colour-blind-safe set, chosen so the chart is
  // readable by the roughly one person in twelve who cannot reliably tell red from green.
};

/** The evidence blocks the panel carries. One learner is fitted per block. */
// The four families of evidence, exactly matching the Python side.
export type FeatureBlock =
  | 'market'
  | 'microstructure'
  | 'regime'
  | 'propagation';

/** One instrument-day assessment. Deliberately carries no actionable field. */
// PLAIN ENGLISH: "deliberately carries no actionable field" -- there is no target price, no
// recommendation, no position size. The shape itself makes advice impossible to express,
// which is a far stronger guarantee than a rule asking people not to add one.
export interface RiskAssessment {
  instrument: string;
  date: string;
  // The risk score, 0 to 1.
  integrityRisk: number;
  // How unsure we are of it -- always travelling beside it, never separable.
  uncertainty: number;
  // And how much of the evidence we actually had.
  coverage: number;
  riskState: RiskState;
  // Which market mood, if known. `?` and `| null` together mean it may be absent or
  // explicitly unknown -- both honest, and different from zero.
  regime?: number | null;
  // How much each family contributed, and how much each was trusted. Optional, and
  // `Partial` means not every family need appear -- an absent family is simply absent
  // rather than being recorded as a zero contribution.
  blockContribution?: Partial<Record<FeatureBlock, number>>;
  blockWeight?: Partial<Record<FeatureBlock, number>>;
}

// One episode of trouble.
export interface RiskWindow {
  instrument: string;
  tEntry: string;
  // The end date CAN be null -- for an episode that never finished. The type itself
  // enforces the honesty: any code using this is forced to handle the "we do not know"
  // case rather than being able to assume an ending.
  tExit: string | null;
  tPeak: string;
  peakScore: number;
  // And the flag saying it was still running when we stopped watching.
  censored: boolean;
}

// One piece of evidence.
export interface EvidenceItem {
  block: FeatureBlock;
  // The two times from the point-in-time contract: when it happened, and when we could have
  // known it. Both carried right through to the interface.
  eventTime: string;
  knowledgeTime: string;
  source: string;
  // What we are legally allowed to do with it -- so the display can show a link rather than
  // a copy where that is all the licence permits.
  licenceStatus: string;
  summary: string;
  // Two different kinds of link: one to embed in a frame, one merely to point at. Which is
  // available depends on the licence, which is why both are optional.
  embedUrl?: string;
  referenceUrl?: string;
}

// One experiment's result.
export interface ExperimentRecord {
  experimentId: string;
  arm: string;
  status: string;
  combiner: string;
  blocks: string;
  // All the measures optional, because a failed experiment has none of them -- and the
  // shape says so rather than forcing a fake zero.
  auprc?: number;
  auroc?: number;
  f1?: number;
  ece?: number;
  // And the interval, so a number is never shown without its uncertainty.
  ciLow?: number;
  ciHigh?: number;
}

// One statistical comparison.
export interface StatisticRecord {
  arm: string;
  comparison: string;
  // The effect size FIRST, then the p-values -- the same ordering discipline as the Python
  // side, where "how big" outranks "how surprising".
  deltaAuprc: number;
  pValue: number | null;
  // The multiple-comparisons-corrected value, carried alongside the raw one so a reader can
  // see how much the correction mattered.
  adjustedP: number | null;
  significant: boolean;
  // And the test's name and description, so a p-value never appears without its method.
  test: string;
  description: string;
}

// One chart, with its full provenance.
export interface FigureRecord {
  figureId: string;
  number: string | null;
  title: string;
  caption: string;
  // Whether it belongs in the paper, the appendix, or is internal only.
  placement: 'MAIN' | 'SUPPLEMENTARY' | 'INTERNAL';
  // WHICH RUN MADE IT, at WHICH code version, from WHICH data, by WHICH script. Four fields
  // that together make any chart traceable back to the exact work that produced it.
  experimentId: string;
  runId: string;
  commit: string | null;
  sourceData: string;
  generationScript: string;
  outputFormats: string[];
}

// Where one data source came from and what may be done with it.
export interface ProvenanceRow {
  source: string;
  block: string;
  licence: string;
  coverage: string;
  status: string;
}

// How complete one family of evidence is.
export interface CoverageSummary {
  block: FeatureBlock | string;
  coverage: number;
  status: string;
  note?: string;
}

/** The universe actually driving the product, with its provenance. */
export interface UniverseInfo {
  id: string;
  name: string;
  // Which KIND of universe, as a fixed choice. This is what stops the honest stand-in ever
  // being mistaken for real index membership -- they are different values here, and the
  // display can word each differently.
  kind: 'point_in_time_proxy' | 'static_list' | 'index_membership';
  effectiveDate: string | null;
  datasetVersion: string;
  memberCount: number;
  // The survivorship-bias evidence: how many companies were EVER members, how often the
  // list was redone, and how much it changed each time. If the first is far larger than the
  // member count, the list genuinely churned.
  distinctMembersEver: number | null;
  rebalances: number | null;
  meanEntriesPerRebalance: number | null;
  // An explicit yes/no, so no page has to infer it from the kind.
  isIndexMembership: boolean;
  // And the warning, carried as a required field -- so a universe can never be displayed
  // without whatever caveat belongs to it.
  caveat: string;
}

/** Statistical grouping used in place of sectors, which are not licence-clear. */
// PLAIN ENGLISH: we would like to group companies by industry. That list is not ours to
// use. So companies are grouped by how they actually move together instead -- and the name
// of the field says "cluster", not "sector", so the substitution is visible.
export interface ClusterInfo {
  id: string;
  label: string;
  members: string[];
  meanAbsCorrelation: number | null;
  // WHAT THE GROUPING IS BASED ON, in words. Without this a reader would reasonably assume
  // industry, which it is not.
  basis: string;
}

// -- research: limitations, claims, angles ------------------------------------------------

// The precise result vocabulary, exactly matching the Python register -- so "not measured"
// and "not supported" stay distinguishable all the way to the screen.
export type ResearchStatus =
  | 'SUPPORTED'
  | 'PARTIAL'
  | 'NOT_SUPPORTED'
  | 'NOT_RUN'
  | 'NOT_MEASURED'
  | 'BLOCKED'
  | 'OPEN_QUESTION'
  | 'FUTURE_VALIDATION'
  | 'FAILED_SANITY_CHECK'
  | 'MEASURED';

// How each status should LOOK.
export const STATUS_TONE: Record<ResearchStatus, 'good' | 'warn' | 'bad' | 'neutral'> = {
  // Green: the evidence supports it.
  SUPPORTED: 'good',
  MEASURED: 'good',
  // Amber: partly, or still open.
  PARTIAL: 'warn',
  OPEN_QUESTION: 'warn',
  FUTURE_VALIDATION: 'warn',
  // GREY, not red. This is the important line. "We never measured it" and "we could not run
  // it" are not failures -- they are absences. Colouring them red would tell a reader
  // something went wrong, when in fact nothing was ever attempted.
  NOT_MEASURED: 'neutral',
  NOT_RUN: 'neutral',
  BLOCKED: 'neutral',
  // Red is reserved for the two that genuinely are bad news: we checked and it did not hold,
  // or it failed a check designed to catch nonsense.
  NOT_SUPPORTED: 'bad',
  FAILED_SANITY_CHECK: 'bad',
};

// One designed experiment -- the same compulsory form as the Python register.
export interface ExperimentSpec {
  id: string;
  hypothesis: string;
  independent_variable: string;
  dependent_variable: string;
  control: string;
  treatment: string;
  dataset: string;
  evaluation_period: string;
  metrics: string[];
  statistical_test: string;
  // What we would conclude from each outcome, written before running.
  expected_interpretation: string;
  // And the honest list of ways it could still mislead.
  threats_to_validity: string[];
  status: ResearchStatus;
  required_data: string[];
  // Null until it has genuinely run -- so a plan can never be displayed as a result.
  result_artifact: string | null;
}

// One open question.
export interface ResearchQuestion {
  id: string;
  question: string;
  limitation_id: string;
  status: ResearchStatus;
  experiments: ExperimentSpec[];
  current_evidence: string | null;
  // Kept separate from the evidence, so partial progress never reads as a finished answer.
  what_remains_unresolved: string | null;
}

// One limitation, complete with everything that follows from it.
export interface LimitationRecord {
  id: string;
  title: string;
  category: string;
  severity: string;
  description: string;
  why_it_exists: string;
  current_status: ResearchStatus;
  current_substitute: string | null;
  // Both sides, always: what this stops us claiming, and what still stands.
  invalidated_claims: string[];
  still_valid: string[];
  research_questions: ResearchQuestion[];
  required_data: string[];
  future_validation: string;
  // The phrases the automatic checker blocks -- carried to the website too, so the
  // interface can show a reader exactly which wordings are forbidden and why.
  forbidden_phrasings: string[];
  scope_note: string;
}

// One claim the project makes.
export interface ClaimRecord {
  id: string;
  claim: string;
  status: ResearchStatus;
  // How far it reaches -- see the labels below.
  scope: string;
  // The evidence, the data and the experiment behind it. A claim is never displayed alone.
  evidence: string;
  dataset: string;
  experiment: string;
  limitations: string[];
  // AND EXAMPLES OF HOW IT WOULD BE OVERSTATED. Unusual and admirable: the project writes
  // down the wrong version of its own claim, so a reader can see exactly where the line is.
  overclaim_examples: string[];
  figure_ids: string[];
  note: string;
}

// The plain-English names for how far a claim reaches.
export const SCOPE_LABEL: Record<string, string> = {
  // Weakest first, and the labels do the work. "Synthetic-validation result" tells a reader
  // immediately that this was measured on painted-in episodes -- so the caveat is in the
  // label itself, not in a footnote they might not reach.
  SYNTHETIC_VALIDATION: 'Synthetic-validation result',
  VALIDATION: 'Validation result',
  // The strongest: measured on data never used for anything else.
  OUT_OF_SAMPLE_HOLDOUT: 'Out-of-sample holdout result',
  // Proved by argument rather than measured.
  ANALYTIC: 'Analytic result',
  // A property of the software, not a finding about markets.
  ENGINEERING: 'Engineering property',
};

// The four-way breakdown of what each family of evidence contributes.
export interface BlockInfoRow {
  block: string;
  // Every field nullable, because each can genuinely be unmeasurable -- and null shows as
  // "n/a" rather than as a zero that would read as "contributes nothing".
  total_auprc: number | null;
  unique: number | null;
  redundant: number | null;
  conflict_rate: number | null;
  missing_rate: number | null;
}

/**
 * One instrument's risk trajectory across the analysis window.
 *
 * The arrays are parallel and share an index: `dates[i]`, `risk[i]`, `phase[i]` and
 * `state[i]` all describe the same session. `changePoints` holds indices into them.
 */
// PLAIN ENGLISH: "parallel arrays" means several lists that line up position by position.
// Position 5 of the dates, position 5 of the risks and position 5 of the states all
// describe the same day.
// It is compact and fast to draw, and it has one danger: sort one list without the others
// and everything silently misaligns, with no error anywhere. Hence the docstring spelling
// out the arrangement in full -- so nobody touches one list on its own.
export interface LifecycleTrajectory {
  symbol: string;
  n_sessions: number;
  dates: string[];
  // Nullable entries, for days where a value could not be computed. A gap in the line,
  // rather than a zero that would draw as a dramatic crash to the axis.
  risk: (number | null)[];
  uncertainty: (number | null)[];
  phase: string[];
  state: string[];
  band: string[];
  // Positions in the lists above where the behaviour changed noticeably -- so the chart can
  // mark the turning points.
  change_points: number[];
  first_date: string;
  last_date: string;
  final_band: string;
  final_risk: number | null;
}
