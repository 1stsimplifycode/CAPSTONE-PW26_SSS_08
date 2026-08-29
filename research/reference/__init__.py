"""Authoritative exchange reference data, and an honest account of what is missing.

The Week 1 criteria ask for twelve finance inputs. This package delivers the ones that
can be obtained from the exchange itself and *refuses to substitute anything* for the
ones that cannot. That refusal is the load-bearing part: a fabricated circuit band or an
invented review cycle is worse than an absent one, because an absent one is visible.

Every item in :data:`REQUIRED_INPUTS` resolves to exactly one of three states:

``OBTAINED``     an artifact exists on disk, with source, retrieval instant, licence,
                 checksum and temporal coverage recorded in the manifest
``PARTIAL``      an artifact exists but does not cover what the criterion asks for; the
                 shortfall is named in ``shortfall``
``UNAVAILABLE``  no authoritative artifact. ``attempts`` records what was tried and what
                 the exchange answered, so the gap is auditable rather than asserted

Nothing in this package infers a market rule. A value that NSE did not publish is not
here, and :func:`research.reference.registry.status_report` says so by name.

Provenance grading is separate from availability and equally explicit. A fact read out of
an exchange file is ``EXCHANGE_PUBLISHED``. A quantity computed from exchange files by
this repository -- the corporate-action adjustment factor, for instance, which is derived
from NSE's own restatement of ``prev_close`` -- is ``DERIVED_FROM_EXCHANGE_DATA`` and
carries the derivation in its ``note``. A number this project chose is
``PROJECT_ASSUMPTION`` and may never be presented as an exchange rule.

PLAIN ENGLISH -- what this whole file is about:

THE FILE THAT KEEPS TRACK OF WHAT WE DO NOT KNOW.

The project needs twelve pieces of official information from the stock exchange -- things
like "what are the daily price limits?" and "when does settlement happen?".

Some we could get. Some we could not.

For the ones we could not get, there is a very tempting shortcut: put in a sensible-looking
number. Circuit limits are usually 10% or 20%, so just write 20% and move on. Everything
runs, every table fills in, and the project looks finished.

The sentence in the docstring explains why that is forbidden, and it is worth memorising:

    "a fabricated circuit band is worse than an absent one, because an absent one is
     visible."

A made-up number does not announce itself. It sits in the table looking exactly like the
real ones. Every conclusion built on it inherits the invention, and nobody can tell -- not
a reviewer, not a future reader, not even the person who wrote it, six months later.

So each of the twelve gets one of three honest labels: got it, got part of it, or did not
get it. And for the ones we did not get, we record WHAT WE TRIED and WHAT HAPPENED. The
gap becomes a documented finding rather than a silence.

AND THE SECOND, SEPARATE IDEA -- WHERE DOES A NUMBER'S AUTHORITY COME FROM?

Having a number is one question. Being able to say why anyone should believe it is
another, and they are kept deliberately apart. Six different grades of authority are
defined below, from "the exchange published this exact number" all the way down to "we
chose this ourselves". A project that grades its own inputs this carefully is one where a
reader can check any claim back to its source.

There is also a subtle third distinction hiding in the ReferenceSource record below: a
piece of information can be genuinely OBTAINED and still be useless. A list of today's
restricted companies is a real, official file -- and it tells you nothing whatever about
2015. That is why coverage is tracked separately from availability.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For making fingerprints of files.
import hashlib
# For reading and writing JSON.
import json
# Record-building tools.
from dataclasses import asdict, dataclass, field
# The world clock and the tool for reading the time.
from datetime import UTC, datetime
# For fixed menus of allowed choices.
from enum import StrEnum
# A safe way to talk about places on the disk.
from pathlib import Path

# A label for this version.
REFERENCE_VERSION = "reference-v1"


# Did we get it?
class Availability(StrEnum):
    # Yes, complete, with all its paperwork.
    OBTAINED = "OBTAINED"
    # Partly -- and the shortfall is named.
    PARTIAL = "PARTIAL"
    # No. And what we tried is recorded.
    UNAVAILABLE = "UNAVAILABLE"


# Why should anyone believe this number?
class Basis(StrEnum):
    """Where a value's authority comes from. Never inferred, always declared."""
    # PLAIN ENGLISH: "never inferred, always declared" means the code never works out for
    # itself how trustworthy something is. A human states it explicitly, once, and it then
    # travels with the value forever.

    #: Read verbatim out of a file the exchange published.
    # The gold standard. The exchange said this, in these words.
    EXCHANGE_PUBLISHED = "EXCHANGE_PUBLISHED"
    #: Obtained from a commercial redistributor of exchange prices rather than from the
    #: exchange. Real market data, but one hop removed: the redistributor's own
    #: consolidation and adjustment rules sit between the tape and the number, and it is
    #: not an NSE publication. Never conflated with EXCHANGE_PUBLISHED.
    # PLAIN ENGLISH: a company that sells on market data. The numbers are real, but they
    # passed through somebody else's hands, and that company applied its own cleaning and
    # adjustment rules on the way. Usually sensible rules -- but they are that company's
    # rules, not the exchange's, and the difference must never be blurred.
    THIRD_PARTY_REDISTRIBUTOR = "THIRD_PARTY_REDISTRIBUTOR"
    #: Computed by this repository from exchange files, by a documented derivation.
    # We worked it out ourselves from official numbers. The inputs are authoritative; the
    # arithmetic is ours, and the arithmetic is written down.
    DERIVED_FROM_EXCHANGE_DATA = "DERIVED_FROM_EXCHANGE_DATA"
    #: Inferred by a published statistical rule that is known to be imperfect -- trade
    #: signing by the tick test, for instance. Real method, real error rate, and *not* a
    #: statement by the exchange about what actually happened.
    # PLAIN ENGLISH: a good example. We often need to know whether a trade was a buy or a
    # sell, and the exchange does not say. There is a well-known method (the "tick test")
    # that guesses from whether the price ticked up or down. It is right most of the time
    # and wrong some of the time. So this is a real, respectable method -- and it is a GUESS,
    # not a fact, and it is labelled as such.
    INFERRED_BY_PUBLISHED_RULE = "INFERRED_BY_PUBLISHED_RULE"
    #: Observed behaviour of the data, not a statement by the exchange.
    # "The data behaves as though trading stops at 15:30." True, useful, and not the same
    # thing as the exchange having stated it as a rule.
    OBSERVED_IN_DATA = "OBSERVED_IN_DATA"
    #: A choice this project made. Never an exchange rule, never displayed as one.
    # The weakest grade, and the one that most needs labelling. Our own decision -- perfectly
    # legitimate to make, and never to be dressed up as somebody else's authority.
    PROJECT_ASSUMPTION = "PROJECT_ASSUMPTION"


