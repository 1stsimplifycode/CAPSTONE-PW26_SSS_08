// Runs in the browser: it responds to a button being pressed.
'use client';

/**
 * The interactive half of a module page: choose a slice, run it, read what came back.
 *
 * The button says which of the two things it will do before it is pressed. A module with a
 * live analysis adapter recomputes on the selection; a module without one replays its
 * stored artifact, and says so both before and after, so nobody presses "Run" expecting
 * fresh numbers and receives old ones under a fresh-looking heading.
 *
 * Protected modules are the interesting case. Their artifacts are cited by the claim
 * ledger, so no request may regenerate them — but many of them can still *analyse* live,
 * because analysing writes nothing. The panel says exactly that rather than presenting the
 * guard as a failure.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE RUN PANEL: pick your settings, press the button, read the answer.
 *
 * THE FIRST IDEA: THE BUTTON TELLS YOU WHAT IT WILL DO, BEFORE YOU PRESS IT.
 * A module that can compute says "Run this analysis".
 * A module that can only replay says "Load the verified result".
 * Both are honest, and neither surprises you. The failure this avoids is spelled out in
 * the docstring: pressing something labelled "Run", expecting fresh numbers, and receiving
 * last month's under a heading that looks freshly generated.
 *
 * THE SECOND IDEA, and it is a subtle one: PROTECTED MODULES CAN STILL BE ANALYSED.
 * Some results are frozen because the paper cites them. The instinct is to disable those
 * modules entirely.
 * But freezing protects against OVERWRITING. Analysing writes nothing at all -- it reads
 * the data and hands back an answer. So most protected modules can happily be run live;
 * they simply cannot be made to save over their stored results.
 * So instead of a locked, greyed-out panel, the page explains: the artifacts are protected,
 * analysing here writes nothing, and the guard is not in your way.
 * The guard is presented as a fact about the system, not as a failure and not as a wall.
 */
import { useMemo, useState } from 'react';

import type { ExecutionSpec, InputSpec, RunResponse } from '@/lib/runTypes';
import { defaultsFor } from '@/lib/runTypes';

import { Controls, type Values } from './Controls';
import { Result } from './Result';
import { useRun } from './useRun';

export function ModuleRunner({
  moduleId,
  moduleName,
  inputs,
  execution,
  summary,
}: {
  moduleId: string;
  moduleName: string;
  inputs: InputSpec[];
  execution: ExecutionSpec;
  summary: string;
}) {
  // The form starts filled with the defaults from the module's own declared settings -- so
  // the starting state is guaranteed to be something the server accepts.
  const [values, setValues] = useState<Values>(() => defaultsFor(inputs));
  const { phase, result, transport, run, reset } = useRun<RunResponse>(
    `/api/aegis/modules/${moduleId}/run`,
  );

  // Build what will be sent, dropping anything left blank. `useMemo` rebuilds it only when
  // the values change rather than on every redraw.
  const body = useMemo(
    // Blanks are removed rather than sent as empty -- because an empty value would be read
    // by the server as a setting deliberately supplied, rather than as one left alone.
    () => Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '' && v !== null)),
    [values],
  );

  // THE BUTTON'S WORDING, decided by what will actually happen.
  const verb = execution.is_live ? 'Run this analysis' : 'Load the verified result';
  const running = phase === 'running';

  return (
    // `aria-labelledby` ties the section to its heading, so screen-reader software
    // announces the panel by name rather than as an unlabelled region.
    <section className="runPanel" data-module={moduleId} aria-labelledby={`run-${moduleId}`}>
      <header className="runPanel__head">
        {/* Even the heading differs: "Run it yourself" versus "The stored result". */}
        <h3 id={`run-${moduleId}`}>{execution.is_live ? 'Run it yourself' : 'The stored result'}</h3>
        <p className="runPanel__lede">{summary}</p>
        <p className="small muted">
          {execution.is_live ? (
            <>
              {/* Says what will happen AND roughly how long -- so a forty-second module
                  reads as slow rather than as broken. */}
              The canonical implementation runs on your selection when you press the button.
              Typical time: {execution.typical_seconds}s.
            </>
          ) : (
            <>
              {/* And for a replay-only module: says so, gives the SERVER'S OWN REASON, and
                  promises the result will be labelled as stored. All before the click. */}
              This module does not compute on request. {execution.artifact_reason} The stored,
              provenance-stamped result is served instead, labelled as one.
            </>
          )}
        </p>
        {execution.protected ? (
          <p className="runPanel__guard">
            {/* THE PROTECTED EXPLANATION. Note the tone: it explains what protection means
                and why it exists, rather than simply refusing. */}
            Its published artifacts are protected: they are cited elsewhere, so no request from
            this page can overwrite them.
            {execution.is_live
              // And the reassurance where it applies: the guard is not stopping you.
              ? ' Analysing here writes nothing, so the guard is not in the way.'
              // Or an honest statement of what regenerating would take.
              : ' Regenerating them takes a deliberate terminal command.'}
          </p>
        ) : null}
      </header>

      {/* The form, built from the module's declared settings. */}
      <Controls
        inputs={inputs}
        values={values}
        // `{...prev, [name]: value}` updates one setting while keeping the rest.
        onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
        // Everything is switched off while a run is in progress, so nothing can be changed
        // underneath a request that is already in the air.
        disabled={running}
        idPrefix={`run-${moduleId}`}
      />

      <div className="runPanel__actions">
        <button
          type="button"
          className="runPanel__go"
          onClick={() => void run(body)}
          disabled={running}
          // `aria-busy` tells assistive software the panel is working -- so a listening
          // reader is told something is happening rather than sitting in silence.
          aria-busy={running}
        >
          {/* The label changes while running, naming the module so it is obvious what is
              being waited for. */}
          {running ? `Running ${moduleName}…` : verb}
        </button>
        {phase === 'done' ? (
          // A Clear button, appearing only once there is something to clear.
          <button type="button" className="runPanel__reset" onClick={reset}>
            Clear
          </button>
        ) : null}
      </div>

      {running ? (
        // `role="status"` makes assistive software announce this when it appears.
        <p className="runPanel__waiting" role="status">
          {execution.is_live
            // AND THE REASSURANCE THAT MATTERS MOST: "Nothing is written while it runs."
            // Somebody about to interrupt a long-running job is told they can, safely.
            ? `Running ${moduleId} over the selected slice. Nothing is written while it runs.`
            : `Reading the stored result for ${moduleId}.`}
        </p>
      ) : null}

      {transport ? (
        // OUTCOME 3 from useRun: nothing answered. Shown as its own block with the reason
        // and the remedy -- and, crucially, NOT as a fabricated result.
        <div className="runRefusal" role="status">
          <h4>No result</h4>
          <p>{transport.reason}</p>
          <p className="runRefusal__remedy">{transport.remedy}</p>
        </div>
      ) : null}

      {/* And the result itself, whether it succeeded or refused -- the Result component
          reads the status and renders each appropriately. */}
      {result ? <Result response={result} /> : null}
    </section>
  );
}
