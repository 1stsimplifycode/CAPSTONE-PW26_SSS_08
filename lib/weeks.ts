/**
 * The weekly registry, read from the bundle `scripts/export_modules.py` wrote.
 *
 * Server side only. The registry is the manifest's `weeks:` block passed through
 * `backend/registry.py`, so the schema a form draws itself from is the same schema the
 * backend validates against. Every page that renders controls reads them from here.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SIXTEEN WEEKS, AND WHAT EACH ONE ASKS.
 *
 * AND THE MOST IMPORTANT SENTENCE IS THE SECOND ONE, which describes a genuinely elegant
 * arrangement:
 *
 *     "the schema a form draws itself from is the same schema the backend validates
 *      against."
 *
 * Meaning: the boxes you fill in on the web page, and the rules the server checks your
 * answers against, come from THE SAME DESCRIPTION.
 *
 * Why does that matter? Picture the alternative. The form is written by hand on the
 * website, and the checking rules are written by hand on the server. They agree today.
 * Then somebody widens a date range on the server. The form still offers the old range.
 * Now the website silently forbids something the server would happily accept -- and nobody
 * finds out, because nothing is broken, it is merely wrong.
 * One description, used for both, makes that impossible rather than unlikely.
 */
// The honest file reader.
import { getBundle } from './data';
// The shape of a week's record.
import type { WeekRecord } from './runTypes';

// Pass the types straight through, so anything importing this file gets them too and does
// not need a second import line.
export * from './runTypes';

// Read all sixteen weeks.
export async function getWeeks(): Promise<{
  available: boolean;
  generatedAt: string | null;
  rows: WeekRecord[];
  note?: string;
}> {
  const bundle = await getBundle<WeekRecord>('weeks.json');
  return {
    // `available` requires BOTH that the file was read AND that it actually contains
    // something. A file that exists but is empty is not usable data, and treating it as
    // available would give a page an empty list to render as though it were a finding.
    available: bundle.dataAvailable && bundle.rows.length > 0,
    generatedAt: bundle.generatedAt,
    rows: bundle.rows,
    // The "here is how to produce it" note carried through, so a blank page can explain
    // itself rather than just being blank.
    note: bundle.note,
  };
}

// One week by number.
export async function getWeek(week: number): Promise<WeekRecord | null> {
  const { rows } = await getWeeks();
  return rows.find((r) => r.week === week) ?? null;
}

/** The week a module belongs to, for the cross-link on a module page. */
export async function weekOfModule(moduleId: string): Promise<WeekRecord | null> {
  // The link works in both directions: from a week to its module, and from a module back
  // to its week. So a reader who lands on a module page can always find the question it
  // was built to answer.
  const { rows } = await getWeeks();
  return (
    rows.find((r) => r.stats_module === moduleId) ?? null
  );
}

/**
 * What a module page needs in order to render its run panel.
 *
 * Returns `null` for a module the weekly registry does not cover, which is the correct
 * answer for one: a page cannot offer to run something the backend has no declaration for.
 */
export async function getModuleExecution(moduleId: string): Promise<{
  inputs: WeekRecord['input_schema'][string];
  execution: WeekRecord['execution'][string];
  summary: string;
  week: number;
} | null> {
  // PLAIN ENGLISH: returning null here means the page shows NO RUN BUTTON at all. That is
  // the right outcome. A button offering to run something the server has no description of
  // would fail the moment anybody pressed it -- so the honest thing is not to offer it.
  const week = await weekOfModule(moduleId);
  if (!week) return null;
  const execution = week.execution[moduleId];
  const mod = week.modules.find((m) => m.module_id === moduleId);
  // Both pieces are required. Missing either means we cannot describe the run properly, so
  // again: no button, rather than a half-built one.
  if (!execution || !mod) return null;
  return {
    // THE FORM FIELDS -- the same description the server will check against.
    inputs: week.input_schema[moduleId] ?? [],
    // Whether it can compute live, whether it is frozen, how long it takes.
    execution,
    summary: mod.analysis.summary,
    week: week.week,
  };
}

/**
 * Just enough about a week to name it, and nothing about what it computes.
 *
 * The gated page describes a week it must not reveal. Reading the full registry to do that
 * hands the whole table — every week's headline metrics, series keys and visual
 * declarations — to the renderer, and in development that lands in the page's own payload.
 * No computed value is in there, but a page whose entire job is to withhold week 16 should
 * not be shipping week 16's feature declaration to get its title.
 *
 * So this returns the four fields a title needs and drops the rest before anything renders.
 */
// PLAIN ENGLISH: a subtle and rather sharp piece of thinking.
// A "locked" page has to say something like "Week 16: coming soon". To print that title it
// needs the week's name. The obvious way is to read the whole registry and use one field.
// But "read the whole registry" means the page's data now CONTAINS the whole registry --
// and in development that data is visible to anybody who looks at what the page downloaded.
// So a page whose entire purpose is to withhold week 16 would be quietly shipping week 16's
// whole description in order to print its title. Not the numbers -- but not nothing either.
// The fix is not to hide it better. It is to read a SMALLER FILE that only ever contained
// four harmless fields in the first place.
export interface WeekSummary {
  week: number;
  title: string;
  question: string;
  route: string;
}

export async function getWeekSummaries(): Promise<WeekSummary[]> {
  // Its own bundle, not a projection of the full one. The development server streams the
  // file a server component read into that page's payload, so narrowing the *return* type
  // would not narrow what ships — only reading a smaller file does.
  // PLAIN ENGLISH: and here is why the obvious fix does not work. You might think "just
  // return the four fields" would be enough. It is not. The full file was still READ, and
  // what gets read is what gets sent along with the page -- regardless of how much of it
  // the code then chose to use. Narrowing the return type narrows nothing.
  // Reading a genuinely smaller file is the only thing that changes what ships.
  const bundle = await getBundle<WeekSummary>('week_titles.json');
  return bundle.rows;
}
