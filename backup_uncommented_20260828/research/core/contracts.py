"""Data contracts for AEGIS-Market.

Everything that enters the system is an :class:`EvidenceRecord` carrying a
:class:`Provenance` stamp. The stamp is what makes point-in-time correctness checkable
rather than merely intended (spec sections 25-27).

Four timestamps, and the distinction between them is the whole point:

``event_time``        when the thing described actually happened
``publication_time``  when a publisher first made it public
``knowledge_time``    when *this system* could first have acted on this exact value
``retrieval_time``    when we fetched it

A restatement shares ``event_time`` with the value it restates but carries a later
``knowledge_time``. A query as of an earlier cutoff must return the original value, not
the restatement -- that is leakage test L3.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EvidenceBlock(StrEnum):
    """Which evidence block a recorded fact belongs to. One value per feature block."""

    MARKET = "MARKET"
    FUNDAMENTALS = "FUNDAMENTALS"
    MICROSTRUCTURE = "MICROSTRUCTURE"
    REGIME = "REGIME"
    PROPAGATION = "PROPAGATION"


#: Blocks subject to the licence gate, i.e. those redistributed under terms that the
#: gate must check before a payload leaves the process.
GATED_BLOCKS = frozenset({EvidenceBlock.FUNDAMENTALS})


class RiskState(StrEnum):
    """Temporal integrity-risk states (spec section 6).

    Ordered by escalation level; not every episode visits every state.
    """
    NORMAL = "NORMAL"
    EARLY_WARNING = "EARLY_WARNING"
    EMERGING = "EMERGING"
    ACTIVE = "ACTIVE"
    ESCALATING = "ESCALATING"
    PEAK = "PEAK"
    RESOLVING = "RESOLVING"
    RESOLVED = "RESOLVED"

    @property
    def level(self) -> int:
        return _STATE_LEVEL[self]

    @property
    def is_elevated(self) -> bool:
        """True for states that count as inside a risk window."""
        return self in _ELEVATED


_STATE_LEVEL = {
    RiskState.NORMAL: 0,
    RiskState.EARLY_WARNING: 1,
    RiskState.EMERGING: 2,
    RiskState.ACTIVE: 3,
    RiskState.ESCALATING: 4,
    RiskState.PEAK: 5,
    RiskState.RESOLVING: 2,   # de-escalating but still inside the window
    RiskState.RESOLVED: 0,
}

_ELEVATED = frozenset({
    RiskState.EARLY_WARNING, RiskState.EMERGING, RiskState.ACTIVE,
    RiskState.ESCALATING, RiskState.PEAK, RiskState.RESOLVING,
})


class LeakageError(RuntimeError):
    """A point-in-time violation. Always fatal -- never downgraded to a warning."""


def utc(ts: datetime | str) -> datetime:
    """Normalise to timezone-aware UTC. Naive input is *assumed* UTC and marked so."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


