"""An item's artifact link (RFC-038 section 2): one reserved key of `Result.meta`, `artifact`, a path inside the project.

An adapter that leaves something a person should open (an agent's trial directory, a rendered report) names it:
`meta["artifact"] = "artifacts/<system>/<trial>"`. The core keeps it as a clean project-relative POSIX path (`normalise`,
at write) and builds the link from it when an item is shown (`link`, at read). A stored path is never trusted: a run
copied from elsewhere or a hand-edited row is checked again, and a value that does not hold is `refused`, never linked.

The link is a URL under a prefix the inspector already serves read-only (`catalog_serve.served`): the data tree, a
catalog adapter's `served_dirs` and, by default, `artifacts/` at the project root. Nothing here reads the file's content.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from evaluation_harness import _common, _store

#: The key of `Result.meta` that names an item's artifact, and the one the core adds when it drops a value.
KEY = "artifact"
REFUSED = "artifact_refused"
#: The directory at the project root an adapter writes artifacts to without configuring anything: always a served prefix.
DIR = "artifacts"


def _root(root: Path | None) -> Path:
    return Path(root if root is not None else _common.ROOT).resolve()


def normalise(value: Any, root: Path | None = None) -> tuple[str | None, str | None]:
    """(the path as the core stores it, None), or (None, why it is not kept). A string naming a place inside the project
    (relative to it, or absolute), symlinks followed, `..` cleaned: stored as a POSIX path relative to the project, with no
    `..` and no leading `/`. A path that resolves outside the project (a `..`, an absolute path elsewhere, a symlink that
    leads out), the project itself, and anything that is not a non-empty string are refused."""
    if not isinstance(value, str) or not value.strip():
        return None, "not a path (a non-empty string)"
    base = _root(root)
    p = Path(value)
    try:
        target = (p if p.is_absolute() else base / p).resolve()
        rel = target.relative_to(base)
    except (ValueError, OSError):
        return None, "outside the project"
    if not rel.parts:
        return None, "the project itself, not a path in it"
    return rel.as_posix(), None


def served_prefixes(
    data_dir: Path | None, served_dirs: Iterable[Path] = (), root: Path | None = None
) -> tuple[str, ...]:
    """The URL prefixes of the project's files the inspector serves, in the form `catalog_serve.served` gives: `artifacts/`,
    the data tree and each of `served_dirs`, those inside the project (one outside it has no URL)."""
    base = _root(root)
    out = [f"/{DIR}/"]
    for p in (data_dir, *served_dirs):
        if p is None:
            continue
        try:
            rel = "/" + Path(p).resolve().relative_to(base).as_posix().strip("/") + "/"
        except ValueError:
            continue
        if rel not in out:
            out.append(rel)
    return tuple(out)


def link(stored: Any, prefixes: Iterable[str], root: Path | None = None) -> dict[str, Any] | None:
    """What an item's view says of the artifact a row stored: `{"path", "kind"}` and, when the path lies under a served
    prefix, `"url"`. `kind` is `dir`, `file`, `missing` (not on this machine) or `refused` (what is stored is not a path
    inside the project: no url, whatever was stored). None when the row stored nothing."""
    if stored is None:
        return None
    rel, _why = normalise(stored, root)
    if rel is None:
        return {"path": str(stored), "kind": "refused"}
    target = _root(root) / rel
    kind = "dir" if _store.is_dir(target) else "file" if _store.is_file(target) else "missing"
    out: dict[str, Any] = {"path": rel, "kind": kind}
    if any(f"/{rel}/".startswith(x) for x in prefixes):
        out["url"] = "/" + quote(rel) + ("/" if kind == "dir" else "")
    return out
