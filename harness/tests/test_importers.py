#!/usr/bin/env python3
"""The built-in importers beyond jsonl (RFC-019 P1): tsv, github and langfuse, offline.

github runs against a stand-in `gh` (EVH_GH) that replays recorded GraphQL pages; langfuse against a
local HTTP stand-in. No network.

    python tests/test_importers.py
"""

import base64
import json
import os
import stat
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _importers
from evaluation_harness._check import check, summary

tmp = Path(tempfile.mkdtemp(prefix="evh-importers-"))


def read_list(name: str, query: dict) -> list:
    return list(_importers.read(name, query)[0])


# ── tsv ────────────────────────────────────────────────────────────────────────────────────
(tmp / "ledger.tsv").write_text(
    "occurrence_id\tts\tdisposition\treason\n"
    "o1\t2026-10-01T00:00:00Z\tdismiss\tnoise\n"
    "o2\t2026-10-02T00:00:00Z\tfile\ta bug\n"
    "o3\t\tescalate\tunsure\n"
)
recs = read_list(
    "tsv",
    {
        "path": str(tmp / "ledger.tsv"),
        "id": "occurrence_id",
        "created_at": "ts",
        "where": {"disposition": ["dismiss", "file"]},
    },
)
recs = [_importers.normalise(r) for r in recs]
check(
    "tsv: rows by the id and time columns, filtered, the whole row as the body",
    [r["id"] for r in recs] == ["o1", "o2"]
    and recs[1]["body"]["reason"] == "a bug"
    and recs[0]["created_at"] == "2026-10-01T00:00:00Z",
    recs,
)
(tmp / "ledger.csv").write_text("id,x\na,1\n")
recs = read_list("tsv", {"path": str(tmp / "ledger.csv"), "delimiter": ","})
check("tsv: delimiter reads a comma-separated file", [r["id"] for r in recs] == ["a"])

# ── github, against a stand-in gh ──────────────────────────────────────────────────────────


def issue(n, created, state="CLOSED", events=(), comments=(), labels=()):
    return {
        "number": n,
        "title": f"issue {n}",
        "body": "b",
        "url": f"https://github.com/o/r/issues/{n}",
        "createdAt": created,
        "closedAt": None,
        "state": state,
        "stateReason": "COMPLETED" if state == "CLOSED" else None,
        "labels": {"nodes": [{"name": x} for x in labels]},
        "comments": {"totalCount": len(comments), "nodes": list(comments)},
        "events": {"nodes": list(events)},
    }


def c(who, at, body):
    return {"author": {"login": who}, "createdAt": at, "body": body}


pages = [
    {
        "pageInfo": {"hasNextPage": True, "endCursor": "P2"},
        "nodes": [
            issue(
                1,
                "2026-10-01T00:00:00Z",
                events=[
                    {
                        "__typename": "ClosedEvent",
                        "createdAt": "2026-10-03T10:00:00Z",
                        "actor": {"login": "ann"},
                        "stateReason": "COMPLETED",
                        "duplicateOf": None,
                    }
                ],
                comments=[
                    c("ann", "2026-10-03T09:59:30Z", "Fixed in v1.2 by abc123"),
                    c("bob", "2026-10-03T10:00:10Z", "thanks"),
                ],
            ),
            issue(
                2,
                "2026-10-02T00:00:00Z",
                events=[
                    {
                        "__typename": "ClosedEvent",
                        "createdAt": "2026-10-04T00:00:00Z",
                        "actor": {"login": "ann"},
                        "stateReason": "DUPLICATE",
                        "duplicateOf": {"number": 1, "repository": {"nameWithOwner": "o/r"}},
                    },
                    {
                        "__typename": "ReopenedEvent",
                        "createdAt": "2026-10-06T00:00:00Z",
                        "actor": {"login": "ann"},
                    },
                ],
                comments=[c("ann", "2026-10-06T00:00:20Z", "Recurred 2026-10-06 after close — reopening.")],
            ),
        ],
    },
    {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [issue(3, "2026-10-09T00:00:00Z", state="OPEN")],
    },
]
(tmp / "pages.json").write_text(json.dumps(pages))
calls = tmp / "calls.log"
fake = tmp / "gh"
fake.write_text(
    "#!/usr/bin/env python3\n"
    "import json, sys\n"
    f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
    f"pages = json.load(open({str(tmp / 'pages.json')!r}))\n"
    "page = pages[1] if any(a == 'after=P2' for a in sys.argv) else pages[0]\n"
    "print(json.dumps({'data': {'repository': {'issues': page}}}))\n"
)
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
os.environ["EVH_GH"] = str(fake)