@dataclass(frozen=True)
class Provenance:
    source: str
    licence: str
    event_time: datetime
    knowledge_time: datetime
    publication_time: datetime | None = None
    retrieval_time: datetime | None = None
    dataset_version: str = "unversioned"
    content_hash: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", utc(self.event_time))
        object.__setattr__(self, "knowledge_time", utc(self.knowledge_time))
        if self.publication_time is not None:
            object.__setattr__(self, "publication_time", utc(self.publication_time))
        if self.retrieval_time is not None:
            object.__setattr__(self, "retrieval_time", utc(self.retrieval_time))
        if self.knowledge_time < self.event_time:
            raise LeakageError(
                "knowledge_time %s precedes event_time %s for source %r: the system "
                "cannot know a fact before it happens"
                % (self.knowledge_time, self.event_time, self.source)
            )

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("event_time", "knowledge_time", "publication_time", "retrieval_time"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return d


@dataclass(frozen=True)
class EvidenceRecord:
    instrument_id: str
    block: EvidenceBlock
    payload: dict[str, Any]
    provenance: Provenance
    #: Stable identity of the underlying fact. Two records sharing a ``fact_key`` and an
    #: ``event_time`` are versions of the same fact; the later ``knowledge_time`` is a
    #: restatement of the earlier.
    fact_key: str = "default"
    licence_status: str | None = None

    @property
    def event_time(self) -> datetime:
        return self.provenance.event_time

    @property
    def knowledge_time(self) -> datetime:
        return self.provenance.knowledge_time

    def content_hash(self) -> str:
        blob = json.dumps(
            {"i": self.instrument_id, "m": self.block.value, "k": self.fact_key,
             "e": self.event_time.isoformat(), "p": _stable(self.payload)},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "instrument_id": self.instrument_id,
            "block": self.block.value,
            "fact_key": self.fact_key,
            "payload": self.payload,
            "provenance": self.provenance.to_dict(),
            "licence_status": self.licence_status,
            "content_hash": self.content_hash(),
        }


def _stable(obj: Any) -> Any:
    """JSON-stable projection of a payload, for hashing."""
    if isinstance(obj, dict):
        return {k: _stable(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_stable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float):
        return round(obj, 12)
    return obj


@dataclass
class RiskAssessment:
    """The system output contract (spec section 7). Deliberately contains no
    instruction, target price, or allocation -- see ``research/risk/non_advisory.py``."""
    instrument_id: str
    decision_time: datetime
    integrity_risk: float
    uncertainty: float
    coverage: float
    risk_state: RiskState
    regime: str | None = None
    block_evidence: dict[str, float] = field(default_factory=dict)
    affective_state: dict[str, float] = field(default_factory=dict)
    propagation: dict[str, float] = field(default_factory=dict)
    xai: dict[str, Any] = field(default_factory=dict)
    knowledge_cutoff: datetime | None = None

    def __post_init__(self) -> None:
        self.decision_time = utc(self.decision_time)
        if self.knowledge_cutoff is not None:
            self.knowledge_cutoff = utc(self.knowledge_cutoff)
        for name in ("integrity_risk", "uncertainty", "coverage"):
            v = getattr(self, name)
            if not (0.0 - 1e-9 <= float(v) <= 1.0 + 1e-9):
                raise ValueError("%s must lie in [0,1], got %r" % (name, v))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_state"] = self.risk_state.value
        d["decision_time"] = self.decision_time.isoformat()
        if self.knowledge_cutoff is not None:
            d["knowledge_cutoff"] = self.knowledge_cutoff.isoformat()
        return d


class BitemporalStore:
    """Append-only bitemporal evidence store.

    Retrieval is always ``as-of``: a query names a ``decision_time`` (how far the world
    has advanced) and a ``knowledge_cutoff`` (what the system is permitted to have
    learned). Records failing either bound are invisible -- not filtered later, invisible.
    """

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[EvidenceRecord]:
        return iter(self._records)

    def append(self, record: EvidenceRecord) -> None:
        self._records.append(record)

    def extend(self, records: Iterable[EvidenceRecord]) -> None:
        for r in records:
            self.append(r)

    def query(
        self,
        instrument_id: str | None,
        decision_time: datetime,
        knowledge_cutoff: datetime | None = None,
        blocks: Sequence[EvidenceBlock] | None = None,
        lookback_days: float | None = None,
    ) -> list[EvidenceRecord]:
        """Return the as-of view. ``knowledge_cutoff`` defaults to ``decision_time``.

        When several versions of the same fact are visible, only the one with the
        greatest ``knowledge_time`` at or before the cutoff survives -- restatements
        published after the cutoff cannot influence the answer.
        """
        decision_time = utc(decision_time)
        cutoff = utc(knowledge_cutoff) if knowledge_cutoff is not None else decision_time
        if cutoff > decision_time:
            raise LeakageError(
                "knowledge_cutoff %s is after decision_time %s: a decision may not use "
                "knowledge from its own future" % (cutoff, decision_time)
            )
        want = set(blocks) if blocks else None
        floor = None
        if lookback_days is not None:
            floor = decision_time.timestamp() - lookback_days * 86400.0

        best: dict[tuple, EvidenceRecord] = {}
        for r in self._records:
            if instrument_id is not None and r.instrument_id != instrument_id:
                continue
            if want is not None and r.block not in want:
                continue
            if r.event_time > decision_time:
                continue
            if r.knowledge_time > cutoff:
                continue
            if floor is not None and r.event_time.timestamp() < floor:
                continue
            key = (r.instrument_id, r.block, r.fact_key, r.event_time)
            prev = best.get(key)
            if prev is None or r.knowledge_time > prev.knowledge_time:
                best[key] = r
        return sorted(best.values(), key=lambda r: (r.event_time, r.instrument_id))


def get_evidence(
    store: BitemporalStore,
    instrument_id: str | None,
    decision_time: datetime,
    knowledge_cutoff: datetime | None = None,
    **kwargs: Any,
) -> list[EvidenceRecord]:
    """The spec-mandated entry point (section 26). Thin by design: every caller in the
    system goes through this function so that the leakage tests have one place to attack.
    """
    records = store.query(instrument_id, decision_time, knowledge_cutoff, **kwargs)
    cutoff = utc(knowledge_cutoff) if knowledge_cutoff is not None else utc(decision_time)
    for r in records:  # belt and braces: the invariant is asserted, not assumed
        if r.knowledge_time > cutoff:
            raise LeakageError(
                "record %s leaked: knowledge_time %s > cutoff %s"
                % (r.content_hash()[:12], r.knowledge_time, cutoff)
            )
    return records
