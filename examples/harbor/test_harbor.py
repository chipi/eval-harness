#!/usr/bin/env python3
"""The Harbor example's own checks (RFC-038 section 4): the source, the importer, the adapter and a run, with a fake
`harbor` and the job directories recorded from Harbor's `oracle` and `nop` agents. No Docker, no model, no network.

    python examples/harbor/test_harbor.py

  the fixtures    recorded job directories hold nothing that names a machine, a person, a URL or a key; the core names
                  nothing of Harbor (`test_core_stays_generic`)
  the source      the three local tasks as items, with their fields and no author; a registry dataset through a fake
                  `harbor dataset download`
  the importer    one record per trial from the fixtures: ids, outcomes, `pick`, `job`; capture, dataset and a recorded arm
                  whose outputs and scores equal what the live adapter gives on the same trial (two routes, one `score`)
  the adapter     `harbor run` once per item, `-r 0`, no retry whatever the failure (crash, "connection reset by peer",
                  a timeout); a trial that ran and failed is a scored 0, one that gave no result a failed item with its
                  trial directory as the artifact; `--resume` does not call it again, `--recall-failed` does, once; a hang
                  ends at the timeout and leaves no process, SIGTERM or not; the item's link is served read-only
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HARNESS = REPO / "harness"
sys.path.insert(0, str(HARNESS))
# The checkout's own project, as the other examples' tests name it.
os.environ.setdefault("EVAL_HOME", str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))  # _cli, _runstore
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
import adapter  # noqa: E402
import importer  # noqa: E402
import source  # noqa: E402
from evaluation_harness import _format, _importers  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as _R  # noqa: E402

TASKS = HERE / "tasks"
FIXTURES = HERE / "fixtures" / "jobs"
NAMES = sorted(p.name for p in TASKS.iterdir() if (p / "task.toml").is_file())

# --- the fixtures and the core -------------------------------------------------------------------------------------
jobs = sorted(p.name for p in FIXTURES.iterdir())
check(
    "fixtures: an oracle job and a nop job per task, a recorded agent timeout, and the one synthetic exception job",
    jobs
    == sorted(
        [f"oracle-{t}" for t in NAMES]
        + [f"nop-{t}" for t in NAMES]
        + ["timeout-write-greeting", "exception-write-greeting"]
    ),
    jobs,
)
bad = [
    f"{p.relative_to(HERE)}: {s}"
    for p in FIXTURES.rglob("*")
    if p.is_file()
    for s in ("/home/", "/work/", "http", "_KEY")
    if s in p.read_text(encoding="utf-8")
]
check("fixtures: no path of a machine, no URL, no key's name in any file", not bad, bad[:3])
check(
    "fixtures: no agent folder, no log, no lock (only the files the importer and the adapter read)",
    {p.name for p in FIXTURES.rglob("*") if p.is_file()}
    == {"config.json", "result.json", "ctrf.json", "reward.txt", "test-stdout.txt"},
    sorted({p.name for p in FIXTURES.rglob("*") if p.is_file()}),
)


def reward_of(job):
    t = next((FIXTURES / job).glob("*__*"))
    return (
        (json.loads((t / "result.json").read_text()).get("verifier_result") or {})
        .get("rewards", {})
        .get("reward")
    )


check(
    "fixtures: the verifier passes every oracle job and fails every nop job (a pass is not free)",
    all(reward_of(f"oracle-{t}") == 1.0 and reward_of(f"nop-{t}") == 0.0 for t in NAMES),
    {t: (reward_of(f"oracle-{t}"), reward_of(f"nop-{t}")) for t in NAMES},
)


def test_core_stays_generic() -> list[str]:
    """Every line of the harness's code that says `harbor` and is not a comment citing RFC-038."""
    found = []
    for base in (HARNESS / "scripts", HARNESS / "workbench", HARNESS / "catalog_assets"):
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix in (".pyc", ".png", ".svg", ".ico"):
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if "harbor" in line.lower() and not (
                    line.lstrip().startswith(("#", "//")) and "RFC-038" in line
                ):
                    found.append(f"{p.relative_to(HARNESS)}:{n}: {line.strip()[:80]}")
    return found


