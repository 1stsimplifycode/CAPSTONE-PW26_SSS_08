"""Dispatcher for the 16 STATS execution modules.

    python scripts/run_module.py --module STATS-02
    python scripts/run_module.py --module STATS-02 --check
    python scripts/run_module.py --module STATS-13 --force
    python scripts/run_module.py --list

One dispatcher rather than 16 shim scripts: the manifest already names each module's
adapter, so a second per-module file would only be a place for the two to drift apart.
Every ``run.bat`` calls this with its own module id.

**The protected-artifact guard.** Eight modules regenerate files that the claim ledger and
the documentation already quote. Running one of those by accident would silently change
numbers that are cited in prose, which is a worse failure than not running it at all. They
refuse with exit code 5 unless ``--force`` is passed.

Exit codes are the contract with the .bat layer:
  0 OK · 1 FAILED · 3 BLOCKED · 4 INPUTS MISSING · 5 SKIPPED (protected) ·
  6 NOT YET EXECUTED

PLAIN ENGLISH -- what this whole file is about:

THE ONE SWITCHBOARD THAT RUNS ANY OF THE SIXTEEN ANALYSES.

The obvious design is sixteen little scripts, one per module. This is one script that reads
a manifest -- a list saying which piece of code each module uses -- and calls the right one.
The reason given is a good one: two files describing the same thing are "only a place for the
two to drift apart." Update one, forget the other, and now they disagree with no warning.

THE PROTECTED-ARTIFACT GUARD IS THE HEART OF THIS FILE.
Eight of the sixteen modules OVERWRITE result files that are already quoted -- in the claim
ledger, in the documentation, in prose that says "the model achieved 0.712".
Rerun one carelessly, the numbers shift slightly, and now the prose cites a figure the files
no longer contain. Nothing crashes. Nothing warns you. The documentation is just quietly
wrong.
So those eight REFUSE TO RUN. You have to type --force, which means you did it on purpose.
And the refusal is written to the log too, so the record shows the run was declined.

THE EXIT CODES matter because .bat files call this and can only see a number. 0 means it
worked; 5 means "refused, protected"; 6 means "this has never been run". Six distinct
outcomes rather than a single pass/fail, so the caller can tell WHY.
"""
from __future__ import annotations

import argparse
# importlib turns a string like "scripts.stages.stats" into the actual module.
import importlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.core import jsonio  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from scripts.stages import (  # noqa: E402
    FAILED,
    OK,
    SKIPPED_PROTECTED,
    StageResult,
)

# The single list of every module and what it does. One source of truth.
MANIFEST = REPO_ROOT / "research_modules.yaml"


def load_manifest() -> dict:
    # Imported here rather than at the top, so `--list` works even in an environment where
    # yaml is unavailable for other reasons.
    import yaml
    # `safe_load` rather than `load`: it will not execute code hidden in the file.
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def find_module(manifest: dict, module_id: str) -> dict | None:
    # Trim spaces and upper-case, so "stats-02", " STATS-02 " and "STATS-02" all work.
    wanted = module_id.strip().upper()
    for m in manifest["modules"]:
        if m["id"].upper() == wanted:
            return m
    # Not found -> None, and the caller prints a helpful message.
    return None


def _resolve(adapter: str):
    """`scripts.stages.stats:universe_survivorship` -> the callable."""
    # PLAIN ENGLISH: the manifest stores the code to run as text -- "which file : which
    # function". `partition(":")` splits at the colon, then importlib loads the file and
    # getattr fetches the function out of it.
    mod_name, _, func_name = adapter.partition(":")
    return getattr(importlib.import_module(mod_name), func_name)


def _log(entry: dict) -> Path:
    category = entry["category"].lower()
    d = REPO_ROOT / "logs" / "stats"
    d.mkdir(parents=True, exist_ok=True)
    # One log file per module: STATS-02 -> stats_02.jsonl.
    p = d / ("%s.jsonl" % entry["module_id"].lower().replace("-", "_"))
    # jsonio rather than json.dumps: an adapter can legitimately return a non-finite
    # value in its detail dict, and one bare NaN or Infinity makes the entire provenance
    # log unreadable to every strict parser. Caught by
    # tests/unit/test_module_structure.py::test_provenance_records_are_strict_json.
    # PLAIN ENGLISH: NaN means "not a number" and comes up honestly in statistics. But
    # standard JSON has no way to write it, so plain json.dumps produces a file that many
    # readers will refuse ENTIRELY -- one bad value destroys the whole log. jsonio writes it
    # as null instead. And a test enforces this, so the rule cannot quietly lapse.
    # "a" means APPEND: every run adds a line, nothing is ever overwritten. The log is a
    # complete history.
    with p.open("a", encoding="utf-8") as f:
        f.write(jsonio.dumps(entry, indent=None) + "\n")
    return p


