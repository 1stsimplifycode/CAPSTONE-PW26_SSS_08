"""Data contracts for AEGIS-Market.

Everything that enters the system is an :class:`EvidenceRecord` carrying a
:class:`Provenance` stamp. The stamp is what makes point-in-time correctness checkable
rather than merely intended (spec sections 25-27).

Four timestamps, and the distinction between them is the whole point:

``event_time``        when the thing described actually happened
``publication_time``  when a publisher first made it public
``knowledge_time``    when *this system* could first have acted on this exact value
``retrieval_time``    when we fetched it

A restatement shares ``event_time`` with the value it restates but carries a later
``knowledge_time``. A query as of an earlier cutoff must return the original value, not
the restatement -- that is leakage test L3.

PLAIN ENGLISH -- what this whole file is about, and why it matters more than any other:

This file exists to stop the project CHEATING BY ACCIDENT.

Here is the cheat. Suppose you are building something that tries to predict which
companies are in trouble. You test it on the year 2020. It gets nearly everything
right! Brilliant... except that the numbers you fed it for January 2020 were the
CORRECTED numbers, the ones published in June 2020 after the company admitted its
first figures were wrong.

In January, nobody on Earth knew those corrected numbers. Your program was not clever.
It was peeking at the answers. This is called LEAKAGE -- information leaking backwards
from the future into the past -- and it is the single most common way that a piece of
research can be completely, confidently wrong.

The fix is to write down FOUR separate times for every single fact, because "when" is
genuinely four different questions:

  event_time        -- when the thing actually happened.
                       ("The company's sales for March were 100.")
  publication_time  -- when it was first announced to the world.
                       ("They announced it on 15 April.")
  knowledge_time    -- when WE could first have known this exact value.
                       (Maybe our data supplier only got it to us on 17 April.)
  retrieval_time    -- when we actually downloaded it onto this computer.

Now the trick in the last paragraph above. A "restatement" is when a company says
"sorry, March's sales were not 100, they were 80." That correction is about MARCH
(same event_time) but it only became known in JUNE (later knowledge_time).

So if you ask this system "what did we know on 1 May?", it must answer 100 -- the wrong
number! Because 100 is genuinely what anybody could have known on 1 May. Answering 80
would be peeking at the future. Being deliberately, carefully "wrong" in this exact way
is what makes the research honest, and the test that checks it is called L3.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For making fingerprints of information.
import hashlib
# For turning information into JSON text.
import json
# Three type hints describing kinds of collections:
#   `Iterable` -- something you can walk through once, item by item.
#   `Iterator` -- the walker itself, which hands you the next item each time you ask.
#   `Sequence` -- an ordered collection you can also count and index into, like a list.
from collections.abc import Iterable, Iterator, Sequence
# Tools for tidy records: turn one into boxes, mark a class as a record, smarter defaults.
from dataclasses import asdict, dataclass, field
# The world clock, and the tool for reading dates and times.
from datetime import UTC, datetime
# For building fixed menus of allowed choices.
from enum import StrEnum
# "any kind of value at all".
from typing import Any


# A menu naming which family of evidence a fact belongs to.
class EvidenceBlock(StrEnum):
    """Which evidence block a recorded fact belongs to. One value per feature block."""

    # Prices and trading volumes -- what the market did.
    MARKET = "MARKET"
    # The company's own accounts -- sales, profits, debts.
    FUNDAMENTALS = "FUNDAMENTALS"
    # The fine detail of trading: individual orders and trades, second by second.
    # ("Microstructure" means the tiny-scale structure of how a market actually works.)
    MICROSTRUCTURE = "MICROSTRUCTURE"
    # What mood the whole market is in -- calm, panicking, and so on.
    REGIME = "REGIME"
    # How trouble spreads from one company to another, like a cold going round a class.
    PROPAGATION = "PROPAGATION"


#: Blocks subject to the licence gate, i.e. those redistributed under terms that the
#: gate must check before a payload leaves the process.
# PLAIN ENGLISH: of the five families above, only company accounts data comes with legal
# strings attached, so it is the only one the librarian (see licensing.py) has to inspect
# before anything is allowed out of the door. Prices we may share; accounts we may not,
# unless the licence says so.
GATED_BLOCKS = frozenset({EvidenceBlock.FUNDAMENTALS})


# A menu of how much trouble a company appears to be in, right now.
class RiskState(StrEnum):
    """Temporal integrity-risk states (spec section 6).

    Ordered by escalation level; not every episode visits every state.
    """
    # PLAIN ENGLISH: like the stages of an illness. "Escalation level" means how serious
    # things are. "Not every episode visits every state" means trouble does not always go
    # neatly through all the stages -- sometimes it jumps, and sometimes it gets better
    # before reaching the worst.

    # Nothing unusual. All quiet.
    NORMAL = "NORMAL"
    # The very first hint that something might be off.
    EARLY_WARNING = "EARLY_WARNING"
    # A pattern is starting to form.
    EMERGING = "EMERGING"
    # Something is definitely happening now.
    ACTIVE = "ACTIVE"
    # It is getting worse.
    ESCALATING = "ESCALATING"
    # The worst point.
    PEAK = "PEAK"
    # It is getting better, but it is not over.
    RESOLVING = "RESOLVING"
    # It is over.
    RESOLVED = "RESOLVED"

    # `@property` makes the next action behave like a plain fact you can read. You write
    # `state.level`, with no brackets, even though a little calculation happens behind it.
    @property
    # How serious is this state, as a number? Numbers can be compared and sorted; words
    # cannot. This is what lets other code ask "is this worse than that?".
    def level(self) -> int:
        # Look the answer up in the table defined just below.
        return _STATE_LEVEL[self]

    @property
    # Is this one of the states that counts as "we are inside a period of trouble"?
    def is_elevated(self) -> bool:
        """True for states that count as inside a risk window."""
        return self in _ELEVATED


# The lookup table turning each state into a seriousness number.
_STATE_LEVEL = {
    # All quiet: zero.
    RiskState.NORMAL: 0,
    # Then climbing, one step at a time, as things get worse.
    RiskState.EARLY_WARNING: 1,
    RiskState.EMERGING: 2,
    RiskState.ACTIVE: 3,
    RiskState.ESCALATING: 4,
    # The peak is the most serious.
    RiskState.PEAK: 5,
    RiskState.RESOLVING: 2,   # de-escalating but still inside the window
    # PLAIN ENGLISH on that comment: notice RESOLVING is given 2, the same as EMERGING,
    # rather than continuing the climb to 6. That is on purpose. The number means "how bad
    # is it", not "how far along the story are we". Getting better is genuinely less bad --
    # but it is not zero, because it has not finished yet.
    # Over. Back to zero, the same as never having started.
    RiskState.RESOLVED: 0,
}

# The bag of states that count as "trouble is happening right now".
# Note which one is missing: RESOLVED is not here, and neither is NORMAL. Everything in
# between is, including RESOLVING -- because "getting better" still means "not yet safe".
_ELEVATED = frozenset({
    RiskState.EARLY_WARNING, RiskState.EMERGING, RiskState.ACTIVE,
    RiskState.ESCALATING, RiskState.PEAK, RiskState.RESOLVING,
})


# A new kind of error, for when the future leaks into the past.
class LeakageError(RuntimeError):
    """A point-in-time violation. Always fatal -- never downgraded to a warning."""
    # PLAIN ENGLISH: "always fatal" means the program STOPS. It never merely prints a
    # warning and carries on. A warning would scroll past unread, and the research would be
    # published with a hole in it. Better to break loudly now than be wrong quietly forever.


# Put any time into one single agreed form: the world clock, clearly labelled as such.
def utc(ts: datetime | str) -> datetime:
    """Normalise to timezone-aware UTC. Naive input is *assumed* UTC and marked so."""
    # PLAIN ENGLISH: a "naive" time is one written down with no country attached, like
    # "3 o'clock". Three o'clock WHERE? In London or in Mumbai those are different moments.
    # A "timezone-aware" time says which -- and this action turns everything into the one
    # world-wide clock, UTC, so that every time in the whole system can be compared fairly.
    # If we get a naive time, we assume it meant UTC and stamp it as such -- and the word
    # "assumed" in the sentence above is an honest admission that this is a guess.

    # Was it handed to us as text, like "2026-08-28T14:05:09"?
    if isinstance(ts, str):
        # `fromisoformat` reads that international standard spelling and turns it into a
        # real date-and-time object the computer can do sums with.
        ts = datetime.fromisoformat(ts)
    # `.tzinfo` is the timezone label. If it is None, no country was attached: it is naive.
    if ts.tzinfo is None:
        # `.replace(tzinfo=UTC)` sticks a "this is UTC" label on WITHOUT changing the
        # numbers on the clock face. 3 o'clock stays 3 o'clock, and is now declared to be
        # 3 o'clock UTC. This is the assumption being made.
        return ts.replace(tzinfo=UTC)
    # It already had a country attached, so we convert properly. `.astimezone(UTC)` DOES
    # change the numbers: 3pm in Mumbai becomes 09:30 UTC, because it is the same instant
    # written in the world clock's language.
    return ts.astimezone(UTC)


# `frozen=True`: once made, this record can never be altered. A provenance stamp that could
# be edited afterwards would be worthless as evidence.
@dataclass(frozen=True)
# The stamp recording where a fact came from and when it became knowable.
# ("Provenance" is the word museums use for an object's documented history of ownership.)
class Provenance:
    # Who told us. A data supplier, an exchange, a filing.
    source: str
    # What we are legally allowed to do with it.
    licence: str
    # When the thing described actually happened.
    event_time: datetime
    # When THIS SYSTEM could first have acted on this exact value. The most important one.
    knowledge_time: datetime
    # When a publisher first made it public, if we know. May be unknown.
    publication_time: datetime | None = None
    # When we downloaded it, if we know.
    retrieval_time: datetime | None = None
    # Which version of the dataset it came out of. Defaults to an honest "unversioned"
    # rather than to a made-up version number.
    dataset_version: str = "unversioned"
    # A fingerprint of the content, so we can later detect if it was altered.
    content_hash: str | None = None
    # Any remark a human wanted to attach.
    note: str | None = None

    # The tidy-up step Python runs automatically just after one of these is built.
    def __post_init__(self) -> None:
        # Put every time onto the world clock. Normally we would write `self.event_time =
        # ...`, but this record is frozen and refuses ordinary changes. `object.__setattr__`
        # is the special back door for setting a value during construction, before the
        # record is handed out. After this moment it really is sealed.
        object.__setattr__(self, "event_time", utc(self.event_time))
        object.__setattr__(self, "knowledge_time", utc(self.knowledge_time))
        # The last two are optional, so only convert them if they were actually supplied.
        if self.publication_time is not None:
            object.__setattr__(self, "publication_time", utc(self.publication_time))
        if self.retrieval_time is not None:
            object.__setattr__(self, "retrieval_time", utc(self.retrieval_time))
        # THE CENTRAL SAFETY CHECK OF THE WHOLE PROJECT.
        # Could we have known about it BEFORE it happened? Obviously not. If the numbers say
        # otherwise, something is badly wrong with the data, and every conclusion built on
        # top of it would be worthless.
        if self.knowledge_time < self.event_time:
            # So stop dead, and explain it in plain words a human can act on.
            raise LeakageError(
                "knowledge_time %s precedes event_time %s for source %r: the system "
                "cannot know a fact before it happens"
                % (self.knowledge_time, self.event_time, self.source)
            )

    # Turn this stamp into plain labelled boxes, ready to be saved.
    def to_dict(self) -> dict:
        # Convert every slot into a box automatically.
        d = asdict(self)
        # Walk through the four time slots by name.
        for k in ("event_time", "knowledge_time", "publication_time", "retrieval_time"):
            # Only convert the ones that actually hold a time; the optional ones may be None.
            if d[k] is not None:
                # Write the time in the international standard spelling, which is text and so
                # can live in a JSON file. A raw date object cannot be saved directly.
                d[k] = d[k].isoformat()
        return d


# Frozen again: a piece of evidence must not be editable after the fact.
@dataclass(frozen=True)
# One single fact that entered the system, complete with its stamp.
class EvidenceRecord:
    # Which company or traded thing this is about. ("Instrument" is the finance word for
    # anything you can trade: a share, a bond, and so on.)
    instrument_id: str
    # Which of the five families of evidence it belongs to.
    block: EvidenceBlock
    # The actual information. `dict[str, Any]` means labelled boxes holding anything, which
    # is deliberately flexible because a price and a set of accounts have very different
    # shapes.
    payload: dict[str, Any]
    # The stamp saying where it came from and when it became knowable.
    provenance: Provenance
    #: Stable identity of the underlying fact. Two records sharing a ``fact_key`` and an
    #: ``event_time`` are versions of the same fact; the later ``knowledge_time`` is a
    #: restatement of the earlier.
    # PLAIN ENGLISH: this is the name of the THING being measured -- "sales", say. It is how
    # the system recognises that two records are two versions of one fact rather than two
    # separate facts. Same company + same fact_key + same event_time = the same fact told
    # twice, and whichever was learned later is the correction.
    fact_key: str = "default"
    # What the librarian decided we may do with this. May be unknown for now.
    licence_status: str | None = None

    # A shortcut so other code can write `record.event_time` instead of having to know it
    # lives inside the provenance stamp. It just passes the question along.
    @property
    def event_time(self) -> datetime:
        return self.provenance.event_time

    # The same shortcut for the knowledge time.
    @property
    def knowledge_time(self) -> datetime:
        return self.provenance.knowledge_time

    # Work out this record's fingerprint, so identical facts can be recognised and altered
    # ones detected.
    def content_hash(self) -> str:
        # Build a short, strictly-ordered description of the fact, as text.
        blob = json.dumps(
            # Short single-letter labels, purely to keep the text small; the fingerprint
            # does not care what the labels are called, only that they are always the same.
            #   "i" -- which instrument
            #   "m" -- which block (its plain text form)
            #   "k" -- which fact
            #   "e" -- when it happened, in the standard spelling
            #   "p" -- the information itself, put into a stable form (see `_stable` below)
            {"i": self.instrument_id, "m": self.block.value, "k": self.fact_key,
             "e": self.event_time.isoformat(), "p": _stable(self.payload)},
            # Always alphabetical, so the same fact always spells itself the same way and so
            # always produces the same fingerprint.
            sort_keys=True,
        )
        # NOTE what is deliberately absent: knowledge_time is NOT part of the fingerprint.
        # That is the point. The original figure and its later correction are two DIFFERENT
        # facts (different values, so different fingerprints), but a record re-imported
        # twice is recognisably the same thing regardless of when we happened to learn it.
        # Turn the text into raw bytes and fingerprint it.
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # Turn the whole record into labelled boxes, ready to be saved or sent.
    def to_dict(self) -> dict:
        return {
            "instrument_id": self.instrument_id,
            # `.value` gives the plain text form of the menu choice, e.g. "MARKET".
            "block": self.block.value,
            "fact_key": self.fact_key,
            "payload": self.payload,
            # Ask the stamp to convert itself, using its own method from earlier.
            "provenance": self.provenance.to_dict(),
            "licence_status": self.licence_status,
            # Work out the fingerprint fresh and include it, so whoever receives this can
            # check nothing was changed in transit.
            "content_hash": self.content_hash(),
        }


# A private helper: rewrite information into one single predictable form before
# fingerprinting it.
def _stable(obj: Any) -> Any:
    """JSON-stable projection of a payload, for hashing."""
    # PLAIN ENGLISH: a fingerprint is only useful if the SAME information always produces
    # the SAME code. But the same information can be written down in several ways -- labels
    # in a different order, or a number with a few extra wobbly digits on the end. This
    # action forces one single spelling, so identical facts really do match.

    # Labelled boxes: `sorted(obj.items())` puts the labels into alphabetical order, so
    # {"b":2,"a":1} and {"a":1,"b":2} come out identical. Then each value is stabilised too.
    if isinstance(obj, dict):
        return {k: _stable(v) for k, v in sorted(obj.items())}
    # Rows of things: keep the order exactly as it is (order genuinely means something in a
    # list), but stabilise each item inside.
    if isinstance(obj, (list, tuple)):
        return [_stable(v) for v in obj]
    # Times become the standard text spelling, which never varies.
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Decimal numbers get rounded to 12 decimal places. This handles a genuine and annoying
    # fact about computers: they store decimals slightly imperfectly, so the same sum done
    # two different ways can give 0.30000000000000004 and 0.3. Rounding to 12 places is far
    # more precision than any of this data has, and it makes those two agree.
    if isinstance(obj, float):
        return round(obj, 12)
    # Anything else -- text, whole numbers, True/False, None -- is already unambiguous.
    return obj


# The shape of what the system finally says about a company.
@dataclass
class RiskAssessment:
    """The system output contract (spec section 7). Deliberately contains no
    instruction, target price, or allocation -- see ``research/risk/non_advisory.py``."""
    # PLAIN ENGLISH: read that carefully, because it is a promise. This system describes
    # what it observes. It never says "buy this" or "sell that" or "this share is worth
    # 40 pounds". It is a smoke alarm, not a fire chief: it tells you it can smell smoke,
    # and what you do about that is entirely your decision. That is partly honesty (it does
    # not actually know what you should do) and partly law (telling people what to buy is a
    # regulated activity in most countries).

    # Which company this is about.
    instrument_id: str
    # The moment this judgement refers to.
    decision_time: datetime
    # How much integrity risk we see, as a number from 0 to 1. 0 means none at all, 1 means
    # as much as possible. Using a fraction rather than words makes it comparable and sortable.
    integrity_risk: float
    # How unsure we are of that number, again from 0 to 1. Reporting this is essential
    # honesty: "0.8 risk, and we are very unsure" is a completely different message from
    # "0.8 risk, and we are confident", and hiding the difference would mislead.
    uncertainty: float
    # How much of the evidence we hoped for we actually had, from 0 to 1. A confident answer
    # based on a quarter of the data deserves to be read differently from the same answer
    # based on all of it.
    coverage: float
    # Which stage of trouble, from the menu near the top of this file.
    risk_state: RiskState
    # What mood the whole market was in at the time, if known.
    regime: str | None = None
    # How much each family of evidence contributed to the verdict. Starts empty.
    block_evidence: dict[str, float] = field(default_factory=dict)
    # Measures of the emotional tone found in text about this company (in news, filings).
    affective_state: dict[str, float] = field(default_factory=dict)
    # Measures of trouble arriving from connected companies rather than from this one.
    propagation: dict[str, float] = field(default_factory=dict)
    # The explanation of WHY -- eXplainable AI. An answer nobody can question is not
    # evidence, so the reasoning travels with the verdict.
    xai: dict[str, Any] = field(default_factory=dict)
    # The line the system promised not to look past: nothing learned after this moment was
    # allowed to influence the verdict.
    knowledge_cutoff: datetime | None = None

    # The tidy-up step run automatically just after one of these is built.
    def __post_init__(self) -> None:
        # Put the times onto the world clock. This record is not frozen, so ordinary
        # assignment works and no back door is needed.
        self.decision_time = utc(self.decision_time)
        if self.knowledge_cutoff is not None:
            self.knowledge_cutoff = utc(self.knowledge_cutoff)
        # Check the three fractions really are fractions. A "risk" of 4.2 or -1 would be
        # meaningless, and would quietly poison every chart and average built on top of it.
        for name in ("integrity_risk", "uncertainty", "coverage"):
            # Fetch the value by its name.
            v = getattr(self, name)
            # Must sit between 0 and 1. The `1e-9` is a hair's breadth of tolerance
            # (0.000000001), added because computers store decimals slightly imperfectly and
            # a perfectly good 1.0 can arrive as 1.0000000000000002. We want to catch real
            # mistakes, not punish arithmetic dust.
            if not (0.0 - 1e-9 <= float(v) <= 1.0 + 1e-9):
                # Stop, and say which slot was wrong and what it actually held.
                raise ValueError("%s must lie in [0,1], got %r" % (name, v))

    # Turn the assessment into labelled boxes, ready to be saved or sent to the website.
    def to_dict(self) -> dict:
        d = asdict(self)
        # Menu choices and times need converting into plain text by hand, because JSON can
        # only hold simple things.
        d["risk_state"] = self.risk_state.value
        d["decision_time"] = self.decision_time.isoformat()
        if self.knowledge_cutoff is not None:
            d["knowledge_cutoff"] = self.knowledge_cutoff.isoformat()
        return d


# The storehouse holding every piece of evidence, which can answer questions about the past
# honestly.
class BitemporalStore:
    """Append-only bitemporal evidence store.

    Retrieval is always ``as-of``: a query names a ``decision_time`` (how far the world
    has advanced) and a ``knowledge_cutoff`` (what the system is permitted to have
    learned). Records failing either bound are invisible -- not filtered later, invisible.
    """
    # PLAIN ENGLISH:
    # "Bitemporal" means "two times". This store keeps track of both when things HAPPENED
    # and when we LEARNED them, and can rewind either one independently.
    # "Append-only" means you may add, but never change or delete. Like writing in pen in a
    # bound notebook: the history stays honest because it cannot be tidied up afterwards.
    # "As-of" means every question is really the question "as of this moment, what did we
    # know?" -- like asking someone to answer using only last Tuesday's newspaper.
    # And "invisible -- not filtered later, invisible" is the crucial design choice. Facts
    # from the future are not fetched-then-removed; they are never fetched at all. If you
    # fetch them first, one day somebody forgets the removing step and the cheat comes back.

    # The set-up recipe, run when a new store is made.
    def __init__(self) -> None:
        # One empty list to hold the records. Private, so nobody outside can reach in and
        # rearrange history behind the store's back.
        self._records: list[EvidenceRecord] = []

    # A special name Python recognises: it makes `len(store)` work, answering "how many
    # records are in here?".
    def __len__(self) -> int:
        return len(self._records)

    # Another special name: it makes `for record in store:` work, so you can walk through
    # every record. NOTE this walks through EVERYTHING, ignoring the time rules -- which is
    # why real questions must go through `query` below, never through this.
    def __iter__(self) -> Iterator[EvidenceRecord]:
        return iter(self._records)

    # Add one record to the end. The only way anything ever gets in.
    def append(self, record: EvidenceRecord) -> None:
        self._records.append(record)

    # Add many records, by adding each one in turn.
    def extend(self, records: Iterable[EvidenceRecord]) -> None:
        for r in records:
            self.append(r)

    # THE MOST IMPORTANT ACTION IN THE FILE: ask the store what was known at a given moment.
    def query(
        self,
        # Which company to ask about. `None` means "all of them".
        instrument_id: str | None,
        # How far the world has moved on: nothing that happened after this counts.
        decision_time: datetime,
        # What we are allowed to have learned by now. If not given, it matches decision_time.
        knowledge_cutoff: datetime | None = None,
        # Which families of evidence to include. `None` means all of them.
        blocks: Sequence[EvidenceBlock] | None = None,
        # How far back to look. `None` means all the way back to the beginning.
        lookback_days: float | None = None,
    ) -> list[EvidenceRecord]:
        """Return the as-of view. ``knowledge_cutoff`` defaults to ``decision_time``.

        When several versions of the same fact are visible, only the one with the
        greatest ``knowledge_time`` at or before the cutoff survives -- restatements
        published after the cutoff cannot influence the answer.
        """
        # PLAIN ENGLISH on that second paragraph: this is the restatement rule from the top
        # of the file, in action. If a fact has been told three times, we take the most
        # recent telling THAT WE WERE ALLOWED TO HAVE HEARD. A correction published after
        # the cutoff simply does not exist as far as this answer is concerned.

        # Put both times onto the world clock so they can be compared fairly.
        decision_time = utc(decision_time)
        # If no learning limit was given, use the decision time itself -- meaning "you may
        # know everything that was knowable by then, and not one second more".
        cutoff = utc(knowledge_cutoff) if knowledge_cutoff is not None else decision_time
        # A safety check against a nonsensical request: you cannot be allowed to know things
        # from after the moment you are deciding. That is time travel, and it is exactly the
        # cheat this file exists to prevent.
        if cutoff > decision_time:
            raise LeakageError(
                "knowledge_cutoff %s is after decision_time %s: a decision may not use "
                "knowledge from its own future" % (cutoff, decision_time)
            )
        # Turn the requested families into a bag for fast checking. `if blocks` handles both
        # "none given" and "an empty list given" as "no filter at all".
        want = set(blocks) if blocks else None
        # The earliest moment we will accept. `None` for now means no limit.
        floor = None
        if lookback_days is not None:
            # `.timestamp()` turns a date into a plain count of seconds, which makes the
            # arithmetic easy. `86400` is the number of seconds in a day (60 x 60 x 24), so
            # this works out the moment `lookback_days` before the decision.
            floor = decision_time.timestamp() - lookback_days * 86400.0

        # A place to keep the best version found so far of each distinct fact.
        # The label is a group of several values at once, explained where it is built below.
        best: dict[tuple, EvidenceRecord] = {}
        # Look at every record in the store, one at a time.
        for r in self._records:
            # Wrong company? `continue` means "skip this one, go straight to the next".
            if instrument_id is not None and r.instrument_id != instrument_id:
                continue
            # Not one of the requested families? Skip.
            if want is not None and r.block not in want:
                continue
            # Did it happen after the moment we are asking about? Then it is in the future.
            # Skip it -- this is the first of the two time gates.
            if r.event_time > decision_time:
                continue
            # Did we learn it after the cutoff? Then we were not allowed to know it yet.
            # Skip it -- the second time gate, and the one that catches restatements.
            if r.knowledge_time > cutoff:
                continue
            # Too old to be within the lookback window? Skip.
            if floor is not None and r.event_time.timestamp() < floor:
                continue
            # It survived every gate. Build the label identifying WHICH FACT this is: the
            # company, the family, the name of the measurement, and when it happened. Two
            # records with an identical label are two tellings of one single fact.
            key = (r.instrument_id, r.block, r.fact_key, r.event_time)
            # Have we already seen a version of this fact? `.get` asks politely, handing back
            # None rather than complaining if we have not.
            prev = best.get(key)
            # Keep this one if it is the first we have seen, or if we learned it more
            # recently than the one we are already holding. So the newest PERMITTED telling
            # wins -- and any telling that came after the cutoff was already thrown out above
            # and never gets this far.
            if prev is None or r.knowledge_time > prev.knowledge_time:
                best[key] = r
        # Hand back the surviving records, sorted into a fixed, predictable order: oldest
        # event first, and companies alphabetically within the same moment. `key=lambda r:
        # (...)` is a tiny inline instruction saying "sort by these things, in this order".
        # A predictable order matters because it makes two runs of the program directly
        # comparable, instead of differing merely because things came out shuffled.
        return sorted(best.values(), key=lambda r: (r.event_time, r.instrument_id))


# The official front door. Every part of the system asks its questions through here.
def get_evidence(
    # Which storehouse to ask.
    store: BitemporalStore,
    # Which company, or None for all.
    instrument_id: str | None,
    # The moment being asked about.
    decision_time: datetime,
    # What we are allowed to have learned.
    knowledge_cutoff: datetime | None = None,
    # `**kwargs` means "any other named settings you like" -- they get passed straight
    # through to `query`, so this front door does not have to list every option itself.
    **kwargs: Any,
) -> list[EvidenceRecord]:
    """The spec-mandated entry point (section 26). Thin by design: every caller in the
    system goes through this function so that the leakage tests have one place to attack.
    """
    # PLAIN ENGLISH: "thin by design" means it deliberately does hardly anything. The point
    # is not what it does but that it is the ONLY door. A castle with one gate can be
    # guarded; a castle with forty doors cannot. Because every single request comes through
    # here, the tests that hunt for cheating have exactly one place to stand and watch.

    # Do the real work by asking the storehouse.
    records = store.query(instrument_id, decision_time, knowledge_cutoff, **kwargs)
    # Work out the cutoff again, here, independently.
    cutoff = utc(knowledge_cutoff) if knowledge_cutoff is not None else utc(decision_time)
    for r in records:  # belt and braces: the invariant is asserted, not assumed
        # PLAIN ENGLISH: "belt and braces" is an old expression for wearing two things to
        # hold your trousers up, in case one fails. The store has already promised nothing
        # from the future gets through. Here we CHECK that promise rather than trusting it.
        # This loop should never, ever find anything. If it does, there is a bug in the
        # store, and finding out by crashing beats finding out by publishing a false result.
        if r.knowledge_time > cutoff:
            raise LeakageError(
                # `[:12]` keeps just the first twelve characters of the fingerprint -- plenty
                # to identify the record in an error message, without printing all 64.
                "record %s leaked: knowledge_time %s > cutoff %s"
                % (r.content_hash()[:12], r.knowledge_time, cutoff)
            )
    # Everything checked out. Hand the evidence back.
    return records
