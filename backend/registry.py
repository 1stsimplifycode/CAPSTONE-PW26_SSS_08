"""What the backend knows, all of it read from ``research_modules.yaml``.

The manifest is already the single source of truth for the modules; the week pairing, the
input schema and the execution mode are declared there too rather than in a second table
the backend keeps for itself. A second table is a second thing to drift.

Input validation lives here because it is the boundary: everything past this point is a
dict of primitives that has been range-checked against a declared schema. Nothing a caller
sends reaches a shell, a path join, or an ``eval``.

PLAIN ENGLISH -- what this whole file is about:

TWO JOBS: THE CATALOGUE, AND THE BOUNCER.

JOB 1 -- THE CATALOGUE. What modules exist, what each does, what it needs to be told, and
how long it takes. All of it read from ONE file (`research_modules.yaml`), never written
out a second time here.

Why so insistent? The docstring puts it in seven words: "A second table is a second thing
to drift." Copy the list of modules into a second place and one day somebody updates one
copy. Now the website advertises a module that no longer exists, or hides one that does.
Nothing breaks. Nothing warns anybody. One list means that cannot happen.

JOB 2 -- THE BOUNCER, and this is the security-critical half.

Everything a visitor types arrives here first. It is checked against a written-down
description of what that module accepts -- the right kind of thing, inside the right
range, no longer than allowed. Only then is it passed inwards.

Read the last sentence of the docstring carefully, because it names the three classic
catastrophes it is preventing:

  "Nothing a caller sends reaches a shell, a path join, or an eval."

  A SHELL     -- if what somebody types could become a command, they could tell the
                 computer to do anything at all.
  A PATH JOIN -- if it could become part of a filename, a request for "../../../secrets"
                 could walk out of the project and read the rest of the machine.
  AN EVAL     -- if it could be run as code, that is simply handing over the keys.

None of the three is possible, because past this point everything is a plain checked
value in a labelled box, and nothing else.

AND ONE SMALL DECISION WORTH NOTICING, further down: a misspelled parameter is REJECTED,
not ignored. Type "instrment" instead of "instrument" and you get told. The friendlier
alternative -- quietly using the default -- means you sit there wondering why your setting
had no effect, with nothing anywhere to tell you why.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For handling dates.
import datetime as dt
# For remembering the result of slow work so it is not repeated.
import functools
# Record-building tools.
from dataclasses import dataclass, field
# A safe way to talk about places on the disk.
from pathlib import Path
# "any kind of value at all".
from typing import Any

# The project root, worked out from this file's own location.
REPO_ROOT = Path(__file__).resolve().parents[1]
# THE ONE SOURCE OF TRUTH. Everything this file knows comes out of here.
MANIFEST = REPO_ROOT / "research_modules.yaml"

#: Categories the weekly programme covers. SCENARIO and PRODUCT are reachable as
#: modules but are not part of the sixteen-week programme.
WEEKLY_CATEGORIES = ("STATS",)


# A new kind of error, for a request that does not satisfy the rules.
class ValidationError(ValueError):
    """A caller's input did not satisfy the declared schema."""


# Frozen: a description of what a module accepts must not change while a request is being
# checked against it.
@dataclass(frozen=True)
# The description of ONE setting a module accepts.
class InputSpec:
    # Its machine name and its kind (date, number, list of companies, and so on).
    name: str
    kind: str
    # What to call it on screen.
    label: str
    # What to use if the caller says nothing.
    default: Any = None
    # A hint for the person filling it in.
    note: str = ""
    # For a choice, the permitted options.
    options: list[str] = field(default_factory=list)
    # For a number or a date, the allowed range.
    minimum: Any = None
    maximum: Any = None
    # For a list, how many items are allowed.
    max_items: int | None = None
    # Whether it must be supplied.
    required: bool = False

    # Turn it into labelled boxes, so the website can build a form from it automatically.
    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "label": self.label,
                "default": self.default, "note": self.note,
                "options": list(self.options), "minimum": self.minimum,
                "maximum": self.maximum, "max_items": self.max_items,
                "required": self.required}