def run(module_id: str, *, check: bool = False, force: bool = False,
        quiet: bool = False) -> int:
    manifest = load_manifest()
    spec = find_module(manifest, module_id)
    if spec is None:
        # `file=sys.stderr` sends this to the error channel, so it stays visible even if the
        # normal output is being piped into a file.
        print("unknown module %r; try --list" % module_id, file=sys.stderr)
        return FAILED

    started = time.time()
    header = "%s  %s" % (spec["id"], spec["name"])
    if not quiet:
        # A banner naming the module, the files it is authoritative for, the code it runs and
        # whether it is protected -- BEFORE it runs, so nobody is surprised by what happened.
        print("=" * 74)
        print(header)
        print("  canonical : %s" % (", ".join(spec["canonical"]) or "(none yet)"))
        print("  adapter   : %s" % spec["adapter"])
        print("  wrapper   : %s" % spec["wrapper_status"])
        print("=" * 74)

    # --check verifies the contract without executing: is the adapter importable, are the
    # declared inputs present? This is what the structural validator uses so that
    # validating the pipeline can never mutate an artifact.
    # PLAIN ENGLISH: a dress rehearsal. Can the code be loaded, are the input files there?
    # Nothing is run and nothing is written. Which matters because otherwise checking that
    # the pipeline is healthy would itself change the results.
    if check:
        try:
            fn = _resolve(spec["adapter"])
        except Exception as exc:
            print("  ADAPTER NOT IMPORTABLE: %s: %s" % (type(exc).__name__, exc))
            return FAILED
        # Which declared input files are missing.
        missing = [i for i in spec.get("inputs") or [] if not (REPO_ROOT / i).exists()]
        state = "OK" if callable(fn) else "NOT CALLABLE"
        if missing:
            # Both facts kept: the code is fine, the DATA is not. Two different problems.
            state = "OK (adapter) / inputs missing: %s" % ", ".join(missing)
        if not quiet:
            print("  check: %s" % state)
        return OK if callable(fn) else FAILED

    # THE GUARD. Protected module, no --force -> refuse.
    if spec["wrapper_status"] == "WRAPS_EXISTING_PROTECTED" and not force:
        # The refusal NAMES THE FILES at risk, and says exactly how to proceed on purpose.
        # "deliberately" is the operative word: the flag exists to make the act conscious.
        msg = ("refused: this module regenerates artifacts that the claim ledger and "
               "documentation already cite (%s). Pass --force to regenerate them "
               "deliberately." % ", ".join(spec.get("outputs") or []))
        print("  SKIPPED (protected): %s" % msg)
        # AND THE REFUSAL IS LOGGED. So the history shows the attempt and the decline, rather
        # than a mysterious gap where a run should be.
        _log({"ts": datetime.now(UTC).isoformat(), "module_id": spec["id"],
              "category": spec["category"], "status": "SKIPPED_PROTECTED",
              "code": SKIPPED_PROTECTED, "message": msg,
              "git_commit": git_commit(), "elapsed_s": 0.0})
        return SKIPPED_PROTECTED

    try:
        fn = _resolve(spec["adapter"])
        # Product adapters are manifest-driven: they execute the command declared in the
        # spec, so they need the spec itself. Research adapters do not take it, and
        # passing it unconditionally would break all sixteen of them.
        # PLAIN ENGLISH: two kinds of adapter want different arguments. Rather than maintain
        # a list of which is which -- a list that would go stale -- the code ASKS the function
        # what it accepts, using `inspect.signature`, and passes accordingly.
        import inspect
        if "module" in inspect.signature(fn).parameters:
            result: StageResult = fn(force=force, module=spec)
        else:
            result = fn(force=force)
    except Exception as exc:  # a module failure is reported, never swallowed
        # THE FULL ERROR TRACE IS PRINTED. Not a tidy one-line "something went wrong" --
        # everything needed to actually fix it. Then it becomes a FAILED result rather than
        # crashing, so the log entry below still gets written.
        import traceback
        traceback.print_exc()
        result = StageResult(FAILED, "%s: %s" % (type(exc).__name__, exc))

    elapsed = time.time() - started
    if not quiet:
        print("  %s  (%.1fs)" % (result.status, elapsed))
        if result.message:
            print("  %s" % result.message)
        # Every file written, listed. So the reader knows what changed on disk.
        for o in result.outputs:
            print("  -> %s" % o)

    # THE PROVENANCE RECORD -- everything about this run, appended to the module's log.
    _log({
        # WHEN.
        "ts": datetime.now(UTC).isoformat(),
        # WHAT ran.
        "module_id": spec["id"], "category": spec["category"], "name": spec["name"],
        # WHAT HAPPENED, including failures.
        "status": result.status, "code": result.code, "message": result.message,
        "outputs": result.outputs, "detail": result.detail,
        "wrapper_status": spec["wrapper_status"], "adapter": spec["adapter"],
        "canonical": spec["canonical"], "experiment_id": spec.get("experiment_id"),
        # THE CAVEATS travel with the run record too.
        "limitations": spec.get("limitations"),
        # WHICH VERSION OF THE CODE, and which library versions.
        "git_commit": git_commit(), "environment": environment_snapshot(),
        # AND WHETHER THE PROTECTION WAS OVERRIDDEN. Permanently on the record.
        "forced": bool(force), "elapsed_s": round(elapsed, 2),
    })
    return result.code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", help="module id, e.g. STATS-02")
    ap.add_argument("--check", action="store_true",
                    help="verify the adapter and inputs without executing")
    ap.add_argument("--force", action="store_true",
                    help="allow a module to regenerate protected artifacts")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--list", action="store_true", help="list every module and exit")
    args = ap.parse_args()

    if args.list:
        manifest = load_manifest()
        for m in manifest["modules"]:
            # `%-16s` pads to 16 characters, left-aligned, so the columns line up on screen.
            print("%-16s %-2d %-12s %-42s %s"
                  % (m["id"], m["index"], m["category"], m["name"], m["wrapper_status"]))
        return OK
    if not args.module:
        # `ap.error` prints the usage text and exits -- friendlier than a bare crash.
        ap.error("--module is required unless --list is given")
    return run(args.module, check=args.check, force=args.force, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