#: The twelve inputs the Week 1 criteria name, in the order C7 lists them.
# PLAIN ENGLISH: the shopping list. Kept in a fixed order so the status report reads the
# same way every time and can be compared between runs.
REQUIRED_INPUTS = (
    # Which companies are in the index, and how often that gets reviewed.
    "index_composition",
    "index_review_cycle",
    # Share splits, bonuses and dividends, and the rules for when they take effect.
    "corporate_actions",
    "ex_date_conventions",
    # Companies that left the market, or were temporarily halted.
    "delisting",
    "suspension",
    # Extra surveillance measures the exchange applies to risky shares.
    "asm_gsm",
    # The daily limits on how far a price may move.
    "circuit_bands",
    # How long after a trade the shares and money actually change hands.
    "settlement_cycle",
    # When the market is open, plus its special sessions.
    "market_timings",
    "auction_windows",
    "block_deal_windows",
)


# Work out a file's fingerprint.
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    # `"rb"` reads the raw bytes exactly as they are.
    with open(path, "rb") as fh:
        # `iter(action, sentinel)` keeps calling the action until it returns the sentinel --
        # here, until reading returns empty bytes, meaning end of file. Reading a megabyte at
        # a time means a file larger than the computer's memory can still be fingerprinted.
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Frozen: a record of what happened must not be editable afterwards.
@dataclass(frozen=True)
class Attempt:
    """One acquisition attempt, successful or not. The failures are the point."""
    # PLAIN ENGLISH: "the failures are the point" is the heart of this whole file. Anybody
    # records their successes. Recording the failures -- which address was tried, on what
    # date, and exactly what the exchange answered -- is what turns "we do not have this"
    # from an excuse into a checkable finding. A reader can go and try the same address.

    # Where we tried.
    url: str
    # What came back. `int | str` because it might be a numeric code like 404, or a
    # description like "connection refused".
    http_status: int | str
    # When we tried. Essential, because a website that refused us last year may well work
    # now, and without a date nobody knows whether to retry.
    attempted_at: str
    # Anything else worth recording.
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
# Everything known about one of the twelve inputs.
class ReferenceSource:
    """One reference dataset and everything needed to judge it.

    ``temporal_coverage`` is deliberately separate from availability. A current-snapshot
    ASM list is genuinely obtained and genuinely useless for a 2015 point-in-time query,
    and only the coverage field can say that.
    """
    # PLAIN ENGLISH: the key insight, worth dwelling on. You can have a file. It can be
    # completely genuine and properly obtained. And it can still be no use at all, because
    # it describes today and your question is about 2015.
    # If "we have it" and "it covers what we need" were the same field, that file would be
    # marked OBTAINED and everyone would assume the question was answered. Keeping them
    # separate is what makes the real limitation visible.

    # Which of the twelve this is.
    input_id: str
    # A readable name for it.
    title: str
    # Got it, partly, or not.
    availability: Availability
    # How authoritative it is, from the six grades above.
    basis: Basis | None = None
    # Who provided it, and where from.
    provider: str = ""
    source_url: str = ""
    source_identifier: str = ""
    # What we may legally do with it.
    licence: str = ""
    # When we fetched it.
    retrieved_at: str = ""
    # Where it is stored, and its fingerprint and size -- so anyone can confirm they are
    # looking at the identical file.
    artifact_path: str = ""
    sha256: str = ""
    bytes: int = 0
    version: str = ""
    # WHICH PERIOD IT ACTUALLY COVERS. The field this whole class's docstring is about.
    temporal_coverage: str = ""
    # Whether it is a proper historical record (True) or only a snapshot of today (False).
    # A snapshot cannot answer a question about the past, however genuine it is.
    point_in_time: bool = False
    # If it is PARTIAL, exactly what is missing -- named, not left vague.
    shortfall: str = ""
    # Every attempt made to get it, including the failures.
    attempts: list[Attempt] = field(default_factory=list)
    note: str = ""

    # Turn it into labelled boxes for saving.
    def to_dict(self) -> dict:
        d = asdict(self)
        # Menu choices become plain text, so JSON can hold them.
        d["availability"] = str(self.availability)
        # `if self.basis else None` -- an unstated basis stays honestly unknown rather than
        # becoming the text "None".
        d["basis"] = str(self.basis) if self.basis else None
        # The attempts likewise. The `isinstance` check makes this tolerant of already-
        # converted entries, so converting twice cannot break.
        d["attempts"] = [a.to_dict() if isinstance(a, Attempt) else a
                         for a in self.attempts]
        return d

    # Rebuild one from a saved file.
    @classmethod
    def from_dict(cls, d: dict) -> ReferenceSource:
        # Copy first, so we never modify the caller's dictionary behind their back.
        d = dict(d)
        # Turn the plain text back into proper menu choices. Doing this matters: it means a
        # corrupted file with an invalid status fails loudly here, rather than travelling on
        # as an unrecognised string that quietly matches nothing later.
        d["availability"] = Availability(d["availability"])
        d["basis"] = Basis(d["basis"]) if d.get("basis") else None
        d["attempts"] = [Attempt(**a) for a in d.get("attempts", [])]
        return cls(**d)

    @property
    # Does this actually satisfy the requirement?
    def satisfies_criterion(self) -> bool:
        # Note the strictness: ONLY fully obtained counts. PARTIAL does not. That is
        # deliberate -- letting "partly" count as "yes" is precisely how a gap disappears
        # from a summary table while remaining a gap in reality.
        return self.availability is Availability.OBTAINED


