"""Canonical filesystem locations. Nothing else in the codebase hardcodes a path.

PLAIN ENGLISH: This file is the project's ADDRESS BOOK.

Imagine a big house with lots of rooms. Instead of every person in the house
having to remember "the pictures are in the third room on the left", everybody
just asks this address book: "where do pictures go?" and the address book
answers. If we ever move the picture room, we only change the address book once,
and everyone in the whole house automatically looks in the new place.

That is what the first sentence means by "nothing else in the codebase hardcodes
a path" -- no other file is allowed to write out a folder location by hand.
"""
# This is a special instruction to Python. It says: "when you read the type hints
# I wrote (like `-> None`), treat them as plain text and do not try to work out
# what they mean right this second." It lets us write modern, tidy type hints even
# on older versions of Python without anything breaking.
from __future__ import annotations

# "import" means "go and fetch a toolbox somebody else already built, so we do not
# have to build it ourselves".
# The `os` toolbox lets us talk to the computer's operating system -- for example
# to read "environment variables", which are little named notes a user can leave
# outside the program to change how it behaves.
import os
# The `pathlib` toolbox knows how to handle folder and file locations properly.
# We only want one tool out of that box: `Path`, which means "a place on the disk".
# Using Path instead of plain text means Windows, Mac and Linux all work, even
# though Windows writes C:\folder\file and the others write /folder/file.
from pathlib import Path

# Work out the top folder of this whole project, automatically.
# Read it from the inside out:
#   `__file__`   is Python's way of saying "the file you are reading right now"
#                (that is, this very paths.py file).
#   `Path(...)`  turns that name into a proper location object.
#   `.resolve()` cleans it into the full, complete address, with no shortcuts and
#                no "go up one" hops left inside it.
#   `.parents`   is the list of folders above this file: parents[0] is the folder
#                holding this file (research/core), parents[1] is the one above
#                that (research), parents[2] is the one above THAT -- the project
#                root, AEGIS-MARKET-STATISTICS.
# So REPO_ROOT means "the very top folder of this project", figured out on the fly,
# so everything still works if you move or rename the whole project folder.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Where all the results the research produces get saved (charts, tables, numbers).
# `os.environ` is the bag of environment variables -- those notes left outside the
# program. `.get("AEGIS_ARTIFACTS", <fallback>)` means:
#   "Is there a note called AEGIS_ARTIFACTS? If yes, use whatever it says.
#    If there is no such note, use the fallback instead."
# The fallback is a folder called `research_artifacts` inside the project root.
# The `/` between REPO_ROOT and the folder name does NOT mean divide here; for Path
# objects it means "and then go into", like the slash in a web address.
# Being overridable matters because a different computer (or a big shared cluster)
# may want these large output files written somewhere else, like a network drive.
ARTIFACTS = Path(os.environ.get("AEGIS_ARTIFACTS", REPO_ROOT / "research_artifacts"))
# Each line below carves out one labelled drawer inside that results folder, so the
# outputs never end up jumbled together in a single giant pile.
# The drawer for pictures and charts.
FIGURES = ARTIFACTS / "figures"
# The drawer for tables -- grids of numbers with headings.
TABLES = ARTIFACTS / "tables"
# The drawer for captions -- the little sentences printed underneath each figure
# that explain what the reader is looking at.
CAPTIONS = ARTIFACTS / "captions"
# The drawer for statistics -- the test results that say whether a finding is real
# or could easily have happened by pure luck.
STATISTICS = ARTIFACTS / "statistics"
# The drawer for full written reports about each experiment that was run.
REPORTS = ARTIFACTS / "experiment_reports"
# The drawer for supplementary material: the extra detail that would clutter up the
# main report, but that a careful checker still wants to be able to read.
SUPPLEMENTARY = ARTIFACTS / "supplementary"
# The drawer for LaTeX files. LaTeX is a typesetting language used to make academic
# papers look neat, especially the mathematics in them.
LATEX = ARTIFACTS / "latex"
# The drawer for CSV files. CSV means "comma separated values" -- a plain, simple
# spreadsheet that almost any program (including Excel) can open.
CSV = ARTIFACTS / "csv"
# The drawer for JSON files. JSON is a plain-text way of writing down structured
# information so that both people and programs can read it.
JSON = ARTIFACTS / "json"
# The drawer for manifests. A manifest is a packing list: it records exactly what
# was produced, when, and from which inputs, so results can be traced back later.
MANIFESTS = ARTIFACTS / "manifests"

