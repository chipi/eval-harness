#!/usr/bin/env python3
"""The model's first entity, the goal (RFC-032 step 1), through both surfaces.

    python tests/test_model_goals.py

In a project `evh init --tutorial` makes, with a dataset, its gold reference and a run: a goal made with `evh goal-new`
is listed and shown by the command line and by the API alike (the same JSON); `goal-set` changes one field and keeps
the file's comments; a field the schema refuses, or a dataset that does not exist, is refused with the field it is at
and nothing written; each save is in the goal's history with who made it; `goal-status` says where it stands and the
next step; the API refuses a write with no data header, no `by`, or an agent with no `for`; a goal being written by a
job is refused; data in an older format is refused; and the registry wires every operation into evh, the MCP server's
lists and the API's.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-goals-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-model-goals",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError("the server did not start")


def call(port: int, method: str, path: str, body: dict | None = None, data: bool = True) -> tuple[int, dict]:
    """One API call with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}"}
    if data:
        h["X-EVH-Data"] = "1"
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"text": raw.decode(errors="replace")[-500:]}


GOAL = proj / "data" / "goals" / "tickets_summary.yaml"
SETS = [
    "title=Ticket summaries", "statement=A one-line summary of a support ticket for the person triaging it.",
    "decision=Which system writes the summary.", "success_criteria.primary.measure=overlap_f1",
    "success_criteria.primary.direction=higher", "datasets.0.dataset_id=tk_v1", "datasets.0.role=test",
]  # fmt: skip

