"""Reproducibility manifests (spec sections 54, 83).

Every artifact the system emits can be traced back to one of these. A manifest that
cannot record a field records ``null`` and the reason -- it never guesses.

PLAIN ENGLISH -- what this whole file is about:

This file writes the RECEIPT for every result the project produces.

Imagine you baked a cake and it came out brilliant. A year later somebody asks you to
bake exactly the same cake again. Could you? Only if you wrote down: which recipe, which
brand of flour, which oven, what temperature, how long, and who baked it. Without those
notes, "it was great, I think there was flour in it" is not enough.

Science has the same problem, and the word for solving it is "reproducibility": another
person, on another computer, should be able to redo your work and get the very same
numbers. If they cannot, nobody can check whether you were right.

So every time this project produces a result, it also writes a receipt recording:
  * which version of the code was used (down to the exact edit),
  * which version of every toolbox was installed,
  * which computer it ran on,
  * which "seed" was used (the starting point for anything random),
  * the exact moment it ran,
  * and a fingerprint of the data, so we can tell if the data later changed.

And one strict rule, from the sentence above: if the receipt cannot find something out,
it writes down "null" -- meaning "unknown" -- and never, ever makes a guess. A guessed
receipt is worse than no receipt, because a guess still looks like a fact.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# `hashlib` makes "hashes" -- fingerprints for information. Feed it anything and it gives
# back a long code. The same input always gives the same code, and changing even one
# single character gives a completely different code. That is how we detect changes.
import hashlib
# For turning information into JSON text and back.
import json
# For talking to the operating system (here: asking how many processors the computer has).
import os
# For asking which kind of computer and operating system we are running on.
import platform
# For running other programs from inside this one -- here, the `git` and `node` commands.
import subprocess
# For asking about Python itself, such as its version number.
import sys
# Three tools from the `dataclasses` toolbox, for building tidy record-shaped things:
#   `dataclass` -- a label that turns a plain class into a neat record automatically.
#   `asdict`    -- turns such a record into a dictionary of labelled boxes.
#   `field`     -- lets us give a slot a cleverer default value than a fixed one.
from dataclasses import asdict, dataclass, field
# The world clock (UTC) and the tool for reading the date and time.
from datetime import UTC, datetime
# A safe, cross-platform way to talk about places on the disk.
from pathlib import Path
# A type hint meaning "any kind of value at all could be here".
from typing import Any


# A private helper for running a `git` command and getting its answer back as text.
# Git is the tool programmers use to track every change ever made to their code -- like a
# time machine with a complete history.
# `*args: str` means "accept any number of text arguments", so we can call `_git("status")`
# or `_git("rev-parse", "HEAD")` and both work.
# `-> str | None` means it hands back either some text, or nothing at all if it failed.
def _git(*args: str) -> str | None:
    # Be ready for this to go wrong: git might not be installed on this computer at all.
    try:
        # Run the command and wait for it to finish.
        out = subprocess.run(
            # The command to run. `["git", *args]` builds a list starting with the word
            # "git" and then all the extra words we were handed. The `*` unpacks them, so
            # they arrive as separate words rather than as one list stuffed inside a list.
            ["git", *args],
            # `cwd` is "current working directory": which folder to stand in while running.
            # We stand in the project root (this file, up three levels), because git only
            # answers properly when you are inside the project it is tracking.
            cwd=str(Path(__file__).resolve().parents[2]),
            # `capture_output=True` -- catch what the command prints instead of letting it
            #                          spill onto our screen.
            # `text=True`           -- hand it to us as readable words rather than as raw
            #                          computer bytes.
            # `timeout=15`          -- if it has not finished within 15 seconds, give up.
            #                          Without this, a stuck git command would freeze the
            #                          whole build forever.
            capture_output=True, text=True, timeout=15,
        )
        # The "return code" is how a finished program reports whether it went well.
        # By long tradition, 0 means "all fine" and anything else means "something failed".
        if out.returncode == 0:
            # `out.stdout` is what the command printed. `.strip()` trims off the blank
            # space and the newline at the ends.
            # `... or None` is a neat trick: if the trimmed text is empty, an empty piece
            # of text counts as "false" in Python, so the `or` moves on and hands back
            # None instead. That way "it printed nothing" is reported honestly as "unknown"
            # rather than as an empty answer pretending to be a real one.
            return out.stdout.strip() or None
    except Exception:
        # Git missing, git stuck, project not tracked by git -- any of these. Say nothing.
        pass
    # If we reach here, either the command failed or something went wrong. Hand back None,
    # which is the honest "I do not know" this file promised never to fake.
    return None


# Ask git: exactly which version of the code is this?
def git_commit() -> str | None:
    # A "commit" is one saved snapshot of the whole project at a moment in time, and it has
    # a unique fingerprint code. "HEAD" is git's word for "the snapshot we are on right
    # now". `rev-parse` means "turn that name into its actual code".
    # The answer looks like: a4f3c9e8b2... -- and it pins down the code exactly.
    return _git("rev-parse", "HEAD")


# Ask git: has anybody edited the code since the last saved snapshot?
# `-> bool | None` means the answer is True, or False, or "unknown".
def git_dirty() -> bool | None:
    # `status --porcelain` asks git to list any changed files in a plain, tidy format
    # designed for programs to read rather than humans. If nothing has changed, it prints
    # nothing at all.
    status = _git("status", "--porcelain")
    # Read this as: "if we could not ask git, the answer is None (unknown). Otherwise, turn
    # what it said into a plain yes-or-no."
    # `bool(status)` is True when there is some text (so: files were changed = dirty), and
    # False when the text is empty (so: nothing changed = clean).
    # This matters enormously for the receipt: "dirty" means the code was fiddled with
    # after the last snapshot, so the snapshot fingerprint alone no longer tells the whole
    # truth about what actually ran.
    return None if status is None else bool(status)


# Find out which version of each toolbox is installed on this computer.
# `-> dict[str, str]` means it hands back labelled boxes where both the labels and the
# contents are pieces of text, e.g. {"numpy": "1.26.4"}.
def package_versions() -> dict[str, str]:
    # The list of toolboxes we care about. Very briefly, what each one does:
    #   numpy       -- fast maths on big piles of numbers
    #   pandas      -- tables of data, like a programmable spreadsheet
    #   scipy       -- scientific and statistical maths
    #   sklearn     -- machine learning (programs that learn patterns from examples)
    #   matplotlib  -- drawing charts
    #   statsmodels -- statistical models and tests
    #   networkx    -- networks: dots joined by lines, for studying how things connect
    #   shap        -- explaining WHY a model gave the answer it gave
    #   pyarrow     -- reading and writing large data files quickly
    #   duckdb      -- a small, fast database for querying data
    #   PIL         -- images
    #   soundfile   -- sound files
    #   imageio     -- reading and writing images and video
    # Versions matter because toolboxes change. A result produced with one version might
    # not come out identical under another, so the receipt has to name them.
    names = ["numpy", "pandas", "scipy", "sklearn", "matplotlib", "statsmodels",
             "networkx", "shap", "pyarrow", "duckdb", "PIL", "soundfile", "imageio"]
    # Start with an empty set of labelled boxes to fill in.
    out: dict[str, str] = {}
    # Go through the toolbox names one at a time, calling the current one `n`.
    for n in names:
        # Be ready for failure: this toolbox may simply not be installed.
        try:
            # `__import__(n)` fetches a toolbox whose name is held in a variable. (The
            # ordinary `import numpy` needs the name typed out in the code; this version
            # works when the name is only known while the program is running.)
            mod = __import__(n)
            # Ask the toolbox for its version label. `getattr(mod, "__version__", "unknown")`
            # means "give me its __version__ if it has one, otherwise the word unknown" --
            # polite asking again, so a toolbox that does not advertise its version does not
            # crash us. `str(...)` makes sure the answer is text either way.
            out[n] = str(getattr(mod, "__version__", "unknown"))
        except Exception:
            # Not installed. Record that plainly. Note we write down the fact rather than
            # skipping the entry: "this toolbox was absent" is itself useful evidence for
            # somebody trying to reproduce the run.
            out[n] = "NOT INSTALLED"
    # Hand back the filled-in set of boxes.
    return out


# Work out the fingerprint of a file, so we can prove later whether it changed.
#   `path`  which file.
#   `chunk` how much to read at a time. `1 << 20` is a compact way of writing 1,048,576,
#           which is one megabyte. (The `<<` means "shift the number 1 left by 20 binary
#           places", which is the same as multiplying by 2 twenty times.)
def file_hash(path: str | Path, chunk: int = 1 << 20) -> str:
    # Start a new SHA-256 fingerprint machine. SHA-256 is a well-known, trusted recipe
    # that turns any amount of information into a 64-character code.
    h = hashlib.sha256()
    # Open the file. `"rb"` means "read, in binary" -- take the raw bytes exactly as they
    # are, making no attempt to read them as words. That is right here because we want the
    # fingerprint of the true contents, whether it is text, a picture or anything else.
    with open(path, "rb") as fh:
        # `while True:` means "keep going round and round forever", until something inside
        # explicitly breaks out.
        while True:
            # Read the next megabyte. We do it a piece at a time, rather than all at once,
            # so that a file bigger than the computer's memory can still be fingerprinted.
            b = fh.read(chunk)
            # If we got nothing back, we have reached the end of the file.
            if not b:
                # `break` means "leave the loop now".
                break
            # Feed this piece into the fingerprint machine. Feeding it in pieces gives
            # exactly the same final answer as feeding the whole file in one go.
            h.update(b)
    # `hexdigest()` asks the machine for the finished fingerprint, written using the
    # characters 0-9 and a-f, which makes it safe to store in text and JSON.
    return h.hexdigest()


# Work out the fingerprint of a set of settings, rather than of a file.
def dict_hash(obj: Any) -> str:
    return hashlib.sha256(
        # Read this from the inside out:
        #   `json.dumps(obj, ...)` -- write the settings out as text.
        #   `sort_keys=True`       -- ALWAYS put the labels in alphabetical order. This is
        #                             the crucial bit: {"a":1,"b":2} and {"b":2,"a":1} mean
        #                             exactly the same thing, but written differently they
        #                             would give different fingerprints. Sorting forces one
        #                             single spelling, so identical settings always produce
        #                             an identical code.
        #   `default=str`          -- if json meets something it cannot write down, use its
        #                             name as text instead of giving up.
        #   `.encode("utf-8")`     -- turn the text into raw bytes, because the fingerprint
        #                             machine works on bytes, not on words.
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# This label tells Python: "the class below is a plain record". Python then writes all the
# boring set-up code for us -- how to build one, how to compare two, how to print one.
@dataclass
# Define the receipt itself.
class ReproducibilityManifest:
    # Each line below is one slot on the receipt. `name: type` declares the slot and says
    # what sort of value belongs in it. Slots with no `=` are compulsory: you must supply
    # them when making a receipt.

    # Which experiment this was -- the name of the question being asked.
    experiment_id: str
    # Which particular run of it -- you might run the same experiment many times.
    run_id: str
    # The "seed" for randomness. Computers cannot really be random; they follow a fixed
    # recipe that only LOOKS random, and the seed is where that recipe starts. Same seed,
    # same "random" numbers, every time. Writing it down is what lets somebody else get
    # byte-for-byte identical results instead of merely similar ones.
    seed: int
    # All the settings and dials used for this run.
    # `field(default_factory=dict)` means "if nobody supplies one, make a brand new empty
    # dictionary". It must be written this way rather than as `= {}`, because a plain `{}`
    # would be ONE dictionary shared by every receipt ever made, so filling in one receipt
    # would mysteriously fill in all the others too.
    config: dict[str, Any] = field(default_factory=dict)
    # Which version of the data was used. `| None = None` means "may be unknown, and
    # unknown is what you get if nobody says".
    dataset_version: str | None = None
    # The fingerprint of that data, so we can prove later whether it was altered.
    dataset_hash: str | None = None
    # Which versions of the prediction models were used.
    model_versions: dict[str, str] = field(default_factory=dict)
    # Which versions of the explanation tools were used. XAI stands for "eXplainable
    # Artificial Intelligence" -- the tools that say WHY a model decided what it decided.
    xai_versions: dict[str, str] = field(default_factory=dict)
    # Which version of the "features" -- the measurements calculated from the raw data and
    # fed to the models.
    feature_version: str | None = None
    # The code snapshot fingerprint. `default_factory=git_commit` means "if nobody tells
    # me, go and RUN the git_commit action and use whatever it finds out". So the receipt
    # fills this in by itself.
    git_commit: str | None = field(default_factory=git_commit)
    # Whether the code had unsaved edits when this ran. Also filled in automatically.
    git_dirty: bool | None = field(default_factory=git_dirty)
    # Which version of Python. `lambda: ...` is a tiny throwaway action written inline.
    # `sys.version` is a long sentence like "3.12.1 (main, Dec 2023) [MSC v.1937]", and
    # `.split()[0]` chops it at the spaces and keeps only the first piece: "3.12.1".
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    # Which version of Node.js, the tool that runs the website side of this project.
    # Filled in later, in the tidy-up step below, rather than here.
    node_version: str | None = None
    # A description of the computer and operating system, e.g. "Windows-11-10.0.26200".
    platform: str = field(default_factory=lambda: platform.platform())
    # Every toolbox version, gathered automatically by the action we defined earlier.
    packages: dict[str, str] = field(default_factory=package_versions)
    # The exact moment this receipt was created.
    # `datetime.now(UTC)` reads the world clock, and `.isoformat()` writes it in the
    # international standard spelling: 2026-08-28T14:05:09.123456+00:00. That spelling is
    # unambiguous everywhere, unlike "08/28/26", which different countries read differently.
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat())
    # Any extra remarks a human wanted to attach. Starts as an empty list.
    notes: list[str] = field(default_factory=list)

    # `__post_init__` is a special tidy-up step Python runs automatically straight after a
    # new record has been built. It is the place for anything that has to wait until the
    # ordinary slots are already filled in.
    def __post_init__(self) -> None:
        # If nobody told us the Node.js version, go and find it out ourselves.
        # This is done here rather than as a `default_factory` above so that a caller who
        # already knows the answer can supply it and we skip the slow lookup entirely.
        if self.node_version is None:
            self.node_version = _node_version()
        # If there are any settings, fingerprint them, so two runs can be compared at a
        # glance: same code means the same fingerprint, and one different dial means a
        # completely different one.
        if self.config:
            self.config_hash = dict_hash(self.config)
        else:
            # No settings, so no fingerprint. We say None (unknown) rather than inventing
            # the fingerprint of an empty box, which would look like a real answer.
            self.config_hash = None

    # Save this receipt to disk as a JSON file.
    def write(self, path: Path) -> Path:
        # Make sure the folder exists first, building the whole staircase if need be.
        path.parent.mkdir(parents=True, exist_ok=True)
        # Turn the record into a plain dictionary of labelled boxes, which is the shape
        # json knows how to write down.
        d = asdict(self)
        # Add the settings fingerprint by hand. It needs adding separately because it was
        # created in the tidy-up step rather than declared as a proper slot, so `asdict`
        # does not know about it. `getattr(..., None)` asks politely, so this still works
        # if for some reason the tidy-up never ran.
        d["config_hash"] = getattr(self, "config_hash", None)
        # Write the file.
        #   `indent=2`         -- lay it out over several lines with two-space steps, so a
        #                         human can actually read the receipt.
        #   `default=str`      -- anything json cannot handle gets written as its name.
        #   `encoding="utf-8"` -- the alphabet to save in; utf-8 covers every language.
        path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        # Hand back where it was saved.
        return path


# A private helper that asks Node.js which version it is. Node.js is the program that runs
# JavaScript outside a browser; this project's website half is built with it.
def _node_version() -> str | None:
    # Be ready for failure -- Node may not be installed at all.
    try:
        # Run the command `node --version`, catching its output, as readable words, and
        # giving up after 10 seconds so a stuck command cannot freeze the build.
        out = subprocess.run(["node", "--version"], capture_output=True, text=True,
                             timeout=10)
        # 0 means it worked.
        if out.returncode == 0:
            # Hand back what it printed, with the surrounding blank space trimmed off.
            # It looks like "v20.11.0".
            return out.stdout.strip()
    except Exception:
        # Not installed, or it hung. Never mind.
        pass
    # Honest "I do not know".
    return None


# Take one complete photograph of the whole environment: the computer, the software, the
# code version, and the moment in time. This is the fullest form of the receipt.
def environment_snapshot() -> dict[str, Any]:
    # Hand back one set of labelled boxes holding everything worth recording.
    return {
        # The full Python version sentence, including how it was built.
        "python": sys.version,
        # The interpreter's *name*, not its path. Which directory someone's virtualenv
        # lives in reproduces nothing, and these snapshots are copied into artifacts that
        # are served to readers, so the path would publish a stranger's home directory
        # while telling them nothing they could act on.
        # PLAIN ENGLISH: `sys.executable` is the full address of the Python program that
        # is running, something like C:/Users/alice/project/.venv/Scripts/python.exe.
        # `Path(...).name` keeps only the last bit: "python.exe". We deliberately throw the
        # rest away for two reasons -- it would tell the world Alice's username and how her
        # computer is arranged, and it would help the reader not one jot, because they do
        # not have a folder called C:/Users/alice anyway.
        "executable": Path(sys.executable).name,
        # Which operating system and version.
        "platform": platform.platform(),
        # Which kind of processor chip is inside the machine.
        "processor": platform.processor(),
        # How many processor cores the machine has. More cores means more work can happen
        # at the same time, which is worth recording because it can change how long a run
        # takes -- and, for some calculations, even the exact order things are added up.
        "cpu_count": os.cpu_count(),
        # Every toolbox version, gathered by the action defined earlier.
        "packages": package_versions(),
        # The Node.js version, or None if Node is not installed.
        "node": _node_version(),
        # Which snapshot of the code this was.
        "git_commit": git_commit(),
        # Whether the code had unsaved edits at the time.
        "git_dirty": git_dirty(),
        # The exact moment the photograph was taken, on the world clock.
        "timestamp": datetime.now(UTC).isoformat(),
    }
