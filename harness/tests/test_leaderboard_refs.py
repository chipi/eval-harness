#!/usr/bin/env python3
"""The leaderboard keeps one table per reference: never averaged across silver and gold.

    python tests/test_leaderboard_refs.py

In a throwaway project built from the tutorial ($0, offline, the echo provider): an arm runs
before any reference, against a silver reference made from the author's run, and against gold.
The leaderboard printed them as one ranking (a silver 0.90 beside a gold 0.24, the table called
silver); each reference now has its own table, gold first, and a row never mixes them.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
KIT = HERE.parent / "tutorial"
from _check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-lbrefs-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-lbrefs")
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
    for arm in ("lead1", "author"):
        shutil.copy(KIT / "configs" / f"tickets_{arm}.yaml", data / "configs")
    for cfg in ("lead1", "author"):  # no reference yet
        r = evh(
            "experiment-run",
            "--config",
            f"data/configs/tickets_{cfg}.yaml",
            "--run-id",
            f"tickets_{cfg}_v1_none",
        )
        check(f"setup: {cfg} runs with no reference", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    author = next((data / "runs").glob("tickets_author_v1_*"))
    r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", author.name)
    check("setup: a silver reference from the author's run", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    time.sleep(1.1)  # created_at has whole seconds: each run is measured after the last
    r = evh(
        "experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--run-id", "tickets_lead1_v1_silver"
    )
    check("setup: lead1 runs against silver", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    time.sleep(1.1)
    r = evh(
        "experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--run-id", "tickets_lead1_v1_gold"
    )
    check("setup: lead1 runs against gold", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    r = evh("leaderboard", "--dataset-id", "tickets_v1")
    out = r.stdout
    heads = re.findall(r"^=== scored against (.+) ===$", out, re.M)
    check(
        "one table per reference, gold first",
        r.returncode == 0 and heads[:2] == ["gold/tickets_v1", "silver/tickets_v1"] and len(heads) == 3,
        out[-1500:] + r.stderr[-300:],
    )
    gold_part = out.split("=== scored against silver/tickets_v1 ===")[0]
    check(
        "the gold table holds only the gold-scored run (one run of lead1, not three averaged)",
        re.search(r"tickets_lead1_v1\s+1\s", gold_part) is not None and "tickets_author_v1" not in gold_part,
        gold_part[-800:],
    )
    check("it says the tables are never averaged across references", "never averaged across them" in out)

    # The catalog and the inspector read an arm against the reference of its latest run, and
    # say which runs they left out (they averaged all three before, labelled ×3).
    r = evh("inspect", "--runs", "tickets_lead1_v1,tickets_author_v1", "--metric", "output_words")
    check(
        "inspect: an arm is read against its latest run's reference; the runs left out are named",
        "2 earlier run(s) scored against no reference, silver/tickets_v1 left out" in r.stdout
        and "tickets_lead1_v1 ×" not in r.stdout,
        (r.stdout + r.stderr)[-800:],
    )

    # A round whose arms are scored against different references is read against one of them;
    # the others are named, never silently dropped or compared across references.
    (data / "goals").mkdir(exist_ok=True)
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--hypothesis", "mixed references", "--keep", "tickets_lead1_v1,tickets_author_v1",
    )  # fmt: skip
    rs = evh("rounds", "--goal", "tickets_summary")
    check(
        "rounds: read against one reference; an arm scored against another is named",
        r.returncode == 0
        and "read against gold/tickets_v1; not compared: tickets_author_v1 (scored against no reference)"
        in rs.stdout,
        (r.stdout + r.stderr)[-300:] + rs.stdout[-800:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# A judged run is scored by its judge, not by its source run's reference: one group per judge.
import leaderboard as lb  # noqa: E402

judged_on_silver = {
    "derived": {"kind": "judge", "with": {"scorer_id": "j1"}},
    "fingerprint": {"data": {"reference_id": "silver/x"}},
}
judged_on_none = {"derived": {"kind": "judge", "with": {"scorer_id": "j1"}}, "fingerprint": {"data": {}}}
check(
    "a judged run is grouped by its judge, whatever its source run was scored against",
    lb._reference_of(judged_on_silver) == lb._reference_of(judged_on_none) == "judge j1",
)
check("a judged table is headed as scored by the judge", lb._heading("judge j1") == "scored by judge j1")
check("runs with no reference are not called a reference", lb._heading(None) == "scored against no reference")

# The judging pass's summary can hold checks that did not run (None): printed as —, never a crash.
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    run = Path(td) / "arm_a_1"
    run.mkdir()
    (Path(td) / "summary.json").write_text(
        json.dumps(
            {
                "items_scored": 3,
                "items_total": 3,
                "label": "unvalidated judge",
                "judge_agreement": {"a~b": {"mean_item_tau": None, "arm_mean_spearman": None}},
                "controls": {"a": {"position": {"mean_tau": None}, "noise": {}}},
            }
        )
    )
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            lb._judging_summary([(run, {})])
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok, buf = False, io.StringIO(repr(exc))
    check(
        "the judging-pass block prints a check that did not run as —, and does not crash",
        ok and "item tau —" in buf.getvalue() and "(position)" in buf.getvalue(),
        buf.getvalue()[-300:],
    )

sys.exit(summary())
