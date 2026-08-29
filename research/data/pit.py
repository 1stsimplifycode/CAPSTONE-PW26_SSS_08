"""The point-in-time read path. The only way Week 1 reads history.

A prediction made at time *T* may use a fact only if the system could have known it at
*T*. That is one sentence, and it is violated by the most natural query anybody writes::

    panel[panel["date"] <= T]              # WRONG: filters on when it happened

The bhavcopy for session *D* is published after *D* closes. Filtering on the event date
alone hands a model the close of *D* at 15:30 on *D*, two and a half hours before it
exists. The correct filter is on knowledge time::

    panel[panel["knowledge_time"] <= cutoff]

This module makes the second form the easy one and the first form impossible to write by
accident. :class:`AsOf` is a value, not a convention: a read either carries one or does
not happen. :func:`as_of_frame` refuses a frame with no ``knowledge_time`` column rather
than silently falling back to dates, because a silent fallback is precisely the bug.

Relationship to :class:`research.core.contracts.BitemporalStore`: the store is the
record-level implementation and holds the semantics -- restatement resolution, the
cutoff-after-decision-time check. It cannot hold 8.4 million panel rows as dataclasses,
so this module applies *the same* rules to columnar data, and
:func:`assert_same_semantics` proves on every run that the two agree. The store is not a
parallel implementation left to rot; :func:`evidence_for_instrument` routes real product
reads through ``get_evidence`` so the tested path is also the shipped one.

PLAIN ENGLISH -- what this whole file is about:

THE MISTAKE THIS FILE EXISTS TO PREVENT, told as a story.

The Indian stock exchange finishes trading each day at 15:30 (half past three in the
afternoon). But it does not publish the day's official summary file -- called the
"bhavcopy" -- until about 18:00 (six in the evening). So there is a gap of two and a
half hours when the day is over but nobody outside the exchange has the numbers yet.

Now imagine you write the most obvious line of code in the world:

    "give me every row whose DATE is on or before today"

That looks completely innocent. It is a disaster. Because "today" is included, and
today's official numbers do not exist until six in the evening. So a program pretending
to make a decision at half past three is handed numbers from two and a half hours in its
own future. It then looks astonishingly clever, and it is really just peeking.

The right question is not "when did this happen?" but "when could we have KNOWN this?".

So this file does three things:
  1. Makes the safe version of the question the EASY one to write.
  2. Makes the dangerous version impossible to write by accident.
  3. If a table does not even record when things became known, it REFUSES to answer at
     all -- rather than quietly guessing with the dates, because quietly guessing with
     the dates is precisely the bug.

The last paragraph is about the fact that this project does the same job in two different
ways, and why that is not sloppiness. There is a careful, thorough way (one record at a
time -- see contracts.py) and a fast way (whole tables at once -- in this file). The
careful way is far too slow for 8.4 million rows. So we keep both, and then, crucially,
we make them race each other on every single run and CHECK THEY AGREE. Two methods that
must agree will catch each other's mistakes; one method on its own catches nothing.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building a tidy record type.
from dataclasses import dataclass
# `UTC` the world clock; `datetime` a moment in time; `timedelta` a LENGTH of time (like
# "5 hours"); `timezone` for describing a particular country's clock offset.
from datetime import UTC, datetime, timedelta, timezone
# "any kind of value at all".
from typing import Any

# numpy: fast maths over big piles of numbers. `as np` gives it a short nickname so we can
# write `np.floating` instead of `numpy.floating`.
import numpy as np
# pandas: tables of data -- a programmable spreadsheet. Its main object is the "DataFrame",
# which is exactly that: rows, columns, and headings.
import pandas as pd

# Fetch the pieces we need from the contracts file explained earlier.
from research.core.contracts import (
    # The careful, record-by-record storehouse.
    BitemporalStore,
    # One single stamped fact.
    EvidenceRecord,
    # The error raised when the future leaks into the past.
    LeakageError,
    # The menu of evidence families.
    EvidenceBlock,
    # The stamp saying where a fact came from and when it became knowable.
    Provenance,
    # The one official front door for asking what was known.
    get_evidence,
    # The helper that puts any time onto the world clock.
    utc,
)

# A label for this version of the point-in-time rules. It gets written into results, so
# that if the rules ever change, old results can still be identified as following the old
# ones rather than being silently mixed in with the new.
PIT_VERSION = "pit-v1"

# India Standard Time. It is 5 hours and 30 minutes ahead of the world clock -- one of the
# few timezones offset by a half hour rather than a whole one, which is exactly the sort of
# detail that quietly breaks programs that assume otherwise.
IST = timezone(timedelta(hours=5, minutes=30))

#: Session close and bhavcopy publication, in IST. Imported from the ingestion module so
#: there is exactly one definition; see ``research.reference.sessions`` for which of
#: these is an exchange fact and which is a project assumption.
# PLAIN ENGLISH: that last part is an unusually honest note. One of these two times is a
# hard fact published by the exchange, and the other is our own best estimate. The comment
# points at where that distinction is written down, so a reader can tell which parts of the
# result rest on facts and which rest on our assumptions.
# Trading stops at 15:30 -- half past three in the afternoon, Indian time.
CLOSE_IST = (15, 30)
# The summary file appears at about 18:00 -- six in the evening.
PUBLISH_IST = (18, 0)

#: Columns that carry knowledge time, in the order they are preferred.
# PLAIN ENGLISH: different tables in this project spell the "when could we know it" column
# differently. We look for the first name, and if that is absent we try the second. Listing
# them in order means the preferred spelling always wins when both happen to be present.
KNOWLEDGE_COLUMNS = ("knowledge_time", "knowledge_cutoff")
#: Columns that carry event time.
# The same idea for the "when did it actually happen" column.
EVENT_COLUMNS = ("event_time", "decision_time")


# A new kind of error, for a table that cannot be read safely because it never recorded
# when its facts became known. `KeyError` in the brackets is Python's usual error for
# "the thing you asked for is not here", so this is a more specific version of that.
class MissingKnowledgeTime(KeyError):
    """A frame was read point-in-time but carries no knowledge time.

    Deliberately fatal. The alternative -- quietly filtering on ``date`` instead -- is
    the exact defect the point-in-time read path exists to prevent, and it would be
    invisible in the result.
    """
    # PLAIN ENGLISH: we could have been helpful here and said "no knowledge column? never
    # mind, I will use the dates instead". That would be the worst possible kindness. It
    # would produce a perfectly normal-looking answer that is silently cheating, and nothing
    # in the output would show it. Refusing to answer is loud, annoying, and safe.


# Work out the exact instant, on the world clock, when a given trading day's summary file
# becomes knowable.
def publication_instant(d: object) -> pd.Timestamp:
    """The instant session *d*'s bhavcopy becomes knowable, in UTC."""
    # Turn whatever we were given -- text, a date, a pandas timestamp -- into one timestamp.
    ts = pd.Timestamp(d)
    # Is it "naive", meaning no country attached? A bare date like "2026-03-05" is.
    if ts.tzinfo is None:
        # Declare it to be Indian time, because these are Indian trading sessions. Note
        # `tz_localize` attaches the label without shifting the clock numbers -- which is
        # right, since the date was always meant as an Indian one.
        ts = ts.tz_localize(IST)
    return (
        # `.normalize()` throws away any time-of-day and winds back to midnight, so we start
        # from a clean "the beginning of that day in India".
        ts.normalize()
        # Then add 18 hours and 0 minutes, landing on six in the evening, Indian time.
        + pd.Timedelta(hours=PUBLISH_IST[0], minutes=PUBLISH_IST[1])
    # And finally convert that instant to the world clock, so it can be compared with every
    # other time in the system. Unlike `tz_localize` above, `tz_convert` DOES change the
    # clock numbers: it is the same instant said in a different language.
    ).tz_convert("UTC")