#: NSE publishes these reports for public download. Public accessibility is not
#: permission to redistribute, which is why the acquired files are gitignored and only
#: their checksums are committed.
# PLAIN ENGLISH: an important legal distinction that is very widely got wrong. Being able to
# download something freely does NOT mean you may republish it. A library lets anyone read a
# book; that is not permission to photocopy it and hand the copies out.
# So the actual files are kept locally and deliberately excluded from the shared code
# repository. Only their FINGERPRINTS are shared -- which proves exactly which file was used,
# without redistributing a single byte of it. That is a genuinely elegant solution: full
# reproducibility, no copyright breach.
NSE_LICENCE = (
    "NSE publishes these reports for public download under its website terms of use. "
    "Public accessibility is not permission to redistribute: acquired files are held "
    "locally, excluded from version control, and only their checksums are committed. "
    "Index names, levels and constituent lists are the property of NSE Indices Limited "
    "and are used here for non-commercial research."
)


# Where the packing list lives.
def manifest_path(root: Path | None = None) -> Path:
    # Fetched inside the action to avoid two files trying to load each other at startup.
    from research.core import paths
    return (root or paths.REFERENCE) / "reference_manifest.json"


# Save the packing list.
def write_manifest(sources: list[ReferenceSource], root: Path | None = None) -> Path:
    from research.core import paths
    root = root or paths.REFERENCE
    root.mkdir(parents=True, exist_ok=True)
    p = manifest_path(root)
    payload = {
        "reference_version": REFERENCE_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
        # The full shopping list is written out too, not just what we found. That is what
        # lets a reader see the SHAPE OF THE HOLE -- twelve wanted, seven obtained -- rather
        # than only the seven successes, which on their own would look complete.
        "required_inputs": list(REQUIRED_INPUTS),
        "sources": [s.to_dict() for s in sources],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


# Read the packing list back.
def read_manifest(root: Path | None = None) -> list[ReferenceSource]:
    p = manifest_path(root)
    # No manifest yet: hand back an empty list rather than crashing. An empty list correctly
    # means "nothing obtained", which is the honest state before anything has been fetched.
    if not p.exists():
        return []
    payload = json.loads(p.read_text(encoding="utf-8"))
    # `.get("sources", [])` copes with a manifest that has no sources section at all.
    return [ReferenceSource.from_dict(s) for s in payload.get("sources", [])]
