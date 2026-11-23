#!/usr/bin/env python3
"""A leaderboard ranked on a descriptive metric says the metric is neutral, as every other reader does (RFC-041 F1).

  EVAL_STORE=files python tests/test_leaderboard_neutral.py        (and EVAL_STORE=sqlite)

No run declares a primary metric and no goal names the dataset, so `evh leaderboard` ranks by the first metric in sort
order, `output_words`, a count the adapter declares descriptive. Its heading said `(higher is better)` while the
inspector, metric-list and the arm page call it neutral. The heading and the JSON now use the one direction word; the
`RANKED ON A DESCRIPTIVE METRIC` warning stays; a `--asc` or `--desc` the caller passes still decides the order.
"""

import json
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

proj = Path(tempfile.mkdtemp(prefix="evh-lb-neutral-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-lb-neutral", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from evaluation_harness.adapter import Result

METRIC_KINDS = {"output_words": "descriptive"}

def call_system(text, params):
    words = text.split()[: params["words"]]
    return Result(output=" ".join(words), tokens_in=len(text.split()), tokens_out=len(words), cost_usd=0.0)

def score(output, reference):
    return {"output_words": float(len(output.split()))}
"""


def evh(*args):
    return _cli.run(proj, env, *args)


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapters").mkdir()
    (proj / "adapters" / "count.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    for name, words in (("w4", 4), ("w9", 9)):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: adapters/count.py\nparams:\n  words: {words}\n",
        )
        r = r if r.returncode else evh("run", "--system", f"{name}_v1", "--dataset", "tickets_v1")
    check(
        "setup: two arms of an adapter whose only metric is descriptive, no goal",
        r.returncode == 0,
        r.stderr[-300:],
    )

    lb = evh("leaderboard", "tickets_v1")
    head = next((ln for ln in lb.stdout.splitlines() if ln.startswith("dataset:")), lb.stderr[-300:])
    check(
        "the heading calls a descriptive metric neutral, not higher is better",
        "ranked by: output_words (neutral" in head and "higher is better" not in head,
        head,
    )
    check(
        "the warning that it is a descriptive metric stays",
        "RANKED ON A DESCRIPTIVE METRIC (output_words)" in lb.stdout,
        lb.stdout[-400:],
    )
    group = (
        json.loads(evh("leaderboard", "tickets_v1", "--json").stdout)["result"]["values"]["groups"] or [{}]
    )[0]
    check(
        "--json: direction neutral, as metric-list says",
        group.get("direction") == "neutral" and group.get("ranked_on_descriptive") is True,
        {k: group.get(k) for k in ("direction", "ranked_on_descriptive")},
    )
    listed = {
        m["metric"]: m["better"] for m in json.loads(evh("metric-list", "--json").stdout)["result"]["metrics"]
    }
    check("metric-list says the same word", listed.get("output_words") == "neutral", listed)
    asc = evh("leaderboard", "tickets_v1", "--asc")
    check(
        "--asc still decides: lower is better, the arm with fewer words first",
        "ranked by: output_words (lower is better)" in asc.stdout
        and asc.stdout.index("w4_v1") < asc.stdout.index("w9_v1"),
        asc.stdout[:300],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