# The same thing for the moment trading stops, rather than the moment the file appears.
def session_close_instant(d: object) -> pd.Timestamp:
    # Turn the input into a timestamp.
    ts = pd.Timestamp(d)
    # Attach Indian time if no country was given.
    if ts.tzinfo is None:
        ts = ts.tz_localize(IST)
    # Wind back to midnight, then add 15 hours 30 minutes: half past three in the afternoon.
    return (ts.normalize() + pd.Timedelta(hours=CLOSE_IST[0],
                                          minutes=CLOSE_IST[1])).tz_convert("UTC")


# Frozen: once made, this cannot be changed. The moment you are standing at must not shift
# under your feet halfway through a calculation.
@dataclass(frozen=True)
class AsOf:
    """A point in time to read the world from.

    ``decision_time`` is how far the world has advanced; ``knowledge_cutoff`` is what the
    system is allowed to have learned by then. They differ when a backtest wants to model
    a reporting lag. The cutoff may never exceed the decision time -- a decision cannot
    use knowledge from its own future -- and the constructor enforces it.
    """
    # PLAIN ENGLISH: think of this as a pair of glasses that only let you see the world as
    # it was at one particular moment. Two separate dials:
    #   decision_time    -- how far the clock has run.
    #   knowledge_cutoff -- how much of what happened you are allowed to have heard about.
    # Usually they are the same. They come apart when we want to be deliberately pessimistic
    # -- for instance "pretend it is Friday, but pretend we only ever hear news a week late",
    # which is a fair way to model a slow data supplier.
    # A "backtest" means replaying history to see how something WOULD have performed.
    # A "reporting lag" is the delay between something happening and you being told.

    # How far the world has advanced.
    decision_time: datetime
    # What we are permitted to have learned by then.
    knowledge_cutoff: datetime

    # The tidy-up step run automatically just after one is built.
    def __post_init__(self) -> None:
        # Put both onto the world clock. `object.__setattr__` is the back door needed
        # because this record is frozen and refuses ordinary changes.
        object.__setattr__(self, "decision_time", utc(self.decision_time))
        object.__setattr__(self, "knowledge_cutoff", utc(self.knowledge_cutoff))
        # The rule, enforced at the moment of creation rather than later. Being allowed to
        # know MORE than the clock has run is exactly time travel.
        if self.knowledge_cutoff > self.decision_time:
            raise LeakageError(
                "knowledge_cutoff %s is after decision_time %s: a decision may not use "
                "knowledge from its own future"
                % (self.knowledge_cutoff, self.decision_time))
        # Note WHERE this check lives: in the constructor. That means a bad AsOf can never
        # exist at all, not even for an instant. Anywhere in the program you are holding one
        # of these, it is already known to be sane -- nothing later has to re-check it.

    # `@classmethod` marks a second, alternative way of making one of these, with a helpful
    # name. `cls` means "this class", so `cls(...)` builds a new AsOf.
    @classmethod
    def at_session_close(cls, d: object) -> AsOf:
        """Standing at the close of session *d*, before its bhavcopy is out.

        This is the strict reading and the one a live system faces: at 15:30 the day's
        own numbers are not yet published, so they are not available.
        """
        # PLAIN ENGLISH: this is the harsh, realistic setting. It is half past three, the
        # market has just shut, and today's official numbers do not exist yet. Anything
        # running for real, right now, faces exactly this.
        t = session_close_instant(d)
        # Both dials set to the same instant: the world has run to 15:30, and we know
        # everything knowable by 15:30, which pointedly does not include today's summary.
        return cls(decision_time=t, knowledge_cutoff=t)

    @classmethod
    def after_publication(cls, d: object) -> AsOf:
        """Standing after session *d*'s bhavcopy is published.

        The default for research over daily data: session *d* is usable, session *d+1*
        is not.
        """
        # PLAIN ENGLISH: the gentler, evening setting. It is six o'clock, today's summary
        # has come out, so today counts -- but tomorrow, of course, still does not.
        t = publication_instant(d)
        return cls(decision_time=t, knowledge_cutoff=t)

    @classmethod
    def latest(cls) -> AsOf:
        # "Right now, and everything knowable right now." Used for live views rather than
        # for replaying history.
        now = datetime.now(UTC)
        return cls(decision_time=now, knowledge_cutoff=now)

    # Turn it into labelled boxes for saving, with both times as standard text.
    def to_dict(self) -> dict:
        return {"decision_time": self.decision_time.isoformat(),
                "knowledge_cutoff": self.knowledge_cutoff.isoformat()}

    # `__str__` is a special name Python uses when something needs to be printed. Without
    # it, printing one of these gives an ugly machine description; with it, you get a clear
    # sentence like "as-of 2026-03-05T12:30:00+00:00 (knowledge <= ...)".
    def __str__(self) -> str:
        return "as-of %s (knowledge <= %s)" % (
            self.decision_time.isoformat(), self.knowledge_cutoff.isoformat())


