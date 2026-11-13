#!/usr/bin/env python3
"""Scoring that evolves (RFC-022): a round recorded from runs made before it (--adopt), a scoring change previewed
without writing anything, applied to a round (rescore --round) as a score under each run, adopted from
the next round (round-open --scoring, the carried arms re-scored), read by the goal and the round alike, and a
round whose arms one adapter scored in two versions noted by validate.

    python tests/test_scoring_evolves.py

In a throwaway project from the tutorial ($0, offline, the echo provider), with a project adapter that wraps the
bundled one and adds BONUS to overlap_f1: editing BONUS is a scoring change, with a new code hash.
"""

import os
import re
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

proj = Path(tempfile.mkdtemp(prefix="evh-scoring-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-scoring")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)
ADAPTER = '''"""The bundled adapter, with BONUS added to overlap_f1: editing BONUS changes the scoring."""
from evaluation_harness.adapter import *  # noqa: F401,F403
from evaluation_harness.adapter import score as _score

BONUS = {bonus}


def score(output, reference):
    row = _score(output, reference)
    if "overlap_f1" in row:
        row["overlap_f1"] = row["overlap_f1"] + BONUS
    if BONUS:
        row["bonus_seen"] = BONUS  # a measure only the re-score has, as triage_cost was on production's run
    return row
'''


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def set_bonus(b: float) -> None:
    (proj / "bonus_adapter.py").write_text(ADAPTER.format(bonus=b))


def files_under() -> set[str]:
    return set(_runstore.files_under(proj))


def rescored_scores() -> list:
    """[(run id, label, record)] of every score read as "rescored <scorer>" under the project's runs."""
    return [
        (rid, lb, rec)
        for rid in _runstore.listdir(proj, "runs")
        for _k, lb, rec in _runview.scores_of(proj, rid)
        if lb.startswith("rescored ")
    ]


# A module edited within the second to a value of the same length is loaded as edited: a stale .pyc (trusted while
# the source's mtime in whole seconds and its size match) once ran the old scorer under the new one's hash.
from evaluation_harness._common import load_module  # noqa: E402

mod_dir = Path(tempfile.mkdtemp(prefix="evh-pyc-"))
f = mod_dir / "scorer_mod.py"
f.write_text("BONUS = 0.0\n")
first = load_module(f, "evh_test_pyc_a").BONUS
f.write_text("BONUS = 0.5\n")
second = load_module(f, "evh_test_pyc_b").BONUS
shutil.rmtree(mod_dir, ignore_errors=True)
check("load_module: an edit within the same second, same length, is what runs", (first, second) == (0.0, 0.5))

