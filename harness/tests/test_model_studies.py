#!/usr/bin/env python3
"""Studies through the model (RFC-032 step 7), in the suite's store.

    python tests/test_model_studies.py

In a project `evh init` makes, with two studies of one goal (a grid study that ended with three trials and a
confirmation, an agent study nothing has run) and one of another goal with the first's id, written as the study
commands write them:

- the model's layout is the one place a study's files are named: the studies list by their ids, a study id one goal has
  is found by its bare name, two goals' is refused naming both, a trial's system is where the project's systems are
  found (`_common.system_files`), and trials come in their numbers' order (t10 after t2);
- a study's state is its log's: status, round, the best trial, what it spent, its confirmations; a study with a spec and
  no log is "not started" in the list and absent from a goal's page;
- a spec is checked against its schema: every shape the commands write holds, a key that is not one and a sampler that
  names no program are refused;
- a study is read from the data directory it is asked for: a deployment's copy of the project's data is read through the
  catalog's adapter, and what the project's study logs afterwards is not in it;
- the copy holds the study whole (a dataset that is not hidden): its files byte for byte;
- `study-list` and `study-show` give the views' answers on the command line and through the API, and refuse a goal or
  a study that does not exist.
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
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-studies-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-studies")
release = Path(tempfile.mkdtemp(prefix="evh-studies-release-"))


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def put(rel: str, text: str) -> None:
    _runstore.write_text(proj, rel, text)


def log(rel: str, events: list[dict]) -> None:
    put(rel, "".join(json.dumps(e, sort_keys=True) + "\n" for e in events))


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
    raise RuntimeError(f"the server did not start: {(p.communicate()[0] or '')[-500:]}")


def call(port: int, path: str) -> tuple[int, dict]:
    """One API read with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", headers=h, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def dies(fn, *args) -> str:
    """The message of the refusal `fn` exits with, "" when it does not."""
    try:
        fn(*args)
    except SystemExit as exc:
        return str(exc)
    return ""


SYS = "system_id: {}\nparams:\n  provider: echo\n  sentences: {}\n"
GRID = ("dataset: tk_val\nbaseline: {system: one_v1}\nmeasure: overlap_f1\nsampler: grid\naccept: {point: {min_gain: 0}}\n"
        "stop: {trials: 5}\nspace:\n  groups:\n    - {name: length, reason: how much to keep, params: {sentences: [2, 3, 4]}}\n")  # fmt: skip
AGENT = ("dataset: tk_val\nbaseline: {system: one_v1}\nmeasure: overlap_f1\nsampler: agent\naccept: {point: {min_gain: 0}}\n"
         "stop: {trials: 10}\ndirections: keep what a reader needs\n")  # fmt: skip
START = {
    "event": "start",
    "round": "r1",
    "baseline": "one_v1",
    "at": "2026-11-12T14:00:00Z",
    "spec_sha256": "x",
}


def trial(k: int, outcome: str, delta: float, **more) -> dict:
    return {"event": "trial", "k": k, "config_id": f"s1-t{k}", "from": "one_v1", "outcome": outcome, "cost_usd": 0.01,
            "reason": f"decided {outcome}", "hypothesis": f"sentences = {k + 1}", "runs": [f"s1-t{k}_r"],
            "change": {"params": {"sentences": k + 1}, "prompts": []}, "vs_best": {"delta": delta, "p": 0.01},
            "at": f"2026-11-12T14:0{k}:00Z", **more}  # fmt: skip


LOOK = {"set": "d" * 16, "number": 1, "level": 0.0152}
EVENTS = [
    START,
    trial(1, "kept", 0.25, shown=[{"item_id": "t01", "sha256": "h1"}]),
    {"event": "group", "k": 1, "group": "length"},
    trial(2, "dropped", -0.1667),
    {"event": "end", "reason": "the space is exhausted", "spent_usd": 0.02, "summary": "2 trial(s), 1 kept"},
    {"event": "confirm", "phase": "named", "trial": 1, "test": "tk_test", "rule": "superiority", "items": 2},
    {"event": "confirm", "phase": "verdict", "trial": 1, "test": "tk_test", "rule": "superiority", "outcome": "better",
     "delta": 0.3, "validation_delta": 0.25, "look": LOOK, "actor": {"type": "person", "name": "owner"}},
]  # fmt: skip