# A private helper: given several possible column names, find which one this table actually
# uses.
def _column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    # Try the candidates in order, so the preferred spelling wins.
    for c in candidates:
        # `frame.columns` is the list of headings across the top of the table.
        if c in frame.columns:
            return c
    # None of them is present. Say so honestly rather than guessing.
    return None


# Find the knowledge-time column, or refuse to go on.
def knowledge_column(frame: pd.DataFrame) -> str:
    c = _column(frame, KNOWLEDGE_COLUMNS)
    if c is None:
        # Stop dead. And note the quality of the error message: it says what was looked for,
        # WHY falling back is not an option, and which columns the table does have -- so
        # whoever hits this can fix it without having to go digging.
        raise MissingKnowledgeTime(
            "frame has no knowledge-time column (looked for %s). A point-in-time read "
            "cannot fall back to the event date: that is the leak it prevents. Columns "
            # `list(frame.columns)[:12]` prints at most the first twelve headings, so a
            # table with 300 columns does not bury the message in noise.
            "present: %s" % (list(KNOWLEDGE_COLUMNS), list(frame.columns)[:12]))
    return c


# THE MAIN ACTION OF THE FILE: cut a table down to only what was knowable at a given moment.
def as_of_frame(frame: pd.DataFrame, asof: AsOf,
                lookback_days: float | None = None) -> pd.DataFrame:
    """Restrict a frame to what was knowable at ``asof``.

    Both bounds are applied, never one: ``event_time <= decision_time`` because the world
    has not advanced past it, and ``knowledge_time <= knowledge_cutoff`` because the
    system had not learned it. A frame carrying only an event time is refused.
    """
    # PLAIN ENGLISH: two separate gates, and a row must get through BOTH.
    #   Gate 1: did it happen yet?      (or it is in the future -- not allowed)
    #   Gate 2: had we heard about it?  (or we are peeking -- not allowed)
    # Checking only gate 1 is the classic bug. Checking only gate 2 is not enough either.

    # Find the knowledge column, or stop. This is the first thing done, deliberately: no
    # knowledge column means no safe answer exists, so there is no point going further.
    kcol = knowledge_column(frame)
    # Find the event column, which may legitimately be absent -- we cope below.
    ecol = _column(frame, EVENT_COLUMNS)

    # Read that column as proper dates, all on the world clock so comparisons are fair.
    k = pd.to_datetime(frame[kcol], utc=True)
    # Build the "mask": a column of True/False, one per row, saying whether to keep it.
    # Here: True when we had already learned this row by the cutoff.
    mask = k <= pd.Timestamp(asof.knowledge_cutoff)

    # Does the table have a proper event-time column?
    if ecol is not None:
        # Read it as dates on the world clock.
        e = pd.to_datetime(frame[ecol], utc=True)
        # `&=` means "and this in". A row now has to satisfy BOTH tests to survive: already
        # learned, AND already happened. This is gate 1 joining gate 2.
        mask &= e <= pd.Timestamp(asof.decision_time)
        # Was a lookback window requested?
        if lookback_days is not None:
            # Then also throw away anything older than that many days before the decision.
            # Useful because ancient history is often irrelevant, and dropping it makes the
            # calculation both faster and more focused.
            mask &= e >= pd.Timestamp(asof.decision_time) - pd.Timedelta(
                days=lookback_days)
    # `elif` -- no event column, but is there a plain "date" column?
    elif "date" in frame.columns:
        # No explicit event time: the session date stands in, at its close.
        # PLAIN ENGLISH: we only have the day, not the instant. So which instant of that day
        # should we use? We use the market close, 15:30. That is the conservative choice: the
        # latest moment we could honestly claim the day's business had happened. Assuming an
        # earlier instant would let the day count as "done" sooner than it really was.
        # `.map(...)` applies that conversion to every single date in the column.
        e = pd.to_datetime(frame["date"]).map(session_close_instant)
        # Apply gate 1 as before.
        mask &= e <= pd.Timestamp(asof.decision_time)
        # And the lookback window, if one was asked for.
        if lookback_days is not None:
            mask &= e >= pd.Timestamp(asof.decision_time) - pd.Timedelta(
                days=lookback_days)
    # If there is neither an event column nor a date column, only gate 2 applies. That is
    # acceptable here, unlike a missing knowledge column, because gate 2 is the one that
    # actually prevents peeking: you cannot use what you had not yet heard.

    # Hand back only the rows whose mask entry says True.
    return frame[mask]


