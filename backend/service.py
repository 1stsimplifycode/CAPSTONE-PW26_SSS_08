"""Resolve a module, validate the request, invoke the canonical code, shape the response.

The whole of the backend's decision-making is here, and it is deliberately small: this
layer decides *which* canonical function runs and *what shape* comes back, never *what it
computes*.

Execution goes down one of two paths and the response says which:

* the module declares a live analysis adapter → the adapter runs now, on the caller's
  validated inputs, and returns numbers that did not exist before the request;
* it does not → the verified artifact is replayed through a traceable endpoint, with the
  commit and run time that produced it, and the reason live execution is unavailable.

A protected module refuses. ``force`` is not a parameter of any endpoint and there is no
code path from a request to one.

PLAIN ENGLISH -- what this whole file is about:

THE DECISION-MAKER. Everything the backend actually decides happens here, and the list of
things it decides is deliberately tiny:

  * WHICH piece of research code should run,
  * and WHAT SHAPE the answer comes back in.

It never decides what anything computes. That would be the display layer quietly doing
research, which is exactly what this whole design forbids.

TWO PATHS, AND THE ANSWER ALWAYS SAYS WHICH IT TOOK:
  LIVE   -- the research code runs, now, on what you asked for. These numbers did not
            exist a moment ago.
  REPLAY -- nothing is computed; a saved result is served, together with when it was made
            and which version of the code made it, AND the reason it cannot be computed
            live right now.

THE PROTECTED-RESULT GUARD, which is the strongest safety measure in the project.
Some results are cited in the published paper. Regenerating one would change a number
somebody has already read. So those modules refuse.
And note HOW they refuse -- not with a permission check that could be got round, but by
the override simply not existing on any web address. There is no request, of any shape,
that reaches it. The only way is a person typing a command at the machine with the word
`--force` in it, deliberately.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For loading a piece of code by name at run time.
import importlib
# For asking a function what arguments it takes.
import inspect
# For reading JSON files.
import json
# For timing requests.
import time
# The world clock and the tool for reading the time.
from datetime import UTC, datetime

# The shared status names.
from backend import (
    ARTIFACT,
    FAILED,
    INVALID_INPUT,
    LIVE,
    OK,
    PROTECTED,
    UNKNOWN_MODULE,
)
# The reply shape.
from backend import contract as ct
# The catalogue and the bouncer.
from backend import registry as reg
from backend.registry import REPO_ROOT, ModuleSpec, ValidationError

#: Where a replayed artifact may be read from. Anything outside this list is not served,
#: which is what stops a path in the manifest becoming a filesystem read primitive.
# PLAIN ENGLISH: a short list of four folders, and nothing outside them can ever be read.
# "A filesystem read primitive" is the technical term for a bug that lets somebody ask for
# any file on the machine. Even though these paths come from our own manifest and not from
# a visitor, the list is enforced anyway -- because a manifest is editable, and a rule that
# only holds while everybody behaves is not really a rule.
ARTIFACT_ROOTS = ("outputs", "research_artifacts", "public/data", "logs")


# ------------------------------------------------------------------ helpers ----

# Turn a written name like "research.market.arrival:fit_all" into the actual function.
def _resolve(dotted: str):
    # `partition(":")` splits at the colon: the file on the left, the function on the right.
    mod_name, _, func_name = dotted.partition(":")
    # Load the file, then fetch the named function from inside it.
    return getattr(importlib.import_module(mod_name), func_name)


# Make a path safe to publish.
def _rel(path: str) -> str:
    """Repository-relative, forward-slashed. Absolute paths never leave this process."""
    # Same reasoning as in jsonio: a full address would publish somebody's private folder
    # layout while being useless to the reader.
    text = str(path).replace("\\", "/")
    root = REPO_ROOT.as_posix()
    # Chop the project root off the front if it is there; otherwise leave it alone.
    return text[len(root) + 1:] if text.startswith(root + "/") else text


# Read a saved JSON result -- but only from the permitted folders.
def _safe_read(rel_path: str) -> dict | None:
    """Read a JSON artifact from the allowlist, or return None."""
    clean = _rel(rel_path).lstrip("/")
    # THREE CHECKS, and each blocks a specific trick:
    #   `".." in clean`  -- ".." means "go up a folder". A path like
    #                       "outputs/../../../etc/passwords" starts inside the allowed
    #                       folder and climbs straight out of it. Refusing "..." entirely
    #                       is the simple, reliable defence.
    #   `startswith`     -- and it must begin inside one of the four permitted folders.
    if ".." in clean or not any(clean.startswith(r) for r in ARTIFACT_ROOTS):
        return None
    p = REPO_ROOT / clean
    #   `.suffix != ".json"` -- and it must be a JSON file. This function reads results, and
    #                       nothing else, so anything else is refused whatever its path.
    if not p.exists() or p.suffix != ".json":
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # A corrupt or unreadable file reports as "nothing here" rather than crashing the
        # whole request.
        return None


# Fetch the caveats attached to a module.
def _limitations(spec: ModuleSpec) -> list[dict]:
    from research.limitations import registry as lr
    out = []
    for lid in spec.limitations:
        entry = lr.by_id(lid)
        # THIS IS THE CHAIN THAT CARRIES THE CAVEATS ALL THE WAY TO THE SCREEN. The
        # limitations register is not a document nobody opens -- it is read here, on every
        # request, and the warnings travel attached to the numbers.
        out.append({"id": lid,
                    # `if entry else` handles a limitation id that no longer exists: it
                    # shows "unknown limitation" rather than crashing, so a stale reference
                    # is visible instead of fatal.
                    "title": entry.title if entry else "unknown limitation",
                    "scope_note": entry.scope_note if entry else "",
                    "status": entry.current_status.value if entry else "UNKNOWN"})
    return out


# When did this module last run, and how did it go?
def _last_run(spec: ModuleSpec) -> dict | None:
    # The log file for this module. `.jsonl` means one JSON record per line, which makes
    # appending cheap and reading the last entry easy.
    log = REPO_ROOT / "logs" / spec.category.lower() / (
        "%s.jsonl" % spec.id.lower().replace("-", "_"))
    if not log.exists():
        return None
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        # `[-1]` is the last line -- the most recent run.
        last = json.loads(lines[-1])
    except ValueError:
        return None
    return {"at": last.get("ts"), "status": last.get("status"),
            "message": last.get("message"), "elapsed_s": last.get("elapsed_s"),
            # The code version at the time, and how many runs there have been altogether.
            "git_commit": last.get("git_commit"), "runs_recorded": len(lines)}


# The provenance stamp attached to every single reply.
def _base_provenance(spec: ModuleSpec) -> dict:
    from research.core.manifest import git_commit
    return {
        "module_id": spec.id,
        # Which code ran, and which research code it is a front for.
        "adapter": spec.adapter,
        "canonical": list(spec.canonical),
        "wrapper_status": spec.wrapper_status,
        "research_status": spec.status,
        "experiment_id": spec.experiment_id,
        # Exactly which version of the code, and exactly when.
        "git_commit": git_commit(),
        "requested_at": datetime.now(UTC).isoformat(),
        "declared_inputs": list(spec.inputs),
        "declared_outputs": [_rel(o) for o in spec.outputs],
        # AND THE COMMAND TO REPRODUCE IT. A reader is handed the exact instruction to run
        # this themselves, in every reply. That is reproducibility offered rather than
        # merely claimed.
        "regenerate_with": "python scripts/run_module.py --module %s" % spec.id,
    }


# Everything the website needs to draw a module's controls before anything is run.
def describe(module_id: str) -> dict:
    """Everything the interface needs to render a module's controls before running it."""
    spec = reg.module(module_id)
    if spec is None:
        return {"status": UNKNOWN_MODULE, "module_id": module_id}
    d = spec.to_dict()
    d["last_run"] = _last_run(spec)
    d["limitations"] = _limitations(spec)
    # WHETHER EACH REQUIRED FILE ACTUALLY EXISTS. So the page can say "this cannot run yet,
    # because this file is missing" BEFORE somebody presses a button and waits.
    d["inputs_present"] = [
        {"path": _rel(i), "exists": (REPO_ROOT / i).exists()} for i in spec.inputs
    ]
    d["outputs_present"] = [
        {"path": _rel(o), "exists": (REPO_ROOT / o).exists()} for o in spec.outputs
    ]
    return d


