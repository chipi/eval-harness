#!/usr/bin/env python3
"""The looks a test set allows (RFC-029), $0 and offline.

    python tests/test_looks.py

Look k's level is 2.5%·6/(π²k²). A sealed side's unseals are looks: the first at 1.52%, the next question at 0.38%,
the same question again reuses its look. Past the limit (a goal's `test_looks`) a look is refused without the
person's --confirm-extra-look, and an agent's consent is refused. A promotion on the test set is a look too, the same
question as the unseal that opened it (reused); it decides one-sided at the look's level, and items that could never
reach it are refused unless the person overrides (then labelled inconclusive). pair-test on a test set says "nominal,
not a look". `evh looks` lists them; V25 reports a number two questions took.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _looks  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402

check(
    "levels: look k at 2.5%·6/(π²k²): 1.52%, 0.38%, 0.17%; the series sums to 2.5%",
    abs(_looks.level(1) - 0.025 * 6 / math.pi**2) < 1e-15
    and round(_looks.level(1) * 100, 2) == 1.52
    and round(_looks.level(2) * 100, 2) == 0.38
    and round(_looks.level(3) * 100, 2) == 0.17
    and abs(sum(_looks.level(k) for k in range(1, 200000)) - 0.025) < 1e-6,
)

# The one-sided p a look decides with, against counting every sign pattern by hand.
import itertools  # noqa: E402
import random  # noqa: E402

from evaluation_harness import stats  # noqa: E402

rng = random.Random(5)
agree = True
for n in (1, 4, 7, 9):
    for _ in range(20):
        d = [round(rng.uniform(-1, 1.4), 2) for _ in range(n)]
        obs = sum(d)
        hits = sum(
            1
            for signs in itertools.product((1, -1), repeat=n)
            if sum(s * x for s, x in zip(signs, d, strict=True)) >= obs - 1e-12
        )
        agree = agree and abs(stats.exact_p_one_sided(d) - hits / 2**n) < 1e-12
check(
    "the one-sided p: every sign pattern counted by hand agrees; 1/2^n' is the smallest it can be",
    agree
    and stats.exact_p_one_sided([1, 2, 3, 4]) == 1 / 16
    and stats.min_attainable_p_one_sided([1, 0, 2, -1]) == 1 / 8
    and stats.min_attainable_p_one_sided(n=5) == 1 / 32
    and stats.min_attainable_p_one_sided(n=50, rule="noninferiority") is None,
)

proj = Path(tempfile.mkdtemp(prefix="evh-looks-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-looks")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)


def evh(*args, extra=None):
    e = {**env, **(extra or {})}
    return subprocess.run([sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=e, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL)  # fmt: skip


def git(*args):
    return subprocess.run(["git", "-C", str(proj), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          capture_output=True, text=True, check=False)  # fmt: skip


def system(name, sentences, against=None):
    text = f"system_id: {name}\nparams:\n  provider: echo\n  sentences: {sentences}\n"
    if against:
        text += (
            f"hypothesis:\n  against: {against}\n  measure: overlap_f1\n  direction: better\n"
            f"  statement: {name} summarises better than {against}\n"
        )
    _runstore.write_text(proj, f"systems/{name}.yaml", text)


def commit(msg):
    """Each unseal changes the dataset's record: committed, as a person would, before the next one checks the tree."""
    git("add", "-A")
    git("commit", "-qm", msg)