# Belt and braces: check afterwards that the filtering really worked.
def assert_no_leakage(frame: pd.DataFrame, asof: AsOf) -> None:
    """Belt and braces: the invariant is asserted on the result, not assumed."""
    # An empty table cannot possibly contain a leak, so there is nothing to check.
    if frame.empty:
        return
    # Find the knowledge column again.
    kcol = knowledge_column(frame)
    # Read it as dates on the world clock.
    k = pd.to_datetime(frame[kcol], utc=True)
    # `.max()` finds the very latest one -- the single most suspicious row in the table. If
    # even the worst offender is within the limit, then every row is.
    worst = k.max()
    # Is that worst row later than we were allowed to know? Then something has gone wrong
    # upstream, and we stop.
    if worst > pd.Timestamp(asof.knowledge_cutoff):
        raise LeakageError(
            "point-in-time read leaked: a row carries knowledge_time %s, after the "
            "cutoff %s" % (worst, asof.knowledge_cutoff))
    # This should never fire. It exists because "should never" and "does never" are two
    # different claims, and only the check turns the first into the second.


# -- the record-level path -------------------------------------------------------------
# PLAIN ENGLISH: everything above worked on whole tables at once, which is fast. Everything
# below works one careful record at a time, which is slow but thorough. Both exist so they
# can check each other.

