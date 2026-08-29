"""Strict JSON writing for every published artifact.

Python's ``json`` module emits bare ``NaN``, ``Infinity`` and ``-Infinity`` by default.
None of those is valid JSON. ``json.loads`` accepts them, so a Python-only pipeline never
notices, but ``JSON.parse`` and most strict parsers reject the *entire document* — one
non-finite float buried in a nested result turns a whole artifact into an unreadable file.

That failure already happened once here, in the exported app bundles, where it silently
rendered a page as "data not available" while every Python test passed. This module
exists so the same class of bug cannot recur in the research artifacts, which are the
reproducible record the paper is built from.

A non-finite float becomes ``null``. That is the honest encoding: the value is not a
number, and a reader deserves to see a missing value rather than a token their parser
cannot read.

PLAIN ENGLISH -- what this whole file is about:

JSON is a way of writing information down as plain text so that any program can read
it back. Think of it as a very strict form for filling in.

Now, sometimes a sum goes wrong and the answer is not a real number. There are three
famous "not a real number" answers:
  * NaN       -- "Not a Number", what you get from a nonsense sum like 0 divided by 0.
  * Infinity  -- what you get from dividing by zero: bigger than any number there is.
  * -Infinity -- the same thing, but smaller than any number there is.

Python is happy to scribble those three words into a JSON file. But the official JSON
rules say those words are not allowed. Python does not mind reading its own scribbles
back, so if only Python ever looks, nobody notices anything is wrong. The trouble comes
when a web browser tries to read the file: the browser follows the rules strictly, sees
one illegal word, and throws away THE WHOLE FILE -- not just the bad bit.

That really happened on this project. One bad number hidden deep inside a file made a
whole web page say "data not available", while every single test still passed, so it
looked fine from the inside. This file exists so that can never happen again.

The fix is to write `null` (meaning "no value here") instead. That is the honest thing
to say: the sum did not produce a number, so the reader should be told the value is
missing, rather than being handed a word their program cannot understand.
"""
# Tells Python to treat the type hints in this file as plain text rather than working
# them out immediately. It keeps modern, tidy type hints working everywhere.
from __future__ import annotations

# The `json` toolbox knows how to turn Python information into JSON text and back.
import json
# The `math` toolbox holds mathematical helpers. We want one in particular: a checker
# that tells us whether a number is a proper, ordinary, finite number.
import math
# `Path` represents a place on the disk (a file or folder) in a safe, cross-platform way.
from pathlib import Path
# `Any` is a type hint meaning "literally any kind of value could turn up here". We use
# it because the things we are saving could be numbers, words, lists, or nested boxes.
from typing import Any


# Define an action called `sanitise`, which is British English for "make clean and safe".
# It takes one thing (`obj`, short for "object", meaning "any piece of information") and
# hands back a cleaned-up version of it.
def sanitise(obj: Any) -> Any:
    """Recursively replace non-finite floats with ``None``."""
    # PLAIN ENGLISH: "recursively" means this action calls ITSELF on the smaller pieces
    # inside. Picture opening a parcel: inside are more parcels, and inside those are
    # more parcels still. You handle each one the same way -- open it, and if what is
    # inside is another parcel, do the whole thing again -- until you reach real objects.

    # `isinstance(obj, float)` asks: "is this thing a decimal number?" A `float` is a
    # number that can have a fractional part, like 3.5 or -0.001.
    if isinstance(obj, float):
        # `math.isfinite(obj)` asks: "is this a proper ordinary number?" It answers no for
        # NaN, Infinity and -Infinity.
        # `not math.isfinite(obj)` therefore means "this is one of the bad ones".
        # The whole line reads: "hand back None if the number is bad, otherwise hand back
        # the number exactly as it is". `None` is Python's word for "nothing here", and it
        # is written as `null` when it is saved into JSON.
        return None if not math.isfinite(obj) else obj
    # `dict` is short for "dictionary": a set of labelled boxes, like {"price": 10}. You
    # look things up by their label (the "key") rather than by their position.
    if isinstance(obj, dict):
        # This builds a brand new dictionary from the old one.
        # `for k, v in obj.items()` walks through every pair, calling the label `k` (key)
        # and the contents `v` (value).
        # `k: sanitise(v)` keeps each label exactly as it was, but sends the contents back
        # through this same cleaning action -- that is the recursion opening the next
        # parcel down.
        return {k: sanitise(v) for k, v in obj.items()}
    # A `list` is an ordered row of things, like [1, 2, 3]. A `tuple` is the same idea but
    # frozen so it can never be changed afterwards. We treat both the same way here.
    if isinstance(obj, (list, tuple)):
        # Build a new list by cleaning every item inside the old one, keeping the order.
        # Note a tuple comes back as a list -- which is fine, because JSON has only one
        # kind of row anyway and does not know the difference.
        return [sanitise(v) for v in obj]
    # numpy scalars answer to ``item()`` and would otherwise slip through as float
    # subclasses that ``isinstance(obj, float)`` does catch, and as integer types it does
    # not. Converting first keeps both paths on the same branch.
    # PLAIN ENGLISH: numpy is a toolbox for doing maths on huge piles of numbers very
    # fast. Its numbers look like ordinary Python numbers but are secretly a different
    # species. Some of them get caught by the float check above and some sneak past. To
    # stop that being unpredictable, we spot them here and turn them into normal Python
    # numbers, so every one of them goes down exactly the same road.
    # `getattr(obj, "item", None)` means: "does this thing have a button labelled `item`?
    # If it does, hand me the button; if not, hand me None." Asking this way is polite --
    # it does not crash when the button is missing.
    item = getattr(obj, "item", None)
    # Two checks before we press it, because we must be sure this really is a numpy number:
    #   `callable(item)`        -- is the thing we found actually a button we can press
    #                              (an action), rather than just a value sitting there?
    #   `hasattr(obj, "dtype")` -- does it also carry a "dtype" label? dtype means "data
    #                              type" and is numpy's way of recording what kind of
    #                              number it is holding. Only numpy things have it.
    if callable(item) and hasattr(obj, "dtype"):
        # Press the button (`item()`) to get the plain Python number out, then send THAT
        # back through the cleaner -- so if it turns out to be a NaN, the very first check
        # in this action will catch it and turn it into None.
        return sanitise(item())
    # If it was none of the above -- so a piece of text, a whole number, a True/False, or
    # a None -- there is nothing to clean. Hand it straight back untouched.
    return obj


