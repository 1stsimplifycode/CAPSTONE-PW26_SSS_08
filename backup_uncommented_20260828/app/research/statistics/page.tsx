import {
  CalibrationSection,
  LeadTimeSection,
  PowerSection,
  RegimeSection,
  SelectiveRiskSection,
} from '@/components/research/AngleSections';
import { NoData } from '@/components/ui/Primitives';
import { getResearchAngles } from '@/lib/data';

export const dynamic = 'force-static';

export default async function StatisticsPage() {
  const b = await getResearchAngles();
  const angles = (b.meta?.results ?? {}) as Record<string, any>;

  return (
    <>
      <h1>Statistics</h1>
      <p className="lede">
        The analyses that turn reported boundaries into measurements. Every one of these
        was runnable with data already on disk, so leaving them unrun would have meant
        publishing a limitation where a result was available.
      </p>

      {!b.dataAvailable || Object.keys(angles).length === 0 ? (
        <NoData
          what="Research-angle analyses"
          note={
            b.note ??
            'Run python scripts/run_research_angles.py, then python scripts/export_app_data.py.'
          }
        />
      ) : (
        <>
          <LeadTimeSection angles={angles} />
          <CalibrationSection angles={angles} />
          <SelectiveRiskSection angles={angles} />
          <PowerSection angles={angles} />
          <RegimeSection angles={angles} />
        </>
      )}

      <section className="boundary">
        <h3>Method notes</h3>
        <ul>
          <li>
            Bootstraps resample whole episodes, not rows: instrument-days inside one
            episode are not independent draws.
          </li>
          <li>
            p-values across the ablation family are adjusted by Benjamini-Hochberg at a 5%
            false-discovery rate.
          </li>
          <li>
            Expected calibration error uses equal-mass bins; equal-width bins leave the
            high-confidence bins nearly empty under class imbalance.
          </li>
          <li>
            Where a variable has too few distinct values to bucket, the analysis reports
            NOT MEASURABLE rather than fitting a line to the binning.
          </li>
        </ul>
      </section>
    </>
  );
}
