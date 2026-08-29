import { NoData } from '@/components/ui/Primitives';

/**
 * Renderers for the research-angle results produced by
 * `scripts/run_research_angles.py`.
 *
 * Shared because the same measurement appears in more than one research view: the
 * lead-time frontier belongs on both the temporal page and the XAI-adjacent discussion of
 * what the model can see, and duplicating the rendering would let the two drift.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * DISPLAYING THE PROJECT'S MOST UNCOMFORTABLE FINDINGS.
 *
 * Every section below shows a result that a less honest project would have quietly left
 * out. Read the headings in order and you get a list of things that did not work:
 *   * detection is late, not early;
 *   * one explanation method is unstable;
 *   * the clever weighting shows no advantage on the headline metric;
 *   * regime conditioning underperforms;
 *   * and several comparisons could never have detected a difference anyway.
 *
 * The components are SHARED for the usual reason: the same finding appears on more than one
 * page, and two copies of a renderer would eventually show the same result two different
 * ways.
 */

// `any` here because these results come from a research script whose shape varies by
// experiment. A stricter type would have to be updated every time an experiment gained a
// field -- and the alternative is a wall of type-checking noise around data that is only
// being displayed.
type Angles = Record<string, any>;

// A simple two-column table of labels and values.
export function KeyValue({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    // The wrapper scrolls sideways on a narrow screen rather than stretching the page.
    <div className="tableWrap">
      <table>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              {/* A fixed label width, so several of these tables on one page line up with
                  each other rather than each choosing its own column width. */}
              <th style={{ width: 260 }}>{k}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// A general results table.
export function AngleTable({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: { key: string; label: string; num?: boolean; digits?: number }[];
}) {
  // No rows: says so plainly rather than rendering an empty grid that would look like a
  // finding of zero.
  if (!rows?.length) return <p className="muted small">No rows.</p>;
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              // Numeric columns are right-aligned, so digits line up down the column.
              <th key={c.key} className={c.num ? 'num' : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => {
                const v = r[c.key];
                const text =
                  typeof v === 'number'
                    ? Number.isFinite(v)
                      // A real number, to the requested precision.
                      ? v.toFixed(c.digits ?? 4)
                      // AND AN INFINITY OR NaN BECOMES "n/a" -- never a monstrous number
                      // sitting in a results table looking like a measurement.
                      : 'n/a'
                    : v === null || v === undefined
                      // A missing value likewise. Three different absences, one honest
                      // display, and never a zero.
                      ? 'n/a'
                      : String(v);
                return (
                  <td key={c.key} className={c.num ? 'num' : undefined}>
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// FINDING 1: is the lateness a choice, or a limit?
export function LeadTimeSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N03-1'];
  if (!a) return <NoData what="Lead-time analysis" />;
  const r = a.frontier_range ?? {};
  return (
    <section>
      <h2>Detection timing (EXP-N03-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        {/* The question stated before the answer: the headline number cannot tell you
            whether lateness is a tuning choice or a property of the evidence itself. */}
        The headline lead-time number cannot say whether lateness is a tuning choice or a
        property of the evidence. Sweeping the entry threshold answers it.
      </p>
      <KeyValue
        rows={[
          [
            // AND THE ANSWER IS BLUNT. Not "limited early detection" but, where it applies,
            // "no — none across the sweep". Meaning: at no setting anywhere in the range
            // does this system detect anything early. That is the strongest possible form
            // of the negative finding, and it is the one printed.
            'Any operating point with positive lead time',
            a.any_positive_lead_operating_point ? 'yes' : 'no — none across the sweep',
          ],
          [
            // The RANGE across the whole sweep, not one number -- so a reader sees the
            // whole trade-off curve rather than a single chosen point on it.
            'Median lead time range',
            `${r.median_lead_time_min} to ${r.median_lead_time_max} sessions`,
          ],
          [
            'Window precision range',
            `${(r.window_precision_min ?? 0).toFixed(3)} to ${(r.window_precision_max ?? 0).toFixed(3)}`,
          ],
        ]}
      />

      <h3>Block lead and lag</h3>
      <p className="small muted">
        {/* The method explained before the table, including how to read the sign. */}
        Cross-correlation of each block score against the episode indicator, per
        instrument and averaged. Positive lag means the block moves first.
      </p>
      <AngleTable
        rows={a.block_lead_lag ?? []}
        columns={[
          { key: 'block', label: 'Block' },
          { key: 'peak_lag_sessions', label: 'Peak lag', num: true, digits: 0 },
          { key: 'peak_correlation', label: 'Peak corr', num: true, digits: 3 },
          // The correlation at zero lag, so a reader can see whether the "peak" is
          // meaningfully better than no shift at all.
          { key: 'correlation_at_zero', label: 'Corr at lag 0', num: true, digits: 3 },
          // And the plain-English reading, so nobody has to remember which sign means what.
          { key: 'interpretation', label: 'Reading' },
        ]}
      />

      {a.lifecycle?.status === 'OK' ? (
        <>
          <h3>Lifecycle sub-tasks scored separately</h3>
          <p className="small muted">
            {/* The reasoning: three different jobs of three different difficulties, and one
                combined score describes none of them. */}
            Onset, peak and resolution are different problems with different difficulty.
            Collapsing them into one detection score hides that.
          </p>
          <AngleTable
            // Only onset and resolution -- peak is deliberately absent, for the reason the
            // note below gives.
            rows={[a.lifecycle.onset, a.lifecycle.resolution].filter(Boolean)}
            columns={[
              { key: 'task', label: 'Task' },
              { key: 'n', label: 'n', num: true, digits: 0 },
              { key: 'median_error_days', label: 'Median error (days)', num: true, digits: 1 },
              // The average SIZE of the error as well as the average error -- so early and
              // late mistakes cannot cancel into a flattering zero.
              { key: 'mean_abs_error_days', label: 'Mean abs error', num: true, digits: 1 },
              // The most practically useful column: what fraction were within three days.
              { key: 'within_3_days', label: 'Within 3 days', num: true, digits: 3 },
            ]}
          />
          {/* The note explaining why peak timing is not scored -- the measurement would
              mostly be measuring noise. Declining to report, and saying why. */}
          <p className="small muted">{a.lifecycle.note}</p>
        </>
      ) : null}
    </section>
  );
}

// FINDING 2: is the model's confidence worth anything?
export function CalibrationSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-L10-1'];
  if (!a) return null;
  return (
    <section>
      <h2>Calibration under uncertainty (EXP-L10-1)</h2>
      <AngleTable
        // Only the rows that could actually be measured -- and the INSUFFICIENT ones were
        // recorded upstream rather than silently dropped, so nothing is lost.
        rows={(a.by_uncertainty ?? []).filter((r: any) => r.status === 'OK')}
        columns={[
          { key: 'bucket_low', label: 'Uncertainty from', num: true, digits: 3 },
          { key: 'bucket_high', label: 'to', num: true, digits: 3 },
          { key: 'n', label: 'n', num: true, digits: 0 },
          { key: 'ece', label: 'ECE', num: true },
          { key: 'brier', label: 'Brier', num: true },
          { key: 'auprc', label: 'AUPRC', num: true },
        ]}
      />
      <p className="small">
        {/* A POSITIVE finding, and explained rather than merely stated: the model's
            calibration gets worse exactly where it says it is unsure. That is precisely what
            an honest uncertainty estimate should do -- it is the model correctly knowing
            where it is unreliable. */}
        <strong>Slope of ECE against uncertainty:</strong>{' '}
        {a.ece_slope_vs_uncertainty?.toFixed?.(3) ?? 'n/a'} — calibration degrades exactly
        where the model reports being unsure, which is the behaviour an uncertainty
        estimate should show.
      </p>
      <p className="small muted">
        {/* And immediately after the good news, the limitation: whether coverage could be
            measured at all on this dataset, with the reason if not. */}
        <strong>Coverage:</strong>{' '}
        {a.coverage_measurable ? 'measurable' : 'NOT MEASURABLE on this dataset'}.{' '}
        {a.coverage_note}
      </p>
    </section>
  );
}

// FINDING 3: the arm that looked useless, judged on the right measure.
export function SelectiveRiskSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N04-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      <h2>Selective risk (EXP-N04-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        {/* A genuinely interesting result, and honestly framed. The uncertainty-weighted
            method shows no advantage on the headline metric. But that metric does not match
            what the method is FOR. Judged on the measure that does -- error rate once the
            least certain cases are set aside -- the ordering reverses.
            Note it does not claim the method is therefore better. It reports that the answer
            depends on which question you ask, which is the honest finding. */}
        The uncertainty-weighted combination arm shows no AUPRC advantage. Judged on the metric
        that matches its purpose — error rate when the least certain rows are set aside —
        the ordering reverses.
      </p>
      <AngleTable
        rows={a.table ?? []}
        columns={[
          { key: 'coverage', label: 'Coverage', num: true, digits: 2 },
          // Both methods side by side, and the difference -- so a reader can see the
          // reversal happening rather than being told about it.
          { key: 'selective_risk_static', label: 'Static', num: true },
          { key: 'selective_risk_unc', label: 'Uncertainty-weighted', num: true },
          { key: 'risk_delta', label: 'Delta', num: true },
        ]}
      />
      <p className="small muted">{a.note}</p>
    </section>
  );
}

// FINDING 4: could this study have detected a difference at all?
export function PowerSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-L12-1'];
  if (!a) return null;
  return (
    <section>
      <h2>Statistical power (EXP-L12-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        {/* The metal-detector argument, on the page. A "no difference" result means nothing
            unless the study could have found a difference had one existed. */}
        A non-significant difference is only informative if the study could have detected
        a difference worth caring about. The minimum detectable effect is the
        bootstrap interval half-width at the full episode count.
      </p>
      <AngleTable
        rows={a.comparisons ?? []}
        columns={[
          { key: 'arm', label: 'Comparison' },
          // "REPORTED AS" -- what the project previously said about this comparison. So a
          // reader can see the earlier claim next to the evidence that it was never
          // measurable. That is a project checking its own past statements in public.
          { key: 'prior_label', label: 'Reported as' },
          {
            key: 'minimum_detectable_effect',
            label: 'Min detectable effect',
            num: true,
            digits: 6,
          },
          { key: 'observed_difference', label: 'Observed', num: true, digits: 6 },
          // THE VERDICT COLUMN: was this comparison capable of telling us anything at all.
          { key: 'informative', label: 'Informative' },
          { key: 'scaling_exponent', label: 'Scaling exponent', num: true, digits: 3 },
        ]}
      />
      <p className="small muted">
        {/* The textbook value given for comparison, and what agreement with it would mean --
            so the last column can be interpreted rather than merely read. */}
        The textbook exponent is -0.5. Measured exponents near it indicate the bootstrap
        is behaving as expected under clustering.
      </p>
    </section>
  );
}

// FINDING 5: an explanation method that fails its own test.
export function LimeStabilitySection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N01-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      <h2>Explanation stability against cost (EXP-N01-1)</h2>
      <AngleTable
        rows={a.table ?? []}
        columns={[
          { key: 'n_perturbations', label: 'Perturbations', num: true, digits: 0 },
          { key: 'sign_consistency', label: 'Sign consistency', num: true, digits: 3 },
          // The pass mark NAMED in the column heading -- 0.80 -- so the bar is visible
          // beside the score rather than living in a document somewhere.
          { key: 'passes_threshold', label: 'Passes 0.80' },
          {
            key: 'spearman_vs_occlusion',
            label: 'Rank corr vs occlusion',
            num: true,
            digits: 3,
          },
          // The COST, alongside the quality. A method that works only at a price nobody can
          // pay is a different proposition from one that works.
          { key: 'seconds_per_run', label: 'Seconds', num: true, digits: 3 },
        ]}
      />
      <p className="small">
        {/* AND THE SENTENCE IN BOLD IS THE MOST VALUABLE THING ON THIS PAGE:
            "stability is not agreement."
            The method CAN be made stable -- give it enough work and it repeats itself. But
            its answers still disagree completely with a different explanation method.
            So two methods can each be perfectly reproducible and still tell you different
            things about the same model. Reproducibility is not correctness.
            That is a subtle and genuinely useful insight, and most projects would have
            reported the stability figure and stopped. */}
        Crosses the pre-declared threshold at {a.crosses_threshold_at ?? 'n/a'}{' '}
        perturbations, still cheaper than occlusion (
        {a.occlusion_seconds?.toFixed?.(3)} s). Its rank correlation against occlusion
        stays near zero throughout: <strong>stability is not agreement</strong>. Two
        methods can each be reproducible and still rank features differently.
      </p>
    </section>
  );
}

// FINDING 6: WHY the clever idea did not work.
export function RegimeSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N02-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      {/* The heading is "WHY regime conditioning underperforms" -- not merely that it does.
          Reporting a negative result is good; investigating the cause is better, and far
          rarer. */}
      <h2>Why regime conditioning underperforms (EXP-N02-1)</h2>
      <KeyValue
        rows={[
          [
            'Gap trend per additional episode cluster',
            a.gap_trend_per_cluster?.toExponential?.(2) ?? 'n/a',
          ],
          [
            // AND THE DIAGNOSIS: the gap narrows as the sample grows, which is what you
            // would expect if the problem is having too little data per market mood rather
            // than the idea itself being wrong.
            // That is a hypothesis about the cause, stated so it could be tested and could
            // turn out to be false.
            'Gap narrows as sample grows',
            a.gap_shrinks_with_sample ? 'yes — consistent with variance inflation' : 'no',
          ],
          [
            // The raw counts per mood, so a reader can see the thinness for themselves.
            'Episodes per regime (validation)',
            JSON.stringify(a.episodes_per_regime_validation ?? {}),
          ],
        ]}
      />
      {/* And the rule for interpreting all of it, supplied by the analysis rather than
          composed here. */}
      <p className="small muted">{a.interpretation_rule}</p>
    </section>
  );
}
