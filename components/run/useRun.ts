// Runs in the browser: it sends requests and tracks what came back.
'use client';

/**
 * The request half of a run panel: state, the POST, and the four outcomes.
 *
 * A run ends in exactly one of four states and each is rendered differently, because
 * collapsing them would mean showing a user the wrong thing:
 *
 * * **a result** — the service answered, whether it computed or replayed;
 * * **a refusal** — the service answered and declined, with a reason and a remedy; it
 *   arrives as an ordinary response and is rendered from the response, not invented here;
 * * **a transport failure** — nothing answered. This hook does not manufacture a response
 *   for that case: an empty panel with an explanation is honest, a fabricated payload is
 *   not;
 * * **still running** — with the module's declared typical duration, so a slow module
 *   reads as slow rather than as broken.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * PRESSING THE RUN BUTTON, AND THE FOUR THINGS THAT CAN HAPPEN NEXT.
 *
 * Most code collapses these four into two: "it worked" and "an error". That is exactly
 * what the docstring says must not happen, and the reason is that a reader shown the wrong
 * one of these draws the wrong conclusion.
 *
 * 1. A RESULT. It answered. Show the numbers.
 *
 * 2. A REFUSAL. It answered, and said no -- with a reason and a way forward. "That result
 *    is frozen", "your date range holds no data".
 *    THE CRUCIAL DETAIL: the refusal is DISPLAYED FROM THE SERVER'S OWN REPLY. This file
 *    does not compose its own explanation. Otherwise there would be two versions of the
 *    reason -- one on the server, one here -- and they would drift.
 *
 * 3. A TRANSPORT FAILURE. Nothing answered at all. The service is not running, or the
 *    network is down.
 *    AND HERE IS THE BEST DECISION IN THE FILE: it would be easy to invent a reply saying
 *    FAILED, so the rest of the page has something normal-shaped to display. That is
 *    explicitly refused. Inventing a reply means putting words into the server's mouth
 *    when the server said nothing at all. So the panel stays empty, and an explanation is
 *    shown beside it.
 *
 * 4. STILL RUNNING. And -- a lovely touch -- shown alongside how long this module usually
 *    takes. Without that, a module that honestly needs forty seconds is indistinguishable
 *    from one that has hung, and the visitor gives up on something that was working.
 */
import { useCallback, useRef, useState } from 'react';

import type { RunResponse, WeekRunResponse } from '@/lib/runTypes';

// The three stages a run passes through.
export type Phase = 'idle' | 'running' | 'done';

// What we show when nothing answered at all. Note it has the same reason/remedy shape as a
// real error -- so the display treats both the same way, even though only one came from
// the server.
export interface Transport {
  reason: string;
  remedy: string;
}

export function useRun<T extends RunResponse | WeekRunResponse>(endpoint: string) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<T | null>(null);
  // Kept SEPARATE from `result`, which is what keeps outcomes 2 and 3 distinguishable. A
  // refusal lives in `result`; a silence lives in `transport`. One variable for both would
  // make them indistinguishable to whatever displays them.
  const [transport, setTransport] = useState<Transport | null>(null);
  const [ranAt, setRanAt] = useState<string | null>(null);
  // A second click while a run is in flight must not race the first one's result into
  // view after the second's; the older request is abandoned rather than rendered.
  // PLAIN ENGLISH: a real and nasty bug, prevented. Click Run, then change a setting and
  // click again. Two requests are now in the air. If the FIRST one happens to come back
  // second -- perfectly possible -- you would be shown the old answer, labelled with your
  // new settings. It would look completely normal and be entirely wrong.
  // So starting a new request cancels the old one outright.
  const inflight = useRef<AbortController | null>(null);

  const run = useCallback(
    async (body: Record<string, unknown>) => {
      // Cancel anything already running. `?.` means "only if there is one".
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;
      setPhase('running');
      // Clear any previous failure, so an old message cannot linger beside a new run.
      setTransport(null);

      try {
        const res = await fetch(endpoint, {
          // POST, because this DOES something rather than merely reading.
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          // The cancellation handle, which is what makes the abort above work.
          signal: controller.signal,
        });
        // Read as plain text first, THEN try to interpret it. Reading it as JSON directly
        // would throw an unhelpful error with nothing to inspect; this way we still have
        // the raw text and can report a precise problem.
        const text = await res.text();
        let payload: unknown;
        try {
          payload = JSON.parse(text);
        } catch {
          // The service answered with something that is not a result at all -- an HTML
          // error page from a proxy, most likely.
          setResult(null);
          setTransport({
            // Precisely worded: it ANSWERED, but not with a result. That points at a
            // misconfiguration rather than at a service being down, which is a different
            // thing to go and check.
            reason: 'The service answered with something that is not a result.',
            remedy: 'Check that the analysis backend is the one this build expects.',
          });
          setPhase('done');
          return;
        }
        // Success -- and note this covers outcomes 1 AND 2 together. A refusal is a
        // perfectly valid reply and is stored as one; whatever displays it reads the status
        // and shows the server's own reason.
        setResult(payload as T);
        setRanAt(new Date().toISOString());
        setPhase('done');
      } catch (err) {
        // If WE cancelled this request, say nothing at all -- a newer request is already
        // running and about to set its own state. Reporting an error here would flash a
        // failure message every time somebody clicked twice.
        if (controller.signal.aborted) return;
        // OUTCOME 3. Note `setResult(null)` -- no reply is invented. The panel will be
        // empty, with an explanation beside it.
        setResult(null);
        setTransport({
          // Two different messages for two different situations, because they call for
          // different responses from the reader.
          reason:
            err instanceof Error && err.name === 'TimeoutError'
              // It is running, just slowly.
              ? 'The request took longer than this page waits.'
              // It is not there at all.
              : 'No answer from the analysis service.',
          remedy:
            // The exact command to start it, AND the reassurance that the rest of the site
            // still works without it. That last clause matters: it tells the reader the
            // whole page is not broken, only the live-run part.
            'Start it with run_dev.bat, or open this page against a deployment that has ' +
            'one. Stored results remain readable without it.',
        });
        setPhase('done');
      } finally {
        // `finally` runs whatever happened. Clear the handle -- but only if it is still
        // OURS. Without that check, a slow old request finishing late would wipe out the
        // handle belonging to the newer request, and the newer one could no longer be
        // cancelled.
        if (inflight.current === controller) inflight.current = null;
      }
    },
    [endpoint],
  );

  // Clear everything and stop anything in flight.
  const reset = useCallback(() => {
    inflight.current?.abort();
    setPhase('idle');
    setResult(null);
    setTransport(null);
  }, []);

  // Hand back everything the panel needs: where we are, what came back, what failed, when
  // it ran, and the two actions.
  return { phase, result, transport, ranAt, run, reset };
}
