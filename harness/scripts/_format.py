"""The project's data format (RFC-032): one number, `data/project.yaml`'s `format`, the release reading it its own.

A project whose data is older is refused until `evh migrate` brings it to this release's format; one whose data is
newer was written by a later release and is refused too. No record carries a version of its own: the project migrates
whole, by numbered steps (`evaluation_harness.migrations`). A project with no `project.yaml` is at format 0, the data
as releases before the format existed wrote it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._version import __version__

#: The format this release reads and writes.
FORMAT = 1
NAME = "project.yaml"


def path(data: _Path | None = None) -> _Path:
    """Where the format is recorded: the project's data/, or the data folder `data`."""
    return (data or _common.DATA) / NAME


def record() -> dict[str, Any]:
    """`data/project.yaml` as written, or {} when there is none (format 0)."""
    import yaml  # noqa: PLC0415

    p = path()
    if not _store.is_file(p):
        return {}
    try:
        doc = yaml.safe_load(_store.read_text(p, encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        _common.die(f"{p}: not YAML ({exc})", "invalid-file")
    if (
        not isinstance(doc, dict)
        or not isinstance(doc.get("format", 0), int)
        or isinstance(doc.get("format"), bool)
    ):
        _common.die(f"{p}: `format` must be a whole number", "invalid-file")
    return doc


def data_format() -> int:
    """The format the project's data is in: 0 when it records none."""
    return int(record().get("format", 0))


def stamp(n: int = FORMAT, data: _Path | None = None) -> None:
    """Record that the data (the project's, or the folder `data`) is at format `n`, and which release wrote it."""
    _store.mkdir(data or _common.DATA, parents=True, exist_ok=True)
    _store.write_text(
        path(data),
        "# The format of this project's data (RFC-032): written by `evh init` and `evh migrate`, never by hand.\n"
        f"format: {n}\nwritten_by: {__version__}\n",
        encoding="utf-8",
    )


def require() -> None:
    """Refuse a project whose data is not in this release's format."""
    have = record()
    n = int(have.get("format", 0))
    if n < FORMAT:
        _common.die(
            f"the project's data is at format {n}, this release reads {FORMAT}: run evh migrate (evh migrate --dry-run "
            "first shows what it changes)",
            "old-format",
        )
    if n > FORMAT:
        _common.die(
            f"the project's data is at format {n}, written by {have.get('written_by') or 'a later release'}; this "
            f"release ({__version__}) reads {FORMAT}: install that release",
            "mismatch",
        )
