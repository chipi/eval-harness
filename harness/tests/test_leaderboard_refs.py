#!/usr/bin/env python3
"""The leaderboard keeps one table per reference: never averaged across silver and gold.

    python tests/test_leaderboard_refs.py

In a throwaway project built from the tutorial ($0, offline, the echo provider): an arm runs
before any reference, against a silver reference made from the author's run, and against gold.
The leaderboard printed them as one ranking (a silver 0.90 beside a gold 0.24, the table called
silver); each reference now has its own table, gold first, and a row never mixes them. The tables are the goal
view's (model/goal_views): an arm is in the one table of the reference its latest run was scored against, as the
catalog and the inspector read it.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format, _store  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-lbrefs-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-lbrefs")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
    for arm in ("lead1", "author"):
        _runstore.write_bytes(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_bytes()
        )
    for cfg in ("lead1", "author"):  # no reference yet
        r = evh(
            "run",
            "--system",
            f"tickets_{cfg}_v1",
            "--dataset",
            "tickets_v1",
            "--run-id",
            f"tickets_{cfg}_v1_none",
        )
        check(f"setup: {cfg} runs with no reference", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    author = next(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_author_v1_"))
    r = evh("label-from-run", "--run", author, "--set", "author_labels")
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "author_labels",
            "--tier",
            "silver",
            "--reason",
            "The author's outputs rank the others.",
            "--by",
            "test",
        )
    )
    check("setup: a silver reference from the author's run", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    time.sleep(1.1)  # created_at has whole seconds: each run is measured after the last
    r = evh(
        "run",
        "--system",
        "tickets_lead1_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "tickets_lead1_v1_silver",
    )
    check("setup: lead1 runs against silver", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    time.sleep(1.1)
    r = evh(
        "run",
        "--system",
        "tickets_author_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "tickets_author_v1_silver",
    )
    check("setup: the author runs against its own silver", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    r = evh(
        "label-import",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v1",
        "--set",
        "owner_gold",
        "--by",
        "owner",
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "owner_gold",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        )
    )
    check("setup: the kit's gold, imported and promoted", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    time.sleep(1.1)
    r = evh(
        "run", "--system", "tickets_lead1_v1", "--dataset", "tickets_v1", "--run-id", "tickets_lead1_v1_gold"
    )
    check("setup: lead1 runs against gold", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    r = evh("leaderboard", "--dataset-id", "tickets_v1")
    out = r.stdout
    heads = re.findall(r"^=== scored against (.+) ===$", out, re.M)
    check(
        "one table per reference, gold first",
        r.returncode == 0 and heads == ["gold/tickets_v1", "silver/tickets_v1"],
        out[-1500:] + r.stderr[-300:],
    )
    gold_part, silver_part = out.split("=== scored against silver/tickets_v1 ===")

    def rows(part):  # the table's rows (a warning above it names every run of the dataset)
        return [ln.split()[0] for ln in part.splitlines() if re.match(r"^  tickets_\S+( \*)?\s+\d+\s", ln)]

    check(
        "the gold table holds only the gold-scored run (one run of lead1, not three averaged)",
        rows(gold_part) == ["tickets_lead1_v1"]
        and re.search(r"tickets_lead1_v1\s+1\s", gold_part) is not None,
        gold_part[-800:],
    )
    check(
        "an arm is in the one table of its latest run's reference: lead1 is not also in silver's",
        rows(silver_part) == ["tickets_author_v1"],
        silver_part[-800:],
    )
    check(
        "the arm that wrote the silver reference is marked, and says why",
        "* tickets_author_v1 wrote the reference silver/tickets_v1" in silver_part,
        silver_part[-800:],
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
    _runstore.write_bytes(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_bytes()
    )
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--hypothesis", "mixed references", "--keep", "tickets_lead1_v1,tickets_author_v1",
    )  # fmt: skip
    rs = evh("rounds", "--goal", "tickets_summary")
    check(
        "rounds: read against one reference; an arm scored against another is named",
        r.returncode == 0
        and "read against gold/tickets_v1; not compared: tickets_author_v1 (scored against silver/tickets_v1)"
        in rs.stdout,
        (r.stdout + r.stderr)[-300:] + rs.stdout[-800:],
    )

    # With the goal that names the dataset the tables are the goal's: its decision under each, its flags in the data.
    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--json")
    doc = json.loads(r.stdout) if r.returncode == 0 else {}
    vals = (doc.get("result") or {}).get("values") or {}
    gold_g: dict = next((g for g in vals.get("groups", []) if g["reference"] == "gold/tickets_v1"), {})
    check(
        "leaderboard: the goal that names the dataset reads it; its decision is in the data, an arm's flags in its row",
        vals.get("goal") == "tickets_summary"
        and (gold_g.get("decision") or {}).get("goal") == "tickets_summary"
        and gold_g["decision"]["leader"] == "runs/tickets_v1/tickets_lead1_v1"
        and gold_g["arms"][0]["arm"] == "runs/tickets_v1/tickets_lead1_v1"
        and gold_g["arms"][0]["flags"] == [],
        r.stdout[-700:] + r.stderr[-300:],
    )
    r = evh("leaderboard", "--dataset-id", "tickets_v1")
    check(
        "leaderboard: under a table, what the goal makes of it",
        "goal tickets_summary: leader tickets_lead1_v1" in r.stdout,
        r.stdout[-600:],
    )
    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--goal", "no_such_goal")
    check(
        "leaderboard --goal: a goal that does not exist is refused, naming those there are",
        r.returncode != 0 and "no goal 'no_such_goal': one of tickets_summary" in r.stderr,
        r.stdout[-300:] + r.stderr[-300:],
    )
    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--label", "silver")
    check(
        "leaderboard --label: only the arms read under it; none is refused with the label named",
        r.returncode != 0 and "read as 'silver'" in r.stderr,
        r.stdout[-300:] + r.stderr[-300:],
    )
    r = evh("goal-leaderboard", "tickets_summary", "--json")
    ops = json.loads(r.stdout)["result"] if r.returncode == 0 else {}
    first = ((ops.get("datasets") or [{}])[0].get("groups") or [{}])[0]
    check(
        "goal-leaderboard: the goal's tables through the operation, the same leader as `evh leaderboard`",
        first.get("scored_against") == "gold/tickets_v1"
        and first.get("leader") == "runs/tickets_v1/tickets_lead1_v1",
        r.stdout[-500:] + r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# A judged run is scored by its judge, not by its source run's reference: one group per judge.
from evaluation_harness import leaderboard as lb  # noqa: E402
from evaluation_harness.model import goal_views as gv  # noqa: E402

judged_on_silver = {"judge": "j1", "reference": "silver/x"}
judged_on_none = {"judge": "j1", "reference": ""}
check(
    "a judged arm is grouped by its judge, whatever its source run was scored against",
    gv._group_key(judged_on_silver) == gv._group_key(judged_on_none) == "judge j1",
)
check("an arm with no reference is in the group of none", gv._group_key({"reference": ""}) == "no reference")
check("a judged table is headed as scored by the judge", lb._heading("judge j1") == "scored by judge j1")
check("runs with no reference are not called a reference", lb._heading(None) == "scored against no reference")

# The judging pass's summary can hold checks that did not run (None): printed as —, never a crash.
import contextlib  # noqa: E402
import io  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    key = "judge-summ-v1@set_a"
    run = Path(td) / "runs" / "arm_a_1" / "scores" / key
    summary_doc = {
        "items_scored": 3,
        "items_total": 3,
        "label": "unvalidated judge",
        "judge_agreement": {"a~b": {"mean_item_tau": None, "arm_mean_spearman": None}},
        "controls": {"a": {"position": {"mean_tau": None}, "noise": {}}},
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), _runstore._InProject(td) as data:
            # in the suite's store: the summary is the project's data (its database in the sqlite store)
            _store.write_text(data / "judge-summaries" / f"{key}.json", json.dumps(summary_doc))
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