# ------------------------------------------------------------------- running ----

# THE MAIN ENTRY POINT.
def run_module(module_id: str, payload: dict | None = None) -> dict:
    """One module, one response.

    Never raises: a failure is a response, not a traceback.
    """
    # PLAIN ENGLISH: "never raises" is a promise. Whatever goes wrong, this hands back a
    # proper reply explaining it. It never lets an error escape to become a blank page or a
    # wall of technical text in somebody's browser.
    started = time.perf_counter()
    spec = reg.module(module_id)
    if spec is None:
        return ct.Response(
            module_id=module_id, category="", name="", status=UNKNOWN_MODULE,
            mode=ARTIFACT,
            error=ct.ContractError(
                UNKNOWN_MODULE, "no module with id %r" % module_id,
                # And a remedy pointing at where the valid names are listed.
                "Call GET /api/modules for the list of module identifiers."),
        ).to_dict()

    try:
        # THE BOUNCER. Nothing past this line has been unchecked.
        inputs = reg.validate(spec, payload)
    except ValidationError as exc:
        # The mode is the one this module *has*, not a stand-in. Reporting ARTIFACT on a
        # rejected request to a live module would say an artifact was served when nothing
        # was, and the interface would render a badge describing a replay that never
        # happened.
        # PLAIN ENGLISH: a small detail with real consequences. Even in a failure reply, the
        # mode must be truthful. Defaulting to "replay" here would put a badge on screen
        # saying a saved result had been served -- when in fact nothing was served at all.
        # A lie in an error message is still a lie.
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name,
            week=spec.week, status=INVALID_INPUT,
            mode=LIVE if spec.analysis.is_live else ARTIFACT,
            inputs=dict(payload or {}),
            provenance=_base_provenance(spec),
            limitations=_limitations(spec),
            error=ct.ContractError(
                INVALID_INPUT, str(exc),
                # The remedy names the exact address where the accepted settings are listed.
                "Correct the input and send the request again; the accepted schema is on "
                "GET /api/modules/%s." % spec.id),
        ), started)

    # THE FORK: compute now, or replay a saved result.
    if spec.analysis.is_live:
        return _run_live(spec, inputs, started)
    return _replay_artifact(spec, inputs, started)


