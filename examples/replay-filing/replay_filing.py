"""The filing replay's adapter (RFC-030): the system's own `filing.py`, at the commit each decision ran, over its
frozen world.

Nothing of the system is re-written here. Each decision runs `filing.file(signal)` imported from the copy of the
commit its code record says ran it (`params["code"]`); at a new commit the module is imported again and the two
seams the system exposes are set again: `GH`, the tracker (the stand-in from replay_world.py), and `LEDGER`, the
file of keys filed so far. The ledger and the stand-in's world live here and in a file, never in the system's
modules, because a version switch drops those.

Production read the tracker when its decision started, before its own writes (`started`); the decision is stamped
after them (`ts`). Reading at the stamp would see production's own writes for the decision being replayed: the first
bug the fleet's naive replay had (READ_AT below), which the faithfulness gate catches.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation_harness import _codeload, _common

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_world

#: The item field the tracker is read at: `started`, before the decision's own writes.
READ_AT = "started"
METRIC_KINDS = {"exact": "quality"}
METRIC_DESCRIPTIONS = {
    "exact": "1 when the action (create, reopen, comment or none, and on which issue) is the reference's"
}


@dataclass
class Result:
    """What one decision did, as an action: create:N, reopen:N, comment:N or none."""

    output: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    extra: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


#: This replay's state: the world, the stand-in, the ledger file and the filing module loaded now. Reset by warmup.
_S: dict[str, Any] = {}


def warmup(params: dict[str, Any]) -> None:
    """A fresh world and an empty ledger, once per replay."""
    world = replay_world.World.from_folder(_common.ROOT / str(params["world"]))
    _S.clear()
    _S.update(
        world=world,
        gh=replay_world.TrackerStandIn(world),
        ledger=str(Path(tempfile.mkdtemp(prefix="replay-filing-")) / "filed.json"),
        filing=None,
    )
    hide = params.get("hide") or {}
    if hide:  # RFC-031 P1: production's own writes of these kinds, inside the replayed window, are hidden
        world.hide_kinds = set(hide.get("kinds") or [])
        world.hide_since = replay_world.moment(hide["since"]) if hide.get("since") else None


def call_system(text: str, params: dict[str, Any]) -> Result:
    """One decision: the signal through `filing.file`, at its commit, against the world as production read it."""
    if not _S:
        warmup(params)
    code, fields = params["code"], params["item"]["fields"]
    if code["changed"] or _S["filing"] is None:
        filing = _codeload.use(Path(code["path"]), ["filing"])["filing"]
        filing.GH, filing.LEDGER = _S["gh"], _S["ledger"]
        _S["filing"] = filing
    gh = _S["gh"]
    gh.at = replay_world.moment(fields["started"])
    gh.read_at = replay_world.moment(fields[READ_AT])
    gh.create_as = fields.get("production_issue")
    gh.writes = []
    out = _S["filing"].file(json.loads(text))
    extra: dict[str, float] = {}
    if params.get("hide"):
        # The history confound (RFC-031 P1): production filed an issue here, this replay did not, and a person
        # closed that issue afterwards: a reaction to an action this variant never took.
        pi = fields.get("production_issue")
        issue = _S["world"].issues.get(int(pi)) if pi else None
        reacted = bool(issue) and any(
            e.get("by") == "person" and replay_world.moment(e["at"]) > replay_world.moment(fields["ts"])
            for e in issue["events"]
        )
        if pi:  # marked only where production acted, as a real adapter may: the run counts the rest as not confounded
            extra["history_confound"] = 1.0 if not out.startswith("create") and reacted else 0.0
    return Result(
        output=out,
        cost_usd=0.0,
        extra=extra,
        meta={"commit": code["commit"][:12], "changed": code["changed"], "writes": gh.writes},
    )


def score(output: str, reference: str | None = None) -> dict[str, float]:
    """1 when the action is the reference's."""
    if reference is None:
        return {}
    return {"exact": 1.0 if output.strip() == reference.strip() else 0.0}


def same(a: str, b: str) -> bool:
    """One decision: the same action on the same issue; two creates agree whatever number each got."""
    oa, _, na = str(a).strip().partition(":")
    ob, _, nb = str(b).strip().partition(":")
    return oa == ob and (na == nb or oa == "create")
