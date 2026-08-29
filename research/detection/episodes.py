"""Synthetic integrity-risk episodes injected into real market data (spec section 31).

Why this exists: no open, labelled corpus of NSE market-integrity incidents was found
(limitation L-04), and inventing incident labels for real companies would be both
fabrication and defamation. The alternative adopted here is to inject *known* episodes
into the real panel and evaluate recovery of what was injected. Every number produced
this way is a statement about the detector's behaviour on injected episodes, never a
claim about real-world manipulation.

Generator/detector separation is structural, not a promise:

* :class:`GeneratorConfig` holds every parameter used to *create* episodes. No module
  under ``research/models`` or ``research/detection/state.py`` imports it, and
  ``tests/property/test_invariants.py`` asserts that.
* Train and test episodes are drawn from disjoint seeds *and* disjoint instrument sets,
  so a detector cannot memorise which symbols carry episodes.

Injection acts on the raw panel -- prices, volumes, trade counts -- and features are
recomputed afterwards. The detector therefore sees only data, exactly as it would in
production, and cannot read an injection flag by accident.

PLAIN ENGLISH -- what this whole file is about:

THE PROBLEM: how do you test a smoke alarm without burning down a house?

We want to build something that spots companies behaving suspiciously. To check whether
it works, we need examples where we KNOW the right answer. But:

  * Nobody publishes a free, reliable list saying "these Indian companies were up to no
    good on these dates."
  * And we absolutely must not make one up. Writing "Company X was manipulating its
    share price in March 2019" when we do not know that is two separate disasters: it is
    inventing evidence, and it is defamation -- publicly accusing a real business of a
    crime it may not have committed.

THE SOLUTION: take REAL market data, and carefully paint FAKE trouble onto it.

Because we painted it ourselves, we know exactly where it is. Then we hide the answers
and see whether the detector can find them. It is a smoke machine, not a real fire.

AND THE PROMISE THAT COMES WITH IT: every number this produces means "the detector found
X% of the trouble WE PAINTED IN". It never means "X% of real market manipulation". Those
are completely different claims, and the file says so repeatedly so that no reader can
mistake one for the other.

TWO WAYS WE STOP OURSELVES CHEATING:

1. The settings used to PAINT the trouble are kept in a locked box that the DETECTOR
   code is forbidden to open. If the detector could peek at "peak intensity is 0.7", it
   would not be detecting anything -- it would be reading the answer sheet. And this is
   not merely a promise written in a comment: there is an automatic test that fails the
   build if any detector file ever tries to import that box.

2. Practice companies and test companies are kept completely separate. Otherwise a model
   could learn something useless like "Reliance always has episodes in this dataset"
   rather than "this shape means trouble". It would score beautifully and know nothing.

Finally: we paint the trouble onto the RAW data -- the prices and volumes -- and then
let all the measurements be recalculated from scratch afterwards. That way the detector
sees only ordinary market data, exactly as it would in real life. There is no hidden
"this one is fake" flag anywhere for it to accidentally find.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# A type hint for "an ordered collection you can walk through and count".
from collections.abc import Sequence
# Record-building tools. `replace` makes a copy of a record with one slot changed.
from dataclasses import dataclass, field, replace
# For describing a country's clock offset.
from datetime import timedelta, timezone

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# The menu of trouble stages.
from research.core.contracts import RiskState

# India Standard Time: five and a half hours ahead of the world clock.
_IST = timezone(timedelta(hours=5, minutes=30))

# A label for this version of the painting recipe.
GENERATOR_VERSION = "episodes-v1"

#: Phase order and the state each phase maps to. Not every episode uses every phase.
# PLAIN ENGLISH: the script for how an episode of trouble unfolds, in order. Each entry
# pairs our internal name for the phase with the official stage name from the menu.
# "Not every episode uses every phase" because some never resolve -- see censoring below.
PHASES = [
    # The first faint hint.
    ("early_warning", RiskState.EARLY_WARNING),
    # Something is taking shape.
    ("emerging", RiskState.EMERGING),
    # It is definitely happening.
    ("active", RiskState.ACTIVE),
    # It is getting worse.
    ("escalating", RiskState.ESCALATING),
    # The worst of it.
    ("peak", RiskState.PEAK),
    # Calming down.
    ("resolving", RiskState.RESOLVING),
]


# Frozen: these settings must not change while episodes are being made, or different
# episodes in one run would have been painted under different rules.
@dataclass(frozen=True)
class GeneratorConfig:
    """Parameters of the *data-generating process*. Never visible to a detector."""
    # PLAIN ENGLISH: THIS IS THE LOCKED BOX. Everything in here is the answer sheet. The
    # detector must never see any of it, and an automatic test enforces that.

    # How many episodes to paint in.
    n_episodes: int = 120
    #: Mean phase lengths in trading sessions. Actual lengths are Poisson-jittered.
    # PLAIN ENGLISH: roughly how many days each phase should last. "Poisson-jittered" means
    # the real length is drawn at random around that average, so episodes are not all
    # identical. If every episode were exactly 4-5-6-4-3-6 days, a detector could learn that
    # rhythm and score brilliantly without understanding anything at all.
    # (Poisson is the pattern of counting random events that happen at a steady average
    # rate -- how many buses arrive in an hour, or raindrops in a second.)
    phase_days: dict[str, int] = field(default_factory=lambda: {
        "early_warning": 4, "emerging": 5, "active": 6, "escalating": 4,
        "peak": 3, "resolving": 6})
    #: Peak intensity is drawn from a Beta so most episodes are subtle and a few severe.
    # PLAIN ENGLISH: how bad each episode gets is drawn at random from a lopsided shape
    # ("Beta") that produces lots of mild cases and only a few dramatic ones -- which is how
    # trouble actually arrives in the world. Making them all severe would be much easier to
    # detect and would flatter the results enormously.
    intensity_a: float = 2.0
    intensity_b: float = 3.0
    # But never below this, or the episode would be so faint that nothing could possibly
    # find it, and it would only serve to make the score look worse for no useful reason.
    intensity_floor: float = 0.25
    #: Return drift injected at peak intensity, in units of the symbol's own daily vol.
    # PLAIN ENGLISH: how hard to push the price. Crucially it is measured in units of THAT
    # COMPANY'S OWN normal jumpiness. A push that is dramatic for a sleepy utility would be
    # invisible in a wild tech stock, so a fixed push would mean completely different things
    # in different companies. Scaling by each one's own behaviour makes it mean one thing.
    return_kappa: float = 0.55
    #: Multiplicative volume/turnover inflation at peak intensity.
    # How much extra trading activity to paint in. 1.60 means up to 160% more than usual.
    volume_kappa: float = 1.60
    #: Trade-count inflation; deliberately smaller than volume, so average trade size
    #: rises -- the microstructure proxies must have something real to detect.
    # PLAIN ENGLISH: a genuinely clever touch. The AMOUNT traded goes up a lot (1.60), but
    # the NUMBER of separate trades goes up less (0.75). Divide one by the other and each
    # individual trade is bigger than usual -- which is exactly the fingerprint of a few
    # large players moving in, rather than lots of ordinary people. Without this asymmetry
    # the fine-grained measurements would have nothing real to find, and any success they
    # showed would be an illusion.
    trades_kappa: float = 0.75
    #: Fraction of episodes that never resolve inside the window (censored).
    # About one in seven never finishes, because in real life plenty of situations are still
    # unfolding when you stop looking. A test set where everything tidily concludes would be
    # unrealistically easy.
    censored_fraction: float = 0.15
    # The starting point for all the randomness, so the identical set of episodes can be
    # painted again exactly.
    seed: int = 20260818


@dataclass
# One painted episode.
class Episode:
    # A unique name for it.
    episode_id: str
    # Which company it was painted onto.
    symbol: str
    # When it starts.
    t_entry: pd.Timestamp
    t_exit: pd.Timestamp | None          # None = censored / unresolved
    # PLAIN ENGLISH: no end date means it was still going when the data ran out.
    # When it is at its worst.
    t_peak: pd.Timestamp
    # How bad it gets at that worst point.
    peak_intensity: float
    # Whether it never finished.
    censored: bool
    schedule: pd.DataFrame               # date, state, intensity
    # The day-by-day plan: which date, which stage, and how strongly to paint it.


# A private helper: write the day-by-day plan for one episode.
def _phase_schedule(rng: np.random.Generator, cfg: GeneratorConfig,
                    sessions: Sequence[pd.Timestamp], start_idx: int,
                    peak_intensity: float, censored: bool
                    ) -> tuple[pd.DataFrame, int]:
    rows = []
    # Where in the company's calendar to begin.
    i = start_idx
    # Intensity ramps to the peak phase then decays through resolving.
    # PLAIN ENGLISH: what fraction of full strength each phase gets. It climbs 0.25, 0.45,
    # 0.70, 0.88, up to 1.00 at the peak, then drops back to 0.45 while resolving. That
    # rise-and-fall is what makes it look like a real developing situation rather than a
    # block of trouble switched on and off.
    ramp = {"early_warning": 0.25, "emerging": 0.45, "active": 0.70,
            "escalating": 0.88, "peak": 1.00, "resolving": 0.45}
    # Walk through the phases in order.
    for name, state in PHASES:
        # If this episode is meant never to finish, stop before the recovery phase -- which
        # is precisely what "never resolved" means.
        if censored and name == "resolving":
            break
        # The average length of this phase.
        mean = cfg.phase_days[name]
        # Draw the actual length at random around that average. `max(1, ...)` guarantees at
        # least one day, since a random draw can legitimately come out as zero and a
        # zero-day phase would simply vanish.
        n = max(1, int(rng.poisson(mean)))
        # Write one row per day of this phase. The underscore for the loop variable is the
        # usual signal for "we are just counting; the number itself is not used".
        for _ in range(n):
            # Ran out of calendar? Stop.
            if i >= len(sessions):
                break
            rows.append({"date": sessions[i], "state": state.value,
                         # Full strength scaled down by this phase's position on the ramp.
                         "intensity": peak_intensity * ramp[name], "phase": name})
            i += 1
        # Check again after the inner loop, so we escape the outer one too rather than
        # pointlessly starting another phase with no days left to put it in.
        if i >= len(sessions):
            break
    # Hand back the plan and where in the calendar we finished.
    return pd.DataFrame(rows), i


# Decide what episodes to paint -- but do not paint them yet.
def generate(panel: pd.DataFrame, universe_symbols: Sequence[str],
             cfg: GeneratorConfig) -> list[Episode]:
    """Draw episode specifications. Does not touch the panel."""
    # PLAIN ENGLISH: planning and painting are kept as two separate steps. That means the
    # plans can be inspected, saved and reasoned about on their own, and the same plan can be
    # applied to different versions of the data.

    # Start the randomness from the fixed seed.
    rng = np.random.default_rng(cfg.seed)
    # Every trading day in the data, in order.
    sessions = np.sort(panel["date"].unique())
    sessions = [pd.Timestamp(s) for s in sessions]
    # How many days of data each company has.
    counts = panel.groupby("symbol")["date"].count()
    # Only use companies with a good long history -- more than 400 trading days, roughly a
    # year and a half. A short history leaves no room for the run-up and the aftermath.
    eligible = [s for s in universe_symbols if counts.get(s, 0) > 400]
    # Nobody qualifies? Stop, rather than quietly producing zero episodes and letting the
    # rest of the pipeline report a meaningless perfect score on an empty test.
    if not eligible:
        raise ValueError("no eligible symbols with sufficient history")

    episodes: list[Episode] = []
    # Plan each episode in turn.
    for e in range(cfg.n_episodes):
        # Pick a company at random.
        sym = str(rng.choice(eligible))
        # Get that company's trading days, in order.
        sym_dates = sorted(panel.loc[panel["symbol"] == sym, "date"].unique())
        sym_dates = [pd.Timestamp(d) for d in sym_dates]
        # A second, stricter history check for this particular company.
        if len(sym_dates) < 300:
            continue
        # Leave room before (feature warm-up) and after (resolution) the episode.
        # PLAIN ENGLISH: do not start an episode in the first 150 days, because the
        # measurements need a run-up before they mean anything. And do not start one in the
        # last 60, or there would be no room for it to play out. `lo` and `hi` are the
        # earliest and latest allowed starting points.
        lo, hi = 150, len(sym_dates) - 60
        # Not enough room between them? Skip this company.
        if hi <= lo:
            continue
        # Pick a starting day at random within the allowed range.
        start = int(rng.integers(lo, hi))
        # Draw how bad this one gets, but never below the floor.
        peak_intensity = max(cfg.intensity_floor,
                             float(rng.beta(cfg.intensity_a, cfg.intensity_b)))
        # Roll a die to decide whether this one never resolves. `rng.random()` gives a number
        # between 0 and 1, so "below 0.15" happens about 15% of the time.
        censored = bool(rng.random() < cfg.censored_fraction)
        # Write the day-by-day plan.
        sched, end = _phase_schedule(rng, cfg, sym_dates, start, peak_intensity,
                                     censored)
        # Empty plan (we ran off the end of the calendar)? Skip it.
        if sched.empty:
            continue
        # Find the peak day.
        peak_rows = sched[sched["phase"] == "peak"]
        # If the plan got cut short before reaching the peak phase, fall back to the last day
        # we did manage to plan -- the worst point we actually have.
        t_peak = (peak_rows["date"].iloc[0] if len(peak_rows)
                  else sched["date"].iloc[-1])
        # Censored episodes get no end date at all -- the honest blank.
        t_exit = None if censored else sched["date"].iloc[-1]
        episodes.append(Episode(
            # `"EP%04d" % e` makes names like EP0000, EP0001 -- padded with zeros so they
            # sort correctly as text, which "EP1, EP2, EP10" would not.
            episode_id="EP%04d" % e, symbol=sym,
            t_entry=sched["date"].iloc[0], t_exit=t_exit, t_peak=t_peak,
            peak_intensity=peak_intensity, censored=censored, schedule=sched))
    return episodes


# NOW paint the planned episodes onto the real data.
def inject(panel: pd.DataFrame, episodes: Sequence[Episode],
           cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply episodes to the raw panel.

    Returns ``(modified_panel, labels)``. The modified panel differs from the original
    only in ``close``/``high``/``low``/``volume``/``turnover``/``trades`` inside episode
    windows. Prices are adjusted multiplicatively by the cumulative injected drift so
    that returns -- not levels -- carry the signal, which keeps the series continuous at
    the episode boundary.
    """
    # PLAIN ENGLISH on that last sentence, which is subtle and important.
    # We could have painted trouble by ADDING to the price: "add 5 rupees each day". But
    # then on the last day of the episode the price would suddenly snap back down, leaving
    # an impossible cliff that no real market ever produces. Any detector would spot that
    # cliff instantly and score brilliantly -- by finding our painting mistake rather than
    # the trouble.
    # Instead we MULTIPLY, and the multiplication carries forward. The price drifts
    # smoothly away and then simply stops drifting further. The line stays continuous, there
    # is no cliff, and the signal lives in the day-to-day CHANGES, which is exactly where
    # real market signals live.

    # Work on a copy, so the caller's original data is never disturbed.
    df = panel.copy()
    # A different random stream from the planning step. `cfg.seed + 1` keeps it reproducible
    # while making sure the painting randomness is not identical to the planning randomness.
    rng = np.random.default_rng(cfg.seed + 1)

    # Volume and trade counts arrive as integers. Injection multiplies them by a
    # continuous factor, so widen first rather than let pandas refuse (or, worse,
    # silently truncate) the assignment.
    # PLAIN ENGLISH: you cannot trade half a share, so those columns hold whole numbers. But
    # multiplying by 1.6 produces decimals. Pandas might then quietly chop the decimal part
    # off, subtly changing what we painted without telling us. Converting to decimals first
    # makes that impossible.
    for col in ("close", "high", "low", "prev_close", "volume", "turnover", "trades"):
        if col in df.columns:
            df[col] = df[col].astype(float)

    # Per-symbol daily volatility, used to scale the injected drift so a 0.55-kappa
    # episode means the same thing in a quiet name and a volatile one.
    # First, the daily return in "log" form: the difference between the logarithm of today's
    # price and of yesterday's. Logs are used because they turn multiplying into adding,
    # which makes a run of daily changes simple to accumulate.
    df["_lr"] = np.log(df["close"]) - np.log(df["prev_close"])
    # Then how much those returns wobble, over a rolling 63-day window (about three months).
    # `min_periods=20` means "produce an answer once there are at least 20 days", so early
    # rows are not left blank unnecessarily but are not computed from three days either.
    vol = df.groupby("symbol")["_lr"].transform(
        lambda s: s.rolling(63, min_periods=20).std())
    # Where the wobble could not be worked out, fall back to the middle value across all
    # companies. A sensible stand-in beats a blank, which would silently skip painting there.
    df["_vol"] = vol.fillna(vol.median())

    # Build a two-part label -- company AND date -- so we can address any single cell of the
    # table directly.
    key = pd.MultiIndex.from_arrays([df["symbol"], df["date"]])
    df = df.set_index(key)

    label_rows = []
    # Paint each episode in turn.
    for ep in episodes:
        sched = ep.schedule
        # Build the (company, date) labels for every day of this episode.
        idx = pd.MultiIndex.from_arrays([[ep.symbol] * len(sched), sched["date"]])
        # Which of those days actually exist in the data? A planned day might be missing if
        # the market was shut.
        present = idx.isin(df.index)
        # None of them present? Skip this episode.
        if not present.any():
            continue
        # Keep only the days that exist, in both the labels and the plan, so the two stay
        # lined up with each other.
        idx = idx[present]
        sched = sched[present]
        # The strength for each day.
        inten = sched["intensity"].to_numpy()
        sign = -1.0 if rng.random() < 0.75 else 1.0   # most integrity events are adverse
        # PLAIN ENGLISH: three times out of four we push the price DOWN, because most
        # integrity problems are bad news. But one time in four we push it UP, because some
        # manipulation is about pumping a price up. If we only ever pushed down, a detector
        # could get away with simply shouting "trouble!" at every price fall, and would look
        # far better than it deserved.

        # That company's own jumpiness on each of those days.
        v = df.loc[idx, "_vol"].to_numpy()
        # The daily push: direction x strength setting x today's intensity x that company's
        # own scale.
        drift = sign * cfg.return_kappa * inten * v
        # Plus some randomness, so the push is not suspiciously smooth. A perfectly straight
        # drift would be trivially easy to spot and utterly unlike a real market.
        noise = rng.normal(0.0, 0.25 * cfg.return_kappa * inten * v)
        # Accumulate the daily pushes into a running total, then undo the logarithm with
        # `np.exp` to get a multiplier. This is the "cumulative multiplicative drift" that
        # keeps the price line continuous.
        cum = np.exp(np.cumsum(drift + noise))

        # Apply that multiplier to the closing, highest and lowest prices of each day.
        for col in ("close", "high", "low"):
            df.loc[idx, col] = df.loc[idx, col].to_numpy() * cum
        # Work out the trading-activity multipliers. `1.0 +` means "normal, plus extra".
        # `np.abs(rng.normal(1.0, 0.3, ...))` adds randomness around 1, and the `abs` keeps
        # it positive so we never accidentally paint in NEGATIVE trading, which is impossible.
        vmul = 1.0 + cfg.volume_kappa * inten * np.abs(rng.normal(1.0, 0.3, len(inten)))
        tmul = 1.0 + cfg.trades_kappa * inten * np.abs(rng.normal(1.0, 0.3, len(inten)))
        # More shares changing hands.
        df.loc[idx, "volume"] = df.loc[idx, "volume"].to_numpy() * vmul
        # More money changing hands -- and note this is multiplied by BOTH the volume rise
        # AND the price change, because turnover is shares times price. Missing that second
        # multiplier would leave the three columns quietly inconsistent with each other.
        df.loc[idx, "turnover"] = df.loc[idx, "turnover"].to_numpy() * vmul * cum
        # More individual trades -- but by a smaller factor, which is the average-trade-size
        # fingerprint described in the settings above.
        df.loc[idx, "trades"] = df.loc[idx, "trades"].to_numpy() * tmul

        # Write down the answer sheet: what we painted, where, and how strongly.
        for (_, r) in sched.iterrows():
            label_rows.append({
                "episode_id": ep.episode_id, "symbol": ep.symbol, "date": r["date"],
                "state": r["state"], "phase": r["phase"],
                "intensity": float(r["intensity"]),
                "peak_intensity": ep.peak_intensity, "censored": ep.censored,
                "t_entry": ep.t_entry, "t_exit": ep.t_exit, "t_peak": ep.t_peak,
            })

    # Put the row numbering back to normal.
    df = df.reset_index(drop=True)
    # Throw away our two working columns. They were scaffolding for the painting, and
    # leaving them in would hand the detector a clue we never meant to give it.
    df = df.drop(columns=["_lr", "_vol"])
    # prev_close must stay consistent with the modified closes, or the injected drift
    # would be visible as an impossible overnight jump.
    # PLAIN ENGLISH: each row records yesterday's closing price as well as today's. We
    # changed today's prices but not yesterday's copies of them, so the two now disagree.
    # A detector comparing them would see impossible overnight gaps -- and would find our
    # painting rather than the trouble. So we rebuild that column from the new prices.
    df = df.sort_values(["symbol", "date"])
    # `.shift(1)` moves each company's closing prices down one row, so every row now carries
    # the previous day's true closing price. `.fillna(...)` keeps the original value for the
    # very first row of each company, which has no previous day to shift from.
    df["prev_close"] = df.groupby("symbol")["close"].shift(1).fillna(df["prev_close"])
    # Turn the answer sheet into a table.
    labels = pd.DataFrame(label_rows)
    # Hand back the painted data and the answers, kept as two separate things so the answers
    # can be locked away while the data is handed to the detector.
    return df.reset_index(drop=True), labels


