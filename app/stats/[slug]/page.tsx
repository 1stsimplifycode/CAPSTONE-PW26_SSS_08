import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { ModuleShell } from '@/components/modules/ModuleShell';
import { ModuleRunner } from '@/components/run/ModuleRunner';
import {
  getModuleBySlugOrIndex,
  routeSlugsWithAliases,
} from '@/lib/modules';
import { getModuleExecution } from '@/lib/weeks';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * ONE PAGE THAT SERVES ALL SIXTEEN MODULES.
 *
 * The folder name `[slug]` in square brackets is Next.js's way of saying "this part of the
 * address is a variable". So `/stats/universe` and `/stats/thresholds` both land here, with
 * the last part handed over as `slug`.
 * One file, sixteen pages -- and every module page therefore behaves identically, because
 * there is only one of it.
 */

// Built at build time rather than per visitor.
export const dynamic = 'force-static';

/**
 * Every module is prerendered at build time from the exported manifest, so the route set
 * is exactly the module set: a module added to `research_modules.yaml` and exported gets
 * a page, and a route with no module 404s rather than rendering an empty shell.
 */
// PLAIN ENGLISH: this tells the build system which addresses to make pages for -- and the
// list comes from the module manifest itself.
// So the set of pages IS the set of modules, by construction. Add a module and it gets a
// page automatically. And an address with no module behind it produces a proper "not found"
// rather than an empty page frame with nothing in it, which is what would happen if the
// page were built for any address at all.
export async function generateStaticParams() {
  // Every alias too, so `/stats/01` and `/stats/STATS-01` are built as well as the
  // friendly name. Otherwise those addresses would work but be slow, or not work at all.
  const slugs = await routeSlugsWithAliases('STATS');
  return slugs.map((slug) => ({ slug }));
}

// The tab title and description for each individual module page.
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const mod = await getModuleBySlugOrIndex('STATS', slug);
  // An honest title for a page that does not exist, rather than a blank tab.
  if (!mod) return { title: 'Module not found — AEGIS-Market' };
  return {
    title: `${mod.name} — AEGIS-Market`,
    // The description comes from the module's own headline -- so a link shared on a chat
    // or in search results previews with the module's real summary rather than a generic one.
    description: mod.product.headline,
  };
}

export default async function StatsModulePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  // Resolve by friendly name, formal id, or number -- all three work.
  const mod = await getModuleBySlugOrIndex('STATS', slug);
  // `notFound()` produces a proper 404. Not an empty page, and not a crash.
  if (!mod) notFound();
  // Can this module be run interactively?
  const run = await getModuleExecution(mod.id);
  return (
    <ModuleShell
      module={mod}
      runner={
        // THE RUN PANEL ONLY WHERE THE BACKEND HAS A DECLARATION FOR IT. A module with no
        // declaration simply gets no button -- rather than a button that would fail the
        // moment anybody pressed it.
        run ? (
          <ModuleRunner
            moduleId={mod.id}
            moduleName={mod.name}
            // The form fields, the execution details and the summary all come from that one
            // declaration -- the same one the server validates against.
            inputs={run.inputs}
            execution={run.execution}
            summary={run.summary}
          />
        ) : undefined
      }
    />
  );
}