# PATH 1: actually run the research code.
def _run_live(spec: ModuleSpec, inputs: dict, started: float) -> dict:
    try:
        fn = _resolve(spec.analysis.adapter)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=FAILED, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(
                FAILED, "the analysis adapter could not be imported: %s: %s"
                % (type(exc).__name__, exc),
                # Honest about whose fault it is.
                "This is a defect in the backend, not in your request."),
        ), started)

    try:
        # Call the research code. `inspect.signature(fn).parameters` asks whether it takes
        # any arguments at all, so a function needing none is not handed an empty dict and
        # made to crash. `**inputs` spreads the settings out as named arguments.
        result = fn(**inputs) if inspect.signature(fn).parameters else fn()
    except ValidationError as exc:
        # The research code itself objected -- perhaps the dates are valid but leave no data.
        # Reported as a bad request, with a remedy the caller can act on.
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=INVALID_INPUT, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(INVALID_INPUT, str(exc),
                                   "Adjust the selection and try again."),
        ), started)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=FAILED, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(
                FAILED, "%s: %s" % (type(exc).__name__, exc),
                # AN IMPORTANT REASSURANCE: nothing was half-done. This layer never writes
                # anything, so a crash cannot have left the project in a broken half-changed
                # state. Telling the caller that saves them wondering what to clean up.
                "The canonical implementation raised. The request was not partially "
                "applied: this layer writes nothing."),
        ), started)

    return _finish(_from_analysis(spec, inputs, result), started)