try:
    r = evh("init", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the goal test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    (proj / "data" / "systems" / "one_v1.yaml").write_text(
        "system_id: one_v1\nparams:\n  provider: echo\n  sentences: 1\n"
    )
    r = r if r.returncode else evh("run", "--system", "one_v1", "--dataset", "tk_v1")
    r = r if r.returncode else evh("catalog")
    check(
        "setup: a project with a dataset, its gold reference, a run and its catalog",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )

    made = evh("goal-new", "tickets_summary", *(x for s in SETS for x in ("--set", s)))
    check(
        "goal-new makes the goal", made.returncode == 0 and GOAL.is_file(), (made.stdout + made.stderr)[-300:]
    )
    again = evh("goal-new", "tickets_summary", "--set", "title=x")
    check(
        "goal-new refuses an id that is taken",
        again.returncode == 1 and "ERROR (would-overwrite)" in again.stderr,
        again.stderr[-200:],
    )

    GOAL.write_text(GOAL.read_text().replace("title:", "# what a person calls it\ntitle:", 1))
    s = evh("goal-set", "tickets_summary", "--set", "status=active")
    text = GOAL.read_text()
    check(
        "goal-set changes one field and keeps the file's comments",
        s.returncode == 0 and "# what a person calls it" in text and "status: active" in text,
        (s.stderr[-200:], text[:300]),
    )
    before = GOAL.read_text()
    bad = evh("goal-set", "tickets_summary", "--set", "datasets.0.dataset_id=nope_v1", "--json")
    bad2 = evh("goal-set", "tickets_summary", "--set", "success_criteria.primary.direction=sideways")
    check(
        "a dataset that does not exist, or a value the schema refuses, is refused with its field; nothing written",
        bad.returncode == 1
        and "ERROR (invalid-file)" in bad.stderr
        and "datasets.0.dataset_id: no dataset 'nope_v1'" in bad.stderr
        and bad2.returncode == 1
        and "success_criteria.primary.direction" in bad2.stderr
        and GOAL.read_text() == before,
        (bad.stderr[-300:], bad2.stderr[-300:]),
    )
    h = result(evh("goal-history", "tickets_summary", "--json"))
    check(
        "each save is in the goal's history, newest first, with who made it and what it was",
        [x["by"] for x in h["saves"]] == ["person:tester", "person:tester"]
        and h["saves"][1]["was"] is None
        and h["saves"][0]["was"]["title"] == "Ticket summaries",
        h,
    )
    st = result(evh("goal-status", "tickets_summary", "--json"))
    d = st["datasets"][0]
    check(
        "goal-status: the dataset made and materialized, its reference, its run, no baseline yet, and that next step",
        d["made"] and d["materialized"] and d["references"] == ["gold/tk_v1"] and d["runs"] == 1
        and d["baseline"] is None and st["next"]["what"] == "promote a baseline on tk_v1",
        st,
    )  # fmt: skip

    srv, port = serve()
    try:
        cli = {
            name: result(evh(name, *args, "--json"))
            for name, args in (
                ("goal-list", ()),
                ("goal-show", ("tickets_summary",)),
                ("goal-status", ("tickets_summary",)),
            )
        }
        api = {
            "goal-list": call(port, "GET", "/goals")[1].get("result"),
            "goal-show": call(port, "GET", "/goals/tickets_summary")[1].get("result"),
            "goal-status": call(port, "GET", "/goals/tickets_summary/status")[1].get("result"),
        }
        check(
            "the API's resources give the command line's answers (list, show, status)", api == cli, (api, cli)
        )
        code, body = call(
            port,
            "PATCH",
            "/goals/tickets_summary",
            {"set": {"title": "Ticket summaries, one line"}, "by": "person:api"},
        )
        check(
            "PATCH changes the goal through the model, recorded as who sent it",
            code == 200
            and body["result"]["changed"]
            and result(evh("goal-history", "tickets_summary", "--json"))["saves"][0]["by"] == "person:api",
            (code, body),
        )
        refusals = {
            "no data header": call(
                port, "PATCH", "/goals/tickets_summary", {"set": {"title": "x"}, "by": "person:a"}, data=False
            )[0],
            "no by": call(port, "PATCH", "/goals/tickets_summary", {"set": {"title": "x"}})[0],
            "an agent with no for": call(
                port, "PATCH", "/goals/tickets_summary", {"set": {"title": "x"}, "by": "agent:bot"}
            )[0],
            "an input it does not take": call(
                port, "PATCH", "/goals/tickets_summary", {"sett": {}, "by": "person:a"}
            )[0],
            "a field the schema refuses": call(
                port,
                "PATCH",
                "/goals/tickets_summary",
                {"set": {"success_criteria.primary.direction": "up"}, "by": "person:a"},
            )[0],
            "no such goal": call(port, "GET", "/goals/nope")[0],
        }
        check(
            "the API refuses: no data header 403, no by 400, an agent with no for 400, an unknown input 400, the schema 422, no such goal 404",
            refusals == {"no data header": 403, "no by": 400, "an agent with no for": 400, "an input it does not take": 400,
                         "a field the schema refuses": 422, "no such goal": 404},
            refusals,
        )  # fmt: skip
    finally:
        srv.terminate()
        srv.wait(timeout=20)

    # A goal being written by a job: its lock is held, and a save is refused rather than waiting on it.
    holder = proj / "hold_goal.py"
    holder.write_text(
        "import sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from evaluation_harness import _jobs\n"
        "with _jobs.holding([('goal:tickets_summary', True)], 'job-x'):\n"
        "    print('held', flush=True)\n"
        "    time.sleep(60)\n"
    )
    held = subprocess.Popen(
        [sys.executable, str(holder), str(HARNESS)], cwd=proj, env=env, stdout=subprocess.PIPE, text=True
    )
    try:
        assert held.stdout is not None
        held.stdout.readline()
        busy = evh("goal-set", "tickets_summary", "--set", "status=paused")
        check(
            "a goal a job is writing is refused, naming it, not waited on",
            busy.returncode == 1 and "ERROR (not-allowed)" in busy.stderr and "job-x" in busy.stderr,
            busy.stderr[-300:],
        )
    finally:
        held.kill()
        held.wait(timeout=10)

    stamp = proj / "data" / "project.yaml"
    kept = stamp.read_text()
    stamp.unlink()
    old = evh("goal-list")
    stamp.write_text(kept)
    check(
        "data in an older format is refused by the model",
        old.returncode == 1 and "ERROR (old-format)" in old.stderr,
        old.stderr[-200:],
    )

    from evaluation_harness import _api, mcp_server, ops
    from evaluation_harness.cli import COMMANDS

    wired = []
    for op in ops.OPS.values():
        if COMMANDS.get(op.name, ("",))[0] != "op_command.py":
            wired.append(f"{op.name}: not an evh command")
        if (op.kind == "read") != (op.name in mcp_server.READ_TOOLS and op.name in mcp_server.JSON):
            wired.append(f"{op.name}: MCP lists")
        if (op.kind != "read") != (op.name in mcp_server.NOT_TOOLS and op.name in _api.NOT_SERVED):
            wired.append(f"{op.name}: NOT_TOOLS / NOT_SERVED")
        if mcp_server.parser_of(op.name).prog != f"evh {op.name}":
            wired.append(f"{op.name}: parser_of")
    check(
        "every operation is an evh command, a read an MCP tool, a write neither tool nor job; parser_of makes its parser",
        not wired,
        wired,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
