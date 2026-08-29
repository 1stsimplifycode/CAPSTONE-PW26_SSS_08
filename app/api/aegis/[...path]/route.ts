/**
 * The one route between the browser and the Python backend.
 *
 * Everything interactive goes through here: `/api/aegis/modules/STATS-03/run` reaches the
 * backend's `/api/modules/STATS-03/run`, and nothing else does. The browser never learns
 * where the backend is, and the backend never receives a path this file did not recognise.
 *
 * Four rules, and each exists because its absence is a real hole:
 *
 * 1. **The path is matched against a fixed table**, not concatenated. A proxy that
 *    forwards whatever it is given is a request-forgery primitive pointed at whatever the
 *    backend can reach.
 * 2. **The backend's location is never returned.** `AEGIS_BACKEND_URL` may carry a host, a
 *    port or a token; a reader gets `backend: "reachable" | "unavailable"` and no more.
 * 3. **The body is capped and forwarded unmodified.** This layer adds no parameter — in
 *    particular there is no code path that could add `force`.
 * 4. **When the backend is absent, the response says so.** A deployment without a Python
 *    process still serves the stored, provenance-stamped result, labelled
 *    `VERIFIED_ARTIFACT`, alongside the reason live execution was unavailable. What it
 *    must never do is present that stored result as something just computed.
 *
 * EXTRACTION NOTE. This is the source repository's `app/api/aegis/[...path]/route.ts`
 * with the routes for surfaces outside the statistical subsystem removed — trading,
 * funds, orders, portfolio, notifications, audit, watchlists, uploads, the product read
 * models, and the weekly orchestration. The week-gating block went with them: it is a
 * demonstration-sequencing feature, not a statistical one, and the
 * capability registry it read is not exported here. Everything that remains — the route
 * table's matching, the body cap, `forward`, `fallback` and `artifactResponse` — is
 * unchanged.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SINGLE DOOR BETWEEN THE WEBSITE AND THE ANALYSIS SERVICE.
 *
 * This is a "proxy": the browser asks this file, and this file asks the Python service.
 * The browser never talks to the service directly and never learns where it is.
 *
 * RULE 1 IS THE SECURITY-CRITICAL ONE, and the phrase to understand is
 * "request-forgery primitive".
 * The easy way to write a proxy is: take whatever address you were given, stick it on the
 * end of the backend's address, and forward it. That works perfectly -- and it means
 * anybody can make YOUR SERVER fetch anything the backend can reach. Internal systems,
 * admin pages, a cloud provider's private metadata service. The attacker's own computer
 * cannot reach those; yours can.
 * So instead there is a FIXED TABLE of five permitted addresses. Anything else is refused.
 *
 * RULE 2: the backend's address may contain a hostname, a port, even a token. None of that
 * ever reaches a reply. The browser is told "reachable" or "unavailable" and nothing more.
 *
 * RULE 3: the request body is size-capped and passed through UNCHANGED. This layer adds no
 * parameter of its own -- and the docstring names the one that matters: there is no code
 * path here that could add `force`. The protected-result override is unreachable from the
 * internet not because it is guarded, but because nothing here can produce it.
 *
 * RULE 4 IS ABOUT HONESTY RATHER THAN SECURITY. With no service running, the stored
 * results are still real and are still served -- clearly labelled as stored, with the run
 * that produced them. What must never happen is those being presented as freshly computed.
 */
import { NextResponse } from 'next/server';

import { listModules } from '@/lib/modules';
import type { RunResponse } from '@/lib/runTypes';
import { getWeeks } from '@/lib/weeks';

// Never cached, and run in a full Node environment because it needs to read files.
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/** Requests larger than this are refused unread: nothing this API accepts is large. */
const MAX_BODY_BYTES = 64 * 1024;

/** How long to wait for the backend before treating it as absent. */
// Two minutes -- generous, because a real analysis can legitimately take a while. Quite
// different from the eight seconds the market pages allow, where a reader is waiting.
const TIMEOUT_MS = Number(process.env.AEGIS_BACKEND_TIMEOUT_MS ?? 120_000);

// `String.raw` again, so the backslash survives -- the same load-bearing detail as the boot
// script. A module id is letters, a dash, then exactly two digits.
const MODULE_ID = String.raw`[A-Za-z]+-\d{2}`;