# Shape what the research code returned into the standard reply.
def _from_analysis(spec: ModuleSpec, inputs: dict, result) -> ct.Response:
    """Shape an :class:`AnalysisResult` into the response contract."""
    provenance = _base_provenance(spec)
    provenance.update(result.provenance or {})
    provenance["computed"] = True
    # Stated in words, not just as a flag, so it reaches a human reader.
    provenance["execution"] = (
        "The canonical implementation named above ran during this request. No artifact "
        "was written and no stored result was read for the metrics below.")

    observations = list(result.observations)
    if spec.is_protected:
        # A protected module CAN still be analysed live -- reading is safe; it is writing
        # that is forbidden. So the reply says so explicitly, twice: once in the provenance
        # for a program, once in the observations for a person.
        provenance["protected_artifacts"] = [_rel(o) for o in spec.outputs]
        provenance["protection_note"] = (
            "This module's stored artifacts are protected. This analysis read the data "
            "and wrote nothing; the artifacts on disk are untouched, and regenerating "
            "them still requires a deliberate terminal command.")
        observations.append(
            "This module's published artifacts are protected. Nothing was overwritten: "
            "the analysis above wrote no file.")

    status = OK if result.ok else (result.status or FAILED)
    error = None
    if not result.ok:
        error = ct.ContractError(status, result.message,
                                 result.remedy or "See the module's declared inputs.")
    return ct.Response(
        module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
        status=status, mode=LIVE, experiment_id=spec.experiment_id,
        dataset=result.dataset, inputs=inputs,
        # `ct.Metric(**m)` builds a proper Metric from each set of boxes -- which also means
        # a malformed one fails here rather than reaching the screen.
        metrics=[ct.Metric(**m) for m in result.metrics],
        series=[ct.Series(**s) for s in result.series],
        uncertainty=result.uncertainty, observations=observations,
        figures=_figures_for(spec), tables=_tables_for(spec),
        provenance=provenance, limitations=_limitations(spec),
        message=result.message,
        error=error,
    )


# PATH 2: serve a saved result, clearly labelled as one.
def _replay_artifact(spec: ModuleSpec, inputs: dict, started: float) -> dict:
    """Serve the verified artifact, labelled as a replay and never as a computation."""
    provenance = _base_provenance(spec)
    provenance["computed"] = False

    # Which of the expected files actually exist.
    present = [o for o in spec.outputs if (REPO_ROOT / o).exists()]
    if not present:
        reason = (spec.analysis.artifact_reason
                  or "this module computes nothing live and its artifact is absent")
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status="INPUTS_MISSING", mode=ARTIFACT, inputs=inputs,
            provenance=provenance, limitations=_limitations(spec),
            error=ct.ContractError(
                "INPUTS_MISSING", reason,
                # And the exact command that would produce it.
                "Run `python scripts/run_module.py --module %s` to produce it."
                % spec.id),
        ), started)

    # Read them, through the safe reader.
    payloads = {}
    for rel_path in present:
        data = _safe_read(rel_path)
        if data is not None:
            payloads[_rel(rel_path)] = data

    run = _last_run(spec)
    # THE REPLAY STAMP: which files, from which run, at which code version. This is what
    # makes a replay traceable rather than an anonymous old number.
    provenance["artifacts"] = [_rel(o) for o in present]
    provenance["replayed_run_id"] = (run or {}).get("at") or "unknown"
    provenance["replayed_commit"] = (run or {}).get("git_commit")
    provenance["execution"] = (
        "Nothing was computed for this request. The values below were read from the "
        "artifact listed above, which was produced by the run identified here.")

    metrics, series = _artifact_view(spec, payloads)
    if not metrics and not series:
        # Some modules produce asset directories or model bundles rather than JSON and
        # CSV. Replaying one has nothing to tabulate, but "nothing" is the wrong answer:
        # what exists on disk, how large it is and which run wrote it are exactly what a
        # reader wants from a module that cannot be re-run on request.
        # PLAIN ENGLISH: a module that produces a folder of images has no numbers to show.
        # An empty panel would read as "broken". So instead we describe what IS there --
        # how many files, how big, from which run. Useful, and honest about what it is.
        metrics = _artifact_inventory(spec, present)
    status = OK
    error = None
    if spec.is_protected:
        # Not a failure: the guard working. Regeneration would overwrite an artifact the
        # claim ledger cites, and no request can authorise that.
        # PLAIN ENGLISH: note the status stays OK. The saved result IS served -- the reader
        # gets what they asked for. The error block is an explanation attached alongside,
        # not a refusal to answer. And the remedy is honest about what it would take: a
        # deliberate command at a terminal, with the word "force" in it.
        error = ct.ContractError(
            PROTECTED,
            "This module regenerates artifacts the claim ledger and the documentation "
            "already cite, so it will not re-run on request.",
            "The verified result is served above. Regenerating requires "
            "`python scripts/run_module.py --module %s --force` at a terminal, "
            "deliberately." % spec.id,
            {"outputs": [_rel(o) for o in spec.outputs]})

    return _finish(ct.Response(
        module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
        status=status, mode=ARTIFACT, experiment_id=spec.experiment_id,
        dataset={"source": "verified artifact", "paths": provenance["artifacts"]},
        inputs=inputs, metrics=metrics, series=series,
        uncertainty=_replay_uncertainty(provenance["artifacts"]),
        # Whatever the original run said about itself, if anything.
        observations=[o for o in ([run.get("message")] if run else []) if o],
        figures=_figures_for(spec), tables=_tables_for(spec),
        provenance=provenance, limitations=_limitations(spec),
        message=spec.analysis.artifact_reason
        or "Verified experiment result, replayed from its artifact.",
        error=error,
    ), started)


