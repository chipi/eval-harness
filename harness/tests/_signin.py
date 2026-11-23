"""The Workbench's sign-in link from `evh catalog-serve`'s startup lines, for the browser tests.

Their server's output is a pipe, so the link names the token's file instead of carrying the token (no log holds
one): the link is made the way a person makes it from a background job's log, with the token read from that file.
"""

from __future__ import annotations

import re
from pathlib import Path

SHOWN = re.compile(r"(http://\S+/api/v1/session\?token=)<the token in (\S+)>(&next=/workbench/)")


def link(lines: list[str]) -> str | None:
    """The sign-in link, the token read from the file the startup line names; None when no line names one."""
    for ln in lines:
        if m := SHOWN.search(ln):
            return m.group(1) + Path(m.group(2)).read_text(encoding="utf-8").strip() + m.group(3)
    return None
