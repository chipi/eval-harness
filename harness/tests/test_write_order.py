#!/usr/bin/env python3
"""What a reader sees while a command writes (RFC-026 step 1): nothing half done.

    python tests/test_write_order.py

In a throwaway project ($0, offline): a run killed partway is not listed (its metrics.json, written last, is
missing); a rescore whose scorer fails partway leaves nothing listed; a reference promotion that fails partway
leaves no reference folder and no staging folder (it is built beside its place and moved in whole). And a file
written over is never seen cut short: the old bytes or the new ones.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-write-order-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-write-order")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """import os
from evaluation_harness.adapter import Result, score as _score
N = [0]
def call_system(text, params):
    N[0] += 1
    if os.environ.get("KILL_AT") and N[0] == int(os.environ["KILL_AT"]):
        os._exit(9)  # killed partway: no clean end
    return Result(output=text.split(".")[0] + ".", cost_usd=0.0)
def score(output, reference):
    if os.environ.get("SCORE_FAILS"):
        N[0] += 1
        if N[0] == 3:
            raise RuntimeError("the scorer broke partway")
    return _score(output, reference)
"""


def evh(*args, **extra):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **extra},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def out(r):
    return r.stdout + r.stderr


def listed():
    r = evh("runs-list", "--json")
    rows = [
        x for b in (json.loads(r.stdout).get("result") or {}).get("blocks", []) for x in b.get("rows", [])
    ]
    return {x["run_id"] for x in rows}


try:
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "adapter.py").write_text(ADAPTER)
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
            "--reason", "the kit's summaries, for the test", "--by", "t",
        )
    )  # fmt: skip
    check("setup: a dataset with gold", r.returncode == 0, out(r)[-300:])
    _runstore.write_text(
        proj,
        "configs/a.yaml",
        "config_id: a_v1\ndataset_id: tk_v1\nadapter: adapter.py\nparams:\n  provider: echo\n",
    )
    r = evh("run", "--config", "data/configs/a.yaml", "--run-id", "a_killed", KILL_AT="3")
    check(
        "a run killed partway is not listed: its metrics.json is written last",
        r.returncode != 0
        and "a_killed" not in listed()
        and not _runstore.exists(proj, "runs/a_killed/metrics.json"),
        out(r)[-300:],
    )
    r = evh("run", "--config", "data/configs/a.yaml", "--run-id", "a_whole")
    check("a run that ends is listed", r.returncode == 0 and "a_whole" in listed(), out(r)[-300:])
    r = evh(
        "rescore",
        "--dataset-id",
        "tk_v1",
        "--match",
        "a_v1",
        "--out",
        "data/runs-rescored-test",
        SCORE_FAILS="1",
    )
    gone = not _runstore.exists(proj, "runs-rescored-test/a_whole/metrics.json")
    check(
        "a rescore whose scorer fails partway leaves no rescored run",
        r.returncode != 0 and "the scorer broke partway" in out(r) and gone,
        out(r)[-300:],
    )

    # A reference promotion that fails partway: the manifest write raises, in the command's own process.
    r = evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g2", "--by", "t")
    check("setup: a second label set to promote", r.returncode == 0, out(r)[-300:])
    breaker = proj / "breaker.py"
    breaker.write_text(
        "import runpy, sys\n"
        "from evaluation_harness import _references\n"
        "def broken(*a, **k):\n"
        "    raise OSError('disk full')\n"
        "_references.write_manifest = broken\n"
        "import evaluation_harness.reference_promote as rp\n"
        "rp.write_manifest = broken\n"
        "sys.argv = ['reference-promote'] + sys.argv[1:]\n"
        "raise SystemExit(rp.main())\n"
    )
    r = subprocess.run(
        [
            sys.executable, str(breaker), "--dataset-id", "tk_v1", "--labels", "g2", "--tier", "silver",
            "--reason", "promoted to fail partway", "--by", "t",
        ],
        cwd=proj, env={**env, "PYTHONPATH": str(HERE.parent)}, capture_output=True, text=True,
    )  # fmt: skip
    leftovers = (
        [p.name for p in (proj / "data" / "references" / "silver").glob(".*")]
        if (proj / "data" / "references" / "silver").is_dir()
        else []
    )
    check(
        "a reference promotion that fails partway leaves no reference and no staging folder",
        r.returncode != 0
        and "disk full" in out(r)
        and not _runstore.exists(proj, "references/silver/tk_v1/manifest.json")
        and not any(_runstore.files_under(proj, "references/silver"))
        and not leftovers,
        (out(r)[-300:], leftovers),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# A file written over while another thread reads it: the old bytes or the new ones, never a cut.
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "big.json"
    olds, news = b"a" * 400_000, b"b" * 800_000
    f.write_bytes(olds)
    seen: set[str] = set()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                b = f.read_bytes()
            except FileNotFoundError:
                seen.add("missing")
                continue
            seen.add("old" if b == olds else "new" if b == news else f"cut at {len(b)}")

    t = threading.Thread(target=reader)
    t.start()
    for i in range(60):
        _store.write_bytes(f, news if i % 2 == 0 else olds)
    stop.set()
    t.join()
    check("a file written over is read whole, old or new, never cut or missing", seen <= {"old", "new"}, seen)
sys.exit(summary())
