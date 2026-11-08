#!/usr/bin/env python3
"""Picks and the next version of a governed dataset (RFC-023 step 6, ADR-0023).

    python tests/test_picks.py

In a throwaway project ($0, offline): a governed dataset (the tutorial's six tickets) and a production one (four new
tickets, captured); picks with targets, tags and notes in the append-only list; retargeting, dropping, the waiting
list; dataset-extend with --picks and --pick, the lineage and `extended_from` it records, the picks used leaving the
list, an item already in V1 kept once, a changed file refused; labels following a picked item into V2; validate.
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
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-picks-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-picks")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


def picks():
    r = evh("picks", "--json")
    return {p["item"]: p for p in json.loads(r.stdout)["picks"]} if r.returncode == 0 else {}


try:
    if not _runstore.sqlite():
        (proj / "data").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tickets")
    check("setup: the governed dataset", r.returncode == 0, out(r)[-300:])
    new = [
        {
            "id": f"p{n}",
            "body": f"A new production ticket number {n}: something else broke.",
            "channel": "email",
            "created_at": f"2026-11-0{n}T09:00:00Z",
        }
        for n in range(1, 5)
    ]
    (proj / "prod.jsonl").write_text("".join(json.dumps(x) + "\n" for x in new))
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "prod.jsonl"}),
        "--capture",
        "prod_c1",
    )
    r = r if r.returncode else evh("dataset-from-capture", "prod_c1", "--dataset-id", "prod_v1")
    check("setup: the production dataset", r.returncode == 0, out(r)[-300:])

    # ── pick, retarget, drop, the waiting list ─────────────────────────────────────────────
    r = evh(
        "pick",
        "--dataset-id",
        "prod_v1",
        "--item",
        "p1",
        "--item",
        "p2",
        "--item",
        "p3",
        "--for",
        "tickets_v1",
        "--tag",
        "case=new",
        "--note",
        "nothing like it in v1",
        "--by",
        "owner",
    )
    w = picks()
    check(
        "pick: each item a line, with its dataset, capture, sha256, targets, tags, note and who",
        r.returncode == 0
        and sorted(w) == ["p1", "p2", "p3"]
        and w["p1"]["capture"] == "prod_c1"
        and w["p1"]["for"] == ["tickets_v1"]
        and w["p1"]["tags"] == {"case": "new"}
        and w["p1"]["note"] == "nothing like it in v1"
        and len(w["p1"]["sha256"]) == 64,
        out(r)[-300:],
    )
    evh("pick", "--dataset-id", "prod_v1", "--item", "p4")
    evh("pick", "--dataset-id", "prod_v1", "--item", "p3", "--for", "prod_v1", "--tag", "case=other")
    w = picks()
    check(
        "picking again retargets and retags (the latest line wins); a pick may have no target yet",
        w["p3"]["for"] == ["prod_v1"] and w["p3"]["tags"] == {"case": "other"} and w["p4"]["for"] == [],
        json.dumps(w)[:400],
    )
    r = evh("pick", "--dataset-id", "prod_v1", "--item", "p2", "--drop")
    check("pick --drop: off the waiting list", r.returncode == 0 and "p2" not in picks(), out(r)[-200:])
    r = evh("pick", "--dataset-id", "prod_v1", "--item", "p2", "--drop")
    check("pick --drop of an item not waiting is refused", refused(r, "not waiting"), out(r)[-200:])
    lines = _runstore.read_text(proj, "picks.jsonl").splitlines()
    check(
        "the list is append-only: every action is a line (a refused one writes none)",
        len(lines) == 6,
        str(len(lines)),
    )
    r = evh("pick", "--dataset-id", "prod_v1", "--item", "no_such")
    check("pick: an item not in the dataset is refused", refused(r, "not in prod_v1"), out(r)[-200:])
    r = evh("pick", "--dataset-id", "prod_v1", "--item", "p1", "--for", "no_such_dataset")
    check("pick: a target that is not a dataset is refused", refused(r, "no such dataset"), out(r)[-200:])
    r = evh("picks", "--for", "tickets_v1")
    check(
        "picks --for: what waits for it, where it came from, its labels",
        "tickets_v1: 1 pick(s) waiting" in r.stdout
        and "p1  from prod_v1 (capture prod_c1)" in r.stdout
        and "none yet" in r.stdout,
        r.stdout[-400:],
    )
    r = evh("picks")
    check(
        "picks: a pick with no target yet is listed as such",
        "no target yet: 1 pick(s) waiting" in r.stdout,
        r.stdout[-400:],
    )

    # ── a label on a picked item follows it ────────────────────────────────────────────────
    (proj / "sheet.csv").write_text("item_id,label\np1,needs-engineering\n")
    r = evh("label-import", "sheet.csv", "--dataset-id", "prod_v1", "--set", "owner_p", "--by", "owner")
    check("setup: the owner labels a picked item", r.returncode == 0, out(r)[-200:])

    # ── dataset-extend ─────────────────────────────────────────────────────────────────────
    r = evh("dataset-extend", "tickets_v1", "--dataset-id", "tickets_v2", "--picks")
    v2 = _runstore.read_json(proj, "datasets/tickets_v2.json") if r.returncode == 0 else {}
    ids = [it["item_id"] for it in v2.get("items", [])]
    check(
        "dataset-extend --picks: V1's items and the picks waiting for it, where each came from recorded",
        len(ids) == 7
        and "p1" in ids
        and v2["extended_from"]
        == {
            "dataset": "tickets_v1",
            "picks": [
                {"item_id": "p1", "from": "prod_v1", "capture": "prod_c1", "note": "nothing like it in v1"}
            ],
        }
        and _runstore.is_file(proj, "sources/tickets_v2/p1.txt"),
        out(r)[-400:],
    )
    check(
        "the picks used leave the waiting list",
        "p1" not in picks() and "p3" in picks(),
        json.dumps(picks())[:200],
    )
    r = evh("labels", "--dataset-id", "tickets_v2", "--json")
    cov = {s["set"]: s["items"] for s in json.loads(r.stdout)["sets"]} if r.returncode == 0 else {}
    check("a picked item's labels follow it into V2", cov.get("owner_p") == ["p1"], r.stdout[-300:])
    r = evh("dataset-extend", "tickets_v2", "--dataset-id", "tickets_v3", "--pick", "prod_v1:p4")
    v3 = _runstore.read_json(proj, "datasets/tickets_v3.json") if r.returncode == 0 else {}
    check(
        "dataset-extend --pick DATASET:ITEM: one pick, whatever its target",
        [p["item_id"] for p in v3.get("extended_from", {}).get("picks", [])] == ["p4"]
        and len(v3.get("items", [])) == 8,
        out(r)[-300:],
    )
    r = evh("dataset-extend", "tickets_v2", "--dataset-id", "tickets_v2", "--picks")
    check("dataset-extend: an existing dataset is never overwritten", refused(r, "exists"), out(r)[-200:])
    r = evh("dataset-extend", "tickets_v1", "--dataset-id", "tickets_v4", "--pick", "no_such")
    check("dataset-extend --pick of an item not waiting is refused", refused(r, "not waiting"), out(r)[-200:])
    _runstore.write_text(proj, "sources/prod_v1/p3.txt", "changed after it was picked")
    r = evh("dataset-extend", "tickets_v1", "--dataset-id", "tickets_v5", "--pick", "p3")
    check(
        "dataset-extend: a picked item whose file changed since is refused",
        refused(r, "not the one picked") and not _runstore.exists(proj, "datasets/tickets_v5.json"),
        out(r)[-200:],
    )
    r = evh("validate")
    check(
        "validate: the versions made from picks pass (schema, lineage)",
        "V1" in out(r) and "dataset" in out(r) and "FAIL V1 " not in out(r) and "FAIL V2 " not in out(r),
        out(r)[-600:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
