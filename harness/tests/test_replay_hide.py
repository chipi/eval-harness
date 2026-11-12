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
P2: `evh periods` numbers the code record's deployed periods; `evh period-compare` puts a period's production, its
code as it ran and the candidate side by side, and says when the as-run replay disagrees with production there.
X2: a rule label set keeps a label only where the replay at the recorded versions reproduces production's decision;
a version whose deployment was dated by commit time counts as approximate.
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
    # The fleet's beta (F7): the adapter marks only the items where production acted; the score's mean was taken over
    # those (5 of 34) while the note said 5 of 287. One denominator: every item of the run.
    check(
        "the history confound's score and its note count the same items: an item the adapter left unmarked is 0",
        (mc.get("scores") or {}).get("history_confound") == round(1 / 20, 6),
        json.dumps((mc.get("scores") or {}).get("history_confound")),
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

    # ── P2: a past period at its own code, beside the candidate ───────────────────────────────────────────────────
    per = evh(
        "periods", "--model", "toy_filing", "--config", "data/configs/filing_replay_hidden_v1.yaml", "--json"
    )
    ps = values(per).get("periods") or []
    check(
        "periods: the code record's three deployed periods, numbered, with the items of the replay's dataset in each",
        per.returncode == 0
        and [x["period"] for x in ps] == [1, 2, 3]
        and [x["items"] for x in ps] == [8, 6, 6],
        said(per)[-500:],
    )
    PC = [
        "period-compare",
        "--production",
        "filing_production_v1",
        "--period",
        "1",
        "--metric",
        "exact",
        "--json",
    ]
    pc = evh(
        *PC,
        "--config",
        "data/configs/filing_replay_hidden_v1.yaml",
        "--candidate",
        "filing_candidate_v3_hidden",
    )
    pv = values(pc)
    check(
        "period-compare: period 1's eight items; the replay agrees with production there, so it counts; production "
        "and the code that ran score alike, 7 of 8 (gold fixes the info alert), the candidate beside them",
        pc.returncode == 0
        and pv.get("items") == 8
        and pv.get("counts") is True
        and pv.get("as_run") == 0.875
        and pv.get("production") == 0.875
        and isinstance(pv.get("candidate"), float)
        and pv.get("delta") is not None,
        said(pc)[-600:],
    )
    check(
        "period-compare: the candidate's history confound is counted over the period's items, not the run's 20 "
        "(the fleet's beta: 5 of 287 beside a comparison of 52)",
        "filing_candidate_v3_hidden: history confound: 1 of 8" in said(pc)
        and (pv.get("history_confound") or {}).get("filing_candidate_v3_hidden") == {"items": 1, "of": 8},
        said(pc)[-600:],
    )
    # The fleet's beta (F8): faithfulness --production takes a run id; the same id here was refused ("no run of").
    prod_run = sorted(n for n in _runstore.listdir(proj, "runs") if n.startswith("filing_production_v1_"))[-1]
    pc_id = evh(
        *[prod_run if x == "filing_production_v1" else x for x in PC],
        "--config", "data/configs/filing_replay_hidden_v1.yaml", "--candidate", "filing_candidate_v3_hidden",
    )  # fmt: skip
    check(
        "period-compare --production takes a run id too, with the same answer as its config_id",
        pc_id.returncode == 0 and values(pc_id).get("production") == pv.get("production"),
        said(pc_id)[-400:],
    )
    bad_pc = evh(
        *PC,
        "--config",
        "data/configs/filing_candidate_v3_hidden.yaml",
        "--candidate",
        "filing_replay_hidden_v1",
    )
    check(
        "period-compare: a 'code that ran' that disagrees with production on the period (v3 merges d05) does not count",
        bad_pc.returncode == 0 and values(bad_pc).get("counts") is False and "DOES NOT COUNT" in said(bad_pc),
        said(bad_pc)[-500:],
    )

    # ── X2: a label counts only where the replay at the recorded versions reproduces production's decision ─────────
    import yaml

    rec = yaml.safe_load(_runstore.read_text(proj, "models/toy_filing.yaml"))
    # The fleet's beta (F9): dated_by on a version, not on its deployment, was accepted and dated nothing.
    wrong = {**rec, "versions": [{**rec["versions"][0], "dated_by": "commit"}, *rec["versions"][1:]]}
    _runstore.write_text(proj, "models/toy_filing.yaml", yaml.safe_dump(wrong, sort_keys=False))
    w = evh("periods", "--model", "toy_filing")
    check(
        "a code record with dated_by on a version (not its deployment) is refused, saying where it goes",
        w.returncode != 0 and "dated_by" in said(w) and "versions[].deployed[].dated_by" in said(w),
        said(w)[-400:],
    )
    rec["versions"][0]["deployed"][0]["dated_by"] = (
        "commit"  # the host's pull time no longer recorded: approximate
    )
    _runstore.write_text(proj, "models/toy_filing.yaml", yaml.safe_dump(rec, sort_keys=False))
    (proj / "lab.yaml").write_text("- {absent: [no_such_field], label: decided}\n")
    LAB = [
        "label-from-capture",
        "--dataset-id",
        "filing_history_v1",
        "--capture",
        "filing_prod",
        "--map",
        "lab.yaml",
    ]
    x = evh(*LAB, "--set", "lab_hidden", "--reproduced-by", run_id(hid), "--production", prod_id)
    doc = (
        _runstore.read_json(proj, "labels/filing_history_v1/lab_hidden/labels.json")
        if x.returncode == 0
        else {}
    )
    rb = (doc.get("source") or {}).get("reproduced_by") or {}
    kinds = sorted({r.get("reproduced") for r in (doc.get("items") or {}).values()})
    check(
        "X2: the replay reproduces production on all 20: every label kept, the first period's 8 (its deployment dated "
        "by commit time) counted as approximate, apart from the 12 dated by the pull",
        x.returncode == 0
        and (rb.get("reproduced"), rb.get("approximate"), rb.get("not_reproduced")) == (20, 8, 0)
        and kinds == ["approximate", "yes"],
        said(x)[-500:] + json.dumps(rb),
    )
    x2 = evh(*LAB, "--set", "lab_cand", "--reproduced-by", cid, "--production", prod_id)
    doc2 = (
        _runstore.read_json(proj, "labels/filing_history_v1/lab_cand/labels.json")
        if x2.returncode == 0
        else {}
    )
    rb2 = (doc2.get("source") or {}).get("reproduced_by") or {}
    check(
        "X2: by a replay that does not reproduce production everywhere (v3 merges d05), those labels are left out, counted",
        x2.returncode == 0
        and rb2.get("not_reproduced", 0) >= 1
        and "d05" in (rb2.get("left_out") or [])
        and doc2.get("n_items") == 20 - rb2.get("not_reproduced", 0),
        said(x2)[-500:] + json.dumps(rb2),
    )
    per2 = evh("periods", "--model", "toy_filing", "--json")
    check(
        "periods says how each period was dated: the first by commit time (approximate)",
        [x.get("dated_by") for x in values(per2).get("periods") or []][:1] == ["commit"]
        and "approximate" in said(per2),
        said(per2)[-400:],
    )
    evh("catalog")
    page = next((proj / ".build" / "catalog" / "a").glob("*filing_candidate_v3_hidden*.html"), None)
    check(
        "the catalog's arm page marks the candidate's history confound",
        page is not None and "history confound" in page.read_text() and "1 of 20 item(s)" in page.read_text(),
        str(page),
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