# Split the episodes into a practice set and a test set -- by COMPANY, not by episode.
def split_by_symbol(episodes: Sequence[Episode], test_fraction: float = 0.35,
                    seed: int = 20260818) -> tuple[list[Episode], list[Episode]]:
    """Disjoint-instrument split.

    Splitting by episode would put the same symbol in train and test, letting a model
    learn "this ticker has episodes" instead of "this pattern is an episode".
    """
    # PLAIN ENGLISH: this is a real and very common mistake, worth being clear about.
    # The obvious approach is to shuffle all 120 episodes and take 35% for testing. But then
    # a company might have two episodes, one in practice and one in the test. The model could
    # then learn "whenever I see Company X, say trouble" -- and be right, and learn precisely
    # nothing about what trouble looks like.
    # Splitting by COMPANY means the test companies were never seen at all during practice,
    # so the only way to do well is to have genuinely learned the pattern.

    rng = np.random.default_rng(seed)
    # Every distinct company that has an episode. Sorted first so the starting order is
    # always the same -- otherwise the shuffle below would give different splits on different
    # runs even with the same seed, and the experiment would not be reproducible.
    syms = sorted({e.symbol for e in episodes})
    # Shuffle them into a random order.
    rng.shuffle(syms)
    # How many companies go into the test set. `max(1, ...)` guarantees at least one, so we
    # never end up with an empty test set that would report a meaningless perfect score.
    n_test = max(1, int(len(syms) * test_fraction))
    # The first slice of the shuffled list becomes the test companies.
    test_syms = set(syms[:n_test])
    # Every episode belonging to a company NOT in that set is for practice...
    train = [e for e in episodes if e.symbol not in test_syms]
    # ...and every episode belonging to one that IS in it is for testing. Because the split
    # is by company, no company can possibly appear in both lists.
    test = [e for e in episodes if e.symbol in test_syms]
    return train, test


# Make a copy of the settings with a different seed.
def with_seed(cfg: GeneratorConfig, seed: int) -> GeneratorConfig:
    # `replace` builds a new record identical to the old one except for the named slot. It is
    # needed because the settings record is frozen and cannot be edited in place -- and this
    # is exactly how the project runs the same experiment under many different random draws
    # to check that a result is not just a lucky one.
    return replace(cfg, seed=seed)