try:
    r = evh("init")
    r = (
        r
        if r.returncode
        else subprocess.run(["git", "-C", str(proj), "init", "-q"], capture_output=True, text=True)
    )
    check("setup: a project", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    put("goals/g.yaml", "goal_id: g\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n  - {dataset_id: tk_test, role: test}\n")  # fmt: skip
    put("studies/g/s1.yaml", GRID)
    log("studies/g/s1.events.jsonl", EVENTS)
    for n in (1, 2, 10):
        put(f"studies/g/s1/s1-t{n}.yaml", SYS.format(f"s1-t{n}", n + 1))
    put("studies/g/s1/confirm/t1-on-tk_test.items", "t01\nt02\n")
    put("studies/g/s2.yaml", AGENT)
    put("studies/h/s1.yaml", GRID)
    put("goals/h.yaml", "goal_id: h\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n")  # fmt: skip
    put("datasets/tk_test.json", json.dumps({"dataset_id": "tk_test", "version": "1.0", "created_at": "2026-11-14T00:00:00Z",
                                             "items": [{"item_id": "t01", "source_path": "t01.txt", "source_sha256": "a" * 64}]}))  # fmt: skip
    _runstore.migrate_in(proj)

    from evaluation_harness import _common, _looks, _release
    from evaluation_harness import catalog_build as cb
    from evaluation_harness.catalog_adapter import HarnessAdapter
    from evaluation_harness.model import studies as ms
    from evaluation_harness.model import study_views as sv

    LOOK["set"] = _looks.digest("tk_test")  # the set's own digest: what the look is counted on
    log("studies/g/s1.events.jsonl", EVENTS)

    # ── the layout ────────────────────────────────────────────────────────────────────────────────────────────────
    check(
        "the studies list by their ids, `<goal>/<study_id>`, from their specs",
        ms.ids() == ["g/s1", "g/s2", "h/s1"] and ms.ids("g") == ["g/s1", "g/s2"],
        (ms.ids(), ms.ids("g")),
    )
    found = {p.name for p in _common.system_files()}
    check(
        "a trial's system is where `_common.system_files` finds the project's systems, and trials come in their numbers' "
        "order",
        ms.trial_path("g", "s1", 1) in _common.system_files()
        and [p.name for p in ms.trial_systems("g", "s1")] == ["s1-t1.yaml", "s1-t2.yaml", "s1-t10.yaml"]
        and {"s1-t1.yaml", "s1-t2.yaml", "s1-t10.yaml"} <= found,
        ([p.name for p in ms.trial_systems("g", "s1")], sorted(found)),
    )
    check(
        "a confirmation's items are in the study's confirm folder, named by the trial and the test set",
        ms.confirm_items("g", "s1", 1, "tk_test").parent == ms.confirm_dir("g", "s1")
        and ms.confirm_items("g", "s1", 1, "tk_test").name == "t1-on-tk_test.items"
        and _runstore.is_file(proj, "studies/g/s1/confirm/t1-on-tk_test.items"),
        str(ms.confirm_items("g", "s1", 1, "tk_test")),
    )
    refused_name = dies(ms.resolve, "s1")
    check(
        "a study id one goal has is found by its bare name; two goals' is refused naming both; no goal's is refused",
        ms.resolve("s2") == ("g", "s2")
        and ms.resolve("h/s1") == ("h", "s1")
        and "several goals have one (g, h): name it <goal>/s1" in refused_name
        and "no such study" in dies(ms.resolve, "nope")
        and "no study g/nope" in dies(ms.resolve, "g/nope"),
        (refused_name, dies(ms.resolve, "nope")),
    )

    # ── the state, from the log ───────────────────────────────────────────────────────────────────────────────────
    st = ms.state("g", "s1")
    check(
        "a study's state is its log's: ended, its round, three trials' worth of spend, the best kept trial, its confirm "
        "lines, the trial's group",
        st["status"] == "ended"
        and st["round"] == "r1"
        and st["baseline"] == "one_v1"
        and len(st["trials"]) == 2
        and (st["best"] or {}).get("config_id") == "s1-t1"
        and st["spent_usd"] == 0.02
        and len(st["confirms"]) == 2
        and st["trials"][0].get("group") == "length",
        {k: v for k, v in st.items() if k not in ("trials", "start", "end", "confirms")},
    )
    check(
        "a study with a spec and no log is not started",
        ms.state("g", "s2")["status"] == "not started" and ms.events("g", "s2") == [],
        ms.state("g", "s2")["status"],
    )
    check(
        "the items shown to a sampler in any study of the goal, by id and by content; another goal's are not",
        ms.shown("g") == {"t01", "h1"} and ms.shown("h") == set(),
        ms.shown("g"),
    )
    conf = ms.confirms()
    check(
        "the confirm lines of every study, each with its study's id (what the test set's looks are counted from)",
        [c["study"] for c in conf] == ["s1", "s1"]
        and {c.get("phase") for c in conf} == {"named", "verdict"}
        and any(x.get("what", "").endswith("s1") for x in _looks.recorded("tk_test"))
        and any(x.get("number") == 1 for x in _looks.recorded("tk_test")),
        (conf, _looks.recorded("tk_test")),
    )

    # ── the views ─────────────────────────────────────────────────────────────────────────────────────────────────
    page = sv.of_goal("g")
    check(
        "a goal's studies as its page shows them: the study with its log, its trials in rows; a spec nothing has run is "
        "not there",
        [s["study"] for s in page] == ["s1"]
        and page[0]["status"] == "ended"
        and page[0]["end"] == "the space is exhausted"
        and [r["change"] for r in page[0]["rows"]] == ["sentences = 2", "sentences = 3"]
        and [c["outcome"] for c in page[0]["confirms"]] == ["better"]
        and page[0]["round"] == "r1",
        page,
    )
    lst = sv.list_studies("g")
    check(
        "study-list's rows: both studies, the one nothing has run as not started",
        [(x["study"], x["status"], x["trials"], x["kept"]) for x in lst]
        == [("g/s1", "ended", 2, 1), ("g/s2", "not started", 0, 0)]
        and lst[0]["dataset"] == "tk_val"
        and lst[0]["measure"] == "overlap_f1"
        and lst[0]["confirms"] == 2,
        lst,
    )
    show = sv.show_study("g", "s1")
    check(
        "study-show: the spec as written, the trials, the best, how it ended, the confirmations and the trials' systems",
        show["spec"]["sampler"] == "grid"
        and show["best"] == "s1-t1"
        and show["summary"] == "2 trial(s), 1 kept"
        and show["trial_systems"] == ["s1-t1", "s1-t2", "s1-t10"]
        and len(show["confirms"]) == 2
        and show["file"].endswith("studies/g/s1.yaml")
        and show["open_ask"] is None,
        {k: v for k, v in show.items() if k != "spec"},
    )

    # ── the schema ────────────────────────────────────────────────────────────────────────────────────────────────
    from evaluation_harness.model.entity import Problem

    check(
        "a spec the commands write holds against its schema (grid, agent)",
        ms.problems("g/s1") == [] and ms.problems("g/s2") == [],
        (ms.problems("g/s1"), ms.problems("g/s2")),
    )
    import yaml

    shapes = {
        "command sampler, the test rule, limits, repeats, frozen":
            "dataset: v\nbaseline: {system: a}\nmeasure: m\nsampler: {command: 'python s.py'}\n"
            "accept: {rule: test, margin: 0.01, tie_break: cost}\nlimits: [{metric: cost, direction: lower, limit: 0.1}]\n"
            "stop: {usd: 5, wall_h: 2, patience: 3, ask_timeout_h: 1}\nrepeats: 2\nfrozen: [a.py]\nshow_items: 3\ndirection: lower\n",
        "accept: test": "dataset: v\nbaseline: {system: a}\nmeasure: m\nsampler: agent\naccept: test\nstop: {trials: 3}\n",
        "an imported study": "imported: true\nsource: results.tsv\nmeasure: val_bpb\ndirection: lower\nnote: imported\n",
        "a prompt space": "dataset: v\nbaseline: {system: a}\nmeasure: m\nsampler: agent\naccept: test\nstop: {trials: 3}\n"
                          "space: {prompts: [lib/a.txt], max_candidates: 4, groups: [{name: g, enabled: false, move_on_after: 2, params: {x: {low: 1, high: 3, step: 1}}}]}\n",
    }  # fmt: skip
    bad_shapes = {
        "a key that is not one": "dataset: v\nstoop: {trials: 3}\n",
        "a sampler named command, which names no program": "dataset: v\nsampler: command\n",
        "a baseline that names a config": "baseline: {config: a}\n",
        "a patience of none": "stop: {patience: 0}\n",
    }
    for name, text in shapes.items():
        put("studies/x/shape.yaml", text)
        check(f"schema: {name} holds", ms.problems("x/shape") == [], ms.problems("x/shape"))
    for name, text in bad_shapes.items():
        put("studies/x/shape.yaml", text)
        check(f"schema: {name} is refused", bool(ms.problems("x/shape")), ms.problems("x/shape"))
    _runstore.unlink(proj, "studies/x/shape.yaml")
    try:
        ms.STUDY.save("g/s1", yaml.safe_load(GRID), "person:tester")
        refused = ""
    except Problem as exc:
        refused = exc.kind
    check(
        "a study is written by its own commands: an edit is refused, nothing written",
        refused == "not-allowed",
        refused,
    )

    # ── validate (V27) ────────────────────────────────────────────────────────────────────────────────────────────
    v_ok = evh("validate")
    put("studies/g/s1.yaml", GRID + "stoop: 1\n")
    put("studies/nogoal/s9.yaml", GRID)
    log("studies/g/s1.events.jsonl", [*EVENTS, trial(3, "kept", 0.3), {"event": "bogus"}])
    v_bad = evh("validate")
    put("studies/g/s1.yaml", GRID)
    _runstore.unlink(proj, "studies/nogoal/s9.yaml")
    log("studies/g/s1.events.jsonl", EVENTS)
    check(
        "validate V27: the studies pass; a spec with a key that is not one, a study of a goal that does not exist, a log "
        "line of an event no study writes and a trial with no system fail, each named",
        "ok   V27 studies — 3 study(ies)" in v_ok.stdout
        and "FAIL V27" in v_bad.stdout
        and "not a field of this setting: 'stoop'" in v_bad.stdout
        and "nogoal/s9: no goal 'nogoal'" in v_bad.stdout
        and "g/s1: a log line of event 'bogus'" in v_bad.stdout
        and "g/s1: trial 3 has no system (s1-t3.yaml)" in v_bad.stdout,
        (v_ok.stdout[-500:], v_bad.stdout[-900:]),
    )

    # ── read where the data is: a deployment's copy ───────────────────────────────────────────────────────────────
    counts = _release.copy_data(proj / "data", release)
    same = all(
        _runstore.read_bytes(proj, f"studies/{rel}") == (release / "studies" / rel).read_bytes()
        for rel in (
            "g/s1.yaml",
            "g/s1.events.jsonl",
            "g/s1/s1-t1.yaml",
            "g/s1/s1-t10.yaml",
            "g/s1/confirm/t1-on-tk_test.items",
            "g/s2.yaml",
            "h/s1.yaml",
        )
    )
    check(
        "the release copy holds a study whole, byte for byte, for a dataset that is not hidden",
        same
        and counts["hidden_studies"] == 0
        and (release / "studies" / "g" / "s1" / "s1-t2.yaml").is_file(),
        counts,
    )
    check(
        "a study is read from the data directory it is asked for: the copy's views are the project's",
        ms.ids(data=release) == ms.ids()
        and sv.of_goal("g", release) == sv.of_goal("g")
        and ms.state("g", "s1", release) == ms.state("g", "s1")
        and ms.confirms(release) == ms.confirms()
        and ms.shown("g", release) == ms.shown("g")
        and [p.name for p in ms.system_files(release)] == [p.name for p in ms.system_files()] != [],
        sv.of_goal("g", release),
    )
    (release / "studies" / "g" / "s1" / "s1-t10.yaml").unlink()
    check(
        "a study's systems are read from the data directory asked for: the copy lost one, the project has it",
        sorted(p.name for p in ms.system_files(release)) == ["s1-t1.yaml", "s1-t2.yaml"]
        and "s1-t10.yaml" in [p.name for p in ms.system_files()],
        [p.name for p in ms.system_files(release)],
    )
    # The project's study moves on; the copy does not (a reader that took the project's data instead would see it).
    log("studies/g/s1.events.jsonl", [*EVENTS, trial(3, "kept", 0.3)])
    moved = sv.of_goal("g")
    A = HarnessAdapter(release)
    A_proj = HarnessAdapter()
    check(
        "a deployment's studies are the copy's: what the project logged after the copy is not in them, and is in the "
        "project's",
        len(moved[0]["rows"]) == 3
        and len(sv.of_goal("g", release)[0]["rows"]) == 2
        and [r["k"] for r in A.studies("g")[0]["rows"]] == [1, 2]
        and [r["k"] for r in A_proj.studies("g")[0]["rows"]] == [1, 2, 3],
        ([len(s["rows"]) for s in moved], [r["k"] for r in A.studies("g")[0]["rows"]]),
    )
    goal = next(g for g in A.goals() if g["goal_id"] == "g")
    block = cb._studies_block(A, goal)
    check(
        "the catalog's goal page block, built on the copy, shows the study, its trials and its confirmation",
        'id="study-s1"' in block
        and "sentences = 2" in block
        and "decided dropped" in block
        and "confirmed on tk_test" in block
        and "<b>better</b>" in block
        and "sentences = 4" not in block,
        block[:600],
    )

    # ── the operations, on the command line and through the API ───────────────────────────────────────────────────
    log("studies/g/s1.events.jsonl", EVENTS)
    pairs = {
        "study-list": ("/goals/g/studies", ("g",)),
        "study-show": ("/goals/g/studies/s1", ("g", "s1")),
    }
    got = {n: result(evh(n, *args, "--json")) for n, (_route, args) in pairs.items()}
    check(
        "study-list and study-show answer the views' rows, and `evh studies` still lists what it did",
        got["study-list"] == {"goal": "g", "studies": sv.list_studies("g")}
        and got["study-show"] == json.loads(json.dumps(sv.show_study("g", "s1")))
        and {x["study"] for x in result(evh("studies", "--json"))["values"]["studies"]} == {"s1", "s2"}
        and "g/s1" in evh("study-list", "g").stdout
        and "round r1" in evh("study-show", "g", "s1").stdout,
        (got["study-list"], evh("study-list", "g").stderr[-200:]),
    )
    nogoal, nostudy, empty = (
        evh("study-list", "no_such"),
        evh("study-show", "g", "nope"),
        evh("study-list", "h"),
    )
    check(
        "a goal that does not exist and a study that does not exist are refused; a goal with no studies says so",
        nogoal.returncode != 0
        and "no goal 'no_such'" in nogoal.stderr
        and nostudy.returncode != 0
        and "no study 'g/nope'" in nostudy.stderr,
        (nogoal.stderr[-200:], nostudy.stderr[-200:], empty.stdout, empty.stderr[-200:]),
    )
    r = evh("catalog")
    p, port = serve() if r.returncode == 0 else (None, 0)
    try:
        api = {n: call(port, route) for n, (route, _args) in pairs.items()} if p else {}
        missing = call(port, "/goals/g/studies/nope") if p else (0, {})
        check(
            "the API's resources give the command line's answers; a study that does not exist is a 404",
            p is not None
            and all(api[n][0] == 200 and api[n][1].get("result") == got[n] for n in pairs)
            and missing[0] == 404,
            (r.stderr[-200:], {n: v[0] for n, v in api.items()}, missing),
        )
    finally:
        if p:
            p.terminate()
            p.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(release, ignore_errors=True)

sys.exit(summary())
