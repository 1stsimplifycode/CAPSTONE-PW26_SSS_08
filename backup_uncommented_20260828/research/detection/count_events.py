"""Count-based event detection, and its hard dependency on the Week 2 arrival model.

An event here is a session whose trade count is too high to be ordinary. The detector's
whole difficulty is the word "too": it needs an expected count and a width, and the width
is exactly what the Week 2 arrival model measures.

Under a Poisson assumption the band would be::

    upper = lambda + z * sqrt(lambda)

That is what a detector writes when nobody has checked the dispersion. On NSE daily trade
counts the check has now been done (:mod:`research.market.arrival`) and the counts are
overdispersed by orders of magnitude -- the variance is thousands of times the mean, not
equal to it. A Poisson band on this data is narrower than reality by ``sqrt(Fano)``, so it
fires on almost every ordinary session and the detector is useless.

The corrected band widens by exactly that factor::

    upper = lambda + z * sqrt(lambda) * sd_inflation,    sd_inflation = sqrt(Fano)

**The dependency is structural, not decorative.** :class:`CountEventDetector` cannot be
constructed without an :class:`~research.market.arrival.OverdispersionResult`; passing
``None`` raises :class:`MissingWeek2Input`. There is no default, no fallback to Poisson,
and no silent degradation. Disconnect Week 2 and this detector stops working rather than
quietly reverting to a band that does not hold -- which is the difference between a real
dependency and a field that happens to share a name.

The Week 2 result reaches here through a persisted artifact,
``data/reference/week2_overdispersion.json``, written by
``scripts/build_week2_foundation.py`` and loaded by :func:`load_week2_overdispersion`.
Producer, stored result and consumer are three separable pieces, and the integration test
changes the stored value and asserts the detector's band moves.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.core import paths
from research.market.arrival import OverdispersionResult

COUNT_EVENTS_VERSION = "count-events-v1"

#: Where Week 2 publishes its dispersion result for Week 8 to consume.
OVERDISPERSION_ARTIFACT = "week2_overdispersion.json"

#: Band half-width in standard deviations. 3 is the conventional control-chart choice and
#: is stated here rather than tuned.
DEFAULT_Z = 3.0


class MissingWeek2Input(RuntimeError):
    """The detector was asked to run without the Week 2 arrival-dispersion result.

    Deliberately fatal. A Poisson fallback would look like a working detector while
    silently using a band that this repository has *measured* to be wrong by a factor of
    roughly two hundred on NSE daily counts.
    """


def week2_artifact_path(root: Path | None = None) -> Path:
    return (root or paths.REFERENCE) / OVERDISPERSION_ARTIFACT


def save_week2_overdispersion(result: OverdispersionResult,
                              root: Path | None = None) -> Path:
    """Week 2 publishes. Called by the Week 2 build, never by Week 8."""
    p = week2_artifact_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result.to_dict())
    payload["artifact_version"] = COUNT_EVENTS_VERSION
    payload["written_at"] = datetime.now(UTC).isoformat()
    payload["consumed_by"] = "research.detection.count_events.CountEventDetector"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def load_week2_overdispersion(root: Path | None = None) -> OverdispersionResult:
    """Week 8 consumes. Raises when Week 2 has not published."""
    p = week2_artifact_path(root)
    if not p.exists():
        raise MissingWeek2Input(
            "No Week 2 arrival-dispersion result at %s. The count-event detector needs "
            "it to size its alarm band and will not fall back to a Poisson assumption "
            "this repository has measured to be wrong. Run "
            "scripts/build_week2_foundation.py." % p)
    return OverdispersionResult.from_dict(json.loads(p.read_text(encoding="utf-8")))


@dataclass
class CountEventDetector:
    """Flags sessions whose trade count exceeds the dispersion-corrected band."""

    overdispersion: OverdispersionResult
    z: float = DEFAULT_Z

    def __post_init__(self) -> None:
        if self.overdispersion is None:
            raise MissingWeek2Input(
                "CountEventDetector requires a Week 2 OverdispersionResult. Passing "
                "None is not a supported configuration: the band would silently revert "
                "to Poisson.")
        if not isinstance(self.overdispersion, OverdispersionResult):
            raise MissingWeek2Input(
                "overdispersion must be a research.market.arrival.OverdispersionResult, "
                "got %r. A bare number cannot say whether Week 2 ran."
                % type(self.overdispersion).__name__)

    @classmethod
    def from_week2(cls, root: Path | None = None,
                   z: float = DEFAULT_Z) -> CountEventDetector:
        """The wiring the Week 8 stage uses: load what Week 2 published, then detect."""
        return cls(overdispersion=load_week2_overdispersion(root), z=z)

    # -- the band --------------------------------------------------------------------

    @property
    def sd_inflation(self) -> float:
        """The Week 2 correction, read straight off the consumed result."""
        return self.overdispersion.sd_inflation()

    def upper_band(self, baseline: float | np.ndarray) -> np.ndarray:
        """``lambda + z * sqrt(lambda) * sd_inflation``."""
        lam = np.asarray(baseline, dtype=float)
        return lam + self.z * np.sqrt(np.maximum(lam, 0.0)) * self.sd_inflation

    def poisson_band(self, baseline: float | np.ndarray) -> np.ndarray:
        """What the band would have been without Week 2. For comparison only."""
        lam = np.asarray(baseline, dtype=float)
        return lam + self.z * np.sqrt(np.maximum(lam, 0.0))

    # -- detection -------------------------------------------------------------------

    def detect(self, counts: pd.DataFrame, baseline_window: int = 21) -> pd.DataFrame:
        """Flag per (symbol, session) events against a rolling baseline.

        The baseline is a trailing median of the symbol's own counts -- median rather than
        mean so that a previous event does not raise the bar against the next one, and
        strictly trailing so a session never helps predict itself.
        """
        need = {"symbol", "date", "trades"}
        missing = need - set(counts.columns)
        if missing:
            raise KeyError("counts frame is missing %s" % sorted(missing))

        df = counts.sort_values(["symbol", "date"]).copy()
        g = df.groupby("symbol", sort=False)["trades"]
        df["baseline"] = g.transform(
            lambda s: s.shift(1).rolling(baseline_window, min_periods=5).median())

        df["upper_band"] = self.upper_band(df["baseline"].to_numpy())
        df["poisson_upper_band"] = self.poisson_band(df["baseline"].to_numpy())
        df["count_event"] = df["trades"] > df["upper_band"]
        df["count_event_poisson_only"] = df["trades"] > df["poisson_upper_band"]
        df["sd_inflation_applied"] = self.sd_inflation
        return df

    def to_dict(self) -> dict:
        return {
            "count_events_version": COUNT_EVENTS_VERSION,
            "z": self.z,
            "band": "lambda + z * sqrt(lambda) * sd_inflation",
            "sd_inflation": self.sd_inflation,
            "week2_input": {
                "fano_factor": self.overdispersion.fano_factor,
                "overdispersed": self.overdispersion.overdispersed,
                "model_selected": self.overdispersion.model_selected,
                "source": self.overdispersion.source,
                "computed_at": self.overdispersion.computed_at,
                "basis": self.overdispersion.basis,
            },
            "dependency": (
                "research.market.arrival -> data/reference/week2_overdispersion.json -> "
                "this detector. Constructing without the Week 2 result raises "
                "MissingWeek2Input; there is no Poisson fallback."),
        }


def summary(detected: pd.DataFrame, detector: CountEventDetector) -> dict:
    ev = int(detected["count_event"].sum())
    pois = int(detected["count_event_poisson_only"].sum())
    scored = int(detected["baseline"].notna().sum())
    return {
        "count_events_version": COUNT_EVENTS_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "rows_scored": scored,
        "events_detected": ev,
        "event_rate": float(ev / scored) if scored else None,
        "events_a_poisson_detector_would_have_raised": pois,
        "poisson_event_rate": float(pois / scored) if scored else None,
        "false_alarm_reduction": (
            float(1.0 - ev / pois) if pois else None),
        "detector": detector.to_dict(),
        "interpretation": (
            "The Poisson band would have called %d of %d scored sessions an event. "
            "Widening it by the Week 2 dispersion factor of %.1f leaves %d. The "
            "difference is the Week 2 result doing work."
            % (pois, scored, detector.sd_inflation, ev)),
    }
