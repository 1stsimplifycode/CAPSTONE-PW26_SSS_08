"""Temporal integrity-risk state machine (spec sections 6, 8).

Turns a risk score series into a state trajectory and a risk window
:math:`W_e = [t_{entry}, t_{exit}]`.

Three design decisions, all of which change the numbers and are therefore stated:

**Hysteresis.** Entry needs the score above ``enter_threshold`` for ``enter_persistence``
consecutive sessions; exit needs it below ``exit_threshold`` for ``exit_persistence``.
Separate thresholds with ``exit < enter`` prevent the chattering that a single threshold
produces on a noisy score, and the persistence requirement is what makes ``t_entry`` an
*evidence-supported emergence point* rather than the first noisy crossing.

**Escalation is measured on the trend, not the level.** ESCALATING requires the score to
be rising; PEAK is the local maximum of the episode; RESOLVING requires a sustained fall.
A model that simply sits at a high level therefore reports ACTIVE, never PEAK -- which is
the honest reading.

**Unresolved is a state.** An episode whose score never falls back below the exit
threshold before the series ends is reported ``t_exit = None`` and censored, not silently
closed at the last observation. Premature and delayed resolution are then measurable
(spec section 8).

Thresholds are *detector* parameters. They are selected on the training split only and
frozen before the holdout, which leakage test L6 verifies.

PLAIN ENGLISH -- what this whole file is about:

This file turns a WIGGLY LINE into a STORY.

What comes in is one number per day, saying how worried we are about a company. It
wiggles about: 0.3, 0.4, 0.61, 0.58, 0.7, 0.4, 0.2 ...

What comes out is a story with named chapters: "nothing much... a first warning...
trouble starting... getting worse... THE WORST POINT... calming down... over."

Three clever ideas make this work, and each one is explained because each one changes
the answers.

IDEA 1: HYSTERESIS (a thermostat's trick).
Think of the heating in your house. If it switched on at exactly 20 degrees and off at
exactly 20 degrees, then at 20 degrees it would flick on-off-on-off-on-off all day long,
because the temperature always wobbles a tiny bit. That is called "chattering", and it
is maddening.
The fix every thermostat uses: switch ON at 19 degrees but OFF at 21. Now a little
wobble cannot flip it, because it would have to travel two whole degrees.
This file does exactly that. Trouble STARTS at 0.55 but only ENDS below 0.40. And on top
of that, it must stay there for several days in a row. So one jumpy day cannot declare a
crisis, and one calm day cannot declare it over.

IDEA 2: JUDGE THE TREND, NOT THE HEIGHT.
"Getting worse" is not the same as "being bad". A company can sit at a steadily high 0.7
for months -- that is bad, but it is not getting worse. So ESCALATING requires the number
to actually be RISING, and the PEAK is the single highest point of the whole episode, not
every point that happens to be high. A flat-but-high model therefore never gets to claim
a dramatic peak, which is the honest reading.

IDEA 3: "IT NEVER ENDED" IS A REAL ANSWER.
Suppose our data stops in March but a company's trouble is still going strong. The easy
thing would be to write "it ended in March". That is a lie -- it did not end, we merely
stopped watching. So instead this records "still going, we do not know the end", and
marks it CENSORED. That word comes from medical research, where a patient is still alive
when the study finishes: you must not write down that they died on the last day.

The final note means the thresholds (0.55, 0.40 and so on) are chosen using only the
practice data, and then FROZEN before the real test -- like sealing your answers in an
envelope before seeing the exam paper. Adjusting them after seeing the test would be
marking your own homework, and test L6 exists to catch anyone who does.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types with smarter defaults.
from dataclasses import dataclass, field

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The menu of trouble stages: NORMAL, EARLY_WARNING, EMERGING, and so on.
from research.core.contracts import RiskState

# A label for this version of the rules, written into results so old and new runs stay
# distinguishable.
STATE_VERSION = "state-machine-v1"


# Frozen: the settings must not change halfway through reading a series, or the earlier
# part of the story would be told under different rules from the later part.
@dataclass(frozen=True)
class StateConfig:
    # Go above this to start counting towards "trouble". Just over half.
    enter_threshold: float = 0.55
    # Go below this to start counting towards "over". Note it is LOWER than the entry
    # threshold -- that gap is the thermostat trick from idea 1.
    exit_threshold: float = 0.40
    # A quieter level. Crossing this is not trouble, but it is worth mentioning -- a raised
    # eyebrow rather than an alarm.
    early_warning_threshold: float = 0.45
    # How many days in a row above the entry level before we declare trouble. Two, so a
    # single odd day cannot do it.
    enter_persistence: int = 2
    # How many days in a row below the exit level before we declare it over. Three -- more
    # than the two needed to start, because it is worse to say "all clear" too early than to
    # say "trouble" too early.
    exit_persistence: int = 3
    # How many days to look back over when asking "is this rising or falling?".
    escalation_window: int = 3
    #: Minimum rise over ``escalation_window`` sessions to call ESCALATING.
    # A rise of 0.02 over three days. Anything smaller is treated as noise rather than a
    # trend, so we do not cry "escalating" over a wobble.
    escalation_slope: float = 0.02
    # How far above the entry threshold the highest point must be before it earns the name
    # PEAK. Stops a barely-over-the-line episode from claiming a dramatic summit.
    peak_margin: float = 0.02


@dataclass
# One complete episode of trouble, from beginning to end.
class RiskWindow:
    # Which company.
    symbol: str
    # When the trouble began.
    t_entry: pd.Timestamp
    # When it ended -- or None if it never did before our data ran out.
    t_exit: pd.Timestamp | None
    # When it was at its worst.
    t_peak: pd.Timestamp
    # How bad it got at that worst moment.
    peak_score: float
    # True when the episode was still going when we stopped watching. This is the honest
    # "we do not know how it ended" flag from idea 3.
    censored: bool
    # How many trading days the episode lasted (as far as we saw).
    n_sessions: int
    # The full list of stage names, day by day -- the story itself.
    states: list[str] = field(default_factory=list)

    # How long did it last?
    def duration(self) -> int | None:
        # If it never finished, the honest answer is "unknown", not the length we happened
        # to observe. Reporting the observed length would systematically make unfinished
        # episodes look shorter than they really were -- and since the worst episodes are
        # exactly the ones still running at the end, that would flatter the results.
        return None if self.t_exit is None else self.n_sessions


# THE MAIN ACTION: read the wiggly line and name each day's chapter.
def label_states(dates: pd.Series, score: np.ndarray,
                 # `cfg: StateConfig = StateConfig()` means "if you do not hand me settings,
                 # use a standard set". That is safe here only because the settings record is
                 # frozen and can never be modified.
                 cfg: StateConfig = StateConfig()) -> list[str]:
    """Assign one :class:`RiskState` per session."""
    # How many days are we looking at?
    n = len(score)
    # Start by assuming every day is ordinary. `[x] * n` makes a list of n copies.
    states = [RiskState.NORMAL.value] * n
    # No days at all? Hand back the empty list rather than crashing on the maths below.
    if n == 0:
        return states

    # Work out the trend: how much has the score changed over the last three days?
    # Start with zero everywhere.
    slope = np.full(n, 0.0)
    w = cfg.escalation_window
    # Only if we have more days than the window; otherwise there is nothing to compare
    # against and the trend stays zero.
    if n > w:
        # `score[w:]` is every day from the fourth onwards; `score[:-w]` is every day up to
        # three from the end. Subtracting them pairs each day with the day three before it,
        # for the whole series at once. The first three days keep a slope of zero, which is
        # correct -- there is no earlier day to compare them with.
        slope[w:] = score[w:] - score[:-w]

    # Are we currently inside an episode of trouble?
    inside = False
    # Counters for consecutive days above the entry level and below the exit level.
    run_hi = run_lo = 0
    # Where the current episode began. None means "not in one".
    entry_i = None
    # Walk through the days one at a time.
    for i in range(n):
        # Today's score.
        s = score[i]
        # CASE A: we are not currently in trouble, so we are watching for it to start.
        if not inside:
            # Count up if today is high, and reset to zero the moment it is not. That reset
            # is what makes it "consecutive days" rather than "days in total".
            run_hi = run_hi + 1 if s >= cfg.enter_threshold else 0
            # Have we now had enough high days in a row?
            if run_hi >= cfg.enter_persistence:
                inside = True
                # Backdate the start. This is important and easy to get wrong: the trouble
                # did not begin today, when we finally became convinced -- it began on the
                # FIRST of the run of high days. Stepping back marks the real beginning
                # rather than the moment our rule happened to notice.
                entry_i = i - cfg.enter_persistence + 1
                run_lo = 0
                # Label those backdated days as EMERGING -- trouble taking shape.
                for j in range(entry_i, i + 1):
                    states[j] = RiskState.EMERGING.value
            # Not enough for trouble, but is it above the quieter level?
            elif s >= cfg.early_warning_threshold:
                states[i] = RiskState.EARLY_WARNING.value
            # Otherwise the day stays NORMAL, as it was set at the start.
        # CASE B: we are inside an episode, so we are watching for it to end.
        else:
            # Count consecutive low days, resetting on any day that is not low.
            run_lo = run_lo + 1 if s <= cfg.exit_threshold else 0
            # Enough low days in a row to call it over?
            if run_lo >= cfg.exit_persistence:
                inside = False
                # The days during the fall get labelled RESOLVING -- getting better.
                for j in range(i - cfg.exit_persistence + 1, i):
                    states[j] = RiskState.RESOLVING.value
                # And today, when the fall is confirmed, is RESOLVED -- over.
                states[i] = RiskState.RESOLVED.value
                entry_i = None
                run_hi = 0
                # `continue` skips the rest of this day's checks and moves on, since a day
                # that is over cannot also be escalating.
                continue
            # Still in trouble. Which way is it heading? This is idea 2 in action.
            # Rising fast enough: getting worse.
            if slope[i] >= cfg.escalation_slope:
                states[i] = RiskState.ESCALATING.value
            # Falling fast enough: getting better. (`-cfg.escalation_slope` is the same size
            # of move in the downward direction.)
            elif slope[i] <= -cfg.escalation_slope:
                states[i] = RiskState.RESOLVING.value
            # Neither: bad, but steady.
            else:
                states[i] = RiskState.ACTIVE.value

    # PEAK is assigned last, per contiguous elevated run, so it is unique and truly the
    # maximum rather than every point above a threshold.
    # PLAIN ENGLISH: this second pass exists because you cannot know which day was the worst
    # until you have seen the whole episode. Doing it in the loop above would mean labelling
    # a day PEAK and then having to take it back when a worse day turned up. So we wait,
    # then walk through each episode once and crown exactly one winner.
    i = 0
    while i < n:
        # Skip the calm days.
        if states[i] in (RiskState.NORMAL.value, RiskState.RESOLVED.value):
            i += 1
            continue
        # Found the start of an episode. Now walk forward to find where it ends.
        j = i
        while j + 1 < n and states[j + 1] not in (RiskState.NORMAL.value,
                                                  RiskState.RESOLVED.value):
            j += 1
        # Take this episode's stretch of scores. `j + 1` because a slice stops just before
        # its end point, and we want day j included.
        seg = score[i:j + 1]
        # `np.argmax` gives the POSITION of the biggest value, not the value itself -- which
        # is what we need, since we want to label that particular day.
        k = int(np.argmax(seg))
        # Only crown it if it was clearly high, not merely the tallest of a low bunch.
        if seg[k] >= cfg.enter_threshold + cfg.peak_margin:
            # `i + k` converts the position within this episode back into a position in the
            # whole series.
            states[i + k] = RiskState.PEAK.value
        # Jump past this episode and carry on looking.
        i = j + 1
    return states


# Turn the day-by-day story into a list of complete episodes.
def extract_windows(dates: pd.Series, score: np.ndarray, symbol: str,
                    cfg: StateConfig = StateConfig()) -> list[RiskWindow]:
    # First get the day-by-day labels.
    states = label_states(dates, score, cfg)
    # Rebuild the dates as a clean, freshly numbered series. Going out to a plain numpy array
    # and back is a way of guaranteeing we are not carrying along some odd leftover row
    # numbering from the caller, which would make the position lookups below wrong.
    dates = pd.Series(pd.to_datetime(pd.Series(dates).to_numpy())).reset_index(drop=True)
    out: list[RiskWindow] = []
    i = 0
    n = len(states)
    while i < n:
        # Skip days that are not part of an episode. Note EARLY_WARNING is skipped here,
        # unlike in the peak pass above: a raised eyebrow on its own is not an episode, so it
        # must not be allowed to start one.
        if states[i] in (RiskState.NORMAL.value, RiskState.RESOLVED.value,
                         RiskState.EARLY_WARNING.value):
            i += 1
            continue
        # Found an episode start; walk forward to its end.
        j = i
        while j + 1 < n and states[j + 1] not in (RiskState.NORMAL.value,
                                                  RiskState.RESOLVED.value):
            j += 1
        seg = score[i:j + 1]
        # Which day within the episode was worst.
        k = int(np.argmax(seg))
        # Censored when the run reaches the end of the series without a RESOLVED marker.
        # PLAIN ENGLISH: two ways this episode might not have properly finished --
        #   `j + 1 >= n`                              we ran out of data, or
        #   `states[j + 1] != RESOLVED`               the next day is not a clean ending.
        # Either way we do not know how it really ended, and we say so instead of pretending.
        censored = (j + 1 >= n) or (states[j + 1] != RiskState.RESOLVED.value)
        out.append(RiskWindow(
            symbol=symbol, t_entry=dates.iloc[i],
            # No end date at all when censored -- an honest blank rather than the last day
            # we happened to see.
            t_exit=None if censored else dates.iloc[min(j + 1, n - 1)],
            # When it was worst, and how bad.
            t_peak=dates.iloc[i + k], peak_score=float(seg[k]), censored=censored,
            # How many days it ran, and the story day by day.
            n_sessions=j - i + 1, states=states[i:j + 1]))
        # Jump past this episode.
        i = j + 1
    return out


# Add a "which stage" column to a whole table of many companies.
def apply_to_frame(df: pd.DataFrame, score_col: str = "integrity_risk",
                   cfg: StateConfig = StateConfig()) -> pd.DataFrame:
    """Add ``risk_state`` per row, computed per symbol in date order."""
    out = []
    # One company at a time, in date order. Doing it per company is essential: one firm's
    # trouble must never be allowed to run into the next firm's history and be read as a
    # continuing episode.
    for _sym, g in df.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        # Work on our own copy, so we never modify the caller's table behind their back.
        g = g.copy()
        # `.to_numpy(float)` hands the scores over as a plain row of decimals, which is what
        # the maths above expects.
        g["risk_state"] = label_states(g["date"], g[score_col].to_numpy(float), cfg)
        out.append(g)
    # Glue the per-company pieces back together and restore the caller's original row order.
    # If there was nothing at all, hand back the table with an empty column added, so the
    # shape is still what the caller expects rather than a crash.
    return pd.concat(out).sort_index() if out else df.assign(risk_state=[])


# Pull every episode, for every company, out of a whole table.
def windows_from_frame(df: pd.DataFrame, score_col: str = "integrity_risk",
                       cfg: StateConfig = StateConfig()) -> list[RiskWindow]:
    wins: list[RiskWindow] = []
    # Again one company at a time, in date order.
    for sym, g in df.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        # `.extend` adds all of that company's episodes to the growing list (as opposed to
        # `.append`, which would add the list itself as a single lumpy item).
        wins.extend(extract_windows(g["date"], g[score_col].to_numpy(float), sym, cfg))
    return wins