@dataclass(frozen=True)
# How a module can be run.
class Analysis:
    """How a module can be executed live, if it can be."""

    # Which piece of code actually does the work.
    adapter: str | None
    # LIVE (can compute now) or ARTIFACT (can only replay a saved result).
    mode: str
    # Roughly how long it takes, so the website can warn the user before they wait.
    typical_seconds: float
    summary: str
    # The settings it accepts.
    inputs: tuple[InputSpec, ...] = ()
    #: Why this module cannot compute live, when it cannot. Shown to the caller verbatim.
    # PLAIN ENGLISH: not merely "unavailable" but the actual reason, shown word for word to
    # whoever asked. "Unavailable" invites people to keep trying; a reason lets them
    # understand and move on.
    artifact_reason: str = ""

    @property
    # Can it genuinely compute right now? Both conditions matter -- a module claiming to be
    # live with no code behind it would fail confusingly at the moment somebody pressed Run.
    def is_live(self) -> bool:
        return self.mode == "LIVE" and bool(self.adapter)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "is_live": self.is_live,
                # The analysis adapter, which is deliberately not the module's
                # regenerating adapter: one reads and returns, the other writes.
                # PLAIN ENGLISH: two different pieces of code with a very important
                # difference. One computes and hands the answer back. The other computes and
                # OVERWRITES the saved results on disk. Keeping them apart is what stops a
                # visitor clicking a button on a web page and destroying a published result.
                "adapter": self.adapter,
                "typical_seconds": self.typical_seconds, "summary": self.summary,
                "inputs": [i.to_dict() for i in self.inputs],
                "artifact_reason": self.artifact_reason}


@dataclass(frozen=True)
# Everything known about one module.
class ModuleSpec:
    id: str
    index: int
    category: str
    slug: str
    name: str
    # What it is for, and the research question it answers.
    purpose: str
    research_question: str
    adapter: str
    wrapper_status: str
    status: str
    experiment_id: str | None
    # What it reads and what it produces.
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    # Which research code it is a front for -- the traceability link back to the real work.
    canonical: tuple[str, ...]
    # Which known gaps bound its results.
    limitations: tuple[str, ...]
    notes: str
    # Where it lives on the website.
    route: str
    icon: str
    #: What the product calls this module. The identifier stays the identifier.
    # PLAIN ENGLISH: a module may have a friendly public name AND a fixed internal one. The
    # friendly name can be reworded freely; the identifier must never change, because saved
    # results and links refer to it. Keeping the two separate lets the wording improve
    # without breaking anything.
    product_name: str
    analysis: Analysis
    week: int | None

    @property
    # Is this result frozen because the paper cites it?
    def is_protected(self) -> bool:
        return self.wrapper_status == "WRAPS_EXISTING_PROTECTED"

    def to_dict(self) -> dict:
        return {
            "module_id": self.id, "index": self.index, "category": self.category,
            "slug": self.slug, "name": self.name, "purpose": self.purpose,
            "research_question": self.research_question,
            "adapter": self.adapter, "wrapper_status": self.wrapper_status,
            "status": self.status, "experiment_id": self.experiment_id,
            "declared_inputs": list(self.inputs), "outputs": list(self.outputs),
            "canonical": list(self.canonical), "limitations": list(self.limitations),
            "notes": self.notes, "route": self.route, "icon": self.icon,
            # `or self.name` falls back to the identifier's name when no friendly one was
            # set, so a page never shows a blank title.
            "product_name": self.product_name or self.name,
            "week": self.week, "protected": self.is_protected,
            "analysis": self.analysis.to_dict(),
        }


