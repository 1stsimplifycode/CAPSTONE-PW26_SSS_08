"""The response contract every module endpoint returns, and the rules it must satisfy.

One shape for every module, so the interface has one renderer rather than forty. The
fields a reader needs in order to judge a number — where it came from, whether it was
computed or replayed, what bounds it — are required fields rather than optional extras,
because an optional provenance field is one that eventually goes missing.

:meth:`Response.check` is run before every response leaves the service. It refuses:

* a successful response with no provenance;
* a ``LIVE_COMPUTATION`` that names a prior run identifier, which would mean a replay
  wearing a live label;
* a ``VERIFIED_ARTIFACT`` with no artifact path, which would mean a live computation
  wearing a replay label;
* an absolute filesystem path anywhere in the payload.

PLAIN ENGLISH -- what this whole file is about:

THE SHAPE OF EVERY ANSWER THE WEBSITE EVER RECEIVES.

There are around forty different things this system can compute. Each could have replied
in its own format. Then the website would have needed forty different pieces of code to
display them, and every new module would mean writing a forty-first.

So instead every single one replies in the SAME shape. One shape, one display code.

BUT THE REAL POINT IS NOT TIDINESS. Look at what the shape makes COMPULSORY.

Every answer must say WHERE IT CAME FROM. Not "may include if convenient" -- must. The
reason is in the docstring and it is worth remembering:

    "an optional provenance field is one that eventually goes missing."

Anything optional gets skipped eventually. Somebody is in a hurry, the field is blank, and
a number arrives on screen with no way to tell where it came from. Making it required
means that can never happen, because a reply without it is rejected outright.

THE TWO LABELS THAT MUST NEVER BE SWAPPED:
  LIVE_COMPUTATION  -- "we worked this out just now, from the actual data."
  VERIFIED_ARTIFACT -- "we are showing you a saved result from an earlier run."
Both are perfectly honest. Confusing them is not. A saved result presented as if it were
freshly computed would let a stale number look live indefinitely.

So the checker below tests both directions:
  * a "live" answer that names a previous run -- that is a replay in disguise. Refused.
  * a "saved" answer that names no saved file -- that is a live computation in disguise.
    Refused.

AND THE LAST RULE: no absolute file paths anywhere in the reply. `C:/Users/alice/...`
would tell every visitor to the website Alice's username and how her computer is arranged,
while being of no use to them whatsoever.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# Record-building tools.
from dataclasses import asdict, dataclass, field
# "any kind of value at all".
from typing import Any

# The shared constants: the two mode names, their labels and meanings, the OK status, and
# the list of statuses that count as refusals.
from backend import (
    ARTIFACT,
    BACKEND_VERSION,
    LIVE,
    MODE_LABEL,
    MODE_MEANING,
    OK,
    REFUSALS,
)


@dataclass
# One number to be shown on screen.
class Metric:
    """One number the interface renders, with everything needed to render it honestly."""

    # A machine name for it.
    key: str
    # A human name for it.
    label: str
    # The value itself. It may be any of several kinds, or None for "unknown" -- which is
    # allowed on purpose, since an unknown must be showable.
    value: float | int | str | bool | None
    # The value already formatted as text, so the website does not have to decide how to
    # round it. That matters: if formatting happened on the website, two pages could show
    # the same number to different precision and appear to disagree.
    display: str
    # How it was formatted, recorded so the choice is visible.
    format: str = "float4"
    # Any caveat that belongs with this particular number.
    note: str = ""
    #: Repository-relative artifact this value was read from, when it was read rather
    #: than computed. Empty for a live computation, which is itself informative.
    # PLAIN ENGLISH: the last clause is neat -- a BLANK here is not missing information, it
    # is a statement. Empty means "computed fresh", and that is exactly what an empty source
    # should mean.
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
# A set of numbers to be drawn as a chart.
class Series:
    """A named series the interface can chart, as columns rather than as a picture."""
    # PLAIN ENGLISH: "as columns rather than as a picture" is an important choice. The
    # backend sends the NUMBERS, not a finished image. So the website can draw them however
    # suits the screen, a reader can download the actual data, and nobody is stuck with a
    # picture they cannot check or reuse.

    key: str
    label: str
    # The column headings, and the rows of values beneath them.
    columns: list[str]
    rows: list[list[Any]]
    note: str = ""
    # Whether the data was cut short to keep the reply a sensible size...
    truncated: bool = False
    # ...and how many rows there really are. Both together mean a shortened chart announces
    # itself, instead of silently looking like the whole picture.
    total_rows: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
# What comes back when something goes wrong.
class ContractError:
    # A machine-readable code.
    code: str
    # What went wrong, in words.
    reason: str
    #: What the caller can actually do about it. An error with no remedy is a dead end.
    # PLAIN ENGLISH: an error saying only "failed" leaves the reader stuck. This field
    # insists on a way forward -- "run this command first", "choose a different date". It is
    # the difference between an error message and a locked door.
    remedy: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
# THE SHAPE. Every reply from every module looks like this.
class Response:
    # Which module answered.
    module_id: str
    category: str
    name: str
    # Whether it worked.
    status: str
    # LIVE or ARTIFACT -- freshly computed, or replayed from a saved run.
    mode: str
    week: int | None = None
    experiment_id: str | None = None
    # Which data was used.
    dataset: dict = field(default_factory=dict)
    # What was asked for.
    inputs: dict = field(default_factory=dict)
    # The numbers, and the charts.
    metrics: list[Metric] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    # How confident to be in them.
    uncertainty: dict = field(default_factory=dict)
    # Plain-English notes about what was found.
    observations: list[str] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    # WHERE IT ALL CAME FROM. The field the checker below insists on.
    provenance: dict = field(default_factory=dict)
    # And which known gaps bound this answer -- so the caveats travel with the numbers all
    # the way to the screen.
    limitations: list[dict] = field(default_factory=list)
    message: str = ""
    elapsed_s: float = 0.0
    error: ContractError | None = None

    # -- the rules -----------------------------------------------------------------

    # THE CHECKER. Run on every single reply before it is allowed out.
    def check(self) -> list[str]:
        # Collect ALL the problems rather than stopping at the first, so whoever is fixing
        # it sees the full list in one go instead of one per attempt.
        problems: list[str] = []
        # The mode must be one of the two we recognise.
        if self.mode not in (LIVE, ARTIFACT):
            problems.append("mode %r is outside the declared scale" % self.mode)
        if self.status == OK:
            # A successful answer with no statement of where it came from is exactly what
            # this whole file exists to prevent.
            if not self.provenance:
                problems.append("a successful response with no provenance")
            # And a "success" containing nothing at all is a failure wearing a success label.
            if not self.metrics and not self.series:
                problems.append("a successful response with nothing in it")
        # Anything that is neither a success nor a recognised refusal must carry an error
        # record, or the caller is told something went wrong with no idea what.
        if self.status not in REFUSALS and self.status != OK and self.error is None:
            problems.append("status %s with no error record" % self.status)
        # And a refusal must say why. Note the wording of the message -- not merely "no
        # reason" but "no reason A CALLER COULD ACT ON".
        if self.status in REFUSALS and self.error is None:
            problems.append("a refusal with no reason a caller could act on")

        # THE TWO LABEL CHECKS, one in each direction.
        # A "live" answer naming a previous run is a replay wearing a live label.
        if self.mode == LIVE and self.provenance.get("replayed_run_id"):
            problems.append("a live computation carrying a replayed run identifier")
        # A "saved" answer naming no saved file is a live computation wearing a replay label.
        if self.mode == ARTIFACT and self.status == OK \
                and not self.provenance.get("artifacts"):
            problems.append("a verified-artifact response naming no artifact")

        # And finally, hunt the entire reply -- however deeply nested -- for a full computer
        # path that would leak somebody's private folder layout to the public.
        for path in _all_strings(self.to_dict()):
            if _looks_absolute(path):
                # `break` after the first, since one example is enough to make the point and
                # a page's worth of them would bury the other problems.
                problems.append("an absolute filesystem path in the payload: %s" % path)
                break
        return problems

    # Turn the whole reply into labelled boxes, ready to be sent as JSON.
    def to_dict(self) -> dict:
        return {
            # Which version of the backend produced this. Useful when a saved reply from
            # months ago turns up and somebody needs to know which rules it followed.
            "backend_version": BACKEND_VERSION,
            "module_id": self.module_id,
            "week": self.week,
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "mode": self.mode,
            # The mode is sent three ways: the code, a human label, and a full explanation
            # of what it means. So the website can display "Verified artifact" and explain
            # what that is, without having to know anything itself.
            "mode_label": MODE_LABEL.get(self.mode, self.mode),
            "mode_meaning": MODE_MEANING.get(self.mode, ""),
            "experiment_id": self.experiment_id,
            "dataset": self.dataset,
            "inputs": self.inputs,
            "metrics": [m.to_dict() for m in self.metrics],
            "series": [s.to_dict() for s in self.series],
            "uncertainty": self.uncertainty,
            # `list(...)` takes copies, so a caller who edits what they receive cannot reach
            # back and alter this response object.
            "observations": list(self.observations),
            "figures": list(self.figures),
            "tables": list(self.tables),
            "provenance": self.provenance,
            "limitations": list(self.limitations),
            "message": self.message,
            # Rounded to milliseconds -- more precision than that is meaningless noise.
            "elapsed_s": round(self.elapsed_s, 3),
            "error": self.error.to_dict() if self.error else None,
        }


# Walk through a nested reply and hand back every piece of text inside it.
def _all_strings(node: Any, depth: int = 0):
    # A depth limit, so a structure that somehow refers back to itself cannot send this
    # searching forever. Eight levels is far deeper than any real reply.
    if depth > 8:
        return
    # `yield` hands values back one at a time as they are found, rather than building a
    # complete list first -- which matters on a large reply.
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            # `yield from` passes along everything the deeper search finds.
            yield from _all_strings(v, depth + 1)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _all_strings(v, depth + 1)


# Does this text look like a full path on somebody's computer?
def _looks_absolute(text: str) -> bool:
    """A Windows drive path or a POSIX home path. Repository-relative paths are fine."""
    # A very long piece of text is prose, not a path. Skipping it also avoids scanning
    # something enormous for no reason.
    if len(text) > 4096:
        return False
    lowered = text.lower()
    return (
        # Windows style: a letter, a colon, then a slash -- "C:/" or "C:\".
        (len(text) > 2 and text[1] == ":" and text[2] in "\\/")
        # Or Linux and Mac style: a path inside somebody's home directory.
        or lowered.startswith("/home/") or lowered.startswith("/users/"))
    # Note what is deliberately ALLOWED: a path like "data/panel/prices.csv". That is
    # relative to the project, tells nobody anything private, and is genuinely useful to a
    # reader who wants to find the file for themselves.
