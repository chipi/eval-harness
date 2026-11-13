#!/usr/bin/env python3
"""Eval rounds (ADR-0004): open, run, the evidence and its suggestions, retire, close, the next.

    python tests/test_rounds.py

In a throwaway project built from the tutorial ($0, offline, the echo provider): a round of a goal
is opened carrying two arms in, a third runs naming it; `evh rounds` suggests retiring the arm the
test finds significantly worse, with the command; the retirement and the close (promoting the leader) are
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
from evaluation_harness import _common, _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-rounds-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-rounds")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
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
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        )
        evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")

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
    doc = _runstore.read_text(proj, "rounds/tickets_summary/r1.yaml") if r.returncode == 0 else ""
    check(
        "round-open: writes r1, open, with the arms carried in",
        "status: open" in doc and "tickets_lead1_v1" in doc,
        out(r),
    )

    cfg = (KIT / "systems" / "tickets_author_v1.yaml").read_text()
    _runstore.write_text(proj, "systems/tickets_author_v1.yaml", cfg)
    r = evh(
        "run",
        "--system",
        "tickets_author_v1",
        "--dataset",
        "tickets_v1",
        "--goal",
        "tickets_summary",
        "--round",
        "r1",
    )
    run = next(
        (data / "runs" / n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_author_v1_")),
        None,
    )
    check(
        "a run naming the round runs in it, and the run records the round",
        r.returncode == 0
        and run is not None
        and _runstore.read_json(proj, f"runs/{run.name}/run.json").get("round") == "r1",
        out(r)[-300:],
    )

    r = evh("rounds", "--goal", "tickets_summary")
    # On gold over six tickets lead2 leads and no arm differs significantly: more items, the evidence says.
    check(
        "rounds: the evidence and its suggestions, each as the command that does it",
        "leader tickets_lead2_v1" in r.stdout
        and "not significantly different from the leader" in r.stdout
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
    # CLI parity: the inspector's sheet and analysis charts, and the catalog's search.
    r = evh("inspect", "--sheet", "--dataset-id", "tickets_v1", "--runs", "tickets_lead1_v1,tickets_lead2_v1")
    check(
        "evh inspect --sheet: every item's score per arm, the winner per row and each arm's win rate",
        r.returncode == 0 and "overlap_f1" in r.stdout and "win rate" in r.stdout,
        out(r)[-500:],
    )
    r = evh("inspect", "--round", "r1", "--goal", "tickets_summary", "--analysis")
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
    r = evh("label-from-run", "--run", run.name if run else "", "--set", "author_labels")
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
        r.returncode == 0
        and "one sentence drops" in _runstore.read_text(proj, "rounds/tickets_summary/r1.yaml"),
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
    doc = _runstore.read_text(proj, "rounds/tickets_summary/r1.yaml")
    base = "baselines/tickets_summary/tickets_v1/1.json"
    check(
        "round-close: closed with its conclusion, and the run promoted with it as the reason",
        r.returncode == 0
        and "status: closed" in doc
        and _runstore.is_file(proj, base)
        and _runstore.read_json(proj, base)["reason"].startswith("three sentences lead"),
        out(r)[-300:],
    )
    r = evh(
        "run",
        "--system",
        "tickets_author_v1",
        "--dataset",
        "tickets_v1",
        "--goal",
        "tickets_summary",
        "--round",
        "r1",
        "--dry-run",
    )
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
    doc2 = _runstore.read_text(proj, "rounds/tickets_summary/r2.yaml") if r.returncode == 0 else ""
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
    _runstore.write_text(
        proj,
        "rounds/tickets_summary/r3.yaml",
        "round_id: r3\ngoal: tickets_summary\ndataset_id: nope\nstatus: closed\nopened_at: x\n",
    )
    r = evh("validate")
    check(
        "validate: V14 fails a round on a missing dataset, closed without a conclusion",
        "FAIL V14" in r.stdout
        and "dataset 'nope' does not exist" in r.stdout
        and "closed without a conclusion" in r.stdout,
        r.stdout[-600:],
    )
    _runstore.unlink(proj, "rounds/tickets_summary/r3.yaml")

    # A re-timing of the same system on another machine (purpose retime, machine linux) is its own arm in the
    # catalog; a round retires that copy alone, by naming its runs.
    assert run is not None, "a run of round r1 is needed to copy"
    linux_id = f"{run.name}_linux"
    with _runstore._InProject(proj):
        _runstore.copy_run(run, data / "runs" / linux_id)
    m = _runstore.read_json(proj, f"runs/{linux_id}/run.json")
    m.update(run_id=linux_id, round="r2", purpose="retime", machine="linux", of=run.name)
    _runstore.write_text(proj, f"runs/{linux_id}/run.json", json.dumps(m))
    cfg_id = m["config_id"]
    r = evh(
        "round-retire", "--goal", "tickets_summary", "--round", "r2", "--arm", cfg_id,
        "--runs", linux_id, "--reason", "a re-timing of the same config on another machine",
    )  # fmt: skip
    doc2 = _runstore.read_text(proj, "rounds/tickets_summary/r2.yaml")
    check(
        "round-retire --runs: the retirement names the runs it applies to",
        r.returncode == 0 and f"- {linux_id}" in doc2 and "runs_dir" not in doc2,
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

    # Fleet feedback 22: a round opened with --keep carried its baseline arm in but recorded no baseline, and
    # `pair-test --round` refused. --baseline names it, by config id or run id.
    r = evh(
        "round-close",
        "--goal",
        "tickets_summary",
        "--round",
        "r2",
        "--conclusion",
        "closed to open r3 in the test",
    )
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--keep", "tickets_lead1_v1", "--baseline", "nope_v1",
    )  # fmt: skip
    check(
        "round-open --baseline: a config with no measured run on the dataset is refused, nothing written",
        r.returncode != 0
        and "no measured run" in out(r)
        and not _runstore.exists(proj, "rounds/tickets_summary/r3.yaml"),
        out(r),
    )
    lead1 = sorted(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_lead1_v1_"))
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1", "--baseline", "tickets_lead1_v1",
    )  # fmt: skip
    doc3 = _runstore.read_text(proj, "rounds/tickets_summary/r3.yaml") if r.returncode == 0 else ""
    check(
        "round-open --baseline <config>: the round records that config's latest run, and says so",
        bool(lead1) and f"baseline: {lead1[-1]}" in doc3 and f"It starts from {lead1[-1]}" in r.stdout,
        out(r) + doc3,
    )
    check(
        "round-open records the harness code it opened on, and says so (the fleet's feedback 17)",
        "harness:" in doc3 and "code_sha256:" in doc3 and "On harness " in r.stdout,
        out(r) + doc3,
    )
    evh(
        "run",
        "--system",
        "tickets_author_v1",
        "--dataset",
        "tickets_v1",
        "--goal",
        "tickets_summary",
        "--round",
        "r3",
    )
    r3run = next(
        (n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_author_v1_")
         and _runstore.read_json(proj, f"runs/{n}/run.json").get("round") == "r3"),
        None,
    )  # fmt: skip
    r = evh("rounds", "--goal", "tickets_summary", "--round", "r3")
    check(
        "rounds: a run on the round's own harness code gets no split note",
        r3run is not None and "other harness code" not in r.stdout and "harness: " in r.stdout,
        out(r)[-600:],
    )
    if r3run:
        m = _runstore.read_json(proj, f"runs/{r3run}/run.json")
        m["fingerprint"]["instrument"]["harness"]["code_sha256"] = "0" * 64
        m["fingerprint"]["instrument"]["harness"]["version"] = "9.9.9"
        _runstore.write_text(proj, f"runs/{r3run}/run.json", json.dumps(m))
    r = evh("rounds", "--goal", "tickets_summary", "--round", "r3")
    check(
        "rounds: a run on other harness code than the round opened on is named, with how to run it on the round's",
        "1 run(s) ran on other harness code" in r.stdout
        and f"{r3run} (9.9.9, code 000000000000)" in r.stdout
        and ("git worktree add ../r3-harness" in r.stdout or "pip install evaluation-harness==" in r.stdout),
        out(r)[-800:],
    )
    r = evh("pair-test", "--dataset-id", "tickets_v1", "--goal", "tickets_summary", "--round", "r3")
    check(
        "pair-test --round on that round: its leader against the named baseline, no --b needed",
        r.returncode == 0
        and "records no other baseline" not in out(r)
        and "against tickets_lead1_v1" in out(r),
        out(r)[-400:],
    )
    r = evh(
        "pair-test", "--dataset-id", "tickets_v1", "--goal", "tickets_summary", "--round", "r3",
        "--a", "tickets_lead1_v1",
    )  # fmt: skip
    check(
        "pair-test --round with --a its baseline: says the arm is the baseline, not that none is recorded",
        r.returncode != 0
        and "tickets_lead1_v1 is round r3's baseline" in out(r)
        and "records no baseline" not in out(r),
        out(r)[-400:],
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
    check(
        "catalog: each round is one folded section headed by its row (no rounds table), retirements grouped by reason",
        '<table id="rounds"' not in page
        and page.count('<details class="roundcard') >= 2
        and 'id="round-r1"' in page
        and '<details class="roundcard' in page
        and " open>" not in page[page.find('<details class="roundcard') :][:200]
        and bool(__import__("re").search(r"retired \d+</b>: ", page))
        and '<h4 class="rc-h">arms</h4>' in page
        and '<h4 class="rc-h">suggested next</h4>' in page,
        page[page.find('<details class="roundcard') :][:600],
    )

    # The fleet's feedback 33: k runs of a deterministic arm are near-copies, not k samples.
    r = evh("run", "--system", "tickets_lead1_v1", "--dataset", "tickets_v1", "--repeat", "2")
    check(
        "run --repeat: the summary says how many items every repeat scored the same, and items, not item-runs",
        r.returncode == 0
        and "the same score on 6 of 6 items (near-copies, not independent samples)" in r.stdout
        and "read 6 items, not 12 item-runs" in r.stdout,
        out(r)[-600:],
    )
    r = evh(
        "pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead1_v1", "--b", "tickets_lead2_v1",
        "--metric", "overlap_f1", "--json",
    )  # fmt: skip
    pj = json.loads(r.stdout) if r.returncode == 0 else {}
    rep = ((pj.get("result") or {}).get("values") or pj).get("repeats") or {}
    check(
        "pair-test: an arm's repeats are named with their agreement, each item counted once",
        r.returncode == 0
        and (rep.get("tickets_lead1_v1") or {}).get("same") == 6
        and "tickets_lead2_v1" not in rep,
        r.stdout[-800:] + r.stderr[-300:],
    )

    # The fleet's beta (F3): a new round whose only arm is its baseline was said to "record no other baseline run".
    evh(
        "round-close",
        "--goal",
        "tickets_summary",
        "--round",
        "r3",
        "--conclusion",
        "closed to open r4 in the test",
    )
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--keep", "tickets_lead1_v1", "--baseline", "tickets_lead1_v1",
    )  # fmt: skip
    r4 = evh("pair-test", "--dataset-id", "tickets_v1", "--goal", "tickets_summary", "--round", "r4")
    check(
        "pair-test --round on a round whose only arm is its baseline: says so, not that no baseline is recorded",
        r.returncode == 0
        and r4.returncode != 0
        and "round r4 has no arm besides its baseline tickets_lead1_v1" in out(r4)
        and "records no baseline" not in out(r4),
        out(r)[-300:] + out(r4)[-400:],
    )
    # The fleet's retest (F3b): --a naming the baseline, in that same round, was told there is no other arm.
    r4a = evh(
        "pair-test", "--dataset-id", "tickets_v1", "--goal", "tickets_summary", "--round", "r4",
        "--a", "tickets_lead1_v1",
    )  # fmt: skip
    check(
        "pair-test --round --a the baseline, in a round of only the baseline: says --a is the baseline",
        r4a.returncode != 0
        and "tickets_lead1_v1 is round r4's baseline" in out(r4a)
        and "no arm besides" not in out(r4a),
        out(r4a)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
    # _runstore aimed this process at the test project; the checks below read this repository's committed data,
    # which is files.
    _common.project_root.cache_clear()
    os.environ["EVAL_STORE"] = "files"

# Promote only a leader the evidence puts ahead (the 2026-10-25 newcomer run: r2 suggested
# promoting an arm not significantly different from the baseline, and r1's best was ahead of it).
from evaluation_harness.rounds import _promote_hold  # noqa: E402


def row(label, verdict, delta=0.01, p=0.5):
    return {"label": label, "verdict": verdict, "delta": delta, "p": p}


BASE, PREV = "the baseline it started from", "r1's best"
check(
    "promote: a leader significantly better than the baseline, not behind r1's best, is promoted",
    _promote_hold([row(BASE, "significant: better", p=0.01), row(PREV, "not significant")], "r1") == "",
)
check(
    "promote: a leader not significantly different from the baseline is not, and the reason says so with its p",
    _promote_hold([row(BASE, "not significant", 0.001, 0.9661)], "r1").startswith(
        "not ahead of the baseline it started from (not significant, Δ +0.0010, p 0.9661"
    ),
)
check(
    "promote: a leader significantly worse than the previous round's best is not",
    _promote_hold(
        [row(BASE, "significant: better", p=0.01), row(PREV, "significant: worse", -0.06, 0.03)], "r1"
    ).startswith("behind r1's best (significant: worse"),
)
check(
    "promote: a round with no baseline and no previous round, its leader separated from the others, promotes it",
    _promote_hold([], None) == "",
)
# Review 2026-11-04 (M3): with no baseline row, a leader tied with other arms, or a round whose own note
# says its arms were scored differently, was still handed a --promote command.
check(
    "promote: a leader not separated from other arms after Holm is not promoted; the reason names them",
    _promote_hold([], None, ["mini", "fy"]).startswith("not separated from mini, fy"),
)
check(
    "promote: arms measured by different scorers are not promoted from, whatever the test says",
    _promote_hold([row(BASE, "significant: better", p=0.01)], None, [], True).startswith(
        "measured by different scorers"
    ),
)
check(
    "promote: the reason carries the family the baseline test was corrected for",
    "Bonferroni over 4 arms: 0.8000"
    in _promote_hold([{**row(BASE, "not significant", 0.01, 0.2), "family": 4, "p_adjusted": 0.8}], None),
)

# Review 2026-11-04 (L2): --goal reached files outside data/rounds through `..` and glob characters.
from evaluation_harness import _rounds  # noqa: E402

check(
    "rounds: a goal that is not a plain name has no rounds (no `..`, separator or glob reaches outside)",
    all(_rounds.load_rounds(g) == [] for g in ("../x", "a/b", "*", "x?", "[a]", ".hidden", ".."))
    # and the check is not vacuous: a real goal of this repository still has its rounds
    and bool(_rounds.load_rounds("news_topic_ag")),
)

sys.exit(summary())