@dataclass(frozen=True)
# One week of the programme.
class WeekSpec:
    week: int
    title: str
    question: str
    stats_module: str
    summary: str
    #: What the week *shows*: the headline figures, the primary series, and the question
    #: it answers in a reader's words. Declared in the manifest rather than decided in a
    #: component, so a headline naming a metric the module stopped returning fails a test
    #: instead of rendering an empty card.
    # PLAIN ENGLISH: an excellent piece of design. The website could have decided for itself
    # which number to feature. Then if the module stopped producing that number, the page
    # would simply show a blank box -- no error, no warning, and the first person to notice
    # would be a visitor. Declaring it alongside the module means an automatic test catches
    # the mismatch instead.
    feature: dict = field(default_factory=dict)
    #: When this week's capability becomes visible, and what to call it. Declared beside
    #: the modules it gates so the unlock order is readable in one place; `capability.py`
    #: is what enforces it.
    gate: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"week": self.week, "title": self.title, "question": self.question,
                "stats_module": self.stats_module, "summary": self.summary,
                # `dict(...)` takes copies, so a caller cannot edit the originals.
                "feature": dict(self.feature), "gate": dict(self.gate)}


# ------------------------------------------------------------------- loading ----

# `lru_cache(maxsize=1)` means: run this once, remember the answer, and hand back the same
# answer every time afterwards. The manifest file is large and never changes while the
# program is running, so reading it repeatedly would be pure waste.
@functools.lru_cache(maxsize=1)
def _manifest() -> dict:
    # YAML is a human-friendly format for settings files -- easier to read and edit than JSON.
    import yaml
    # `safe_load` rather than plain `load`: the unsafe version can be tricked into running
    # code hidden inside the file. Always the safe one, even for a file we wrote ourselves.
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


# Build the "how to run it" description from the raw manifest entry.
def _analysis_of(raw: dict) -> Analysis:
    # `or {}` copes with a module that declares no analysis section at all.
    a = raw.get("analysis") or {}
    specs = tuple(
        InputSpec(
            # The three compulsory fields are read directly, so a manifest missing one
            # fails loudly at startup rather than producing a broken form later.
            name=i["name"], kind=i["kind"], label=i["label"],
            # The optional ones are asked for politely, with sensible fallbacks.
            default=i.get("default"), note=i.get("note", ""),
            options=list(i.get("options") or []),
            minimum=i.get("minimum"), maximum=i.get("maximum"),
            max_items=i.get("max_items"), required=bool(i.get("required", False)),
        )
        for i in (a.get("inputs") or [])
    )
    return Analysis(
        adapter=a.get("adapter"),
        # ARTIFACT is the default. That is the SAFE default: a module that forgot to declare
        # its mode is treated as replay-only rather than being allowed to compute.
        mode=a.get("mode", "ARTIFACT"),
        typical_seconds=float(a.get("typical_seconds", 0.0)),
        summary=a.get("summary", ""),
        inputs=specs,
        artifact_reason=a.get("artifact_reason", ""),
    )


# The weekly programme, read once and remembered.
@functools.lru_cache(maxsize=1)
def weeks() -> tuple[WeekSpec, ...]:
    raw = _manifest().get("weeks") or []
    return tuple(WeekSpec(week=int(w["week"]), title=w["title"], question=w["question"],
                          stats_module=w["stats_module"],
                          summary=w.get("summary", ""),
                          feature=dict(w.get("feature") or {}),
                          gate=dict(w.get("gate") or {}))
                 # Sorted by week number, so the programme always reads in order however it
                 # happens to be written in the file.
                 for w in sorted(raw, key=lambda w: int(w["week"])))


