#!/usr/bin/env python3
"""A run-level metric: the adapter's score_run(items) (the fleet's feedback 20).

    python tests/test_run_metrics.py

In a throwaway project ($0, offline): an adapter whose score_run() computes one number over the whole run (here
the share of items whose output is longer than its reference, and how many items it saw). The run records it in
`scores` and names it in `run_metrics`; the leaderboard shows it; pair-test and family-test refuse to test it item
by item, by name; a rescore recomputes it from the stored outputs; the comparison shows it as an average, never
tested. A score_run() that returns a per-item metric's name, a non-number, or raises is refused.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import _runview  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-run-metrics-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-run-metrics")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """from evaluation_harness.adapter import Result, score  # noqa: F401
def call_system(text, params):
    n = int(params.get("sentences", 1))
    return Result(output=". ".join(text.split(". ")[:n]), cost_usd=0.0)
def score_run(items):
    longer = sum(1 for it in items if it["reference"] and len(it["output"]) > len(it["reference"]))
    return {"share_longer": longer / len(items), "items_seen": len(items)}
"""


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def metrics_of(prefix):
    return _runview.record_of(proj, prefix)


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "o")
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's hand-written summaries", "--by", "o",
        )
    )  # fmt: skip
    check("setup: a dataset with gold", r.returncode == 0, out(r)[-300:])
    (proj / "adapter.py").write_text(ADAPTER)
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj,
            f"systems/{cid}.yaml",
            f"system_id: {cid}\nadapter: adapter.py\nparams:\n  provider: echo\n  sentences: {n}\n",
        )
        r = evh("run", "--system", cid, "--dataset", "tickets_v1")
        check(f"setup: {cid} runs", r.returncode == 0, out(r)[-400:])
    name, m = metrics_of("one_v1_")
    check(
        "run: score_run's numbers are in scores, named in run_metrics, beside the per-item means",
        m.get("run_metrics") == ["items_seen", "share_longer"]
        and m["scores"].get("items_seen") == 6
        and 0 <= m["scores"].get("share_longer", -1) <= 1
        and "overlap_f1" in m["scores"],
        json.dumps(m.get("scores")) + str(m.get("run_metrics")),
    )
    rows = _runview.rows_of(proj, name)
    check(
        "run: a run-level metric is on no item's row",
        len(rows) == 6 and not any("share_longer" in x or "items_seen" in x for x in rows),
    )
    r = evh("validate")
    check("validate: a record with run_metrics passes the schema", r.returncode == 0, r.stdout[-600:])

    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--json")
    lb = json.loads(r.stdout) if r.returncode == 0 else {}
    cols = [c for b in (lb.get("result") or {}).get("blocks", []) for c in b.get("columns", [])]
    check(
        "leaderboard: shows the run-level metric as a column",
        "share_longer" in cols,
        r.stdout[-600:] + r.stderr[-300:],
    )

    for cmd in (
        (
            "pair-test",
            "--dataset-id",
            "tickets_v1",
            "--a",
            "one_v1",
            "--b",
            "two_v1",
            "--metric",
            "share_longer",
        ),
        (
            "family-test",
            "--dataset-id",
            "tickets_v1",
            "--a",
            "one_v1",
            "--against",
            "two_v1",
            "--metric",
            "share_longer",
        ),
    ):
        r = evh(*cmd)
        check(
            f"{cmd[0]}: a run-level metric is refused by name, not 'nothing to test'",
            r.returncode != 0
            and "share_longer is a run-level metric" in out(r)
            and "Traceback" not in out(r),
            out(r)[-400:],
        )
    r = evh("inspect", "--runs", "one_v1,two_v1", "--metric", "share_longer")
    check(
        "inspect --metric <run-level>: said it cannot be tested, with each arm's recorded value, and what was compared",
        r.returncode == 0
        and "share_longer has no score per item for these runs, so it cannot be tested: recorded per run as"
        in r.stdout
        and "Compared on overlap_f1 instead" in r.stdout,
        out(r)[-700:],
    )
    r = evh("inspect", "--runs", "one_v1,two_v1")
    check(
        "inspect: with no --metric, a per-item metric is compared, not the run-level one",
        r.returncode == 0 and "share_longer" not in r.stdout.splitlines()[0] if r.stdout else False,
        out(r)[-500:],
    )
    r = evh(
        "pair-test", "--dataset-id", "tickets_v1", "--a", "one_v1", "--b", "two_v1", "--metric", "overlap_f1"
    )
    check("pair-test: a per-item metric of the same runs still tests", r.returncode == 0, out(r)[-300:])

    (proj / "adapter.py").write_text(
        ADAPTER.replace('"items_seen": len(items)', '"items_seen": len(items) + 100')
    )
    r = evh("rescore", "--match", "one_v1", "--dataset-id", "tickets_v1")
    rs = [rec for _k, lb, rec in _runview.scores_of(proj, name) if lb.startswith("rescored ")]
    rm = rs[-1] if rs else {}
    check(
        "rescore: the run-level metric is recomputed by the current score_run, from the stored outputs",
        r.returncode == 0 and (rm.get("scores") or {}).get("items_seen") == 106 and rm.get("run_metrics"),
        out(r)[-400:] + json.dumps(rm.get("scores")),
    )
    (proj / "adapter.py").write_text(ADAPTER)

    for bad, said in (
        ('{"overlap_f1": 1.0}', "also a per-item metric"),
        ('{"x": "high"}', "not a name and a finite number"),
        ("1 / 0", "score_run() raised"),
    ):
        (proj / "adapter.py").write_text(
            ADAPTER.split("def score_run")[0] + f"def score_run(items):\n    return {bad}\n"
        )
        r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1")
        check(
            f"run: score_run returning {bad} is refused ({said})",
            r.returncode != 0 and said in out(r),
            out(r)[-300:],
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
