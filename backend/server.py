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

PLAIN ENGLISH -- what this whole file is about:

THE FRONT DOOR. This is the bit that listens for requests from a web browser.

"STANDARD LIBRARY ONLY", and the reasoning is unusual and rather good.

Most people would reach for a ready-made web framework. This does not, and the argument is
in the first paragraph: every extra piece of borrowed software is another thing a reader
must trust before they can trust the numbers. A big framework is a great deal of code
nobody in the project has read. For five web addresses, it is not worth it.

THE SECURITY MEASURES, each guarding a specific known attack:

  A FIXED LIST OF ADDRESSES. Anything not on the list is refused. There is no clever
  matching that might be talked into something unexpected.

  A SIZE CAP ON REQUESTS. Nothing this service legitimately accepts is large. So anything
  over 64 kilobytes is refused, which stops somebody tying up the machine by sending a
  gigabyte.

  A LIST OF PERMITTED WEBSITES. Only pages from named addresses may call this. The
  alternative -- allowing anybody -- would mean any website a reader happens to have open
  could quietly drive the backend running on their own computer.

  AN OPTIONAL PASSWORD, off for local use, available if the service is ever reachable from
  further away.

  NO "FORCE" OPTION ANYWHERE. The code that can overwrite a published result does have an
  override -- and it is simply not a parameter of any web address here. So no request, of
  any shape, can reach it. Not "difficult to reach": absent.

AND ONE THING WORTH KNOWING ABOUT ERROR CODES. A refusal is NOT reported as a server
failure. If a result is frozen and refuses to be regenerated, that is the safety system
working perfectly -- so it returns a success code with an explanation. Returning a failure
code would tell the browser to try again, which would refuse again, forever, for the same
perfectly good reason.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For reading and writing JSON.
import json
# For reading environment variables.
import os
# For matching web addresses against patterns.
import re
# For talking to the terminal.
import sys
# For printing a full error report when something goes wrong internally.
import traceback
# The web server built into Python itself -- no external framework.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
# For pulling a web address apart into its pieces.
from urllib.parse import parse_qs, urlparse

# The shared status names and version label.
from backend import (
    BACKEND_VERSION,
    INVALID_INPUT,
    REFUSALS,
    UNKNOWN_MODULE,
)
# The layer that actually does the work. This file only routes; it never computes.
from backend import service as svc

# Which port to listen on if nobody says otherwise.
DEFAULT_PORT = 8787

#: Requests larger than this are refused unread. Nothing this API accepts is large: the
#: biggest legitimate body is a date range, a symbol list and a handful of numbers.
# 64 kilobytes -- generous for a few dates and names, and far too small to tie the machine up.
MAX_BODY_BYTES = 64 * 1024

#: An oversized body is drained up to this much so the caller can read the refusal.
#: Beyond it the connection is simply closed: reading further would be the denial of
#: service the size cap exists to refuse.
# PLAIN ENGLISH: a genuinely subtle point about how networks work, explained below where it
# is used.
DRAIN_LIMIT_BYTES = 8 * 1024 * 1024

