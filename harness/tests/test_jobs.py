#!/usr/bin/env python3
"""Jobs (RFC-026 step 3): one command each, detached, with locks, a log, stop, resume, and a supervisor that may die.

    python tests/test_jobs.py

Every job command has its locks named. Then a real `evh catalog-serve` in a throwaway tutorial project ($0,
offline; a slow arm sleeps per item): a run job without `max_cost_usd`, a decision without `by`, a read asked as a
job and a call without the data header are refused before a job exists; a run job ends `succeeded`, its envelope in
the result and its actor the job's `by`; a second run of the same system waits (`queued`, naming the lock and the
job holding it) and starts when the first is stopped (`cancelled`, its process group gone); a stopped run is resumed
by a new job; a job whose supervisor is killed reads `running (unsupervised)` while its command lives and `lost`
after; an artifact (label-sheet's sheet) is fetched from the job; an upload (import-run's scores) reaches the job;
a new server lists the jobs the old one started. Step 4: a catalog job swaps its pages in with every page served
throughout; while a migration holds the project the server answers 503; data-migrate runs as a job with the server
up, and the server then reads the new store. Step 6: jobs-start, jobs-status, jobs-logs and jobs-stop work on the
same jobs as the API.
"""

import base64
import fcntl
import json
import os
import shutil
import signal
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
KIT = HERE.parent / "tutorial"
from evaluation_harness import _api, _jobs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402

jobs = {c for c, v in _api.registry().items() if v["served"] == "job"}
named = set(_jobs.LOCK_RULES) | _jobs.MIGRATIONS | _jobs.PROJECT_ONLY
check(
    "every job command has its locks named (a rule, a migration, or the project only)",
    jobs <= named,
    sorted(jobs - named),
)

_run_meta, _jobs._run_meta = _jobs._run_meta, lambda run_id: {"config_id": "slow_v1"}
try:
    run_key = {
        k
        for k, _ex in _jobs.locks_for("run", {"system": "slow_v1", "dataset": "tk_v1"})
        if k.startswith("system:")
    }
    rm_key = {
        k
        for k, _ex in _jobs.locks_for("data-rm", {"path": "runs/slow_v1_20261113"})
        if k.startswith("system:")
    }
    capture_key = {
        k for k, _ex in _jobs.locks_for("arm-from-capture", {"as": "slow_v1"}) if k.startswith("system:")
    }
finally:
    _jobs._run_meta = _run_meta
check(
    "a data-rm of a run's folder and an arm-from-capture of a system take the lock a run of that system takes",
    run_key == rm_key == capture_key == {"system:slow_v1"},
    (run_key, rm_key, capture_key),
)

proj = Path(tempfile.mkdtemp(prefix="evh-jobs-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-jobs")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)

SLOW = """import time
from evaluation_harness.adapter import Result, score  # noqa: F401
def call_system(text, params):
    time.sleep(float(params.get("sleep", 1.5)))
    return Result(output=text.split(".")[0] + ".", cost_usd=float(params.get("cost", 0.0)))
"""


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def serve(*extra):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port), *extra],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(200):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, (proj / ".build" / "api-token").read_text().strip()


def call(method, path, body=None, data_header=True):
    h = {"Host": f"127.0.0.1:{PORT}", "Authorization": f"Bearer {TOKEN}"}
    if data_header:
        h["X-EVH-Data"] = "1"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — the test's own server  # nosec B310
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def job(command, args, **extra):
    return call("POST", "/api/v1/jobs", {"command": command, "args": args, **extra})


