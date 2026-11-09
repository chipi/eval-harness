#!/usr/bin/env python3
"""What a command may spend (RFC-026 step 5), $0 and offline: an adapter that reports a cost per item and calls
nothing.

    python tests/test_spend.py

`run --repeat 3` stops at one cap in total, not one a pass; the provider layer stops an adapter that reports less than
its calls cost; `arm-smoke` stops at the cap; `sweep` gives each arm what the arms before it left. A round's budget:
a run spends at most what the round has left; two runs started at once share it, never both all of it; a killed
run's paid items count against it; with nothing left a run is refused before its first call; a job's run that is
stopped has its reservation closed by the supervisor. `POST /api/v1/estimate` answers a job command's --dry-run.
"""

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
from evaluation_harness import _common, _providers  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

# ── the provider layer's own net, in this process ──────────────────────────────────────────────────────────────────
os.environ["EVAL_MAX_COST_USD"] = "0.03"
saved = dict(_providers._SHAPES)
shape = _providers.SPECS["openai"].shape
_providers._SHAPES[shape] = lambda prompt, params, r: _providers.Completion(text="ok", cost_usd=0.01)
calls, stopped = 0, None
try:
    for _ in range(10):
        _providers.complete(
            "x",
            {"provider": "openai", "model": "m", "base_url": "http://127.0.0.1:9"},
            role="arm",
            max_tokens=5,
        )
        calls += 1
except _common.CostCapExceeded as exc:
    stopped = str(exc)
finally:
    _providers._SHAPES.clear()
    _providers._SHAPES.update(saved)
    os.environ.pop("EVAL_MAX_COST_USD")
check(
    "the provider layer stops a process at the cap by its own count, before the call (an adapter reporting nothing)",
    calls == 3 and stopped is not None and "provider layer" in stopped,
    (calls, stopped),
)