leaks = test_core_stays_generic()
check(
    "test_core_stays_generic: nothing under harness/scripts, workbench or catalog_assets names Harbor",
    not leaks,
    leaks[:3],
)

# --- the source ------------------------------------------------------------------------------------------------------
src = source.Source({})
items = list(src.items({"path": str(TASKS)}))
by = {i["item_id"]: i for i in items}
check("source: one item per task directory, by its name", sorted(by) == NAMES, sorted(by))
doc = json.loads(by["write-greeting"]["text"])
check(
    "source: the item's text is the one JSON document {task, path, instruction}",
    set(doc) == {"task", "path", "instruction"}
    and doc["task"] == "write-greeting"
    and doc["instruction"].startswith("Create the file"),
    doc,
)
check(
    "source: its fields are difficulty, category and the agent's timeout, read from task.toml",
    by["write-greeting"]["fields"]
    == {"difficulty": "easy", "category": "file-ops", "agent_timeout_sec": 120.0}
    and by["make-script"]["fields"]["difficulty"] == "medium",
    by["write-greeting"]["fields"],
)
check(
    "source: no author is ever read (a task.toml with author_name and author_email gives neither)",
    "author" not in json.dumps(items),
)
d = src.describe({"path": str(TASKS)})
check(
    "source: describe names the provider and counts the tasks",
    d["source"]["provider"] == "harbor" and "3 Harbor task" in d["description"],
    d,
)
try:
    list(src.items({"path": str(HERE / "nope")}))
    refused = False
except ValueError:
    refused = True
check("source: a folder that is not there is refused with a reason", refused)

# --- the tiny TOML reader, on the shape of a real registry task ------------------------------------------------------
import _toml  # noqa: E402

REAL = """schema_version = "1.1"
artifacts = []

[task]
name = "terminal-bench/x"
keywords = ["a", "b"]
[[task.authors]]
name = "Somebody"
email = "somebody@example.org"

[metadata]
author_name = "Somebody"
difficulty = "hard"
tags = [
  "a",
  "b",
]
expert_time_estimate_min = 120.0

[agent]
timeout_sec = 1800.0 # seconds
[environment]
build_timeout_sec = 600
allow_internet = true
"""
with tempfile.TemporaryDirectory() as t:
    (Path(t) / "task.toml").write_text(REAL)
    tt = _toml.read(Path(t) / "task.toml")
check(
    "toml: scalars of a table, arrays and [[array tables]] skipped, comments and multi-line arrays survived",
    _toml.get(tt, "metadata", "difficulty") == "hard"
    and _toml.get(tt, "agent", "timeout_sec") == 1800.0
    and _toml.get(tt, "environment", "build_timeout_sec") == 600
    and _toml.get(tt, "environment", "allow_internet") is True
    and _toml.get(tt, "task.authors", "name") is None
    and "tags" not in tt["metadata"]
    and _toml.get(tt, "metadata", "expert_time_estimate_min") == 120.0,
    tt,
)

