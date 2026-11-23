"""The console cannot be asked to hold every character the harness prints.

A Windows console (cp1252, cp437) or a POSIX shell under LC_ALL=C cannot encode "×", "—" or "→", and
`print` of one raised UnicodeEncodeError and ended the command. `degrade_unencodable()` makes a character the
console cannot encode print as its backslash escape: the text still uses the console's own encoding, and a
console that is UTF-8 is untouched. Called first from each entry point.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def degrade_unencodable() -> None:
    """Make stdout and stderr write an unencodable character as a backslash escape, not raise.

    A stream that cannot be reconfigured (a test's StringIO, a closed or detached stream) is left as it is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (ValueError, OSError):
            continue


def dump_json(doc: Any, indent: int | None = None, default: Callable[[Any], Any] | None = None) -> str:
    """The document as JSON text for stdout: characters as they are, but escaped (`\\uXXXX`) where the console cannot
    encode them. `degrade_unencodable` alone would write its own escape (`\\xd7`), which is not JSON."""
    text = json.dumps(doc, ensure_ascii=False, indent=indent, default=default)
    try:
        text.encode(getattr(sys.stdout, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(doc, indent=indent, default=default)
    return text