# Define an action called `dumps`. In Python's json toolbox, "dump" means "write this
# information out", and the trailing "s" means "to a string" (a piece of text) rather
# than straight into a file.
#   `payload`      is the information we want to write down.
#   `indent: int | None = 2`
#                  is how many spaces to use when nesting things, to make the text
#                  pretty and readable. The `| None` means you may also say "no indenting
#                  at all, squash it flat". The `= 2` means if you do not say anything,
#                  two spaces is what you get.
# `-> str` means the action hands back a piece of text.
def dumps(payload: Any, indent: int | None = 2) -> str:
    """Serialise with non-finite floats nulled and bare ``NaN`` refused outright."""
    # PLAIN ENGLISH: "serialise" means "flatten this information into a line of text that
    # can be saved or sent somewhere". Reading the arguments one by one:
    #   `sanitise(payload)` -- clean it first, so the bad numbers are already gone.
    #   `indent=indent`     -- lay it out prettily with the requested spacing.
    #   `default=str`       -- if json meets something it has no idea how to write down
    #                          (a date, say), do not give up: just write its name as text.
    #   `allow_nan=False`   -- this is the belt-and-braces safety catch. It orders json to
    #                          REFUSE, loudly and with an error, if any bad number is still
    #                          in there. The cleaning above should have removed them all,
    #                          so if this ever fires it means the cleaner has a hole in it,
    #                          and we would far rather find out with a crash right now than
    #                          quietly ship a broken file that a browser cannot read.
    return json.dumps(sanitise(payload), indent=indent, default=str, allow_nan=False)


# Define an action called `write`, which actually saves a file on the disk.
#   `path`    is where to save it. `str | Path` means you may pass the location either as
#             ordinary text or as a proper Path object -- both are accepted.
#   `payload` is the information to save.
#   `indent`  is the pretty-printing spacing, same as above.
# `-> Path` means it hands back the location it saved to, which is handy for logging.
def write(path: str | Path, payload: Any, indent: int | None = 2) -> Path:
    """Write a strict-JSON artifact, creating the parent directory if needed."""
    # Turn whatever we were given into a proper Path object. If it already is one, this
    # changes nothing; if it was text, it is now upgraded. Either way, from here on we
    # know exactly what we are holding.
    p = Path(path)
    # `p.parent` is the folder that contains the file. `.mkdir()` makes that folder.
    #   `parents=True`   -- also build any missing folders above it, the whole staircase.
    #   `exist_ok=True`  -- if it is already there, that is fine, do not complain.
    # Without this line, saving into a brand new folder would fail.
    p.parent.mkdir(parents=True, exist_ok=True)
    # `write_text` puts a piece of text into the file, replacing anything already there.
    # `dumps(...)` produces that text, already cleaned and checked.
    # `encoding="utf-8"` says which alphabet to use when saving. UTF-8 can spell every
    # character in every language, so names with accents or symbols survive the trip.
    p.write_text(dumps(payload, indent=indent), encoding="utf-8")
    # Hand the location back to whoever asked, so they can report or reuse it.
    return p


# -- bundles served to a reader --------------------------------------------------------
# PLAIN ENGLISH: everything from this point down is about files that get sent to somebody
# else's web browser, which needs more care than files we only keep for ourselves.

