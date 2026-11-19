#!/usr/bin/env python3
"""The catalog never goes stale (RFC-032 step 8, Q6): catalog-serve refreshes what it read and rebuilds the pages.

    python tests/test_catalog_fresh.py

In a throwaway tutorial project ($0, offline), in either store. A server in this process (its handler, adapter and
rebuild jobs are the real ones) is asked, through its API, to change the data:

  - an edit over the API: the adapter answers the new data when the answer to the edit has been sent, a `catalog` job
    is building the pages while the old ones are served, and then the pages show the edit;
  - two more writes during that rebuild cost one more build, not two;
  - a rebuild that fails leaves the pages that were there, and says so (health, log), and the next write rebuilds;
  - a change by another process (the command line) is noticed on the next read, with the same refresh and rebuild;
  - a job the API starts that writes (a run) is looked at when it ends: the new arm is known and on the pages;
  - nothing changed, nothing rebuilt: reads, and the rebuild's own effects, leave the data's state as it was.

Then a real `evh catalog-serve` process: its log names the rebuild instead of telling a person to restart it, a
change by the command line reaches its pages, and a --public server answers /api/health as it did (no catalog).
"""

import json
import os
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


def settled() -> bool:
    s = cs.catalog_status()
    return s["state"] != "building" and not s["queued"]


def title_of(page: str) -> bool:
    return (proj / ".build" / "catalog" / "goals.html").read_text(encoding="utf-8").count(page) > 0


def adapter_title() -> str:
    return str(next((g.get("title") for g in cs.A.goals() if g["goal_id"] == GOAL), ""))


