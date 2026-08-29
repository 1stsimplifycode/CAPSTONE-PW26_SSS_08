"""Stage timing that survives a buffered pipe.

Long builds print nothing until they exit when stdout is redirected, which makes a slow
stage indistinguishable from a hung one. Every stage therefore also appends to
``research_artifacts/manifests/progress.log`` with an explicit flush, so progress is
observable from another process while the build runs.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime

from research.core import paths

_LOG = paths.MANIFESTS / "progress.log"


def _emit(msg: str) -> None:
    line = "%s  %s" % (datetime.now(UTC).strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
    except Exception:
        pass


def log(msg: str) -> None:
    _emit(msg)


def reset() -> None:
    try:
        if _LOG.exists():
            _LOG.unlink()
    except Exception:
        pass


@contextmanager
def stage(name: str):
    _emit("START  %s" % name)
    t = time.perf_counter()
    try:
        yield
    finally:
        _emit("DONE   %s  (%.1fs)" % (name, time.perf_counter() - t))


class Ticker:
    """Periodic progress inside a long loop."""

    def __init__(self, name: str, total: int, every: int = 250) -> None:
        self.name = name
        self.total = total
        self.every = every
        self.n = 0
        self.t0 = time.perf_counter()

    def tick(self, k: int = 1) -> None:
        self.n += k
        if self.every and self.n % self.every == 0:
            el = time.perf_counter() - self.t0
            rate = self.n / el if el > 0 else 0.0
            eta = (self.total - self.n) / rate if rate > 0 else float("nan")
            _emit("  %s %d/%d  %.1f/s  eta %.0fs"
                  % (self.name, self.n, self.total, rate, eta))