recs = read_list("github", {"repo": "o/r", "labels": ["l1"]})
check(
    "github: every issue across both pages",
    [r["id"] for r in recs] == ["1", "2", "3"],
    [r["id"] for r in recs],
)
o1 = recs[0]["outcome"]
check(
    "github: a close event with its actor and the comment beside it, not someone else's",
    o1["close_events"]
    == [
        {
            "at": "2026-10-03T10:00:00Z",
            "actor": "ann",
            "comment": "Fixed in v1.2 by abc123",
            "reason": "COMPLETED",
        }
    ],
    o1,
)
o2 = recs[1]["outcome"]
check(
    "github: a duplicate, and a reopen with its comment",
    o2["duplicate_of"] == "o/r#1"
    and o2["reopen_count"] == 1
    and (o2["reopen_events"][0]["comment"] or "").startswith("Recurred"),
    o2,
)
check("github: the labels variable passed as an array", "labels[]=l1" in calls.read_text())
calls.write_text("")
recs = read_list("github", {"repo": "o/r", "until": "2026-10-02T00:00:00Z"})
check(
    "github: stops at `until`, without reading the next page",
    [r["id"] for r in recs] == ["1"] and calls.read_text().count("graphql") == 1,
    calls.read_text(),
)
try:
    read_list("github", {"repo": "no-slash"})
    check("github: a repo without owner/name is refused", False)
except ValueError:
    check("github: a repo without owner/name is refused", True)

# ── langfuse, against a local stand-in ─────────────────────────────────────────────────────
seen_auth: list = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        seen_auth.append(self.headers.get("Authorization"))
        if self.path.startswith("/api/public/projects"):
            body = {"data": [{"id": "proj1"}]}
        elif self.path.startswith("/api/public/traces/t1"):
            body = {
                "id": "t1",
                "observations": [
                    {"id": "g1", "type": "GENERATION", "startTime": "2026-10-01T00:00:01Z", "model": "m"}
                ],
                "scores": [{"name": "ok", "value": 1}],
            }
        else:
            body = {
                "data": [
                    {
                        "id": "t1",
                        "name": "triage",
                        "timestamp": "2026-10-01T00:00:00Z",
                        "input": "in",
                        "output": "out",
                        "tags": ["x"],
                    }
                ],
                "meta": {"totalPages": 1},
            }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update(
    LANGFUSE_HOST=f"http://127.0.0.1:{srv.server_port}", LANGFUSE_PUBLIC_KEY="pk", LANGFUSE_SECRET_KEY="sk"
)
recs = read_list("langfuse", {"name": "triage", "observations": True})
r = recs[0] if recs else {}
check(
    "langfuse: a trace, its observations and scores, a path-only link",
    r.get("id") == "t1"
    and r["body"]["observations"][0]["model"] == "m"
    and r["outcome"]["scores"][0]["name"] == "ok"
    and r["source"]["url"] == "/project/proj1/traces/t1",
    r,
)
check(
    "langfuse: the keys sent as Basic auth",
    seen_auth and seen_auth[0] == "Basic " + base64.b64encode(b"pk:sk").decode(),
)
os.environ["LANGFUSE_HOST"] = "file:///etc"
try:
    _importers.read("langfuse", {})
    check("langfuse: a host that is not http(s) is refused", False)
except ValueError as exc:
    check("langfuse: a host that is not http(s) is refused", "http(s)" in str(exc))
srv.shutdown()

sys.exit(summary())
