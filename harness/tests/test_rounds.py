#!/usr/bin/env python3
"""Experiment rounds (ADR-0004): open, run, the evidence and its suggestions, retire, close, the next.

    python tests/test_rounds.py

In a throwaway project built from the tutorial ($0, offline, the echo provider): a round of a goal
is opened carrying two arms in, a third runs naming it; `evh rounds` suggests retiring the arm the
test separates as worse, with the command; the retirement and the close (promoting the leader) are
recorded; a closed round refuses new runs; the next round continues it; validate checks the
records; the leaderboard scopes to a round; the goal page shows the rounds. Rounds are optional:
a project without them is unchanged (every other test).
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

proj = Path(tempfile.mkdtemp(prefix="evh-rounds-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-rounds")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    for arm in ("lead1", "lead2"):
        shutil.copy(KIT / "configs" / f"tickets_{arm}.yaml", data / "configs")
        evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")

    r = evh("rounds", "--goal", "tickets_summary")
    check(
        "rounds are optional: a goal without any says so, and how to start",
        "has no rounds" in r.stdout,
        out(r),
    )

    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--hypothesis", "how many leading sentences summarise a ticket best",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1",
    )  # fmt: skip
    doc = (data / "rounds" / "tickets_summary" / "r1.yaml").read_text() if r.returncode == 0 else ""
    check(
        "round-open: writes r1, open, with the arms carried in",
        "status: open" in doc and "tickets_lead1_v1" in doc,
        out(r),
    )

    cfg = (KIT / "configs" / "tickets_author.yaml").read_text()
    (data / "configs" / "author.yaml").write_text(cfg + "goal: tickets_summary\nround: r1\n")
    r = evh("experiment-run", "--config", "data/configs/author.yaml")
    run = next((data / "runs").glob("tickets_author_v1_*"), None)
    check(
        "a config naming the round runs in it, and the run records the round",
        r.returncode == 0
        and run is not None
        and json.loads((run / "metrics.json").read_text()).get("round") == "r1",
        out(r)[-300:],
    )

    r = evh("rounds", "--goal", "tickets_summary")
    # On gold over six tickets lead2 leads and no arm separates: the evidence says tie, more items.
    check(
        "rounds: the evidence and its suggestions, each as the command that does it",
        "leader tickets_lead2_v1" in r.stdout
        and "tie with the leader" in r.stdout
        and "evh rank-stability --dataset-id tickets_v1" in r.stdout
        and "evh round-close --goal tickets_summary --round r1" in r.stdout,
        r.stdout[-900:],
    )
    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--round", "r1")
    check(
        "leaderboard --round: the round's arms",
        r.returncode == 0 and "tickets_author_v1" in r.stdout,
        out(r)[-300:],
    )
    r = evh("inspect", "--round", "r1", "--goal", "tickets_summary")
    check(
        "evh inspect --round: the round's arms, tested against one of them",
        r.returncode == 0 and "run vs baseline" in r.stdout and "tickets_author_v1" in r.stdout,
        out(r)[-300:],
    )
    check(
        "evh inspect --round: on the goal's measure, against the round's leader (as evh rounds reads it)",
        "overlap_f1 (higher is better) · baseline tickets_lead2_v1" in r.stdout,
        out(r)[-400:],
    )

    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--round",
        "r1",
        "--goal",
        "tickets_summary",
        "--b",
        "tickets_lead1_v1",
    )
    check(
        "pair-test --round: the round's leader by default, on the goal's measure",
        r.returncode == 0
        and "tickets_lead2_v1 (its leader) against tickets_lead1_v1" in r.stdout
        and "metric=overlap_f1" in r.stdout,
        out(r)[-400:],
    )
    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--round",
        "r1",
        "--goal",
        "tickets_summary",
        "--a",
        "tickets_nope_v1",
    )
    check(
        "pair-test --round: an arm not in play is refused",
        r.returncode != 0 and "not in play" in out(r),
        out(r)[-300:],
    )
    # CLI parity: the inspector's per-item table and analysis charts, and the catalog's search.
    r = evh("inspect", "--round", "r1", "--goal", "tickets_summary", "--items", "--analysis")
    check(
        "evh inspect --items: every item's score per arm, and each arm's Δ against the baseline",
        r.returncode == 0
        and "(overlap_f1; Δ is each arm minus the baseline)" in r.stdout
        and "Δ tickets_" in r.stdout,
        out(r)[-500:],
    )
    check(
        "evh inspect --analysis: the charts' numbers (spread per run, difference from the baseline)",
        "spread per run (overlap_f1" in r.stdout and "difference from the baseline" in r.stdout,
        out(r)[-500:],
    )
    r = evh("search", "lead2")
    check(
        "evh search: the catalog's search, each hit with the command that shows it",
        r.returncode == 0 and "evh inspect --runs runs/tickets_v1/tickets_lead2_v1" in r.stdout,
        out(r)[-500:],
    )
    # The author arm's outputs become a silver reference: the round's leader is then read against
    # the arm that wrote it, and that arm is never suggested for retirement (it is the yardstick).
    r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", run.name if run else "")
    rs = evh("rounds", "--goal", "tickets_summary")
    check(
        "rounds: the leader against the arm that wrote a silver reference",
        r.returncode == 0 and "against the arm that wrote silver/tickets_v1 (tickets_author_v1)" in rs.stdout,
        out(r)[-300:] + rs.stdout[-600:],
    )
    check(
        "rounds: the silver author is not suggested for retirement",
        "retire tickets_author_v1" not in rs.stdout,
        rs.stdout[-600:],
    )
    r = evh(
        "round-retire",
        "--goal",
        "tickets_summary",
        "--round",
        "r1",
        "--arm",
        "tickets_lead1_v1",
        "--reason",
        "one sentence drops what the ticket asks",
    )
    check(
        "round-retire: recorded with its reason",
        r.returncode == 0 and "one sentence drops" in (data / "rounds/tickets_summary/r1.yaml").read_text(),
        out(r),
    )
    r = evh("leaderboard", "--dataset-id", "tickets_v1", "--round", "r1")
    check(
        "leaderboard --round: a retired arm is out of it", "tickets_lead1_v1" not in r.stdout, r.stdout[-400:]
    )

    r = evh("round-close", "--goal", "tickets_summary", "--round", "r1", "--conclusion", "too short")
    check(
        "round-close: a conclusion must be a sentence",
        r.returncode != 0 and "must be a sentence" in out(r),
        out(r),
    )
    r = evh(
        "round-close", "--goal", "tickets_summary", "--round", "r1",
        "--conclusion", "three sentences lead on the tutorial's six tickets", "--promote", run.name if run else "",
    )  # fmt: skip
    doc = (data / "rounds/tickets_summary/r1.yaml").read_text()
    base = data / "baselines" / "tickets_v1_baseline.json"
    check(
        "round-close: closed with its conclusion, and the run promoted with it as the reason",
        r.returncode == 0
        and "status: closed" in doc
        and base.is_file()
        and json.loads(base.read_text())["reason"].startswith("three sentences lead"),
        out(r)[-300:],
    )
    r = evh("experiment-run", "--config", "data/configs/author.yaml", "--dry-run")
    check("a closed round refuses new runs", r.returncode != 0 and "is closed" in out(r), out(r)[-300:])

    r = evh(
        "round-open",
        "--goal",
        "tickets_summary",
        "--dataset",
        "tickets_v1",
        "--from",
        "r1",
        "--keep",
        "tickets_author_v1",
    )
    doc2 = (data / "rounds/tickets_summary/r2.yaml").read_text() if r.returncode == 0 else ""
    check(
        "the next round continues the last, from its baseline",
        "from: r1" in doc2 and f"baseline: {run.name if run else None}" in doc2,
        out(r) + doc2,
    )
    r = evh("round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1")
    check("only one round of a goal is open at a time", r.returncode != 0 and "still open" in out(r), out(r))

    r = evh("validate")
    check(
        "validate: V14 counts the rounds and passes",
        "2 round(s)" in r.stdout and "FAIL V14" not in r.stdout,
        r.stdout[-600:],
    )
    (data / "rounds/tickets_summary/r3.yaml").write_text(
        "round_id: r3\ngoal: tickets_summary\ndataset_id: nope\nstatus: closed\nopened_at: x\n"
    )
    r = evh("validate")
    check(
        "validate: V14 fails a round on a missing dataset, closed without a conclusion",
        "FAIL V14" in r.stdout
        and "dataset 'nope' does not exist" in r.stdout
        and "closed without a conclusion" in r.stdout,
        r.stdout[-600:],
    )
    (data / "rounds/tickets_summary/r3.yaml").unlink()

    # A re-timing of the same config on another machine (data/runs-linux) is its own arm in the
    # catalog; a round retires that copy alone, by naming its runs directory.
    assert run is not None, "a run of round r1 is needed to copy"
    linux = data / "runs-linux" / run.name
    shutil.copytree(run, linux)
    m = json.loads((linux / "metrics.json").read_text())
    m["round"] = "r2"
    (linux / "metrics.json").write_text(json.dumps(m))
    cfg_id = m["config_id"]
    r = evh(
        "round-retire", "--goal", "tickets_summary", "--round", "r2", "--arm", cfg_id,
        "--runs-dir", "runs-linux", "--reason", "a re-timing of the same config on another machine",
    )  # fmt: skip
    doc2 = (data / "rounds/tickets_summary/r2.yaml").read_text()
    check(
        "round-retire --runs-dir: the retirement names the runs directory it applies to",
        r.returncode == 0 and "runs_dir: runs-linux" in doc2,
        out(r) + doc2,
    )
    r = evh("goals", "--goal", "tickets_summary")
    rows = [ln for ln in r.stdout.splitlines() if cfg_id in ln]
    check(
        "the retired copy reads retired; the arm in data/runs does not",
        any("linux" in ln and "[retired in r2]" in ln for ln in rows)
        and any("linux" not in ln and "[retired in r2]" not in ln for ln in rows),
        "\n".join(rows) or r.stdout[-800:],
    )

    evh("catalog")
    page = (proj / ".build/catalog/g/tickets_summary.html").read_text()
    check(
        "catalog: the goal page shows its rounds, the open one's suggestions as commands",
        'id="rounds"' in page
        and "r1" in page
        and "r2" in page
        and "suggested next" in page
        and "retired in r1" in page,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# Promote only a leader the evidence puts ahead (the 2026-10-25 newcomer run: r2 suggested
# promoting an arm not separated from the baseline, and r1's best was ahead of it).
from evaluation_harness.rounds import _promote_hold  # noqa: E402


def row(label, verdict, delta=0.01, p=0.5):
    return {"label": label, "verdict": verdict, "delta": delta, "p": p}


BASE, PREV = "the baseline it started from", "r1's best"
check(
    "promote: a leader separated better than the baseline, not behind r1's best, is promoted",
    _promote_hold([row(BASE, "separated: better", p=0.01), row(PREV, "not separated")], "r1") == "",
)
check(
    "promote: a leader not separated from the baseline is not, and the reason says so with its p",
    _promote_hold([row(BASE, "not separated", 0.001, 0.9661)], "r1").startswith(
        "not ahead of the baseline it started from (not separated, Δ +0.0010, p 0.9661"
    ),
)
check(
    "promote: a leader separated worse than the previous round's best is not",
    _promote_hold(
        [row(BASE, "separated: better", p=0.01), row(PREV, "separated: worse", -0.06, 0.03)], "r1"
    ).startswith("behind r1's best (separated: worse"),
)
check(
    "promote: a round with no baseline and no previous round promotes its leader",
    _promote_hold([], None) == "",
)

sys.exit(summary())
