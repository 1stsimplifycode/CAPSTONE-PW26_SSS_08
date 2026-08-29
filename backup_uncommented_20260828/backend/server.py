"""The HTTP surface of the backend: a small, explicit router over :mod:`backend.service`.

Standard library only. The project's ``requirements.txt`` is deliberately short and pinned
because every dependency is something a reader has to trust before they can trust a
number, and a web framework would be a large one to add for five routes.

What this module is allowed to do is narrow by construction:

* it parses a path against a fixed table of routes and rejects anything else;
* it parses a JSON body, capped in size, and hands it to the service as a dict;
* it returns whatever the service returns, plus a status code.

It never touches the filesystem, never builds a command line, and never sees a module's
inputs before :func:`backend.registry.validate` has range-checked them. ``--force`` is not
a parameter of any route here, so there is no request that can regenerate a protected
artifact.

Run it with ``python -m backend.server``.

EXTRACTION NOTE. This is the source repository's ``backend/server.py`` with the routes for
surfaces outside the statistical subsystem removed: the simulated brokerage (account,
funds, orders, portfolio, notifications, audit, watchlists), the product read models
(market, instruments, indices, alignment, evidence) and the document-upload path. The
week-capability gate went with them; it sequences a demonstration rather than computing
anything, and its registry is not part of this extraction. Everything that remains -- the handler plumbing, the body cap and
drain, the origin and token checks, ``_dispatch``, ``_code_for``, ``_query``, ``serve``
and ``main`` -- is unchanged.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from backend import (
    BACKEND_VERSION,
    INVALID_INPUT,
    REFUSALS,
    UNKNOWN_MODULE,
)
from backend import service as svc

DEFAULT_PORT = 8787

#: Requests larger than this are refused unread. Nothing this API accepts is large: the
#: biggest legitimate body is a date range, a symbol list and a handful of numbers.
MAX_BODY_BYTES = 64 * 1024

#: An oversized body is drained up to this much so the caller can read the refusal.
#: Beyond it the connection is simply closed: reading further would be the denial of
#: service the size cap exists to refuse.
DRAIN_LIMIT_BYTES = 8 * 1024 * 1024

#: Browsers that may call this service. A wildcard would let any page a reader has open
#: drive their local backend, which is not a trade this project needs to make.
ALLOWED_ORIGINS = tuple(
    o.strip() for o in os.environ.get(
        "AEGIS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
)

#: Optional shared secret. Unset locally; set it when the service is reachable from
#: anywhere but the machine it runs on. The value is never echoed in a response.
AUTH_TOKEN = os.environ.get("AEGIS_BACKEND_TOKEN", "")

#: HTTP status per response status. A refusal is not a server error: the guard working is
#: a correct outcome, and 5xx would tell a client to retry something that will refuse
#: again for the same good reason.
HTTP_STATUS = {
    "OK": 200,
    "INVALID_INPUT": 400,
    "INSUFFICIENT_DATA": 422,
    "INPUTS_MISSING": 409,
    "PROTECTED": 200,
    "NOT_YET_EXECUTED": 501,
    "BLOCKED": 409,
    "UNKNOWN_MODULE": 404,
    "TIMEOUT": 504,
    "FAILED": 500,
    "PARTIAL": 200,
}

MODULE_ID = r"(?P<module_id>[A-Za-z]+-\d{2})"


def _routes() -> list[tuple[str, re.Pattern, str]]:
    return [
        ("GET", re.compile(r"^/api/health$"), "health"),
        ("GET", re.compile(r"^/api/catalogue$"), "catalogue"),
        ("GET", re.compile(r"^/api/modules$"), "modules"),
        ("GET", re.compile(r"^/api/modules/%s$" % MODULE_ID), "module"),
        ("POST", re.compile(r"^/api/modules/%s/run$" % MODULE_ID), "run_module"),
    ]


ROUTES = _routes()


class Handler(BaseHTTPRequestHandler):
    server_version = "aegis-backend/%s" % BACKEND_VERSION
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:            # noqa: A002
        sys.stderr.write("[backend] %s %s\n" % (self.address_string(), fmt % args))

    def _origin_ok(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin is None:
            return ""            # a non-browser client; nothing to allow or deny
        return origin if origin in ALLOWED_ORIGINS else None

    def _send(self, status_code: int, payload: dict) -> None:
        # Through the strict writer, not `json.dumps`. Python emits bare NaN and Infinity
        # by default and `json.loads` reads them back, so a Python-only test never
        # notices — but `JSON.parse` rejects the *whole document*, and the proxy then
        # reports the backend as unreachable and serves a stored artifact instead. The
        # analysis had succeeded; the reader was told it had not. `research/core/jsonio`
        # already existed for exactly this failure in the exported bundles; the live
        # response path simply never used it.
        from research.core import jsonio
        body = jsonio.dumps(payload, indent=None).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self._origin_ok()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status_code: int, code: str, reason: str, remedy: str) -> None:
        self._send(status_code, {
            "backend_version": BACKEND_VERSION,
            "status": code,
            "error": {"code": code, "reason": reason, "remedy": remedy},
        })

    def _body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            # Refusing is not enough: a client that is still sending cannot read the
            # answer if the socket closes underneath it, and would see a dropped
            # connection instead of the reason. So the body is drained first — bounded,
            # because draining an unbounded one would be the very thing being refused.
            if length <= DRAIN_LIMIT_BYTES:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            self._error(413, INVALID_INPUT,
                        "request body is larger than %d bytes" % MAX_BODY_BYTES,
                        "Send only the declared inputs for this module.")
            return None
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._error(400, INVALID_INPUT, "the request body is not valid JSON",
                        "Send a JSON object of the module's declared inputs.")
            return None
        if not isinstance(parsed, dict):
            self._error(400, INVALID_INPUT, "the request body must be a JSON object",
                        "Send {\"date_from\": \"...\"} rather than a list or a string.")
            return None
        return parsed

    def _authorised(self) -> bool:
        if not AUTH_TOKEN:
            return True
        supplied = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if supplied == AUTH_TOKEN:
            return True
        self._error(401, "UNAUTHORISED", "this backend requires a bearer token",
                    "Set the same token the service was started with.")
        return False

    # -- verbs -------------------------------------------------------------------

    def do_OPTIONS(self) -> None:                              # noqa: N802
        origin = self._origin_ok()
        self.send_response(204 if origin is not None else 403)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, "
                                                             "Authorization")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:                                  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:                                 # noqa: N802
        self._dispatch("POST")

    # -- routing -----------------------------------------------------------------

    def _dispatch(self, verb: str) -> None:
        if self._origin_ok() is None:
            self._error(403, "FORBIDDEN_ORIGIN",
                        "this backend does not accept browser requests from that origin",
                        "Set AEGIS_ALLOWED_ORIGINS to include it, deliberately.")
            return
        if not self._authorised():
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        # Method first, then path. Matching on the path alone means a route that exists
        # under two verbs answers 405 for whichever verb happens to be declared second.
        candidates = [(m, pat, n) for (m, pat, n) in ROUTES if pat.match(path)]
        if candidates and not any(m == verb for (m, _p, _n) in candidates):
            allowed = ", ".join(sorted({m for (m, _p, _n) in candidates}))
            self._error(405, "METHOD_NOT_ALLOWED",
                        "%s is served over %s" % (path, allowed),
                        "Use %s for this route." % allowed)
            return
        for method, pattern, name in candidates:
            if method != verb:
                continue
            match = pattern.match(path)
            body = self._body() if verb == "POST" else _query(parsed.query)
            if body is None:
                return                     # _body already answered
            try:
                status_code, payload = self._handle(name, match.groupdict(), body)
            except Exception:              # noqa: BLE001 - reported, never leaked
                traceback.print_exc()
                self._error(500, "FAILED",
                            "the backend failed while handling this request",
                            "This is a defect in the backend, not in your request.")
                return
            self._send(status_code, payload)
            return

        self._error(404, "UNKNOWN_ROUTE", "no route matches %s" % path,
                    "GET /api/health lists the service; GET /api/catalogue lists "
                    "every module.")

    def _handle(self, name: str, params: dict, body: dict) -> tuple[int, dict]:
        if name == "health":
            return 200, svc.health()
        if name == "catalogue":
            return 200, svc.catalogue()
        if name == "modules":
            return 200, {"backend_version": BACKEND_VERSION,
                         "modules": [m.to_dict()
                                     for m in svc.reg.modules().values()]}
        if name == "module":
            payload = svc.describe(params["module_id"].upper())
            if payload.get("status") == UNKNOWN_MODULE:
                return 404, payload
            return 200, payload
        if name == "run_module":
            payload = svc.run_module(params["module_id"].upper(), body)
            return _code_for(payload), payload
        raise AssertionError("unrouted handler %r" % name)     # pragma: no cover


def _code_for(payload: dict) -> int:
    status = payload.get("status", "FAILED")
    return HTTP_STATUS.get(status, 200 if status in REFUSALS else 500)


def _query(raw: str) -> dict:
    """Query parameters as a flat dict; repeated keys become a list.

    Only GET routes use this, and none of them run anything, so the loose shape here
    cannot reach an adapter. Run requests carry a JSON body.
    """
    out: dict = {}
    for key, values in parse_qs(raw, keep_blank_values=False).items():
        out[key] = values[0] if len(values) == 1 else values
    return out


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    counts = svc.health()
    sys.stderr.write(
        "[backend] aegis %s on http://%s:%d — %d weeks, %d modules, %d live-capable\n"
        % (BACKEND_VERSION, host, port, counts["weeks"], counts["modules"],
           counts["live_capable_modules"]))
    sys.stderr.write("[backend] origins allowed: %s\n" % ", ".join(ALLOWED_ORIGINS))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[backend] stopped\n")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    port = int(os.environ.get("AEGIS_BACKEND_PORT", DEFAULT_PORT))
    host = os.environ.get("AEGIS_BACKEND_HOST", "127.0.0.1")
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    serve(port, host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