#: Browsers that may call this service. A wildcard would let any page a reader has open
#: drive their local backend, which is not a trade this project needs to make.
# PLAIN ENGLISH: this is about a real attack. If any website were allowed to call this,
# then a completely unrelated page open in another tab could quietly send requests to the
# backend running on your own computer. Naming the permitted addresses closes that off.
# The list can be overridden by an environment variable, so a different setup is possible --
# but it has to be done deliberately, not by accident.
ALLOWED_ORIGINS = tuple(
    o.strip() for o in os.environ.get(
        "AEGIS_ALLOWED_ORIGINS",
        # By default only the local development website.
        "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
)

#: Optional shared secret. Unset locally; set it when the service is reachable from
#: anywhere but the machine it runs on. The value is never echoed in a response.
# That last clause matters: a service that repeats your password back in an error message
# has just written it into every log file on the way.
AUTH_TOKEN = os.environ.get("AEGIS_BACKEND_TOKEN", "")

#: HTTP status per response status. A refusal is not a server error: the guard working is
#: a correct outcome, and 5xx would tell a client to retry something that will refuse
#: again for the same good reason.
# PLAIN ENGLISH: web status codes come in families -- 200s mean success, 400s mean the
# request was wrong, 500s mean the server broke. Browsers and tools react to the family:
# they retry a 500, because a server hiccup might pass. So reporting a deliberate refusal
# as a 500 would cause endless pointless retrying of something that will always refuse.
HTTP_STATUS = {
    "OK": 200,
    # Bad request.
    "INVALID_INPUT": 400,
    # Understood, but the data cannot support an answer.
    "INSUFFICIENT_DATA": 422,
    # A conflict with the current state -- a needed file is not there.
    "INPUTS_MISSING": 409,
    # SUCCESS, with an explanation. The frozen-result guard working correctly is not an
    # error, and this line is what stops it being reported as one.
    "PROTECTED": 200,
    # Not built yet.
    "NOT_YET_EXECUTED": 501,
    "BLOCKED": 409,
    # No such module.
    "UNKNOWN_MODULE": 404,
    # Took too long.
    "TIMEOUT": 504,
    # A genuine internal failure -- the only one that really is our fault.
    "FAILED": 500,
    "PARTIAL": 200,
}

# The pattern a module name must match: letters, a dash, then exactly two digits.
# `(?P<module_id>...)` names the captured part so it can be fetched by name later. This
# tight pattern is itself a security measure: nothing else can ever reach the lookup.
MODULE_ID = r"(?P<module_id>[A-Za-z]+-\d{2})"


# THE COMPLETE LIST OF WEB ADDRESSES. Five, and nothing else exists.
def _routes() -> list[tuple[str, re.Pattern, str]]:
    return [
        # Is the service alive?
        ("GET", re.compile(r"^/api/health$"), "health"),
        # What can it do?
        ("GET", re.compile(r"^/api/catalogue$"), "catalogue"),
        # The list of modules.
        ("GET", re.compile(r"^/api/modules$"), "modules"),
        # One module's description.
        ("GET", re.compile(r"^/api/modules/%s$" % MODULE_ID), "module"),
        # And the only address that RUNS anything -- and it is a POST, which is the correct
        # method for something that does work rather than merely reading.
        ("POST", re.compile(r"^/api/modules/%s/run$" % MODULE_ID), "run_module"),
    ]


ROUTES = _routes()


# The thing that handles one incoming request.
class Handler(BaseHTTPRequestHandler):
    server_version = "aegis-backend/%s" % BACKEND_VERSION
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------------

    # Write a log line. Sent to the error stream so it does not get mixed into any output
    # another program might be reading.
    def log_message(self, fmt: str, *args) -> None:            # noqa: A002
        sys.stderr.write("[backend] %s %s\n" % (self.address_string(), fmt % args))

    # Is this browser allowed to call us?
    def _origin_ok(self) -> str | None:
        origin = self.headers.get("Origin")
        # No origin at all means it is not a browser -- a script or a command-line tool.
        # Those are not subject to this rule, because the rule protects browser users from
        # other websites, which does not apply here.
        if origin is None:
            return ""            # a non-browser client; nothing to allow or deny
        # A browser: it must be on the list. None means refused.
        return origin if origin in ALLOWED_ORIGINS else None

    # Send a reply.
    def _send(self, status_code: int, payload: dict) -> None:
        # Through the strict writer, not `json.dumps`. Python emits bare NaN and Infinity
        # by default and `json.loads` reads them back, so a Python-only test never
        # notices — but `JSON.parse` rejects the *whole document*, and the proxy then
        # reports the backend as unreachable and serves a stored artifact instead. The
        # analysis had succeeded; the reader was told it had not. `research/core/jsonio`
        # already existed for exactly this failure in the exported bundles; the live
        # response path simply never used it.
        # PLAIN ENGLISH: this is the NaN bug from jsonio.py, caught a SECOND time in a
        # different place -- and the consequence here was even more misleading. One bad
        # number made the whole reply unreadable to the browser; the website concluded the
        # backend was down and quietly showed an old saved result instead. So the analysis
        # ran perfectly, and the reader was shown stale data and told the service was
        # unavailable. The fix already existed; this one path simply was not using it.
        from research.core import jsonio
        # `indent=None` means no pretty-printing -- this is for a program, not a person, and
        # the extra spaces would only be wasted bandwidth.
        body = jsonio.dumps(payload, indent=None).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Never cache: these results can change, and a stale cached answer would be worse
        # than a slow one.
        self.send_header("Cache-Control", "no-store")
        # A security header telling the browser not to guess at the content type. Guessing
        # is how a text file occasionally gets treated as a program.
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self._origin_ok()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            # `Vary: Origin` tells caches that the answer depends on who asked, so one
            # visitor's permission cannot be handed to another.
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    # Send an error, in the same shape as everything else.
    def _error(self, status_code: int, code: str, reason: str, remedy: str) -> None:
        self._send(status_code, {
            "backend_version": BACKEND_VERSION,
            "status": code,
            # Always a code, a reason AND a remedy. Never a bare failure.
            "error": {"code": code, "reason": reason, "remedy": remedy},
        })

    # Read and check the request body.
    def _body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            # Refusing is not enough: a client that is still sending cannot read the
            # answer if the socket closes underneath it, and would see a dropped
            # connection instead of the reason. So the body is drained first — bounded,
            # because draining an unbounded one would be the very thing being refused.
            # PLAIN ENGLISH: a lovely piece of network care. If you simply hang up on
            # somebody mid-sentence, they never hear your explanation -- they just see the
            # line go dead and have no idea why. So we politely listen to the rest of what
            # they are sending, THEN explain the refusal.
            # But listening to an unlimited amount would be exactly the attack we are
            # refusing. So there is a limit: up to 8 megabytes we listen politely; beyond
            # that we hang up, because at that point they are not making a mistake.
            if length <= DRAIN_LIMIT_BYTES:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            # 413 is the standard code for "what you sent is too big".
            self._error(413, INVALID_INPUT,
                        "request body is larger than %d bytes" % MAX_BODY_BYTES,
                        "Send only the declared inputs for this module.")
            return None
        # An empty body is fine -- it means "use all the defaults".
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._error(400, INVALID_INPUT, "the request body is not valid JSON",
                        "Send a JSON object of the module's declared inputs.")
            return None
        # It must be a set of labelled settings, not a list or a bare word.
        if not isinstance(parsed, dict):
            self._error(400, INVALID_INPUT, "the request body must be a JSON object",
                        # And the remedy SHOWS the correct shape rather than describing it.
                        "Send {\"date_from\": \"...\"} rather than a list or a string.")
            return None
        return parsed

    # Check the password, if one is set.
    def _authorised(self) -> bool:
        # No password configured means no check -- the normal case when running locally.
        if not AUTH_TOKEN:
            return True
        # "Bearer " is the standard prefix; `removeprefix` strips it if present.
        supplied = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if supplied == AUTH_TOKEN:
            return True
        # Note the message says a token is REQUIRED but never hints at what it is.
        self._error(401, "UNAUTHORISED", "this backend requires a bearer token",
                    "Set the same token the service was started with.")
        return False

    # -- verbs -------------------------------------------------------------------

    # The browser's advance question: "am I allowed to call you, and how?"
    def do_OPTIONS(self) -> None:                              # noqa: N802
        origin = self._origin_ok()
        # 204 means "yes, and there is nothing more to say"; 403 means "no".
        self.send_response(204 if origin is not None else 403)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, "
                                                             "Authorization")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # A request to READ something.
    def do_GET(self) -> None:                                  # noqa: N802
        self._dispatch("GET")

    # A request to DO something.
    def do_POST(self) -> None:                                 # noqa: N802
        self._dispatch("POST")

    # -- routing -----------------------------------------------------------------

    # Work out which handler a request belongs to, checking everything first.
    def _dispatch(self, verb: str) -> None:
        # GATE 1: is this browser allowed to talk to us?
        if self._origin_ok() is None:
            self._error(403, "FORBIDDEN_ORIGIN",
                        "this backend does not accept browser requests from that origin",
                        # And the remedy includes the word "deliberately", which is a small
                        # but pointed reminder that widening this is a decision, not a fix.
                        "Set AEGIS_ALLOWED_ORIGINS to include it, deliberately.")
            return
        # GATE 2: the password, if one is set.
        if not self._authorised():
            return

        parsed = urlparse(self.path)
        # `rstrip("/")` so "/api/health/" and "/api/health" are the same. `or "/"` keeps a
        # bare slash from becoming an empty string.
        path = parsed.path.rstrip("/") or "/"
        # Method first, then path. Matching on the path alone means a route that exists
        # under two verbs answers 405 for whichever verb happens to be declared second.
        # PLAIN ENGLISH: a real bug, avoided. If one address is served both for reading and
        # for doing, and you check the address first and find the wrong-method entry, you
        # would wrongly reply "method not allowed" for a request that was perfectly valid.
        # Gathering ALL the matches first and then looking for the right method fixes it.
        candidates = [(m, pat, n) for (m, pat, n) in ROUTES if pat.match(path)]
        if candidates and not any(m == verb for (m, _p, _n) in candidates):
            allowed = ", ".join(sorted({m for (m, _p, _n) in candidates}))
            # And the error names which method WOULD work.
            self._error(405, "METHOD_NOT_ALLOWED",
                        "%s is served over %s" % (path, allowed),
                        "Use %s for this route." % allowed)
            return
        for method, pattern, name in candidates:
            if method != verb:
                continue
            match = pattern.match(path)
            # POST requests carry a JSON body; GET requests carry query parameters.
            body = self._body() if verb == "POST" else _query(parsed.query)
            if body is None:
                return                     # _body already answered
            try:
                status_code, payload = self._handle(name, match.groupdict(), body)
            except Exception:              # noqa: BLE001 - reported, never leaked
                # PLAIN ENGLISH: "reported, never leaked" is the security rule here. The
                # full technical detail is printed to OUR log, where it helps us fix the
                # bug. The visitor gets a plain apology with no internals in it -- because an
                # error message revealing file paths and code structure is a map for anybody
                # looking for a way in.
                traceback.print_exc()
                self._error(500, "FAILED",
                            "the backend failed while handling this request",
                            # And an honest remedy: this one is our fault, not yours.
                            "This is a defect in the backend, not in your request.")
                return
            self._send(status_code, payload)
            return

        # Nothing matched at all. Refuse, and point at the two addresses that would help
        # somebody find their way.
        self._error(404, "UNKNOWN_ROUTE", "no route matches %s" % path,
                    "GET /api/health lists the service; GET /api/catalogue lists "
                    "every module.")

    # Hand the request to the layer that actually does the work.
    def _handle(self, name: str, params: dict, body: dict) -> tuple[int, dict]:
        # Notice how thin every branch is. This file routes; the service computes.
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
        # Reaching here would mean a route was declared with no handler -- a programming
        # mistake, so it fails loudly. `pragma: no cover` tells the test tooling not to
        # expect this line to run, because by construction it never should.
        raise AssertionError("unrouted handler %r" % name)     # pragma: no cover


