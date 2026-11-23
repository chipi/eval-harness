#!/usr/bin/env python3
"""The Workbench as a read-only viewer on a public server (RFC-039), at the server, through real HTTP.

    python tests/test_workbench_viewer.py

A project with a goal, a round, two arms and a dataset marked `text: hidden`, every text of which carries a marker word
(tests/_viewer_fixture.py), behind `evh catalog-serve --public`:

- /workbench/ is served (its five files and no other), /api/v1 is answered with no token;
- each of the reads the public MCP server offers (`mcp_server.read_ops(True)`) answers, and the marker word is in none
  of the answers; the same marker is in the local server's, or a search that found nothing would prove nothing;
- every other route is refused before anything runs: each job and edit operation (by its own route), the jobs' routes,
  POST /estimate, /session, each read a public server leaves out, and each input a public read does not take; nothing
  is written, no job started, no process run;
- the rate limit counts /api/v1; a foreign Host or Origin is refused; the sheet and an item's input still are;
- a local (token) server, and one behind a proxy, are as they were.
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _serve  # noqa: E402
import _viewer_fixture as fx  # noqa: E402
from evaluation_harness import mcp_server, ops  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-viewer-"))
env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-viewer")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_STORE", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)

#: What a path's `{part}` is, in the fixture.
IDS = {
    "goal": fx.GOAL, "dataset": fx.DS, "system": fx.SYSTEMS[0], "round": "r1", "model": "gem", "deployment": "mac",
    "scorer": "none_v1", "set": "owner_gold", "fieldset": "notes", "failure_modes": "none", "capture": "none",
    "tier": "gold", "name": fx.DS, "label": "runs", "kind": "intervals", "study": "s1", "metric": "overlap_f1",
}  # fmt: skip
ARM = f"runs/{fx.DS}/{fx.SYSTEMS[0]}"
#: What a read that needs an input is given.
NEEDS = {
    "comparison-crosstab": {"runs": ARM, "crosstab": "overlap_f1"}, "search": {"text": "ticket"},
    "prompt-show": {"name": f"{fx.GOAL}/prompt"}, "prompt-diff": {"a": "x", "b": "y"},
    "period-compare": {"dataset": fx.DS, "candidate": fx.SYSTEMS[1]}, "run-compare": {"baseline": ARM, "candidate": ARM},
    "comparison-show": {"goal": fx.GOAL, "round": "r1"}, "chart": {"goal": fx.GOAL},
}  # fmt: skip
#: Statuses of an answer from the operation itself: found, or refused for what the project does not hold.
ANSWERED = (200, 400, 404, 409, 422)


def call(port: int, method: str, path: str, body=None, headers=None):
    """(status, text, headers) of one request, the Host this machine's own."""
    h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


def route(op, **extra: str) -> str:
    """The operation's path, its parts filled from the fixture (`extra` overrides)."""
    parts = {**IDS, **extra}
    return "/api/v1" + "/".join(
        parts.get(p[1:-1], "x") if p.startswith("{") else p for p in op.route.split("/")
    )


def read_path(op, **extra: str) -> str:
    q = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in NEEDS.get(op.name, {}).items())
    return route(op, **extra) + (f"?{q}" if q else "")


def kind_of(text: str) -> str:
    try:
        return str(json.loads(text).get("kind", ""))
    except (ValueError, AttributeError):
        return ""


def snapshot() -> list:
    """What a request that wrote or started something would change: the project's data, its jobs and its calls."""
    out = []
    for root in (proj / "data", proj / ".build" / "jobs", proj / ".build" / "calls"):
        out += [(str(p.relative_to(proj)), p.stat().st_size) for p in sorted(root.rglob("*")) if p.is_file()]
    return out