def looks_of():
    r = evh("looks", "--dataset", "tk_v1_test", "--json")
    sets = (
        (json.loads(r.stdout).get("result") or {}).get("values", {}).get("sets", [])
        if r.returncode == 0
        else []
    )
    return sets[0] if sets else {}


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    git("init", "-q")
    (proj / ".gitignore").write_text(
        ".build/\n"
    )  # as evh init writes it: locks and jobs are not the project's
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t")
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
        "--reason", "the kit's summaries, for the looks test", "--by", "t",
    )  # fmt: skip
    r = r if r.returncode else evh("dataset-split", "tk_v1", "--test", "0.7", "--seed", "3", "--seal")
    for ds in ("tk_v1_validation", "tk_v1_test"):
        r = r if r.returncode else evh("dataset-materialize", "--dataset-id", ds)
    check("setup: a split whose test side is sealed", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    system("base_v1", 1)
    system("cand_v1", 2, against="base_v1")
    system("cand2_v1", 3, against="base_v1")
    system("cand3_v1", 4, against="base_v1")
    git("add", "-A")
    git("commit", "-qm", "systems with their hypotheses")

    u1 = evh(
        "dataset-unseal", "tk_v1_test", "--system", "cand_v1", "--reason", "the two-sentence arm, frozen now"
    )
    commit("unsealed for cand_v1")
    u1b = evh(
        "dataset-unseal", "tk_v1_test", "--system", "cand_v1", "--reason", "the same question asked again"
    )
    commit("again")
    u2 = evh(
        "dataset-unseal",
        "tk_v1_test",
        "--system",
        "cand2_v1",
        "--reason",
        "the three-sentence arm, frozen now",
    )
    commit("unsealed for cand2_v1")
    s = looks_of()
    check(
        "unseals are looks: 1.52% for the first question, the same question again reuses look 1, the next is 0.38%",
        u1.returncode == u1b.returncode == u2.returncode == 0
        and "look 1:" in u1.stdout and "1.5198%" in u1.stdout
        and "look 1:" in u1b.stdout
        and "look 2:" in u2.stdout and "0.3800%" in u2.stdout
        and s.get("next") == 3,
        (u1.stdout[-200:], u1b.stdout[-200:], u2.stdout[-200:], u1.stderr[-200:], s.get("next")),
    )  # fmt: skip

    # A goal that tests on the set limits it to 2 looks.
    _runstore.write_text(
        proj,
        "goals/g.yaml",
        "goal_id: g\ntitle: t\nstatement: s\ndecision: d\ntest_looks: 2\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_v1_validation, role: validation}\n  - {dataset_id: tk_v1_test, role: test}\n",
    )
    commit("the goal")
    refused = evh(
        "dataset-unseal", "tk_v1_test", "--system", "cand3_v1", "--reason", "a third arm, past the limit"
    )
    agent = evh(
        "dataset-unseal", "tk_v1_test", "--system", "cand3_v1", "--reason", "a third arm, past the limit",
        "--confirm-extra-look", extra={"EVH_ACTOR": "agent:helper", "EVH_FOR": "person:test"},
    )  # fmt: skip
    person = evh(
        "dataset-unseal", "tk_v1_test", "--system", "cand3_v1", "--reason", "a third arm, past the limit",
        "--confirm-extra-look",
    )  # fmt: skip
    check(
        "past the limit: refused without consent, an agent's consent refused, the person's taken (look 3, 0.17%)",
        refused.returncode != 0 and "--confirm-extra-look" in refused.stderr
        and agent.returncode != 0 and "agent cannot" in agent.stderr
        and person.returncode == 0 and "look 3:" in person.stdout and "0.1689%" in person.stdout,
        (refused.stderr[-200:], agent.stderr[-200:], person.stdout[-200:], person.stderr[-200:]),
    )  # fmt: skip

    commit("unsealed for cand3_v1")
    # The open test side gets its gold (allowed once it is unsealed), then pair-test reads it nominally.
    side = {it["item_id"] for it in _runstore.read_json(proj, "datasets/tk_v1_test.json")["items"]}
    gold = proj / "gold_test"
    gold.mkdir()
    for f in (KIT / "gold").iterdir():
        if f.stem in side:
            shutil.copy(f, gold / f.name)
    g = evh("label-import", str(gold), "--dataset-id", "tk_v1_test", "--set", "gt", "--by", "t")
    g = g if g.returncode else evh(
        "reference-promote", "--dataset-id", "tk_v1_test", "--labels", "gt", "--tier", "gold",
        "--reason", "the kit's summaries, for the test side", "--by", "t",
    )  # fmt: skip
    check("setup: the test side's gold", g.returncode == 0, (g.stdout + g.stderr)[-400:])
    r1 = evh("run", "--system", "base_v1", "--dataset", "tk_v1_test")
    r2 = evh("run", "--system", "cand_v1", "--dataset", "tk_v1_test")
    pt = evh("pair-test", "--dataset-id", "tk_v1_test", "--a", "cand_v1", "--b", "base_v1")
    check(
        "pair-test on a test set: 'nominal, not a look', and the next look's level",
        r1.returncode == r2.returncode == 0 and pt.returncode == 0 and "nominal, not a look" in pt.stdout,
        (r1.stderr[-200:], r2.stderr[-200:], pt.stdout[-400:], pt.stderr[-200:]),
    )

    # A promotion on the test set: the first is not a look (nothing compared); the second is the unseal's question.
    def run_of(cid):
        return next(n for n in _runstore.listdir(proj, "runs") if n.startswith(cid + "_"))

    p1 = evh(
        "run-promote",
        "--run",
        run_of("base_v1"),
        "--goal",
        "g",
        "--reason",
        "the first baseline on the test set",
        "--allow-dirty",
    )
    p2 = evh(
        "run-promote",
        "--run",
        run_of("cand_v1"),
        "--goal",
        "g",
        "--reason",
        "the candidate, as named in advance",
        "--allow-dirty",
    )
    p3 = evh(
        "run-promote", "--run", run_of("cand_v1"), "--goal", "g", "--reason", "the candidate, as named in advance",
        "--allow-dirty", "--override-no-evidence",
    )  # fmt: skip
    versions = _runstore.listdir(proj, "baselines/g/tk_v1_test")
    ev = (
        _runstore.read_json(proj, f"baselines/g/tk_v1_test/{sorted(versions)[-1]}").get("evidence", {})
        if versions
        else {}
    )
    check(
        "a promotion on a test set reuses the unseal's look (1), cannot reach 1.52% on its items and is refused; "
        "with the person's override it is recorded inconclusive",
        p1.returncode == 0 and p2.returncode != 0 and "never be shown" in p2.stderr
        and p3.returncode == 0 and (ev.get("look") or {}).get("number") == 1
        and (ev.get("look") or {}).get("verdict") == "INCONCLUSIVE",
        (p1.stderr[-200:], p2.stderr[-300:], p3.stdout[-300:], p3.stderr[-300:], ev.get("look")),
    )  # fmt: skip

    # round-close --promote on the test set: the same look rules, its flags passed to run-promote.
    ro = evh("round-open", "--goal", "g", "--dataset", "tk_v1_test", "--hypothesis", "one sentence against two",
             "--keep", "base_v1,cand_v1")  # fmt: skip
    commit("round r1")
    base_run = run_of("base_v1")
    rc1 = evh(
        "round-close",
        "--goal",
        "g",
        "--round",
        "r1",
        "--conclusion",
        "the one-sentence arm after all",
        "--promote",
        base_run,
    )
    rc2 = evh(
        "round-close", "--goal", "g", "--round", "r1", "--conclusion", "the one-sentence arm after all",
        "--promote", base_run, "--confirm-extra-look", "--override-no-evidence",
    )  # fmt: skip
    versions = sorted(_runstore.listdir(proj, "baselines/g/tk_v1_test"))
    ev = (
        _runstore.read_json(proj, f"baselines/g/tk_v1_test/{versions[-1]}").get("evidence", {})
        if versions
        else {}
    )
    check(
        "round-close --promote on a test set is a look: past the limit refused, then with the person's flags passed "
        "through, look 4 recorded inconclusive and the round closed",
        ro.returncode == 0 and rc1.returncode != 0 and "--confirm-extra-look" in rc1.stderr
        and rc2.returncode == 0 and (ev.get("look") or {}).get("number") == 4
        and (ev.get("look") or {}).get("verdict") == "INCONCLUSIVE",
        (ro.stderr[-300:], rc1.stderr[-300:], rc2.stdout[-300:], rc2.stderr[-300:], ev.get("look")),
    )  # fmt: skip

    # The goal's page and `evh goals` say the test set's looks.
    gv = evh("goals", "--goal", "g")
    cat = evh("catalog")
    page = (proj / ".build" / "catalog" / "g" / "g.html").read_text() if cat.returncode == 0 else ""
    line = "test set: 4 look(s) of 2; a decision here is look 5"
    check(
        "the goal's page and evh goals: the test set's looks, its limit and the next look's level",
        line in gv.stdout and line in page,
        (gv.stdout[-500:], cat.stderr[-300:]),
    )

    # V25: two questions on one number (two clones deciding at once).
    ok = evh("validate")
    doc = _runstore.read_json(proj, "datasets/tk_v1_test.json")
    forged = json.loads(json.dumps(doc["unsealed"][-1]))
    forged["config_id"] = "cand2_v1"
    forged["look"] = {**forged["look"], "number": 2, "key": "0000000000000000"}
    doc["unsealed"].append(forged)
    _runstore.write_text(proj, "datasets/tk_v1_test.json", json.dumps(doc, indent=2) + "\n")
    bad = evh("validate")
    check(
        "V25: passes, then fails on a look number two questions took",
        "ok   V25" in ok.stdout and "FAIL V25" in bad.stdout and "double spend" in bad.stdout,
        (next((x for x in ok.stdout.splitlines() if "V25" in x), ""), bad.stdout[-400:]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
