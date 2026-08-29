import { NoData, ScoreBar, StatCard } from '@/components/ui/Primitives';
import { Bars } from '@/components/visualization/Sparkline';
import { fmt, getExperiments, getBlockInfo, getStatistics, signed } from '@/lib/data';

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
                      <th className="num">Alone</th>
                      <th className="num">Unique</th>
                      <th className="num">Redundant</th>
                      <th className="num">Conflict rate</th>
                      <th className="num">Missing rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.rows.map((r) => (
                      <tr key={r.block}>
                        <td>{r.block}</td>
                        <td className="num">{fmt(r.total_auprc)}</td>
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
                A negative unique contribution means the block costs performance when
                present. The regime and propagation blocks are derived from the same price
                series the market block reads, so a low uniqueness for either is expected
                by construction rather than a failure of the block.
              </p>
            </>
          )}

          <h2>Arms by AUPRC</h2>
          <Bars
            items={sorted.map((r) => ({ name: r.arm, value: r.auprc ?? null }))}
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
                  <th className="num">95% CI</th>
                  <th className="num">ECE</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.arm}>
                    <td className="mono">{r.arm}</td>
                    <td className="muted small">{r.blocks}</td>
                    <td className="num">{fmt(r.auprc)}</td>
                    <td>
                      <ScoreBar value={r.auprc} />
                    </td>
                    <td className="num">
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
                <th className="num">Delta AUPRC</th>
                <th className="num">95% CI</th>
                <th className="num">p</th>
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
