// Tools for reading a file from disk, and for building a file path safely.
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

/**
 * The product's capabilities and the week each one joins the demonstration.
 *
 * Read from `public/data/capabilities.json`, which `scripts/export_modules.py` writes from
 * the manifest's `product_capabilities:` block. The bundle carries no active week: which
 * of these are locked depends on the week a run is started at, and that is decided per
 * request. Keeping the two apart is what lets the pages stay statically prerendered while
 * the locks still change with `AEGIS_ACTIVE_WEEK`.
 *
 * Server-side only — it touches the filesystem. The navigation receives the result as a
 * prop rather than importing it, so no client bundle pulls `node:fs` in behind it.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * WHICH FEATURES ARE UNLOCKED YET.
 *
 * The project is presented as a sixteen-week programme, and features appear as the weeks
 * progress. This file holds the list: what each feature is, and which week it arrives.
 *
 * THE CLEVER SEPARATION IN THE MIDDLE PARAGRAPH:
 * This file knows WHEN each feature unlocks. It deliberately does NOT know which week we
 * are currently on. Those are two different things, decided in two different places.
 * Why? Because a website can be built once, in advance, into fast pre-made pages -- but
 * only if nothing in them changes per visitor. If the current week were baked in here, the
 * pages would have to be rebuilt every time it changed. Keeping "when does it unlock" in
 * the pre-built file and "what week is it now" decided per request means the pages stay
 * fast AND the locks still work.
 *
 * "SERVER-SIDE ONLY", and why the last sentence matters.
 * This file reads from a disk. A visitor's web browser has no disk to read and no business
 * having one. If this were imported into browser code, the packaging tool would try to
 * include the file-reading machinery in what it sends to the browser -- which either fails
 * to build or, worse, bloats every visitor's download with tools that cannot work there.
 * So the answer is worked out on the server and handed to the display as a plain value.
 */
// The shape of one feature.
export interface ProductCapability {
  id: string;
  // What to call it, and where it lives on the site.
  name: string;
  href: string;
  // WHICH WEEK IT UNLOCKS. The only timing fact this file holds.
  enabled_from_week: number;
  summary: string;
  /** "nav" for the primary navigation, "analysis" for a section of /analysis. */
  // Where it should appear. The `?` means optional -- a feature that does not say gets a
  // sensible default further down.
  surfaces?: string[];
}

// Read the list of features.
export async function getCapabilities(): Promise<ProductCapability[]> {
  try {
    const raw = await readFile(
      join(process.cwd(), 'public', 'data', 'capabilities.json'),
      'utf-8',
    );
    // `rows` is the envelope every exported bundle uses; a second shape would be a
    // second reader and a test that only covers one of them.
    // PLAIN ENGLISH: every exported file wraps its contents in a "rows" list. Sticking to
    // that one shape everywhere means one way of reading them and one test covering it.
    // Two shapes would mean two readers, and eventually a test that only covers one.
    const parsed = JSON.parse(raw) as { rows?: ProductCapability[] };
    // An empty list if the file has no rows, rather than undefined for the caller to trip on.
    return parsed.rows ?? [];
  } catch {
    // No bundle means the export has not run. The navigation then shows its ordinary
    // entries and no capability progression, which is a smaller product rather than a
    // broken one — and never a locked capability nobody can explain.
    // PLAIN ENGLISH: a nicely reasoned fallback. With no file, the menu simply shows its
    // normal entries and no unlocking story. The site is smaller, and it works.
    // And note the last clause -- the outcome that is specifically avoided. Guessing here
    // could produce a menu item that appears greyed-out and locked for a reason nobody
    // could explain, because the reason was invented. Showing nothing is better than
    // showing an inexplicable lock.
    return [];
  }
}

/** The capabilities that appear on one surface. One registry, filtered, never a second. */
export async function getCapabilitiesOn(surface: string): Promise<ProductCapability[]> {
  // PLAIN ENGLISH: "one registry, filtered, never a second" -- the same rule as everywhere
  // else in this project. There is ONE list of features. Different parts of the site filter
  // it differently. Nobody keeps a second list, which would be a second thing to drift out
  // of step with the first.
  const all = await getCapabilities();
  // `c.surfaces ?? ['nav']` means: use the feature's own declared surfaces, or default to
  // the main navigation if it did not say. A sensible default rather than a crash or an
  // invisible feature.
  return all.filter((c) => (c.surfaces ?? ['nav']).includes(surface));
}
