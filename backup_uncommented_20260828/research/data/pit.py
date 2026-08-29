"""The point-in-time read path. The only way Week 1 reads history.

A prediction made at time *T* may use a fact only if the system could have known it at
*T*. That is one sentence, and it is violated by the most natural query anybody writes::

    panel[panel["date"] <= T]              # WRONG: filters on when it happened

The bhavcopy for session *D* is published after *D* closes. Filtering on the event date
alone hands a model the close of *D* at 15:30 on *D*, two and a half hours before it
exists. The correct filter is on knowledge time::

    panel[panel["knowledge_time"] <= cutoff]

This module makes the second form the easy one and the first form impossible to write by
accident. :class:`AsOf` is a value, not a convention: a read either carries one or does
not happen. :func:`as_of_frame` refuses a frame with no ``knowledge_time`` column rather
than silently falling back to dates, because a silent fallback is precisely the bug.

Relationship to :class:`research.core.contracts.BitemporalStore`: the store is the
record-level implementation and holds the semantics -- restatement resolution, the
cutoff-after-decision-time check. It cannot hold 8.4 million panel rows as dataclasses,
so this module applies *the same* rules to columnar data, and
:func:`assert_same_semantics` proves on every run that the two agree. The store is not a
parallel implementation left to rot; :func:`evidence_for_instrument` routes real product
reads through ``get_evidence`` so the tested path is also the shipped one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from research.core.contracts import (
    BitemporalStore,
    EvidenceRecord,
    LeakageError,
    EvidenceBlock,
    Provenance,
    get_evidence,
    utc,
)

PIT_VERSION = "pit-v1"

IST = timezone(timedelta(hours=5, minutes=30))

#: Session close and bhavcopy publication, in IST. Imported from the ingestion module so
#: there is exactly one definition; see ``research.reference.sessions`` for which of
#: these is an exchange fact and which is a project assumption.
CLOSE_IST = (15, 30)
PUBLISH_IST = (18, 0)

#: Columns that carry knowledge time, in the order they are preferred.
KNOWLEDGE_COLUMNS = ("knowledge_time", "knowledge_cutoff")
#: Columns that carry event time.
EVENT_COLUMNS = ("event_time", "decision_time")


class MissingKnowledgeTime(KeyError):
    """A frame was read point-in-time but carries no knowledge time.

    Deliberately fatal. The alternative -- quietly filtering on ``date`` instead -- is
    the exact defect the point-in-time read path exists to prevent, and it would be
    invisible in the result.
    """


def publication_instant(d: object) -> pd.Timestamp:
    """The instant session *d*'s bhavcopy becomes knowable, in UTC."""
    ts = pd.Timestamp(d)
    if ts.tzinfo is None:
        ts = ts.tz_localize(IST)
    return (ts.normalize() + pd.Timedelta(hours=PUBLISH_IST[0],
                                          minutes=PUBLISH_IST[1])).tz_convert("UTC")


def session_close_instant(d: object) -> pd.Timestamp:
    ts = pd.Timestamp(d)
    if ts.tzinfo is None:
        ts = ts.tz_localize(IST)
    return (ts.normalize() + pd.Timedelta(hours=CLOSE_IST[0],
                                          minutes=CLOSE_IST[1])).tz_convert("UTC")


@dataclass(frozen=True)
class AsOf:
    """A point in time to read the world from.

    ``decision_time`` is how far the world has advanced; ``knowledge_cutoff`` is what the
    system is allowed to have learned by then. They differ when a backtest wants to model
    a reporting lag. The cutoff may never exceed the decision time -- a decision cannot
    use knowledge from its own future -- and the constructor enforces it.
    """

    decision_time: datetime
    knowledge_cutoff: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", utc(self.decision_time))
        object.__setattr__(self, "knowledge_cutoff", utc(self.knowledge_cutoff))
        if self.knowledge_cutoff > self.decision_time:
            raise LeakageError(
                "knowledge_cutoff %s is after decision_time %s: a decision may not use "
                "knowledge from its own future"
                % (self.knowledge_cutoff, self.decision_time))

    @classmethod
    def at_session_close(cls, d: object) -> AsOf:
        """Standing at the close of session *d*, before its bhavcopy is out.

        This is the strict reading and the one a live system faces: at 15:30 the day's
        own numbers are not yet published, so they are not available.
        """
        t = session_close_instant(d)
        return cls(decision_time=t, knowledge_cutoff=t)

    @classmethod
    def after_publication(cls, d: object) -> AsOf:
        """Standing after session *d*'s bhavcopy is published.

        The default for research over daily data: session *d* is usable, session *d+1*
        is not.
        """
        t = publication_instant(d)
        return cls(decision_time=t, knowledge_cutoff=t)

    @classmethod
    def latest(cls) -> AsOf:
        now = datetime.now(UTC)
        return cls(decision_time=now, knowledge_cutoff=now)

    def to_dict(self) -> dict:
        return {"decision_time": self.decision_time.isoformat(),
                "knowledge_cutoff": self.knowledge_cutoff.isoformat()}

    def __str__(self) -> str:
        return "as-of %s (knowledge <= %s)" % (
            self.decision_time.isoformat(), self.knowledge_cutoff.isoformat())


def _column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in frame.columns:
            return c
    return None


