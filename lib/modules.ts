/**
 * Reading the exported module bundles.
 *
 * Server-only: it touches the filesystem through `lib/data`. Every type and label lives
 * in `lib/moduleTypes` and is re-exported here, so a server component imports one module
 * and a client component imports the types directly without pulling `node:fs` in with
 * them.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * READING THE LIST OF MODULES, AND FINDING ONE BY WHATEVER NAME SOMEBODY USED.
 *
 * THE SPLIT DESCRIBED IN THE HEADER is a practical necessity rather than fussiness.
 * The SHAPES of things (what a module record looks like) live in a separate file with no
 * file-reading in it. The READING lives here.
 * Why? Because the browser needs to know the shapes -- it displays them -- but must never
 * be handed the file-reading tools, which cannot work there and would bloat every visitor's
 * download. Separating them means each side gets exactly what it can use.
 */
import { getBundle, type Bundle } from './data';
import type {
  ModuleCategory,
  ModuleFigure,
  ModuleTable,
  ResearchModule,
} from './moduleTypes';

// Pass the shapes through, so a server component needs only one import.
export * from './moduleTypes';

// Summary counts that may accompany the module bundle. Every field optional, since an
// older export may not carry all of them.
export interface ModuleMeta {
  n_modules?: number;
  by_category?: Record<string, number>;
  n_figures?: number;
  n_tables?: number;
  // How many numbers could not be resolved -- a quality figure worth surfacing rather than
  // quietly dropping.
  n_unresolved_metrics?: number;
  manifest_version?: string;
}

// Read the full module bundle.
export async function getModules(): Promise<Bundle<ResearchModule>> {
  return getBundle<ResearchModule>('modules.json');
}

// Every module, optionally just one category, in a stable order.
export async function listModules(category?: ModuleCategory): Promise<ResearchModule[]> {
  const bundle = await getModules();
  const rows = category
    ? bundle.rows.filter((m) => m.category === category)
    : bundle.rows;
  // `[...rows]` copies before sorting, so the original order is not disturbed for anything
  // else holding the same list.
  return [...rows].sort((a, b) =>
    // Within a category, by number; across categories, alphabetically. A fixed order means
    // the page looks the same every time rather than shuffling between visits.
    a.category === b.category
      ? a.index - b.index
      : a.category.localeCompare(b.category),
  );
}

/**
 * Resolve a module from the last segment of its route.
 *
 * Routes are short and readable (`/stats/universe`), while manifest slugs are long and
 * descriptive (`universe_survivorship`). Matching on the route segment keeps the URL a
 * product decision and the slug a research one, and lets either change without the other.
 */
// PLAIN ENGLISH: two names for the same thing, on purpose.
// The web address is short and friendly, because people read and share it.
// The internal name is long and precise, because researchers need it to be unambiguous.
// Keeping them separate means the web address can be reworded for clarity without
// disturbing any research reference, and vice versa.
export async function getModuleByRouteSlug(
  category: ModuleCategory,
  routeSlug: string,
): Promise<ResearchModule | null> {
  const rows = await listModules(category);
  // `.split('/').pop()` takes the last piece of the address -- "universe" out of
  // "/stats/universe".
  return rows.find((m) => m.route.split('/').pop() === routeSlug) ?? null;
}

// Every route ending, used to build the pages in advance.
export async function routeSlugs(category: ModuleCategory): Promise<string[]> {
  const rows = await listModules(category);
  // The `!` tells the type checker "this is definitely not empty"; `.filter(Boolean)` then
  // removes any that turned out to be anyway. Belt and braces.
  return rows.map((m) => m.route.split('/').pop()!).filter(Boolean);
}

/** Every figure the export copied into `public/figures/`, with its caption. */
export async function getFigureIndex(): Promise<Bundle<ModuleFigure>> {
  return getBundle<ModuleFigure>('figures_index.json');
}

/** Every generated table, with its caption, source artifact and column list. */
export async function getTableIndex(): Promise<Bundle<ModuleTable>> {
  return getBundle<ModuleTable>('tables_index.json');
}

/** Modules that cite a given figure, so the figure explorer can link back. */
export function modulesCitingFigure(
  modules: ResearchModule[],
  figure: string,
): ResearchModule[] {
  // PLAIN ENGLISH: the link works backwards as well as forwards. From a chart you can find
  // every module that uses it -- so a reader looking at a figure can immediately see what
  // conclusions were drawn from it, rather than having to hunt.
  return modules.filter((m) => m.figures.some((f) => f.figure === figure));
}

