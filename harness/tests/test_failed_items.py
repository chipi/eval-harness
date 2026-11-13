#!/usr/bin/env python3
"""A failed item is scored and the run goes on (PLAN_0.8.0 A5, owner 2026-11-05).

    python tests/test_failed_items.py

In a throwaway project with the tutorial's six tickets: an adapter that fails on one ticket finishes the run, scores
that ticket as an empty answer (0), marks its row `failed`, lists it in metrics.json and writes no output for it (so
--resume calls it again); one that fails on every ticket stops with ERROR (failed); a provider error that stays
transient past its retries stops the run with exit 75, as an unreachable server does.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-failed-"))
env = dict(
    os.environ,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-failed-items",
    EVAL_MAX_RETRIES="2",
    EVAL_RETRY_MAX_DELAY="0",
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


ADAPTER = """from evaluation_harness.adapter import Result, score  # noqa: F401


def call_system(text, params):
    mode = params.get("mode")
    if mode == "one" and "invoice" in text.lower():
        raise ValueError("400: this input is refused by the provider")
    if mode == "all":
        raise ValueError("400: every input refused")
    if mode == "weather":
        raise RuntimeError("429 Too Many Requests")
    return Result(output=text[:80], cost_usd=0.0)
"""

try:
    data = proj / "data"
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (data / "systems").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "owner"
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "g",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        )
    )
    check("setup: the tutorial dataset and its gold", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    (proj / "flaky.py").write_text(ADAPTER)
    for mode in ("one", "all", "weather"):
        _runstore.write_text(
            proj,
            f"systems/{mode}_v1.yaml",
            f"system_id: {mode}_v1\nadapter: flaky.py\nparams: {{mode: {mode}}}\n",
        )

    r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1")
    name = next((n for n in _runstore.listdir(proj, "runs") if n.startswith("one_v1_")), None)
    m = _runstore.read_json(proj, f"runs/{name}/metrics.json") if name else {}
    with _runstore._InProject(proj) as pdata:
        run = pdata / "runs" / name if name else None
        rows = _runstore.rows(run) if run else []
        out_bad = _outputs.output(run, "t02_invoice") if run else None
        out_ok = _outputs.output(run, "t01_login") if run else None
    bad: dict = next((x for x in rows if x["failed"] == 1.0), {})
    check(
        "one ticket fails: the run finishes (exit 0) and lists it, with its error",
        r.returncode == 0
        and len(m.get("failed_items") or []) == 1
        and "refused" in m["failed_items"][0]["error"],
        (r.stdout + r.stderr)[-400:],
    )
    check(
        "... its row is marked failed and scored as an empty answer (0); the others are not",
        bad.get("item_id") == "t02_invoice"
        and bad.get("overlap_f1") == 0.0
        and sum(x["failed"] for x in rows) == 1.0,
        rows,
    )
    check(
        "... and no output is written for it, so --resume calls it again",
        run is not None and out_bad is None and out_ok is not None,
    )

    r = evh("run", "--system", "all_v1", "--dataset", "tickets_v1")
    check(
        "every ticket fails: more than 5 and over 20% is the adapter, and the run stops (ERROR (failed))",
        r.returncode != 0 and "ERROR (failed)" in r.stderr and "not the items" in r.stderr,
        (r.stdout + r.stderr)[-400:],
    )
    r = evh("run", "--system", "weather_v1", "--dataset", "tickets_v1")
    check(
        "a transient error past its retries is weather: the run stops with 75, to resume later",
        r.returncode == 75 and "kept failing after its retries" in (r.stdout + r.stderr),
        (r.stdout + r.stderr)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
