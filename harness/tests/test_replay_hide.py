#!/usr/bin/env python3
"""Replays with production's own writes hidden, and the history confound (RFC-031 P1), $0 and offline.

    python tests/test_replay_hide.py

The replay example (examples/replay-filing) with `replay.hide: {kinds: [reopened]}`: production's own reopens made
inside the replayed window are hidden from the world the replay reads, the replay's own reopens stand in for them,
and a person's closes stay. A malformed hide is refused. The setting is part of the adapter's identity: the replay
without it has a faithfulness record, and scoring the hidden replay is refused until one is made with it; with it,
the default variant reproduces production on all 20 (the fleet's requirement before any variant counts). A
candidate at the third commit, with the same hiding, records its history confound (items where production filed an
issue it did not, and a person closed that issue later), writes their ids beside the run, and every score on it says so.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
EXAMPLE = HARNESS.parent / "examples" / "replay-filing"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-replay-hide-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-replay-hide")
env["PYTHONPATH"] = str(HARNESS) + os.pathsep + env.get("PYTHONPATH", "")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)
MINE = proj / "examples" / "replay-filing"


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip


def values(r):
    try:
        return (json.loads(r.stdout).get("result") or {}).get("values") or {}
    except ValueError:
        return {}


def run_id(r):
    runs = values(r).get("runs") or []
    return runs[0]["run_id"] if runs else None


def said(r):
    return r.stdout + r.stderr


try:
    (proj / "data").mkdir()
    shutil.copytree(EXAMPLE, MINE, ignore=shutil.ignore_patterns("__pycache__"))
    made = subprocess.run(
        [sys.executable, str(MINE / "make_history.py"), "--out", "replay-filing"], cwd=proj, env=env,
        capture_output=True, text=True,
    )  # fmt: skip
    steps = [
        ("capture", "--importer", "jsonl", "--query", json.dumps({"path": "replay-filing/rows.jsonl"}), "--capture", "filing_prod"),
        ("dataset-from-capture", "filing_prod", "--dataset-id", "filing_history_v1", "--fieldset", "filing",
         "--field", "ts", "--field", "started", "--field", "production_issue"),
        ("dataset-materialize", "--dataset-id", "filing_history_v1"),
        ("label-import", "replay-filing/gold", "--dataset-id", "filing_history_v1", "--set", "gold", "--by", "person:t"),
        ("reference-promote", "--dataset-id", "filing_history_v1", "--labels", "gold", "--tier", "gold",
         "--reason", "what each decision should have done", "--by", "person:t"),
    ]  # fmt: skip
    r = None
    for argv in steps:
        r = evh(*argv)
        if r.returncode:
            break
    prod = evh("run", "--config", "data/configs/filing_production_v1.yaml", "--json")
    prod_id = run_id(prod)
    check(
        "setup: the example's history, its dataset, gold, and production's recorded arm",
        made.returncode == 0 and r is not None and r.returncode == 0 and bool(prod_id),
        (made.stderr[-400:], said(r)[-400:] if r else "", prod.stderr[-300:]),
    )
    if not prod_id:
        sys.exit(summary())

    bad = (
        _runstore.read_text(proj, "configs/filing_replay_hidden_v1.yaml")
        .replace("config_id: filing_replay_hidden_v1", "config_id: filing_bad_hide_v1")
        .replace("hide: {kinds: [reopened]}", "hide: {kinds: [], window: always}")
    )
    _runstore.write_text(proj, "configs/filing_bad_hide_v1.yaml", bad)
    r = evh("run", "--config", "data/configs/filing_bad_hide_v1.yaml")
    check(
        "a malformed replay.hide is refused, saying its shape",
        r.returncode != 0 and "replay.hide is" in said(r),
        said(r)[-300:],
    )

    f0 = evh(
        "faithfulness", "--config", "data/configs/filing_replay_v1.yaml", "--production", prod_id, "--json"
    )
    r = evh("run", "--config", "data/configs/filing_replay_hidden_v1.yaml")
    check(
        "the hiding is part of the adapter's identity: the record made without it does not let the hidden replay be scored",
        f0.returncode == 0
        and (values(f0).get("faithfulness") or {}).get("counts", {}).get("agree") == 20
        and r.returncode != 0
        and "made with another adapter or other support modules, and none with these" in said(r),
        said(r)[-500:],
    )
    f1 = evh(
        "faithfulness",
        "--config",
        "data/configs/filing_replay_hidden_v1.yaml",
        "--production",
        prod_id,
        "--json",
    )
    rec = values(f1).get("faithfulness") or {}
    check(
        "with production's own reopens hidden in the window, the default variant still reproduces production: 20 of 20",
        f1.returncode == 0 and (rec.get("counts") or {}).get("agree") == 20 and not rec.get("disagreements"),
        said(f1)[-600:],
    )
    hid = evh("run", "--config", "data/configs/filing_replay_hidden_v1.yaml", "--json")
    mh = _runstore.read_json(proj, f"runs/{run_id(hid)}/metrics.json") if run_id(hid) else {}
    check(
        "the hidden replay is scored once its record exists; the default variant meets no confound (0 of 20)",
        hid.returncode == 0
        and (mh.get("faithfulness") or {}).get("faithful") is True
        and mh.get("history_confound") == {"items": 0, "of": 20},
        said(hid)[-500:] + json.dumps(mh.get("history_confound")),
    )
    cand = evh("run", "--config", "data/configs/filing_candidate_v3_hidden.yaml", "--json")
    cid = run_id(cand)
    mc = _runstore.read_json(proj, f"runs/{cid}/metrics.json") if cid else {}
    hc = mc.get("history_confound") or {}
    ids = (
        [
            json.loads(x)["item_id"]
            for x in _runstore.read_text(proj, f"runs/{cid}/confound.jsonl").splitlines()
            if x
        ]
        if cid and _runstore.is_file(proj, f"runs/{cid}/confound.jsonl")
        else []
    )
    check(
        "the candidate with the same hiding records its history confound, its ids beside the run, and says so",
        cand.returncode == 0
        and hc.get("of") == 20
        and hc.get("items")
        == 1  # d05: production filed, v3 merged it, a person closed production's issue later
        and ids == ["d05"]
        and "history confound:" in said(cand),
        said(cand)[-600:] + json.dumps(hc),
    )
    pt = evh(
        "pair-test", "--dataset-id", "filing_history_v1", "--a", "filing_candidate_v3_hidden",
        "--b", "filing_replay_hidden_v1", "--metric", "exact",
    )  # fmt: skip
    check(
        "a paired score on the candidate says its history confound",
        f"filing_candidate_v3_hidden: history confound: {hc.get('items')} of 20" in said(pt),
        said(pt)[-600:],
    )
    _runstore.unlink(proj, "configs/filing_bad_hide_v1.yaml")
    v = evh("validate")
    check(
        "validate passes",
        v.returncode == 0,
        "\n".join(x for x in v.stdout.splitlines() if "V24" in x or x.startswith("       ")),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