# Every module, read once and remembered.
@functools.lru_cache(maxsize=1)
def modules() -> dict[str, ModuleSpec]:
    # Build a lookup from module to week, so each module can be told which week it belongs
    # to without that being written down twice.
    week_of: dict[str, int] = {}
    for w in weeks():
        week_of[w.stats_module] = w.week

    out: dict[str, ModuleSpec] = {}
    for raw in _manifest()["modules"]:
        ui = raw.get("ui") or {}
        out[raw["id"]] = ModuleSpec(
            id=raw["id"], index=int(raw["index"]), category=raw["category"],
            slug=raw["slug"], name=raw["name"],
            # `.strip()` trims stray blank space, which YAML text blocks pick up easily.
            purpose=(raw.get("purpose") or "").strip(),
            research_question=(raw.get("research_question") or "").strip(),
            adapter=raw["adapter"], wrapper_status=raw["wrapper_status"],
            status=raw["status"], experiment_id=raw.get("experiment_id"),
            inputs=tuple(raw.get("inputs") or []),
            outputs=tuple(raw.get("outputs") or []),
            canonical=tuple(raw.get("canonical") or []),
            limitations=tuple(raw.get("limitations") or []),
            notes=(raw.get("notes") or "").strip(),
            route=ui.get("route", ""), icon=ui.get("icon", ""),
            product_name=ui.get("product_name", "") or raw["name"],
            analysis=_analysis_of(raw),
            week=week_of.get(raw["id"]),
        )
    return out


# Look one module up by name.
def module(module_id: str) -> ModuleSpec | None:
    # `.strip().upper()` is forgiving about stray spaces and capitals, so a link with an
    # extra space still works. `.get` hands back None for an unknown name rather than
    # crashing -- the caller then reports UNKNOWN_MODULE properly.
    return modules().get((module_id or "").strip().upper())


# Look one week up by number.
def week(number: int) -> WeekSpec | None:
    # `next(..., None)` takes the first match, or None if there is none.
    return next((w for w in weeks() if w.week == number), None)


# The modules belonging to one week.
def weekly_modules(number: int) -> list[ModuleSpec]:
    w = week(number)
    if w is None:
        return []
    # A slightly indirect form that quietly drops the module if it does not exist, rather
    # than returning a list containing None for the caller to trip over.
    return [m for m in (module(w.stats_module),) if m]


#: The response envelope every module run returns, whatever it computed. Declared once
#: here so a week can publish its output schema without a second copy going stale.
# The field names every reply contains -- the same shape defined in contract.py, listed here
# once so the website can be told what to expect.
OUTPUT_SCHEMA = (
    "backend_version", "module_id", "week", "category", "name", "status", "mode",
    "mode_label", "mode_meaning", "experiment_id", "dataset", "inputs", "metrics",
    "series", "uncertainty", "observations", "figures", "tables", "provenance",
    "limitations", "message", "elapsed_s", "error",
)


# Everything the website needs to render one week.
def week_payload(number: int) -> dict | None:
    """A week as the interface consumes it.

    Routes, schemas, views and artifact sources are *derived* from the named module
    rather than restated in the manifest. Restating them would let a week advertise an
    endpoint, a parameter or an artifact its modules do not have, and the first person to
    notice would be a user looking at an empty panel.
    """
    # PLAIN ENGLISH: "derived, not restated" again, and the consequence spelled out plainly.
    # Write the web addresses down separately and a week could advertise a button that leads
    # nowhere. Building them from the module itself means they are correct by construction --
    # they cannot describe something that does not exist.
    w = week(number)
    if w is None:
        return None
    mods = weekly_modules(number)
    out = w.to_dict()
    # The web addresses, BUILT from the module names rather than typed out.
    out["backend_routes"] = {
        "week": "/api/weeks/%d" % w.week,
        "run_week": "/api/weeks/%d/run" % w.week,
        "modules": {m.id: "/api/modules/%s" % m.id for m in mods},
        "run_module": {m.id: "/api/modules/%s/run" % m.id for m in mods},
    }
    # The form fields, taken from the module's own declared settings -- so the form on
    # screen and the checks performed on submission are the same list, and can never differ.
    out["input_schema"] = {
        m.id: [i.to_dict() for i in m.analysis.inputs] for m in mods
    }
    out["output_schema"] = list(OUTPUT_SCHEMA)
    # Two views of the same module: a plain one for a general reader, and a detailed one for
    # a researcher.
    out["product_view"] = {m.id: "%s?mode=product" % m.route for m in mods if m.route}
    out["research_view"] = {m.id: "%s?mode=research" % m.route for m in mods if m.route}
    out["route"] = "/weeks/%d" % w.week
    out["artifact_sources"] = {m.id: list(m.outputs) for m in mods}
    # Whether each module can compute live, whether it is frozen, and how long it takes --
    # so the page can set expectations before somebody presses a button.
    out["execution"] = {
        m.id: {"mode": m.analysis.mode, "is_live": m.analysis.is_live,
               "protected": m.is_protected,
               "typical_seconds": m.analysis.typical_seconds,
               "artifact_reason": m.analysis.artifact_reason}
        for m in mods
    }
    out["modules"] = [m.to_dict() for m in mods]
    return out