def until(job_id, states, seconds=120):
    end = time.monotonic() + seconds
    j = {}
    while time.monotonic() < end:
        _st, j = call("GET", f"/api/v1/jobs/{job_id}")
        if j.get("state") in states:
            return j
        time.sleep(0.2)
    return j


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "slow.py").write_text(SLOW)
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t")
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's summaries, for the jobs test", "--by", "t",
        )
    )  # fmt: skip
    _runstore.write_text(proj, "systems/fast_v1.yaml", "system_id: fast_v1\nparams:\n  provider: echo\n")
    _runstore.write_text(
        proj,
        "systems/slow_v1.yaml",
        "system_id: slow_v1\nadapter: slow.py\nparams:\n  provider: echo\n  sleep: 1.5\n  cost: 0.01\n",
    )
    r = r if r.returncode else evh("catalog")
    check(
        "setup: a project with gold, a fast arm and a slow one",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )
    srv, PORT, TOKEN = serve()

    st, j = job("run", {"system": "fast_v1", "dataset": "tk_v1"}, by="person:ana")
    st2, _j = job("run-promote", {"run": "x"}, reason="no one named")
    st3, _j = job("leaderboard", {"dataset-id": "tk_v1"})
    st4, _j = call(
        "POST",
        "/api/v1/jobs",
        {"command": "dataset-profile", "args": {"dataset-id": "tk_v1"}},
        data_header=False,
    )
    check(
        "refused before a job exists: a spending job without max_cost_usd, a decision without by, a read, no data header",
        (st, st2, st3, st4) == (400, 400, 400, 403) and "max_cost_usd" in j.get("error", ""),
        (st, st2, st3, st4, j),
    )
    st, j = job("run", {"system": "fast_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=1)
    done = until(j.get("id"), ("succeeded", "failed")) if st == 202 else {}
    run_id = (done.get("run_id") or "") if done else ""
    m = (
        _runstore.read_json(proj, f"runs/{run_id}/run.json")
        if run_id and _runstore.exists(proj, f"runs/{run_id}/run.json")
        else {}
    )
    check(
        "a run job: 202, then succeeded, its envelope in the result, its run named up front, its actor the job's by",
        st == 202
        and done.get("state") == "succeeded"
        and (done.get("result") or {}).get("command") == "run"
        and m.get("actor", {}).get("name") == "ana",
        (st, {k: done.get(k) for k in ("state", "exit", "refusal", "run_id")}),
    )
    st, lg = call("GET", f"/api/v1/jobs/{j.get('id')}/log?from=0")
    check(
        "its log, followed from an offset",
        st == 200 and lg.get("next", 0) > 0 and "fast_v1" in lg.get("log", ""),
        lg,
    )

    # Locks: a second run of one system waits for the first.
    st, a = job("run", {"system": "slow_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=1)
    until(a["id"], ("running",), 30)
    st, b = job("run", {"system": "slow_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=1)
    time.sleep(1.5)
    _st, bq = call("GET", f"/api/v1/jobs/{b['id']}")
    check(
        "a second run of the same system waits: queued, naming the lock and the job that holds it",
        bq.get("state") == "queued"
        and (bq.get("waiting_for") or {}).get("job") == a["id"]
        and "slow_v1" in (bq.get("waiting_for") or {}).get("lock", ""),
        bq,
    )
    end = time.monotonic() + 60
    while time.monotonic() < end and "[2/6]" not in call("GET", f"/api/v1/jobs/{a['id']}/log")[1].get(
        "log", ""
    ):
        time.sleep(0.2)  # two items written: something for the resume to continue from
    _st, stopped = call("POST", f"/api/v1/jobs/{a['id']}/stop")
    pgid = stopped.get("pgid")
    try:
        os.killpg(pgid, 0)
        gone = False
    except (ProcessLookupError, TypeError):
        gone = True
    check(
        "stop: cancelled, its process group gone",
        stopped.get("state") == "cancelled" and gone,
        (stopped.get("state"), pgid),
    )
    # Stopping a QUEUED job: its supervisor waits in flock for the next lock and holds the ones it took before; it is
    # ended, and those locks are free again (it read `cancelled` while still holding them, a review found).
    os.environ["EVAL_HOME"] = str(proj)
    from evaluation_harness import _common as _c

    _c.project_root.cache_clear()
    held = _jobs.take_locks([("dataset:hold_x", True)], "the test")
    qid = _jobs.new_id()
    _jobs.create("prompt-version", ["who_q", "--text", "x", "--note", "n"], "person:ana", None,
                 [("aaa:first", True), ("dataset:hold_x", True)], job_id=qid)  # fmt: skip
    _jobs.start(qid)
    end = time.monotonic() + 30
    while (
        time.monotonic() < end and (_jobs.read(qid).get("waiting_for") or {}).get("lock") != "dataset:hold_x"
    ):
        time.sleep(0.1)
    spid = _jobs.read(qid).get("supervisor_pid")
    stopped_q = _jobs.stop(qid)
    stat = Path(f"/proc/{spid}/stat")
    # Ended: no such process, or a zombie this test (its parent) has not reaped.
    sup_gone = not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    try:
        fds = _jobs.take_locks([("aaa:first", True)], "the test")
        first_free = True
        for fd in fds:
            os.close(fd)
    except _jobs.Busy:
        first_free = False
    for fd in held:
        os.close(fd)
    check(
        "stop on a queued job: cancelled, its supervisor ended, the lock it had taken free again",
        stopped_q.get("state") == "cancelled" and sup_gone and first_free,
        (stopped_q.get("state"), sup_gone, first_free),
    )
    # A command that waits for a lock says so (it waited in silence; a review, 2026-11-11), and no script waits mutely.
    held = _jobs.take_locks([("goal:wait_g", True)], "job 2026-the-holder")
    waiter_py = proj / "waiter.py"
    waiter_py.write_text(
        "from evaluation_harness import _jobs\n"
        "with _jobs.holding([('goal:wait_g', True)], 'the waiter', _jobs.say_waiting):\n    print('got it')\n"
    )
    w = subprocess.Popen([sys.executable, str(waiter_py)], cwd=proj, env={**env, "PYTHONPATH": str(HERE.parent)},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # fmt: skip
    time.sleep(1.5)
    for fd in held:
        os.close(fd)
    w_out, w_err = w.communicate(timeout=30)
    silent = [
        f"{f.name}:{n}"
        for f in sorted(HERE.glob("*.py"))
        for n, line in enumerate(f.read_text().splitlines(), 1)
        if "holding(" in line and "lambda" in line and ": None" in line
    ]
    check(
        "a command waiting for a lock says which and who holds it, then goes on; no script waits in silence",
        "waiting for goal:wait_g, held by job 2026-the-holder" in w_err and "got it" in w_out and not silent,
        (w_err[-300:], w_out[-100:], silent),
    )
    bdone = until(b["id"], ("succeeded", "failed"), 120)
    check(
        "the waiting job starts when the lock is free, and ends",
        bdone.get("state") == "succeeded",
        (bdone.get("state"), call("GET", f"/api/v1/jobs/{b['id']}/log")[1].get("log", "")[-700:]),
    )
    st, res = call("POST", f"/api/v1/jobs/{a['id']}/resume")
    rdone = until(res.get("id"), ("succeeded", "failed"), 120) if st == 202 else {}
    check(
        "a stopped run is resumed by a new job (run --resume its run id)",
        st == 202
        and rdone.get("state") == "succeeded"
        and "--resume" in rdone.get("argv", [])
        and a.get("run_id") in rdone.get("argv", []),
        (
            st,
            rdone.get("state"),
            rdone.get("argv"),
            call("GET", f"/api/v1/jobs/{res.get('id')}/log")[1].get("log", "")[-600:],
        ),
    )
    st, _x = call("POST", f"/api/v1/jobs/{bdone['id']}/resume")
    check("a succeeded job is not resumed", st == 409, st)
    paid = json.loads((proj / ".build/jobs" / a["id"] / "spent.json").read_text())["spent_usd"]
    rjob = json.loads((proj / ".build/jobs" / res["id"] / "job.json").read_text()) if res.get("id") else {}
    check(
        "the resumed job is given what the stopped one left of its cap, not the cap again",
        paid > 0 and abs(float(rjob.get("env", {}).get("EVAL_MAX_COST_USD", "nan")) - (1 - paid)) < 1e-6,
        (paid, rjob.get("env")),
    )
    st, f = job("run", {"system": "slow_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=0.01)
    fdone = until(f.get("id"), ("succeeded", "failed", "cancelled"), 120) if st == 202 else {}
    st, refusal = call("POST", f"/api/v1/jobs/{f.get('id')}/resume")
    check(
        "a job that spent all its cap is not resumed: nothing is left",
        fdone.get("state") == "failed"
        and st == 409
        and "nothing is left to resume with" in refusal.get("error", ""),
        (fdone.get("state"), st, refusal),
    )

    # A supervisor that dies.
    st, e = job("run", {"system": "slow_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=1)
    run_e = until(e["id"], ("running",), 30)
    os.kill(run_e["supervisor_pid"], signal.SIGKILL)
    time.sleep(0.5)
    _st, unsup = call("GET", f"/api/v1/jobs/{e['id']}")
    check(
        "a job whose supervisor is killed reads running (unsupervised) while its command lives",
        unsup.get("state") == "running (unsupervised)",
        unsup.get("state"),
    )
    lost = until(e["id"], ("lost",), 120)
    check("and lost once its command is gone", lost.get("state") == "lost", lost.get("state"))

    # An artifact, and an upload.
    st, ls = job("label-sheet", {"dataset-id": "tk_v1", "out": "sheet.csv"}, by="person:ana")
    lsd = until(ls.get("id"), ("succeeded", "failed"), 120) if st == 202 else {}
    st2, body = call("GET", f"/api/v1/jobs/{ls.get('id')}/files/sheet.csv")
    check(
        "an artifact: the job writes it in its folder, and it is fetched from there",
        lsd.get("state") == "succeeded" and st2 == 200 and isinstance(body, bytes) and b"item_id" in body,
        (lsd.get("state"), lsd.get("refusal"), st2),
    )
    scores = "".join(
        json.dumps({"item_id": i, "acc": 1.0}) + "\n"
        for i in sorted(p.stem for p in (proj / "tickets").glob("*.txt"))
    )
    st, imp = job(
        "import-run",
        {
            "dataset-id": "tk_v1", "system-id": "imported_v1", "primary-metric": "acc", "source": "a test",
            "scorer-id": "test", "build-ref": "test", "scores": {"name": "scores.jsonl", "content_base64": base64.b64encode(scores.encode()).decode()},
        },
        by="person:ana",
    )  # fmt: skip
    impd = until(imp.get("id"), ("succeeded", "failed"), 120) if st == 202 else {}
    check(
        "an upload: the file reaches the job, kept under .build/uploads",
        impd.get("state") == "succeeded" and any(".build/uploads/" in x for x in impd.get("argv", [])),
        (st, imp, impd.get("state"), impd.get("refusal")),
    )
    srv.terminate()
    srv.wait(timeout=10)
    srv, PORT, TOKEN = serve()
    _st, lj = call("GET", "/api/v1/jobs")
    check(
        "a new server lists the jobs the old one started",
        len(lj.get("jobs", [])) >= 7,
        len(lj.get("jobs", [])),
    )

    # Step 6: the terminal's jobs are the same jobs. Started with jobs-start, listed by the API, stopped by jobs-stop;
    # one the API started, followed by jobs-logs.
    r = evh(
        "jobs-start",
        "run",
        "--arg",
        "system=slow_v1",
        "--arg",
        "dataset=tk_v1",
        "--max-cost-usd",
        "1",
        "--json",
    )
    tj = (
        (json.loads(r.stdout).get("result") or {}).get("values", {}).get("job", {})
        if r.returncode == 0
        else {}
    )
    _st, lj = call("GET", "/api/v1/jobs")
    listed = any(x.get("id") == tj.get("id") for x in lj.get("jobs", []))
    until(tj.get("id"), ("running",), 60)
    r2 = evh("jobs-stop", tj.get("id", "none"))
    _st, after = call("GET", f"/api/v1/jobs/{tj.get('id')}")
    check(
        "jobs-start: a job the API lists (its actor this process's); jobs-stop stops it (cancelled)",
        r.returncode == 0 and listed and tj.get("by") == "person:test" and r2.returncode == 0
        and after.get("state") == "cancelled",
        (r.returncode, r.stderr[-300:], listed, tj.get("by"), r2.stderr[-200:], after.get("state")),
    )  # fmt: skip
    st, aj = job("run", {"system": "fast_v1", "dataset": "tk_v1"}, by="person:ana", max_cost_usd=1)
    r3 = evh("jobs-logs", aj.get("id", "none"), "--follow")
    r4 = evh("jobs-status", aj.get("id", "none"))
    check(
        "jobs-logs --follow: a job the API started, followed to its end; jobs-status reads it",
        r3.returncode == 0 and f"[{aj.get('id')} succeeded]" in r3.stdout and "[6/6]" in r3.stdout
        and "succeeded" in r4.stdout,
        (st, r3.stdout[-300:], r3.stderr[-200:], r4.stdout[-200:]),
    )  # fmt: skip
    r5 = evh("jobs-start", "round-close", "--arg", "goal=g")
    r6 = evh("jobs-start", "datasets")
    check(
        "jobs-start refuses as the API does: a read is not a job; and needs no server",
        r6.returncode != 0 and "not a job" in r6.stderr and r5.returncode != 0,
        (r5.stderr[-200:], r6.stderr[-200:]),
    )

    # Step 4: a catalog job builds beside the served folder and swaps it in; the pages are served throughout.
    st, cj = job("catalog", {}, by="person:ana")
    check("a job just started reads queued, not lost, before its supervisor takes its lock",
          st == 202 and cj.get("state") in ("queued", "running"), (st, cj.get("state")))  # fmt: skip
    codes = []
    end = time.monotonic() + 180
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/.build/catalog/index.html", timeout=30
            ) as r:  # nosec B310
                codes.append(r.status)
        except urllib.error.HTTPError as exc:
            codes.append(exc.code)
        _st, cjs = call("GET", f"/api/v1/jobs/{cj.get('id')}")
        if cjs.get("state") in ("succeeded", "failed", "lost"):
            break
    left = sorted(p.name for p in (proj / ".build").iterdir() if p.name.startswith("catalog."))
    check(
        "a catalog job: built beside and swapped in, every page asked for during it served (200), nothing left over",
        cjs.get("state") == "succeeded" and codes and set(codes) == {200} and not left,
        (cjs.get("state"), cjs.get("refusal"), sorted(set(codes)), len(codes), left),
    )

    # Step 4: a migration holds the whole project; the server answers 503 (Retry-After) to every call until it ends.
    locks = proj / ".build" / "locks"
    fd = os.open(str(locks / "project.lock"), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        seen = None
        for _ in range(40):
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/health")
            try:
                with urllib.request.urlopen(req, timeout=10):  # noqa: S310  # nosec B310
                    pass
            except urllib.error.HTTPError as exc:
                if exc.code == 503:
                    seen = exc.headers.get("Retry-After")
                    break
            time.sleep(0.1)
    finally:
        os.close(fd)
    back = None
    for _ in range(40):
        time.sleep(0.1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=10) as r:  # nosec B310
                back = r.status
                break
        except urllib.error.HTTPError:
            continue
    check("while a migration holds the project: 503 with Retry-After; 200 again once it ends",
          seen == "5" and back == 200, (seen, back))  # fmt: skip
    srv.terminate()
    srv.wait(timeout=10)

    # The token is on disk before the port listens. A client waits for the port and reads .build/api-token at once:
    # the server listened first and wrote its token after, so for a moment the file held the previous server's token
    # (a 401 in the store matrix under load). A start hook that sleeps makes that moment 1.5 s; an old token is there.
    (proj / "slow_start.py").write_text("import time\n\ndef start(info):\n    time.sleep(1.5)\n")
    (proj / ".build" / "api-token").write_text("the-previous-servers-token\n")
    srv, PORT, TOKEN = serve("--hooks", "slow_start.py")
    first, _ = call("GET", "/api/v1/commands")
    srv.terminate()
    srv.wait(timeout=10)
    check(
        "a client that reads the token as soon as the port opens has this server's token (written before it listens)",
        first == 200 and TOKEN != "the-previous-servers-token",
        (first, TOKEN[:8]),
    )

    # Who acted, through the API (RFC-027): an agent names the person it acts for, refused before a job exists without
    # it (a run would have spent its cap and then failed to write its record); and a job's actor is the job's alone,
    # never the server's own EVH_ACTOR / EVH_FOR (every agent job was recorded for whoever the server ran as).
    env["EVH_ACTOR"], env["EVH_FOR"] = "agent:server-shell", "person:mallory"
    srv, PORT, TOKEN = serve()
    no_for, _ = job("prompt-version", {"name": "who_p", "text": "a", "note": "n"}, by="agent:bot")
    st_a, ja = job(
        "prompt-version", {"name": "who_p", "text": "b", "note": "n"}, by="agent:bot", **{"for": "person:ana"}
    )
    st_p, jp = job("prompt-version", {"name": "who_p", "text": "c", "note": "n"}, by="person:bea")
    da = until(ja.get("id"), ("succeeded", "failed"), 60) if st_a == 202 else {}
    dp = until(jp.get("id"), ("succeeded", "failed"), 60) if st_p == 202 else {}
    srv.terminate()
    srv.wait(timeout=10)
    env.pop("EVH_ACTOR")
    env.pop("EVH_FOR")
    actors = {}
    for f in _runstore.listdir(proj, "prompts/who_p") if _runstore.exists(proj, "prompts/who_p") else []:
        if f.endswith(".json"):
            rec = _runstore.read_json(proj, f"prompts/who_p/{f}")
            actors[rec.get("note") + rec["sha256"][:4]] = rec.get("actor")
    got = sorted((a.get("type"), a.get("name"), a.get("for")) for a in actors.values())
    check(
        "through the API an agent names the person it acts for (refused before a job exists without it), and a job's "
        "actor is its own, never the server's EVH_ACTOR / EVH_FOR",
        no_for == 400 and da.get("state") == "succeeded" and dp.get("state") == "succeeded"
        and got == [("agent", "bot", "ana"), ("person", "bea", None)],
        (no_for, da.get("state"), dp.get("state"), got),
    )  # fmt: skip

    # Step 4: data-migrate as a job with the server up. The store comes from config.yaml here (no EVAL_STORE), so the
    # server reads the new store once the move ends; moving out of the database proves the server let go of it.
    cur = env.get("EVAL_STORE", "files")
    target = "files" if cur == "sqlite" else "sqlite"
    env.pop("EVAL_STORE", None)
    (proj / "config.yaml").write_text(f"store: {cur}\n")
    srv, PORT, TOKEN = serve()
    st, before = call("POST", "/api/v1/read/datasets", {"args": {}})

    def served_file():  # the server itself reads it (from the database, in a sqlite project): it holds the store
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/data/datasets/tk_v1.json", timeout=30) as r:  # nosec B310
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code

    file_before = served_file()
    (proj / "config.yaml").write_text(f"store: {target}\n")
    st2, mj = job("data-migrate", {"to": target}, by="person:ana")
    mjd = until(mj.get("id"), ("succeeded", "failed", "lost"), 180) if st2 == 202 else {}
    after = {}
    for _ in range(40):
        st3, after = call("POST", "/api/v1/read/datasets", {"args": {}})
        if st3 == 200:
            break
        time.sleep(0.25)
    ids = lambda b: sorted(  # noqa: E731
        r.get("dataset") for blk in (b.get("result") or {}).get("blocks", []) for r in blk.get("rows", [])
    )
    file_after = served_file()
    check(
        f"data-migrate --to {target} as a job with the server up: it succeeds, and the server reads the new store",
        st == 200
        and mjd.get("state") == "succeeded"
        and st3 == 200
        and ids(after) == ids(before)
        and ids(after)
        and (file_before, file_after) == (200, 200),
        (st, mjd.get("state"), mjd.get("refusal"), st3, ids(before), ids(after), file_before, file_after),
    )
    srv.terminate()
    srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
