"""Thin execution adapters for the STATS modules.

Every function here is a **wrapper**, not an implementation. Each one imports canonical
code that already exists in ``research/`` or ``scripts/`` and calls it. No statistical
method, feature definition, model or evaluation metric is defined in this package, and
none may be: when a module needs science that does not exist yet, the manifest marks it
``INFRASTRUCTURE_ONLY`` and the adapter returns NOT YET EXECUTED instead of inventing a
substitute.

That rule is what keeps the restructuring reversible. Deleting this package and the
``STATS`` directory would leave the research pipeline exactly as it was.

PLAIN ENGLISH -- what this whole file is about:

THE SHARED VOCABULARY EVERY MODULE ANSWERS IN.

THE RULE THIS PACKAGE IS BUILT ON: everything in here is a WRAPPER, never an
implementation. Not one line of statistics, not one feature definition, not one metric is
invented here. Each adapter finds the real code elsewhere and calls it.

WHY THAT MATTERS SO MUCH: if this package could define its own version of a calculation,
then over time there would be two versions of it -- the real one and this one -- and they
would slowly drift apart. Nobody would notice until two pages showed different numbers for
the same thing.
The docstring makes the strongest possible statement of it: delete this whole package and
the research pipeline is EXACTLY as it was. Nothing of value would be lost, because nothing
of value lives here.

AND THE RULE HOLDS EVEN WHEN IT IS INCONVENIENT. If a module needs analysis that has not
been written yet, the adapter does NOT knock together something approximate. It returns
NOT YET EXECUTED and writes nothing at all. See `not_yet_executed` below, which explains
exactly why a plausible placeholder would be the worst possible outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Exit codes shared with ``scripts/run_module.py`` and the .bat runners. Kept as plain
#: integers because a .bat file compares ERRORLEVEL numerically.
# PLAIN ENGLISH: six distinct outcomes, not two. .bat files can only see a number, so each
# meaning gets its own. The reader of a build log can tell "refused because protected" from
# "the code broke" from "this was never written".
OK = 0
FAILED = 1
BLOCKED = 3
INPUTS_MISSING = 4
SKIPPED_PROTECTED = 5
NOT_YET_EXECUTED = 6

# The human-readable name for each number, so a log never shows a bare "5".
STATUS_NAME = {
    OK: "OK",
    FAILED: "FAILED",
    BLOCKED: "BLOCKED",
    INPUTS_MISSING: "INPUTS MISSING",
    SKIPPED_PROTECTED: "SKIPPED (protected artifacts)",
    NOT_YET_EXECUTED: "NOT YET EXECUTED",
}


@dataclass
class StageResult:
    """What a module run reports back to the dispatcher."""
    code: int
    message: str = ""
    # `default_factory=list` gives EACH result its own fresh empty list. Writing `= []`
    # instead would share one list between every result ever created -- a classic and
    # extremely confusing Python bug.
    outputs: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        # An unknown code still prints readably rather than crashing.
        return STATUS_NAME.get(self.code, "UNKNOWN(%d)" % self.code)


def not_yet_executed(what: str, tracked_as: str) -> StageResult:
    """The honest return for a module whose science has not been written yet.

    Writes nothing. A module that produced a plausible-looking placeholder file would be
    indistinguishable from one that had actually run, which is the single most damaging
    thing this pipeline could do.
    """
    # PLAIN ENGLISH: "the single most damaging thing this pipeline could do" is not
    # overstatement. Imagine the module writes a file full of reasonable-looking numbers as a
    # placeholder. It sits on disk looking exactly like a real result. Six months later
    # somebody reads it, quotes it, builds on it. There is nothing about the file that says
    # it was invented.
    # So: write NOTHING. Say what is missing, and say where the gap is tracked.
    return StageResult(
        NOT_YET_EXECUTED,
        # AND THE MESSAGE SAYS IT TWICE, in the plainest terms: "No output was written and
        # no value was substituted."
        "%s is not implemented. Tracked as %s. No output was written and no value was "
        "substituted." % (what, tracked_as),
    )


def require(paths: list[str | Path]) -> StageResult | None:
    """Return an INPUTS MISSING result if any declared input is absent."""
    # Check the inputs BEFORE running, and name every missing one at once -- rather than
    # failing on the first, being fixed, then failing on the second.
    missing = [str(p) for p in paths if not Path(p).exists()]
    if missing:
        return StageResult(INPUTS_MISSING,
                           "missing input(s): %s" % ", ".join(missing))
    # None means "nothing wrong, carry on".
    return None


# ---------------------------------------------------------------- live analysis ----
#
# A second, distinct operation from the one above.
#
# ``StageResult`` describes *regenerating a module's artifacts*: it writes files, the
# protected guard applies, and it is what ``run.bat`` invokes.
#
# ``AnalysisResult`` describes *running a module's analysis over a slice the caller
# chose*: it writes nothing, takes validated parameters, and is what the backend invokes
# when someone presses a button. Keeping them separate is what lets the product be
# interactive without any request being able to overwrite a cited artifact.
#
# Both call the same canonical code. Neither defines any.
#
# PLAIN ENGLISH: TWO SEPARATE THINGS, AND THE SEPARATION IS A SECURITY BOUNDARY.
# StageResult = "regenerate the official files". Writes to disk. Guarded. Run deliberately
#               from a command line.
# AnalysisResult = "somebody clicked a button on the website". Writes NOTHING. Ever.
# Because they are different types with different code paths, there is no way for a web
# request to end up on the writing path. The interactivity is safe not because it is
# carefully guarded, but because the capability is simply absent.

def fmt_value(value, fmt: str = "auto") -> str:
    """Render a number the way the interface should show it.

    Formatting lives here rather than in the frontend so that a value and its rendering
    travel together: a metric that arrives as 0.9411660307392683 and is rounded in three
    different components is three chances to disagree about what the number is.
    """
    # PLAIN ENGLISH: a real observed problem. One long number, displayed in three places, each
    # rounding it its own way: 0.94, 0.941, 94%. A reader sees three different numbers for one
    # fact and cannot tell which is the number. So the value and its display text are computed
    # ONCE, here, and travel together everywhere.
    if value is None:
        # Nothing -> "n/a". Not "0", which would be a claim.
        return "n/a"
    if isinstance(value, bool):
        # Checked BEFORE the number check, because in Python True secretly equals 1 and
        # would otherwise print as "1".
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        # Not convertible -> show it as it is rather than hiding it.
        return str(value)
    # `num != num` is the standard test for NaN: not-a-number is the only value in all of
    # computing that is not equal to itself. Infinities caught alongside it.
    if num != num or num in (float("inf"), float("-inf")):
        return "n/a"
    if fmt == "int":
        # `{:,}` inserts thousands separators: 1234567 -> "1,234,567".
        return "{:,}".format(int(round(num)))
    if fmt == "pct":
        # `%%` prints one literal percent sign.
        return "%.1f%%" % (num * 100)
    if fmt == "sci":
        return "%.2e" % num
    if fmt.startswith("float"):
        # "float3" -> 3 decimals. `fmt[5:]` is everything after the word "float"; the `or 4`
        # covers a bare "float".
        return "%.*f" % (int(fmt[5:] or 4), num)
    if fmt == "inr":
        # Indian rupee formatting, which groups digits differently from the Western
        # convention -- and comes from the money module, not reinvented here.
        from research.scenario.money import inr
        return inr(num)
    # auto: integers as counts, everything else at four decimals.
    if isinstance(value, int) or float(num).is_integer():
        return "{:,}".format(int(num))
    return "%.4f" % num


def metric(key: str, label: str, value, fmt: str = "auto", note: str = "",
           source: str = "") -> dict:
    """One number, with everything the interface needs to render it honestly."""
    # THE RAW VALUE AND ITS DISPLAY TEXT TOGETHER -- plus a note explaining it and the file it
    # came from. A number never travels through this system naked.
    return {"key": key, "label": label, "value": value,
            "display": fmt_value(value, fmt), "format": fmt,
            "note": note, "source": source}


def series(key: str, label: str, columns: list[str], rows: list[list],
           note: str = "", total_rows: int | None = None) -> dict:
    """A named table the interface can chart, as columns rather than as a picture."""
    # PLAIN ENGLISH: "as columns rather than as a picture" is the important choice. Sending an
    # image would let the reader look but never check. Sending the actual numbers means they
    # can be re-plotted, exported, or recalculated by anyone.
    return {"key": key, "label": label, "columns": [str(c) for c in columns],
            "rows": rows, "note": note,
            # AND IF THE TABLE WAS CUT SHORT, IT SAYS SO -- plus the true total. A chart drawn
            # from the first 500 of 5,000 rows, with no warning, would silently misrepresent
            # the shape of the data.
            "truncated": bool(total_rows is not None and total_rows > len(rows)),
            "total_rows": total_rows if total_rows is not None else len(rows)}


@dataclass
class AnalysisResult:
    """What a live analysis returns. Writes nothing; every field is for the caller."""

    ok: bool = True
    #: Set only when ``ok`` is false, using the backend's status vocabulary.
    status: str = ""
    message: str = ""
    #: What the caller can do about a refusal. An error with no remedy is a dead end.
    # PLAIN ENGLISH: every refusal in this project must carry a way forward. "Something went
    # wrong" leaves a reader stuck; "the range you chose has 11 rows, widen it to at least 30"
    # lets them fix it themselves.
    remedy: str = ""
    dataset: dict = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    series: list[dict] = field(default_factory=list)
    uncertainty: dict = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


def insufficient(message: str, remedy: str) -> AnalysisResult:
    """The honest return when the caller's selection leaves nothing to analyse.

    A slice with three rows in it does not produce a small result; it produces a
    meaningless one. Saying so is the only correct behaviour.
    """
    # PLAIN ENGLISH: the crucial distinction. Three rows do not give you a LESS RELIABLE
    # answer -- they give you no answer at all, dressed up as a number.
    # A model scoring 1.000 on three rows looks perfect and means nothing. So rather than
    # returning it with a small footnote nobody reads, the analysis REFUSES and says why.
    return AnalysisResult(ok=False, status="INSUFFICIENT_DATA", message=message,
                          remedy=remedy)