# Define an action called `scrub_paths`. To "scrub" is to clean hard.
#   `node`  is the piece of information we are looking at right now. It is called a "node"
#           because information nests inside information like branches on a tree, and each
#           point on the tree is a node.
#   `found` is a notepad we carry along, writing down every path we had to fix.
#           `list[str] | None = None` means: a list of text items, or nothing at all, and
#           if you do not pass one then nothing is what you get by default.
def scrub_paths(node: Any, found: list[str] | None = None) -> Any:
    """Rewrite absolute paths under the repository to repository-relative ones.

    Everything written by :func:`write_public` is served to a browser. An absolute path in
    that payload publishes the directory layout of whichever machine ran the pipeline,
    while being useless to the reader: a path under someone's home directory is not a
    citation. Rewriting is the correct repair because the *relative* path is the true
    reference — the file is in the repository either way.
    """
    # PLAIN ENGLISH: an "absolute path" is a full address starting from the very top of
    # the computer, like C:/Users/alice/Downloads/project/data/prices.csv. A "relative
    # path" starts from the project instead: data/prices.csv.
    # Two reasons the full address is wrong to publish:
    #   1. PRIVACY -- it tells the whole world your username and how your computer is
    #      arranged. That is nobody's business.
    #   2. IT IS USELESS -- the reader does not have a folder called C:/Users/alice, so
    #      the address means nothing on their machine.
    # The short version works for everybody, because the file sits at the same spot inside
    # the project no matter whose computer the project has been copied onto.

    # Fetch the address book (the paths module we met earlier) so we can ask it where the
    # project root is. It is fetched here, inside the action, rather than at the top of
    # the file, to avoid two files trying to load each other at the same moment and
    # getting stuck in a loop -- a classic problem called a "circular import".
    from research.core import paths as _paths

    # If nobody handed us a notepad, start a fresh empty one.
    # Why not just write `found=[]` up in the definition line? Because in Python that one
    # single list would be shared by every call for the whole life of the program, so
    # notes from one run would leak into the next. This is the standard, safe way.
    found = [] if found is None else found
    # Get the project's top folder as text. `.as_posix()` writes it with forward slashes
    # (/) even on Windows, so we have one consistent spelling to compare against.
    root = _paths.REPO_ROOT.as_posix()
    # Is the thing we are looking at a piece of text? Only text can hide a file path.
    if isinstance(node, str):
        # Swap every backslash for a forward slash, so a Windows-style address is written
        # the same way as the `root` we just prepared and the two can be compared fairly.
        text = node.replace("\\", "/")
        # Does this text begin with the project root followed by a slash? If so, it is an
        # absolute address pointing inside our own project -- exactly what we must fix.
        if text.startswith(root + "/"):
            # Note the original down on the notepad, so we can report it afterwards.
            found.append(node)
            # Snip off the front. `len(root) + 1` counts the characters in the root plus
            # the one slash after it, and `text[that:]` means "everything from there on".
            # C:/Users/alice/project/data/x.csv  becomes  data/x.csv
            return text[len(root) + 1:]
        # It was text, but not one of our addresses -- an ordinary word or sentence. Leave
        # it completely alone.
        return node
    # If it is a set of labelled boxes, clean the contents of each box, keeping the labels.
    # The same `found` notepad is passed down so every note lands on one shared page.
    if isinstance(node, dict):
        return {k: scrub_paths(v, found) for k, v in node.items()}
    # If it is a row of things, clean each item in the row, in order.
    if isinstance(node, (list, tuple)):
        return [scrub_paths(v, found) for v in node]
    # Anything else -- a number, a True/False, a None -- cannot contain a file path, so
    # hand it straight back untouched.
    return node


# Define an action for saving a file that will be published to the outside world.
#   `path`    where to save it.
#   `payload` what to save.
#   `log`     an optional way of announcing messages. `log=None` means "if you do not give
#             me one, I will simply stay quiet".
def write_public(path: str | Path, payload: Any, log=None) -> Path:
    """Write a bundle destined for ``public/``, with no absolute path left in it.

    Whatever is rewritten is reported rather than silently corrected, so a producer that
    starts recording absolute paths becomes visible on the next export instead of being
    cleaned up forever behind its own back.
    """
    # PLAIN ENGLISH on that second paragraph: we could just quietly fix the addresses and
    # say nothing. But then whichever part of the program keeps producing bad addresses
    # would never get found, and this cleaner would be covering for it forever. So we fix
    # the file AND announce what we fixed, and somebody can go and mend the real cause.
    # Start a blank notepad. The `: list[str]` is a note to other programmers saying "this
    # holds pieces of text", which helps their editors catch mistakes.
    found: list[str] = []
    # Clean the whole payload, and let the notepad fill up as a side effect.
    cleaned = scrub_paths(payload, found)
    # `if log:` means "if somebody actually gave us a way to announce things". If they did
    # not, we skip this whole block rather than crashing.
    if log:
        # `set(found)` throws away duplicates, so a path seen ten times is reported once.
        # `sorted(...)` puts them in alphabetical order so the report is tidy and the same
        # every time, which makes runs easy to compare.
        for one in sorted(set(found)):
            # Announce it. The `%s` is a gap that the path gets slotted into.
            log("      REWROTE ABSOLUTE PATH %s" % one)
    # Now save the cleaned-up version using the strict writer defined further up, so it
    # gets the bad-number treatment as well. Hand back where it was saved.
    return write(path, cleaned)
