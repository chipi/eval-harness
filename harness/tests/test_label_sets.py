#!/usr/bin/env python3
"""Label sets (RFC-023 step 2): what is right for an item, and who said it.

    python tests/test_label_sets.py

In a throwaway project built from the tutorial ($0, offline): a run's outputs become a `model` set, with the
refusals reference-create has; a sheet of the items to label (unlabelled, all, where two runs disagree, chosen
ones, with a proposal) and its import as a `person` set (`yes` takes the proposal, notes kept); a set is never
edited; a capture's outcomes become a `rule` set by the mapping; `evh labels` lists the sets, their coverage and
how often two agree; and labels follow an item by its sha256 into another dataset holding it.
"""

import csv
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

proj = Path(tempfile.mkdtemp(prefix="evh-labels-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-labels")
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


LABELS = proj / "data" / "labels"

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copytree(KIT / "production", proj / "tutorial" / "production")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, out(r)[-300:])
    (data / "goals").mkdir()
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    for arm in ("lead1", "author"):
        cfg = data / "configs" / f"tickets_{arm}.yaml"
        cfg.write_text((KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n")
        r = evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    author = next(p.name for p in (data / "runs").glob("tickets_author_v1_*"))
    lead = next(p.name for p in (data / "runs").glob("tickets_lead1_v1_*"))

    # ── label-from-run ──────────────────────────────────────────────────────────────────────
    (proj / "author_prompt.txt").write_text("Summarise the ticket for the support lead.\n")
    r = evh("label-from-run", "--run", author, "--set", "author_v1", "--guideline", "author_prompt.txt")
    doc = (
        json.loads((LABELS / "tickets_v1" / "author_v1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-from-run: the run's outputs as a model set, its source the run, its guideline hashed",
        doc.get("n_items") == 6
        and doc["source"]["kind"] == "model"
        and doc["source"]["run_id"] == author
        and doc["guideline"]["path"] == "author_prompt.txt"
        and len(doc["guideline"]["sha256"]) == 64
        and all(len(v["item_sha256"]) == 64 for v in doc["items"].values())
        and (LABELS / "tickets_v1" / "author_v1" / "t01_login.txt").read_text()
        == (data / "runs" / author / "outputs" / "t01_login.txt").read_text().strip() + "\n",
        out(r)[-300:],
    )
    r = evh("label-from-run", "--run", author, "--set", "author_v1")
    check("a set is never edited: the same name again is refused", refused(r, "never edited"), out(r)[-300:])
    r = evh("label-from-run", "--run", author, "--set", "../escape")
    check("a set's name cannot leave data/labels/", refused(r, "lowercase"), out(r)[-200:])
    r = evh("label-from-run", "--run", "no_such_run", "--set", "x")
    check("label-from-run: an unknown run is refused", refused(r, "no finished run"), out(r)[-200:])

    # ── label-sheet ───────────────────────────────────────────────────────────────────────
    def sheet(name, *args):
        p = proj / name
        r = evh("label-sheet", "--dataset-id", "tickets_v1", "--out", name, *args)
        rows = list(csv.DictReader(p.open(encoding="utf-8"))) if r.returncode == 0 else []
        return r, rows

    r, rows = sheet("s_unlabelled.csv")
    check(
        "label-sheet: by default only the unlabelled items (the model set covers all six)",
        r.returncode == 0 and rows == [],
        out(r)[-200:],
    )
    r, rows = sheet("s_all.csv", "--items", "all", "--runs", f"{lead},{author}", "--propose", "author_v1")
    check(
        "label-sheet --items all: every item, the start of the item, each run's decision, the proposal, empty label",
        len(rows) == 6
        and rows[0]["item"]
        and rows[0][f"decided: {lead}"]
        and rows[0]["proposal"]
        == (LABELS / "tickets_v1" / "author_v1" / f"{rows[0]['item_id']}.txt").read_text().strip()
        and rows[0]["label"] == "",
        out(r)[-300:],
    )
    r, rows = sheet("s_dis.csv", "--items", "disagree", "--runs", f"{lead},{author}")
    lo = {p.stem: p.read_text().strip() for p in (data / "runs" / lead / "outputs").glob("*.txt")}
    au = {p.stem: p.read_text().strip() for p in (data / "runs" / author / "outputs").glob("*.txt")}
    check(
        "label-sheet --items disagree: exactly the items the two runs decided differently",
        r.returncode == 0
        and sorted(x["item_id"] for x in rows) == sorted(i for i in lo if lo[i] != au.get(i)),
        out(r)[-300:],
    )
    r, rows = sheet("s_pick.csv", "--item", "t02_invoice", "--item", "t04_api", "--runs", "tickets_lead1_v1")
    check(
        "label-sheet --item: exactly those; a config names its latest run",
        [x["item_id"] for x in rows] == ["t02_invoice", "t04_api"],
        out(r)[-300:],
    )
    r, _ = sheet("s_pick.csv", "--items", "all")
    check("label-sheet: an existing sheet is never overwritten", refused(r, "not overwritten"), out(r)[-200:])
    r, _ = sheet("s_bad.csv", "--items", "disagree", "--runs", lead)
    check("label-sheet --items disagree needs two runs", refused(r, "two runs"), out(r)[-200:])

    # ── label-import ──────────────────────────────────────────────────────────────────────
    filled = proj / "filled.csv"
    with (proj / "s_all.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[0]["label"], rows[0]["note"] = "needs-engineering", "a real bug"
    rows[1]["label"] = "yes"
    rows[2]["label"] = "support-only"
    with filled.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    r = evh("label-import", "filled.csv", "--dataset-id", "tickets_v1", "--set", "owner_v1", "--by", "owner")
    doc = (
        json.loads((LABELS / "tickets_v1" / "owner_v1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-import: the filled rows as a person set; `yes` takes the proposal; a note kept; empty rows left out",
        doc.get("n_items") == 3
        and doc["source"]
        == {
            "kind": "person",
            "by": "owner",
            "sheet": "filled.csv",
            "sheet_sha256": doc["source"].get("sheet_sha256"),
        }
        and (LABELS / "tickets_v1" / "owner_v1" / f"{rows[1]['item_id']}.txt").read_text().strip()
        == rows[1]["proposal"]
        and doc.get("notes") == {rows[0]["item_id"]: "a real bug"},
        out(r)[-300:],
    )
    (proj / "bad.csv").write_text("id,answer\nt01_login,x\n")
    r = evh("label-import", "bad.csv", "--dataset-id", "tickets_v1", "--set", "bad_v1", "--by", "owner")
    check(
        "label-import: a file without item_id and label is refused",
        refused(r, "item_id and label"),
        out(r)[-200:],
    )
    (proj / "ghost.csv").write_text("item_id,label\nno_such_item,x\n")
    r = evh("label-import", "ghost.csv", "--dataset-id", "tickets_v1", "--set", "ghost_v1", "--by", "owner")
    check(
        "label-import: an item not in the dataset is refused", refused(r, "not in tickets_v1"), out(r)[-200:]
    )

    # ── labels ───────────────────────────────────────────────────────────────────────────
    r = evh("labels", "--dataset-id", "tickets_v1", "--json")
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    pair: dict = next(
        (
            p
            for p in v.get("agreement", [])
            if {p["a"], p["b"]} == {"tickets_v1/author_v1", "tickets_v1/owner_v1"}
        ),
        {},
    )
    agree = sum(
        (LABELS / "tickets_v1" / "owner_v1" / f"{i}.txt").read_text()
        == (LABELS / "tickets_v1" / "author_v1" / f"{i}.txt").read_text()
        for i in json.loads((LABELS / "tickets_v1" / "owner_v1" / "labels.json").read_text())["items"]
    )
    check(
        "labels --dataset-id: each set's coverage, and how often two agree on the items both label",
        sorted((s["set"], len(s["items"])) for s in v.get("sets", [])) == [("author_v1", 6), ("owner_v1", 3)]
        and pair.get("both") == 3
        and pair.get("agree") == agree,
        r.stdout[-400:],
    )
    r = evh("labels")
    check(
        "labels: every set, with its source",
        "tickets_v1/owner_v1: person · owner" in r.stdout and "model · " in r.stdout,
        r.stdout[-300:],
    )

    # ── labels follow the item ─────────────────────────────────────────────────────────────
    r = evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v2",
        "--source-dir",
        "tutorial/tickets",
        "--from",
        "tickets_v1",
    )
    r2 = evh("labels", "--dataset-id", "tickets_v2", "--json")
    v2 = json.loads(r2.stdout) if r2.returncode == 0 else {}
    check(
        "labels follow the item: a new version with the same items has v1's labels",
        r.returncode == 0
        and sorted((s["set"], len(s["items"])) for s in v2.get("sets", []))
        == [("author_v1", 6), ("owner_v1", 3)],
        out(r)[-200:] + r2.stdout[-300:],
    )
    edited = proj / "tutorial" / "tickets_edited"
    shutil.copytree(proj / "tutorial" / "tickets", edited)
    first = sorted(edited.iterdir())[0]
    first.write_text(first.read_text() + "\nEdited.\n")
    evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v3",
        "--source-dir",
        "tutorial/tickets_edited",
        "--from",
        "tickets_v1",
    )
    r = evh("labels", "--dataset-id", "tickets_v3", "--json")
    v3 = json.loads(r.stdout) if r.returncode == 0 else {}
    cover = {s["set"]: s["items"] for s in v3.get("sets", [])}
    check(
        "an edited item's labels do not follow it",
        len(cover.get("author_v1", [])) == 5 and first.stem not in cover.get("author_v1", []),
        r.stdout[-300:],
    )

    # ── label-from-capture ─────────────────────────────────────────────────────────────────
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "tutorial/production/desk_export.jsonl"}),
        "--capture",
        "desk_c1",
    )
    r = r if r.returncode else evh("dataset-from-capture", "desk_c1", "--dataset-id", "desk_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-from-capture",
            "--dataset-id",
            "desk_v1",
            "--capture",
            "desk_c1",
            "--map",
            "tutorial/production/outcomes.yaml",
            "--set",
            "outcomes_c1",
        )
    )
    doc = (
        json.loads((LABELS / "desk_v1" / "outcomes_c1" / "labels.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "label-from-capture: the mapping's labels as a rule set, the capture and the mapping hashed, the counts",
        doc.get("n_items") == 5
        and doc["source"]["kind"] == "rule"
        and doc["source"]["capture"] == "desk_c1"
        and doc["source"]["skipped"] == 1
        and len(doc["source"]["mapping_sha256"]) == 64
        and doc["guideline"]["path"].endswith("outcomes.yaml"),
        out(r)[-300:],
    )

    # ── reference-promote (step 3): a reference is labels you promote ─────────────────────────
    REF = proj / "data" / "references"
    reason = "the owner's labels of three tickets, for this test"
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    m = json.loads((REF / "gold" / "tickets_v1" / "manifest.json").read_text()) if r.returncode == 0 else {}
    owner_ids = sorted(json.loads((LABELS / "tickets_v1" / "owner_v1" / "labels.json").read_text())["items"])
    check(
        "reference-promote: the set's labels as the dataset's gold, recording the set, its source, the reason and who",
        sorted(p.stem for p in (REF / "gold" / "tickets_v1").glob("*.txt")) == owner_ids
        and m.get("tier") == "gold"
        and m["promoted_from"]
        == {"labels": "owner_v1", "dataset_id": "tickets_v1", "source": m["promoted_from"]["source"]}
        and m["promoted_from"]["source"]["kind"] == "person"
        and m["reason"] == reason
        and m["promoted_by"] == "owner"
        and "promoted as gold from tickets_v1/owner_v1 (person · owner)" in m["caveat"]
        and "authored_by" not in m,
        out(r)[-300:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check("reference-promote: never overwrites a reference", refused(r, "never overwritten"), out(r)[-200:])
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--tier",
        "silver",
        "--name",
        "x1",
        "--by",
        "owner",
        "--reason",
        "fine",
    )
    check("reference-promote: a reason is a sentence", refused(r, "a sentence"), out(r)[-200:])
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "no_such_set",
        "--tier",
        "silver",
        "--name",
        "x2",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote: an unknown set is refused",
        refused(r, "no labels of tickets_v1/no_such_set"),
        out(r)[-200:],
    )
    unlabelled = next(i for i in au if i not in owner_ids)
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_v1",
        "--items",
        unlabelled,
        "--tier",
        "silver",
        "--name",
        "x3",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote --items: an item the set does not label is refused",
        refused(r, "has no label for"),
        out(r)[-200:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "author_v1",
        "--tier",
        "silver",
        "--name",
        "tickets_v1_author",
        "--by",
        "owner",
        "--reason",
        "the author model's answers, to rank the arms",
    )
    m = (
        json.loads((REF / "silver" / "tickets_v1_author" / "manifest.json").read_text())
        if r.returncode == 0
        else {}
    )
    check(
        "a model set promoted keeps who authored it (the fingerprint hashes it): its config, model and run",
        m.get("authored_by") == "tickets_author_v1" and (m.get("from_run") or {}).get("run_id") == author,
        out(r)[-300:] + json.dumps(m)[:300],
    )
    r = evh(
        "rescore",
        "--dataset-id",
        "tickets_v1",
        "--reference-id",
        "silver/tickets_v1_author",
        "--out",
        "data/runs-author",
    )
    r = (
        r
        if r.returncode
        else subprocess.run(
            [sys.executable, str(HERE / "cli.py"), "leaderboard", "--dataset-id", "tickets_v1"],
            cwd=proj,
            env={**env, "EVAL_RUNS_DIR": "data/runs-author"},
            capture_output=True,
            text=True,
        )
    )
    check(
        "scored against it, the author arm is marked as graded against its own answers",
        r.returncode == 0
        and any(
            line.strip().startswith("tickets_author_v1") and "*" in line for line in r.stdout.splitlines()
        ),
        out(r)[-500:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v2",
        "--labels",
        "tickets_v1/owner_v1",
        "--tier",
        "gold",
        "--by",
        "owner",
        "--reason",
        reason,
    )
    check(
        "reference-promote from a set on another dataset: labels follow the item",
        r.returncode == 0
        and sorted(p.stem for p in (REF / "gold" / "tickets_v2").glob("*.txt")) == owner_ids,
        out(r)[-300:],
    )

    # ── scoring against labels (step 4) ───────────────────────────────────────────────────
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "author_v1")
    lab_dir = data / "runs-labels-tickets_v1-author_v1"
    ms = (
        [json.loads(p.read_text()) for p in sorted(lab_dir.glob("*/metrics.json"))]
        if r.returncode == 0
        else []
    )
    check(
        "rescore --labels: every run scored against the set, beside the runs, never in the re-score goals read",
        len(ms) == 2
        and all(
            m["fingerprint"]["data"]["reference_id"] == "labels/tickets_v1/author_v1"
            and m["fingerprint"]["data"]["reference_tier"] == "labels"
            and len(m["fingerprint"]["data"]["references_sha256"] or "") == 64
            for m in ms
        )
        and not (data / "runs-rescored").exists(),
        out(r)[-300:],
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "tickets_v2/owner_v1")
    check(
        "rescore --labels: a set on another dataset is refused (promote it, or label this one)",
        refused(r, "a set on tickets_v2"),
        out(r)[-300:],
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "no_such_set")
    check("rescore --labels: an unknown set is refused", refused(r, "no label set at"), out(r)[-200:])
    r = subprocess.run(
        [
            sys.executable,
            str(HERE / "cli.py"),
            "experiment-run",
            "--config",
            "data/configs/tickets_lead1.yaml",
            "--labels",
            "author_v1",
        ],
        cwd=proj,
        env={**env, "EVAL_RUNS_DIR": "data/runs-labelrun"},
        capture_output=True,
        text=True,
    )
    run_m: dict = next(
        (json.loads(p.read_text()) for p in (data / "runs-labelrun").glob("*/metrics.json")), {}
    )
    check(
        "experiment-run --labels: the arm run against the label set, which the run records",
        r.returncode == 0
        and "the label set labels/tickets_v1/author_v1" in out(r)
        and run_m.get("reference_tier") == "labels"
        and run_m["fingerprint"]["data"]["reference_id"] == "labels/tickets_v1/author_v1",
        out(r)[-300:],
    )
    shutil.rmtree(data / "runs-labelrun", ignore_errors=True)
    r = evh("goals", "--goal", "tickets_summary")
    group = (
        out(r).split("labels/tickets_v1/author_v1", 1)[1] if "labels/tickets_v1/author_v1" in out(r) else ""
    )
    check(
        "the goal groups the arms scored against the set, flags the arm that made its labels, recommends another",
        r.returncode == 0
        and group
        and "[recommended]" in group.split("\n\n", 1)[0]
        and not any(
            "tickets_author_v1" in line and "[recommended]" in line
            for line in group.split("\n\n", 1)[0].splitlines()
        ),
        out(r)[-1500:],
    )

    # ── V19: a set's labels are the ones it recorded ──────────────────────────────────────────
    r = evh("validate")
    check(
        "validate V19: every label set matches its hashes",
        "V19 label sets" in out(r) and "FAIL V19" not in out(r),
        out(r)[-400:],
    )
    (LABELS / "tickets_v1" / "owner_v1" / f"{rows[0]['item_id']}.txt").write_text("edited by hand\n")
    r = evh("validate")
    check(
        "validate V19: an edited label fails",
        r.returncode != 0 and "FAIL V19" in out(r) and "never edited" in out(r),
        out(r)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