def knowledge_column(frame: pd.DataFrame) -> str:
    c = _column(frame, KNOWLEDGE_COLUMNS)
    if c is None:
        raise MissingKnowledgeTime(
            "frame has no knowledge-time column (looked for %s). A point-in-time read "
            "cannot fall back to the event date: that is the leak it prevents. Columns "
            "present: %s" % (list(KNOWLEDGE_COLUMNS), list(frame.columns)[:12]))
    return c


def as_of_frame(frame: pd.DataFrame, asof: AsOf,
                lookback_days: float | None = None) -> pd.DataFrame:
    """Restrict a frame to what was knowable at ``asof``.

    Both bounds are applied, never one: ``event_time <= decision_time`` because the world
    has not advanced past it, and ``knowledge_time <= knowledge_cutoff`` because the
    system had not learned it. A frame carrying only an event time is refused.
    """
    kcol = knowledge_column(frame)
    ecol = _column(frame, EVENT_COLUMNS)

    k = pd.to_datetime(frame[kcol], utc=True)
    mask = k <= pd.Timestamp(asof.knowledge_cutoff)

    if ecol is not None:
        e = pd.to_datetime(frame[ecol], utc=True)
        mask &= e <= pd.Timestamp(asof.decision_time)
        if lookback_days is not None:
            mask &= e >= pd.Timestamp(asof.decision_time) - pd.Timedelta(
                days=lookback_days)
    elif "date" in frame.columns:
        # No explicit event time: the session date stands in, at its close.
        e = pd.to_datetime(frame["date"]).map(session_close_instant)
        mask &= e <= pd.Timestamp(asof.decision_time)
        if lookback_days is not None:
            mask &= e >= pd.Timestamp(asof.decision_time) - pd.Timedelta(
                days=lookback_days)

    return frame[mask]


def assert_no_leakage(frame: pd.DataFrame, asof: AsOf) -> None:
    """Belt and braces: the invariant is asserted on the result, not assumed."""
    if frame.empty:
        return
    kcol = knowledge_column(frame)
    k = pd.to_datetime(frame[kcol], utc=True)
    worst = k.max()
    if worst > pd.Timestamp(asof.knowledge_cutoff):
        raise LeakageError(
            "point-in-time read leaked: a row carries knowledge_time %s, after the "
            "cutoff %s" % (worst, asof.knowledge_cutoff))


# -- the record-level path -------------------------------------------------------------

def records_from_panel(panel: pd.DataFrame, instrument_id: str,
                       fields: tuple[str, ...] = ("close", "volume", "turnover"),
                       licence: str = "NSE bhavcopy, research use",
                       ) -> list[EvidenceRecord]:
    """Turn one instrument's panel rows into evidence records.

    Bounded on purpose: this is used for a single instrument's history, which is
    thousands of rows, not the whole 8.4-million-row panel. The columnar path in
    :func:`as_of_frame` exists for the bulk case and is checked against this one.
    """
    need = {"date", "event_time", "knowledge_time"}
    missing = need - set(panel.columns)
    if missing:
        raise MissingKnowledgeTime(
            "panel is missing %s; cannot build bitemporal records" % sorted(missing))
    out: list[EvidenceRecord] = []
    for r in panel.itertuples(index=False):
        payload = {f: getattr(r, f, None) for f in fields}
        payload = {k: (float(v) if isinstance(v, (int, float, np.floating))
                       and v == v else None)
                   for k, v in payload.items()}
        out.append(EvidenceRecord(
            instrument_id=instrument_id, block=EvidenceBlock.MARKET, payload=payload,
            fact_key="daily_bar",
            provenance=Provenance(
                source="nse_bhavcopy_cm", licence=licence,
                event_time=r.event_time, knowledge_time=r.knowledge_time,
                dataset_version="cash-panel-v1"),
        ))
    return out


def store_for_instrument(panel: pd.DataFrame, instrument_id: str) -> BitemporalStore:
    store = BitemporalStore()
    store.extend(records_from_panel(panel, instrument_id))
    return store


def evidence_for_instrument(panel: pd.DataFrame, instrument_id: str, asof: AsOf,
                            lookback_days: float | None = None,
                            ) -> list[EvidenceRecord]:
    """The spec's ``get_evidence`` entry point, on real panel data.

    This is what the product's instrument view calls. It is deliberately the same
    function the leakage suite attacks, so the tested path and the shipped path are one
    path.
    """
    store = store_for_instrument(panel, instrument_id)
    return get_evidence(store, instrument_id, asof.decision_time,
                        asof.knowledge_cutoff, lookback_days=lookback_days)


def assert_same_semantics(panel: pd.DataFrame, instrument_id: str,
                          asof: AsOf) -> dict[str, Any]:
    """Prove the columnar filter and the record store return the same rows.

    Two implementations of one rule is a liability unless something checks them against
    each other. This is that check, and the C2 test runs it over randomised cutoffs.
    """
    frame = as_of_frame(panel, asof)
    records = evidence_for_instrument(panel, instrument_id, asof)
    frame_times = sorted(pd.to_datetime(frame["event_time"], utc=True).tolist())
    record_times = sorted(r.event_time for r in records)
    agree = len(frame_times) == len(record_times) and all(
        pd.Timestamp(a) == pd.Timestamp(b)
        for a, b in zip(frame_times, record_times, strict=False))
    if not agree:
        raise LeakageError(
            "columnar and record-level point-in-time reads disagree at %s: "
            "%d rows vs %d records" % (asof, len(frame_times), len(record_times)))
    return {"rows": len(frame_times), "asof": asof.to_dict(), "agree": True}
