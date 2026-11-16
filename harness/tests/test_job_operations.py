#!/usr/bin/env python3
"""A job names an operation and its typed inputs (RFC-032 step 9 P3, step 2): the record, the runner, the routes.

    python tests/test_job_operations.py

In a throwaway tutorial project ($0, offline). First without a server, on synthetic operations (tests/_job_ops.py) that
declare what the pilots do not: a spend without its cap, a body that repeats a part, a call by an agent with no person,
a reason that is no field of a job, an unknown input, an input outside its pattern or enum, a system that does not exist,
the defaults filled, the locks from the declaration, a run id made for a resumable operation (and a record with none for
one that is not), an upload kept and an artifact placed in the job's folder, a resume that gives the new job what the
stopped one left of its cap and is refused above one repeat or while the job runs. Then a real `evh catalog-serve` and the
two pilots, cost-report (work) and round-close (decision), through their resource routes, through POST /api/v1/jobs and
through `evh jobs-start`: 202 with the job, the record's shape (operation, inputs, by, locks, env, created_at, harness; no
command, argv or reason), a child started as `cli.py <operation> --json --inputs-file`, its log live, its envelope in
result.json, its actor the job's; a refusal before a job exists (no data header 403, no `by`, a part repeated in the body,
an input the operation does not take, the old shape for an operation, an operation that is not one); a job that fails
says why (`refusal`); a second job of a goal waits for the first's lock and is stopped; the OpenAPI document describes
both with 202 and their locks.
"""

import base64
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

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _job_ops
KIT = HERE.parent / "tutorial"
os.environ.setdefault("EVAL_STORE", "files")
import _job_ops  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _api, _common, _format, _jobs, ops  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.ops import registry  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-jobops-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-jobops")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)
SERVERS: list[subprocess.Popen] = []


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return port, (proj / ".build" / "api-token").read_text().strip()


def call(method, path, body=None, data_header=True):
    h = {"Host": f"127.0.0.1:{PORT}", "Authorization": f"Bearer {TOKEN}"}
    if data_header:
        h["X-EVH-Data"] = "1"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def until(job_id, states=("succeeded", "failed", "cancelled", "lost"), seconds=120):
    end = time.monotonic() + seconds
    j: dict = {}
    while time.monotonic() < end:
        _st, j = call("GET", f"/api/v1/jobs/{job_id}")
        if j.get("state") in states:
            return j
        time.sleep(0.2)
    return j


def on_disk(job_id, name="job.json"):
    return json.loads((proj / ".build" / "jobs" / job_id / name).read_text())


def log_of(job_id):
    return call("GET", f"/api/v1/jobs/{job_id}/log?from=0")[1].get("log", "")