# What a replay can honestly say about its own precision.
def _replay_uncertainty(artifacts: list[str]) -> dict:
    """Say what a replay can and cannot tell you about its own precision.

    Every live module answers this: it either reports an interval or states why there
    isn't one — a count is not an estimate. A replay was answering nothing at all, so
    three of the sixteen modules showed a reader figures with silence beside them,
    which reads identically to "this result has no uncertainty".

    It does not, and inventing one here would be worse than the silence. What this can say
    truthfully is where the answer lives: the run that produced these numbers computed
    whatever it computed, and that is in the artifacts named in the provenance rather than
    summarised for this request. `research_artifacts/statistics/uncertainty_bins.csv` is
    exactly such a file, and pointing at it is more use than an empty block.
    """
    # PLAIN ENGLISH: a bug found by noticing a SILENCE, which is much harder than noticing a
    # wrong number.
    # Every live result says either "here is the uncertainty" or "here is why there is
    # none". Replayed results said nothing at all -- and an empty space beside a figure
    # reads exactly like "this number is exact". Three of the sixteen modules were doing
    # that.
    # The fix could not be to invent an interval, which would be far worse. So it says the
    # truthful thing: nothing was computed for you just now, so nothing was estimated for
    # you; the precision that WAS established lives in these named files, go and look.
    return {
        "kind": "replayed",
        "reading": (
            "Nothing was computed for this request, so no interval was estimated for it. "
            "These are the figures the recorded run produced; whatever precision it "
            # `artifacts[:3]` names up to three files rather than a long list.
            "established is in the artifacts named below (%s) rather than summarised "
            "here." % ", ".join(artifacts[:3]) if artifacts else
            # And a shorter version when there are no files to point at.
            "Nothing was computed for this request, so no interval was estimated for it."
        ),
    }


# Turn saved files into the same shapes a live run produces.
def _artifact_view(spec: ModuleSpec, payloads: dict) -> tuple[list, list]:
    """Turn replayed artifacts into the same metric/series shapes a live run produces."""
    # PLAIN ENGLISH: this is what lets the website have ONE display for everything. A
    # replayed result is reshaped to look exactly like a live one -- differing only in its
    # honest mode label.
    from scripts.stages import fmt_value

    metrics: list[ct.Metric] = []
    series: list[ct.Series] = []
    for rel_path, data in payloads.items():
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            # A number -- but NOT a True/False. The odd-looking double check is necessary
            # because in Python True and False count as numbers, and a True would otherwise
            # be displayed as the number 1.
            if isinstance(value, (int, float, bool)) and not isinstance(value, bool):
                metrics.append(ct.Metric(
                    # `key.replace("_", " ")` turns "false_alarm_rate" into a readable
                    # "false alarm rate".
                    key=key, label=key.replace("_", " "), value=value,
                    display=fmt_value(value), format="auto",
                    # Every replayed value is labelled with where it was read from.
                    note="read from the artifact", source=rel_path))
            # A short piece of text.
            elif isinstance(value, str) and len(value) < 400:
                metrics.append(ct.Metric(
                    key=key, label=key.replace("_", " "), value=value,
                    display=value, format="text",
                    note="read from the artifact", source=rel_path))
        # A cap, so a huge file cannot produce a page of hundreds of unreadable tiles.
        if len(metrics) > 40:
            break

    # And any spreadsheet files become charts.
    for rel_path in spec.outputs:
        clean = _rel(rel_path)
        if not clean.endswith(".csv"):
            continue
        p = REPO_ROOT / clean
        # The allowlist enforced again, on this separate path. Each place that reads a file
        # checks for itself rather than assuming somebody upstream did.
        if not p.exists() or not any(clean.startswith(r) for r in ARTIFACT_ROOTS):
            continue
        import pandas as pd
        frame = pd.read_csv(p)
        # Only the first 50 rows, to keep replies small...
        head = frame.head(50)
        series.append(ct.Series(
            key=clean, label=clean.rsplit("/", 1)[-1],
            columns=[str(c) for c in head.columns],
            rows=json.loads(head.to_json(orient="values")),
            note="read from the artifact",
            # ...and the truncation is ANNOUNCED, with the real total, so a shortened table
            # never masquerades as the whole thing.
            truncated=len(frame) > 50,
            total_rows=int(len(frame))))
    return metrics, series


