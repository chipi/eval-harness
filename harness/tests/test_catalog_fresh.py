#!/usr/bin/env python3
"""The catalog never goes stale (RFC-032 step 8, Q6; RFC-040): catalog-serve renders each page when it is asked for.

    python tests/test_catalog_fresh.py

In a throwaway tutorial project ($0, offline), in either store. A server in this process (its handler and adapter are
the real ones) is asked, through its API, to change the data:

  - an edit over the API: the next request for a page shows it, and no `catalog` job runs, then or ever;
  - two more writes: the next read shows the last; reads that change nothing keep the model they rendered from;
  - many reads during writes: each answer is one whole page of one state of the data, never a mix;
  - a render that fails answers 500 and says why; the next request after the fault is gone renders again;
  - a change by another process (the command line) is noticed on the next read;
  - a job the API starts that writes (a run) is looked at when it ends: the new arm is on the pages.

Then a real `evh catalog-serve` process: its log says the pages are rendered when asked for, a change by the command line
reaches its pages, data that changed while no server ran is on the first page, and a --public server answers
/api/health as it did (no catalog).
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

proj = Path(tempfile.mkdtemp(prefix="evh-fresh-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-fresh")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
os.environ.update(env)

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: E402

GOAL = "tickets_summary"
SETS = [
    "title=Ticket summaries", "statement=A one-line summary of a support ticket for the person triaging it.",
    "decision=Which system writes the summary.", "success_criteria.primary.measure=overlap_f1",
    "success_criteria.primary.direction=higher", "datasets.0.dataset_id=tk_v1", "datasets.0.role=test",
]  # fmt: skip
TOKEN = "test-token"


import _cli  # noqa: E402


def evh(*args):
    return _cli.run(proj, env, *args)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port, method, path, body=None, api=True, headers=None):
    h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    if api:
        h.update({"Authorization": f"Bearer {TOKEN}", "X-EVH-Data": "1"})
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def waiting(cond, seconds=180.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def catalog_jobs() -> list[str]:
    root = proj / ".build" / "jobs"
    out = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            if json.loads((d / "job.json").read_text()).get("operation") == "catalog":
                out.append(d.name)
        except (OSError, ValueError, KeyError):
            pass
    return out


def page(port, name: str, prefix: str | None = None) -> tuple[int, str]:
    return call(port, "GET", (prefix or cs.Handler.prefixes[0]) + name, api=False)


def shows(port, text: str, name: str = "goals.html", prefix: str | None = None) -> bool:
    st, body = page(port, name, prefix)
    return st == 200 and text in body


def adapter_title() -> str:
    return str(next((g.get("title") for g in cs.A.goals() if g["goal_id"] == GOAL), ""))


def patch_title(port, title):
    return call(port, "PATCH", f"/api/v1/goals/{GOAL}", {"set": {"title": title}, "by": "person:t"})


def health(port) -> dict:
    return json.loads(call(port, "GET", "/api/health", api=False)[1])


def wait_up(port: int) -> bool:
    for _ in range(600):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


try:
    r = evh("init", "--store", store_under_test(), "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the freshness test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj, f"systems/{cid}.yaml", f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
    r = r if r.returncode else evh("run", "--system", "one_v1", "--dataset", "tk_v1")
    r = r if r.returncode else evh("goal-new", GOAL, *(x for s in SETS for x in ("--set", s)))
    check(
        "setup: a project with a goal and a run, never built", r.returncode == 0, (r.stdout + r.stderr)[-400:]
    )

    # ── a server in this process: the real handler and adapter ─────────────────────────────────────────────────────
    lines: list[str] = []
    cs.say = lambda line, err=False: lines.append(line)
    cs.FRESH_EVERY_S = 0.0
    cs.set_adapter(load_catalog_adapter(None))
    build_dir = proj / ".build" / "catalog"
    cs.Handler.prefixes = cs.served(build_dir, cs.A.data_dir)
    cs.API_TOKEN[:] = [TOKEN]
    cs.start_fresh()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(cs.Handler, directory=str(cs.ROOT)), bind_and_activate=False
    )
    server.server_bind()
    server.server_activate()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    st, body = call(port, "GET", "/api/health", api=False)
    first = json.loads(body)
    check(
        "health: ok, the catalog rendered on request, nothing prepared before a page is asked for",
        st == 200 and first["ok"] is True and first["catalog"]["mode"] == "on request"
        and first["catalog"]["state"] == "idle" and first["catalog"]["prepared"] == 0,
        first,
    )  # fmt: skip
    check(
        "a project never built: its pages answer at once, from the data",
        shows(port, "Ticket summaries") and shows(port, "one_v1", "arms.html") and not build_dir.exists(),
        (page(port, "goals.html")[0], build_dir.exists()),
    )
    st, _b = page(port, "")
    check(
        "the catalog's own address answers its home page",
        st == 200 and shows(port, "Ticket summaries", ""),
        st,
    )
    st, css = page(port, "assets/catalog.css")
    check("an asset is served", st == 200 and len(css) > 100, st)
    check("an address the data does not name is 404", page(port, "a/no-such-arm.html")[0] == 404)
    prepared = health(port)["catalog"]["prepared"]

    # ── an edit over the API ───────────────────────────────────────────────────────────────────────────────────────
    st, body = patch_title(port, "Fresh one")
    check("the edit is accepted", st == 200, (st, body[:300]))
    check(
        "the adapter answers the new data when the answer to the edit has been sent",
        adapter_title() == "Fresh one",
        adapter_title(),
    )
    t0 = time.monotonic()
    fresh_one = shows(port, "Fresh one")
    read_s = time.monotonic() - t0
    check(
        "the next request for the goals page shows the edit",
        fresh_one and read_s < 30,
        (page(port, "goals.html")[1][:200], read_s),
    )
    check(
        "the log says the data changed, through what, and that the pages are rendered from it",
        any("goal-set through the API" in x and "rendered" in x for x in lines),
        lines,
    )

    # ── two more writes ─────────────────────────────────────────────────────────────────────────────────────────────
    st2, _b = patch_title(port, "Fresh two")
    st3, _b = patch_title(port, "Fresh three")
    check(
        "two more writes: the next read shows the last",
        st2 == st3 == 200 and shows(port, "Fresh three") and not shows(port, "Fresh two"),
        (st2, st3),
    )

    # ── nothing changed, nothing prepared ──────────────────────────────────────────────────────────────────────────
    before = health(port)["catalog"]["prepared"]
    for _ in range(5):
        call(port, "GET", "/api/health", api=False)
        page(port, "index.html")
        page(port, "goals.html")
        time.sleep(0.05)
    check(
        "reads that change nothing render from the model they had: none prepared again",
        health(port)["catalog"]["prepared"] == before and before > prepared,
        (before, health(port)["catalog"]),
    )

    # ── many reads during writes ────────────────────────────────────────────────────────────────────────────────────
    titles = [f"Burst {k}" for k in range(4)]
    answers: list[tuple[int, str]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            answers.append(page(port, "goals.html"))

    readers = [threading.Thread(target=reader) for _ in range(6)]
    for t in readers:
        t.start()
    for title in titles:
        patch_title(port, title)
        time.sleep(0.3)
    stop.set()
    for t in readers:
        t.join(timeout=120)
    named = [sum(t in body for t in ("Fresh three", *titles)) for _st, body in answers]
    check(
        f"{len(answers)} reads during four writes: each is a whole page naming one title of one state",
        answers and all(st == 200 and body.rstrip().endswith("</html>") for st, body in answers)
        and all(n == 1 for n in named),
        ([st for st, _b in answers if st != 200][:3], [n for n in named if n != 1][:3]),
    )  # fmt: skip
    check("after them, the last write shows", shows(port, titles[-1]))
    check("no `catalog` job ran", catalog_jobs() == [], catalog_jobs())

    # ── a render that fails ─────────────────────────────────────────────────────────────────────────────────────────
    del lines[:]
    real_goals = cs.A.goals

    def broken():
        raise RuntimeError("the render breaks here")

    cs.A.goals = broken  # type: ignore[method-assign]  # an adapter that breaks, for this check only
    patch_title(port, "Fresh four")
    st, body = page(port, "goals.html")
    status = health(port)["catalog"]
    check(
        "a render that fails answers 500, says why on health and in the log",
        st == 500 and status["state"] == "failed" and "the render breaks here" in (status["failed"] or {}).get("why", "")
        and any("the render breaks here" in x for x in lines),
        (st, body[:200], status, lines),
    )  # fmt: skip
    cs.A.goals = real_goals  # type: ignore[method-assign]
    check(
        "the next request after the fault is gone renders again, and the failure is cleared",
        shows(port, "Fresh four") and health(port)["catalog"]["state"] == "idle",
        health(port)["catalog"],
    )

    # ── a change by another process ─────────────────────────────────────────────────────────────────────────────────
    check(
        "setup: the adapter has read the goal's title (it is kept)",
        adapter_title() == "Fresh four",
        adapter_title(),
    )
    r = evh("goal-set", GOAL, "--set", "title=Fresh six")
    check("setup: the command line changed the goal", r.returncode == 0, r.stderr[-300:])
    check("no look yet: the server has not read since", adapter_title() == "Fresh four", adapter_title())
    check(
        "the next read notices it, and the page shows it",
        shows(port, "Fresh six") and adapter_title() == "Fresh six",
        adapter_title(),
    )
    check("the log names it as a change it noticed", any("the data changed" in x for x in lines), lines)

    # ── a job that writes ───────────────────────────────────────────────────────────────────────────────────────────
    check(
        "setup: the server does not know the second arm yet",
        not any(a.endswith("/two_v1") for a in cs.A.arms()),
        cs.A.arms(),
    )
    st, body = call(
        port, "POST", "/api/v1/jobs",
        {"operation": "run", "inputs": {"system": "two_v1", "dataset": "tk_v1"}, "by": "person:test", "max_cost_usd": 0.01},
    )  # fmt: skip
    check("the API starts the run job", st == 202, (st, body[:300]))
    job_id = json.loads(body).get("id") if st == 202 else None
    check(
        "the job ends, and the arms page lists the new arm",
        waiting(lambda: job_id and json.loads((proj / ".build" / "jobs" / job_id / "state.json").read_text()).get("state") == "succeeded")
        and waiting(lambda: shows(port, "two_v1", "arms.html")),
        job_id,
    )  # fmt: skip
    check("still no `catalog` job", catalog_jobs() == [], catalog_jobs())

    server.shutdown()
    server.server_close()
    cs.FRESH["on"] = False

    # ── a real process ──────────────────────────────────────────────────────────────────────────────────────────────
    log_file = proj / "serve.log"
    port2 = free_port()
    with open(log_file, "w") as logf:
        srv = subprocess.Popen(
            [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port2)],
            cwd=proj, env=env, stdout=logf, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
        )  # fmt: skip
        try:
            check("setup: catalog-serve started", wait_up(port2), log_file.read_text()[-500:])
            started = log_file.read_text()
            prefix = re.search(r"catalog: http://127\.0\.0\.1:\d+(\S*)", started)
            pre = prefix.group(1) if prefix else "/"
            check(
                "the start-up lines say the pages are rendered when asked for, never to restart it",
                "restart it" not in started and "rendered when it is asked for" in started,
                started,
            )
            check(
                "a real server: health has the catalog's mode",
                health(port2)["catalog"]["mode"] == "on request",
            )
            r = evh("goal-set", GOAL, "--set", "title=Fresh seven")
            # past the look interval (FRESH_EVERY_S): a read sooner is answered from the last look
            time.sleep(0.6)
            check(
                "a change by the command line is on the next page",
                r.returncode == 0 and shows(port2, "Fresh seven", prefix=pre),
                (r.stderr, log_file.read_text()[-400:]),
            )
            check("and the log says the data changed", "the data changed" in log_file.read_text())
        finally:
            srv.terminate()
            srv.wait(timeout=30)

    # ── data that changed while no server ran ─────────────────────────────────────────────────────────────────────
    r = evh("goal-set", GOAL, "--set", "title=Fresh eight")
    port4 = free_port()
    log4 = proj / "serve4.log"
    with open(log4, "w") as logf:
        srv = subprocess.Popen(
            [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port4)],
            cwd=proj, env=env, stdout=logf, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
        )  # fmt: skip
        try:
            wait_up(port4)
            check(
                "a server started after the data changed shows it on its first page, with no rebuild",
                r.returncode == 0 and shows(port4, "Fresh eight", prefix=pre) and catalog_jobs() == [],
                (r.stderr, log4.read_text()[-400:]),
            )
        finally:
            srv.terminate()
            srv.wait(timeout=30)

    port3 = free_port()
    pub = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--public", "localhost", "--port", str(port3)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        wait_up(port3)
        st, body = call(port3, "GET", "/api/health", api=False, headers={"Host": "localhost"})
        check(
            "a --public server answers health as it did: ok, no catalog",
            st == 200 and json.loads(body) == {"ok": True},
            (st, body),
        )
    finally:
        pub.terminate()
        pub.wait(timeout=30)
finally:
    _store.close()
    time.sleep(0.5)
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
