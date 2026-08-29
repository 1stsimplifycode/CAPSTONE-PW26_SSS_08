"""Count-based event detection, and its hard dependency on the Week 2 arrival model.

An event here is a session whose trade count is too high to be ordinary. The detector's
whole difficulty is the word "too": it needs an expected count and a width, and the width
is exactly what the Week 2 arrival model measures.

Under a Poisson assumption the band would be::

    upper = lambda + z * sqrt(lambda)

That is what a detector writes when nobody has checked the dispersion. On NSE daily trade
counts the check has now been done (:mod:`research.market.arrival`) and the counts are
overdispersed by orders of magnitude -- the variance is thousands of times the mean, not
equal to it. A Poisson band on this data is narrower than reality by ``sqrt(Fano)``, so it
fires on almost every ordinary session and the detector is useless.

The corrected band widens by exactly that factor::

    upper = lambda + z * sqrt(lambda) * sd_inflation,    sd_inflation = sqrt(Fano)

**The dependency is structural, not decorative.** :class:`CountEventDetector` cannot be
constructed without an :class:`~research.market.arrival.OverdispersionResult`; passing
``None`` raises :class:`MissingWeek2Input`. There is no default, no fallback to Poisson,
and no silent degradation. Disconnect Week 2 and this detector stops working rather than
quietly reverting to a band that does not hold -- which is the difference between a real
dependency and a field that happens to share a name.

The Week 2 result reaches here through a persisted artifact,
``data/reference/week2_overdispersion.json``, written by
``scripts/build_week2_foundation.py`` and loaded by :func:`load_week2_overdispersion`.
Producer, stored result and consumer are three separable pieces, and the integration test
changes the stored value and asserts the detector's band moves.

PLAIN ENGLISH -- what this whole file is about:

THE JOB: spot days when a company was traded far more often than usual.

That sounds easy. It is not, and the entire difficulty is hidden in the word "unusual".

Suppose a company normally has about 1,000 trades a day. Today it had 1,400. Is that
strange? To answer, you need to know how much this number normally BOUNCES ABOUT. If it
is normally between 950 and 1,050, then 1,400 is astonishing. If it normally swings
between 200 and 5,000, then 1,400 is a perfectly dull Tuesday.

Now, there is a famous piece of mathematics called the POISSON distribution, which
describes how often random independent events happen -- raindrops on a roof, buses
arriving, calls to a call centre. It has one very convenient property: if the average is
1,000, then the typical bounce is the square root of 1,000, which is about 32. So
"unusual" would mean roughly more than 1,000 + 3x32 = 1,096.

Almost everybody writing a detector like this reaches for Poisson, because it is
standard and it makes the maths easy.

IT IS BADLY WRONG HERE, AND THIS PROJECT MEASURED HOW WRONG.

Poisson assumes events arrive independently, each one unaware of the others. Trades do
not behave remotely like that. Traders watch each other. One big trade attracts more.
News sets off a hundred at once. Trades arrive in BURSTS, like people leaving a cinema
rather than raindrops falling.

So the real bounce is not 32; it is roughly two hundred times bigger. Using the Poisson
band would flag nearly every ordinary day as an emergency -- an alarm that shrieks
constantly and therefore tells you nothing at all.

The fix is to widen the band by exactly the measured factor. Another part of this project
(the "Week 2 arrival model") measures how bursty the trades really are, and this detector
uses that measurement.

AND HERE IS THE PART WORTH ADMIRING. It would have been easy to write "use the measured
width if available, otherwise fall back to Poisson". That sounds sensible and helpful.
It would be a disaster: the detector would keep running, look perfectly healthy, and
quietly produce nonsense the moment the measurement went missing.

So instead this detector simply REFUSES TO EXIST without the real measurement. No
default. No fallback. Unplug the measurement and the detector stops dead. That is the
difference between a genuine dependency and one that is decorative.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For reading and writing JSON.
import json
# For building tidy record types.
from dataclasses import dataclass
# The world clock and the tool for reading the time.
from datetime import UTC, datetime
# A safe way to talk about places on the disk.
from pathlib import Path

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The project's address book.
from research.core import paths
# The record type holding the burstiness measurement. Importing the TYPE, not just a
# number, is what makes the check below possible.
from research.market.arrival import OverdispersionResult

# A label for this version of the detector.
COUNT_EVENTS_VERSION = "count-events-v1"

#: Where Week 2 publishes its dispersion result for Week 8 to consume.
# The name of the file that carries the measurement from the part that produces it to the
# part that needs it.
OVERDISPERSION_ARTIFACT = "week2_overdispersion.json"

#: Band half-width in standard deviations. 3 is the conventional control-chart choice and
#: is stated here rather than tuned.
# PLAIN ENGLISH: how many "typical bounces" above normal counts as an event. Three is the
# standard choice used in factory quality control the world over. "Stated here rather than
# tuned" is an honest and important admission: we picked the conventional value up front
# and left it alone. If we had fiddled with it until the results looked good, we would have
# been tuning the answer rather than measuring it.
DEFAULT_Z = 3.0


# A new kind of error, for when the measurement is missing.
class MissingWeek2Input(RuntimeError):
    """The detector was asked to run without the Week 2 arrival-dispersion result.

    Deliberately fatal. A Poisson fallback would look like a working detector while
    silently using a band that this repository has *measured* to be wrong by a factor of
    roughly two hundred on NSE daily counts.
    """
    # PLAIN ENGLISH: "wrong by a factor of roughly two hundred" is not a guess or a worry --
    # it is a number this project went and measured. Falling back to Poisson would not be a
    # slightly-less-good approximation; it would be a band two hundred times too narrow,
    # producing an alarm that fires constantly and means nothing.


# Work out where the measurement file lives.
def week2_artifact_path(root: Path | None = None) -> Path:
    # `root or paths.REFERENCE` means "use the folder you gave me, or the standard reference
    # folder if you gave me none". Allowing an override is what lets the tests point this at
    # a temporary folder instead of the real one.
    return (root or paths.REFERENCE) / OVERDISPERSION_ARTIFACT


# Save the measurement. Used by the part that PRODUCES it.
def save_week2_overdispersion(result: OverdispersionResult,
                              root: Path | None = None) -> Path:
    """Week 2 publishes. Called by the Week 2 build, never by Week 8."""
    # PLAIN ENGLISH: one side writes, the other side reads, and neither reaches into the
    # other. That keeps the two genuinely separable, which is what makes it possible to test
    # them independently -- and to change the stored file and watch the detector react.
    p = week2_artifact_path(root)
    # Make sure the folder exists.
    p.parent.mkdir(parents=True, exist_ok=True)
    # Turn the measurement into labelled boxes. `dict(...)` takes a copy, so the extra
    # entries added below cannot leak back into the caller's original result.
    payload = dict(result.to_dict())
    # Record which version of the format this is.
    payload["artifact_version"] = COUNT_EVENTS_VERSION
    # And exactly when it was written, so a reader can tell a fresh measurement from a stale
    # one left over from months ago.
    payload["written_at"] = datetime.now(UTC).isoformat()
    # And who is meant to read it. Writing the consumer's name into the file is a small
    # kindness to whoever finds this file in two years and wonders what it is for.
    payload["consumed_by"] = "research.detection.count_events.CountEventDetector"
    # Save it, laid out readably.
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


# Load the measurement. Used by the part that NEEDS it.
def load_week2_overdispersion(root: Path | None = None) -> OverdispersionResult:
    """Week 8 consumes. Raises when Week 2 has not published."""
    p = week2_artifact_path(root)
    # Not there?
    if not p.exists():
        # Stop. And look at the quality of this message: it says what is missing, WHY we
        # will not simply carry on, and the exact command to run to fix it. Somebody hitting
        # this at midnight can act on it without having to understand the whole project.
        raise MissingWeek2Input(
            "No Week 2 arrival-dispersion result at %s. The count-event detector needs "
            "it to size its alarm band and will not fall back to a Poisson assumption "
            "this repository has measured to be wrong. Run "
            "scripts/build_week2_foundation.py." % p)
    # Read the file, turn the JSON text back into labelled boxes, and rebuild the proper
    # record type from them.
    return OverdispersionResult.from_dict(json.loads(p.read_text(encoding="utf-8")))


@dataclass
# The detector itself.
class CountEventDetector:
    """Flags sessions whose trade count exceeds the dispersion-corrected band."""

    # The burstiness measurement. Note there is NO default value here -- you cannot make one
    # of these without supplying it, and that absence is the whole design.
    overdispersion: OverdispersionResult
    # How many bounces above normal counts as an event.
    z: float = DEFAULT_Z

    # The tidy-up step, run automatically after one is built. Here it is the bouncer on the
    # door.
    def __post_init__(self) -> None:
        # Did somebody explicitly pass None to get round the missing default?
        if self.overdispersion is None:
            raise MissingWeek2Input(
                "CountEventDetector requires a Week 2 OverdispersionResult. Passing "
                "None is not a supported configuration: the band would silently revert "
                "to Poisson.")
        # And a second, subtler check: did somebody pass a bare number instead of the real
        # measurement record?
        if not isinstance(self.overdispersion, OverdispersionResult):
            raise MissingWeek2Input(
                "overdispersion must be a research.market.arrival.OverdispersionResult, "
                "got %r. A bare number cannot say whether Week 2 ran."
                % type(self.overdispersion).__name__)
            # PLAIN ENGLISH on "a bare number cannot say whether Week 2 ran": if you hand
            # over the number 14.2, the detector has no way of telling whether that was
            # genuinely measured, guessed, or typed in by somebody in a hurry. The full
            # record carries its source, when it was computed and what it was based on -- so
            # insisting on the record is insisting on the evidence, not just the answer.

    # An alternative way of making one: go and fetch the measurement yourself.
    @classmethod
    def from_week2(cls, root: Path | None = None,
                   z: float = DEFAULT_Z) -> CountEventDetector:
        """The wiring the Week 8 stage uses: load what Week 2 published, then detect."""
        return cls(overdispersion=load_week2_overdispersion(root), z=z)

    # -- the band --------------------------------------------------------------------

    @property
    # How much wider the band must be than Poisson would say.
    def sd_inflation(self) -> float:
        """The Week 2 correction, read straight off the consumed result."""
        # "Read straight off" matters: this number is not recalculated or adjusted here. It
        # is exactly what was measured, passed through untouched, so there is no opportunity
        # for it to drift on the way.
        return self.overdispersion.sd_inflation()

    # Work out the alarm line.
    def upper_band(self, baseline: float | np.ndarray) -> np.ndarray:
        """``lambda + z * sqrt(lambda) * sd_inflation``."""
        # `lambda` here is the Greek letter used in statistics for "the expected number". It
        # has nothing to do with Python's `lambda` keyword.
        # `np.asarray(..., dtype=float)` accepts either a single number or a whole column and
        # treats both the same way, so this one line works for one day or for a million.
        lam = np.asarray(baseline, dtype=float)
        # normal + (3 x the Poisson bounce x the burstiness correction).
        # `np.maximum(lam, 0.0)` guards the square root: a rolling median should never come
        # out negative, but taking the root of a negative number would produce NaN and
        # silently disable the alarm for that row.
        return lam + self.z * np.sqrt(np.maximum(lam, 0.0)) * self.sd_inflation

    # The naive band, kept only so we can show what it would have done.
    def poisson_band(self, baseline: float | np.ndarray) -> np.ndarray:
        """What the band would have been without Week 2. For comparison only."""
        # PLAIN ENGLISH: this is never used to detect anything. It exists purely so the
        # report can show, in actual numbers, how much difference the correction makes. That
        # turns "we corrected for burstiness" from a claim into a demonstration.
        lam = np.asarray(baseline, dtype=float)
        return lam + self.z * np.sqrt(np.maximum(lam, 0.0))

    # -- detection -------------------------------------------------------------------

    # The main job: go through the data and flag the unusual days.
    def detect(self, counts: pd.DataFrame, baseline_window: int = 21) -> pd.DataFrame:
        """Flag per (symbol, session) events against a rolling baseline.

        The baseline is a trailing median of the symbol's own counts -- median rather than
        mean so that a previous event does not raise the bar against the next one, and
        strictly trailing so a session never helps predict itself.
        """
        # PLAIN ENGLISH on the two design choices in that sentence:
        #   MEDIAN, NOT MEAN. Suppose yesterday had a huge burst of 50,000 trades. An average
        #   would be dragged up by that one day, so "normal" would rise and today's genuine
        #   burst would slip under the alarm. The median -- the middle value -- barely moves,
        #   so one dramatic day cannot raise the bar against the next one.
        #   STRICTLY TRAILING. Today's own count must not be part of working out what normal
        #   looks like. Otherwise a huge day would partly define its own normal, and would be
        #   comparing itself against itself.

        # Check we have the three columns we need.
        need = {"symbol", "date", "trades"}
        missing = need - set(counts.columns)
        if missing:
            raise KeyError("counts frame is missing %s" % sorted(missing))

        # Sort by company and date, and take our own copy so the caller's table is untouched.
        df = counts.sort_values(["symbol", "date"]).copy()
        # Group by company: each firm's normal is judged against its own history, never
        # against other companies.
        g = df.groupby("symbol", sort=False)["trades"]
        df["baseline"] = g.transform(
            # `.shift(1)` moves everything down one row so today's own count is excluded --
            # this single call is the "strictly trailing" rule.
            # `.rolling(21)` looks at the last 21 trading days, about a month.
            # `min_periods=5` produces an answer once at least five days are available.
            # `.median()` takes the middle value.
            lambda s: s.shift(1).rolling(baseline_window, min_periods=5).median())

        # The real alarm line, using the measured burstiness.
        df["upper_band"] = self.upper_band(df["baseline"].to_numpy())
        # The naive line, for comparison only.
        df["poisson_upper_band"] = self.poisson_band(df["baseline"].to_numpy())
        # True where today's count is above the real line -- these are the events.
        df["count_event"] = df["trades"] > df["upper_band"]
        # True where it is above the naive line -- what a Poisson detector would have shouted
        # about. Kept side by side so the difference is visible in the data itself.
        df["count_event_poisson_only"] = df["trades"] > df["poisson_upper_band"]
        # Record which correction was applied, right there in the results, so a reader never
        # has to go hunting for it or take it on trust.
        df["sd_inflation_applied"] = self.sd_inflation
        return df

    # Describe this detector's settings, for the record.
    def to_dict(self) -> dict:
        return {
            "count_events_version": COUNT_EVENTS_VERSION,
            "z": self.z,
            # The formula written out, so a reader need not go and find the code.
            "band": "lambda + z * sqrt(lambda) * sd_inflation",
            "sd_inflation": self.sd_inflation,
            # Everything about the measurement we depended on -- including where it came from
            # and when it was computed, so the whole chain can be audited.
            "week2_input": {
                "fano_factor": self.overdispersion.fano_factor,
                "overdispersed": self.overdispersion.overdispersed,
                "model_selected": self.overdispersion.model_selected,
                "source": self.overdispersion.source,
                "computed_at": self.overdispersion.computed_at,
                "basis": self.overdispersion.basis,
            },
            # The dependency written out in plain words, in the results themselves.
            "dependency": (
                "research.market.arrival -> data/reference/week2_overdispersion.json -> "
                "this detector. Constructing without the Week 2 result raises "
                "MissingWeek2Input; there is no Poisson fallback."),
        }


# Summarise what the detector found.
def summary(detected: pd.DataFrame, detector: CountEventDetector) -> dict:
    # How many real events. `.sum()` counts the Trues, since True counts as 1.
    ev = int(detected["count_event"].sum())
    # How many the naive Poisson detector would have shouted about.
    pois = int(detected["count_event_poisson_only"].sum())
    # How many days we were able to judge at all -- those with a baseline worked out.
    scored = int(detected["baseline"].notna().sum())
    return {
        "count_events_version": COUNT_EVENTS_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "rows_scored": scored,
        "events_detected": ev,
        # What fraction of days were events. The `if scored else None` guard avoids dividing
        # by zero, and reports "unknown" rather than a made-up 0.0 when nothing was scored.
        "event_rate": float(ev / scored) if scored else None,
        # The comparison figures, named so plainly that no reader can misunderstand them.
        "events_a_poisson_detector_would_have_raised": pois,
        "poisson_event_rate": float(pois / scored) if scored else None,
        # How many false alarms the correction removed, as a fraction. If Poisson shouted
        # 1,000 times and we shout 50, this is 0.95 -- we removed 95% of the noise.
        "false_alarm_reduction": (
            float(1.0 - ev / pois) if pois else None),
        "detector": detector.to_dict(),
        # And finally the whole thing in a plain English sentence, with the real numbers
        # filled in -- so the point survives being read by somebody who never opens the code.
        "interpretation": (
            "The Poisson band would have called %d of %d scored sessions an event. "
            "Widening it by the Week 2 dispersion factor of %.1f leaves %d. The "
            "difference is the Week 2 result doing work."
            % (pois, scored, detector.sd_inflation, ev)),
    }
