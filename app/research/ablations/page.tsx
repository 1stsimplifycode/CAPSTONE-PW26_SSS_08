import { NoData, ScoreBar, StatCard } from '@/components/ui/Primitives';
import { Bars } from '@/components/visualization/Sparkline';
import { fmt, getExperiments, getBlockInfo, getStatistics, signed } from '@/lib/data';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE ABLATIONS PAGE: what happens when you take each ingredient out.
 *
 * Three tables, and the third is the one that matters most:
 *   1. THE BLOCK DECOMPOSITION -- why removing something made no difference.
 *   2. THE ARMS, ranked.
 *   3. THE STATISTICAL TESTS -- whether any of the differences are real.
 *
 * And the closing note is one of the most important paragraphs on the entire site, because
 * it explains how to read a result that found nothing. It is commented at length below.
 */

export const dynamic = 'force-static';

export default async function AblationsPage() {
  const experiments = await getExperiments();
  const statistics = await getStatistics();
  const info = await getBlockInfo();

  const ok = experiments.rows.filter((r) => r.status === 'OK' && r.auprc !== undefined);
  const full = ok.find((r) => r.arm === 'FULL');
  const sorted = [...ok].sort((a, b) => (b.auprc ?? 0) - (a.auprc ?? 0));
  const significant = statistics.rows.filter((s) => s.significant);

  return (
    <>
      <h1>Ablations</h1>
      <p className="lede">
        {/* Two things stated before any number: every arm is compared ON THE SAME ROWS, and
            the intervals resample WHOLE EPISODES.
            That second clause is the dependence rule, put in a sentence a reader can follow:
            "so within-episode dependence is not mistaken for independent evidence". */}
        Each arm removes one part of the method and is compared against the full evidence
        stack on the same rows. Intervals come from a cluster bootstrap that resamples
        whole episodes, so within-episode dependence is not mistaken for independent
        evidence.
      </p>

      {!experiments.dataAvailable ? (
        <NoData what="Ablation results" note={experiments.note} />
      ) : (
        <>
          <div className="grid">
            <StatCard label="Arms" value={String(ok.length)} />
            <StatCard label="Full-stack AUPRC" value={fmt(full?.auprc)} />
            <StatCard
              // HOW MANY RESULTS SURVIVED THE CORRECTION, out of how many were tested.
              // Showing both numbers is the honest form: "3 of 31" tells a reader far more
              // than "3 significant results" ever could.
              label="Significant at 5% FDR"
              value={`${significant.length} of ${statistics.rows.length}`}
            />
          </div>

          <h2>Block information decomposition</h2>
          {!info.dataAvailable || info.rows.length === 0 ? (
            <NoData what="Block decomposition" note={info.note} />
          ) : (
            <>
              <p className="small muted" style={{ marginTop: 0 }}>
                {/* THE KEY INSIGHT, in one sentence: a block can look useful alone while
                    adding nothing once the others are there. That is redundancy, and without
                    this table it would be indistinguishable from uselessness. */}
                A block can look useful in isolation while adding nothing once the
                others are present. This splits each contribution into the part that is
                unique and the part that is redundant, and reports how often the block
                disagrees with the combined decision.
              </p>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Block</th>
                      {/* "Alone" and "Unique" side by side -- and the GAP between them is
                          the redundancy. All three columns shown, so the reader can see the
                          arithmetic rather than being told the conclusion. */}
                      <th className="num">Alone</th>
                      <th className="num">Unique</th>
                      <th className="num">Redundant</th>
                      {/* How often it disagrees with the final verdict, and how often it was
                          missing entirely -- the third and fourth explanations for "removing
                          it changed nothing". */}
                      <th className="num">Conflict rate</th>
                      <th className="num">Missing rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.rows.map((r) => (
                      <tr key={r.block}>
                        <td>{r.block}</td>
                        <td className="num">{fmt(r.total_auprc)}</td>
                        {/* `signed` on the unique column, so a NEGATIVE contribution shows
                            its minus sign unmistakably -- that being the most interesting
                            value in the table. */}
                        <td className="num">{signed(r.unique)}</td>
                        <td className="num">{fmt(r.redundant)}</td>
                        <td className="num">{fmt(r.conflict_rate, 3)}</td>
                        <td className="num">{fmt(r.missing_rate, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="small muted">
                {/* TWO PIECES OF INTERPRETATION, and the second is unusually fair.
                    First: a negative unique contribution means the block actively COSTS
                    performance. Said plainly.
                    Second, and this is the fair part: the mood and contagion blocks are built
                    from the SAME prices the market block already reads. So low uniqueness is
                    "expected by construction rather than a failure of the block".
                    The project defends its own components against a misreading its own table
                    would otherwise invite. */}
                A negative unique contribution means the block costs performance when
                present. The regime and propagation blocks are derived from the same price
                series the market block reads, so a low uniqueness for either is expected
                by construction rather than a failure of the block.
              </p>
            </>
          )}

          <h2>Arms by AUPRC</h2>
          {/* The chart and the table show the SAME data -- but here that is justified,
              because the chart gives the shape at a glance and the table adds the intervals
              and the calibration error the chart cannot carry. */}
          <Bars
            items={sorted.map((r) => ({ name: r.arm, value: r.auprc ?? null }))}
            // The label names the metric AND the split it was measured on.
            label="AUPRC by ablation arm on the validation split"
          />
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Arm</th>
                  <th>Blocks</th>
                  <th className="num">AUPRC</th>
                  <th style={{ width: 120 }}>Level</th>
                  {/* THE INTERVAL COLUMN. Without it a reader would compare 0.412 against
                      0.409 and conclude one is better -- which the intervals may well not
                      support. */}
                  <th className="num">95% CI</th>
                  <th className="num">ECE</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.arm}>
                    <td className="mono">{r.arm}</td>
                    {/* Which evidence this arm was allowed, so the row is self-explaining. */}
                    <td className="muted small">{r.blocks}</td>
                    <td className="num">{fmt(r.auprc)}</td>
                    <td>
                      <ScoreBar value={r.auprc} />
                    </td>
                    <td className="num">
                      {/* "n/a" where no interval exists -- never an empty cell that would
                          read as a precise result. */}
                      {r.ciLow === undefined || r.ciLow === null
                        ? 'n/a'
                        : `${fmt(r.ciLow)} to ${fmt(r.ciHigh)}`}
                    </td>
                    <td className="num">{fmt(r.ece)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Statistical tests</h2>
      {!statistics.dataAvailable ? (
        <NoData what="Statistical tests" note={statistics.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Arm</th>
                {/* THE EFFECT SIZE FIRST, then the p-values. The same ordering discipline as
                    the research layer: how big outranks how surprising. */}
                <th className="num">Delta AUPRC</th>
                <th className="num">95% CI</th>
                <th className="num">p</th>
                {/* BOTH the raw and the corrected p-value, so a reader can see exactly how
                    much the multiple-comparisons correction changed the picture. */}
                <th className="num">adjusted p</th>
                <th>Significant</th>
              </tr>
            </thead>
            <tbody>
              {statistics.rows.map((s) => (
                <tr key={s.arm}>
                  <td className="mono">{s.arm}</td>
                  <td className="num">{signed(s.deltaAuprc)}</td>
                  <td className="num">n/a</td>
                  <td className="num">{fmt(s.pValue, 4)}</td>
                  <td className="num">{fmt(s.adjustedP, 4)}</td>
                  <td>
                    {/* The verdict from the ADJUSTED value. And "no" is written out rather
                        than left blank, so a non-significant result is a stated finding
                        rather than an empty cell. */}
                    <span className={s.significant ? 'chip chip--good' : 'chip'}>
                      {s.significant ? 'yes' : 'no'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="boundary">
        {/* THE MOST IMPORTANT PARAGRAPH ON THE PAGE, and it teaches the reader how to read
            the table above.
            Two principles first: significance is not importance, and a null is not evidence
            of absence.
            Then a WORKED EXAMPLE with the project's own numbers. The smallest difference the
            study could detect was 0.000185. The difference actually observed was 0.000176 --
            just below it.
            So that comparison could never have told us anything. It is not evidence that the
            contribution is zero; it is evidence that we could not measure it.
            Showing this, with their own real numbers, on their own results page, is a project
            explaining exactly why one of its own tables cannot be read the way a reader would
            naturally read it. */}
        <h3>Reading a non-significant result</h3>
        <p style={{ margin: 0 }}>
          Statistical significance is not importance, and a null is not evidence of
          absence. The microstructure comparison has a minimum detectable effect of
          0.000185 against an observed difference of 0.000176: that comparison is
          uninformative at this episode count rather than evidence that the contribution
          is zero. The power analysis under Statistics reports the detectable effect for
          each comparison.
        </p>
      </section>
    </>
  );
}