// The same, for tables.
export function modulesCitingTable(
  modules: ResearchModule[],
  table: string,
): ResearchModule[] {
  return modules.filter((m) => m.tables.some((t) => t.table === table));
}

/**
 * A module by its route slug, its index, or its identifier.
 *
 * `/stats/data-integrity` is what the product links to: a reader scanning a list of
 * capabilities recognises the name and does not recognise a number. `/stats/01` is what a
 * mentor asks for during a weekly demonstration, and `/stats/STATS-01` is what someone
 * arrives with after reading the manifest. All three resolve to one page rather than to a
 * redirect the reader has to wait through.
 */
// PLAIN ENGLISH: a genuinely thoughtful piece of design, because it starts from who is
// actually typing.
//   A READER browsing the site clicks a friendly name: "data-integrity".
//   A MENTOR in a demonstration says "show me number one": "01".
//   A RESEARCHER who has read the manifest types the formal id: "STATS-01".
// Three different people, three different names, one page. And crucially, all three go
// STRAIGHT there rather than bouncing through a redirect -- which is faster, and avoids the
// address in the bar changing under somebody's cursor mid-click.
export async function getModuleBySlugOrIndex(
  category: ModuleCategory,
  slug: string,
): Promise<ResearchModule | null> {
  const modules = await listModules(category);
  // Trimmed and lower-cased, so stray spaces and capitals do not matter.
  const wanted = slug.trim().toLowerCase();

  // Try the friendly name first, since it is the commonest.
  const byRoute = modules.find((m) => m.route.split('/').pop() === wanted);
  if (byRoute) return byRoute;

  // Then the formal identifier.
  const byId = modules.find((m) => m.id.toLowerCase() === wanted);
  if (byId) return byId;

  // And finally a plain number. The checks are careful: it must be a whole number and it
  // must be positive, so "abc" or "-1" do not reach the lookup.
  const asNumber = Number(wanted);
  if (Number.isInteger(asNumber) && asNumber > 0) {
    return modules.find((m) => m.index === asNumber) ?? null;
  }
  // Nothing matched. A clean null, so the page can show a proper "not found".
  return null;
}

/** Every way a module page may be addressed, for prerendering. */
export async function routeSlugsWithAliases(
  category: ModuleCategory,
): Promise<string[]> {
  // PLAIN ENGLISH: pages are built in advance for speed. Since a module can be reached by
  // several names, EVERY name has to be built -- otherwise "/stats/01" would be slow or
  // broken while "/stats/data-integrity" was instant.
  const modules = await listModules(category);
  // A Set, so a name that appears twice is only built once.
  const slugs = new Set<string>();
  for (const m of modules) {
    const tail = m.route.split('/').pop();
    if (tail) slugs.add(tail);
    // `padStart(2, '0')` makes 1 into "01", so both the padded and natural forms work.
    slugs.add(String(m.index).padStart(2, '0'));
  }
  return [...slugs];
}

/**
 * The modules, named and routable, with no result attached.
 *
 * `listModules` returns every module's exported metrics and series, which the module pages
 * need. A page that only lists what exists does not — and reading the full bundle to build
 * a list puts every module's numbers into that page's payload, including the weeks this
 * demonstration has not reached. Reading a smaller file is what removes the possibility,
 * rather than trusting the bundler to drop what was not rendered.
 */
// PLAIN ENGLISH: the same leak as in weeks.ts, guarded the same way.
// A page that only shows a MENU of modules needs their names, not their results. But
// reading the full file to build that menu means every module's numbers -- including
// unreleased weeks -- travel along with the page.
// And note the last clause: "rather than trusting the bundler to drop what was not
// rendered." The packaging tool is usually clever enough to strip unused data. Usually.
// This does not rely on usually. It reads a smaller file, and then there is nothing to strip.
export interface ModuleIndexRow {
  id: string;
  index: number;
  category: string;
  name: string;
  slug: string;
  route: string;
  icon: string;
  // The friendly name and the friendly question -- everything a menu entry needs, and
  // nothing whatever about results.
  product_name: string;
  product_question: string;
}

export async function listModuleIndex(): Promise<ModuleIndexRow[]> {
  const bundle = await getBundle<ModuleIndexRow>('module_index.json');
  return bundle.rows;
}