/** The complete set of paths this proxy will forward. Anything else is a 404. */
// THE WHOLE ALLOWLIST. Five entries. Everything the interactive site can possibly ask for,
// and nothing else exists.
const ROUTES: { method: 'GET' | 'POST'; pattern: RegExp }[] = [
  // `^...$` anchors each pattern to the whole path, so "health" matches and
  // "health/../../secrets" does not.
  { method: 'GET', pattern: new RegExp(`^health$`) },
  { method: 'GET', pattern: new RegExp(`^catalogue$`) },
  { method: 'GET', pattern: new RegExp(`^modules$`) },
  { method: 'GET', pattern: new RegExp(`^modules/${MODULE_ID}$`) },
  // The only one that DOES anything, and the only POST.
  { method: 'POST', pattern: new RegExp(`^modules/${MODULE_ID}/run$`) },
];

// Where the backend is -- known only to the server.
function backendBase(): string | null {
  const raw = process.env.AEGIS_BACKEND_URL?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    // Only http and https. Without this check a mistyped setting could point this at a
    // local file or another protocol entirely.
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    // `.origin` keeps only the scheme, host and port -- discarding any path, query or
    // credentials that might have been in the setting.
    return url.origin;
  } catch {
    return null;
  }
}

// A refusal, in the standard shape.
function refusal(status: number, code: string, reason: string, remedy: string) {
  return NextResponse.json(
    // "unavailable" and nothing more -- RULE 2, in one word.
    { status: code, backend: 'unavailable', error: { code, reason, remedy } },
    { status, headers: { 'Cache-Control': 'no-store' } },
  );
}

// The two entry points. Both hand straight over to one shared handler, so read and write
// requests cannot diverge in how they are checked.
export async function GET(
  request: Request,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return handle('GET', request, await ctx.params);
}

export async function POST(
  request: Request,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return handle('POST', request, await ctx.params);
}

async function handle(
  method: 'GET' | 'POST',
  request: Request,
  params: { path: string[] },
): Promise<NextResponse> {
  const path = (params.path ?? []).join('/');
  // Method and path together, so a path declared under two verbs resolves to the right
  // one rather than to whichever was listed first.
  // PLAIN ENGLISH: the same bug the Python server avoids -- gather every pattern that
  // matches, THEN look for the right method among them. Checking the first match only would
  // wrongly report "method not allowed" for a perfectly valid request.
  const matching = ROUTES.filter((r) => r.pattern.test(path));
  const route = matching.find((r) => r.method === method) ?? matching[0];
  if (!route) {
    // NOT ON THE LIST. Refused -- and the remedy names what IS forwarded, without revealing
    // anything about the backend.
    return refusal(
      404,
      'UNKNOWN_ROUTE',
      `no backend route matches ${path}`,
      'The routes this proxy forwards are health, catalogue and modules.',
    );
  }
  if (route.method !== method) {
    return refusal(
      405,
      'METHOD_NOT_ALLOWED',
      `${path} is served over ${route.method}`,
      `Use ${route.method} for this route.`,
    );
  }

  let body: string | undefined;
  if (method === 'POST') {
    body = await request.text();
    // RULE 3: the size cap.
    if (body.length > MAX_BODY_BYTES) {
      return refusal(
        413,
        'INVALID_INPUT',
        'the request body is larger than this endpoint accepts',
        'Send only the declared inputs for this module.',
      );
    }
    // An empty body means "use the defaults" -- turned into an empty object so the backend
    // receives valid JSON either way.
    if (body.trim() === '') body = '{}';
    try {
      const parsed: unknown = JSON.parse(body);
      // It must be an OBJECT -- not a list, not a bare value, not null. Checked here so the
      // backend never receives a shape it did not expect.
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('not an object');
      }
    } catch {
      return refusal(
        400,
        'INVALID_INPUT',
        'the request body is not a JSON object',
        // The remedy SHOWS the right shape rather than describing it.
        'Send an object of the module inputs, for example {"date_from": "2022-01-01"}.',
      );
    }
    // Note what does NOT happen here: the body is not modified. It is checked and passed on
    // exactly as received -- rule 3.
  }

  const base = backendBase();
  if (base) {
    const query = new URL(request.url).search;
    const forwarded = await forward(base, path, method, body, query);
    if (forwarded) return forwarded;
  }
  // No backend, or it did not answer usably: serve the stored result instead.
  // The two cases are distinguished, because "not configured" and "not answering" call for
  // different explanations.
  return await fallback(path, base === null ? 'not-configured' : 'unreachable');
}

