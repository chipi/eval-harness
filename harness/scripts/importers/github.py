"""The github importer: a repository's issues, each with its fate as the outcome.

Through the `gh` command (its own login; EVH_GH names another binary). Query keys:
  repo        owner/name (required)
  labels      ["label", ...]: issues carrying any of them
  state       open | closed | all (default all)
  since/until ISO times on the issue's creation, [since, until)

A record: id = the issue number, body = {title, body}, fields = {labels, comments}, created_at,
source = {system: github, url}, outcome = {state, state_reason, closed_at, duplicate_of,
reopen_count, close_events, reopen_events}. Each event is {at, actor, comment}: the comment beside
it (the same author's, within two minutes), its first 300 characters. A person's close comment is
often the real verdict ("Fixed in v0.8.0", "external noise"), and a bot that writes with its owner's
token can only be told from the owner by its text. `state_reason` is GitHub's: COMPLETED,
NOT_PLANNED, DUPLICATE, REOPENED.

evh capture --importer github --query '{"repo": "o/r", "labels": ["triage-fleet/filed"]}' --capture c1
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from typing import Any

from evaluation_harness._importers import parse_time

QUERY = """query($owner: String!, $name: String!, $after: String, $labels: [String!], $states: [IssueState!]) {
  repository(owner: $owner, name: $name) {
    issues(first: 50, after: $after, labels: $labels, states: $states, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body url createdAt closedAt state stateReason
        labels(first: 50) { nodes { name } }
        comments(last: 100) { totalCount nodes { author { login } createdAt body } }
        events: timelineItems(itemTypes: [CLOSED_EVENT, REOPENED_EVENT], first: 100) {
          nodes {
            __typename
            ... on ClosedEvent { createdAt actor { login } stateReason duplicateOf { ... on Issue { number repository { nameWithOwner } } } }
            ... on ReopenedEvent { createdAt actor { login } }
          }
        }
      }
    }
  }
}"""
NEAR_S = 120


def _comment_beside(at: str, actor: str | None, comments: list) -> str | None:
    """The comment the same author wrote within NEAR_S seconds of an event, if any."""
    t = parse_time(at)
    best = None
    for c in comments:
        ct = parse_time(c.get("createdAt"))
        who = (c.get("author") or {}).get("login")
        gap = abs((ct - t).total_seconds()) if t and ct else None
        if gap is not None and who == actor and gap <= NEAR_S and (best is None or gap < best[0]):
            best = (gap, (c.get("body") or "")[:300])
    return best[1] if best else None


class Importer:
    """Issues of one repository, with what became of each."""

    def __init__(self, options: dict) -> None:
        self.gh = options.get("gh") or os.environ.get("EVH_GH") or "gh"

    def _query(self, variables: dict) -> dict:
        argv = [self.gh, "api", "graphql", "-f", f"query={QUERY}"]
        for k, v in variables.items():
            if v is None:
                continue
            if isinstance(v, list):
                argv += [arg for item in v for arg in ("-f", f"{k}[]={item}")]
            else:
                argv += ["-f", f"{k}={v}"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"gh api graphql failed: {r.stderr.strip()[:300]}")
        d = json.loads(r.stdout)
        if d.get("errors"):
            raise RuntimeError(f"GitHub: {d['errors'][0].get('message', d['errors'])}")
        return d["data"]["repository"]["issues"]

    def _record(self, n: dict) -> dict:
        comments = (n.get("comments") or {}).get("nodes") or []
        closes: list = []
        reopens: list = []
        dup: dict = {}
        for e in (n.get("events") or {}).get("nodes") or []:
            actor = (e.get("actor") or {}).get("login")
            ev: dict[str, Any] = {
                "at": e.get("createdAt"),
                "actor": actor,
                "comment": _comment_beside(e.get("createdAt"), actor, comments),
            }
            if e.get("__typename") == "ClosedEvent":
                closes.append({**ev, "reason": e.get("stateReason")})
                dup = e.get("duplicateOf") or dup
            else:
                reopens.append(ev)
        return {
            "id": str(n["number"]),
            "body": {"title": n["title"], "body": n.get("body") or ""},
            "fields": {
                "labels": [x["name"] for x in (n.get("labels") or {}).get("nodes") or []],
                "comments": (n.get("comments") or {}).get("totalCount", 0),
            },
            "created_at": n["createdAt"],
            "source": {"system": "github", "url": n["url"]},
            "outcome": {
                "state": n["state"],
                "state_reason": n.get("stateReason"),
                "closed_at": n.get("closedAt"),
                "duplicate_of": f"{dup['repository']['nameWithOwner']}#{dup['number']}"
                if dup.get("number")
                else None,
                "reopen_count": len(reopens),
                "close_events": closes,
                "reopen_events": reopens,
            },
        }

    def records(self, query: dict) -> Iterator[dict]:
        """The repository's issues in creation order, within the query's labels, state and window."""
        repo = query.get("repo") or ""
        if repo.count("/") != 1:
            raise ValueError("the github importer needs repo: owner/name in its query")
        owner, name = repo.split("/")
        state = (query.get("state") or "all").lower()
        if state not in ("open", "closed", "all"):
            raise ValueError(f"state {state!r}: open, closed or all")
        states = {"open": ["OPEN"], "closed": ["CLOSED"], "all": None}[state]
        since, until = parse_time(query.get("since")), parse_time(query.get("until"))
        after = None
        while True:
            page = self._query(
                {
                    "owner": owner,
                    "name": name,
                    "after": after,
                    "labels": query.get("labels"),
                    "states": states,
                }
            )
            for n in page["nodes"]:
                t = parse_time(n["createdAt"])
                if until and t and t >= until:
                    return  # issues come in creation order: nothing later is inside the window
                if since and t and t < since:
                    continue
                yield self._record(n)
            if not page["pageInfo"]["hasNextPage"]:
                return
            after = page["pageInfo"]["endCursor"]