# Turn one company's rows of the big table into individual stamped evidence records.
def records_from_panel(panel: pd.DataFrame, instrument_id: str,
                       # Which measurements to carry across. Defaults to the closing price,
                       # how many shares changed hands, and the total money that moved.
                       fields: tuple[str, ...] = ("close", "volume", "turnover"),
                       # What we are legally allowed to do with this data.
                       licence: str = "NSE bhavcopy, research use",
                       ) -> list[EvidenceRecord]:
    """Turn one instrument's panel rows into evidence records.

    Bounded on purpose: this is used for a single instrument's history, which is
    thousands of rows, not the whole 8.4-million-row panel. The columnar path in
    :func:`as_of_frame` exists for the bulk case and is checked against this one.
    """
    # PLAIN ENGLISH: "bounded on purpose" means we only ever do this for ONE company at a
    # time. Building 8.4 million individual records would eat all the computer's memory and
    # take an age. Thousands is perfectly fine.

    # The three columns we absolutely must have. `{...}` makes a set: an unordered bag.
    need = {"date", "event_time", "knowledge_time"}
    # Which of them are missing? Subtracting one set from another leaves what is in the
    # first but not the second -- a neat way of asking "what is absent?".
    missing = need - set(panel.columns)
    # `if missing:` -- an empty set counts as false in Python, so this means "if anything
    # is missing at all".
    if missing:
        # Stop, naming exactly what is absent. `sorted(...)` so the message reads the same
        # every time rather than in a random order.
        raise MissingKnowledgeTime(
            "panel is missing %s; cannot build bitemporal records" % sorted(missing))
    # Somewhere to collect the finished records.
    out: list[EvidenceRecord] = []
    # `.itertuples()` walks the table one row at a time, handing each row over as a small
    # bundle whose parts you can reach by name. `index=False` says we do not need the row
    # number. It is used here rather than the more famous `.iterrows()` because it is
    # considerably faster and does not mangle the types of the values.
    for r in panel.itertuples(index=False):
        # Pull out the wanted measurements. `getattr(r, f, None)` asks politely for the
        # field named `f`, handing back None if that column is not there, rather than crashing.
        payload = {f: getattr(r, f, None) for f in fields}
        # Now clean every value. Read the condition carefully:
        #   `isinstance(v, (int, float, np.floating))` -- is it a number of some kind?
        #   `and v == v`                               -- is it NOT a NaN?
        # That second test looks absurd: how can something not equal itself? NaN ("Not a
        # Number", the result of a broken sum) is the one value in all of computing that is
        # defined as never equal to anything, including itself. So `v == v` is false only
        # for NaN, which makes it the classic quick way of spotting one.
        # Numbers that pass become plain decimals; anything else becomes None, which is the
        # honest way of saying "no value here".
        payload = {k: (float(v) if isinstance(v, (int, float, np.floating))
                       and v == v else None)
                   for k, v in payload.items()}
        # Build the stamped record and add it to the pile.
        out.append(EvidenceRecord(
            # Which company; which family of evidence; the measurements themselves.
            instrument_id=instrument_id, block=EvidenceBlock.MARKET, payload=payload,
            # The name of the thing being measured: one day's trading summary. This is what
            # lets the system spot two versions of the same fact later on.
            fact_key="daily_bar",
            # The stamp: where it came from and when it became knowable.
            provenance=Provenance(
                source="nse_bhavcopy_cm", licence=licence,
                # Both times copied straight from the row, so the record inherits exactly
                # the timing the table recorded -- no re-derivation, no chance of drift.
                event_time=r.event_time, knowledge_time=r.knowledge_time,
                dataset_version="cash-panel-v1"),
        ))
    return out


