"""The AEGIS-Market backend: an orchestration layer over the canonical research code.

This package defines **no statistic, feature, model or metric**. It resolves a module id
to the adapter the manifest already names, validates the caller's inputs against the
schema the manifest already declares, invokes the canonical implementation, and shapes
what comes back into one response contract. Deleting this package would leave the research
pipeline exactly as it was, which is the same rule ``scripts/stages/`` follows.

Two execution modes, and the difference is reported on every response rather than left for
a reader to infer:

``LIVE_COMPUTATION``   the canonical analysis ran, now, on data the caller selected. The
                       numbers in the response did not exist before the request.
``VERIFIED_ARTIFACT``  a previously executed, provenance-stamped artifact is being
                       replayed through a traceable endpoint. Nothing was computed.

Labelling a replay as a computation is the failure this distinction exists to prevent, and
:func:`backend.contract.Response.check` refuses a response that tries.

Three things this layer will not do:

* **Run a shell.** Inputs reach an adapter as validated primitives in a dict. There is no
  path from a request to a command line, and :mod:`backend.service` never builds one.
* **Expose the filesystem.** Artifact paths are returned repository-relative, and the file
  endpoints serve only from a fixed allowlist of directories.
* **Bypass the protected-artifact guard.** A protected module returns ``PROTECTED`` with
  the reason; ``force`` is not reachable from the network.

PLAIN ENGLISH -- what this whole file is about:

THE WAITER, NOT THE COOK.

This part of the project sits between the website and the research code. And the very
first sentence is a promise about what it is NOT:

    "This package defines no statistic, feature, model or metric."

It calculates nothing. It takes an order, passes it to the kitchen, and brings back what
the kitchen made. The test given for this is lovely and exact: delete this whole package
and the research would be completely unaffected.

Why insist on that? Because the moment a display layer starts doing its own little
calculations -- rounding here, averaging there -- the website and the paper begin to
disagree, and nobody can say which is right. Keeping every number's origin in one place
means there is only ever one answer.

THE THREE THINGS IT REFUSES TO DO, which are security rules:

1. NEVER RUN A COMMAND. What a visitor types never becomes an instruction the computer
   executes. This closes off the single most dangerous class of bug on the internet, where
   somebody types a cleverly-shaped request and takes over the machine. There is simply no
   route from a request to a command line.

2. NEVER EXPOSE THE FILE SYSTEM. It serves files only from a fixed short list of folders.
   Without that, a request for something like `../../../passwords` could walk out of the
   project and into the rest of the computer.

3. NEVER OVERWRITE A PROTECTED RESULT. Some results have been cited in the paper. Those are
   frozen. There IS an override in the code -- and it cannot be reached from the internet,
   only by a person sitting at the machine.

AND THE TWO LABELS, again, because they matter everywhere:
  LIVE     -- "we worked this out just now."
  ARTIFACT -- "we are replaying a saved result."
Both honest. Confusing them is not, and a reply that tries is rejected.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# A label for this version of the backend, sent on every reply.
BACKEND_VERSION = "backend-v1"

#: How a result was obtained. Rendered verbatim in the interface.
# PLAIN ENGLISH: "verbatim" means these exact words reach the screen. The distinction is
# not an internal detail -- the person looking at the page is told which one they are seeing.
LIVE = "LIVE_COMPUTATION"
ARTIFACT = "VERIFIED_ARTIFACT"

# The friendly names shown on screen.
MODE_LABEL = {
    LIVE: "Live computation",
    ARTIFACT: "Verified experiment result",
}

# And the full explanations, so a visitor is never left guessing what a label means.
MODE_MEANING = {
    # Note the last sentence: it makes the freshness unmistakable.
    LIVE: ("The canonical implementation ran when you asked for it, on the data you "
           "selected. These numbers did not exist before this request."),
    # And this one is equally blunt in the other direction -- "nothing was computed for
    # this request" -- while also telling the reader exactly which run to go and check.
    ARTIFACT: ("A previously executed experiment, replayed from its provenance-stamped "
               "artifact. Nothing was computed for this request; the run identifier and "
               "commit below are the ones that produced these numbers."),
}

#: Response statuses. The first six mirror the module exit codes so a backend status and a
#: `run.bat` exit code cannot mean different things.
# PLAIN ENGLISH: the same job can be started from a web page or from the command line, and
# the two must not describe the same outcome differently. Lining the codes up at the bottom
# of this file is what guarantees they cannot drift apart.

# It worked.
OK = "OK"
# Something went wrong.
FAILED = "FAILED"
# It cannot run: something it needs does not exist.
BLOCKED = "BLOCKED"
# A required file is not on the disk.
INPUTS_MISSING = "INPUTS_MISSING"
# This result is frozen because the paper cites it.
PROTECTED = "PROTECTED"
# It has never been run yet.
NOT_YET_EXECUTED = "NOT_YET_EXECUTED"
# The request itself was malformed.
INVALID_INPUT = "INVALID_INPUT"
# No such module.
UNKNOWN_MODULE = "UNKNOWN_MODULE"
# It took too long and was stopped.
TIMEOUT = "TIMEOUT"
#: The selection was valid but left too little data to analyse. Distinct from
#: INPUTS_MISSING, which means a required file is not on disk: here the file is
#: present and the caller simply asked about a window that holds almost nothing.
# PLAIN ENGLISH: a genuinely useful distinction. "The file is missing" and "the file is
# there but you asked about a week when nothing happened" would both show as an error, and
# they call for completely different responses from the user -- go and build the data, or
# simply choose a wider date range.
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
#: The capability exists and works, but this demonstration is running with an earlier
#: active week and does not expose it yet. Distinct from every other refusal here: nothing
#: is missing, nothing failed, and nothing is protected. See `backend/capability.py`.
# PLAIN ENGLISH: "this works perfectly, it is simply switched off for this demonstration."
# Without its own status it would look like a failure, and somebody would waste an afternoon
# debugging a feature that was never broken.
FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"

#: Statuses a caller should render as an explained refusal rather than a failure. A
#: protected module refusing to regenerate a cited artifact is the guard working.
# PLAIN ENGLISH: an important difference for the person looking at the screen. A red ERROR
# says "something is broken, worry". These say "this did not run, and here is the perfectly
# good reason". The example given is exactly right: a frozen result refusing to be
# overwritten is the safety system doing its job, and displaying that as a failure would
# train people to ignore it.
REFUSALS = {PROTECTED, INPUTS_MISSING, NOT_YET_EXECUTED, INVALID_INPUT, BLOCKED,
            INSUFFICIENT_DATA, FEATURE_NOT_ENABLED}

# The translation table between command-line exit codes and these status names.
# By long tradition a program reports 0 for success and other numbers for various failures.
# Writing the mapping down in one place is what stops the web page and the terminal ever
# describing the same outcome in two different ways.
STATUS_FROM_CODE = {
    0: OK,
    1: FAILED,
    3: BLOCKED,
    4: INPUTS_MISSING,
    5: PROTECTED,
    6: NOT_YET_EXECUTED,
}