# --- the importer ---------------------------------------------------------------------------------------------------
os.chdir(
    REPO
)  # the fixtures name their tasks relative to the repository: the importer finds task.toml from here
imp = importer.Importer({})
recs = list(imp.records({"jobs_dir": str(FIXTURES)}))
check(
    "importer: one record per trial: 3 oracle, 3 nop, the agent timeout and the synthetic exception job's",
    len(recs) == 8 and len({r["id"] for r in recs}) == 8,
    [r["id"] for r in recs],
)
check("importer: every id is a valid record id", all(_importers.RECORD_ID.fullmatch(r["id"]) for r in recs))
by_agent = {
    (r["fields"]["agent"], r["fields"]["task"]): r for r in recs if not r["outcome"]["exception_type"]
}
rec = by_agent[("oracle", "write-greeting")]
check(
    "importer: an oracle trial: reward 1, its tests counted, the task's fields and its instruction",
    rec["outcome"]["reward"] == 1.0
    and rec["outcome"]["tests"] == {"passed": 2, "failed": 0, "total": 2}
    and rec["fields"]["difficulty"] == "easy"
    and rec["body"]["instruction"].startswith("Create the file")
    and rec["body"]["path"] == "examples/harbor/tasks/write-greeting"
    and rec["source"]["system"] == "harbor"
    and rec["created_at"],
    rec,
)
check(
    "importer: a nop trial: reward 0, the verifier's tests failed",
    by_agent[("nop", "write-greeting")]["outcome"]["reward"] == 0.0
    and by_agent[("nop", "write-greeting")]["outcome"]["tests"]["failed"] == 2,
    by_agent[("nop", "write-greeting")]["outcome"],
)
timed_out = next(r for r in recs if r["outcome"]["exception_type"] == "AgentTimeoutError")
check(
    "importer: a trial Harbor ended with an AgentTimeoutError (recorded): the exception AND the reward 0 its verifier gave",
    timed_out["outcome"]["reward"] == 0.0 and timed_out["outcome"]["tests"]["failed"] == 2,
    timed_out["outcome"],
)
exc = next(r for r in recs if r["outcome"]["exception_type"] == "EnvironmentStartTimeoutError")
check(
    "importer: a trial that never reached its verifier (the synthetic one): the type, no reward, no tests",
    exc["outcome"]["reward"] is None and exc["outcome"]["tests"] is None,
    exc["outcome"],
)
check(
    "importer: pick first or last gives one record per task (the nop, timeout and exception trials are other trials of the same tasks)",
    len(list(imp.records({"jobs_dir": str(FIXTURES), "pick": "first"}))) == 3
    and len(list(imp.records({"jobs_dir": str(FIXTURES), "pick": "last"}))) == 3,
)
check(
    "importer: job names one job of the folder",
    [r["id"] for r in imp.records({"jobs_dir": str(FIXTURES), "job": "nop-make-script"})]
    == [by_agent[("nop", "make-script")]["id"]],
)
check(
    "importer: a trial's source url is its place under the jobs folder, never an absolute path",
    all(not r["source"]["url"].startswith("/") and "/" in r["source"]["url"] for r in recs),
    recs[0]["source"],
)
check(
    "importer: no author, no key, no url in any record",
    not re.search(r"author|_KEY|http|/home/|/work/", json.dumps(recs)),
)
os.chdir("/")
elsewhere = next(iter(imp.records({"jobs_dir": str(FIXTURES), "job": "oracle-write-greeting"})))
check(
    "importer: read from another directory the task folder is not found, and the record says so (an empty instruction), not guesses",
    elsewhere["body"]["instruction"] == "",
    elsewhere["body"],
)
os.chdir(REPO)
for bad_query in ({}, {"jobs_dir": str(HERE / "nope")}, {"jobs_dir": str(FIXTURES), "pick": "middle"}):
    try:
        list(imp.records(bad_query))
        ok = False
    except ValueError:
        ok = True
    check(f"importer: refuses {bad_query or 'no jobs_dir'}", ok)

