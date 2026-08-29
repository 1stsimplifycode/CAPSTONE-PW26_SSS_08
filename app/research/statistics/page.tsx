import {
  CalibrationSection,
  LeadTimeSection,
  PowerSection,
  RegimeSection,
  SelectiveRiskSection,
} from '@/components/research/AngleSections';
import { NoData } from '@/components/ui/Primitives';
import { getResearchAngles } from '@/lib/data';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE STATISTICS PAGE: five analyses, most of which found something disappointing.
 *
 * The page itself is thin -- it fetches the results and hands them to the five section
 * components. All the interesting reasoning lives in those.
 *
 * What this page adds is the FRAMING, and the method notes at the bottom.
 */

export const dynamic = 'force-static';

export default async function StatisticsPage() {
  const b = await getResearchAngles();
  // `?? {}` so a missing results block becomes an empty object rather than crashing the
  // page -- and the empty case is then handled properly below.
  const angles = (b.meta?.results ?? {}) as Record<string, any>;

  return (
    <>
      <h1>Statistics</h1>
      <p className="lede">
        {/* AN UNUSUALLY POINTED INTRODUCTION, and worth reading closely:
            "leaving them unrun would have meant publishing a limitation where a result was
             available."
            In other words: every one of these analyses COULD have been run with data
            already on the disk. Not running them and instead writing "this is a limitation"
            would have been publishing an excuse in place of an answer that was available
            for the asking.
            That is a standard most projects do not hold themselves to. */}
        The analyses that turn reported boundaries into measurements. Every one of these
        was runnable with data already on disk, so leaving them unrun would have meant
        publishing a limitation where a result was available.
      </p>

      {!b.dataAvailable || Object.keys(angles).length === 0 ? (
        // NOT RUN YET: the honest block with the exact commands, rather than five empty
        // sections that would read as five findings of nothing.
        <NoData
          what="Research-angle analyses"
          note={
            b.note ??
            'Run python scripts/run_research_angles.py, then python scripts/export_app_data.py.'
          }
        />
      ) : (
        <>
          {/* The five analyses. Each is a separate component, shared with other pages, so
              the same finding cannot be presented two different ways in two places. */}
          <LeadTimeSection angles={angles} />
          <CalibrationSection angles={angles} />
          <SelectiveRiskSection angles={angles} />
          <PowerSection angles={angles} />
          <RegimeSection angles={angles} />
        </>
      )}

      <section className="boundary">
        {/* THE METHOD NOTES: four decisions that change the numbers, stated on the page
            rather than buried in code. A reader can disagree with any of them. */}
        <h3>Method notes</h3>
        <ul>
          <li>
            {/* 1. THE DEPENDENCE RULE. Whole episodes, not rows -- because days inside one
                   episode are not independent evidence. */}
            Bootstraps resample whole episodes, not rows: instrument-days inside one
            episode are not independent draws.
          </li>
          <li>
            {/* 2. THE MULTIPLE-COMPARISONS CORRECTION, named and with its rate given. */}
            p-values across the ablation family are adjusted by Benjamini-Hochberg at a 5%
            false-discovery rate.
          </li>
          <li>
            {/* 3. EQUAL-MASS BINS, with the reason: equal-width bins would leave the
                   high-confidence bins nearly empty on a rare-event problem, and the score
                   would then be decided by a handful of points. */}
            Expected calibration error uses equal-mass bins; equal-width bins leave the
            high-confidence bins nearly empty under class imbalance.
          </li>
          <li>
            {/* 4. AND THE REFUSAL: where a variable cannot be bucketed, the analysis reports
                   NOT MEASURABLE rather than "fitting a line to the binning" -- which is a
                   precise description of manufacturing a trend out of an artefact. */}
            Where a variable has too few distinct values to bucket, the analysis reports
            NOT MEASURABLE rather than fitting a line to the binning.
          </li>
        </ul>
      </section>
    </>
  );
}
