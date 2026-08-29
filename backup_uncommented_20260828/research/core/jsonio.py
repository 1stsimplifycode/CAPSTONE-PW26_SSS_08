"""Strict JSON writing for every published artifact.

Python's ``json`` module emits bare ``NaN``, ``Infinity`` and ``-Infinity`` by default.
None of those is valid JSON. ``json.loads`` accepts them, so a Python-only pipeline never
notices, but ``JSON.parse`` and most strict parsers reject the *entire document* — one
non-finite float buried in a nested result turns a whole artifact into an unreadable file.

That failure already happened once here, in the exported app bundles, where it silently
rendered a page as "data not available" while every Python test passed. This module
exists so the same class of bug cannot recur in the research artifacts, which are the
reproducible record the paper is built from.

A non-finite float becomes ``null``. That is the honest encoding: the value is not a
number, and a reader deserves to see a missing value rather than a token their parser
cannot read.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def sanitise(obj: Any) -> Any:
    """Recursively replace non-finite floats with ``None``."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitise(v) for v in obj]
    # numpy scalars answer to ``item()`` and would otherwise slip through as float
    # subclasses that ``isinstance(obj, float)`` does catch, and as integer types it does
    # not. Converting first keeps both paths on the same branch.
    item = getattr(obj, "item", None)
    if callable(item) and hasattr(obj, "dtype"):
        return sanitise(item())
    return obj


def dumps(payload: Any, indent: int | None = 2) -> str:
    """Serialise with non-finite floats nulled and bare ``NaN`` refused outright."""
    return json.dumps(sanitise(payload), indent=indent, default=str, allow_nan=False)


def write(path: str | Path, payload: Any, indent: int | None = 2) -> Path:
    """Write a strict-JSON artifact, creating the parent directory if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(payload, indent=indent), encoding="utf-8")
    return p


# -- bundles served to a reader --------------------------------------------------------

def scrub_paths(node: Any, found: list[str] | None = None) -> Any:
    """Rewrite absolute paths under the repository to repository-relative ones.

    Everything written by :func:`write_public` is served to a browser. An absolute path in
    that payload publishes the directory layout of whichever machine ran the pipeline,
    while being useless to the reader: a path under someone's home directory is not a
    citation. Rewriting is the correct repair because the *relative* path is the true
    reference — the file is in the repository either way.
    """
    from research.core import paths as _paths

    found = [] if found is None else found
    root = _paths.REPO_ROOT.as_posix()
    if isinstance(node, str):
        text = node.replace("\\", "/")
        if text.startswith(root + "/"):
            found.append(node)
            return text[len(root) + 1:]
        return node
    if isinstance(node, dict):
        return {k: scrub_paths(v, found) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [scrub_paths(v, found) for v in node]
    return node


def write_public(path: str | Path, payload: Any, log=None) -> Path:
    """Write a bundle destined for ``public/``, with no absolute path left in it.

    Whatever is rewritten is reported rather than silently corrected, so a producer that
    starts recording absolute paths becomes visible on the next export instead of being
    cleaned up forever behind its own back.
    """
    found: list[str] = []
    cleaned = scrub_paths(payload, found)
    if log:
        for one in sorted(set(found)):
            log("      REWROTE ABSOLUTE PATH %s" % one)
    return write(path, cleaned)