# --- two routes, one score: the live adapter and a recorded arm ------------------------------------------------------
bindir = Path(tempfile.mkdtemp(prefix="evh-harbor-bin-"))
(bindir / "harbor").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_harbor.py"}" "$@"\n')
(bindir / "harbor").chmod(0o755)
live_cwd = Path(tempfile.mkdtemp(prefix="evh-harbor-live-"))
os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ['PATH']}"
os.chdir(live_cwd)
try:
    for t in NAMES:
        item = json.dumps({"task": t, "path": str(TASKS / t), "instruction": ""})
        res = adapter.call_system(item, {"agent": "oracle", "jobs_dir": "artifacts/live"})
        rec = by_agent[("oracle", t)]
        check(
            f"two routes: {t}: the live call's output is byte for byte the recorded arm's",
            res.output == adapter.recorded_output(rec),
            (res.output, adapter.recorded_output(rec)),
        )
        check(
            f"two routes: {t}: one `score` gives the same numbers for both, and they are a pass",
            adapter.score(res.output) == adapter.score(adapter.recorded_output(rec))
            and adapter.score(res.output)["pass"] == 1.0,
            adapter.score(res.output),
        )
    res = adapter.call_system(
        json.dumps({"task": "count-lines", "path": str(TASKS / "count-lines")}),
        {"agent": "oracle", "jobs_dir": "artifacts/live"},
    )
    check(
        "the live call's meta: the trial's directory as the artifact, the wall time, the agent, and a cost of 0 that says why",
        res.meta["artifact"].startswith("artifacts/live/count-lines-")
        and (live_cwd / res.meta["artifact"]).is_dir()
        and res.meta["agent"] == "oracle"
        and res.meta["cost_source"] == "no-model-agent"
        and res.cost_usd == 0.0
        and res.extra == {"reward": 1.0}
        and "wall_s" in res.meta,
        res.meta,
    )
    os.environ["FAKE_HARBOR_MODE"] = "fail"
    res = adapter.call_system(
        json.dumps({"task": "count-lines", "path": str(TASKS / "count-lines")}),
        {"agent": "nop", "jobs_dir": "artifacts/live"},
    )
    del os.environ["FAKE_HARBOR_MODE"]
    check(
        "the nop agent's trial is a scored 0, not an error",
        adapter.score(res.output)["pass"] == 0.0 and adapter.score(res.output)["tests_passed_frac"] == 0.0,
        res.output,
    )
    # a registry dataset, through a stand-in for `harbor dataset download`
    reg = list(source.Source({}).items({"dataset": "fake/tb-mini@1.0"}))
    rdoc = json.loads(reg[0]["text"]) if reg else {}
    check(
        "source: a registry dataset is downloaded to .build/harbor/ and its items name the dataset and the task",
        [i["item_id"] for i in reg] == NAMES
        and rdoc.get("dataset") == "fake/tb-mini@1.0"
        and rdoc["path"].startswith(".build/harbor/tb-mini/"),
        reg[:1],
    )
    check(
        "adapter: an item that names a dataset is run with -d DATASET -i TASK",
        adapter.command(rdoc, {"agent": "oracle"}, "jobs", "j")[2:6]
        == ["-d", "fake/tb-mini@1.0", "-i", rdoc["task"]],
        adapter.command(rdoc, {"agent": "oracle"}, "jobs", "j"),
    )
finally:
    os.chdir(REPO)

# --- a project: runs through the harness -------------------------------------------------------------------------------
proj = Path(tempfile.mkdtemp(prefix="evh-harbor-proj-"))
LOG = proj / "harbor-calls.jsonl"
PIDS = proj / "harbor-pids.txt"
env = dict(
    os.environ,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-harbor",
    EVAL_RETRY_MAX_DELAY="0",
    EVAL_MAX_RETRIES="3",
    FAKE_HARBOR_LOG=str(LOG),
    FAKE_HARBOR_PIDS=str(PIDS),
)
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "FAKE_HARBOR_MODE", "FAKE_HARBOR_ONLY", "EVH_ACTOR"):
    env.pop(k, None)


def evh(*args, **extra):
    e = {**env, **{k: v for k, v in extra.items() if v is not None}}
    for k, v in extra.items():
        if v is None:
            e.pop(k, None)
    return _cli.run(proj, e, *args, timeout=600)


def calls(task=None):
    got = [json.loads(x) for x in LOG.read_text().splitlines()] if LOG.exists() else []
    return [c for c in got if task is None or c["task"] == task]


def reset():
    LOG.unlink(missing_ok=True)
    PIDS.unlink(missing_ok=True)


def first_score(rid):
    with _runstore._InProject(proj):
        return _R.first_score(rid)


def record(rid):
    with _runstore._InProject(proj):
        sd = _R.first_score(rid)
        return (_R.record(sd) if sd else None) or {}


def rows(rid):
    with _runstore._InProject(proj):
        sd = _R.first_score(rid)
        return _runstore.rows(sd) if sd else []