# Where the raw ingredients live -- the market data the research reads IN, as
# opposed to the results it writes OUT. Same override trick as above: look for a
# note called AEGIS_DATA first, and otherwise use the `data` folder in the root.
DATA = Path(os.environ.get("AEGIS_DATA", REPO_ROOT / "data"))
# The "panel" is the main cleaned-up table of market data: many companies down the
# side, many dates across the top, all in one tidy grid.
PANEL = DATA / "panel"
# A cache is a scratch shelf for work that was already done once. If a slow
# calculation finished earlier, its answer is parked here so it need not be redone.
CACHE = DATA / "cache"

#: Authoritative exchange reference data downloaded by ``research.reference.acquire``.
#: Every file here has a row in ``reference_manifest.json`` naming its source, retrieval
#: instant, licence and checksum. Never hand-edited.
# PLAIN ENGLISH: this folder holds the official facts that came straight from the
# stock exchange itself -- the trustworthy master copy. For every file in here we
# also record where it came from, the exact moment we downloaded it, whether we are
# allowed to use it, and a "checksum" (a fingerprint number that changes if even one
# single character of the file changes). "Never hand-edited" is a firm rule: nobody
# may open these and tweak them, because then they would stop being the exchange's
# honest answer and would quietly become ours instead.
REFERENCE = DATA / "reference"

#: Records rejected by ingestion validation. Preserved, never deleted: a dropped row that
#: nobody can inspect is indistinguishable from a row that never existed.
# PLAIN ENGLISH: when data is loaded in it gets checked, and bad rows are thrown out.
# But "thrown out" here means "put in this box", not "destroyed". The reason is in
# the sentence above: if you silently delete a bad row, then later nobody can tell
# the difference between "there was a broken row and we removed it" and "there was
# never any row there at all". Those two stories mean very different things, so we
# keep the evidence.
QUARANTINE = DATA / "quarantine"

#: Read-only external NSE bhavcopy archive discovered by the repository audit.
#: Never written to. Overridable so the pipeline is portable off this machine.
# PLAIN ENGLISH: NSE is India's National Stock Exchange, and a "bhavcopy" is the
# daily summary file it publishes listing every share's prices for that day. This
# points at a big pile of those files that already existed on this computer, outside
# the project. "Read-only" means we may look but never change or add to it. It is
# "overridable" (through the AEGIS_NSE_ARCHIVE note) so that on somebody else's
# computer, where that pile sits somewhere different, the project still works.
NSE_ARCHIVE = Path(
    # Look for the note first...
    os.environ.get(
        # ...under this exact name...
        "AEGIS_NSE_ARCHIVE",
        # ...and if the note is missing, walk to this place instead.
        # `REPO_ROOT.parent` steps one folder UP and OUT of the project, and then we
        # go down into "capstone project", then "beta layer", then "data", then "raw".
        REPO_ROOT.parent / "capstone project" / "beta layer" / "data" / "raw",
    )
)

# One list holding every folder this project is responsible for creating.
# The underscore at the front of `_ALL` is a politeness signal to other programmers:
# "this is for use inside this file only, please do not reach in from outside."
# Notice NSE_ARCHIVE is deliberately NOT in this list -- we must never create it,
# because it belongs to somebody else and we only ever read from it.
_ALL = [
    ARTIFACTS, FIGURES, TABLES, CAPTIONS, STATISTICS, REPORTS, SUPPLEMENTARY,
    LATEX, CSV, JSON, MANIFESTS, DATA, PANEL, CACHE, REFERENCE, QUARANTINE,
]


# `def` means "define" -- teach the computer a brand new action and give it a name.
# This action is called `ensure_dirs`, short for "ensure directories", meaning
# "make certain every one of these folders really exists".
# The empty `()` means it needs nothing handed to it in order to do its job.
# `-> None` means it hands nothing back afterwards; it just goes and does the work.
def ensure_dirs() -> None:
    # A `for` loop means "do the following once for every item in this collection".
    # Here: take each folder location out of the `_ALL` list one at a time, and
    # while working on that one, call it `p` (short for "path").
    for p in _ALL:
        # `.mkdir()` means "make this directory (folder)".
        # `parents=True` says: if the folders ABOVE this one are missing too, build
        #   those as well -- like building the whole staircase, not just the top step.
        # `exist_ok=True` says: if the folder is already there that is perfectly
        #   fine, do not complain, just move on quietly. Without this, running the
        #   program a second time would crash.
        p.mkdir(parents=True, exist_ok=True)
