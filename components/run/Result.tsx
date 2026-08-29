// Runs in the browser: it displays a result that arrived after a click.
'use client';

/**
 * One backend response, rendered in both experiences.
 *
 * The badge is the first thing on the panel and it is not decorative. `LIVE_COMPUTATION`
 * means the canonical implementation ran during this request on the slice that was
 * selected; `VERIFIED_ARTIFACT` means a stored run is being replayed and nothing was
 * computed. Everything else on the panel — whether the inputs were applied, whether there
 * is a run identifier to cite — follows from which of those two it is, so it is stated
 * once, plainly, at the top.
 *
 * Product mode simplifies the language and never the meaning. A refusal is shown as a
 * refusal in both modes, with the reason and what to do about it, because a panel that
 * quietly renders nothing teaches a reader that the tool is broken rather than that their
 * selection was too narrow.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * DISPLAYING WHAT CAME BACK.
 *
 * THE BADGE IS FIRST, AND IT IS NOT DECORATION. Live, or replayed. Everything else on the
 * panel depends on which -- whether your settings were actually applied, whether there is a
 * run to cite. So it is stated once, at the top, before any number.
 *
 * AND THE SECOND PARAGRAPH CONTAINS THE BEST OBSERVATION IN THE FILE:
 *
 *     "a panel that quietly renders nothing teaches a reader that the tool is broken
 *      rather than that their selection was too narrow."
 *
 * Consider what happens when somebody picks a date range with no data in it. If the panel
 * simply shows nothing, they conclude the tool does not work. They may well never try
 * again. The actual situation -- "that week has no data, try a wider range" -- would have
 * taken one sentence and kept them.
 * So a refusal is shown AS a refusal, in both views, with the reason and the fix.
 */
import type { RunMetric, RunResponse, RunSeries } from '@/lib/runTypes';
import { MODE_COPY, statusCopy } from '@/lib/runTypes';

/**
 * The mode badge, when there is a result to describe.
 *
 * A refused request produced neither a computation nor a replay, so labelling it as
 * either would describe something that did not happen. The refusal below says what
 * actually occurred; a badge above it would only contradict that.
 */
// PLAIN ENGLISH: a precise piece of care. If the request was refused, nothing was computed
// AND nothing was replayed. So neither badge would be true. Showing one anyway would put a
// confident label above a message saying nothing happened -- and the two would contradict
// each other on the same panel.
// So when there is no result, there is no badge.
export function ModeBadge({ response }: { response: RunResponse }) {
  const produced = response.metrics.length > 0 || response.series.length > 0;
  if (!produced) return null;
  const copy = MODE_COPY[response.mode] ?? {
    // A fallback for an unrecognised mode: use whatever the server called it, and treat it
    // as the more cautious of the two rather than claiming it was live.
    badge: response.mode_label,
    tone: 'artifact' as const,
    short: response.mode_meaning,
  };
  return (
    <p className="runBadge" data-tone={copy.tone}>
      <span className="runBadge__dot" aria-hidden="true" />
      <span className="runBadge__label">{copy.badge}</span>
      {/* And the explanation right beside the label, so the badge never needs interpreting. */}
      <span className="runBadge__text">{copy.short}</span>
    </p>
  );
}

// The status line.
export function StatusLine({ response }: { response: RunResponse }) {
  const copy = statusCopy(response.status);
  return (
    <p className="runStatus" data-kind={copy.kind}>
      <span className="runStatus__label">{copy.label}</span>
      {/* How long it took, but only on success -- the duration of a failure is not
          interesting and would only clutter the message that is. */}
      {response.status === 'OK' && response.elapsed_s ? (
        <span className="small muted"> · {response.elapsed_s.toFixed(2)}s</span>
      ) : null}
    </p>
  );
}

// A refusal, shown properly.
export function Refusal({ response }: { response: RunResponse }) {
  if (!response.error) return null;
  return (
    <div className="runRefusal" role="status">
      <h4>{statusCopy(response.status).label}</h4>
      {/* THE REASON, then THE REMEDY, then the machine code. In that order: what happened,
          what to do, and finally the technical identifier for anybody reporting it. */}
      <p>{response.error.reason}</p>
      {response.error.remedy ? <p className="runRefusal__remedy">{response.error.remedy}</p> : null}
      {/* The code last and in small monospace -- available for a bug report, not shouting
          at somebody who only wants to know what to do next. */}
      <p className="small muted mono">{response.error.code}</p>
    </div>
  );
}

