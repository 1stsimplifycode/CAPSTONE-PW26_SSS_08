import { ModuleIndex } from '@/components/modules/ModuleLayout';
import { CATEGORY_COPY, listModules } from '@/lib/modules';

export const dynamic = 'force-static';

export const metadata = {
  title: 'Statistics modules — AEGIS-Market',
  description:
    'Sixteen modules characterising the data, validating the model against it, and ' +
    'reporting how much of any difference is real.',
};

export default async function StatsIndexPage() {
  const modules = await listModules('STATS');
  const copy = CATEGORY_COPY.STATS;
  return (
    <ModuleIndex
      modules={modules}
      label={copy.label}
      lede={copy.lede}
    />
  );
}
