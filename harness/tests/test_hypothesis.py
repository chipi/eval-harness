#!/usr/bin/env python3
"""A hypothesis recorded in an arm's config before the run (ADR-0025).

    python tests/test_hypothesis.py

In a throwaway git project built from the tutorial ($0, offline, the echo provider): a hypothesis committed before
the run is recorded as named in advance (yes, with the commit); one added to the config after the run reads no; one
made outside git or on a dirty tree is not determinable; a hypothesis never changes the fingerprint's hash; validate
V20 and `evh run` refuse a malformed one in words; `evh pair-test` and `evh goals --goal` report it; and pair-test
--round corrects for the selection when it chose A, and refuses --family below 1.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
KIT = HERE.parent / "tutorial"

proj = Path(tempfile.mkdtemp(prefix="evh-hypothesis-"))
os.environ["EVAL_HOME"] = str(proj)  # the library below reads the same project the commands do
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR", "EVAL_BUILD_REF"):
    os.environ.pop(k, None)
env = dict(os.environ)

from evaluation_harness import _hypothesis  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def evh(*args, extra_env=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **(extra_env or {})},
        capture_output=True,
        text=True,
    )


def git(*args):
    r = subprocess.run(["git", *args], cwd=proj, capture_output=True, text=True)
    return r.stdout.strip()


def out(r):
    return r.stdout + r.stderr


def commit(msg):
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", msg)


def metrics_of(config_id):
    found = sorted((proj / "data" / "runs").glob(f"{config_id}_*/metrics.json"))
    return json.loads(found[-1].read_text()) if found else {}


def write_cfg(name, config_id, sentences, hypothesis=None, goal=True):
    text = (
        f"config_id: {config_id}\ndataset_id: tickets_v1\n"
        f"params:\n  provider: echo\n  sentences: {sentences}\n" + ("goal: tickets_summary\n" if goal else "")
    )
    if hypothesis:
        text += "hypothesis:\n" + "".join(f"  {k}: {json.dumps(v)}\n" for k, v in hypothesis.items())
    (proj / "data" / "configs" / name).write_text(text)


HYP = {
    "against": "tickets_lead1_v1",
    "measure": "overlap_f1",
    "direction": "better",
    "statement": "two sentences summarise a ticket better than one",
}

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    (proj / ".gitignore").write_text(".cache/\n.build/\n__pycache__/\n")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "o")
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
            "--reason", "The kit's summaries decide.", "--by", "owner",
        )
    )  # fmt: skip
    check("setup: the tutorial dataset and its gold", r.returncode == 0, out(r)[-300:])
    write_cfg("lead1.yaml", "tickets_lead1_v1", 1)
    r = evh("run", "--config", "data/configs/lead1.yaml", extra_env={"EVAL_BUILD_REF": "no-git-test"})
    check("setup: the arm it is compared with has run", r.returncode == 0, out(r)[-300:])

    # ── outside git: not determinable ─────────────────────────────────────────────────────────────────
    write_cfg("nogit.yaml", "tickets_nogit_v1", 2, HYP)
    r = evh("run", "--config", "data/configs/nogit.yaml", extra_env={"EVAL_BUILD_REF": "no-git-test"})
    m = metrics_of("tickets_nogit_v1")
    adv = m.get("hypothesis_in_advance") or {}
    check(
        "run: the hypothesis is recorded on the run, as written",
        r.returncode == 0 and m.get("hypothesis", {}).get("against") == "tickets_lead1_v1"
        and m["hypothesis"]["direction"] == "better",
        out(r)[-300:],
    )  # fmt: skip
    check(
        "run: outside a git repository whether it was named in advance is not determinable",
        adv.get("named") is None and "git" in adv.get("why", ""),
        adv,
    )

    # ── committed before the run: yes ──────────────────────────────────────────────────────────────────
    git("init", "-q")
    write_cfg("lead2.yaml", "tickets_lead2_v1", 2, HYP)
    commit("setup, lead2 with its hypothesis")
    sha = git("log", "-1", "--format=%H", "--", "data/configs/lead2.yaml")
    r = evh("run", "--config", "data/configs/lead2.yaml")
    m = metrics_of("tickets_lead2_v1")
    adv = m.get("hypothesis_in_advance") or {}
    check(
        "run: a hypothesis committed before the run is recorded as named in advance, with the commit",
        r.returncode == 0 and adv.get("named") is True and adv.get("commit") == sha,
        (adv, sha, out(r)[-300:]),
    )
    check(
        "run: it says so while it runs",
        f"named in advance: yes (committed {sha[:8]} before the run)" in r.stdout,
        r.stdout[-400:],
    )

    fp = m["fingerprint"]
    check(
        "the fingerprint does not carry the hypothesis",
        "two sentences summarise" not in json.dumps(fp) and "hypothesis" not in json.dumps(fp),
    )
    from evaluation_harness import _common
    from evaluation_harness._fingerprint import build_fingerprint

    common: dict[str, Any] = {
        "root": _common.ROOT,
        "data_dir": _common.DATA,
        "dataset": _common.load_dataset("tickets_v1"),
        "reference_id": None,
        "reference_tier": None,
        "config_id": "tickets_lead2_v1",
        "params": {"provider": "echo", "sentences": 2},
        "adapter_id": "scripts/adapter.py",
        "adapter_path": None,
    }
    plain = build_fingerprint(cfg={"config_id": "tickets_lead2_v1"}, **common)
    with_h = build_fingerprint(cfg={"config_id": "tickets_lead2_v1", "hypothesis": HYP}, **common)
    other = build_fingerprint(
        cfg={"config_id": "tickets_lead2_v1"}, **{**common, "params": {"provider": "echo", "sentences": 1}}
    )
    check(
        "fingerprint: the same hash with a hypothesis in the config and without (a prediction is not a measurement)",
        plain["hash"] == with_h["hash"] and plain["hash"] != other["hash"],
        (plain["hash"][:12], with_h["hash"][:12], other["hash"][:12]),
    )

    r = evh("pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--b", "tickets_lead1_v1")
    check(
        "pair-test: A's hypothesis against B on the tested metric, named in advance (yes, the commit), agreement",
        r.returncode == 0
        and f"named in advance   yes (committed {sha[:8]} before the run)" in r.stdout
        and "result agrees" in r.stdout
        and "uncorrected: valid because the hypothesis was committed before the run" in r.stdout,
        out(r)[-600:],
    )  # fmt: skip
    js = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--b",
        "tickets_lead1_v1",
        "--json",
    )
    hv = (json.loads(js.stdout)["result"]["values"] if js.returncode == 0 else {}).get("hypothesis") or {}
    check(
        "pair-test --json: values.hypothesis names the direction, the verdict on it and whether it was named in advance",
        hv.get("named_in_advance") == "yes"
        and hv.get("commit") == sha
        and hv.get("direction") == "better"
        and hv.get("agrees") in ("yes", "no", "not shown"),
        hv,
    )  # fmt: skip
    r = evh("pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead1_v1", "--b", "tickets_lead2_v1")
    check(
        "pair-test: a pair no run has a hypothesis for prints what it always did",
        "named in advance" not in r.stdout and "uncorrected: valid only if this pair was named" in r.stdout,
        out(r)[-400:],
    )

    r = evh("goals", "--goal", "tickets_summary")
    check(
        "goals --goal: the hypothesis beside the arm that has one",
        "hypothesis" in r.stdout
        and "better than tickets_lead1_v1 on overlap_f1; named in advance: yes" in r.stdout,
        out(r)[-800:],
    )
    gj = evh("goals", "--goal", "tickets_summary", "--json")
    arms = (
        [a for g in json.loads(gj.stdout)["result"]["values"]["groups"] for a in g["arms"]]
        if gj.returncode == 0
        else []
    )
    check(
        "goals --goal --json: the hypothesis by name on that arm",
        any((a.get("hypothesis") or {}).get("named_in_advance") == "yes" for a in arms),
        arms[:1],
    )

    # ── added to the config after the run: no ──────────────────────────────────────────────────────────
    write_cfg("late.yaml", "tickets_late_v1", 2)
    commit("late arm, no hypothesis yet")
    evh("run", "--config", "data/configs/late.yaml")
    check(
        "the run of an arm without a hypothesis records none",
        "hypothesis" not in metrics_of("tickets_late_v1"),
    )
    write_cfg("late.yaml", "tickets_late_v1", 2, HYP)
    commit("late arm: hypothesis written after the results")
    r = evh("pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_late_v1", "--b", "tickets_lead1_v1")
    check(
        "pair-test: a hypothesis added to the config after the run reads 'no'",
        r.returncode == 0 and "named in advance   no (" in r.stdout and "added after" in r.stdout
        and "uncorrected: valid because" not in r.stdout,
        out(r)[-600:],
    )  # fmt: skip
    # Final review 2026-11-04 (medium): the arm run again AFTER the hypothesis was committed read "yes ... valid
    # because the hypothesis was committed before the run", while the test averaged in the run made before it.
    evh("run", "--config", "data/configs/late.yaml")
    r = evh("pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_late_v1", "--b", "tickets_lead1_v1")
    check(
        "pair-test: an arm with a run from before its hypothesis is not named in advance, though a later run is",
        r.returncode == 0 and "named in advance   no (" in r.stdout and "predate the hypothesis" in r.stdout
        and "uncorrected: valid because" not in r.stdout,
        out(r)[-2500:],
    )  # fmt: skip
    r = evh("goals", "--goal", "tickets_summary", "--json")
    late = [
        a
        for g in (json.loads(r.stdout)["result"]["values"].get("groups") or [] if r.returncode == 0 else [])
        for a in g.get("arms", [])
        if "tickets_late_v1" in str(a.get("arm"))
    ]
    check(
        "goals: the same arm's hypothesis reads 'no' there too, whichever run is newest",
        bool(late) and all((a.get("hypothesis") or {}).get("named_in_advance") == "no" for a in late),
        late[:1] or out(r)[-400:],
    )
    # The run added here, not committed: removed, so the tree is clean again for the checks below (the first run is
    # committed and stays).
    shutil.rmtree(sorted((proj / "data" / "runs").glob("tickets_late_v1_*"))[-1])

    # ── the commit's time against the run's start ──────────────────────────────────────────────────────
    named = _hypothesis.named_before(
        data / "configs" / "lead2.yaml",
        HYP,
        {"ref": git("rev-parse", "HEAD"), "source": "git"},
        "2000-01-01T00:00:00Z",
    )
    check(
        "a hypothesis committed after the run began reads no, with the commit named",
        named["named"] is False and named["commit"] == sha and "not before the run" in named["why"],
        named,
    )
    old = _hypothesis.named_before(
        data / "configs" / "lead2.yaml",
        HYP,
        {"ref": git("rev-parse", "HEAD"), "source": "git"},
        "2999-01-01T00:00:00Z",
    )
    check("... and before a later start, yes", old["named"] is True and old["commit"] == sha, old)
    changed = _hypothesis.named_before(
        data / "configs" / "lead2.yaml",
        {**HYP, "direction": "worse"},
        {"ref": git("rev-parse", "HEAD"), "source": "git"},
        "2999-01-01T00:00:00Z",
    )
    check(
        "a hypothesis that is in no commit reads no",
        changed["named"] is False and changed["commit"] is None,
        changed,
    )

    # ── a dirty tree: not determinable ─────────────────────────────────────────────────────────────────
    write_cfg("dirty.yaml", "tickets_dirty_v1", 2, HYP)
    commit("dirty arm")
    goal_file = data / "goals" / "tickets_summary.yaml"
    goal_file.write_text(goal_file.read_text() + "# edited, not committed\n")
    r = evh("run", "--config", "data/configs/dirty.yaml")
    adv = metrics_of("tickets_dirty_v1").get("hypothesis_in_advance") or {}
    check(
        "run: on a dirty tree whether it was named in advance is not determinable",
        r.returncode == 0 and adv.get("named") is None and "dirty" in adv.get("why", ""),
        (adv, out(r)[-300:]),
    )
    git("checkout", "--", str(goal_file.relative_to(proj)))

    # ── validate V20 and evh run refuse a malformed one ────────────────────────────────────────────────
    r = evh("validate")
    line = next((ln for ln in r.stdout.splitlines() if "V20" in ln), "")
    check(
        "validate V20: passes with sound hypotheses",
        "ok" in line and "FAIL" not in r.stdout and "config(s) with one" in line,
        (line, out(r)[-400:]),
    )
    bad_cases = {
        "direction": (
            {**HYP, "direction": "sideways"},
            "hypothesis.direction: 'sideways' is not one of better, worse, no-worse",
        ),
        "against": (
            {**HYP, "against": "tickets_nope_v1"},
            "hypothesis.against: no config with config_id 'tickets_nope_v1'",
        ),
        "measure": (
            {**HYP, "measure": "overlap_f9"},
            "hypothesis.measure: 'overlap_f9' is not one of this arm's metrics",
        ),
        "statement": ({k: v for k, v in HYP.items() if k != "statement"}, "hypothesis.statement: required"),
        "items": ({**HYP, "items": "no/such/file.txt"}, "hypothesis.items: no file 'no/such/file.txt'"),
    }
    for what, (h, words) in bad_cases.items():
        write_cfg("bad.yaml", "tickets_bad_v1", 2, h)
        v = evh("validate")
        line = next((ln for ln in v.stdout.splitlines() if "V20" in ln), "")
        run_dirs = len(list((data / "runs").glob("tickets_bad_v1_*")))
        rr = evh("run", "--config", "data/configs/bad.yaml")
        check(
            f"validate V20 refuses a hypothesis with a bad {what}, in words",
            v.returncode != 0 and "FAIL" in line and words in v.stdout,
            (line, v.stdout[-500:]),
        )
        check(
            f"evh run refuses it too, before a call is made ({what})",
            rr.returncode != 0
            and words in out(rr)
            and len(list((data / "runs").glob("tickets_bad_v1_*"))) == run_dirs == 0,
            out(rr)[-300:],
        )
    (data / "configs" / "bad.yaml").unlink()

    # ── pair-test --round: the selection is corrected for; --family below 1 is refused ──────────────────
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--hypothesis", "sentences",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1,tickets_late_v1",
    )  # fmt: skip
    check("setup: a round with three arms in play", r.returncode == 0, out(r)[-300:])
    base = [
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--round",
        "r1",
        "--goal",
        "tickets_summary",
        "--b",
        "tickets_lead1_v1",
    ]
    r = evh(*base)
    jr = evh(*base, "--json")
    v = json.loads(jr.stdout)["result"]["values"] if jr.returncode == 0 else {}
    check(
        "pair-test --round: A chosen as the leader is corrected for the arms in play, and the output says so",
        r.returncode == 0
        and "A was chosen from the table: corrected for the 2 comparisons it could have been" in r.stdout
        and "Bonferroni/2" in r.stdout
        and "valid only if this pair was named" not in r.stdout,
        out(r)[-600:],
    )  # fmt: skip
    check(
        "pair-test --round --json: selection leader, family 2, threshold alpha/2",
        (v.get("selection"), v.get("family"), v.get("candidates")) == ("leader", 2, 2)
        and abs(v.get("threshold", 0) - 0.025) < 1e-12,
        v,
    )
    named = json.loads(evh(*base, "--a", "tickets_lead2_v1", "--json").stdout)["result"]["values"]
    check(
        "pair-test --round --a: a named A is not corrected (selection named, family 1)",
        (named["selection"], named["family"]) == ("named", 1),
        named,
    )
    explicit = json.loads(evh(*base, "--family", "5", "--json").stdout)["result"]["values"]
    check("pair-test --round --family 5: the caller's family stands", explicit["family"] == 5, explicit)
    for bad in ("0", "-2"):
        r = evh(
            "pair-test",
            "--dataset-id",
            "tickets_v1",
            "--a",
            "tickets_lead2_v1",
            "--b",
            "tickets_lead1_v1",
            "--family",
            bad,
        )
        check(
            f"pair-test --family {bad}: refused in words, no traceback",
            r.returncode != 0 and "--family must be at least 1" in r.stderr and "Traceback" not in r.stderr,
            r.stderr[-300:],
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
