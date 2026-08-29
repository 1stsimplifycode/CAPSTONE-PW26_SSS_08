"""Authoritative exchange reference data, and an honest account of what is missing.

The Week 1 criteria ask for twelve finance inputs. This package delivers the ones that
can be obtained from the exchange itself and *refuses to substitute anything* for the
ones that cannot. That refusal is the load-bearing part: a fabricated circuit band or an
invented review cycle is worse than an absent one, because an absent one is visible.

Every item in :data:`REQUIRED_INPUTS` resolves to exactly one of three states:

``OBTAINED``     an artifact exists on disk, with source, retrieval instant, licence,
                 checksum and temporal coverage recorded in the manifest
``PARTIAL``      an artifact exists but does not cover what the criterion asks for; the
                 shortfall is named in ``shortfall``
``UNAVAILABLE``  no authoritative artifact. ``attempts`` records what was tried and what
                 the exchange answered, so the gap is auditable rather than asserted

Nothing in this package infers a market rule. A value that NSE did not publish is not
here, and :func:`research.reference.registry.status_report` says so by name.

Provenance grading is separate from availability and equally explicit. A fact read out of
an exchange file is ``EXCHANGE_PUBLISHED``. A quantity computed from exchange files by
this repository -- the corporate-action adjustment factor, for instance, which is derived
from NSE's own restatement of ``prev_close`` -- is ``DERIVED_FROM_EXCHANGE_DATA`` and
carries the derivation in its ``note``. A number this project chose is
``PROJECT_ASSUMPTION`` and may never be presented as an exchange rule.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

REFERENCE_VERSION = "reference-v1"


class Availability(StrEnum):
    OBTAINED = "OBTAINED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class Basis(StrEnum):
    """Where a value's authority comes from. Never inferred, always declared."""

    #: Read verbatim out of a file the exchange published.
    EXCHANGE_PUBLISHED = "EXCHANGE_PUBLISHED"
    #: Obtained from a commercial redistributor of exchange prices rather than from the
    #: exchange. Real market data, but one hop removed: the redistributor's own
    #: consolidation and adjustment rules sit between the tape and the number, and it is
    #: not an NSE publication. Never conflated with EXCHANGE_PUBLISHED.
    THIRD_PARTY_REDISTRIBUTOR = "THIRD_PARTY_REDISTRIBUTOR"
    #: Computed by this repository from exchange files, by a documented derivation.
    DERIVED_FROM_EXCHANGE_DATA = "DERIVED_FROM_EXCHANGE_DATA"
    #: Inferred by a published statistical rule that is known to be imperfect -- trade
    #: signing by the tick test, for instance. Real method, real error rate, and *not* a
    #: statement by the exchange about what actually happened.
    INFERRED_BY_PUBLISHED_RULE = "INFERRED_BY_PUBLISHED_RULE"
    #: Observed behaviour of the data, not a statement by the exchange.
    OBSERVED_IN_DATA = "OBSERVED_IN_DATA"
    #: A choice this project made. Never an exchange rule, never displayed as one.
    PROJECT_ASSUMPTION = "PROJECT_ASSUMPTION"


#: The twelve inputs the Week 1 criteria name, in the order C7 lists them.
REQUIRED_INPUTS = (
    "index_composition",
    "index_review_cycle",
    "corporate_actions",
    "ex_date_conventions",
    "delisting",
    "suspension",
    "asm_gsm",
    "circuit_bands",
    "settlement_cycle",
    "market_timings",
    "auction_windows",
    "block_deal_windows",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Attempt:
    """One acquisition attempt, successful or not. The failures are the point."""

    url: str
    http_status: int | str
    attempted_at: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReferenceSource:
    """One reference dataset and everything needed to judge it.

    ``temporal_coverage`` is deliberately separate from availability. A current-snapshot
    ASM list is genuinely obtained and genuinely useless for a 2015 point-in-time query,
    and only the coverage field can say that.
    """

    input_id: str
    title: str
    availability: Availability
    basis: Basis | None = None
    provider: str = ""
    source_url: str = ""
    source_identifier: str = ""
    licence: str = ""
    retrieved_at: str = ""
    artifact_path: str = ""
    sha256: str = ""
    bytes: int = 0
    version: str = ""
    temporal_coverage: str = ""
    point_in_time: bool = False
    shortfall: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["availability"] = str(self.availability)
        d["basis"] = str(self.basis) if self.basis else None
        d["attempts"] = [a.to_dict() if isinstance(a, Attempt) else a
                         for a in self.attempts]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ReferenceSource:
        d = dict(d)
        d["availability"] = Availability(d["availability"])
        d["basis"] = Basis(d["basis"]) if d.get("basis") else None
        d["attempts"] = [Attempt(**a) for a in d.get("attempts", [])]
        return cls(**d)

    @property
    def satisfies_criterion(self) -> bool:
        return self.availability is Availability.OBTAINED


#: NSE publishes these reports for public download. Public accessibility is not
#: permission to redistribute, which is why the acquired files are gitignored and only
#: their checksums are committed.
NSE_LICENCE = (
    "NSE publishes these reports for public download under its website terms of use. "
    "Public accessibility is not permission to redistribute: acquired files are held "
    "locally, excluded from version control, and only their checksums are committed. "
    "Index names, levels and constituent lists are the property of NSE Indices Limited "
    "and are used here for non-commercial research."
)


def manifest_path(root: Path | None = None) -> Path:
    from research.core import paths
    return (root or paths.REFERENCE) / "reference_manifest.json"


def write_manifest(sources: list[ReferenceSource], root: Path | None = None) -> Path:
    from research.core import paths
    root = root or paths.REFERENCE
    root.mkdir(parents=True, exist_ok=True)
    p = manifest_path(root)
    payload = {
        "reference_version": REFERENCE_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
        "required_inputs": list(REQUIRED_INPUTS),
        "sources": [s.to_dict() for s in sources],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def read_manifest(root: Path | None = None) -> list[ReferenceSource]:
    p = manifest_path(root)
    if not p.exists():
        return []
    payload = json.loads(p.read_text(encoding="utf-8"))
    return [ReferenceSource.from_dict(s) for s in payload.get("sources", [])]