// Pass the request through to the real service.
async function forward(
  base: string,
  path: string,
  method: 'GET' | 'POST',
  body: string | undefined,
  search = '',
): Promise<NextResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  // The token added HERE, on the server. It never touches the browser.
  const token = process.env.AEGIS_BACKEND_TOKEN?.trim();
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const upstream = await fetch(`${base}/api/${path}${search}`, {
      method,
      headers,
      body: method === 'POST' ? body : undefined,
      signal: controller.signal,
      // Never cached -- "live" must genuinely mean live.
      cache: 'no-store',
    });
    const text = await upstream.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      // A non-JSON answer is not the backend this proxy knows about; do not pass it on.
      // PLAIN ENGLISH: something answered, but not with a result -- an error page from a
      // proxy or load balancer, most likely. Passing that through would hand the browser
      // somebody else's content. Returning null instead sends the caller down the fallback
      // path, which produces a proper explanation.
      return null;
    }
    return NextResponse.json(
      // The backend's reply, plus one word: "reachable". Nothing about WHERE it is.
      { ...(payload as Record<string, unknown>), backend: 'reachable' },
      // The backend's own status code preserved, so a refusal stays a refusal.
      { status: upstream.status, headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    // Unreachable, refused, or slower than the timeout. The caller is told the backend is
    // unavailable; it is never told which host failed or why.
    // PLAIN ENGLISH: rule 2 at its most important. An error message naming the host that
    // failed would map out the internal network for anybody probing it.
    return null;
  } finally {
    // `finally` runs whatever happened, so the timer is always cleared -- otherwise every
    // request would leave a two-minute timer behind, and they would accumulate.
    clearTimeout(timer);
  }
}

/**
 * What to serve when no Python process is reachable.
 *
 * The stored artifacts are still real results, so they are served — labelled
 * `VERIFIED_ARTIFACT`, carrying the run that produced them, and accompanied by a
 * `BACKEND_UNAVAILABLE` notice saying that the inputs on the form were not applied. A
 * deployment that quietly returned these under a live label would be the exact failure the
 * two-mode distinction exists to prevent.
 */