def patch_title(port, title):
    return call(port, "PATCH", f"/api/v1/goals/{GOAL}", {"set": {"title": title}, "by": "person:t"})


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
    r = r if r.returncode else evh("catalog")
    check(
        "setup: a project with a goal, a run and its catalog", r.returncode == 0, (r.stdout + r.stderr)[-400:]
    )

    # ── a server in this process: the real handler, adapter and jobs ──────────────────────────────────────────────
    lines: list[str] = []
    cs.say = lambda line, err=False: lines.append(line)
    cs.FRESH_EVERY_S = 0.0
    cs.set_adapter(load_catalog_adapter(None))
    build_dir = proj / ".build" / "catalog"
    cs.Handler.prefixes = cs.served(build_dir, cs.A.data_dir)
    cs.API_TOKEN[:] = [TOKEN]
    cs.start_fresh(build_dir, None)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(cs.Handler, directory=str(cs.ROOT)), bind_and_activate=False
    )
    server.server_bind()
    server.server_activate()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    page = f"http://127.0.0.1:{port}{cs.Handler.prefixes[0]}goals.html"

    st, body = call(port, "GET", "/api/health", api=False)
    health = json.loads(body)
    check(
        "health: ok, the catalog idle, when its pages were built; no rebuild at start (the pages are newer than the data)",
        st == 200 and health["ok"] is True and health["catalog"]["state"] == "idle"
        and health["catalog"]["built_at"] and not catalog_jobs() and not lines,
        (st, body, catalog_jobs(), lines),
    )  # fmt: skip
    check("the adapter lists the goal as it is", adapter_title() == "Ticket summaries", adapter_title())

    # ── an edit over the API ───────────────────────────────────────────────────────────────────────────────────────
    st, body = patch_title(port, "Fresh one")
    check("the edit is accepted", st == 200, (st, body[:300]))
    check(
        "the adapter answers the new data when the answer to the edit has been sent",
        adapter_title() == "Fresh one",
        adapter_title(),
    )
    status = cs.catalog_status()
    t0 = time.monotonic()
    st_page, old_page = call(port, "GET", cs.Handler.prefixes[0] + "goals.html", api=False)
    read_s = time.monotonic() - t0
    still = cs.catalog_status()["state"] == "building"
    check(
        "a catalog job is building the pages at once; a read of a page is answered from the old ones, never waits for it",
        status["state"] == "building" and status["job"] and len(catalog_jobs()) == 1
        and st_page == 200 and (not still or "Fresh one" not in old_page) and read_s < 5,
        (status, st_page, read_s, still),
    )  # fmt: skip
    check(
        "the log says a rebuild started, and for what",
        any("rebuilding the pages" in x and "goal-set through the API" in x for x in lines),
        lines,
    )
    check("the rebuild is a `catalog` job under the `catalog` lock", any(
        ["catalog", True] in json.loads((proj / ".build" / "jobs" / j / "job.json").read_text())["locks"]
        for j in catalog_jobs()
    ))  # fmt: skip

    # ── two more writes during it ───────────────────────────────────────────────────────────────────────────────────
    st2, _b = patch_title(port, "Fresh two")
    queued = cs.catalog_status()
    st3, _b = patch_title(port, "Fresh three")
    still = cs.catalog_status()
    check(
        "two writes during a rebuild: one more waits (never more than one)",
        st2 == st3 == 200 and queued["state"] == "building" and queued["queued"] and still["state"] == "building",
        (st2, st3, queued, still),
    )  # fmt: skip
    check("the adapter has the last write at once", adapter_title() == "Fresh three", adapter_title())
    check("the rebuilds end", waiting(settled), cs.catalog_status())
    jobs = catalog_jobs()
    check("two writes during a rebuild cost one more build, not two: 2 builds in all", len(jobs) == 2, jobs)
    check(
        "the pages show the last write, built when the health says",
        title_of("Fresh three")
        and cs.catalog_status()["state"] == "idle"
        and cs.catalog_status()["built_at"],
        cs.catalog_status(),
    )
    check(
        "the log says when the pages were built",
        any("rebuilt" in x and "the pages are built" in x for x in lines),
        lines,
    )

    # ── nothing changed, nothing rebuilt ────────────────────────────────────────────────────────────────────────────
    for _ in range(5):
        call(port, "GET", "/api/health", api=False)
        call(port, "GET", cs.Handler.prefixes[0] + "index.html", api=False)
        time.sleep(0.15)
    check(
        "reads that change nothing, and the rebuild's own effects, start no build",
        len(catalog_jobs()) == 2 and settled(),
        (catalog_jobs(), cs.catalog_status()),
    )

    # ── a rebuild that fails ────────────────────────────────────────────────────────────────────────────────────────
    before = (build_dir / "goals.html").read_bytes()
    index_before = (build_dir / "index.html").read_bytes()
    built_before = cs.catalog_status()["built_at"]
    # An adapter that breaks while the pages are being built (after the new ones have been started beside the old).
    (proj / "breaking_adapter.py").write_text(
        "from evaluation_harness.catalog_adapter import HarnessAdapter\n\n\n"
        "class Adapter(HarnessAdapter):\n    def goals(self):\n        raise RuntimeError('the build breaks here')\n"
    )
    cs.FRESH["adapter"] = "breaking_adapter.py:Adapter"
    del lines[:]
    patch_title(port, "Fresh four")
    check("the failing rebuild ends", waiting(settled), cs.catalog_status())
    status = cs.catalog_status()
    check(
        "a failed rebuild leaves the pages that were there",
        (build_dir / "goals.html").read_bytes() == before and (build_dir / "index.html").read_bytes() == index_before
        and call(port, "GET", cs.Handler.prefixes[0] + "goals.html", api=False)[0] == 200,
    )  # fmt: skip
    check(
        "and says so on health (failed, why, since which pages) and in the log",
        status["state"] == "failed" and status["failed"] and "the build breaks here" in status["failed"]["why"] and status["built_at"] == built_before
        and json.loads(call(port, "GET", "/api/health", api=False)[1])["catalog"]["state"] == "failed"
        and any("FAILED" in x and "served as they were" in x for x in lines),
        (status, lines),
    )  # fmt: skip
    check("the adapter still has the data", adapter_title() == "Fresh four", adapter_title())
    cs.FRESH["adapter"] = None
    patch_title(port, "Fresh five")
    check("the next write rebuilds", waiting(settled), cs.catalog_status())
    status = cs.catalog_status()
    check(
        "and the failure is cleared",
        status["state"] == "idle" and status["failed"] is None and title_of("Fresh five"),
        status,
    )

    # ── a change by another process ─────────────────────────────────────────────────────────────────────────────────
    n = len(catalog_jobs())
    check(
        "setup: the adapter has read the goal's title (it is kept)",
        adapter_title() == "Fresh five",
        adapter_title(),
    )
    r = evh("goal-set", GOAL, "--set", "title=Fresh six")
    check("setup: the command line changed the goal", r.returncode == 0, r.stderr[-300:])
    check("no look yet: the server has not read since", adapter_title() == "Fresh five", adapter_title())
    call(port, "GET", "/api/health", api=False)  # the next read
    check(
        "the next read notices it: the adapter has the new data and a rebuild is building the pages",
        adapter_title() == "Fresh six" and cs.catalog_status()["state"] == "building" and len(catalog_jobs()) == n + 1,
        (adapter_title(), cs.catalog_status(), len(catalog_jobs()), n),
    )  # fmt: skip
    check(
        "the rebuild ends and the pages show it",
        waiting(settled) and title_of("Fresh six"),
        cs.catalog_status(),
    )
    check(
        "the log names it as a change it noticed",
        any("the data changed" in x and "rebuilding" in x for x in lines),
        lines,
    )

    # ── a job that writes ───────────────────────────────────────────────────────────────────────────────────────────
    n = len(catalog_jobs())
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
        "the job ends, and the pages are rebuilt after it",
        waiting(lambda: job_id and json.loads((proj / ".build" / "jobs" / job_id / "state.json").read_text()).get("state") == "succeeded")
        and waiting(lambda: len(catalog_jobs()) > n and settled()),
        (job_id, catalog_jobs(), cs.catalog_status()),
    )  # fmt: skip
    check(
        "the adapter knows the new arm, and the arms page lists it",
        any(a.endswith("/two_v1") for a in cs.A.arms())
        and "two_v1" in (build_dir / "arms.html").read_text(encoding="utf-8"),
        cs.A.arms(),
    )  # fmt: skip
    check(
        "the run cost the pages at most the builds it needed, never one per file it wrote",
        len(catalog_jobs()) <= n + 3,
        (len(catalog_jobs()), n),
    )

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
            up = False
            for _ in range(600):
                try:
                    with socket.create_connection(("127.0.0.1", port2), timeout=0.2):
                        up = True
                        break
                except OSError:
                    time.sleep(0.1)
            check("setup: catalog-serve started", bool(up), log_file.read_text()[-500:])
            started = log_file.read_text()
            check(
                "the start-up lines no longer tell a person to restart it",
                "restart it" not in started and "rebuilt when the data changes" in started,
                started,
            )
            health = json.loads(call(port2, "GET", "/api/health", api=False)[1])
            check(
                "a real server: health has the catalog's state",
                health["catalog"]["state"] == "idle" and health["catalog"]["built_at"],
                health,
            )
            n = len(catalog_jobs())
            r = evh("goal-set", GOAL, "--set", "title=Fresh seven")
            time.sleep(0.6)  # past the look interval
            state = json.loads(call(port2, "GET", "/api/health", api=False)[1])["catalog"]
            check(
                "a change by the command line: the next read starts a rebuild",
                r.returncode == 0 and state["state"] == "building" and len(catalog_jobs()) == n + 1,
                (r.stderr, state, catalog_jobs()),
            )
            check(
                "it ends, the pages show the change, and the log says so",
                waiting(lambda: json.loads(call(port2, "GET", "/api/health", api=False)[1])["catalog"]["state"] == "idle")
                and title_of("Fresh seven") and "rebuilt (job" in log_file.read_text(),
                log_file.read_text()[-600:],
            )  # fmt: skip
        finally:
            srv.terminate()
            srv.wait(timeout=30)

    # ── data that changed while no server ran ─────────────────────────────────────────────────────────────────────
    r = evh("goal-set", GOAL, "--set", "title=Fresh eight")
    n = len(catalog_jobs())
    port4 = free_port()
    log4 = proj / "serve4.log"
    with open(log4, "w") as logf:
        srv = subprocess.Popen(
            [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port4)],
            cwd=proj, env=env, stdout=logf, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
        )  # fmt: skip
        try:
            for _ in range(600):
                try:
                    with socket.create_connection(("127.0.0.1", port4), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            check(
                "a server started on pages older than the data rebuilds them at once, and says why",
                r.returncode == 0 and len(catalog_jobs()) == n + 1 and "the data is newer than the pages" in log4.read_text()
                and waiting(lambda: json.loads(call(port4, "GET", "/api/health", api=False)[1])["catalog"]["state"] == "idle")
                and title_of("Fresh eight"),
                (r.stderr, log4.read_text()[-400:]),
            )  # fmt: skip
        finally:
            srv.terminate()
            srv.wait(timeout=30)

    port3 = free_port()
    pub = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--public", "localhost", "--port", str(port3)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        for _ in range(600):
            try:
                with socket.create_connection(("127.0.0.1", port3), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        st, body = call(port3, "GET", "/api/health", api=False, headers={"Host": "localhost"})
        check(
            "a --public server answers health as it did: ok, no catalog, no rebuilds of its own",
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
