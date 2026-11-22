"""What production did for each decision, from the tracker's timelines (RFC-030 R4): production's arm.

The filing stage's writes carry no decision id, so a write is joined to the decision whose write window holds it: from
the stamp of the decision before it to its own stamp (a decision is stamped after its writes), plus a measured clock
slack between the two machines' clocks. A create counts first, then a reopen, then a comment; none means nothing was
written (an info alert, a muted one). A fleet write no window holds is reported, never dropped.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

#: The filing host's clock against the tracker's: the triage fleet measured up to 1.6 s; 3 s covers it.
CLOCK_SLACK = dt.timedelta(seconds=3)


def moment(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def fleet_writes(issues: list[dict[str, Any]]) -> list[tuple[dt.datetime, str, int]]:
    """Every write the filing stage made: (time, op, issue), oldest first."""
    out = []
    for i in issues:
        for e in i["events"]:
            if e.get("by") == "fleet":
                op = {"created": "create", "reopened": "reopen", "comment": "comment"}.get(e["type"])
                if op:
                    out.append((moment(e["at"]), op, int(i["number"])))
    return sorted(out)


def actions(
    decisions: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> tuple[dict[str, str], list[tuple]]:
    """({decision id: "create:N" | "reopen:N" | "comment:N" | "none"}, the writes no decision claims)."""
    writes = fleet_writes(issues)
    claimed: set[tuple] = set()
    out: dict[str, str] = {}
    prev = None
    for d in sorted(decisions, key=lambda x: moment(x["ts"])):
        hi = moment(d["ts"])
        lo = prev if prev is not None else hi - dt.timedelta(minutes=1)
        hits = [w for w in writes if lo < w[0] <= hi + CLOCK_SLACK and w not in claimed]
        claimed.update(hits)
        prev = hi
        for op in ("create", "reopen", "comment"):
            got = [w for w in hits if w[1] == op]
            if got:
                out[d["id"]] = f"{op}:{got[0][2]}"
                break
        else:
            out[d["id"]] = "none"
    return out, [w for w in writes if w not in claimed]