# ---------------------------------------------------------------- validation ----

#: Upper bounds on anything a caller can ask for, so a request cannot become a denial of
#: service by asking for a hundred thousand documents.
# PLAIN ENGLISH: a "denial of service" is when somebody asks for something so enormous that
# the computer is still working on it hours later and everybody else is locked out. It need
# not even be malicious -- a typed extra zero would do it. These caps make it impossible.
LIMITS = {
    "sample_size": 5000,
    "instruments": 60,
    "bins": 50,
    "arms": 40,
    "text_length": 20000,
}


# THE BOUNCER. Check a request before anything else sees it.
def validate(spec: ModuleSpec, payload: dict | None) -> dict:
    """Coerce and range-check a request against the module's declared input schema.

    Unknown keys are rejected rather than ignored: a caller who misspells a parameter
    should be told, not silently given the default.
    """
    payload = dict(payload or {})
    # What this module actually accepts.
    declared = {i.name: i for i in spec.analysis.inputs}
    # Anything sent that is not on the list.
    unknown = sorted(set(payload) - set(declared))
    if unknown:
        # Refuse -- and helpfully list what IS accepted, so the mistake is fixable in one go.
        raise ValidationError(
            "unknown input(s) %s; this module accepts %s"
            % (", ".join(unknown), ", ".join(sorted(declared)) or "no inputs"))

    out: dict = {}
    for name, i in declared.items():
        # Take what was sent, or the default if nothing was.
        raw = payload.get(name, i.default)
        # Nothing supplied and no default.
        if raw is None or raw == "":
            if i.required:
                raise ValidationError("%s is required" % i.label)
            # Not required, so simply leave it out rather than passing a blank inwards.
            continue
        out[name] = _coerce(i, raw)
    # What comes back is a fresh set of boxes containing only checked, known settings.
    # Nothing the caller sent survives unexamined.
    return out


