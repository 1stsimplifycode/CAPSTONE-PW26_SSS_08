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
 */
import { NextResponse } from 'next/server';

import { listModules } from '@/lib/modules';
import type { RunResponse } from '@/lib/runTypes';
import { getWeeks } from '@/lib/weeks';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/** Requests larger than this are refused unread: nothing this API accepts is large. */
const MAX_BODY_BYTES = 64 * 1024;

/** How long to wait for the backend before treating it as absent. */
const TIMEOUT_MS = Number(process.env.AEGIS_BACKEND_TIMEOUT_MS ?? 120_000);

const MODULE_ID = String.raw`[A-Za-z]+-\d{2}`;

/** The complete set of paths this proxy will forward. Anything else is a 404. */
const ROUTES: { method: 'GET' | 'POST'; pattern: RegExp }[] = [
  { method: 'GET', pattern: new RegExp(`^health$`) },
  { method: 'GET', pattern: new RegExp(`^catalogue$`) },
  { method: 'GET', pattern: new RegExp(`^modules$`) },
  { method: 'GET', pattern: new RegExp(`^modules/${MODULE_ID}$`) },
  { method: 'POST', pattern: new RegExp(`^modules/${MODULE_ID}/run$`) },
];

function backendBase(): string | null {
  const raw = process.env.AEGIS_BACKEND_URL?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url.origin;
  } catch {
    return null;
  }
}

function refusal(status: number, code: string, reason: string, remedy: string) {
  return NextResponse.json(
    { status: code, backend: 'unavailable', error: { code, reason, remedy } },
    { status, headers: { 'Cache-Control': 'no-store' } },
  );
}

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
  const matching = ROUTES.filter((r) => r.pattern.test(path));
  const route = matching.find((r) => r.method === method) ?? matching[0];
  if (!route) {
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
    if (body.length > MAX_BODY_BYTES) {
      return refusal(
        413,
        'INVALID_INPUT',
        'the request body is larger than this endpoint accepts',
        'Send only the declared inputs for this module.',
      );
    }
    if (body.trim() === '') body = '{}';
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('not an object');
      }
    } catch {
      return refusal(
        400,
        'INVALID_INPUT',
        'the request body is not a JSON object',
        'Send an object of the module inputs, for example {"date_from": "2022-01-01"}.',
      );
    }
  }

  const base = backendBase();
  if (base) {
    const query = new URL(request.url).search;
    const forwarded = await forward(base, path, method, body, query);
    if (forwarded) return forwarded;
  }
  return await fallback(path, base === null ? 'not-configured' : 'unreachable');
}

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
  const token = process.env.AEGIS_BACKEND_TOKEN?.trim();
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const upstream = await fetch(`${base}/api/${path}${search}`, {
      method,
      headers,
      body: method === 'POST' ? body : undefined,
      signal: controller.signal,
      cache: 'no-store',
    });
    const text = await upstream.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      // A non-JSON answer is not the backend this proxy knows about; do not pass it on.
      return null;
    }
    return NextResponse.json(
      { ...(payload as Record<string, unknown>), backend: 'reachable' },
      { status: upstream.status, headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    // Unreachable, refused, or slower than the timeout. The caller is told the backend is
    // unavailable; it is never told which host failed or why.
    return null;
  } finally {
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
async function fallback(path: string, why: 'unreachable' | 'not-configured') {
  const reason =
    why === 'not-configured'
      ? 'This deployment has no analysis backend configured, so nothing can be computed ' +
        'on request here.'
      : 'The analysis backend did not answer, so nothing was computed for this request.';
  const remedy =
    'Start it locally with `python -m backend.server` and set AEGIS_BACKEND_URL. Until ' +
    'then, the stored result below is what the pipeline produced when it last ran.';

  const runModule = /^modules\/([A-Za-z]+-\d{2})\/run$/.exec(path);
  if (runModule) {
    return NextResponse.json(
      {
        ...(await artifactResponse(runModule[1].toUpperCase(), reason, remedy)),
        backend: why,
      },
      { status: 200, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  if (path === 'health') {
    const weeks = await getWeeks();
    return NextResponse.json(
      {
        status: 'BACKEND_UNAVAILABLE',
        backend: why,
        backend_version: 'frontend-fallback',
        weeks: weeks.rows.length,
        live_capable_modules: 0,
        error: { code: 'BACKEND_UNAVAILABLE', reason, remedy },
      },
      { status: 200, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  return refusal(503, 'BACKEND_UNAVAILABLE', reason, remedy);
}

/**
 * A module's last stored result, in the response contract's shape.
 *
 * Every number here was read from an exported artifact and carries the artifact path it
 * came from. Nothing is invented: a module whose artifact is absent returns no metrics and
 * says so.
 */
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
    .filter((m) => m.display !== null)
    .map((m) => ({
      key: m.label,
      label: m.label,
      value: m.value,
      display: m.display ?? '',
      format: m.format,
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
    mode: 'VERIFIED_ARTIFACT',
    mode_label: 'Verified experiment result',
    mode_meaning:
      'Read from the artifact the pipeline last wrote. Nothing was computed for this ' +
      'request, and the inputs on the form were not applied.',
    experiment_id: mod.research.experiment_id,
    dataset: { source: 'stored artifact', paths: mod.research.outputs },
    inputs: {},
    metrics,
    series: [],
    uncertainty: {},
    observations: mod.research.last_run?.message ? [mod.research.last_run.message] : [],
    figures: mod.figures,
    tables: mod.tables,
    provenance: {
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
