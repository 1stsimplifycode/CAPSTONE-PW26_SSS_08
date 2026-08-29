import Link from 'next/link';

import { NoData, StatCard, StatusChip } from '@/components/ui/Primitives';
import { fmt, getExperiments, getLimitations } from '@/lib/data';
import type { ResearchStatus } from '@/lib/types';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE EXPERIMENTS PAGE, AND THE MOST HONEST TABLE IN THE PROJECT.
 *
 * The page keeps two things carefully apart:
 *   EXECUTED ARMS -- experiments that have been RUN and have numbers.
 *   SPECIFICATIONS -- experiments that have been DESIGNED and may or may not have run.
 * A designed experiment is not a result, and the page never lets the two blur.
 *
 * And then the research-questions table lists eighteen questions with their honest
 * outcomes -- six of which are NOT SUPPORTED or NOT RUN. The note beneath it gives the
 * reason for showing them at equal prominence, and it is the best line on the page:
 *
 *     "a research programme that only reports its wins is not reporting."
 */

export const dynamic = 'force-static';

// THE EIGHTEEN RESEARCH QUESTIONS AND THEIR HONEST ANSWERS.
// Read down the third column. This is a project publishing its own scorecard.
const RESEARCH_QUESTIONS: [string, string, string][] = [
  ['RQ1', 'Does combining market evidence blocks improve integrity-risk detection?', 'SUPPORTED'],
  ['RQ2', 'Does each evidence block add measurable information?', 'PARTIAL'],
  ['RQ3', 'Does the derived representation improve on the raw descriptors?', 'SUPPORTED'],
  ['RQ4', 'Does temporal modelling improve on point anomaly detection?', 'PARTIAL'],
  // THE CENTRAL QUESTION OF THE WHOLE PROJECT -- can trouble be spotted BEFORE it starts --
  // answered NOT SUPPORTED. Published in the same table, in the same style, as the wins.
  ['RQ5', 'Can risk emergence be detected before onset?', 'NOT_SUPPORTED'],
  ['RQ6', 'Can risk resolution be identified?', 'PARTIAL'],
  ['RQ7', 'Does propagation improve detection?', 'NOT_SUPPORTED'],
  ['RQ8', 'Does uncertainty-aware combination reduce false positives?', 'NOT_SUPPORTED'],
  ['RQ9', 'Does corrected regime-conditioned combination outperform static combination?', 'NOT_SUPPORTED'],
  ['RQ10', 'Does integrity gating reduce tail capital consequences?', 'PARTIAL'],
  // NOT RUN, rather than NOT SUPPORTED -- the distinction the vocabulary exists to preserve.
  // These were never attempted; that is a different fact from having been tried and failed.
  ['RQ11', 'Does synthetic data improve rare-event detection?', 'NOT_RUN'],
  ['RQ12', 'Does the system generalise across market cycles?', 'NOT_RUN'],
  // The explanation questions, which fared considerably better.
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
  // Every designed experiment, gathered from every question of every limitation -- and each
  // tagged with the limitation it came from, so the trail back is preserved.
  const specs = limitations.rows.flatMap((l) =>
    l.research_questions.flatMap((r) => r.experiments.map((e) => ({ ...e, limitation: l.id }))),
  );
  const ok = experiments.rows.filter((e) => e.status === 'OK');

  return (
    <>
      <h1>Experiments</h1>
      <p className="lede">
        {/* "kept visibly apart" -- the whole design of the page in three words. And then a
            precise definition of each: an arm HAS NUMBERS; a specification has a control, a
            treatment, metrics and a test, and either has run or NAMES THE DATA BLOCKING IT.
            No specification is allowed to sit there unexplained. */}
        Executed arms and designed specifications, kept visibly apart. An arm below the
        first table has been run and has numbers; a specification below the second has a
        control, a treatment, metrics and a statistical test, and either has been run or
        names the data blocking it.
      </p>

      <div className="grid">
        <StatCard label="Arms executed" value={String(ok.length)} href="/research/ablations" />
        <StatCard label="Specifications" value={String(specs.length)} />
        {/* THE TWO COUNTS THAT MATTER MOST, and they are uncomfortable ones:
            RUNNABLE NOW -- designed, needs nothing, and has not been run. No excuse.
            BLOCKED BY DATA -- genuinely prevented.
            Publishing the first number is a project holding itself to account in public. */}
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
              {/* "Status ON THE CURRENT EVALUATION" -- carefully bounded. Not "answer", and
                  not a permanent verdict: this is where things stand on the data evaluated
                  so far. */}
              <th>Status on the current evaluation</th>
            </tr>
          </thead>
          <tbody>
            {RESEARCH_QUESTIONS.map(([id, q, s]) => (
              <tr key={id}>
                <td className="mono">{id}</td>
                <td>{q}</td>
                <td>
                  {/* The same chip component as everywhere else, so the colours mean the
                      same thing here as on every other page. */}
                  <StatusChip status={s as ResearchStatus} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        {/* THE SENTENCE. It counts its own failures -- six of eighteen -- and then gives the
            principle: a research programme that only reports its wins is not reporting.
            Note it does not soften the count, explain it away, or bury it beneath the
            successes. It states it and justifies showing it. */}
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
                {/* FOUR MEASURES, not one. Including the calibration error, which is the one
                    that would be left out of a table designed to flatter. */}
                <th className="num">AUPRC</th>
                <th className="num">AUROC</th>
                <th className="num">F1</th>
                <th className="num">ECE</th>
              </tr>
            </thead>
            <tbody>
              {/* Copied before sorting, so the original order is left undisturbed. Best
                  AUPRC first -- the project's declared headline measure, not the flattering
                  AUROC. */}
              {[...experiments.rows]
                .sort((a, b) => (b.auprc ?? 0) - (a.auprc ?? 0))
                .map((r) => (
                  <tr key={r.arm}>
                    <td className="mono">{r.arm}</td>
                    <td className="muted small">{r.combiner}</td>
                    {/* `fmt` shows "n/a" for anything missing, never a zero. */}
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
                {/* THE HYPOTHESIS SHOWN IN THE TABLE. So a reader can see what each
                    experiment would test, not merely that one was designed. */}
                <th>Hypothesis</th>
                <th>Blocked by</th>
              </tr>
            </thead>
            <tbody>
              {specs.map((s) => (
                <tr key={s.id}>
                  <td className="mono">{s.id}</td>
                  <td className="mono">
                    {/* Linked back to the limitation that gave rise to it -- so the chain
                        from gap to question to experiment is walkable in both directions. */}
                    <Link href={`/research/limitations/${s.limitation}`}>
                      {s.limitation}
                    </Link>
                  </td>
                  <td>
                    <StatusChip status={s.status} />
                  </td>
                  <td className="small">{s.hypothesis}</td>
                  <td className="small muted">
                    {/* EXACTLY WHAT IS MISSING, where something is. And a dash where nothing
                        is -- which, read together with an unrun status, is the row admitting
                        it has no excuse. */}
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
