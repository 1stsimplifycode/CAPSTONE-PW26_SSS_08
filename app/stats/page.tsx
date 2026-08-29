import { ModuleIndex } from '@/components/modules/ModuleLayout';
import { CATEGORY_COPY, listModules } from '@/lib/modules';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE /stats INDEX PAGE: a list of all sixteen statistics modules.
 *
 * Notice how little there is here. The page fetches the list and hands it to a component.
 * It contains no wording of its own, no counts, no layout decisions -- all of that lives in
 * `ModuleIndex`, which the Scenario Lab index also uses.
 * One component, two pages, no chance of the two drifting apart.
 */

// "force-static" means: build this page ONCE, at build time, not per visitor.
// It can be, because the module list only changes when the research is re-exported -- which
// is a rebuild anyway. The result is a page that arrives instantly with no server work.
export const dynamic = 'force-static';

// What a browser tab and a search engine see.
export const metadata = {
  title: 'Statistics modules — AEGIS-Market',
  description:
    'Sixteen modules characterising the data, validating the model against it, and ' +
    'reporting how much of any difference is real.',
};

export default async function StatsIndexPage() {
  // Every module in the STATS family, in a fixed order.
  const modules = await listModules('STATS');
  // AND THE WORDING FROM THE SHARED DEFINITION rather than typed out here. So the label and
  // the introduction on this page are the same ones the navigation and any other surface
  // use -- they cannot disagree.
  const copy = CATEGORY_COPY.STATS;
  return (
    <ModuleIndex
      modules={modules}
      label={copy.label}
      lede={copy.lede}
    />
  );
}