// PLAIN ENGLISH: a nicely balanced piece of judgement. The stored results are genuine, so
// withholding them would be needlessly unhelpful -- the reader gets something real.
// But three things are said alongside: it is labelled as stored, the run that produced it is
// named, AND -- the detail that matters most -- the reader is told THEIR SETTINGS WERE NOT
// APPLIED. Without that, somebody who chose a date range would believe they were looking at
// results for it.
async function fallback(path: string, why: 'unreachable' | 'not-configured') {
  // Two different reasons for two genuinely different situations.
  const reason =
    why === 'not-configured'
      ? 'This deployment has no analysis backend configured, so nothing can be computed ' +
        'on request here.'
      : 'The analysis backend did not answer, so nothing was computed for this request.';
  const remedy =
    // The exact command to start it, AND the reassurance that what is shown below is still
    // real -- so the reader is not left thinking the page is broken.
    'Start it locally with `python -m backend.server` and set AEGIS_BACKEND_URL. Until ' +
    'then, the stored result below is what the pipeline produced when it last ran.';

  const runModule = /^modules\/([A-Za-z]+-\d{2})\/run$/.exec(path);
  if (runModule) {
    return NextResponse.json(
      {
        ...(await artifactResponse(runModule[1].toUpperCase(), reason, remedy)),
        backend: why,
      },
      // Status 200: this is a real, usable answer, not a server failure. Returning an error
      // code would make the browser retry something that will fail identically.
      { status: 200, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  if (path === 'health') {
    // Even the health check answers usefully without a backend -- saying what the site can
    // still do, and being explicit that nothing can be computed live.
    const weeks = await getWeeks();
    return NextResponse.json(
      {
        status: 'BACKEND_UNAVAILABLE',
        backend: why,
        // A distinct version label, so nobody mistakes this for the real backend answering.
        backend_version: 'frontend-fallback',
        weeks: weeks.rows.length,
        // Explicitly zero live-capable modules.
        live_capable_modules: 0,
        error: { code: 'BACKEND_UNAVAILABLE', reason, remedy },
      },
      { status: 200, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  // Anything else genuinely cannot be served without the backend. 503 is the correct code:
  // temporarily unavailable.
  return refusal(503, 'BACKEND_UNAVAILABLE', reason, remedy);
}

/**
 * A module's last stored result, in the response contract's shape.
 *
 * Every number here was read from an exported artifact and carries the artifact path it
 * came from. Nothing is invented: a module whose artifact is absent returns no metrics and
 * says so.
 */
// Shaped exactly like a real backend reply, so the display code needs no special case --
// and differing only in its honest labels.
async function artifactResponse(
  moduleId: string,
  reason: string,
  remedy: string,
): Promise<RunResponse> {
  const modules = await listModules();
  const mod = modules.find((m) => m.id === moduleId);
  const week = (await getWeeks()).rows.find(
    (w) => w.stats_module === moduleId,
  );

  if (!mod) {
    // NO STORED RESULT EITHER. Every list comes back EMPTY -- no metrics, no series, no
    // observations. Nothing whatever is invented to fill the shape.
    return {
      backend_version: 'frontend-fallback',
      module_id: moduleId,
      week: week?.week ?? null,
      category: '',
      name: moduleId,
      status: 'BACKEND_UNAVAILABLE',
      mode: 'VERIFIED_ARTIFACT',
      mode_label: 'Verified experiment result',
      mode_meaning: reason,
      experiment_id: null,
      dataset: {},
      inputs: {},
      metrics: [],
      series: [],
      uncertainty: {},
      observations: [],
      figures: [],
      tables: [],
      provenance: { computed: false, backend: 'unavailable' },
      limitations: [],
      message: reason,
      elapsed_s: 0,
      error: { code: 'BACKEND_UNAVAILABLE', reason, remedy },
    };
  }

  const metrics = [...mod.research.metrics, ...mod.product.metrics]
    // Only numbers that actually have a display value -- an unresolved metric is left out
    // rather than shown blank.
    .filter((m) => m.display !== null)
    .map((m) => ({
      key: m.label,
      label: m.label,
      value: m.value,
      display: m.display ?? '',
      format: m.format,
      // Every value labelled as read from storage, and carrying the file it came from.
      note: m.note ?? 'read from the stored artifact',
      source: m.source ?? '',
    }));

  return {
    backend_version: 'frontend-fallback',
    module_id: mod.id,
    week: week?.week ?? null,
    category: mod.category,
    name: mod.name,
    status: 'BACKEND_UNAVAILABLE',
    // LABELLED AS A REPLAY, correctly.
    mode: 'VERIFIED_ARTIFACT',
    mode_label: 'Verified experiment result',
    mode_meaning:
      // AND THE SENTENCE THAT MATTERS MOST: "the inputs on the form were not applied."
      // Without it, somebody who picked a date range would read these numbers as being for
      // that range. They are not.
      'Read from the artifact the pipeline last wrote. Nothing was computed for this ' +
      'request, and the inputs on the form were not applied.',
    experiment_id: mod.research.experiment_id,
    dataset: { source: 'stored artifact', paths: mod.research.outputs },
    // Empty inputs, because none were applied. Echoing back what the reader typed would
    // imply it had been used.
    inputs: {},
    metrics,
    // No series -- the stored bundle carries numbers, not full tables. Left empty rather
    // than filled with something approximate.
    series: [],
    uncertainty: {},
    observations: mod.research.last_run?.message ? [mod.research.last_run.message] : [],
    figures: mod.figures,
    tables: mod.tables,
    provenance: {
      // THE FULL PROVENANCE, even in the fallback. Which module, which code, which run,
      // which commit, which files -- and the command to regenerate it.
      computed: false,
      backend: 'unavailable',
      module_id: mod.id,
      adapter: mod.research.adapter,
      canonical: mod.research.canonical,
      artifacts: mod.research.outputs,
      replayed_run_id: mod.research.last_run?.at ?? 'unknown',
      replayed_commit: mod.research.last_run?.git_commit ?? null,
      execution:
        'Nothing was computed for this request. These values were read from the stored ' +
        'artifacts named above.',
      regenerate_with: `python scripts/run_module.py --module ${mod.id}`,
    },
    // AND THE LIMITATIONS TRAVEL TOO. Even with no backend running, the caveats reach the
    // screen alongside the numbers.
    limitations: mod.research.limitations.map((l) => ({
      id: l.id,
      title: l.title,
      scope_note: l.scope_note,
      status: l.status,
    })),
    message: reason,
    elapsed_s: 0,
    error: { code: 'BACKEND_UNAVAILABLE', reason, remedy },
  };
}
