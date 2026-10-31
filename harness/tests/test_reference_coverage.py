#!/usr/bin/env python3
"""A run scored against references for only some of its items says so, and records it.

    python tests/test_reference_coverage.py

experiment-run took a gold directory as covering the dataset: an item with no reference file
was simply not scored, so gold for 20 of 200 items gave a 20-item mean recorded as a 200-item
gold run, with no warning. Now: partial coverage is warned, recorded (reference_coverage) and
named by the leaderboard; a reference directory with no file for any item is refused before a
single call. $0, offline (the tutorial's echo arms).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-coverage-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-coverage")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
    shutil.copy(KIT / "configs" / "tickets_lead1.yaml", data / "configs")
    gold = data / "references" / "gold" / "tickets_v1"
    gold.mkdir(parents=True)
    files = sorted((KIT / "gold").glob("*.txt"))
    for f in files[:2]:
        shutil.copy(f, gold / f.name)

    r = evh("experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--run-id", "partial")
    out = r.stdout + r.stderr
    m = json.loads((data / "runs" / "partial" / "metrics.json").read_text()) if r.returncode == 0 else {}
    check(
        "partial gold: the run warns how many items have a reference",
        r.returncode == 0 and f"only 2 of {len(files)} items have a gold reference" in out,
        out[-400:],
    )
    check(
        "partial gold: the run records it",
        m.get("reference_coverage") == {"items_with_reference": 2, "items": len(files)},
        str(m.get("reference_coverage")),
    )
    lb = evh("leaderboard", "--dataset-id", "tickets_v1")
    check(
        "the leaderboard names a run whose quality is a mean over some items",
        f"had a reference for 2 of {len(files)} items" in lb.stdout,
        lb.stdout[-500:],
    )
    r = evh("validate")
    check("validate accepts the recorded coverage (schema)", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    for f in gold.iterdir():
        f.unlink()
    (gold / "not_an_item.txt").write_text("x")
    r = evh("experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--run-id", "none")
    check(
        "a reference directory with no file for any item is refused before a call",
        r.returncode != 0
        and "nothing would be scored" in (r.stdout + r.stderr)
        and not (data / "runs" / "none").exists(),
        (r.stdout + r.stderr)[-400:],
    )

    # rescore keeps what a project adapter attached at call time (`_extra` names it); it used
    # to drop any extra not named `truncated` or `reasoning_tokens` and call it a dropped metric.
    (proj / "adapter.py").write_text(
        "from evaluation_harness.adapter import Result\n"
        'PRIMARY_METRIC = "overlap_f1"\n'
        "def call_system(text, params):\n"
        '    return Result(output=text.split(".")[0] + ".", cost_usd=0.0, extra={"my_extra": 1.0})\n'
        "def score(output, reference):\n"
        '    return {"overlap_f1": 0.5} if reference is not None else {"output_words": 1.0}\n'
    )
    for f in files:
        shutil.copy(f, gold / f.name)
    (data / "configs" / "own.yaml").write_text(
        "config_id: own_v1\ndataset_id: tickets_v1\nadapter: adapter.py\nparams:\n  provider: echo\n"
    )
    env["PYTHONPATH"] = str(HERE)
    r = evh("experiment-run", "--config", "data/configs/own.yaml", "--run-id", "own")
    r2 = evh("rescore", "--dataset-id", "tickets_v1", "--match", "own_v1")
    # where the tool designates a re-score (RFC-022): runs-rescored/<scorer>/<source>/
    resc = next((data / "runs-rescored").glob("*/runs/own*/metrics.json"), None) if r2.returncode == 0 else None
    mr = json.loads(resc.read_text()) if resc else {}
    check(
        "rescore keeps a project adapter's call-time extra, and reports nothing as dropped",
        r.returncode == 0
        and "my_extra" in (mr.get("scores") or {})
        and not mr.get("rescore_dropped_metrics"),
        (r.stdout + r.stderr + r2.stdout + r2.stderr)[-500:] + str(mr.get("rescore_dropped_metrics")),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
