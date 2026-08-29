"""Licence gates for data sources (spec sections 15, 51, 52, 60, 61).

The single rule this module exists to enforce: material whose redistribution rights are
not established must never be copied into a publication artifact.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class LicenseStatus(StrEnum):
    OPEN_LICENSE = "OPEN_LICENSE"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    USER_PROVIDED = "USER_PROVIDED"
    AUTHORIZED = "AUTHORIZED"
    EMBED_ONLY = "EMBED_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


#: Statuses whose material may be ingested (bytes stored, features computed locally).
INGESTIBLE = frozenset({
    LicenseStatus.OPEN_LICENSE,
    LicenseStatus.PUBLIC_DOMAIN,
    LicenseStatus.USER_PROVIDED,
    LicenseStatus.AUTHORIZED,
})

#: Statuses whose material may be redistributed inside a paper package. Kept as a
#: separate name from INGESTIBLE so the two policies can diverge later without
#: silently widening redistribution rights.
REDISTRIBUTABLE = frozenset(INGESTIBLE)

#: Statuses that may only ever be referenced by URL and metadata.
REFERENCE_ONLY_STATUSES = frozenset({
    LicenseStatus.EMBED_ONLY,
    LicenseStatus.REFERENCE_ONLY,
})


class LicenseViolation(RuntimeError):
    """Raised instead of silently degrading. A licence breach is a hard failure."""


@dataclass(frozen=True)
class MediaLicense:
    status: LicenseStatus
    source_url: str
    publisher: str | None = None
    licence_name: str | None = None
    licence_url: str | None = None
    evidence: str | None = None
    asserted_by: str = "MediaLicenseChecker"

    def may_ingest(self) -> bool:
        return self.status in INGESTIBLE

    def may_redistribute(self) -> bool:
        return self.status in REDISTRIBUTABLE

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class MediaLicenseChecker:
    """Classifies a source reference. Defaults to UNKNOWN, never to permissive.

    The domain rules are conservative and deliberately dumb: a checker that guesses
    generously is worse than no checker. Anything not explicitly known is UNKNOWN, and
    An UNKNOWN source is excluded from every redistributable artifact.
    """

    EMBED_ONLY_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")
    OPEN_HOSTS = ("commons.wikimedia.org", "archive.org", "zenodo.org")
    RESTRICTED_HOSTS = ("cnbc.com", "bloomberg.com", "reuters.com", "wsj.com", "ft.com")

    def check(
        self,
        source_url: str,
        *,
        declared: LicenseStatus | None = None,
        publisher: str | None = None,
        licence_name: str | None = None,
        licence_url: str | None = None,
        evidence: str | None = None,
    ) -> MediaLicense:
        if declared is not None:
            # An explicit declaration (user-supplied file, signed permission, verified
            # open licence) wins, but must carry evidence to be ingestible.
            if declared in INGESTIBLE and not evidence:
                raise LicenseViolation(
                    "declared=%s for %r requires `evidence` describing how the right "
                    "was established" % (declared.value, source_url)
                )
            return MediaLicense(declared, source_url, publisher, licence_name,
                                licence_url, evidence)

        host = host_of(source_url)
        if any(h in host for h in self.RESTRICTED_HOSTS):
            status = LicenseStatus.REFERENCE_ONLY
            why = "host %s is all-rights-reserved by default" % host
        elif any(h in host for h in self.EMBED_ONLY_HOSTS):
            status = LicenseStatus.EMBED_ONLY
            why = "host %s permits embedding, not redistribution" % host
        elif any(h in host for h in self.OPEN_HOSTS):
            status = LicenseStatus.REFERENCE_ONLY
            why = ("host %s hosts open material but the per-item licence was not "
                   "verified; upgrade requires declared= plus evidence" % host)
        else:
            status = LicenseStatus.UNKNOWN
            why = "host %s not in any known-licence list" % host
        return MediaLicense(status, source_url, publisher, licence_name,
                            licence_url, evidence or why)

    @staticmethod
    def assert_redistributable(lic: MediaLicense, context: str) -> None:
        if not lic.may_redistribute():
            raise LicenseViolation(
                "%s: source %r has status %s; it may be referenced but not copied into "
                "a redistributable artifact" % (context, lic.source_url, lic.status.value)
            )


def host_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


@dataclass
class DatasetLicence:
    name: str
    source: str
    licence: str
    date_accessed: str
    coverage: str
    restrictions: str
    citation: str
    version_or_hash: str


@dataclass
class ModelLicence:
    name: str
    version: str
    source: str
    licence: str
    weights_available: bool
    research_use: bool
    commercial_use: str
    limitations: str


@dataclass
class LicenceRegistry:
    datasets: list[DatasetLicence] = field(default_factory=list)
    models: list[ModelLicence] = field(default_factory=list)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "datasets": [asdict(d) for d in self.datasets],
            "models": [asdict(m) for m in self.models],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
