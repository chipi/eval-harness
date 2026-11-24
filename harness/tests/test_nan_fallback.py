#!/usr/bin/env python3
"""A failed item counts 0 on a measure even when its fallback score is not a number either (RFC-041 F7; review,
2026-11-24).

    EVAL_STORE=files  python tests/test_nan_fallback.py
    EVAL_STORE=sqlite python tests/test_nan_fallback.py

An item whose score is NaN is a failed item, and `evh run` scores it as a failed item: `score_failure`, else `score("")`.
When that fallback is NaN too, the measure was dropped from the item's row, so the mean ran over the other items and
the failure made the arm look better. Here the first item's score and its fallback are NaN on `q`, the other five 0.5:
`q` is 0 on the failed item, and the run's mean is 0.5 * 5 / 6, not 0.5.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

ADAPTER = """
from types import SimpleNamespace
CALLS = [0]

def call_system(text, params):
    return SimpleNamespace(output="hello world", tokens_in=1, tokens_out=1, cost_usd=None, latency_ms=None, extra={},
                           meta={})

def score(output, reference):
    CALLS[0] += 1
    # the first item's score, and the failed item's fallback score("") for it, are both not a number
    return {"q": float("nan") if CALLS[0] <= 2 else 0.5, "ok": 1.0}

PRIMARY_METRIC = "ok"
"""

proj = Path(tempfile.mkdtemp(prefix="evh-nan-fallback-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tickets")
    (proj / "nan_adapter.py").write_text(ADAPTER, encoding="utf-8")
    r = _cli.run(proj, env, "dataset-create", "--dataset-id", "t_v1", "--source-dir", "tickets")
    r = r if r.returncode else _cli.run(proj, env, "dataset-materialize", "--dataset-id", "t_v1")
    check("setup: a frozen dataset", r.returncode == 0, r.stderr[-300:])
    _runstore.write_text(
        proj, "systems/nan_v1.yaml", "system_id: nan_v1\nadapter: nan_adapter.py\nparams:\n  provider: echo\n"
    )
    r = _cli.run(proj, env, "run", "--system", "nan_v1", "--dataset", "t_v1", "--run-id", "nanrun")
    rec = _runstore.record_of(proj, "nanrun")
    n = int(rec.get("n_items") or 0)
    failed = rec.get("failed_items") or []
    q = (rec.get("scores") or {}).get("q")
    check(
        "the item whose score and fallback are not numbers is one failed item, with its reason",
        r.returncode == 0 and len(failed) == 1 and "not a number" in str(failed[0].get("error")),
        (r.returncode, failed, r.stderr[-300:]),
    )
    check(
        "its q counts 0: the run's mean is over every item, 0.5 * 5 / 6, not the other items' 0.5",
        n == 6 and q is not None and abs(q - 0.5 * 5 / 6) < 1e-6,
        (n, q),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