# For modules whose output is files rather than numbers.
def _artifact_inventory(spec: ModuleSpec, present: list[str]) -> list[ct.Metric]:
    """What the module's artifacts are, when they are not numbers to read."""
    from scripts.stages import fmt_value

    metrics = [ct.Metric(
        key="artifacts", label="Artifacts on disk", value=len(present),
        display=fmt_value(len(present), "int"), format="int",
        note="declared outputs this module has produced", source="")]
    total_files = total_bytes = 0
    for rel_path in present:
        target = REPO_ROOT / rel_path
        # One file, or every file inside a folder. `rglob("*")` searches all the way down.
        files = ([target] if target.is_file()
                 else [p for p in target.rglob("*") if p.is_file()])
        total_files += len(files)
        total_bytes += sum(p.stat().st_size for p in files)
        metrics.append(ct.Metric(
            key=_rel(rel_path), label=_rel(rel_path).rsplit("/", 1)[-1],
            value=len(files), display="%s file(s)" % fmt_value(len(files), "int"),
            format="int",
            # Whether it is one file or a whole folder -- a genuinely useful distinction.
            note="directory" if target.is_dir() else "file",
            source=_rel(rel_path)))
    metrics.append(ct.Metric(
        key="total_files", label="Files", value=total_files,
        display=fmt_value(total_files, "int"), format="int",
        note="across every artifact above", source=""))
    metrics.append(ct.Metric(
        # Bytes divided by a million gives megabytes, which a person can actually picture.
        key="total_mb", label="Size on disk", value=total_bytes / 1e6,
        display="%.1f MB" % (total_bytes / 1e6), format="float1",
        note="what the last run of this module produced", source=""))
    return metrics


# Any charts this module has produced.
def _figures_for(spec: ModuleSpec) -> list[dict]:
    bundle = _safe_read("public/data/modules.json") or {}
    for row in bundle.get("rows", []):
        if row.get("id") == spec.id:
            return row.get("figures") or []
    return []


# And any tables.
def _tables_for(spec: ModuleSpec) -> list[dict]:
    bundle = _safe_read("public/data/modules.json") or {}
    for row in bundle.get("rows", []):
        if row.get("id") == spec.id:
            return row.get("tables") or []
    return []


# THE LAST GATE. Every reply passes through here before it leaves.
def _finish(response: ct.Response, started: float) -> dict:
    response.elapsed_s = time.perf_counter() - started
    # Run the contract checker from contract.py.
    problems = response.check()
    if problems:
        # A contract violation is a backend defect and is reported as one rather than
        # silently shipped: a response that breaks its own rules is worse than an error.
        # PLAIN ENGLISH: the strictest rule in the file. If our own reply breaks our own
        # rules -- no provenance, a mislabelled mode, a leaked file path -- we do not send
        # it. We replace it with an error saying so, and list exactly which rules it broke.
        # It would be far easier to ship it anyway, since it is probably mostly fine. But a
        # reply that breaks the rules the reader is relying on is worse than no reply, because
        # the reader has no way of knowing.
        response.status = FAILED
        response.error = ct.ContractError(
            FAILED, "the backend produced a response that violates its own contract",
            "This is a defect in the backend, not in your request.",
            # The full list of violations included, so the bug is fixable from the reply.
            {"problems": problems})
    return response.to_dict()