# Translate a result status into a web status code.
def _code_for(payload: dict) -> int:
    status = payload.get("status", "FAILED")
    # Look it up in the table; and for anything unlisted, fall back on whether it is a
    # deliberate refusal (200, with an explanation) or a genuine failure (500).
    return HTTP_STATUS.get(status, 200 if status in REFUSALS else 500)


# Read the parameters out of a web address.
def _query(raw: str) -> dict:
    """Query parameters as a flat dict; repeated keys become a list.

    Only GET routes use this, and none of them run anything, so the loose shape here
    cannot reach an adapter. Run requests carry a JSON body.
    """
    # PLAIN ENGLISH: an explicit note about why the looser handling here is safe. These
    # parameters only ever reach read-only addresses, none of which compute anything.
    # Anything that RUNS must arrive as a proper JSON body and go through the full checking.
    out: dict = {}
    for key, values in parse_qs(raw, keep_blank_values=False).items():
        # One value stays a single value; several become a list.
        out[key] = values[0] if len(values) == 1 else values
    return out


# Start the server.
def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
    # "Threading" so several requests can be handled at once rather than queueing.
    httpd = ThreadingHTTPServer((host, port), Handler)
    counts = svc.health()
    # A startup message with the real numbers, so it is immediately obvious if the service
    # came up with nothing loaded.
    sys.stderr.write(
        "[backend] aegis %s on http://%s:%d — %d weeks, %d modules, %d live-capable\n"
        % (BACKEND_VERSION, host, port, counts["weeks"], counts["modules"],
           counts["live_capable_modules"]))
    # And which websites are allowed, printed at startup so a misconfiguration is visible
    # immediately rather than at the moment somebody's request mysteriously fails.
    sys.stderr.write("[backend] origins allowed: %s\n" % ", ".join(ALLOWED_ORIGINS))
    try:
        # Wait for requests, forever.
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Ctrl-C. A tidy message rather than a page of error text.
        sys.stderr.write("\n[backend] stopped\n")
    finally:
        # `finally` runs whatever happened, so the network port is always released properly
        # and the next start does not fail with "address already in use".
        httpd.server_close()


# The command-line entry point.
def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    # Settings come from environment variables first...
    port = int(os.environ.get("AEGIS_BACKEND_PORT", DEFAULT_PORT))
    # `127.0.0.1` means THIS COMPUTER ONLY. A deliberately safe default: the service is not
    # reachable from the network at all unless somebody explicitly changes it.
    host = os.environ.get("AEGIS_BACKEND_HOST", "127.0.0.1")
    # ...and command-line arguments override them.
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    serve(port, host)
    return 0


# This block runs only when the file is executed directly (`python -m backend.server`),
# not when it is imported by something else. `SystemExit` passes the return code out to
# the terminal, so other tools can tell whether it finished cleanly.
if __name__ == "__main__":
    raise SystemExit(main())
