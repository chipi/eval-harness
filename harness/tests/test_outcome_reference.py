#!/usr/bin/env python3
"""References from outcomes (RFC-019 P4): the rule language, the command, and the route a goal decides on.

In a throwaway project built from the tutorial ($0, offline): two arms run against gold/tickets_v1;
an outcome reference is written as silver/tickets_v1_outcomes and the runs rescored against it. The
goal then shows EXACTLY ONE recommendation, from gold, and the outcome group beside it, shown and not
recommended (ADR-0020), on the command and on the catalog's goal page alike.

    python tests/test_outcome_reference.py
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
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.reference_from_outcomes import matches  # noqa: E402

KIT = HERE.parent / "tutorial"

# ── the rule language ──────────────────────────────────────────────────────────────────────
out = {"verdict": "fixed", "days": -3, "issue": 12, "gone": None, "flag": True}
for rule, age, want, label in (
    ({"when": {"verdict": "fixed"}}, None, True, "when: equal"),
    ({"when": {"verdict": ["noise", "fixed"]}}, None, True, "when: any of a list"),
    ({"when": {"verdict": "noise"}}, None, False, "when: different"),
    ({"when": {"missing": "x"}}, None, False, "when: a missing field never matches"),
    ({"unless": {"verdict": "fixed"}}, None, False, "unless: holds, so the rule fails"),
    ({"unless": {"verdict": "noise"}}, None, True, "unless: does not hold"),
    ({"exists": ["issue"]}, None, True, "exists: present"),
    ({"exists": ["gone"]}, None, False, "exists: null is not present"),
    ({"absent": ["gone", "missing"]}, None, True, "absent: null or missing"),
    ({"range": {"days": {"min": -5, "max": 0}}}, None, True, "range: a signed value within bounds"),
    ({"range": {"days": {"min": 0}}}, None, False, "range: below the minimum"),
    ({"range": {"verdict": {"min": 0}}}, None, False, "range: not a number never matches"),
    ({"range": {"flag": {"min": 0}}}, None, False, "range: a boolean is not a number"),
    ({"min_age_days": 14}, 20.0, True, "min_age_days: old enough"),
    ({"min_age_days": 14}, 3.0, False, "min_age_days: too young"),
    ({"min_age_days": 14}, None, False, "min_age_days: no time, no match"),
):
    check(f"rule {label}", matches(rule, out, age) == want)

# ── the command and the route ──────────────────────────────────────────────────────────────
proj = Path(tempfile.mkdtemp(prefix="evh-outref-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-outref")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def said(r):
    return r.stdout + r.stderr


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    for c in ("tickets_lead1", "tickets_lead2"):
        cfg = data / "configs" / f"{c}.yaml"
        cfg.write_text((KIT / "configs" / f"{c}.yaml").read_text() + "goal: tickets_summary\n")
        r = evh("experiment-run", "--config", str(cfg))
        check(f"setup: {c} runs", r.returncode == 0, said(r)[-300:])

    items = [it["item_id"] for it in json.loads((data / "datasets" / "tickets_v1.json").read_text())["items"]]
    rows = [
        {"id": iid, "body": "x", "outcome": {"verdict": ["noise", "fixed", "open"][i % 3]}}
        for i, iid in enumerate(items)
    ]
    (proj / "out.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    evh("capture", "--importer", "jsonl", "--query", json.dumps({"path": "out.jsonl"}), "--capture", "oc")
    (proj / "map.yaml").write_text(
        "- {when: {verdict: open}, skip: true}\n- {when: {verdict: fixed}, label: file}\n- {when: {verdict: noise}, label: dismiss}\n"
    )

    r = evh("reference-from-outcomes", "--dataset-id", "tickets_v1", "--capture", "oc", "--map", "map.yaml")
    check(
        "the default name, gold/<dataset>, is refused when gold exists: never overwritten",
        r.returncode != 0 and "never overwritten" in said(r),
        said(r)[-300:],
    )
    name = "silver/tickets_v1_outcomes"
    r = evh(
        "reference-from-outcomes",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "oc",
        "--map",
        "map.yaml",
        "--name",
        name,
    )
    ref = data / "references" / "silver" / "tickets_v1_outcomes"
    man = json.loads((ref / "manifest.json").read_text()) if (ref / "manifest.json").is_file() else {}
    fo = man.get("from_outcomes") or {}
    check(
        "the outcome reference: skipped items have no text, the rest their label",
        r.returncode == 0
        and sorted(p.stem for p in ref.glob("*.txt")) == sorted(i for n, i in enumerate(items) if n % 3 != 2)
        and fo.get("matched") == 4
        and fo.get("skipped") == 2
        and fo.get("labels") == {"dismiss": 2, "file": 2},
        said(r)[-300:] + json.dumps(fo),
    )
    check(
        "its manifest records the capture, the mapping's hash, and its own caveat",
        fo.get("capture") == "oc"
        and len(fo.get("mapping_sha256", "")) == 64
        and man.get("caveat", "").startswith("OUTCOME:")
        and man.get("tier") == "silver",
        man,
    )
    r = evh(
        "reference-from-outcomes",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "oc",
        "--map",
        "map.yaml",
        "--name",
        name,
    )
    check("a second write to the same name is refused", r.returncode != 0 and "never overwritten" in said(r))
    r = evh("validate")
    check(
        "validate passes with it (V16 checks its texts against the manifest)",
        r.returncode == 0,
        said(r)[-400:],
    )

    r = evh("rescore", "--dataset-id", "tickets_v1", "--reference-id", name, "--out", "data/runs-outcomes")
    check("the runs rescore against it", r.returncode == 0, said(r)[-300:])
    r = evh("goals", "--goal", "tickets_summary")
    lines = r.stdout.splitlines()
    check(
        "THE ROUTE: the goal shows exactly one recommendation, from gold",
        r.returncode == 0
        and sum(ln.strip().startswith("recommended:") for ln in lines) == 1
        and "recommended: tickets_lead2_v1" in r.stdout,
        r.stdout[-1500:],
    )
    check(
        "THE ROUTE: the outcome group is beside it, shown and not recommended",
        "scored against silver/tickets_v1_outcomes" in r.stdout and "shown, not recommended" in r.stdout,
        r.stdout[-1500:],
    )
    r = evh("catalog")
    page = (
        (proj / ".build" / "catalog" / "g" / "tickets_summary.html").read_text() if r.returncode == 0 else ""
    )
    check(
        "THE ROUTE: the catalog's goal page says the same: one Recommended, the outcome group shown",
        page.count("Recommended: tickets_") == 1 and "Shown, not recommended" in page,
        said(r)[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