try:
    data = proj / "data"
    if not _runstore.sqlite():
        (data / "systems").mkdir(parents=True)
        (data / "goals").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
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
    set_bonus(0.0)
    for arm in ("lead1", "lead2"):
        cfg = (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", cfg + "adapter: ../../bonus_adapter.py\n"
        )
        r = evh(
            "run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1", "--goal", "tickets_summary"
        )
    check("setup: two arms run through the project adapter", r.returncode == 0, out(r)[-400:])

    # r1 from the runs made before any round was opened
    r = evh(
        "round-open",
        "--goal",
        "tickets_summary",
        "--dataset",
        "tickets_v1",
        "--adopt",
        "--hypothesis",
        "lead sentences",
    )
    r1 = _runstore.read_text(proj, "rounds/tickets_summary/r1.yaml") if r.returncode == 0 else ""
    check(
        "round-open --adopt: r1 carries the arms already run for the goal",
        "tickets_lead1_v1" in r1 and "tickets_lead2_v1" in r1,
        out(r),
    )
    r = evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--adopt")
    check(
        "round-open --adopt: refused once the goal has a round",
        r.returncode != 0 and "has rounds" in out(r),
        out(r),
    )

    # preview a scoring change: nothing written
    set_bonus(0.5)
    before = files_under()
    r = evh("score-preview", "--goal", "tickets_summary")
    check(
        "score-preview: each arm before and after the change, and the decision",
        r.returncode == 0
        and "+0.5000" in r.stdout
        and "leader" in r.stdout
        and "nothing written" in r.stdout,
        out(r)[-900:],
    )
    check("score-preview: writes nothing to the project", files_under() == before)

    # apply it to r1: a score under each run, the round's record
    r = evh(
        "rescore", "--goal", "tickets_summary", "--round", "r1", "--why", "a bonus to see the scoring move"
    )
    placed = rescored_scores()
    r1 = _runstore.read_text(proj, "rounds/tickets_summary/r1.yaml")
    check(
        "rescore --round: writes a score under each run, read as rescored <scorer>, one re-score per run",
        r.returncode == 0 and len(placed) == 2,
        out(r)[-600:],
    )
    check(
        "rescore --round: the round records the scorer and why",
        "scoring:" in r1 and "a bonus to see the scoring move" in r1,
        r1,
    )
    import yaml

    arms1 = yaml.safe_load(r1)["arms"]
    check(
        "rescore --round: each arm is read under the label its runs were re-scored as, through those runs",
        len(arms1) == 2
        and all(a["label"].startswith("rescored ") and len(a["runs"]) == 1 for a in arms1)
        and len({a["label"] for a in arms1}) == 1,
        arms1,
    )
    g = evh("goals", "--goal", "tickets_summary")
    check(
        "the goal reads the re-score: one row per arm, from its re-score",
        g.stdout.count("rescored") >= 2,
        g.stdout[-900:],
    )
    rs = evh("rounds", "--goal", "tickets_summary", "--round", "r1")
    check(
        "the round reads the re-score as the goal does",
        "read from their re-score by" in rs.stdout,
        rs.stdout[-900:],
    )
    cat = evh("catalog", "--out", str(proj / "cat"))
    page = (
        (proj / "cat" / "g" / "tickets_summary.html").read_text(encoding="utf-8")
        if cat.returncode == 0
        else ""
    )
    m = re.search(r'<span data-v="(\d+)">\d+ arms</span>', page)
    check(
        "the catalog counts a re-scored round's arms once each, as evh rounds does (a re-score is the same arm)",
        m is not None and m.group(1) == "2",
        (m.group(0) if m else out(cat)[-300:]),
    )
    pt = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--round",
        "r1",
        "--goal",
        "tickets_summary",
        "--a",
        "tickets_lead1_v1",
        "--b",
        "tickets_lead2_v1",
        "--metric",
        "bonus_seen",
    )
    check(
        "pair-test --round reads each arm as the round does: a measure only its re-score has is tested",
        pt.returncode == 0 and "N=" in pt.stdout and "shared item" not in out(pt),
        out(pt)[-600:],
    )

    # a round with more arms than the inspector compares in one request still has its rows (they were empty, unsaid)
    probe = proj / "probe_rows.py"
    probe.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(HERE.parent)!r})\n"
        "from evaluation_harness import _rounds, rounds, catalog_serve\n"
        "catalog_serve.LIMITS['max_arms'] = 1\n"
        "ev = rounds.evidence('tickets_summary', _rounds.find('tickets_summary', 'r1'))\n"
        "print('ROWS', len(ev['rows']), 'NOTES', ev['notes'])\n"
    )
    pr = subprocess.run([sys.executable, str(probe)], cwd=proj, env=env, capture_output=True, text=True)
    check(
        "round evidence: more arms than one inspector request takes are still compared, by the same paired test",
        "ROWS 1" in pr.stdout and "no comparison" not in pr.stdout,
        out(pr)[-600:],
    )

    # adopt the next change from r2: the carried arms re-scored before it opens
    evh(
        "round-close",
        "--goal",
        "tickets_summary",
        "--round",
        "r1",
        "--conclusion",
        "the bonus moved every arm alike",
    )
    set_bonus(1.0)
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--from", "r1", "--keep", "all",
        "--scoring", "a larger bonus, adopted from this round",
    )  # fmt: skip
    r2 = _runstore.read_text(proj, "rounds/tickets_summary/r2.yaml") if r.returncode == 0 else ""
    scorers = {lb for _rid, lb, _rec in rescored_scores()}
    check(
        "round-open --scoring: the carried arms re-scored by this tree's scorer, before and after printed",
        r.returncode == 0
        and "2 of 2 carried run(s) re-scored" in r.stdout
        and "->" in r.stdout
        and len(scorers) == 2,
        out(r)[-800:],
    )
    check(
        "round-open --scoring: the round records its scorer and the change",
        "scorer:" in r2 and "scoring: a larger bonus" in r2 and "tickets_lead1_v1" in r2,
        r2,
    )
    arms2 = yaml.safe_load(r2)["arms"] if r2 else []
    check(
        "round-open --scoring: the carried arms are read under the new scorer's label, carried from r1",
        len(arms2) == 2
        and all(a["entered"]["how"] == "carried" and a["entered"]["from"] == "r1" for a in arms2)
        and all(a["label"].startswith("rescored ") and a["label"] != arms1[0]["label"] for a in arms2),
        arms2,
    )
    rs2 = evh("rounds", "--goal", "tickets_summary", "--round", "r2")
    check(
        "evh rounds: the scorer a round is judged by, and its scoring change, as the goal page lists them",
        "judged by:" in rs2.stdout and "scoring " in rs2.stdout and "a larger bonus" in rs2.stdout,
        rs2.stdout[-900:],
    )
    r = evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--keep", "all")
    check(
        "round-open --keep all: refused without --from",
        r.returncode != 0 and "needs --from" in out(r),
        out(r),
    )

    # one adapter in two versions inside a round: validate notes it
    for arm, bonus in (("author", 1.0), ("author2", 2.0)):
        set_bonus(bonus)
        cfg = (
            (KIT / "systems" / "tickets_lead2_v1.yaml")
            .read_text()
            .replace("tickets_lead2_v1", f"tickets_{arm}_v1")
        )
        _runstore.write_text(
            proj,
            f"systems/tickets_{arm}_v1.yaml",
            cfg + "adapter: ../../bonus_adapter.py\n",
        )
        evh(
            "run",
            "--system",
            f"tickets_{arm}_v1",
            "--dataset",
            "tickets_v1",
            "--goal",
            "tickets_summary",
            "--round",
            "r2",
        )
    v = evh("validate")
    check(
        "validate: a round whose arms one adapter scored in two versions is noted, with what to run",
        "versions of that adapter" in v.stdout
        and "evh score-preview --goal tickets_summary --round r2" in v.stdout,
        v.stdout[-1200:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
