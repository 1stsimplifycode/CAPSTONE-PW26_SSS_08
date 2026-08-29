"""Licence gates for data sources (spec sections 15, 51, 52, 60, 61).

The single rule this module exists to enforce: material whose redistribution rights are
not established must never be copied into a publication artifact.

PLAIN ENGLISH -- what this whole file is about:

This file is the project's LIBRARIAN, and its job is to stop us stealing things.

Suppose you are making a school project. You find a brilliant photograph on the
internet. Are you allowed to glue it into your project? It depends:
  * Some pictures are free for anyone to use.        -> glue it in, fine.
  * Some belong to a newspaper who owns them.        -> do NOT glue it in.
  * Some you may show in a special frame, but not copy. -> link to it only.
  * And for some, you simply do not know.            -> and "do not know" means NO.

That last one is the important one. This file's rule is: if we are not certain we are
allowed to copy something, we treat it as NOT ALLOWED. That is called being
"conservative", and it means the worst thing that can happen is we leave out a picture
we could have used -- rather than getting the whole project into legal trouble.

Two different questions get asked, and they are deliberately kept apart:
  1. "May we bring this ONTO our own computer to study it?"   (called: ingest)
  2. "May we COPY it into the finished paper we hand out?"    (called: redistribute)
Question 2 is the stricter one. You may be allowed to read a book in a library without
being allowed to photocopy it and hand the copies out.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For writing information out as JSON text.
import json
# `asdict` turns a record into labelled boxes; `dataclass` marks a class as a tidy record;
# `field` gives a slot a cleverer default value than a fixed one.
from dataclasses import asdict, dataclass, field
# `StrEnum` builds a fixed menu of allowed choices, where each choice is also a piece of
# text. A menu is safer than loose text: you cannot accidentally type "OPNE_LICENSE" and
# have it quietly accepted, because it is not on the menu.
from enum import StrEnum
# A safe, cross-platform way to talk about places on the disk.
from pathlib import Path


# The complete menu of answers to "what are we allowed to do with this?".
class LicenseStatus(StrEnum):
    # Somebody officially said "anyone may use this", e.g. a Creative Commons licence.
    OPEN_LICENSE = "OPEN_LICENSE"
    # So old, or so freely given, that nobody owns it any more. Free for all.
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    # The user of this software supplied it themselves, so it is their business, not ours.
    USER_PROVIDED = "USER_PROVIDED"
    # Somebody with the right to say so gave us written permission.
    AUTHORIZED = "AUTHORIZED"
    # We may display it in a special frame on a page (like a YouTube player), but we may
    # not take our own copy. The video stays on their computer and is merely shown.
    EMBED_ONLY = "EMBED_ONLY"
    # We may only point at it: give its web address and say what it is. No copying.
    REFERENCE_ONLY = "REFERENCE_ONLY"
    # We know for certain it is not ours to use.
    RESTRICTED = "RESTRICTED"
    # We have no idea. Treated exactly as strictly as "not allowed".
    UNKNOWN = "UNKNOWN"


#: Statuses whose material may be ingested (bytes stored, features computed locally).
# PLAIN ENGLISH: the four answers that mean "yes, we may bring this onto our computer and
# study it". A `frozenset` is a bag of items that can never be changed after it is made --
# which is exactly right for a rule, because a rule that any part of the program could
# quietly edit would be no rule at all.
INGESTIBLE = frozenset({
    LicenseStatus.OPEN_LICENSE,
    LicenseStatus.PUBLIC_DOMAIN,
    LicenseStatus.USER_PROVIDED,
    LicenseStatus.AUTHORIZED,
})

#: Statuses whose material may be redistributed inside a paper package. Kept as a
#: separate name from INGESTIBLE so the two policies can diverge later without
#: silently widening redistribution rights.
# PLAIN ENGLISH: right now this holds exactly the same four answers as the list above.
# So why write it out again under a second name instead of just reusing the first?
# Because they are two DIFFERENT questions that happen to have the same answer today. If
# somebody later decides "we may study this kind of thing, but we may not hand out copies
# of it", they can change this one list on its own. Had we reused a single list, that edit
# would silently have loosened BOTH rules at once, including the stricter one -- exactly
# the kind of accident this whole file exists to prevent.
REDISTRIBUTABLE = frozenset(INGESTIBLE)

#: Statuses that may only ever be referenced by URL and metadata.
# PLAIN ENGLISH: the two answers meaning "you may point at it, but never take a copy".
REFERENCE_ONLY_STATUSES = frozenset({
    LicenseStatus.EMBED_ONLY,
    LicenseStatus.REFERENCE_ONLY,
})


# Define a new kind of error. `RuntimeError` in the brackets means "this is a sort of
# runtime error", so it inherits everything an ordinary error can do; we are just giving
# this particular problem its own clear name.
class LicenseViolation(RuntimeError):
    """Raised instead of silently degrading. A licence breach is a hard failure."""
    # PLAIN ENGLISH: "raised instead of silently degrading" means that when this rule is
    # broken, the program STOPS with a loud complaint. It does not shrug, skip the item and
    # carry on quietly. That is deliberate: a copyright breach that nobody notices is far
    # more dangerous than a build that refuses to finish, because the broken build gets
    # fixed and the quiet breach gets published.


# `frozen=True` means that once one of these records has been made, none of its slots can
# ever be changed. A licence decision must not be quietly rewritten after the fact.
@dataclass(frozen=True)
# One record describing what we are allowed to do with one particular piece of material.
class MediaLicense:
    # The verdict, chosen from the menu above.
    status: LicenseStatus
    # The web address the material came from.
    source_url: str
    # Who published it, if we know. `| None = None` means "unknown is allowed, and unknown
    # is what you get if nobody says".
    publisher: str | None = None
    # The name of the licence, e.g. "CC BY 4.0", if we know it.
    licence_name: str | None = None
    # The web address of the licence text itself, so a reader can go and check it.
    licence_url: str | None = None
    # HOW we know. This is the proof: "the page carries a CC BY badge", or "email
    # permission from the publisher dated 3 March". Without proof it is only an opinion.
    evidence: str | None = None
    # Who made this decision. Recorded so a human can tell an automatic guess apart from a
    # judgement a person actually made.
    asserted_by: str = "MediaLicenseChecker"

    # Answer question 1: may we bring this onto our computer to study it?
    def may_ingest(self) -> bool:
        # `in` asks "is my status one of the ones in that bag?" and gives back True or False.
        return self.status in INGESTIBLE

    # Answer question 2: may we copy this into the finished paper?
    def may_redistribute(self) -> bool:
        return self.status in REDISTRIBUTABLE

    # Turn this record into plain labelled boxes, ready for saving as JSON.
    def to_dict(self) -> dict:
        # Convert every slot into a labelled box automatically.
        d = asdict(self)
        # Replace the status with its plain text form. Without this, the saved file would
        # contain the menu item itself rather than the simple word "OPEN_LICENSE", and
        # other programs reading the file would not know what to make of it.
        d["status"] = self.status.value
        return d


# The thing that actually looks at a web address and decides what we may do with it.
class MediaLicenseChecker:
    """Classifies a source reference. Defaults to UNKNOWN, never to permissive.

    The domain rules are conservative and deliberately dumb: a checker that guesses
    generously is worse than no checker. Anything not explicitly known is UNKNOWN, and
    An UNKNOWN source is excluded from every redistributable artifact.
    """
    # PLAIN ENGLISH on "deliberately dumb": this checker is not clever, and that is on
    # purpose. A clever checker that sometimes decides "oh, that one is probably fine"
    # would be worse than useless, because people would trust it and it would occasionally
    # be wrong in the dangerous direction. This one only recognises a short list of sites
    # it is sure about, and answers "I do not know" for absolutely everything else.

    # Sites where you may show a video in their player, but may not take your own copy.
    EMBED_ONLY_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")
    # Sites that mostly hold freely usable material.
    OPEN_HOSTS = ("commons.wikimedia.org", "archive.org", "zenodo.org")
    # News organisations. They own their material and reserve all rights over it.
    RESTRICTED_HOSTS = ("cnbc.com", "bloomberg.com", "reuters.com", "wsj.com", "ft.com")

    # The main action: look at one address and hand back a verdict record.
    def check(
        self,
        # Which address to judge.
        source_url: str,
        # Everything after this bare `*` must be passed BY NAME, not just by position. So a
        # caller has to write `evidence="..."` rather than dropping a value in the right
        # slot and hoping. With this many similar-looking optional details, that stops a
        # publisher's name silently ending up in the evidence slot.
        *,
        # A verdict a human is asserting themselves, overriding the automatic guess.
        declared: LicenseStatus | None = None,
        publisher: str | None = None,
        licence_name: str | None = None,
        licence_url: str | None = None,
        # The proof behind a declared verdict.
        evidence: str | None = None,
    ) -> MediaLicense:
        # Did a human supply their own verdict?
        if declared is not None:
            # An explicit declaration (user-supplied file, signed permission, verified
            # open licence) wins, but must carry evidence to be ingestible.
            # PLAIN ENGLISH: a person is allowed to overrule the automatic guess, because a
            # person can read an actual licence page and a list of website names cannot.
            # But if they are claiming a permissive verdict, they must say HOW they know.
            # Otherwise "declared" would just be a magic word for switching the safety off.
            if declared in INGESTIBLE and not evidence:
                # `raise` means "stop everything and report this problem". The program does
                # not carry on past this point.
                raise LicenseViolation(
                    # `%s` and `%r` are gaps filled in from the pair after the `%`. `%s`
                    # writes a value plainly; `%r` writes it with quote marks around it,
                    # which makes it obvious where an address starts and ends.
                    "declared=%s for %r requires `evidence` describing how the right "
                    "was established" % (declared.value, source_url)
                )
            # The declaration was properly evidenced, so accept it and build the record.
            return MediaLicense(declared, source_url, publisher, licence_name,
                                licence_url, evidence)

        # No human verdict, so fall back to judging by which website it came from.
        # Pull the site name out of the address (explained in the helper further down).
        host = host_of(source_url)
        # `any(h in host for h in self.RESTRICTED_HOSTS)` reads as: "go through the list of
        # restricted sites, and is even one of them found inside this address?"
        # It uses "found inside" rather than "exactly equal" so that news.bloomberg.com and
        # www.bloomberg.com are both caught, not only the bare name.
        if any(h in host for h in self.RESTRICTED_HOSTS):
            # A newspaper. We may cite it, never copy it.
            status = LicenseStatus.REFERENCE_ONLY
            # `why` records the reasoning, so a human reading the receipt later can see not
            # just the verdict but the argument behind it.
            why = "host %s is all-rights-reserved by default" % host
        # `elif` means "else if": only checked when the test above was false.
        elif any(h in host for h in self.EMBED_ONLY_HOSTS):
            # A video site. Show it in their player; do not take a copy.
            status = LicenseStatus.EMBED_ONLY
            why = "host %s permits embedding, not redistribution" % host
        elif any(h in host for h in self.OPEN_HOSTS):
            # Note carefully: even for the free-material sites, the verdict is still only
            # REFERENCE_ONLY. That looks over-strict, and the reason is in the message: an
            # open site is full of individual items, and each item has its own licence.
            # Most are free; some are not. Knowing the site is not knowing the item. To go
            # further, a human must look at that one item and declare it with evidence.
            status = LicenseStatus.REFERENCE_ONLY
            why = ("host %s hosts open material but the per-item licence was not "
                   "verified; upgrade requires declared= plus evidence" % host)
        else:
            # Not on any list we recognise. The honest answer is "I do not know", and this
            # file treats "I do not know" exactly as strictly as "no".
            status = LicenseStatus.UNKNOWN
            why = "host %s not in any known-licence list" % host
        # Build and hand back the verdict record.
        # `evidence or why` means: use the evidence if any was supplied, and otherwise fall
        # back to our own reasoning -- so the record never comes back with an empty
        # explanation, and there is always something for a human to read.
        return MediaLicense(status, source_url, publisher, licence_name,
                            licence_url, evidence or why)

    # `@staticmethod` means this action belongs to the class for tidiness, but does not need
    # to know about any particular checker. It is a plain tool kept in a sensible drawer.
    @staticmethod
    # The final gate: stop the program dead unless this material may really be handed out.
    #   `lic`     the verdict record to check.
    #   `context` where we are, in words, so the error message can say what was going on.
    def assert_redistributable(lic: MediaLicense, context: str) -> None:
        # If it may NOT be redistributed...
        if not lic.may_redistribute():
            # ...stop everything, and explain exactly why, and what is still permitted.
            # Note the message says what you MAY do ("referenced") as well as what you may
            # not. A good error message tells you the way out, not just the wall.
            raise LicenseViolation(
                "%s: source %r has status %s; it may be referenced but not copied into "
                "a redistributable artifact" % (context, lic.source_url, lic.status.value)
            )
        # If it may be redistributed, this action simply finishes quietly and the program
        # carries on. Silence means permission granted.


# Pull the website name out of a full web address.
def host_of(url: str) -> str:
    # Fetch the address-splitting tool here, inside the action, rather than at the top of
    # the file, because it is only needed occasionally and this keeps startup fast.
    from urllib.parse import urlparse
    # Be ready for the address to be nonsense.
    try:
        # `urlparse` breaks an address into its pieces. `.netloc` ("network location") is
        # the site-name piece: for https://www.bbc.co.uk/news/story it is "www.bbc.co.uk".
        # `or ""` means "if that piece came back empty, use an empty piece of text", so we
        # always hand back text and never None.
        # `.lower()` makes it all lower case, so BBC.CO.UK and bbc.co.uk are treated as the
        # same site -- important, because our lists above are written in lower case.
        return (urlparse(url).netloc or "").lower()
    except Exception:
        # Complete rubbish was passed in. Hand back an empty name, which matches none of
        # the known lists, so the verdict lands on UNKNOWN -- the strictest outcome. Failing
        # towards safety like this is the whole spirit of the file.
        return ""


# A record describing the licence of one whole dataset (as opposed to one picture).
@dataclass
class DatasetLicence:
    # What the dataset is called.
    name: str
    # Where it came from.
    source: str
    # Which licence it is published under.
    licence: str
    # When we downloaded it. Important because a website's terms can change afterwards, so
    # "what was allowed" only makes sense alongside "at what date".
    date_accessed: str
    # What it covers: which companies, which dates, which markets.
    coverage: str
    # What we are specifically forbidden from doing with it.
    restrictions: str
    # How to credit it properly in the paper.
    citation: str
    # Which version, or the fingerprint of the exact copy we used, so a reader can confirm
    # they are looking at the very same data and not a later edition.
    version_or_hash: str


# A record describing the licence of one prediction model.
@dataclass
class ModelLicence:
    # What the model is called.
    name: str
    # Which version of it.
    version: str
    # Where we got it.
    source: str
    # Which licence it carries.
    licence: str
    # Whether its "weights" are available. Weights are the millions of numbers a model
    # learned during training -- effectively the model's memory. Without them you have the
    # design but not the trained thing itself, so you cannot reproduce its answers.
    weights_available: bool
    # Whether we are allowed to use it for research.
    research_use: bool
    # What the rules are about using it to make money. Text rather than a simple yes/no,
    # because the real answer is usually "yes, but..." with conditions attached.
    commercial_use: str
    # Known weaknesses: what it is bad at, and where it should not be trusted.
    limitations: str


# The complete book of licences: every dataset and every model, in one place.
@dataclass
class LicenceRegistry:
    # A list of dataset licences, starting empty. `default_factory=list` makes a brand new
    # empty list for each registry, rather than one shared list for all of them.
    datasets: list[DatasetLicence] = field(default_factory=list)
    # A list of model licences, likewise starting empty.
    models: list[ModelLicence] = field(default_factory=list)

    # Save the whole book to disk as a JSON file.
    def write(self, path: Path) -> Path:
        # Make sure the folder exists, building the whole staircase if necessary.
        path.parent.mkdir(parents=True, exist_ok=True)
        # Build the information to save, as labelled boxes.
        payload = {
            # `[asdict(d) for d in self.datasets]` reads as: "go through every dataset
            # licence, turn each one into labelled boxes, and collect the results into a
            # list". The same pattern is used for the models on the next line.
            "datasets": [asdict(d) for d in self.datasets],
            "models": [asdict(m) for m in self.models],
        }
        # Write it out, indented over several lines so a human can read it, in the utf-8
        # alphabet so names from any language survive.
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Hand back where it was saved.
        return path