proj = Path(tempfile.mkdtemp(prefix="evh-spend-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-spend")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_SPENT_TO"):
    env.pop(k, None)

PAY = """import time
from evaluation_harness.adapter import Result, score  # noqa: F401
def call_system(text, params):
    time.sleep(float(params.get("sleep", 0)))
    return Result(output=text.split(".")[0] + ".", cost_usd=float(params.get("cost", 0.01)))
"""


def evh(*args, cap=None, background=False):
    e = dict(env)
    if cap is not None:
        e["EVAL_MAX_COST_USD"] = str(cap)
    cmd = [sys.executable, str(HERE / "cli.py"), *args]
    if background:
        return subprocess.Popen(cmd, cwd=proj, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                stdin=subprocess.DEVNULL, start_new_session=True)  # fmt: skip
    return subprocess.run(cmd, cwd=proj, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def config(name, cid, **extra):
    lines = [f"config_id: {cid}", "dataset_id: tickets_v1", "adapter: pay.py"]
    lines += [f"{k}: {v}" for k, v in extra.items() if k in ("goal", "round")]
    params = {k: v for k, v in extra.items() if k not in ("goal", "round")}
    lines.append("params:\n  provider: echo" + "".join(f"\n  {k}: {v}" for k, v in params.items()))
    _runstore.write_text(proj, f"configs/{name}.yaml", "\n".join(lines) + "\n")
    return f"data/configs/{name}.yaml"


def spent_of(prefix):
    """What the finished runs of this config spent (their metrics), in either store."""
    total = 0.0
    for name in _runstore.listdir(proj, "runs"):
        if name.startswith(prefix) and _runstore.is_file(proj, f"runs/{name}/metrics.json"):
            m = _runstore.read_json(proj, f"runs/{name}/metrics.json")
            total += float((m.get("scores") or {}).get("total_cost_usd") or 0)
    return round(total, 6)


try:
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "pay.py").write_text(PAY)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "t")
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "the kit's summaries, for the spend test", "--by", "t",
    )  # fmt: skip
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    check("setup: a dataset of 6 items, its gold, the goal", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    # ── run --repeat 3: one cap in all ──────────────────────────────────────────────────────────────────────────
    rep = config("rep", "rep_v1")
    r = evh("run", "--config", rep, "--repeat", "3", cap=0.08)
    check(
        "run --repeat 3 with a $0.08 cap and $0.06 a pass: $0.08 in all, not $0.18 (exit 4, stopped)",
        r.returncode == _common.EXIT_STOPPED and abs(spent_of("rep_v1") - 0.08) < 1e-9,
        (r.returncode, spent_of("rep_v1"), (r.stdout + r.stderr)[-300:]),
    )

    # ── arm-smoke stops at the cap ───────────────────────────────────────────────────────────────────────────────
    r = evh("arm-smoke", "--config", rep, "--items", "3", "--json", cap=0.015)
    env_out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    vals = (env_out.get("result") or {}).get("values") or {}
    check(
        "arm-smoke with a $0.015 cap: item 1 and its repeat ($0.02), then stopped, flagged, items 2-3 not called",
        abs(float(vals.get("spent_usd") or 0) - 0.02) < 1e-9
        and len(vals.get("items") or []) == 1
        and any("stopped at the cap" in f for f in vals.get("flags") or []),
        (
            r.returncode,
            vals.get("spent_usd"),
            len(vals.get("items") or []),
            vals.get("flags"),
            r.stderr[-300:],
        ),
    )

    # ── sweep: each arm what the ones before it left ─────────────────────────────────────────────────────────────
    a, b = config("swa", "swa_v1"), config("swb", "swb_v1")
    r = evh("sweep", "--configs", a, b, cap=0.08)
    check(
        "sweep with a $0.08 cap over two $0.06 arms: the first spends $0.06, the second the $0.02 left",
        abs(spent_of("swa_v1") - 0.06) < 1e-9 and abs(spent_of("swb_v1") - 0.02) < 1e-9,
        (r.returncode, spent_of("swa_v1"), spent_of("swb_v1"), (r.stdout + r.stderr)[-500:]),
    )

    # ── a round's budget ─────────────────────────────────────────────────────────────────────────────────────────
    r = evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--hypothesis", "the spend test",
            "--budget-usd", "0.1")  # fmt: skip
    check(
        "setup: round r1 of tickets_summary, with a $0.10 budget",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )
    slow = config("ra", "ra_v1", goal="tickets_summary", round="r1", sleep=1.0)
    slow_b = config("rb", "rb_v1", goal="tickets_summary", round="r1", sleep=1.0)
    pa = evh("run", "--config", slow, cap=0.04, background=True)
    ledger = proj / ".build" / "rounds" / "tickets_summary" / "r1.json"
    for _ in range(100):
        if ledger.is_file() and json.loads(ledger.read_text()).get("entries"):
            break
        time.sleep(0.1)
    pb = evh("run", "--config", slow_b, background=True)  # no cap of its own: what the round has left
    out_a, _ = pa.communicate(timeout=120)
    out_b, _ = pb.communicate(timeout=120)
    check(
        "two runs of a round at once: A reserves its $0.04 cap, B (no cap) the $0.06 left, never both all of it",
        "$0.0400 of its budget reserved" in out_a
        and "$0.0600 of its budget reserved" in out_b
        and spent_of("ra_v1") <= 0.04 + 1e-9
        and spent_of("rb_v1") <= 0.06 + 1e-9,
        (out_a[-300:], out_b[-300:], spent_of("ra_v1"), spent_of("rb_v1")),
    )
    r = evh("run", "--config", slow_b)
    check(
        "the round's budget spent: the next run is refused before its first call (over-budget), nothing written",
        r.returncode != 0 and "ERROR (over-budget)" in r.stderr and spent_of("rb_v1") <= 0.06 + 1e-9,
        (r.returncode, r.stderr[-300:]),
    )

    # A killed run's paid items count against the budget; its reservation is read from what it wrote.
    r = evh("round-close", "--goal", "tickets_summary", "--round", "r1", "--conclusion", "the budget held")
    r = r if r.returncode else evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--from", "r1",
            "--hypothesis", "after the kill", "--budget-usd", "0.1")  # fmt: skip
    check("setup: round r2, a $0.10 budget", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    k = config("rk", "rk_v1", goal="tickets_summary", round="r2", sleep=1.0)
    log = proj / "killed.log"
    with open(log, "w") as fh:
        e = dict(env)
        pk = subprocess.Popen([sys.executable, str(HERE / "cli.py"), "run", "--config", k], cwd=proj, env=e,
                              stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)  # fmt: skip
    # Killed once two items are paid and written (its progress line says so, in either store).
    for _ in range(600):
        time.sleep(0.1)
        if "[2/6]" in log.read_text():
            break
    os.killpg(pk.pid, signal.SIGKILL)
    pk.wait(timeout=30)
    rv = evh("rounds", "--goal", "tickets_summary")
    check(
        "evh rounds names what the round has left, counting the killed run's paid items",
        "left, counting what running or stopped commands hold" in rv.stdout,
        rv.stdout[-600:],
    )
    nk = config("rn", "rn_v1", goal="tickets_summary", round="r2")
    r = evh("run", "--config", nk)
    reserved = next((ln for ln in r.stdout.splitlines() if "of its budget reserved" in ln), "")
    left = float(reserved.split("$")[1].split()[0]) if "$" in reserved else None
    check(
        "a killed run's paid items count: the next run of the round is given the budget less what the killed one paid",
        left is not None and 0.0 < left < 0.1 - 0.015,
        (reserved, r.stdout[-300:], r.stderr[-300:]),
    )

    # ── as jobs: the supervisor closes a stopped run's reservation; the estimate is the command's --dry-run ─────────
    r = evh(
        "round-close", "--goal", "tickets_summary", "--round", "r2", "--conclusion", "the kill was counted"
    )
    r = r if r.returncode else evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--from", "r2",
                                   "--hypothesis", "as a job", "--budget-usd", "0.1")  # fmt: skip
    r = r if r.returncode else evh("catalog")
    check("setup: round r3 ($0.10) and the catalog", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    config("rj", "rj_v1", goal="tickets_summary", round="r3", sleep=1.0)
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    srv = subprocess.Popen([sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj,
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)  # fmt: skip
    try:
        for _ in range(200):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.5)
        token = (proj / ".build" / "api-token").read_text().strip()

        def call(method, path, body=None):
            h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310  # nosec B310
                    return resp.status, json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read() or b"{}")

        st, est = call("POST", "/api/v1/estimate", {"command": "run", "args": {"config": "rj_v1"}})
        st2, none = call("POST", "/api/v1/estimate", {"command": "arm-smoke", "args": {"config": "rj_v1"}})
        check(
            "the estimate: run's --dry-run, what it would call and its cap; a command with no --dry-run is 404",
            st == 200 and est.get("exit") == 0 and "cap" in est.get("text", "") and st2 == 404
            and "no --dry-run" in none.get("error", ""),
            (st, str(est)[:300], st2, none),
        )  # fmt: skip
        st, j = call("POST", "/api/v1/jobs", {"command": "run", "args": {"config": "rj_v1"}, "by": "person:ana",
                                              "max_cost_usd": 0.05})  # fmt: skip
        ledger3 = proj / ".build" / "rounds" / "tickets_summary" / "r3.json"
        for _ in range(300):
            time.sleep(0.1)
            _st, cur = call("GET", f"/api/v1/jobs/{j.get('id')}/log")
            if ledger3.is_file() and "[2/6]" in cur.get("log", ""):
                break
        call("POST", f"/api/v1/jobs/{j.get('id')}/stop")
        end = {}
        for _ in range(100):
            _st, end = call("GET", f"/api/v1/jobs/{j.get('id')}")
            if end.get("state") in ("cancelled", "lost"):
                break
            time.sleep(0.2)
        time.sleep(1.0)
        entries = json.loads(ledger3.read_text()).get("entries", []) if ledger3.is_file() else []
        mine = [e for e in entries if e.get("job") == j.get("id")]
        check(
            "a stopped run job: the supervisor closes its reservation with what its written items paid (not 0, not "
            "all it reserved)",
            st == 202 and end.get("state") == "cancelled" and len(mine) == 1 and mine[0].get("closed_at")
            and 0.0 < float(mine[0].get("spent") or 0) < float(mine[0].get("reserved") or 0),
            (st, end.get("state"), mine),
        )  # fmt: skip
    finally:
        srv.terminate()
        srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