def system(sid, params):
    body = "".join(f"  {k}: {v}\n" for k, v in params.items())
    _runstore.write_text(
        proj, f"systems/{sid}.yaml", f"system_id: {sid}\nadapter: {HERE / 'adapter.py'}\nparams:\n{body}"
    )


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, "fields/harbor_tasks.yaml", (HERE / "fields.yaml").read_text())
    r = evh(
        "dataset-create", "--dataset-id", "harbor_tasks_v1", "--source", f"{HERE / 'source.py'}:Source",
        "--query", json.dumps({"path": str(TASKS)}), "--fieldset", "harbor_tasks",
    )  # fmt: skip
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "harbor_tasks_v1")
    check(
        "setup: the three tasks as a dataset, through the source",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )
    system("harbor_oracle_v1", {"agent": "oracle", "jobs_dir": "artifacts/harbor_oracle_v1"})
    system("harbor_nop_v1", {"agent": "nop", "jobs_dir": "artifacts/harbor_nop_v1"})

    r = evh("run", "--system", "harbor_oracle_v1", "--dataset", "harbor_tasks_v1", "--run-id", "oracle1")
    m = record("oracle1")
    rs = rows("oracle1")
    check(
        "oracle: every task passes at cost 0, and the run says it calls each item once",
        r.returncode == 0
        and m.get("scores", {}).get("pass") == 1.0
        and m.get("scores", {}).get("reward") == 1.0
        and (m.get("scores", {}).get("total_cost_usd") or 0) == 0
        and "calls each item once" in r.stdout
        and m.get("call_once") is True,
        (r.stdout + r.stderr)[-600:],
    )
    check(
        "oracle: harbor was called once per item, with -r 0, one attempt, one trial at a time",
        len(calls()) == 3
        and all(
            "-r" in c["argv"]
            and c["argv"][c["argv"].index("-r") + 1] == "0"
            and c["argv"][c["argv"].index("-n") + 1] == "1"
            and "-y" in c["argv"]
            and "-q" in c["argv"]
            for c in calls()
        ),
        calls()[:1],
    )
    check(
        "oracle: each row's artifact is its trial's directory under artifacts/, and the cost says where it comes from",
        all(
            (x.get("_meta") or {}).get("artifact", "").startswith("artifacts/harbor_oracle_v1/")
            and (x["_meta"].get("cost_source") == "no-model-agent")
            for x in rs
        )
        and all((proj / x["_meta"]["artifact"]).is_dir() for x in rs),
        rs[:1],
    )
    check(
        "oracle: reward is an extra metric of the run",
        "reward" in m.get("scores", {}) and rs[0].get("_extra", {}).get("reward") == 1.0,
        rs[:1],
    )

    r = evh(
        "run",
        "--system",
        "harbor_nop_v1",
        "--dataset",
        "harbor_tasks_v1",
        "--run-id",
        "nop1",
        FAKE_HARBOR_MODE="fail",
    )
    check(
        "nop: every task scores 0 (the verifier fails an untouched environment), and none is a failed item",
        r.returncode == 0
        and record("nop1").get("scores", {}).get("pass") == 0.0
        and not record("nop1").get("failed_items"),
        (r.stdout + r.stderr)[-400:],
    )

    reset()
    system("harbor_exc_v1", {"agent": "oracle", "jobs_dir": "artifacts/harbor_exc_v1"})
    r = evh(
        "run",
        "--system",
        "harbor_exc_v1",
        "--dataset",
        "harbor_tasks_v1",
        "--run-id",
        "exc1",
        FAKE_HARBOR_MODE="exception",
        FAKE_HARBOR_ONLY="write-greeting",
    )
    m = record("exc1")
    bad = next((x for x in rows("exc1") if x["item_id"] == "write-greeting"), {})
    check(
        "a trial that never reached its verifier (an exception, no reward) is a scored 0 with the exception in its output, not a failed item",
        r.returncode == 0
        and not m.get("failed_items")
        and bad.get("pass") == 0.0
        and bad.get("answered") == 0.0
        and bad.get("failed") == 0.0
        and "EnvironmentStartTimeoutError" in str(bad.get("_meta", {}).get("exception_type")),
        (bad, (r.stdout + r.stderr)[-300:]),
    )
    with _runstore._InProject(proj):
        from evaluation_harness import _outputs

        out = _outputs.output(_R.run_dir("exc1"), "write-greeting") or ""
    check(
        "... and the output names the exception",
        '"exception": "EnvironmentStartTimeoutError"' in out and '"answered": false' in out,
        out[:300],
    )
    reset()
    system("harbor_timeout_v1", {"agent": "oracle", "jobs_dir": "artifacts/harbor_timeout_v1"})
    r = evh(
        "run", "--system", "harbor_timeout_v1", "--dataset", "harbor_tasks_v1", "--run-id", "timeout1",
        FAKE_HARBOR_MODE="timeout", FAKE_HARBOR_ONLY="write-greeting",
    )  # fmt: skip
    bad = next((x for x in rows("timeout1") if x["item_id"] == "write-greeting"), {})
    check(
        "a trial Harbor ended with an AgentTimeoutError (recorded) is a scored 0 too: answered (its verifier ran), reward 0, the exception named, not a failed item",
        r.returncode == 0
        and not record("timeout1").get("failed_items")
        and bad.get("pass") == 0.0
        and bad.get("answered") == 1.0
        and bad.get("failed") == 0.0
        and bad.get("_meta", {}).get("exception_type") == "AgentTimeoutError",
        bad,
    )

    # --- a call with no trial result is a failed item, called once ---
    for mode, label in (
        ("crash", "Harbor crashed (exit 1, no directory)"),
        ("reset", "'Connection reset by peer', which a retrying caller would retry"),
    ):
        reset()
        sid = f"harbor_{mode}_v1"
        system(sid, {"agent": "oracle", "jobs_dir": f"artifacts/{sid}"})
        r = evh(
            "run",
            "--system",
            sid,
            "--dataset",
            "harbor_tasks_v1",
            "--run-id",
            f"{mode}1",
            FAKE_HARBOR_MODE=mode,
            FAKE_HARBOR_ONLY="write-greeting",
        )
        m = record(f"{mode}1")
        check(
            f"{mode}: {label}: a failed item (exit 0, not 75), harbor called once for it, never retried",
            r.returncode == 0
            and [f["item_id"] for f in m.get("failed_items") or []] == ["write-greeting"]
            and len(calls("write-greeting")) == 1,
            (r.returncode, len(calls("write-greeting")), (r.stdout + r.stderr)[-300:]),
        )
    reset()
    r = evh(
        "run",
        "--system",
        "harbor_crash_v1",
        "--dataset",
        "harbor_tasks_v1",
        "--run-id",
        "crash2",
        "--resume",
        "crash1",
        FAKE_HARBOR_MODE="crash",
        FAKE_HARBOR_ONLY="write-greeting",
    )
    check(
        "--resume does not call the failed item again (nor the two that have outputs)",
        r.returncode == 0 and calls() == [] and "called once already and not again" in r.stdout,
        (calls(), r.stdout[-400:]),
    )
    reset()
    r = evh(
        "run",
        "--system",
        "harbor_crash_v1",
        "--dataset",
        "harbor_tasks_v1",
        "--run-id",
        "crash3",
        "--resume",
        "crash2",
        "--recall-failed",
    )
    check(
        "--resume --recall-failed calls it once more, and it passes now",
        r.returncode == 0
        and len(calls()) == 1
        and calls()[0]["task"] == "write-greeting"
        and record("crash3").get("recalled") == ["write-greeting"]
        and record("crash3").get("scores", {}).get("pass") == 1.0,
        (calls(), (r.stdout + r.stderr)[-300:]),
    )

    # --- a hang: the adapter's own timeout, the whole process group ---
    for mode in ("hang", "stubborn"):
        reset()
        sid = f"harbor_{mode}_v1"
        system(sid, {"agent": "oracle", "jobs_dir": f"artifacts/{sid}", "timeout_s": 2, "kill_grace_s": 1})
        t0 = time.monotonic()
        r = evh(
            "run",
            "--system",
            sid,
            "--dataset",
            "harbor_tasks_v1",
            "--run-id",
            f"{mode}1",
            FAKE_HARBOR_MODE=mode,
            FAKE_HARBOR_ONLY="write-greeting",
        )
        took = time.monotonic() - t0
        m = record(f"{mode}1")
        failed = (m.get("failed_items") or [{}])[0]
        bad = next((x for x in rows(f"{mode}1") if x["item_id"] == "write-greeting"), {})
        pids = [int(x) for x in PIDS.read_text().split()] if PIDS.exists() else []
        alive = []
        for pid in pids:
            for _ in range(30):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.2)
            else:
                alive.append(pid)
        check(
            f"{mode}: the trial ends at the adapter's timeout (2 s) as a failed item, and Harbor was not called twice",
            r.returncode == 0
            and failed.get("item_id") == "write-greeting"
            and "HarborTimeout" in failed.get("error", "")
            and len(calls("write-greeting")) == 1
            and took < 120,
            (
                r.returncode,
                failed,
                len(calls("write-greeting")),
                round(took, 1),
                (r.stdout + r.stderr)[-300:],
            ),
        )
        check(
            f"{mode}: no process of it is left (Harbor and the child it started both gone)",
            len(pids) == 2 and not alive,
            (pids, alive),
        )
        check(
            f"{mode}: the failed item keeps its trial directory as the artifact",
            (bad.get("_meta") or {}).get("artifact", "").endswith("__hang001")
            and (proj / bad["_meta"]["artifact"]).is_dir()
            and bad.get("failed") == 1.0,
            bad,
        )

    # --- the recorded route, through the harness ---
    reset()
    r = evh(
        "capture",
        "--importer",
        f"{HERE / 'importer.py'}:Importer",
        "--query",
        json.dumps({"jobs_dir": str(FIXTURES)}),
        "--capture",
        "harbor_fx",
    )
    r = (
        r
        if r.returncode
        else evh("dataset-from-capture", "--capture", "harbor_fx", "--dataset-id", "harbor_hist_v1")
    )
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "harbor_hist_v1")
    r = (
        r
        if r.returncode
        else evh(
            "arm-from-capture",
            "--dataset-id",
            "harbor_hist_v1",
            "--capture",
            "harbor_fx",
            "--as",
            "harbor_recorded_v1",
            "--like",
            "harbor_oracle_v1",
        )
    )
    check(
        "capture, dataset and a recorded arm, from the recorded jobs",
        r.returncode == 0,
        (r.stdout + r.stderr)[-500:],
    )
    recorded = rows(next(n for n in _runstore.listdir(proj, "runs") if n.startswith("harbor_recorded_v1")))
    expect = {r_["id"]: adapter.score(adapter.recorded_output(r_)) for r_ in recs}
    check(
        "the recorded arm: every trial scored with the same `score` the live adapter uses: 3 passes, 4 zeros, one unanswered",
        len(recorded) == 8
        and all(all(x.get(k) == v for k, v in expect[x["item_id"]].items()) for x in recorded)
        and sum(x["pass"] for x in recorded) == 3.0
        and sum(x["answered"] for x in recorded) == 7.0,
        [(x["item_id"], x.get("pass"), x.get("answered")) for x in recorded],
    )
    check(
        "the recorded arm costs 0, calls harbor not at all, and is not call-once (nothing is called)",
        calls() == []
        and all((x.get("cost_usd") or 0) == 0 for x in recorded)
        and not record(
            next(n for n in _runstore.listdir(proj, "runs") if n.startswith("harbor_recorded_v1"))
        ).get("call_once"),
    )

    # --- the link, served ---
    r = evh("comparison-item", "--runs", "harbor_oracle_v1", "--item", "write-greeting", "--json")
    views = (json.loads(r.stdout)["result"]["values"].get("item") or {}).get("views") or {}
    art = next((v.get("artifact") for v in views.values()), None) or {}
    check(
        "comparison-item: the item's artifact is the trial's directory, a directory, with a url under artifacts/",
        art.get("kind") == "dir"
        and art.get("url", "").startswith("/artifacts/harbor_oracle_v1/")
        and art["url"].endswith("/"),
        art,
    )
    r = evh("catalog")
    check("the catalog builds with the runs in it", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = subprocess.Popen(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip
    try:
        for _ in range(200):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        (proj / art["path"] / "escape").symlink_to("/etc")

        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:  # nosec B310
                    return resp.status, dict(resp.headers), resp.read().decode(errors="replace")
            except urllib.error.HTTPError as exc:
                return exc.code, {}, ""

        st, h, body = get(art["url"])
        check(
            "the served url answers the trial's directory (a listing), read-only, with nosniff and sandbox",
            st == 200
            and "result.json" in body
            and h.get("X-Content-Type-Options") == "nosniff"
            and h.get("Content-Security-Policy") == "sandbox",
            (st, h),
        )
        st2, _, body2 = get(art["url"] + "verifier/ctrf.json")
        check("... and a file in it", st2 == 200 and "summary" in body2, st2)
        check(
            "... and a symlink an agent left in it to /etc is not followed",
            get(art["url"] + "escape/hostname")[0] == 404,
        )
    finally:
        os.killpg(srv.pid, signal.SIGTERM)
        srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(bindir, ignore_errors=True)
    shutil.rmtree(live_cwd, ignore_errors=True)

# --- a project that copies the example as the README says validates ---------------------------------------------------
import yaml  # noqa: E402

check(
    "every .yaml under systems/ is a system (a mapping): the template is a .yaml.example, which evh validate never reads",
    all(isinstance(yaml.safe_load(f.read_text()), dict) for f in (HERE / "systems").glob("*.yaml"))
    and (HERE / "systems" / "harbor_agent_template.yaml.example").is_file(),
    sorted(f.name for f in (HERE / "systems").iterdir()),
)
vproj = Path(tempfile.mkdtemp(prefix="evh-harbor-validate-"))
try:
    venv = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVH_ACTOR")}
    venv.update(EVAL_HOME=str(vproj), EVAL_BUILD_REF="test-harbor-validate")
    _runstore.write_text(vproj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (vproj / "data" / "systems").mkdir(parents=True)
    shutil.copytree(HERE, vproj / "examples" / "harbor", ignore=shutil.ignore_patterns("__pycache__"))

    def vevh(*a):
        return _cli.run(vproj, venv, *a, timeout=600)

    steps = [
        ("data-put", "--new", "--path", "validate.json", "--set", 'systems=["examples/harbor/systems/harbor_*_v1.yaml"]'),
        ("data-put", "--new", "--path", "fields/harbor_tasks.yaml", "--file", "examples/harbor/fields.yaml"),
        ("dataset-create", "--dataset-id", "harbor_tasks_v1", "--source", "examples/harbor/source.py:Source",
         "--query", '{"path": "examples/harbor/tasks"}', "--fieldset", "harbor_tasks"),
        ("dataset-materialize", "--dataset-id", "harbor_tasks_v1"),
    ]  # fmt: skip
    done = [vevh(*s) for s in steps]
    check(
        "the README's setup commands run in a project that holds a copy of the example",
        all(r.returncode == 0 for r in done),
        [r.stderr[-200:] for r in done if r.returncode],
    )
    r = vevh("validate")
    check(
        "evh validate passes there (its systems and the template included)",
        r.returncode == 0,
        (r.stdout + r.stderr)[-600:],
    )
    r = vevh("run", "--system", "harbor_oracle_v1", "--dataset", "harbor_tasks_v1", "--dry-run")
    check(
        "the example's systems are found where the README put them (a dry run, no Docker)",
        r.returncode == 0 and "calls each item once" in r.stdout,
        (r.stdout + r.stderr)[-300:],
    )
finally:
    shutil.rmtree(vproj, ignore_errors=True)

sys.exit(summary())
