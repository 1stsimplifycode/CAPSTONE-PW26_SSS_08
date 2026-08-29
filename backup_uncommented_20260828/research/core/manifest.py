"""Reproducibility manifests (spec sections 54, 83).

Every artifact the system emits can be traced back to one of these. A manifest that
cannot record a field records ``null`` and the reason -- it never guesses.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def git_commit() -> str | None:
    return _git("rev-parse", "HEAD")


def git_dirty() -> bool | None:
    status = _git("status", "--porcelain")
    return None if status is None else bool(status)


def package_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "scipy", "sklearn", "matplotlib", "statsmodels",
             "networkx", "shap", "pyarrow", "duckdb", "PIL", "soundfile", "imageio"]
    out: dict[str, str] = {}
    for n in names:
        try:
            mod = __import__(n)
            out[n] = str(getattr(mod, "__version__", "unknown"))
        except Exception:
            out[n] = "NOT INSTALLED"
    return out


def file_hash(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def dict_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass
class ReproducibilityManifest:
    experiment_id: str
    run_id: str
    seed: int
    config: dict[str, Any] = field(default_factory=dict)
    dataset_version: str | None = None
    dataset_hash: str | None = None
    model_versions: dict[str, str] = field(default_factory=dict)
    xai_versions: dict[str, str] = field(default_factory=dict)
    feature_version: str | None = None
    git_commit: str | None = field(default_factory=git_commit)
    git_dirty: bool | None = field(default_factory=git_dirty)
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    node_version: str | None = None
    platform: str = field(default_factory=lambda: platform.platform())
    packages: dict[str, str] = field(default_factory=package_versions)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat())
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.node_version is None:
            self.node_version = _node_version()
        if self.config:
            self.config_hash = dict_hash(self.config)
        else:
            self.config_hash = None

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        d["config_hash"] = getattr(self, "config_hash", None)
        path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        return path


def _node_version() -> str | None:
    try:
        out = subprocess.run(["node", "--version"], capture_output=True, text=True,
                             timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def environment_snapshot() -> dict[str, Any]:
    return {
        "python": sys.version,
        # The interpreter's *name*, not its path. Which directory someone's virtualenv
        # lives in reproduces nothing, and these snapshots are copied into artifacts that
        # are served to readers, so the path would publish a stranger's home directory
        # while telling them nothing they could act on.
        "executable": Path(sys.executable).name,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "packages": package_versions(),
        "node": _node_version(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
