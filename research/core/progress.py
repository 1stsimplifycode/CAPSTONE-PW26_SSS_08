"""Stage timing that survives a buffered pipe.

Long builds print nothing until they exit when stdout is redirected, which makes a slow
stage indistinguishable from a hung one. Every stage therefore also appends to
``research_artifacts/manifests/progress.log`` with an explicit flush, so progress is
observable from another process while the build runs.

PLAIN ENGLISH -- what this whole file is about:

This file is the project's TOWN CRIER. Its job is to shout out what the program is
doing right now, and how long each part took.

Why is that hard? Because of something called "buffering". Imagine you are writing a
letter, but instead of posting each page as you finish it, you pile the pages up on
your desk and only post the whole bundle when you have finished the entire letter.
Computers do that with messages, because posting one big bundle is much faster than
posting many small notes.

Usually that is fine. But when the messages are being piped into a file instead of
onto the screen, the pile can sit on the desk for a very long time. So you sit there
watching an empty screen with absolutely no idea whether:
  * the program is working hard on something slow, or
  * the program has frozen solid and will never finish.

Those two look exactly the same from outside, which is horrible when a build takes
hours. So this file does two things: it shouts the message out loud, AND it writes the
same message into a logbook file, forcing it out of the door immediately (that is what
"flush" means -- empty the desk now, do not wait for the pile to grow). Then somebody
in another window can open the logbook and watch progress happening live.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# The `time` toolbox lets us measure how long things take.
import time
# `contextmanager` is a tool for building "wrappers": actions that do something before a
# job and something else after it, automatically. It is explained properly further down.
from contextlib import contextmanager
# `UTC` is Coordinated Universal Time -- the world's single shared clock, the same
# everywhere on Earth, so timestamps mean one thing no matter which country ran the code.
# `datetime` is the tool for asking what the date and time are.
from datetime import UTC, datetime

# Fetch our own address book, so we know where the logbook should live.
from research.core import paths

# Build the full location of the logbook file: inside the manifests drawer, a file called
# progress.log. The underscore in front says "this is private to this file".
_LOG = paths.MANIFESTS / "progress.log"


# Define the private action that actually says a message. "Emit" means "send out".
# `msg: str` means it expects one piece of text. `-> None` means it hands nothing back.
def _emit(msg: str) -> None:
    # Build the line we are going to say, by gluing a timestamp onto the front.
    #   `datetime.now(UTC)`   -- what time is it right now, on the world clock?
    #   `.strftime("%H:%M:%S")` -- "string format time": write that as hours:minutes:seconds,
    #                            so 14:05:09 rather than a long unreadable machine date.
    #   `"%s  %s" % (a, b)`   -- the two `%s` marks are gaps, and the pair after the `%`
    #                            fills them in order. So we end up with the time, two
    #                            spaces, then the message.
    line = "%s  %s" % (datetime.now(UTC).strftime("%H:%M:%S"), msg)
    # Say it on the screen. `flush=True` is the important bit: it means "do not pile this
    # up on the desk, post it this instant".
    print(line, flush=True)
    # `try` means "attempt the following, but be ready for it to go wrong".
    # We use it here because writing the logbook is a nice-to-have. If the disk is full or
    # the folder is locked, we would much rather carry on with the actual research than
    # crash a three-hour build over a failed progress note.
    try:
        # Make sure the folder for the logbook exists before writing into it.
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        # Open the logbook file.
        #   `"a"` means "append": add to the end, keeping everything already written.
        #         (The alternative, "w", would wipe the file first -- wrong here.)
        #   `encoding="utf-8"` -- the alphabet to write in; utf-8 covers every language.
        #   `with ... as fh` -- borrow the file, call it `fh` ("file handle"), and close it
        #         automatically when we are done, even if something goes wrong inside.
        with open(_LOG, "a", encoding="utf-8") as fh:
            # Write the line, and add "\n", which means "start a new line" -- so the next
            # message does not get stuck onto the end of this one.
            fh.write(line + "\n")
            # Force it out of the door right now, rather than letting it wait on the desk.
            # This is the whole reason somebody in another window can watch it live.
            fh.flush()
    # `except Exception:` catches any problem at all that happened inside the `try`.
    except Exception:
        # `pass` means "do absolutely nothing". We deliberately swallow the problem: a
        # failed progress note must never be allowed to stop the real work.
        pass


# The public way to say a message. It simply passes the job to the private action above.
# Having a public name and a private worker means we could change HOW messages are said
# later on, without every other file in the project having to change too.
def log(msg: str) -> None:
    _emit(msg)


# Wipe the logbook clean, ready for a fresh run.
def reset() -> None:
    # Again, wrapped in `try` because tidying up must never crash the program.
    try:
        # Only try to delete it if it is actually there.
        if _LOG.exists():
            # `.unlink()` is Python's word for "delete this file". (The name comes from
            # how file systems work underneath: you remove the link to the file.)
            _LOG.unlink()
    except Exception:
        # Could not delete it -- perhaps another program has it open. Never mind; carry on.
        pass


# This decorator (a line starting with `@` that sits on top of an action and gives it a
# new power) turns the action below into a "wrapper" you can use with the word `with`.
@contextmanager
# Define a wrapper called `stage`. A stage is one named chunk of a long build, like
# "loading data" or "running tests".
def stage(name: str):
    # PLAIN ENGLISH: this lets somebody else write
    #     with stage("loading data"):
    #         ...their work here...
    # and the START message, the stopwatch and the DONE message all happen by themselves.
    # It is like a running track official: they fire the pistol, wait while you run, and
    # write down your time when you cross the line, whatever happens during the race.

    # Fire the pistol: announce that this stage is beginning.
    _emit("START  %s" % name)
    # Start the stopwatch. `perf_counter` is a very precise timer built for measuring how
    # long things take. It is not a clock for telling the time of day -- its number means
    # nothing on its own, and is only useful when you subtract two readings.
    t = time.perf_counter()
    try:
        # `yield` means "pause here and let the other person's work happen now". Everything
        # inside their `with` block runs at this point. When they are finished, we carry on
        # from just after this line.
        yield
    # `finally` means "run the following NO MATTER WHAT" -- whether the work succeeded, or
    # crashed, or was cancelled. That guarantee is why the DONE line and the timing are
    # never lost, even when the stage fails.
    finally:
        # Announce the finish, with how long it took.
        #   `time.perf_counter() - t` -- read the stopwatch again and subtract the start
        #                                reading, giving the elapsed seconds.
        #   `%.1f`                    -- write that number with exactly one digit after the
        #                                decimal point, so "12.3s" not "12.34827104s".
        _emit("DONE   %s  (%.1fs)" % (name, time.perf_counter() - t))


# `class` means "define a new kind of thing", with its own memory and its own abilities.
# A Ticker is a thing that keeps count during a long repetitive job and pipes up every so
# often to say how far along it is.
class Ticker:
    """Periodic progress inside a long loop."""

    # `__init__` is the set-up recipe, run once when a new Ticker is made. The double
    # underscores mark it as a special name Python recognises. "init" is short for
    # "initialise", meaning "get ready for the first time".
    #   `self`  is the Ticker being built right now -- how it refers to itself.
    #   `name`  what to call this job in the messages.
    #   `total` how many items there are altogether, so we can say "37 out of 500".
    #   `every` how often to speak up. `= 250` means "every 250 items unless told
    #           otherwise" -- often enough to be reassuring, rare enough not to be noise.
    def __init__(self, name: str, total: int, every: int = 250) -> None:
        # Store each piece of information inside this particular Ticker, so it remembers
        # them later. `self.name = name` means "my name is the name I was given".
        self.name = name
        self.total = total
        self.every = every
        # `n` is the running count of how many items we have handled. Everything starts at
        # nothing, so it starts at 0.
        self.n = 0
        # `t0` means "time zero": the stopwatch reading at the moment we began. Later
        # readings get compared against this to work out the speed.
        self.t0 = time.perf_counter()

    # The action you call each time you finish one item. To "tick" is what a counter does.
    # `k: int = 1` means "how many items you just finished", and if you do not say, we
    # assume one. Being able to pass a bigger number is useful when work is done in batches.
    def tick(self, k: int = 1) -> None:
        # `+=` means "add this on to what is already there". So the count grows by k.
        self.n += k
        # Should we speak up this time? Two conditions, and both must hold:
        #   `self.every`            -- is speaking up switched on at all? If `every` were 0,
        #                              this counts as "no" and we stay silent forever.
        #   `self.n % self.every == 0` -- the `%` is "remainder after dividing". If dividing
        #                              the count by 250 leaves nothing over, then the count
        #                              is exactly 250, or 500, or 750... which is precisely
        #                              when we want to speak.
        if self.every and self.n % self.every == 0:
            # `el` is short for "elapsed": how many seconds since we started.
            el = time.perf_counter() - self.t0
            # Speed = how many done, divided by how long it took.
            # The `if el > 0 else 0.0` guard exists because dividing by zero is impossible.
            # On a very fast computer the first tick can arrive before the timer has moved
            # at all, so we say the speed is 0.0 rather than crashing.
            rate = self.n / el if el > 0 else 0.0
            # ETA means "estimated time of arrival": a guess at how many seconds are left.
            # How many are still to do, divided by how fast we are getting through them.
            # If the speed is 0 we genuinely cannot guess, so we say NaN ("Not a Number"),
            # which is the honest answer -- better than inventing a comforting fake number.
            eta = (self.total - self.n) / rate if rate > 0 else float("nan")
            # Say the progress line. The gaps get filled in order:
            #   `%s`   the job's name
            #   `%d`   the count so far, as a whole number
            #   `%d`   the total, as a whole number
            #   `%.1f` the speed, to one decimal place, e.g. "83.4/s"
            #   `%.0f` the seconds remaining, rounded to no decimal places -- there is no
            #          point being precise about a guess.
            _emit("  %s %d/%d  %.1f/s  eta %.0fs"
                  % (self.name, self.n, self.total, rate, eta))
