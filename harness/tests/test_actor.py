#!/usr/bin/env python3
"""Who acted on every record (RFC-027 D1).

    python tests/test_actor.py

`_actor.actor()` on its own (the flag, the environment, the terminal; an agent needs whom it acts for), then in a
throwaway project ($0, offline): a run, a dataset, a label set, a reference, a round and a pick each record their
actor; `--by` wins over the environment; a label set keeps who labelled (`source.by`) beside it; a decision
(run-promote, round-close) by an `unknown` actor is refused, saying how to name one; `dataset-split --split-by` is
the split rule, and `--by` there is who acted.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _actor  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402


def with_env(**kw):
    """actor() with these environment values (None removes one) and no --by."""
    saved = {k: os.environ.get(k) for k in kw}
    _actor._FLAG[:] = []
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return _actor.actor()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


a = with_env(EVH_ACTOR="person:ana", EVH_FOR=None)
check(
    "EVH_ACTOR=person:ana is a person, from the environment",
    a == {"type": "person", "name": "ana", "from": "environment"},
    a,
)
a = with_env(EVH_ACTOR="agent:fleet", EVH_FOR="person:ana")
check(
    "an agent records whom it acted for",
    a == {"type": "agent", "name": "fleet", "from": "environment", "for": "ana"},
    a,
)
try:
    with_env(EVH_ACTOR="agent:fleet", EVH_FOR=None)
    refused = False
except SystemExit:
    refused = True
check("an agent without EVH_FOR is refused", refused)
a = with_env(EVH_ACTOR=None, EVH_FOR=None)
check(
    "no flag and no environment: the OS user, a person on a terminal and unknown off one",
    a["from"] == "terminal" and a["type"] == ("person" if sys.stdin.isatty() else "unknown"),
    a,
)

proj = Path(tempfile.mkdtemp(prefix="evh-actor-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-actor")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_ACTOR", "EVH_FOR"):
    env.pop(k, None)


def evh(*args, **extra):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **extra},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def out(r):
    return r.stdout + r.stderr


try:
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets", EVH_ACTOR="person:ana")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    ds = _runstore.read_json(proj, "datasets/tk_v1.json") if r.returncode == 0 else {}
    check(
        "dataset-create: the record names its actor", ds.get("actor", {}).get("name") == "ana", out(r)[-300:]
    )
    r = evh(
        "dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets", "--force", EVH_ACTOR="person:bo"
    )
    ds2 = _runstore.read_json(proj, "datasets/tk_v1.json")
    check(
        "dataset-create again with the same items keeps its actor, as it keeps created_at (no churn)",
        ds2.get("actor", {}).get("name") == "ana" and ds2.get("created_at") == ds.get("created_at"),
        ds2.get("actor"),
    )
    r = evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "person:cy")
    lab = _runstore.read_json(proj, "labels/tk_v1/g/labels.json") if r.returncode == 0 else {}
    check(
        "label-import: who labelled (source.by) and who acted, both kept",
        lab.get("source", {}).get("by") == "person:cy" and lab.get("actor", {}).get("name") == "cy",
        out(r)[-300:] + json.dumps(lab.get("actor")),
    )
    r = evh(
        "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
        "--reason", "the kit's summaries for the actor test", "--by", "cy", EVH_ACTOR="person:ana",
    )  # fmt: skip
    ref = _runstore.read_json(proj, "references/gold/tk_v1/manifest.json") if r.returncode == 0 else {}
    check(
        "reference-promote: --by wins over the environment",
        ref.get("actor") == {"type": "person", "name": "cy", "from": "flag"},
        out(r)[-300:] + json.dumps(ref.get("actor")),
    )
    _runstore.write_text(
        proj,
        "configs/lead1.yaml",
        "config_id: lead1_v1\ndataset_id: tk_v1\nparams:\n  provider: echo\n  sentences: 1\n",
    )
    r = evh("run", "--config", "data/configs/lead1.yaml", EVH_ACTOR="agent:fleet", EVH_FOR="person:ana")
    run = next((n for n in _runstore.listdir(proj, "runs") if n.startswith("lead1_v1_")), None)
    m = _runstore.read_json(proj, f"runs/{run}/metrics.json") if run else {}
    check(
        "run: the record names the agent and the person it acted for",
        m.get("actor") == {"type": "agent", "name": "fleet", "from": "environment", "for": "ana"},
        out(r)[-300:] + json.dumps(m.get("actor")),
    )
    r = evh("run-promote", "--run", run or "x", "--reason", "the only arm, for the actor test")
    check(
        "run-promote by an unknown actor is refused, saying how to name one",
        r.returncode != 0 and "needs who made it" in out(r) and "--by person:NAME" in out(r),
        out(r)[-400:],
    )
    r = evh("run-promote", "--run", run or "x", "--reason", "the only arm, for the actor test", "--by", "ana")
    check("run-promote with --by goes ahead", r.returncode == 0, out(r)[-300:])
    r = evh("pick", "--dataset-id", "tk_v1", "--item", "t01_login", "--by", "person:dee")
    picks = (
        _runstore.read_text(proj, "picks.jsonl")
        if r.returncode == 0 and _runstore.exists(proj, "picks.jsonl")
        else ""
    )
    check("pick: the entry names its actor", '"name": "dee"' in picks, out(r)[-300:] + picks[-300:])
    r = evh("dataset-split", "tk_v1", "--test", "0.5", "--split-by", "hash", "--by", "ana", "--force")
    side = _runstore.read_json(proj, "datasets/tk_v1_test.json") if r.returncode == 0 else {}
    check(
        "dataset-split: --split-by is the rule, --by who acted",
        side.get("split", {}).get("split_by") == "hash" and side.get("actor", {}).get("name") == "ana",
        out(r)[-300:],
    )
    _runstore.write_text(
        proj,
        "goals/g.yaml",
        "goal_id: g\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\ndatasets:\n  - {dataset_id: tk_v1}\n",
    )
    r = evh(
        "round-open",
        "--goal",
        "g",
        "--dataset",
        "tk_v1",
        "--hypothesis",
        "the actor test",
        "--by",
        "person:eve",
    )
    import yaml

    rnd = yaml.safe_load(_runstore.read_text(proj, "rounds/g/r1.yaml")) if r.returncode == 0 else {}
    check(
        "round-open: the round names who opened it",
        (rnd.get("actor") or {}).get("name") == "eve",
        out(r)[-300:] + json.dumps(rnd.get("actor")),
    )
    r = evh("validate")
    check(
        "validate: records with an actor pass the schemas",
        "V1" in r.stdout and r.returncode == 0,
        r.stdout[-800:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