// The headline numbers.
function MetricList({ metrics }: { metrics: RunMetric[] }) {
  if (metrics.length === 0) return null;
  return (
    <div className="grid runMetrics">
      {metrics.map((m) => (
        <div className="card metricCard" key={m.key}>
          <span className="card__label">{m.label}</span>
          {/* The display value from the server, so formatting is decided in one place. */}
          <span className="card__value">{m.display}</span>
          {m.note ? <span className="card__note">{m.note}</span> : null}
          {/* AND THE FILE IT CAME FROM, printed on the card. Present for a replayed value,
              empty for a computed one -- so the blank itself tells you it was fresh. */}
          {m.source ? <span className="metricCard__source mono">{m.source}</span> : null}
        </div>
      ))}
    </div>
  );
}

// A table of results.
function SeriesTable({ series }: { series: RunSeries }) {
  return (
    <section className="runSeries">
      <h4>{series.label}</h4>
      {series.note ? <p className="small muted">{series.note}</p> : null}
      {/* A wrapper that scrolls sideways, so a wide table does not stretch the whole page
          and break the layout on a phone. */}
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              {series.columns.map((c) => (
                // `scope="col"` so screen-reader software pairs each value with its heading.
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {series.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  // Numbers get a monospaced font so their digits line up down the column
                  // and can be compared at a glance; text does not.
                  <td key={j} className={typeof cell === 'number' ? 'mono' : undefined}>
                    {/* An em-dash for a missing value -- visibly absent, never a zero. */}
                    {cell === null ? '—' : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {series.truncated ? (
        // THE TRUNCATION ANNOUNCED, with the real total. So a shortened table never passes
        // for the whole thing.
        <p className="small muted">
          Showing {series.rows.length} of {series.total_rows ?? '?'} rows.
        </p>
      ) : null}
    </section>
  );
}

// The plain-English findings.
function Observations({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="runObservations">
      {items.map((o, i) => (
        <li key={i}>{o}</li>
      ))}
    </ul>
  );
}

// How far the result goes.
function Uncertainty({ payload }: { payload: Record<string, unknown> }) {
  const reading = typeof payload.reading === 'string' ? payload.reading : '';
  if (!reading) return null;
  const kind = typeof payload.kind === 'string' ? payload.kind : 'unspecified';
  return (
    <section className="runUncertainty">
      {/* The heading is the reader's own question: "How far this goes". Not "Uncertainty
          quantification", which would be accurate and would be skipped. */}
      <h4>How far this goes</h4>
      <p>{reading}</p>
      <p className="small muted mono">uncertainty: {kind}</p>
    </section>
  );
}

// The full audit trail.
function Provenance({ response }: { response: RunResponse }) {
  const p = response.provenance;
  const rows: [string, string][] = [];
  // A small helper that adds a row only when there is something to say -- so the list has
  // no empty entries for facts that do not apply to this kind of run.
  const push = (k: string, v: unknown) => {
    if (v === null || v === undefined || v === '') return;
    rows.push([k, Array.isArray(v) ? v.join(', ') : String(v)]);
  };
  push('module', p.module_id);
  push('adapter', p.adapter);
  push('canonical called', p.canonical_called ?? p.canonical);
  // THE TWO FACTS THAT MATTER MOST: was anything computed, and was anything written.
  // The second is the reassurance that this run changed nothing on disk.
  push('computed during this request', p.computed);
  push('wrote nothing', p.wrote_nothing);
  // Exactly which version of the code, and exactly when.
  push('git commit', p.git_commit);
  push('requested at', p.requested_at);
  // For a replay: which stored run, and at which code version. So a replayed number can be
  // cited precisely rather than as "an earlier run".
  push('replayed run', p.replayed_run_id);
  push('replayed commit', p.replayed_commit);
  push('artifacts', p.artifacts);
  // AND THE COMMAND TO REPRODUCE IT, in the panel. A reader is handed the instruction.
  push('regenerate with', p.regenerate_with);
  push('protected artifacts', p.protected_artifacts);

  return (
    <section className="runProvenance">
      <h4>Provenance</h4>
      {/* The plain-English sentences first, then the field list. Prose before data, so a
          reader gets the gist before the detail. */}
      {typeof p.execution === 'string' ? <p className="small">{p.execution}</p> : null}
      {typeof p.protection_note === 'string' ? (
        <p className="small">{p.protection_note}</p>
      ) : null}
      <dl className="runProvenance__list">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// What data was read.
function Dataset({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload).filter(([, v]) => v !== null && v !== '');
  if (entries.length === 0) return null;
  return (
    <section className="runDataset">
      {/* Again the plain question: "What was read". */}
      <h4>What was read</h4>
      <dl className="runProvenance__list">
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">
              {/* Nested structures shown as JSON rather than as "[object Object]", which is
                  what the plain conversion would produce and which tells nobody anything. */}
              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// The caveats.
function Limitations({ response }: { response: RunResponse }) {
  if (response.limitations.length === 0) return null;
  return (
    <section className="runLimits">
      {/* "What this does not cover" -- the reader's own words again, rather than
          "Limitations", which reads as a formality to be skipped. */}
      <h4>What this does not cover</h4>
      <ul>
        {response.limitations.map((l) => (
          <li key={l.id}>
            {/* The reference id, so it can be looked up, then the title and the scope note. */}
            <span className="mono">{l.id}</span> {l.title}
            {l.scope_note ? <span className="small muted"> — {l.scope_note}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The product reading: the badge, the headline numbers, the plain-language findings. */
export function ResultProduct({ response }: { response: RunResponse }) {
  return (
    <div className="runResult">
      <ModeBadge response={response} />
      <StatusLine response={response} />
      {/* THE REFUSAL IS SHOWN IN THIS VIEW TOO. Not hidden away in the detailed one. */}
      {response.error ? <Refusal response={response} /> : null}
      {/* At most six numbers, so the simple view stays simple. */}
      <MetricList metrics={response.metrics.slice(0, 6)} />
      <Observations items={response.observations} />
      {/* AND THE UNCERTAINTY AND THE LIMITATIONS ARE HERE TOO. This is the whole "simplifies
          the language, never the meaning" rule made concrete: the simple view shows fewer
          numbers, and exactly the same caveats. */}
      <Uncertainty payload={response.uncertainty} />
      <Limitations response={response} />
    </div>
  );
}

/** The research reading: everything above, plus the tables and the audit trail. */
export function ResultResearch({ response }: { response: RunResponse }) {
  return (
    <div className="runResult">
      <ModeBadge response={response} />
      <StatusLine response={response} />
      {response.error ? <Refusal response={response} /> : null}
      {/* Every number, not just six. */}
      <MetricList metrics={response.metrics} />
      <Observations items={response.observations} />
      {/* Plus the full tables. */}
      {response.series.map((s) => (
        <SeriesTable key={s.key} series={s} />
      ))}
      <Uncertainty payload={response.uncertainty} />
      <Dataset payload={response.dataset} />
      {Object.keys(response.inputs).length > 0 ? (
        <section className="runInputs">
          {/* "Inputs the service ACCEPTED" -- precisely worded. These are what the server
              actually used after checking, which may differ from what was typed. Showing
              the accepted version is what lets a reader spot a setting that was silently
              defaulted. */}
          <h4>Inputs the service accepted</h4>
          <pre className="mono">{JSON.stringify(response.inputs, null, 2)}</pre>
        </section>
      ) : null}
      <Provenance response={response} />
      <Limitations response={response} />
    </div>
  );
}

/** Both readings, switched by the same `data-mode` attribute the rest of the app uses. */
export function Result({ response }: { response: RunResponse }) {
  // Both in the page, one hidden by styling -- the same technique as everywhere else, so
  // the two views are built from one response and cannot disagree.
  return (
    <>
      <div className="modeOnly modeOnly--product">
        <ResultProduct response={response} />
      </div>
      <div className="modeOnly modeOnly--research">
        <ResultResearch response={response} />
      </div>
    </>
  );
}
