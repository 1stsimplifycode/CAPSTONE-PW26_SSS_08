import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { fmt, getExperiments, getLimitations } from '@/lib/data';
import type { ResearchStatus } from '@/lib/types';

export const dynamic = 'force-static';

const RESEARCH_QUESTIONS: [string, string, string][] = [
  ['RQ1', 'Does combining market evidence blocks improve integrity-risk detection?', 'SUPPORTED'],
  ['RQ2', 'Does each evidence block add measurable information?', 'PARTIAL'],
  ['RQ3', 'Does the derived representation improve on the raw descriptors?', 'SUPPORTED'],
  ['RQ4', 'Does temporal modelling improve on point anomaly detection?', 'PARTIAL'],
  ['RQ5', 'Can risk emergence be detected before onset?', 'NOT_SUPPORTED'],
  ['RQ6', 'Can risk resolution be identified?', 'PARTIAL'],
  ['RQ7', 'Does propagation improve detection?', 'NOT_SUPPORTED'],
  ['RQ8', 'Does uncertainty-aware combination reduce false positives?', 'NOT_SUPPORTED'],
  ['RQ9', 'Does corrected regime-conditioned combination outperform static combination?', 'NOT_SUPPORTED'],
  ['RQ10', 'Does integrity gating reduce tail capital consequences?', 'PARTIAL'],
  ['RQ11', 'Does synthetic data improve rare-event detection?', 'NOT_RUN'],
  ['RQ12', 'Does the system generalise across market cycles?', 'NOT_RUN'],
  ['RQ-X1', 'Can explanations identify the evidence responsible for escalation?', 'SUPPORTED'],
  ['RQ-X2', 'Are explanations faithful?', 'SUPPORTED'],
  ['RQ-X3', 'Are explanations stable?', 'PARTIAL'],
  ['RQ-X4', 'Do different explanation methods agree?', 'PARTIAL'],
  ['RQ-X5', 'Does block attribution identify per-block contributions?', 'SUPPORTED'],
  ['RQ-X6', 'Can counterfactuals identify plausible resolution conditions?', 'SUPPORTED'],
];

export default async function ExperimentsPage() {
  const experiments = await getExperiments();
  const limitations = await getLimitations();
  const specs = limitations.rows.flatMap((l) =>
    l.research_questions.flatMap((r) => r.experiments.map((e) => ({ ...e, limitation: l.id }))),
  );
  const ok = experiments.rows.filter((e) => e.status === 'OK');

  return (
    <>
      <h1>Experiments</h1>
      <p className="lede">
        Executed arms and designed specifications, kept visibly apart. An arm below the
        first table has been run and has numbers; a specification below the second has a
        control, a treatment, metrics and a statistical test, and either has been run or
        names the data blocking it.
      </p>

      <div className="grid">
        <StatCard label="Arms executed" value={String(ok.length)} href="/research/ablations" />
        <StatCard label="Specifications" value={String(specs.length)} />
        <StatCard
          label="Runnable now"
          value={String(specs.filter((s) => s.required_data.length === 0).length)}
        />
        <StatCard
          label="Blocked by data"
          value={String(specs.filter((s) => s.required_data.length > 0).length)}
        />
      </div>

      <h2>Research questions</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Question</th>
              <th>Status on the current evaluation</th>
            </tr>
          </thead>
          <tbody>
            {RESEARCH_QUESTIONS.map(([id, q, s]) => (
              <tr key={id}>
                <td className="mono">{id}</td>
                <td>{q}</td>
                <td>
                  <StatusChip status={s as ResearchStatus} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Six of eighteen are NOT SUPPORTED or NOT RUN. They are listed here at the same
        prominence as the supported ones, because a research programme that only reports
        its wins is not reporting.
      </p>

      <h2>Executed arms</h2>
      {!experiments.dataAvailable ? (
        <NoData what="Experiment results" note={experiments.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Arm</th>
                <th>Combiner</th>
                <th className="num">AUPRC</th>
                <th className="num">AUROC</th>
                <th className="num">F1</th>
                <th className="num">ECE</th>
              </tr>
            </thead>
            <tbody>
              {[...experiments.rows]
                .sort((a, b) => (b.auprc ?? 0) - (a.auprc ?? 0))
                .map((r) => (
                  <tr key={r.arm}>
                    <td className="mono">{r.arm}</td>
                    <td className="muted small">{r.combiner}</td>
                    <td className="num">{fmt(r.auprc)}</td>
                    <td className="num">{fmt(r.auroc)}</td>
                    <td className="num">{fmt(r.f1)}</td>
                    <td className="num">{fmt(r.ece)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Designed specifications</h2>
      {specs.length === 0 ? (
        <NoData what="Experiment specifications" note={limitations.note} />
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Limitation</th>
                <th>Status</th>
                <th>Hypothesis</th>
                <th>Blocked by</th>
              </tr>
            </thead>
            <tbody>
              {specs.map((s) => (
                <tr key={s.id}>
                  <td className="mono">{s.id}</td>
                  <td className="mono">
                    <Link href={`/research/limitations/${s.limitation}`}>
                      {s.limitation}
                    </Link>
                  </td>
                  <td>
                    <StatusChip status={s.status} />
                  </td>
                  <td className="small">{s.hypothesis}</td>
                  <td className="small muted">
                    {s.required_data.length ? s.required_data.join('; ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