try:
    fx.build(proj, env)

    served = mcp_server.read_ops(public=True)
    dropped = [op for op in ops.of_kind("read") if op.public_dropped]
    acting = [op for op in ops.OPS.values() if op.kind != "read"]
    check(
        "the registry has the split RFC-039 counts: 62 reads served, 11 left out; 14 edits, 1 in-process decision, 61 jobs",
        (len(served), len(dropped), len([o for o in acting if o.kind == "edit"]),
         len([o for o in acting if o.kind == "decision" and o.in_process]), len([o for o in acting if o.is_job()]))
        == (62, 11, 14, 1, 61),
        (len(served), len(dropped), len(acting)),
    )  # fmt: skip

    # ── the local server, as it was: the control for the marker, and for "unchanged" ──────────────────────────────
    lsrv, lport, _lines = _serve.start(proj, env)
    try:
        token = (proj / ".build" / "api-token").read_text(encoding="utf-8").strip()
        bearer = {"Authorization": f"Bearer {token}"}
        st, _b, _h = call(lport, "GET", "/api/v1/goals")
        check("local: no token, 401", st == 401, st)
        st, b, h = call(lport, "GET", "/api/v1/goals", headers=bearer)
        check("local: the token answers, with no viewer mark", st == 200 and "X-EVH-Viewer" not in h, (st, h))
        st, b, _h = call(lport, "GET", "/workbench/")
        check("local: /workbench/ is served", st == 200 and "<title>Workbench" in b, st)
        st, b, _h = call(lport, "POST", "/api/v1/estimate", {"operation": "run", "inputs": {}})
        check(
            "local: POST /estimate with no token is 401 (the token's rule, not the viewer's)", st == 401, st
        )
        st, b, _h = call(lport, "GET", f"/api/v1/datasets/{fx.DS}/items?item=t01_login", headers=bearer)
        check(
            "local: an item's text is served to this machine (the marker is in the project and reachable)",
            st == 200 and fx.MARK in b,
            (st, b[:200]),
        )
        st, b, _h = call(
            lport, "GET", f"/api/v1/compare/items?runs={urllib.parse.quote(ARM)}", headers=bearer
        )
        check("local: the recorded outputs carry the marker", st == 200 and fx.MARK in b, (st, b[:200]))
        st, b, _h = call(lport, "GET", "/api/v1/jobs", headers=bearer)
        check("local: the jobs' list is served", st == 200, st)
    finally:
        lsrv.terminate()
        lsrv.wait(timeout=10)

    # ── a public server ────────────────────────────────────────────────────────────────────────────────────────────
    before = snapshot()
    srv, port, _lines = fx.serve_public(proj, env, "--publish", "outputs,references")
    try:
        # the static files
        st, b, h = call(port, "GET", "/workbench/")
        check(
            "public: /workbench/ is served, with no token",
            st == 200 and "<title>Workbench" in b,
            (st, h),
        )
        st, _b, _h = call(port, "GET", "/workbench")
        check("public: /workbench redirects to /workbench/", st in (301, 200), st)
        for name in ("workbench.js", "workbench.css", "live.js", "help.js"):
            st, _b, _h = call(port, "GET", f"/workbench/{name}")
            check(f"public: /workbench/{name} is served", st == 200, st)
        for name in ("mock.js", "mockup.html", "../config.yaml", "%2e%2e/config.yaml", "workbench.py"):
            st, b, _h = call(port, "GET", f"/workbench/{name}")
            check(f"public: /workbench/{name} is not", st == 404 and "evh" not in b[:20], st)

        # the reads
        names = {op.name for op in served}
        answers: dict[str, tuple] = {}
        for op in served:
            st, b, h = call(port, "GET", read_path(op))
            answers[op.name] = (st, b)
            check(
                f"public read {op.name}: answered by the operation (not refused as a viewer), no marker",
                st in ANSWERED
                and kind_of(b) != "not-public"
                and fx.MARK not in b
                and h.get("X-EVH-Viewer") == "1",
                (st, b[:200]),
            )
        for ds in (f"{fx.DS}_validation", f"{fx.DS}_test"):  # the other hidden datasets: the sealed side too
            for op in [o for o in served if "{dataset}" in o.route]:
                st, b, _h = call(port, "GET", read_path(op, dataset=ds))
                check(
                    f"public read {op.name} on {ds}: answered or refused by the operation, no marker",
                    st in (*ANSWERED, 403) and kind_of(b) != "not-public" and fx.MARK not in b,
                    (st, b[:200]),
                )
        found = sorted(n for n, (st, _b) in answers.items() if st == 200)
        must = [
            "goal-list", "goal-show", "goal-status", "goal-leaderboard", "round-list", "round-show", "dataset-list",
            "dataset-show", "dataset-items", "leaderboard", "system-list", "system-show", "runs-list", "arm-list",
            "model-list", "model-show", "prompt-list", "prompt-show", "reference-list", "fieldset-list",
            "overview-show", "comparison-show", "chart", "metric-list", "label-set-list", "baselines", "scorer-list",
        ]  # fmt: skip
        check(
            "public reads: the ones a screen of the fixture needs answer 200",
            not [n for n in must if n not in found],
            [n for n in must if n not in found],
        )
        st, b, _h = call(port, "GET", "/api/v1/goals")
        check(
            "public: the same answer as the local server's, for a goal list",
            st == 200 and json.loads(b)["result"]["goals"][0]["goal"] == fx.GOAL,
            (st, b[:200]),
        )
        st, b, _h = call(port, "GET", "/api/v1/openapi.json")
        check("public: GET /openapi.json is served", st == 200 and '"openapi"' in b and fx.MARK not in b, st)

        # the reads a public server leaves out
        for op in dropped:
            st, b, _h = call(port, "GET", read_path(op))
            check(
                f"public read left out, {op.name}: refused 404 as not public",
                st == 404 and kind_of(b) == "not-public",
                (st, b[:160]),
            )

        # the inputs a public read does not take
        for op in served:
            hidden = sorted(set(op.inputs) - set(op.schema(public=True)["properties"]))
            for name in hidden:
                st, b, _h = call(
                    port, "GET", read_path(op) + ("&" if "?" in read_path(op) else "?") + f"{name}=x"
                )
                check(
                    f"public read {op.name}: its input {name} is refused (400), not ignored",
                    st == 400 and name in b,
                    (st, b[:200]),
                )
        check("public: some inputs are hidden (the loop above ran)", any(
            set(op.inputs) - set(op.schema(public=True)["properties"]) for op in served))  # fmt: skip

        # every write, every job, by its own route
        for op in acting:
            st, b, _h = call(port, op.method, route(op), {"by": "person:x"}, headers={"X-EVH-Data": "1"})
            check(
                f"public {op.kind} {op.name} ({op.method} {op.route}): refused 403",
                st == 403 and kind_of(b) == "not-public",
                (st, b[:160]),
            )
        for method, path, body in (
            ("POST", "/api/v1/jobs", {"operation": "run", "inputs": {}}), ("GET", "/api/v1/jobs", None),
            ("GET", "/api/v1/jobs/j1", None), ("GET", "/api/v1/jobs/j1/log", None), ("GET", "/api/v1/jobs/j1/files/a.csv", None),
            ("POST", "/api/v1/jobs/j1/stop", {}), ("POST", "/api/v1/jobs/j1/resume", {}),
            ("POST", "/api/v1/estimate", {"operation": "run", "inputs": {"system": fx.SYSTEMS[0], "dataset": fx.DS}}),
            ("GET", "/api/v1/session?token=x", None), ("GET", "/api/v1/session", None),
        ):  # fmt: skip
            st, b, _h = call(port, method, path, body, headers={"X-EVH-Data": "1"})
            check(
                f"public {method} {path.split('?')[0]}: refused 403",
                st == 403 and kind_of(b) == "not-public",
                (st, b[:160]),
            )
        for method in ("PUT", "DELETE"):
            st, _b, _h = call(port, method, "/api/v1/goals/hg", {}, headers={"X-EVH-Data": "1"})
            check(f"public {method} /api/v1/goals/hg: refused", st in (403, 404, 405), st)
        st, _b, _h = call(port, "GET", "/api/v1/nothing-here")
        check("public: a path that is no route is 404", st == 404, st)
        check(
            "public: nothing written, no job started, no call file made by any of it",
            snapshot() == before,
            sorted(set(snapshot()) ^ set(before))[:5],
        )

        # the sheet and an item's input, as the inspector refuses them
        st, b, _h = call(port, "GET", f"/api/sheet?dataset={fx.DS}")
        check(
            "public: the sheet is refused (the inspector's own rule)",
            st in (400, 403, 404) and fx.MARK not in b,
            (st, b[:160]),
        )
        st, b, _h = call(port, "GET", f"/api/sheet?dataset={fx.DS}&format=csv")
        check("public: the sheet's CSV is refused", st in (403, 404) and fx.MARK not in b, (st, b[:160]))
        st, b, _h = call(
            port, "GET", f"/api/item?arms={urllib.parse.quote(ARM)}&item=t01_login&ref=gold/{fx.DS}"
        )
        check(
            "public: the inspector's item answer carries no marker (text: hidden, outputs and references published)",
            st in (200, 400, 403, 404) and fx.MARK not in b,
            (st, b[:300]),
        )

        # Host and Origin
        st, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Host": "evil.example"})
        check("public: a foreign Host is 403", st == 403, st)
        st, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Origin": "https://evil.example"})
        check("public: a foreign Origin is 403", st == 403, st)
        st, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Origin": f"http://127.0.0.1:{port}"})
        check("public: its own Origin is served", st == 200, st)
        st, _b, _h = call(
            port, "GET", "/api/v1/goals", headers={"Authorization": "Bearer x", "Cookie": "evh_token=x"}
        )
        check("public: a token that is sent is ignored, not needed", st == 200, st)
        check("public: the whole of it left the project as it was", snapshot() == before)
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    # ── the rate limit counts /api/v1 ──────────────────────────────────────────────────────────────────────────
    srv, port, _lines = fx.serve_public(proj, env, "--rate", "5")
    try:
        got = [call(port, "GET", "/api/v1/goals")[0] for _ in range(8)]
        check(
            "public: the rate limit counts /api/v1 reads (5 a minute: the sixth is 429)",
            got[:5] == [200] * 5 and 429 in got[5:],
            got,
        )
        st, b, h = call(port, "GET", "/api/v1/goals")
        check(
            "public: the refusal says it is the viewer's",
            st == 429 and h.get("X-EVH-Viewer") == "1" and "a minute" in b,
            (st, b),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    # ── behind a proxy: unchanged, the Workbench and the API still refused ─────────────────────────────────────
    srv, port, _lines = _serve.start(proj, env, "--behind-proxy", "evals.example", "--bind", "127.0.0.1")
    try:
        for path in ("/api/v1/goals", "/workbench/"):
            st, _b, _h = call(port, "GET", path, headers={"Host": "evals.example"})
            check(f"behind a proxy: {path} is still 404", st == 404, st)
    finally:
        srv.terminate()
        srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
