#!/usr/bin/env python3
"""Which day it is is one function, and it is UTC (RFC-041 F5): `_common.today()`.

    python tests/test_today.py

Runs are stamped in UTC and a period compares `created_at[:10]`, so a reader that asked the machine's local date
(`date.today()`) saw another day than the data for some hours of every day:

- the test puts this process in a time zone whose date is not UTC's (it picks one from the hour it runs at);
- `today()` is the UTC date; a deployment's staleness, the server's page-cache day and the day a cached view is kept
  for all come from it;
- no source line asks the machine for a date but `_common.today` (read from the tokens, as test_cap_shown.py is).
"""

import io
import os
import sys
import time
import tokenize
from datetime import datetime, timedelta, timezone
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _common, catalog_build, catalog_models  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

# A zone whose date is not UTC's now: +14 is a day ahead from 10:00 UTC, -11 a day behind before 11:00 UTC.
utc_now = datetime.now(timezone.utc)
zone = "Pacific/Kiritimati" if utc_now.hour >= 10 else "Pacific/Pago_Pago"
os.environ["TZ"] = zone
time.tzset()
utc_day = datetime.now(timezone.utc).date()
check(
    "setup: this process's local date is not the UTC date",
    datetime.now().date() != utc_day,
    (zone, datetime.now().date(), utc_day),
)

today = getattr(_common, "today", None)
check("today() is the UTC date, whatever the machine's zone", today is not None and today() == utc_day, zone)

# ── a deployment is stale a fixed number of UTC days after its check ────────────────────────────────────────────────
edge = {"checked_at": (utc_day - timedelta(days=catalog_models.STALE_DAYS)).isoformat()}
over = {"checked_at": (utc_day - timedelta(days=catalog_models.STALE_DAYS + 1)).isoformat()}
check(
    "stale: checked STALE_DAYS UTC days ago is not stale, one day more is",
    catalog_models.stale(edge) is False and catalog_models.stale(over) is True,
    (catalog_models.stale(edge), catalog_models.stale(over)),
)

# ── the server renders its pages again when the day turns, by the same day ──────────────────────────────────────────
real_prepare, saved = catalog_build.prepare, dict(cs.SITE)
catalog_build.prepare = lambda *a, **k: object()  # type: ignore[assignment]
cs.SITE.update(site=None, site_gen=-1, gen=0, day="", prepared=0, failed=None)
try:
    cs.current_site()
    kept_for = cs.SITE["day"]
finally:
    catalog_build.prepare = real_prepare
    cs.SITE.clear()
    cs.SITE.update(saved)
check(
    "the page cache is kept for the UTC day it was prepared on",
    kept_for == utc_day.isoformat(),
    (kept_for, utc_day.isoformat()),
)

# ── the day a view is kept for, in the cache's key ──────────────────────────────────────────────────────────────────
from evaluation_harness.model import view_cache as vc  # noqa: E402

runs = [0]


def answer():
    runs[0] += 1
    return {"n": runs[0]}


class Day:
    """_common.today() as another day."""

    n = 1

    @classmethod
    def toordinal(cls) -> int:
        return cls.n


real_today = _common.today if today else None
_common.today = lambda: Day  # type: ignore[assignment,return-value]
vc.clear()
try:
    vc.result("by-day", {}, answer)
    vc.result("by-day", {}, answer)
    Day.n = 2
    vc.result("by-day", {}, answer)
finally:
    if real_today:
        _common.today = real_today
check("a view that counts back from today is recomputed when the UTC day turns", runs[0] == 2, runs[0])


# ── the source: no reader asks the machine for a date ───────────────────────────────────────────────────────────────
def asks_the_machine(src: str) -> list[int]:
    """Lines with date.today(), datetime.today() or a datetime.now() with no time zone, from the tokens."""
    toks = [
        t
        for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT)
    ]
    out = []
    for i, t in enumerate(toks[:-3]):
        if (
            t.string == "."
            and i
            and toks[i - 1].string in ("date", "datetime")
            and toks[i + 1].string == "today"
            and toks[i + 2].string == "("
        ):
            out.append(t.start[0])
        naive_now = i and toks[i - 1].string == "datetime" and toks[i + 1].string == "now"
        if t.string == "." and naive_now and toks[i + 2].string == "(" and toks[i + 3].string == ")":
            out.append(t.start[0])
    return out


found = []
for p in sorted((HARNESS / "scripts").rglob("*.py")):
    src = p.read_text(encoding="utf-8")
    lines = src.splitlines()
    found += [f"{p.relative_to(HARNESS)}:{n}: {lines[n - 1].strip()}" for n in asks_the_machine(src)]
check("no reader asks the machine for a date or a naive now: they take _common.today()", not found, found)
check(
    "the tokenizer finds what it looks for",
    asks_the_machine("x = date.today()\ny = datetime.now()\n") == [1, 2],
)

sys.exit(summary())