def refused(fn, *args, **kw):
    """(status, message) of the Refused a call raises, or None."""
    try:
        fn(*args, **kw)
    except _api.Refused as exc:
        return exc.status, str(exc)
    return None


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    (data / "goals").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import",
            "--sheet",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "g",
            "--by",
            "o",
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
            "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
        )
    )  # fmt: skip
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        )
        r = r if r.returncode else evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
    check(
        "setup: the tutorial dataset, gold and two arms run", r.returncode == 0, (r.stdout + r.stderr)[-300:]
    )
    runs = sorted(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_lead2_v1_"))
    lead2_run = runs[-1] if runs else ""

    # ── the job machinery on synthetic operations, in this process ────────────────────────────────────────────────
    os.environ["EVAL_HOME"] = str(proj)
    _common.project_root.cache_clear()
    real_start, _jobs.start = (
        _jobs.start,
        lambda job_id: 0,
    )  # the record is the subject; no supervisor is started
    registry.OPS.update({op.name: op for op in _job_ops.ALL})
    try:
        by = "person:ana"
        ok = {"system": "tickets_lead1_v1"}

        def start(name, inputs, **kw):
            kw = {"by": by, "reason": None, "max_cost_usd": None, "for_": None} | kw
            return _api.start_job(name, inputs, **kw)

        check(
            "a spending operation without max_cost_usd, with a zero one, or with a boolean one is refused before a job exists",
            all(
                (r := refused(start, "t-spend", ok, max_cost_usd=cap))
                and r[0] == 400
                and "max_cost_usd" in r[1]
                for cap in (None, 0, -1, True)
            ),
        )
        check(
            "an operation that does not spend takes no max_cost_usd",
            (r := refused(start, "t-plain", {}, max_cost_usd=1)) is not None and "does not spend" in r[1],
            r,
        )
        check(
            "no `by` is refused (every job records who acted), and so is an agent without the person it acts for, and a "
            "person with one",
            all(
                (r := refused(start, "t-plain", {}, by=who, for_=whom)) and r[0] == 400
                for who, whom in ((None, None), ("", None), ("agent:bot", None), ("person:ana", "person:bea"))
            ),
        )
        check(
            "a reason is no field of a job (it is an input): refused, saying which input it is for a decision",
            (r := refused(start, "t-decide", {"study": "g/s", "reason": "x y z"}, reason="why")) is not None
            and "reason is not a field of a job" in r[1]
            and "the reason input" in r[1],
            r,
        )
        for what, name, inputs, status, needle in (
            ("an input the operation does not take", "t-plain", {"nope": 1}, 400, "nope"),
            ("a required input missing", "t-spend", {"dataset": "d"}, 400, "system"),
            ("a text outside its pattern", "t-spend", {**ok, "name": "A1"}, 400, "does not match"),
            ("a value outside its enum", "t-spend", {**ok, "kind": "z"}, 400, "not one of"),
            ("a number given as text", "t-spend", {**ok, "repeat": "two"}, 400, "not of type"),
            (
                "two of an exclusive group",
                "t-spend",
                {**ok, "name": "x", "kind": "a"},
                400,
                "should not be valid",
            ),
            ("a system that does not exist", "t-spend", {"system": "no_such_v1"}, 404, "no system"),
            ("inputs that are not an object", "t-plain", ["x"], 400, "JSON object"),
        ):
            r = refused(start, name, inputs, **({"max_cost_usd": 1} if name == "t-spend" else {}))
            check(
                f"refused before a job exists: {what}", r is not None and r[0] == status and needle in r[1], r
            )

        j = start("t-spend", {**ok, "dataset": "tk_v1"}, max_cost_usd=0.5)
        rec = on_disk(j["id"])
        check(
            "the record: operation, inputs (the defaults filled), by, locks, env, created_at, harness, run_id for a "
            "resumable operation; no command, argv or reason",
            set(rec) == {"id", "operation", "inputs", "by", "locks", "env", "run_id", "created_at", "harness"}
            and rec["operation"] == "t-spend"
            and rec["inputs"] == {**ok, "dataset": "tk_v1", "repeat": 1, "run_id": rec["run_id"]}
            and rec["by"] == by
            and rec["env"] == {"EVAL_MAX_COST_USD": "0.5"}
            and rec["run_id"] == f"tickets_lead1_v1_{j['id']}"
            and on_disk(j["id"], "inputs.json") == rec["inputs"],
            rec,
        )
        check(
            "its locks come from the declaration: the system exclusive, the dataset shared, the function's own, the project "
            "shared, sorted",
            rec["locks"]
            == [
                ["dataset:tk_v1", False],
                ["extra:tickets_lead1_v1", True],
                ["project", False],
                ["system:tickets_lead1_v1", True],
            ],
            rec["locks"],
        )
        check(
            "read back (the state file beside it) it is the record and the state; the job's id is its folder's",
            (r := _jobs.read(j["id"]))["operation"] == "t-spend"
            and r["state"] in ("queued", "lost")
            and r["inputs"] == rec["inputs"]
            and "command" not in r
            and any(x["id"] == j["id"] for x in _jobs.list_jobs()),
        )
        j2 = start("t-plain", {"note": "n"}, by="agent:bot", for_="person:bea")
        rec2 = on_disk(j2["id"])
        check(
            "an operation that is not resumable has no run_id in its record, one that holds nothing but the project holds it "
            "shared, and an agent's job carries the person it acts for in its environment",
            "run_id" not in rec2
            and rec2["locks"] == [["project", False]]
            and rec2["env"] == {"EVH_FOR": "person:bea"}
            and rec2["by"] == "agent:bot",
            rec2,
        )
        j3 = start("t-spend", {**ok, "run_id": "mine_1"}, max_cost_usd=1)
        check("a run id the call names is kept", on_disk(j3["id"])["run_id"] == "mine_1", on_disk(j3["id"]))
        jm = start("t-migrate", {})
        check(
            "a migration holds the whole project exclusive, and nothing else",
            on_disk(jm["id"])["locks"] == [["project", True]],
            on_disk(jm["id"])["locks"],
        )
        jd = start("t-decide", {"study": "g/s", "reason": "three whole words"})
        check(
            "a decision's reason is one of its inputs, and its lock is named by the input",
            on_disk(jd["id"])["inputs"] == {"study": "g/s", "reason": "three whole words"}
            and on_disk(jd["id"])["locks"] == [["project", False], ["study:g/s", True]],
        )

        # files: an upload is kept, an artifact is a name in the job's folder
        up = {"name": "sheet.csv", "content_base64": base64.b64encode(b"a,b\n1,2\n").decode()}
        jf = start("t-spend", {**ok, "sheet": up, "out": "report.csv"}, max_cost_usd=1)
        recf = on_disk(jf["id"])
        kept = proj / recf["inputs"]["sheet"]
        check(
            "an upload is kept under .build/uploads/<sha256>/ and the job is given its path; an artifact is a path in the "
            "job's own folder",
            recf["inputs"]["sheet"].startswith(".build/uploads/")
            and kept.read_bytes() == b"a,b\n1,2\n"
            and recf["inputs"]["out"] == f".build/jobs/{jf['id']}/report.csv",
            recf["inputs"],
        )
        for what, bad in (
            ("an upload that is not base64", {"name": "s.csv", "content_base64": "!!!"}),
            ("an upload with a name that is no file name", {"name": "s s.csv", "content_base64": "YQ=="}),
            ("a file given as text", "tickets/x.csv"),
            ("an upload with a field more", {**up, "path": "/etc/passwd"}),
        ):
            r = refused(start, "t-spend", {**ok, "sheet": bad}, max_cost_usd=1)
            check(f"refused: {what}", r is not None and r[0] in (400, 413), r)
        jx = start("t-spend", {**ok, "out": "../escape.csv"}, max_cost_usd=1)
        check(
            "an artifact named with a path is only its file name, in the job's folder",
            on_disk(jx["id"])["inputs"]["out"] == f".build/jobs/{jx['id']}/escape.csv",
            on_disk(jx["id"])["inputs"],
        )

        # resume: the stopped job's cap, less what it spent; a new run id; the run it continues
        jr = start("t-spend", {**ok}, max_cost_usd=1)
        (proj / ".build/jobs" / jr["id"] / "state.json").write_text(
            json.dumps({"state": "failed", "exit": 1})
        )
        (proj / ".build/jobs" / jr["id"] / "spent.json").write_text(json.dumps({"spent_usd": 0.25}))
        new = _api.resume_job(jr["id"])
        recn = on_disk(new["id"])
        check(
            "a resume is a new job of the same operation: it continues the run, writes a new one, is given the cap the "
            "stopped job left, and holds the same locks",
            recn["operation"] == "t-spend"
            and recn["inputs"]["resume"] == on_disk(jr["id"])["run_id"]
            and recn["inputs"]["run_id"] == f"tickets_lead1_v1_{new['id']}"
            and recn["run_id"] == recn["inputs"]["run_id"]
            and abs(float(recn["env"]["EVAL_MAX_COST_USD"]) - 0.75) < 1e-9
            and recn["locks"] == on_disk(jr["id"])["locks"]
            and recn["by"] == by,
            recn,
        )
        (proj / ".build/jobs" / new["id"] / "state.json").write_text(
            json.dumps({"state": "succeeded", "exit": 0})
        )
        r = refused(_api.resume_job, new["id"])
        check(
            "a job that succeeded is not resumed",
            r is not None and r[0] == 409 and "nothing to resume" in r[1],
            r,
        )
        jq = start("t-spend", {**ok, "repeat": 3}, max_cost_usd=1)
        (proj / ".build/jobs" / jq["id"] / "state.json").write_text(
            json.dumps({"state": "failed", "exit": 1})
        )
        r = refused(_api.resume_job, jq["id"])
        check(
            "a run with repeat above 1 is not resumed", r is not None and r[0] == 409 and "repeat" in r[1], r
        )
        (proj / ".build/jobs" / jr["id"] / "spent.json").write_text(json.dumps({"spent_usd": 1}))
        r = refused(_api.resume_job, jr["id"])
        check(
            "a job that spent all its cap is not resumed",
            r is not None and r[0] == 409 and "nothing is left to resume with" in r[1],
            r,
        )
        jp = start("t-plain", {})
        (proj / ".build/jobs" / jp["id"] / "state.json").write_text(
            json.dumps({"state": "failed", "exit": 1})
        )
        r = refused(_api.resume_job, jp["id"])
        check(
            "an operation without `resume` is not resumed",
            r is not None and r[0] == 409 and "only a run is resumed" in r[1],
            r,
        )
    finally:
        _jobs.start = real_start
        for op in _job_ops.ALL:
            registry.OPS.pop(op.name, None)

    # ── the two pilots, through a real server ─────────────────────────────────────────────────────────────────────
    r = evh("catalog")
    check("setup: the catalog the server serves", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    PORT, TOKEN = serve()

    def open_round(*extra):
        return evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", *extra)

    r = open_round(
        "--hypothesis",
        "how many leading sentences summarise a ticket",
        "--keep",
        "tickets_lead1_v1,tickets_lead2_v1",
    )
    check("setup: round r1 opened", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    R1 = "/api/v1/goals/tickets_summary/rounds/r1/close"
    conclusion = "lead two wins on this slice and is promoted"
    body = {"conclusion": conclusion, "promote": lead2_run, "by": "person:ana"}

    st1, _ = call("POST", R1, body, data_header=False)
    st2, _ = call("POST", R1, {k: v for k, v in body.items() if k != "by"})
    st3, _ = call("POST", R1, {**body, "by": "agent:bot"})
    st4, e4 = call("POST", R1, {**body, "goal": "tickets_summary"})
    st5, e5 = call("POST", R1, {**body, "round": "r1"})
    st6, e6 = call("POST", R1, {**body, "reason": "x"})
    st7, e7 = call("POST", R1, {"by": "person:ana"})
    st8, e8 = call("POST", R1, {**body, "max_cost_usd": 1})
    st9, e9 = call("POST", R1, {**body, "adapter": "x.py:Y"})
    st10, e10 = call("POST", R1, [1])
    check(
        "refused before a job exists: no data header 403; no `by` 400; an agent with no person 400; a part repeated in the "
        "body (as itself, or as its input) 400; an input the operation does not take, a reason among them 400; no "
        "conclusion 400; a cap on an operation that does not spend 400; a body that is not an object 400",
        (st1, st2, st3, st4, st5, st6, st7, st8, st9, st10)
        == (403, 400, 400, 400, 400, 400, 400, 400, 400, 400)
        and "goal" in e4["error"]
        and "round" in e5["error"]
        and "reason" in e6["error"]
        and "conclusion" in e7["error"]
        and "does not spend" in e8["error"]
        and "adapter" in e9["error"],
        (st1, st2, st3, st4, st5, st6, st7, st8, st9, st10, e6, e9),
    )
    check(
        "none of those made a job",
        not any(
            on_disk(x.name).get("operation") == "round-close"
            for x in (proj / ".build" / "jobs").iterdir()
            if (x / "job.json").exists()
        ),
    )

    st, j = call("POST", R1, body)
    done = until(j.get("id"))
    rec = on_disk(j["id"])
    print(f"      job.json of POST {R1}:\n{json.dumps(rec, indent=2, sort_keys=True)}")
    round_doc = yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml"))
    check(
        "POST /goals/{goal}/rounds/{round}/close: 202 with the job; its record is operation, inputs (the route's parts "
        "and the body, merged), by, locks (the goal exclusive, the project shared), env, created_at, harness",
        st == 202
        and j["operation"] == "round-close"
        and set(rec) == {"id", "operation", "inputs", "by", "locks", "env", "created_at", "harness"}
        and rec["inputs"]
        == {"goal": "tickets_summary", "round": "r1", "conclusion": conclusion, "promote": lead2_run}
        and rec["by"] == "person:ana"
        and rec["locks"] == [["goal:tickets_summary", True], ["project", False]]
        and rec["env"] == {}
        and on_disk(j["id"], "inputs.json") == rec["inputs"],
        (st, rec),
    )
    check(
        "the job ran the command as a child through the prelude: succeeded, exit 0, the round closed with the conclusion, "
        "the run promoted, the actor the job's `by`",
        done.get("state") == "succeeded"
        and done.get("exit") == 0
        and round_doc.get("status") == "closed"
        and round_doc["conclusion"]["text"] == conclusion
        and round_doc["conclusion"]["promoted_run"] == lead2_run
        and round_doc["conclusion"]["actor"]["name"] == "ana",
        (done.get("state"), done.get("refusal"), round_doc.get("conclusion"), log_of(j["id"])[-500:]),
    )
    res = on_disk(j["id"], "result.json")
    log = log_of(j["id"])
    check(
        "its envelope is in result.json (command, version, result.blocks), and its log has what it printed, the promotion's "
        "lines too (a call, no longer a process of its own)",
        res.get("command") == "round-close"
        and res["result"]["blocks"]
        and "round r1 of tickets_summary closed; " + lead2_run + " promoted" in log
        and "version" in log,
        (res, log[-400:]),
    )
    check(
        "the promotion's named values reach the envelope (the baseline's version and evidence), as a call inside it",
        (res["result"].get("values") or {}).get("version") is not None,
        res["result"].get("values"),
    )
    base = _runstore.listdir(proj, "baselines")
    check("the promotion wrote the baseline", bool(base), base)

    # the same inputs through POST /jobs; a closed round: the job fails and says why
    _st, again = call("POST", R1, body)
    st, viaj = call(
        "POST", "/api/v1/jobs",
        {"operation": "round-close", "inputs": rec["inputs"], "by": "person:ana"},
    )  # fmt: skip
    d_again, d_viaj = until(again["id"]), until(viaj["id"])
    print(
        f"      job.json of POST /api/v1/jobs (round-close):\n{json.dumps(on_disk(viaj['id']), indent=2, sort_keys=True)}"
    )
    check(
        "the same inputs through POST /api/v1/jobs record the same inputs as the resource route",
        st == 202
        and on_disk(viaj["id"])["inputs"] == on_disk(again["id"])["inputs"] == rec["inputs"]
        and on_disk(viaj["id"])["locks"] == rec["locks"],
        (on_disk(viaj["id"])["inputs"], rec["inputs"]),
    )
    check(
        "a job that is refused says so: failed, exit 1, refusal not-allowed (the round is closed), the message in its log",
        d_again.get("state") == d_viaj.get("state") == "failed"
        and d_again.get("refusal") == "not-allowed"
        and "already closed" in log_of(again["id"]),
        (d_again.get("state"), d_again.get("refusal"), log_of(again["id"])[-300:]),
    )
    st, nope = call(
        "POST", "/api/v1/goals/no_such_goal/rounds/r1/close", {"conclusion": conclusion, "by": "person:ana"}
    )
    dn = until(nope.get("id"))
    check(
        "a goal that does not exist is the job's refusal, not the route's: 202, then failed with refusal not-found",
        st == 202 and dn.get("state") == "failed" and dn.get("refusal") == "not-found",
        (st, dn.get("state"), dn.get("refusal"), log_of(nope.get("id", ""))[-200:]),
    )

    # POST /jobs: the generic way, and what it refuses
    st_a, e_a = call(
        "POST", "/api/v1/jobs", {"command": "round-close", "args": {"goal": "g"}, "by": "person:ana"}
    )
    st_b, e_b = call("POST", "/api/v1/jobs", {"operation": "run", "inputs": {}, "by": "person:ana"})
    st_c, e_c = call(
        "POST",
        "/api/v1/jobs",
        {"operation": "round-close", "inputs": rec["inputs"], "by": "person:ana", "reason": "x"},
    )
    st_d, e_d = call("POST", "/api/v1/jobs", {"operation": "round-close", "inputs": rec["inputs"]})
    st_e, e_e = call(
        "POST", "/api/v1/jobs", {"operation": "round-close", "inputs": {"goal": "g"}, "by": "person:ana"}
    )
    st_f, e_f = call("POST", "/api/v1/jobs", {"operation": "goal-list", "inputs": {}, "by": "person:ana"})
    check(
        "POST /api/v1/jobs refuses: the old shape for an operation (400), an operation that is not a job (404: run is not "
        "one yet, nor is a read), a field beyond {operation, inputs, by, for, max_cost_usd}, no `by`, a missing input",
        (st_a, st_b, st_c, st_d, st_e, st_f) == (400, 404, 400, 400, 400, 404)
        and "is an operation" in e_a["error"]
        and "not an operation that runs as a job" in e_b["error"]
        and "reason" in e_c["error"]
        and "is a required property" in e_e["error"],
        (st_a, st_b, st_c, st_d, st_e, st_f, e_a, e_c),
    )

    # the terminal: jobs-start, with the inputs' names as the operation has them
    r = open_round("--from", "r1", "--keep", "all")
    r = evh(
        "jobs-start", "round-close", "--arg", "goal=tickets_summary", "--arg", "round=r2", "--arg",
        "conclusion=carried on unchanged for the second slice", "--by", "person:cara", "--json",
    )  # fmt: skip
    tj = (
        (json.loads(r.stdout).get("result") or {}).get("values", {}).get("job", {})
        if r.returncode == 0
        else {}
    )
    td = until(tj.get("id", "none"))
    trec = on_disk(tj["id"]) if tj.get("id") else {}
    print(f"      job.json of `evh jobs-start round-close`:\n{json.dumps(trec, indent=2, sort_keys=True)}")
    check(
        "evh jobs-start round-close --arg goal=... --arg round=...: a job of the operation, the actor the terminal's --by, "
        "the same record shape; the round closes",
        r.returncode == 0
        and trec.get("operation") == "round-close"
        and trec["inputs"]
        == {
            "goal": "tickets_summary",
            "round": "r2",
            "conclusion": "carried on unchanged for the second slice",
        }
        and trec["by"] == "person:cara"
        and td.get("state") == "succeeded"
        and yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r2.yaml"))["status"] == "closed",
        (r.returncode, r.stderr[-300:], td.get("state"), trec),
    )
    r2 = evh("jobs-start", "round-close", "--arg", "goal=g", "--reason", "x", "--by", "person:cara")
    r3 = evh("jobs-start", "round-close", "--arg", "goal=g", "--by", "person:cara")
    check(
        "jobs-start refuses what the API refuses: --reason (no field of a job), an input missing",
        r2.returncode != 0
        and "reason is not a field of a job" in r2.stderr
        and r3.returncode != 0
        and "is a required property" in r3.stderr,
        (r2.stderr[-200:], r3.stderr[-200:]),
    )
    sj = evh("jobs-status", tj.get("id", "none"))
    check(
        "jobs-status names the operation and shows the inputs",
        "round-close" in sj.stdout and "inputs: " in sj.stdout and '"round": "r2"' in sj.stdout,
        sj.stdout[-300:],
    )

    # cost-report, a work operation with nothing to lock but the project
    C = "/api/v1/reports/cost"
    st, cj = call("POST", C, {"dataset_id": "tickets_v1", "by": "person:ana"})
    cd = until(cj.get("id"))
    crec = on_disk(cj["id"])
    print(f"      job.json of POST {C}:\n{json.dumps(crec, indent=2, sort_keys=True)}")
    cres = on_disk(cj["id"], "result.json")
    check(
        "POST /reports/cost: 202; its record holds the project shared and no other lock; the job succeeds, its envelope "
        "has the report's lines, its log the same, as it was printed",
        st == 202
        and set(crec) == {"id", "operation", "inputs", "by", "locks", "env", "created_at", "harness"}
        and crec["operation"] == "cost-report"
        and crec["inputs"] == {"dataset_id": "tickets_v1"}
        and crec["locks"] == [["project", False]]
        and cd.get("state") == "succeeded"
        and cres["command"] == "cost-report"
        and any("NO provider bill" in ln for b in cres["result"]["blocks"] for ln in b.get("lines", []))
        and "NO provider bill" in log_of(cj["id"]),
        (st, cd.get("state"), cd.get("refusal"), log_of(cj["id"])[-300:]),
    )
    st, none_ = call("POST", C, {"by": "person:ana"})
    st2, nodata = call("POST", C, {"dataset_id": "nothing", "by": "person:ana"})
    d_none, d_nodata = until(none_.get("id")), until(nodata.get("id"))
    check(
        "cost-report with no input reports every dataset; a dataset with no runs is the job's refusal (not-found)",
        (st, st2) == (202, 202)
        and d_none.get("state") == "succeeded"
        and on_disk(none_["id"])["inputs"] == {}
        and d_nodata.get("state") == "failed"
        and d_nodata.get("refusal") == "not-found"
        and "no runs matched" in log_of(nodata["id"]),
        (d_none.get("state"), d_nodata.get("state"), d_nodata.get("refusal")),
    )
    st, vj = call(
        "POST",
        "/api/v1/jobs",
        {"operation": "cost-report", "inputs": {"dataset_id": "tickets_v1"}, "by": "person:ana"},
    )
    until(vj.get("id"))
    print(
        f"      job.json of POST /api/v1/jobs (cost-report):\n{json.dumps(on_disk(vj['id']), indent=2, sort_keys=True)}"
    )
    check(
        "POST /jobs {operation: cost-report} records the inputs the route's call did",
        st == 202
        and on_disk(vj["id"])["inputs"] == crec["inputs"]
        and on_disk(vj["id"])["locks"] == crec["locks"],
    )
    st, e = call("POST", C, {"match": 1, "by": "person:ana"})
    check(
        "an input of the wrong type is refused by the schema",
        st == 400 and "not of type" in e["error"],
        (st, e),
    )
    r = evh("jobs-start", "cost-report", "--arg", "dataset_id=tickets_v1", "--by", "person:ana", "--json")
    tc = (
        (json.loads(r.stdout).get("result") or {}).get("values", {}).get("job", {})
        if r.returncode == 0
        else {}
    )
    tcd = until(tc.get("id", "none"))
    check(
        "evh jobs-start cost-report --arg dataset_id=...: the same job",
        r.returncode == 0
        and tcd.get("state") == "succeeded"
        and on_disk(tc["id"])["inputs"] == crec["inputs"],
        (r.returncode, r.stderr[-200:], tcd.get("state")),
    )

    # locks: a second job of a goal waits for the first's lock; stopped, it is cancelled; the lock freed, it runs
    r = open_round("--from", "r2", "--keep", "all")
    held = _jobs.take_locks([("goal:tickets_summary", True)], "the test holding the goal")
    R3 = "/api/v1/goals/tickets_summary/rounds/r3/close"
    st, q = call("POST", R3, {"conclusion": "the third slice closes later", "by": "person:ana"})
    end = time.monotonic() + 30
    while (
        time.monotonic() < end
        and (call("GET", f"/api/v1/jobs/{q['id']}")[1].get("waiting_for") or {}).get("lock")
        != "goal:tickets_summary"
    ):
        time.sleep(0.1)
    waiting = call("GET", f"/api/v1/jobs/{q['id']}")[1]
    r_stop = evh("jobs-stop", q["id"])
    stopped = call("GET", f"/api/v1/jobs/{q['id']}")[1]
    for fd in held:
        os.close(fd)
    check(
        "a job of an operation waits for the lock its declaration names (queued, saying which and who holds it) and is "
        "stopped (cancelled); the round is still open",
        waiting.get("state") == "queued"
        and waiting["waiting_for"] == {"lock": "goal:tickets_summary", "job": "the test holding the goal"}
        and r_stop.returncode == 0
        and stopped.get("state") == "cancelled"
        and yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r3.yaml"))["status"] == "open",
        (waiting.get("state"), waiting.get("waiting_for"), stopped.get("state")),
    )
    st, ok3 = call("POST", R3, {"conclusion": "the third slice closes now", "by": "person:ana"})
    check(
        "and with the lock free the same call runs and closes the round",
        until(ok3["id"]).get("state") == "succeeded"
        and yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r3.yaml"))["status"] == "closed",
    )

    # the document
    st, doc = call("GET", "/api/v1/openapi.json")
    paths = doc["paths"]
    rc = paths["/api/v1/goals/{goal}/rounds/{round}/close"]["post"]
    cr = paths["/api/v1/reports/cost"]["post"]
    post_jobs = paths["/api/v1/jobs"]["post"]["requestBody"]["content"]["application/json"]["schema"][
        "properties"
    ]
    check(
        "the OpenAPI document describes both with a 202, the Job schema, the data header, the parts as path parameters, "
        "a body of the inputs the parts do not fill with by, for and max_cost_usd, and their kind, locks and spend",
        "202" in rc["responses"]
        and "200" not in rc["responses"]
        and rc["responses"]["202"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/Job"}
        and [p["name"] for p in rc["parameters"] if p["in"] == "path"] == ["goal", "round"]
        and any(p["name"] == "X-EVH-Data" for p in rc["parameters"])
        and set(rc["requestBody"]["content"]["application/json"]["schema"]["properties"])
        == {
            "conclusion",
            "promote",
            "confirm_extra_look",
            "override_no_evidence",
            "by",
            "for",
            "max_cost_usd",
        }
        and rc["requestBody"]["content"]["application/json"]["schema"]["required"] == ["conclusion", "by"]
        and rc["x-evh-kind"] == "decision"
        and rc["x-evh-locks"] == {"templates": [{"key": "goal:{goal}", "exclusive": True}]}
        and rc["x-evh-spends"] is False
        and cr["x-evh-kind"] == "work"
        and cr["requestBody"]["content"]["application/json"]["schema"]["required"] == ["by"]
        and cr["x-evh-locks"] == {"templates": []}
        and post_jobs["operation"]["enum"] == sorted(o.name for o in ops.OPS.values() if o.is_job()),
        (rc.get("x-evh-locks"), post_jobs["operation"]),
    )
finally:
    for p in SERVERS:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
