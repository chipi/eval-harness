#!/usr/bin/env python3
"""What experiment-run reports about a pass, with a project's own adapter.

    python tests/test_run_reports.py

In a throwaway project ($0, offline), with an adapter written the way INTEGRATION shows (it
returns output and tokens, nothing else): the core records each call's latency; outputs that
stop at max_tokens are named in a warning; a pass that crashes says which run stopped, after how
many items, and how to resume or delete it, and the resume finishes the run.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-reports-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-reports", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
import os, time
from types import SimpleNamespace

def call_system(text, params):
    if params.get("fail_on") and params["fail_on"] in text and not os.path.exists(params["flag"]):
        raise RuntimeError("the provider is down")
    if params.get("refuse_on") and params["refuse_on"] in text and not os.path.exists(params["flag"]):
        # an adapter that turns failed calls into an answer, as the triage fleet's replay does
        refused = {"error": "URLError: <urlopen error [Errno 111] Connection refused>"}
        return SimpleNamespace(output="no decision", tokens_in=0, tokens_out=0, cost_usd=None,
                               latency_ms=None, extra={}, meta={"calls": [refused, refused]})
    if params.get("model_error"):
        failed = {"error": "RuntimeError: prediction aborted, token repeat limit reached"}
        return SimpleNamespace(output="no decision", tokens_in=0, tokens_out=0, cost_usd=None,
                               latency_ms=None, extra={}, meta={"calls": [failed, failed]})
    time.sleep(0.01)
    words = text.split()[: int(params.get("max_tokens", 1000))]
    return SimpleNamespace(output=" ".join(words), tokens_in=len(text.split()), tokens_out=len(words),
                           cost_usd=None, latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split()))}
"""


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def config(name, **params):
    p = proj / "data" / "configs" / f"{name}.yaml"
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    p.write_text(f"config_id: {name}_v1\ndataset_id: tickets_v1\nadapter: adapter.py\nparams:\n{body}")
    return f"data/configs/{name}.yaml"


try:
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])

    r = evh("experiment-run", "--config", config("plain"))
    run = next((proj / "data" / "runs").glob("plain_v1_*"), None)
    rows = [json.loads(x) for x in (run / "predictions.jsonl").read_text().splitlines()] if run else []
    rows_plain = rows
    check(
        "the core times every call: latency_ms on each row, from an adapter that reports none",
        r.returncode == 0 and rows and all(row.get("latency_ms", 0) > 0 for row in rows),
        (r.stderr[-300:], rows[:1]),
    )

    r = evh("experiment-run", "--config", config("capped", max_tokens=12))
    check(
        "outputs that stop at max_tokens are named in a warning",
        r.returncode == 0 and "stopped at max_tokens=12" in r.stdout,
        r.stdout[-400:],
    )

    flag = proj / "provider-back"
    r = evh("experiment-run", "--config", config("flaky", fail_on="export", flag=str(flag)))
    stopped = next((proj / "data" / "runs").glob("flaky_v1_*"), None)
    out = r.stdout + r.stderr
    check(
        "a crashed pass names the run, how far it got, and how to resume or delete it",
        r.returncode != 0
        and stopped is not None
        and f"STOPPED: run {stopped.name} stopped after" in out
        and f"--resume {stopped.name}" in out
        and "or delete" in out,
        out[-600:],
    )
    flag.write_text("1")
    r = evh(
        "experiment-run", "--config", "data/configs/flaky.yaml", "--resume", stopped.name if stopped else ""
    )
    check("resuming it finishes the run", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    back = proj / "server-back"
    r = evh("experiment-run", "--config", config("refused", refuse_on="export", flag=str(back)))
    gone = next((proj / "data" / "runs").glob("refused_v1_*"), None)
    out = r.stdout + r.stderr
    check(
        "an item whose every model call was refused stops the run, unwritten, not scored as an answer",
        r.returncode != 0
        and gone is not None
        and "STOPPED" in out
        and "every model call failed" in out
        and "Connection refused" in out
        and "Traceback" not in out
        and not (gone / "metrics.json").exists()
        and "no decision" not in "".join(p.read_text() for p in (gone / "outputs").glob("*.txt")),
        out[-600:],
    )
    back.write_text("1")
    r = evh("experiment-run", "--config", "data/configs/refused.yaml", "--resume", gone.name if gone else "")
    rows = [json.loads(x) for x in (gone / "predictions.jsonl").read_text().splitlines()] if gone else []
    answers = list((gone / "outputs").glob("*.txt")) if gone else []
    check(
        "resumed with the server back, the refused item is called again and every item is an answer",
        r.returncode == 0
        and len(rows) == len(rows_plain)
        and all(p.read_text() != "no decision" for p in answers)
        and len(answers) == len(rows_plain),
        ((r.stdout + r.stderr)[-300:], len(rows), len(rows_plain)),
    )
    r = evh("experiment-run", "--config", config("broken", model_error=True))
    run = next((proj / "data" / "runs").glob("broken_v1_*"), None)
    check(
        "a model's own failed calls (not an unreachable server) are a measurement: the run completes",
        r.returncode == 0 and run is not None and (run / "metrics.json").exists(),
        (r.stdout + r.stderr)[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
