"""What the catalog's render tests share (RFC-040): production's recorded arm in a tutorial project, the p-value cache
switched in one process, and the footer's time masked for a page another process rendered.

    import _render_proj
    r = _render_proj.add_recorded_arm(evh, proj)
    _render_proj.p_cache("")               # off; a path turns it on, with every p drawn before forgotten
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from evaluation_harness import stats


def add_recorded_arm(evh: Any, proj: Path) -> Any:
    """A capture of production's decisions, a dataset from it and an arm recorded on it: the catalog badges that arm
    "recorded" wherever it names it, and nothing in a tutorial project has one until this. The first failing step's
    result, else the last."""
    rows = [
        {"id": f"p{n}", "body": f"A production ticket number {n}.", "channel": "email", "created_at": f"2026-11-0{n}T09:00:00Z"}
        for n in range(1, 4)
    ]  # fmt: skip
    (proj / "prod.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    r = None
    for step in (
        ("capture", "--importer", "jsonl", "--query", json.dumps({"path": "prod.jsonl"}), "--capture", "prod_c1"),
        ("dataset-from-capture", "--capture", "prod_c1", "--dataset-id", "prod_v1"),
        ("dataset-materialize", "--dataset-id", "prod_v1"),
        ("arm-from-capture", "--dataset-id", "prod_v1", "--capture", "prod_c1", "--as", "production_v1", "--field", "channel"),
    ):  # fmt: skip
        r = evh(*step)
        if r.returncode:
            return r
    return r


def p_cache(path: str) -> None:
    """Turn the p-value cache (stats' EVH_P_CACHE) off with "", or on at `path`, and forget every p this process has
    drawn or read, so the next page draws it (and writes it) or reads it back from the file."""
    os.environ["EVH_P_CACHE"] = path
    for kept in (stats._P, stats._KEPT, stats._SIGNS):
        kept.clear()
    stats._DISK = None


#: The time a page's footer says it was built, to the minute: the one thing a server's page and an export of the same
#: data differ in when they were not rendered in one process (RFC-040: "identical, but for the footer's time").
_BUILT = re.compile(r"Built \d{4}-\d\d-\d\d \d\d:\d\d UTC")


def mask_built(html: str) -> str:
    """The page with its footer's build time masked: the one part two renders of one state may differ in."""
    return _BUILT.sub("Built <time>", html)
