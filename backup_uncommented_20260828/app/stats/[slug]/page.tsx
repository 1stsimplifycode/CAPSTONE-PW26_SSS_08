import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { ModuleShell } from '@/components/modules/ModuleShell';
import { ModuleRunner } from '@/components/run/ModuleRunner';
import {
  getModuleBySlugOrIndex,
  routeSlugsWithAliases,
} from '@/lib/modules';
import { getModuleExecution } from '@/lib/weeks';

export const dynamic = 'force-static';

/**
 * Every module is prerendered at build time from the exported manifest, so the route set
 * is exactly the module set: a module added to `research_modules.yaml` and exported gets
 * a page, and a route with no module 404s rather than rendering an empty shell.
 */
export async function generateStaticParams() {
  const slugs = await routeSlugsWithAliases('STATS');
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const mod = await getModuleBySlugOrIndex('STATS', slug);
  if (!mod) return { title: 'Module not found — AEGIS-Market' };
  return {
    title: `${mod.name} — AEGIS-Market`,
    description: mod.product.headline,
  };
}

export default async function StatsModulePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const mod = await getModuleBySlugOrIndex('STATS', slug);
  if (!mod) notFound();
  const run = await getModuleExecution(mod.id);
  return (
    <ModuleShell
      module={mod}
      runner={
        run ? (
          <ModuleRunner
            moduleId={mod.id}
            moduleName={mod.name}
            inputs={run.inputs}
            execution={run.execution}
            summary={run.summary}
          />
        ) : undefined
      }
    />
  );
}
