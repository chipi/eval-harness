"""The world a filing replay reads (RFC-030 R3): the issue tracker as it was, from frozen timelines.

Production's tracker is not called. Each issue's timeline (created, commented, closed, reopened, with times) was
frozen; the stand-in answers a read as the issue stood at the read's time and records a write instead of sending it.
The replay's own writes are kept in the same world, so a later decision reads what an earlier one did (a reopen at
item 5 is seen at item 9), as in production.

Two times per decision, as the triage fleet's replay found them: the decision is stamped AFTER its own writes, so its
reads happen at the end of the decision before it (`read_at`), never at its own stamp. Reading at the stamp sees
production's writes for this very decision: the first of the six bugs the fleet's naive replay had.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

#: Numbers the replay gives an issue production did not create in the same decision.
SYNTHETIC_FROM = 900000


def moment(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


class World:
    """The tracker as of any time: frozen timelines, plus the replay's own writes."""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        self.issues = {int(i["number"]): i for i in issues}
        self.reopened: dict[int, dt.datetime] = {}
        self.created: dict[int, dt.datetime] = {}
        self.next_synthetic = SYNTHETIC_FROM
        # RFC-031 P1: production's own writes ("by": "fleet") of these kinds, made since the replayed window began, are
        # hidden; the replay's own writes stand in for them, and a person's stay (they are history).
        self.hide_kinds: set[str] = set()
        self.hide_since: dt.datetime | None = None

    @classmethod
    def from_folder(cls, folder: str | Path) -> World:
        lines = (Path(folder) / "issues.jsonl").read_text(encoding="utf-8").splitlines()
        return cls([json.loads(x) for x in lines if x.strip()])

    def hidden(self, e: dict[str, Any]) -> bool:
        """A write production itself made, of a hidden kind, inside the replayed window."""
        return (
            e.get("by") == "fleet"
            and e.get("type") in self.hide_kinds
            and self.hide_since is not None
            and moment(e["at"]) >= self.hide_since
        )

    def state(self, n: int, at: dt.datetime) -> str:
        issue = self.issues.get(int(n))
        if issue is None or moment(issue["created_at"]) > at:
            return "open"  # an issue only the replay opened
        state = "open"
        closed_at = None
        for e in issue["events"]:
            if moment(e["at"]) > at:
                break
            if self.hidden(e):
                continue
            if e["type"] == "closed":
                state, closed_at = "closed", moment(e["at"])
            elif e["type"] == "reopened":
                state, closed_at = "open", None
        mine = self.reopened.get(int(n))
        if (
            state == "closed"
            and mine is not None
            and mine <= at
            and closed_at is not None
            and closed_at <= mine
        ):
            state = "open"
        return state


class TrackerStandIn:
    """`filing.GH` for a replay: reads from the World as of `read_at`, writes recorded."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.at = moment("1970-01-01T00:00:00+00:00")
        self.read_at = self.at
        self.create_as: int | None = None
        self.writes: list[dict[str, Any]] = []

    def state(self, repo: str, n: int) -> str:
        return self.world.state(n, self.read_at)

    def create(self, repo: str, title: str) -> int:
        if self.create_as is not None:
            n = self.create_as
        else:
            n = self.world.next_synthetic
            self.world.next_synthetic += 1
        self.world.created[n] = self.at
        self.writes.append({"op": "create", "issue": n, "title": title})
        return n

    def comment(self, repo: str, n: int, text: str) -> None:
        self.writes.append({"op": "comment", "issue": int(n), "text": text})

    def reopen(self, repo: str, n: int) -> None:
        self.world.reopened[int(n)] = self.at
        self.writes.append({"op": "reopen", "issue": int(n)})

    def __getattr__(self, name: str) -> Any:
        # A call the stand-in does not know is refused, never answered by default: a candidate that calls the tracker
        # some new way fails loudly instead of reading a world the replay does not have.
        raise AttributeError(f"replay: the tracker stand-in has no {name!r}")
