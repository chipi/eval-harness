#!/usr/bin/env python3
"""The catalog's views as resources (RFC-032 step 8): overview, arms, metrics, activity, a comparison, label coverage.

    python tests/test_view_ops.py

In a throwaway project written here: three arms on two datasets, a goal, and a capture of decisions with outcome rules.
Each operation answers in the words its command prints (`op.say` is the command's text, byte for byte) and as data
(`op.call`); the legacy view commands are gone and the routes are not taken; an input that is
not one of its choices, an arm or a metric that is not there, a map outside the project and a comparison of arms the
catalog does not list are refused as the model refuses; and through the API and the command line the answers are the
same. The operations are registered here for the run (`registry.OPS`), so the test does not wait on the registry.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

proj = Path(tempfile.mkdtemp(prefix="evh-viewops-"))
os.environ.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-view-ops", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_PUBLIC"):
    os.environ.pop(k, None)

import _catalog_fixture as fx  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import (  # noqa: E402
    _format,
    _jsonout,
    _visibility,
)
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter, scores_once  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402
from evaluation_harness.model.entity import Problem  # noqa: E402
from evaluation_harness.ops import cli as ops_cli  # noqa: E402
from evaluation_harness.ops import legacy, registry, views  # noqa: E402

_outcomes_items = legacy.OUTCOMES["items"]

NEW = {op.name: op for op in views.OPS}
registry.OPS.update(NEW)  # what `ops/registry.py` does once it lists views


NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(fn, *a, **k) -> tuple[str, str]:
    """(the refusal's kind, its message) of a call, or ("", "") when it answered."""
    try:
        fn(*a, **k)
    except Problem as exc:
        return exc.kind, str(exc)
    return "", ""


def printed(fn, *a) -> str:
    """What a function prints."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a)
    return buf.getvalue().rstrip("\n")


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the project."""
    return _cli.run(proj, os.environ.copy(), *args, timeout=600)


def run(run_id: str, dataset: str, config: str, scores: list[float], **extra) -> None:
    """A run's own score: `acc` per item and a descriptive `words`."""
    rows = [json.dumps({"item_id": f"i{i:02d}", "acc": s, "words": 10.0 + i}) for i, s in enumerate(scores)]
    fx.put(
        proj / "data",
        run_id,
        {
            "run_id": run_id,
            "dataset_id": dataset,
            "system_id": config,
            "primary_metric": "acc",
            "metric_kinds": {"acc": "quality", "words": "descriptive"},
            "fingerprint": {"data": {"reference_id": f"gold/{dataset}"}},
            "created_at": NOW,
            **extra,
        },
        "\n".join(rows) + "\n",
        outputs={f"i{i:02d}": f"output of {config} {i}" for i in range(len(scores))},
    )


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        for d in ("systems", "goals", "datasets"):
            (proj / "data" / d).mkdir(parents=True, exist_ok=True)
    run("a_1", "ds1", "arm_a", [0.5] * 12)
    run("b_1", "ds1", "arm_b", [0.6] * 10 + [0.5, 0.4])
    run("b_2", "ds1", "arm_b", [0.8] * 10 + [0.5, 0.4])  # a repeat: averaged per item
    run("c_1", "ds2", "arm_c", [0.5] * 12)
    _runstore.write_text(
        proj,
        "goals/g1.yaml",
        "goal_id: g1\nschema_version: '0.1'\ntitle: The test goal\nsuccess_criteria:\n  primary: {measure: acc, "
        "direction: higher}\n  min_items: 10\noutput_contract: [{format: text}]\ndatasets: [{dataset_id: ds1}]\n",
    )

    # -- what the operations are -------------------------------------------------------------------------------
    hand = {c for c, (script, _about) in COMMANDS.items() if script != "op_command.py"}
    others = [o for n, o in registry.OPS.items() if n not in NEW]
    check(
        "the nine operations are reads, none named for a command that exists, none declared twice",
        len(NEW) == 9
        and all(o.kind == "read" and o.method == "GET" for o in NEW.values())
        and not set(NEW) & hand
        and not set(NEW) & {o.name for o in others},
        sorted(set(NEW) & hand),
    )

    def shape(route: str) -> list[str | None]:
        return [None if p.startswith("{") else p for p in route.strip("/").split("/")]

    clash = [
        (a, b.name)
        for a in NEW
        for b in others
        if b.method == "GET"
        and len(shape(b.route)) == len(shape(NEW[a].route))
        and all(x == y or x is None or y is None for x, y in zip(shape(b.route), shape(NEW[a].route)))
    ]
    check("no route is one another operation's: the server picks the first that matches", not clash, clash)
    check(
        "every input is typed: a string, an array of strings (the outside captures: of objects) or a flag; a choice names its values",
        all(
            s["type"] in ("string", "boolean")
            or (s["type"] == "array" and s["items"] in ({"type": "string"}, _outcomes_items))
            for o in NEW.values()
            for s in o.inputs.values()
        ),
    )
    check(
        "the routes: overview, arms (all, a dataset's, one), metrics (all, one), activity, compare, label coverage",
        {n: o.route for n, o in NEW.items()}
        == {
            "overview-show": "/overview",
            "arm-list": "/arms",
            "dataset-arm-list": "/datasets/{dataset}/arms",
            "arm-show": "/arms/{label}/{dataset}/{system}",
            "metric-list": "/metrics",
            "metric-show": "/metrics/{metric}",
            "activity-show": "/activity",
            "comparison-show": "/compare",
            "label-coverage-show": "/datasets/{dataset}/label-coverage",
        },
    )

    # -- the text is the command's, the data is the view -------------------------------------------------------
    def same_text(op: str, kwargs: dict, argv: list[str]) -> bool:
        """The operation's text is what its command prints."""
        r = evh(op, *argv)
        return r.returncode == 0 and NEW[op].say(NEW[op].call(**kwargs)) == r.stdout.rstrip("\n")

    check(
        "overview-show says what `evh overview-show` prints, for the default period and for all time",
        same_text("overview-show", {}, [])
        and same_text("overview-show", {"period": "all"}, ["--period", "all"]),
    )
    check(
        "activity-show says what `evh activity-show` prints, with its period and its arms",
        same_text("activity-show", {"period": "30d", "arms": "1"}, ["--period", "30d", "--arms", "1"]),
    )
    check(
        "metric-list and metric-show say what their commands print, whole and for one dataset and one metric",
        same_text("metric-list", {}, [])
        and same_text(
            "metric-list", {"dataset": "ds1", "period": "all"}, ["--dataset", "ds1", "--period", "all"]
        )
        and same_text("metric-show", {"metric": "acc"}, ["acc"])
        and same_text("metric-show", {"metric": "acc", "dataset": "ds1"}, ["acc", "--dataset", "ds1"]),
    )
    check(
        "arm-list, dataset-arm-list and arm-show say what their commands print",
        same_text("arm-list", {}, [])
        and same_text("arm-list", {"systems": "1", "period": "30d"}, ["--systems", "1", "--period", "30d"])
        and same_text("arm-list", {"where": "local"}, ["--where", "local"])
        and same_text("dataset-arm-list", {"dataset": "ds1"}, ["ds1"])
        and same_text(
            "arm-show", {"label": "runs", "dataset": "ds1", "system": "arm_b"}, ["runs", "ds1", "arm_b"]
        ),
    )
    check(
        "comparison-show says what `evh comparison-show --runs` prints",
        same_text(
            "comparison-show",
            {"runs": "runs/ds1/arm_a,runs/ds1/arm_b", "baseline": "runs/ds1/arm_a"},
            ["--runs", "runs/ds1/arm_a,runs/ds1/arm_b", "--baseline", "runs/ds1/arm_a"],
        ),
    )

    ov = NEW["overview-show"].call(period="all")
    check(
        "overview-show: the period, the tiles, each goal at a glance, activity, spend, coverage and what was recorded",
        ov["period"]["key"] == "all"
        and {t["what"] for t in ov["tiles"]} >= {"datasets", "arms"}
        and [g["goal"] for g in ov["goals"]] == ["g1"]
        and {c["dataset"] for c in ov["coverage"]} == {"ds1", "ds2"}
        and "dec" not in ov["goals"][0],
        sorted(ov),
    )
    check(
        "overview-show: a period that is not one is refused",
        refused(NEW["overview-show"].call, period="fortnight")[0] == "bad-argument",
    )
    arms = NEW["arm-list"].call()
    check(
        "arm-list: every arm, a goal as its id, the page's link left out; systems only when asked",
        sorted(r["arm"] for r in arms["arms"]) == ["runs/ds1/arm_a", "runs/ds1/arm_b", "runs/ds2/arm_c"]
        and next(r for r in arms["arms"] if r["arm"] == "runs/ds1/arm_a")["goal"] == "g1"
        and all("against" not in r for r in arms["arms"])
        and arms["systems"] is None
        and len(NEW["arm-list"].call(systems="1")["systems"]) == 3,
    )
    ids = lambda **kw: [r["arm"] for r in NEW["arm-list"].call(**kw)["arms"]]  # noqa: E731
    check(
        "arm-list: a dataset, a place and the goal's quality narrow the rows",
        ids(dataset="ds2") == ["runs/ds2/arm_c"]
        and [r["arm"] for r in NEW["dataset-arm-list"].call(dataset="ds1")["arms"]]
        == ["runs/ds1/arm_a", "runs/ds1/arm_b"]
        and ids(where="hosted") == []
        and ids(where="local") == ["runs/ds1/arm_a", "runs/ds1/arm_b", "runs/ds2/arm_c"]
        and ids(quality="below") == ["runs/ds1/arm_a"]
        and ids(quality="contender") == ["runs/ds1/arm_b"],
        ids(quality="below"),
    )
    check(
        "arm-list: what is not one of an input's choices is refused",
        refused(NEW["arm-list"].call, where="nowhere")[0] == "bad-argument"
        and refused(NEW["arm-list"].call, weights="free")[0] == "bad-argument"
        and refused(NEW["arm-list"].call, quality="best")[0] == "bad-argument"
        and refused(NEW["arm-list"].call, systems="yes")[0] == "bad-argument"
        and refused(NEW["arm-list"].call, period="fortnight")[0] == "bad-argument",
    )
    check(
        "dataset-arm-list: a dataset that is not there is refused as not found",
        refused(NEW["dataset-arm-list"].call, dataset="nope")[0] == "not-found",
    )
    one = NEW["arm-show"].call(label="runs", dataset="ds1", system="arm_b")
    check(
        "arm-show: one arm in full, its repeats counted, its metrics with which way is better, its runs",
        one["arm"] == "runs/ds1/arm_b"
        and one["runs"] == 2
        and {m["metric"]: m["better"] for m in one["metrics"]} == {"acc": "higher", "words": "neutral"}
        and sorted(r["run"] for r in one["run_list"]) == ["b_1", "b_2"]
        and one["headline"]["metric"] == "acc",
        one,
    )
    check(
        "arm-show: an arm that is not there is refused as not found",
        refused(NEW["arm-show"].call, label="runs", dataset="ds1", system="nope")[0] == "not-found",
    )
    mets = NEW["metric-list"].call()
    check(
        "metric-list: each metric with which way is better and where it is recorded; a dataset narrows them",
        {m["metric"]: m["better"] for m in mets["metrics"]}.get("acc") == "higher"
        and {m["metric"]: m["better"] for m in mets["metrics"]}.get("words") == "neutral"
        and next(m for m in mets["metrics"] if m["metric"] == "acc")["datasets"] == {"ds1": 2, "ds2": 1}
        and {m["metric"] for m in NEW["metric-list"].call(dataset="ds2")["metrics"]} == {"acc", "words"},
    )
    met = NEW["metric-show"].call(metric="acc", dataset="ds1")
    check(
        "metric-show: the arms recording it on a dataset, best first",
        [a["arm"] for a in met["datasets"][0]["arms"]] == ["arm_b ×2", "arm_a"]
        and met["datasets"][0]["dataset"] == "ds1",
        met["datasets"],
    )
    check(
        "metric-show: a metric nothing records is refused as not found",
        refused(NEW["metric-show"].call, metric="nope")[0] == "not-found",
    )
    act = NEW["activity-show"].call(period="all")
    check(
        "activity-show: runs by dataset, by arm and by kind; the arms are as many as asked",
        {r["dataset"] for r in act["by_dataset"]} == {"ds1", "ds2"}
        and act["by_arm"]["active"] == 3
        and len(NEW["activity-show"].call(period="all", arms="1")["by_arm"]["rows"]) == 1
        and refused(NEW["activity-show"].call, arms="many")[0] == "bad-argument",
        act["by_arm"],
    )
    cmp_ = NEW["comparison-show"].call(runs="runs/ds1/arm_a,runs/ds1/arm_b", baseline="runs/ds1/arm_a")
    check(
        "comparison-show: each arm tested against the baseline, as the inspector's /api/compare answers",
        cmp_["baseline"] == "runs/ds1/arm_a"
        and cmp_["metric"] == "acc"
        and [r["arm"] for r in cmp_["rows"]] == ["runs/ds1/arm_b"]
        and cmp_["item_word"] == "item"
        and cs.compare({"runs": ["runs/ds1/arm_a,runs/ds1/arm_b"], "baseline": ["runs/ds1/arm_a"]})["rows"]
        == cmp_["rows"],
        cmp_["rows"],
    )
    check(
        "comparison-show: an arm the catalog does not list is not found; arms of two datasets and a bad choice are refused",
        refused(NEW["comparison-show"].call, runs="runs/ds1/arm_a,runs/ds1/nope")[0] == "not-found"
        and refused(NEW["comparison-show"].call, runs="runs/ds1/arm_a,runs/ds2/arm_c")[0] == "bad-argument"
        and refused(NEW["comparison-show"].call, runs="runs/ds1/arm_a", rescore="2")[0] == "bad-argument",
    )

    def strict(x: object) -> bool:
        """Whether JSON holds it as it is: no NaN or infinity, nothing a decoder turns into something else."""
        try:
            return json.loads(json.dumps(x, allow_nan=False)) == x
        except (TypeError, ValueError):
            return False

    nan_prone = NEW["comparison-show"].call(runs="runs/ds1/arm_a,runs/ds1/arm_b", rescore="0")
    check(
        "every answer is what JSON holds: no NaN, infinity, tuple or date the encoder would turn into something else",
        all(strict(x) for x in (ov, arms, one, mets, met, act, cmp_, nan_prone)),
    )

    # -- label coverage: a capture of decisions and rules ------------------------------------------------------
    items = [{"item_id": f"d{i}", "source_path": f"d{i}.txt"} for i in range(4)]
    _runstore.write_text(proj, "datasets/dec_v1.json", json.dumps({"dataset_id": "dec_v1", "items": items}))
    rows = [
        {"id": f"d{i}", "body": "x", "created_at": "2026-01-01T00:00:00Z", "outcome": {"verdict": v}}
        for i, v in enumerate(["y", "n", "y"])
    ]
    (proj / "dec.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    made = evh(
        "capture", "--importer", "jsonl", "--query", json.dumps({"path": "dec.jsonl"}), "--capture", "dec"
    )
    check("setup: a capture of three decisions", made.returncode == 0, (made.stdout + made.stderr)[-300:])
    (proj / "rules.yaml").write_text(
        "- {when: {verdict: y}, label: file}\n- {when: {verdict: n}, label: dismiss}\n"
    )
    lc = NEW["label-coverage-show"]
    cov = lc.call(dataset="dec_v1", capture="dec", map="rules.yaml")
    check(
        "label-coverage-show: each item's class under the rules, counts, rules and the one item the capture lacks",
        cov["items"] == 4
        and cov["counts"]["labelled"] == 3
        and cov["counts"]["no_record"] == 1
        and [r["now"] for r in cov["rules"]] == [2, 1]
        and cov["map"] == "rules.yaml",
        cov["counts"],
    )
    cmd = evh("label-coverage-show", "dec_v1", "--capture", "dec", "--map", "rules.yaml")
    check(
        "label-coverage-show: says what `evh label-coverage-show` prints",
        cmd.returncode == 0 and lc.say(cov) == cmd.stdout.rstrip("\n"),
        (lc.say(cov), cmd.stdout),
    )
    check(
        "label-coverage-show: a map outside the project, a map that is not there, a capture or a dataset that is not "
        "there are refused with their kinds",
        refused(lc.call, dataset="dec_v1", capture="dec", map="../rules.yaml")[0] == "bad-argument"
        and refused(lc.call, dataset="dec_v1", capture="dec", map="/etc/passwd")[0] == "bad-argument"
        and refused(lc.call, dataset="dec_v1", capture="dec", map="nope.yaml")[0] == "not-found"
        and refused(lc.call, dataset="dec_v1", capture="nope", map="rules.yaml")[0] == "not-found"
        and refused(lc.call, dataset="nope", capture="dec", map="rules.yaml")[0] == "not-found"
        and refused(
            lc.call,
            dataset="dec_v1",
            capture="dec",
            map="rules.yaml",
            outcomes=[{"capture": "dec", "join": "bad"}],
        )[0]
        == "bad-argument",
    )

    with _visibility.public_call(True):
        public = refused(lc.call, dataset="dec_v1", capture="dec", map="rules.yaml")[0]
        NEW["comparison-show"].call(runs="runs/ds1/arm_a,runs/ds1/arm_b")
        limited = _visibility.public()
    check(
        "on a public call label coverage is refused, and a comparison is held to the public rules; a local call is not",
        public == "not-allowed" and limited and not _visibility.public(),
        (public, limited),
    )

    # -- through the API and the command line ------------------------------------------------------------------
    cs.set_adapter(scores_once(load_catalog_adapter(None)))
    cs.API_TOKEN[:] = ["viewops-token"]
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(proj)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def get(path: str) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1{path}", headers={"Authorization": "Bearer viewops-token"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def cli(op: str, *argv: str) -> dict:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ops_cli.main(NEW[op], [*argv, "--json"])
        return json.loads(buf.getvalue())

    wanted = {
        "overview-show": ("/overview?period=all", ["--period", "all"]),
        "arm-list": ("/arms?dataset=ds1&systems=1", ["--dataset", "ds1", "--systems", "1"]),
        "dataset-arm-list": ("/datasets/ds1/arms", ["ds1"]),
        "arm-show": ("/arms/runs/ds1/arm_b", ["runs", "ds1", "arm_b"]),
        "metric-list": ("/metrics?period=7d", ["--period", "7d"]),
        "metric-show": ("/metrics/acc?dataset=ds1", ["acc", "--dataset", "ds1"]),
        "activity-show": ("/activity?period=all&arms=2", ["--period", "all", "--arms", "2"]),
        "comparison-show": (
            "/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b&baseline=runs/ds1/arm_a",
            ["--runs", "runs/ds1/arm_a,runs/ds1/arm_b", "--baseline", "runs/ds1/arm_a"],
        ),
        "label-coverage-show": (
            "/datasets/dec_v1/label-coverage?capture=dec&map=rules.yaml",
            ["dec_v1", "--capture", "dec", "--map", "rules.yaml"],
        ),
    }
    got = {n: (get(path), cli(n, *argv)) for n, (path, argv) in wanted.items()}
    check(
        "the API's resource answers the command's --json: the same envelope and the same result, for all nine",
        all(
            st == 200 and body == env and env["command"] == n and set(env) == {"command", "version", "result"}
            for n, ((st, body), env) in got.items()
        ),
        {n: (st, list(body)) for n, ((st, body), _e) in got.items()},
    )
    check(
        "the API's answer is the operation's, as JSON holds it",
        all(
            env["result"] == _jsonout.plain(NEW[n].call(**kw))
            for n, kw, env in (
                ("arm-show", {"label": "runs", "dataset": "ds1", "system": "arm_b"}, got["arm-show"][0][1]),
                ("metric-show", {"metric": "acc", "dataset": "ds1"}, got["metric-show"][0][1]),
                ("dataset-arm-list", {"dataset": "ds1"}, got["dataset-arm-list"][0][1]),
            )
        ),
    )
    st404 = {
        "arm": get("/arms/runs/ds1/nope"),
        "dataset": get("/datasets/nope/arms"),
        "metric": get("/metrics/nope"),
        "label-coverage map": get("/datasets/dec_v1/label-coverage?capture=dec&map=../x.yaml"),
    }
    check(
        "the API refuses what the model refuses, with the model's status and kind",
        [(k, v[0], v[1].get("kind")) for k, v in st404.items()]
        == [
            ("arm", 404, "not-found"),
            ("dataset", 404, "not-found"),
            ("metric", 404, "not-found"),
            ("label-coverage map", 400, "bad-argument"),
        ],
        st404,
    )
    st400 = {
        "choice": get("/arms?where=nowhere"),
        "period": get("/overview?period=fortnight"),
        "no runs": get("/compare"),
        "unknown input": get("/arms?colour=red"),
    }
    check(
        "the API refuses an input that is not one of its choices and a read with a required input missing (400)",
        [(k, v[0]) for k, v in st400.items() if k != "unknown input"]
        == [("choice", 400), ("period", 400), ("no runs", 400)]
        and st400["unknown input"][0] == 200,
        st400,
    )
    srv.shutdown()

    # -- the legacy commands are gone ---------------------------------------------------------------------------
    for c in ("overview", "arms", "metrics", "activity", "inspect", "label-coverage"):
        check(f"`evh {c}` is not a command: its operation is", c not in COMMANDS and c not in NEW)
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