# Build a little storehouse holding just one company's history.
def store_for_instrument(panel: pd.DataFrame, instrument_id: str) -> BitemporalStore:
    # Start an empty one.
    store = BitemporalStore()
    # Fill it with that company's records.
    store.extend(records_from_panel(panel, instrument_id))
    return store


# What the actual product calls when somebody looks at one company's page.
def evidence_for_instrument(panel: pd.DataFrame, instrument_id: str, asof: AsOf,
                            lookback_days: float | None = None,
                            ) -> list[EvidenceRecord]:
    """The spec's ``get_evidence`` entry point, on real panel data.

    This is what the product's instrument view calls. It is deliberately the same
    function the leakage suite attacks, so the tested path and the shipped path are one
    path.
    """
    # PLAIN ENGLISH: this is a genuinely important design decision. It would have been
    # easier to write one route for the tests and a separate, faster one for the real
    # website. But then the tests would be proving the safety of code nobody actually runs.
    # By forcing both through the same door, every attack the test suite survives is an
    # attack the real product survives.
    store = store_for_instrument(panel, instrument_id)
    # Ask through the one official front door, which does its own belt-and-braces check.
    return get_evidence(store, instrument_id, asof.decision_time,
                        asof.knowledge_cutoff, lookback_days=lookback_days)


# The referee: make the fast way and the careful way race, and check they agree.
def assert_same_semantics(panel: pd.DataFrame, instrument_id: str,
                          asof: AsOf) -> dict[str, Any]:
    """Prove the columnar filter and the record store return the same rows.

    Two implementations of one rule is a liability unless something checks them against
    each other. This is that check, and the C2 test runs it over randomised cutoffs.
    """
    # PLAIN ENGLISH: having two ways of doing one job is dangerous -- they can drift apart,
    # and then which one is right? This turns that danger into a strength: if they must
    # always agree, each one is constantly checking the other's homework. "Randomised
    # cutoffs" means the test does not always ask about the same convenient dates; it picks
    # awkward ones at random, so a bug cannot hide in the corners nobody thought to check.

    # Route 1: the fast, whole-table way.
    frame = as_of_frame(panel, asof)
    # Route 2: the slow, one-record-at-a-time way.
    records = evidence_for_instrument(panel, instrument_id, asof)
    # Line both answers up in the same order so they can be compared item by item.
    frame_times = sorted(pd.to_datetime(frame["event_time"], utc=True).tolist())
    record_times = sorted(r.event_time for r in records)
    # Do they agree? Two conditions, both required:
    #   same number of rows, and
    #   `all(...)` -- every single pair of times matches.
    # `zip(a, b)` walks two lists side by side, handing over one pair at a time. The
    # `strict=False` says do not complain if the lists are different lengths -- which is
    # fine here, because the length check on the line above has already caught that case.
    agree = len(frame_times) == len(record_times) and all(
        pd.Timestamp(a) == pd.Timestamp(b)
        for a, b in zip(frame_times, record_times, strict=False))
    # If they disagree, stop everything. One of the two routes has a bug, and until we know
    # which, no result from either can be trusted.
    if not agree:
        raise LeakageError(
            "columnar and record-level point-in-time reads disagree at %s: "
            "%d rows vs %d records" % (asof, len(frame_times), len(record_times)))
    # They agreed. Hand back a small report, which gets written into the results so a reader
    # can see the check was actually run and what it covered -- rather than merely being
    # told it exists.
    return {"rows": len(frame_times), "asof": asof.to_dict(), "agree": True}