# Check and convert one value.
def _coerce(i: InputSpec, raw: Any) -> Any:      # noqa: C901 - one branch per kind
    # The note silences a style checker that objects to the number of branches. It is one
    # branch per kind of input, which is exactly as complicated as it should be.
    kind = i.kind
    if kind == "date":
        value = _as_date(i, raw)
        # Ranges checked in both directions, with messages naming the actual limit so the
        # caller can fix it immediately.
        if i.minimum and value < _as_date(i, i.minimum):
            raise ValidationError("%s is before the earliest available date %s"
                                  % (i.label, i.minimum))
        if i.maximum and value > _as_date(i, i.maximum):
            raise ValidationError("%s is after the latest available date %s"
                                  % (i.label, i.maximum))
        # Handed on in the one standard spelling, so nothing downstream has to parse dates.
        return value.isoformat()

    if kind in ("int", "float"):
        try:
            value = int(raw) if kind == "int" else float(raw)
        except (TypeError, ValueError) as exc:
            # `from exc` keeps the original error attached underneath, which helps anybody
            # debugging while the caller sees the plain message.
            raise ValidationError("%s must be a number" % i.label) from exc
        if i.minimum is not None and value < i.minimum:
            raise ValidationError("%s must be at least %s" % (i.label, i.minimum))
        if i.maximum is not None and value > i.maximum:
            raise ValidationError("%s must be at most %s" % (i.label, i.maximum))
        return value

    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        # Accept the ordinary human ways of writing yes and no, since web forms send text.
        if str(raw).lower() in ("true", "1", "yes"):
            return True
        if str(raw).lower() in ("false", "0", "no"):
            return False
        raise ValidationError("%s must be true or false" % i.label)

    if kind == "select":
        value = str(raw)
        # Must be one of the declared options. Anything else is refused, with the list.
        if i.options and value not in i.options:
            raise ValidationError("%s must be one of: %s"
                                  % (i.label, ", ".join(i.options)))
        return value

    if kind == "multiselect":
        values = _as_list(i, raw)
        if i.options:
            bad = [v for v in values if v not in i.options]
            # Every bad option is named at once, not just the first.
            if bad:
                raise ValidationError("%s: unknown option(s) %s"
                                      % (i.label, ", ".join(bad)))
        cap = i.max_items or LIMITS["instruments"]
        if len(values) > cap:
            raise ValidationError("%s accepts at most %d values" % (i.label, cap))
        return values

    if kind == "symbols":
        values = _as_list(i, raw)
        cap = i.max_items or LIMITS["instruments"]
        if len(values) > cap:
            raise ValidationError("%s accepts at most %d instruments" % (i.label, cap))
        for v in values:
            # A company symbol may contain letters, numbers, "&" and "-", and nothing else.
            # THIS IS A SECURITY CHECK, not a tidiness one. Symbols end up in file lookups
            # and queries, so refusing anything containing a slash, a dot or a quote mark is
            # what stops a crafted "symbol" from being used to reach somewhere it should not.
            if not v.replace("&", "").replace("-", "").isalnum() or len(v) > 24:
                raise ValidationError("%r is not a valid instrument symbol" % v)
        # Upper-cased, so "reliance" and "RELIANCE" are treated as the same company.
        return [v.upper() for v in values]

    if kind in ("text", "document"):
        # `document` differs from `text` only in how the interface offers it: a file
        # picker beside the box. What arrives is a string either way, capped the same
        # way, because an upload that skipped the length check would be an upload that
        # skipped validation.
        # PLAIN ENGLISH: exactly the right instinct. An uploaded file FEELS different from
        # typed text, and the temptation is to treat it differently. But it is the same text
        # arriving by a different route, and the moment one route skips a check, that route
        # becomes the way in.
        value = str(raw)
        if len(value) > LIMITS["text_length"]:
            raise ValidationError("%s is longer than %d characters"
                                  % (i.label, LIMITS["text_length"]))
        return value

    # An unrecognised kind means the manifest declares something this code does not
    # understand. Refuse, rather than passing an unchecked value inwards -- the whole point
    # of this function is that nothing gets past unexamined.
    raise ValidationError("unsupported input kind %r" % kind)


# Read a date, strictly.
def _as_date(i: InputSpec, raw: Any) -> dt.date:
    try:
        # `[:10]` keeps only the first ten characters -- "2026-03-05" -- so a full timestamp
        # is accepted too. `fromisoformat` insists on the international standard spelling,
        # which avoids the "03/05" ambiguity between March 5th and May 3rd entirely.
        return dt.date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        # And the message shows the required format rather than just saying "invalid".
        raise ValidationError("%s must be a date as YYYY-MM-DD" % i.label) from exc


# Read a list, from either a comma-separated string or a real list.
def _as_list(i: InputSpec, raw: Any) -> list[str]:
    if isinstance(raw, str):
        # Split on commas, trim the spaces, and drop empty pieces -- so "A, B, ,C" works.
        return [v.strip() for v in raw.split(",") if v.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(v).strip() for v in raw if str(v).strip()]
    # Anything else is refused rather than guessed at.
    raise ValidationError("%s must be a list" % i.label)