# ---------------------------------------------------------------- weekly view ----

# Run a whole week's work.
def run_week(number: int, payload: dict | None = None) -> dict:
    """Orchestrate one week: run its STATS module.

    Inputs are addressed per module (``{"STATS-01": {...}}``) so a caller can name the
    module explicitly. Shared keys at the top level are applied to whichever declared
    inputs accept them, because a date range usually is shared and making the caller
    repeat it would be noise.
    """
    # PLAIN ENGLISH: a small kindness. You can address a setting to one specific module, or
    # put it at the top level and let it apply to any module that accepts it. A date range
    # almost always applies to everything, and making somebody type it once per module would
    # be pointless friction -- and an invitation to typo one of them.
    started = time.perf_counter()
    spec = reg.week(number)
    if spec is None:
        return {"status": "UNKNOWN_WEEK", "week": number,
                "error": {"code": "UNKNOWN_WEEK",
                          "reason": "no week %s in the registry" % number,
                          # And the remedy states the valid range.
                          "remedy": "Weeks 1 to %d are defined." % len(reg.weeks())}}

    payload = dict(payload or {})
    # Anything not addressed to a specific module is shared.
    shared = {k: v for k, v in payload.items() if not k.startswith("STATS")}
    results = {}
    for module_id in (spec.stats_module,):
        module_spec = reg.module(module_id)
        declared = {i.name for i in module_spec.analysis.inputs} if module_spec else set()
        # Take only the shared settings this module actually understands -- so an unrelated
        # setting cannot cause a spurious "unknown input" rejection.
        merged = {k: v for k, v in shared.items() if k in declared}
        # And anything addressed specifically to it wins over the shared version.
        merged.update(payload.get(module_id) or {})
        results[module_id] = run_module(module_id, merged)

    statuses = [r["status"] for r in results.values()]
    return {
        "backend_version": __import__("backend").BACKEND_VERSION,
        "week": spec.week,
        "title": spec.title,
        "question": spec.question,
        "summary": spec.summary,
        "stats_module": spec.stats_module,
        # OK only if EVERYTHING worked; otherwise PARTIAL. Not "OK because most of it
        # worked" -- a partly-successful week says so.
        "status": OK if all(s == OK for s in statuses) else "PARTIAL",
        # And which modules computed versus replayed, so the mixture is visible at a glance.
        "modes": {k: v["mode"] for k, v in results.items()},
        "results": results,
        "elapsed_s": round(time.perf_counter() - started, 3),
        # A plain-English explanation of what a "week" is, carried in the reply so the
        # website need not know.
        "reading": (
            "One week is one vertical slice: a statistical view of one question, executed "
            "through the same canonical implementations the research pipeline uses. It "
            "reports whether it computed or replayed."),
    }


# The full catalogue, for building the website's navigation.
def catalogue() -> dict:
    return {
        "backend_version": __import__("backend").BACKEND_VERSION,
        "weeks": [w.to_dict() for w in reg.weeks()],
        "modules": [m.to_dict() for m in reg.modules().values()],
        "counts": {
            "weeks": len(reg.weeks()),
            "modules": len(reg.modules()),
            # How many can compute live versus only replay. Published openly rather than
            # blurred -- a reader can see at a glance how much of the system is live.
            "live_capable": sum(1 for m in reg.modules().values()
                                if m.analysis.is_live),
            "artifact_only": sum(1 for m in reg.modules().values()
                                 if not m.analysis.is_live),
        },
    }


# Is the service alive and correctly loaded?
def health() -> dict:
    from research.core.manifest import git_commit
    live = [m for m in reg.modules().values() if m.analysis.is_live]
    return {
        "status": "OK",
        "backend_version": __import__("backend").BACKEND_VERSION,
        # The exact code version, so a monitoring tool can spot a stale deployment.
        "git_commit": git_commit(),
        # And the counts -- so "alive but loaded nothing" is immediately obvious rather
        # than reporting a cheerful OK while being useless.
        "weeks": len(reg.weeks()),
        "modules": len(reg.modules()),
        "live_capable_modules": len(live),
        "checked_at": datetime.now(UTC).isoformat(),
    }
