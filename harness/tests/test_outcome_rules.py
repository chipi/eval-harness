#!/usr/bin/env python3
"""Outcomes as labels (RFC-019, RFC-023): the rule language, a rule label set, promoted like any, and a dataset's tags.

    python tests/test_outcome_rules.py

The rule language first (_outcome_rules). Then, in a throwaway project built from the tutorial ($0, offline): two
arms run against gold/tickets_v1; a capture's outcomes become a `rule` label set (`evh label-from-capture`); it is
promoted to silver and the runs rescored against it. With gold beside it the goal recommends from gold and shows
the silver group; with no gold the silver group is governed like any silver (ADR-0022: outcomes are no special case
once promoted). A dataset's tags group and filter it.
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
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._outcome_rules import matches  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import _runview  # noqa: E402

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

# ── a rule label set, promoted like any ────────────────────────────────────────────────────
proj = Path(tempfile.mkdtemp(prefix="evh-outrules-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-outrules")
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def said(r):
    return r.stdout + r.stderr


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
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
            "The owner's hand-written summaries are what the arms are judged by.",
            "--by",
            "owner",
        )
    )
    check("setup: the owner's gold, promoted", r.returncode == 0, said(r)[-300:])
    _runstore.write_bytes(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_bytes()
    )
    for c in ("tickets_lead1", "tickets_lead2"):
        _runstore.write_text(proj, f"systems/{c}_v1.yaml", (KIT / "systems" / f"{c}_v1.yaml").read_text())
        r = evh("run", "--system", f"{c}_v1", "--dataset", "tickets_v1", "--goal", "tickets_summary")
        check(f"setup: {c} runs", r.returncode == 0, said(r)[-300:])

    items = [it["item_id"] for it in _runstore.read_json(proj, "datasets/tickets_v1.json")["items"]]
    rows = [
        {"id": iid, "body": "x", "outcome": {"verdict": ["noise", "fixed", "open"][i % 3]}}
        for i, iid in enumerate(items)
    ]
    (proj / "out.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    evh("capture", "--importer", "jsonl", "--query", json.dumps({"path": "out.jsonl"}), "--capture", "oc")
    (proj / "map.yaml").write_text(
        "- {when: {verdict: open}, skip: true}\n- {when: {verdict: fixed}, label: file}\n- {when: {verdict: noise}, label: dismiss}\n"
    )
    r = evh(
        "label-from-capture",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "oc",
        "--map",
        "map.yaml",
        "--set",
        "outcomes",
    )
    lab = "labels/tickets_v1/outcomes"
    doc = (
        _runstore.read_json(proj, f"{lab}/labels.json")
        if _runstore.is_file(proj, f"{lab}/labels.json")
        else {}
    )
    src = doc.get("source") or {}
    check(
        "label-from-capture: skipped items have no label, the rest their rule's",
        r.returncode == 0
        and sorted(n[:-4] for n in _runstore.listdir(proj, lab) if n.endswith(".txt"))
        == sorted(i for n, i in enumerate(items) if n % 3 != 2)
        and src.get("matched") == 4
        and src.get("skipped") == 2
        and sorted({_runstore.read_text(proj, f"{lab}/{i}.txt").strip() for i in doc.get("items", {})})
        == ["dismiss", "file"],
        said(r)[-300:] + json.dumps(src),
    )
    check(
        "the set's source is rule: the capture and the mapping's hash",
        src.get("kind") == "rule" and src.get("capture") == "oc" and len(src.get("mapping_sha256", "")) == 64,
        json.dumps(src),
    )
    # A rule naming more than one right answer: a fixed one was right to file or to escalate.
    (proj / "map_two.yaml").write_text(
        "- {when: {verdict: open}, skip: true}\n- {when: {verdict: fixed}, label: [file, escalate]}\n"
        "- {when: {verdict: noise}, label: dismiss}\n"
    )
    r = evh(
        "label-from-capture",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "oc",
        "--map",
        "map_two.yaml",
        "--set",
        "outcomes_two",
    )
    two = "labels/tickets_v1/outcomes_two"
    check(
        "label-from-capture: `label: [file, escalate]` is a label accepting both",
        r.returncode == 0
        and sorted(
            {
                _runstore.read_text(proj, f"{two}/{n}").strip()
                for n in _runstore.listdir(proj, two)
                if n.endswith(".txt")
            }
        )
        == ["dismiss", '{"accept": ["escalate", "file"]}'],
        said(r)[-300:],
    )
    _runstore.rmtree(proj, two)
    (proj / "map_empty.yaml").write_text("- {when: {verdict: fixed}, label: []}\n")
    r = evh(
        "label-from-capture",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "oc",
        "--map",
        "map_empty.yaml",
        "--set",
        "outcomes_empty",
    )
    check(
        "a rule's empty label list is refused", r.returncode != 0 and "label list" in said(r), said(r)[-300:]
    )
    # The fleet's feedback 31: how far a rule set labels the dataset now, and what it waits for.
    import datetime as _dt

    ago = lambda d: (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=d)).isoformat()  # noqa: E731
    outs = [
        {"verdict": "fixed"},  # old enough: labelled now
        {"verdict": "fixed"},  # 3 days old: matures in 11 days
        {"verdict": "open"},  # skipped by design
        {},  # no verdict yet: matches no rule
        {"verdict": "noise"},  # labelled now
    ]
    ages = [30, 3, 30, 30, 30]
    recs = [
        {"id": iid, "body": "x", "created_at": ago(a), "outcome": o}
        for iid, o, a in zip(items[:5], outs, ages, strict=True)
    ]  # items[5] is not in the capture
    (proj / "out2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    evh("capture", "--importer", "jsonl", "--query", json.dumps({"path": "out2.jsonl"}), "--capture", "oc2")
    (proj / "map_age.yaml").write_text(
        "- {when: {verdict: open}, skip: true}\n- {when: {verdict: fixed}, min_age_days: 14, label: file}\n"
        "- {when: {verdict: noise}, label: dismiss}\n"
    )
    r = evh(
        "label-coverage", "--dataset-id", "tickets_v1", "--capture", "oc2", "--map", "map_age.yaml", "--json"
    )
    cov = (json.loads(r.stdout).get("result") or {}).get("values") or {} if r.returncode == 0 else {}
    by = {x["item_id"]: x for x in cov.get("by_item") or []}
    young = by.get(items[1]) or {}
    check(
        "label-coverage: labelled now, skipped, not yet mature (with its date), unmatched (and what they lack), "
        "not in the capture",
        cov.get("counts")
        == {"labelled": 2, "skipped": 1, "not_mature": 1, "unmatched": 1, "no_record": 1, "gone": 0}
        and young.get("rule") == 2
        and str(young.get("matures", ""))[:10] == ago(3 - 14)[:10]
        and young.get("today") is None
        and cov.get("lacking") == {"verdict": 1},
        said(r)[-800:],
    )
    check(
        "label-coverage: per rule, the items it takes now and when mature",
        [(x["now"], x["when_mature"]) for x in cov.get("rules") or []] == [(1, 0), (1, 1), (1, 0)],
        json.dumps(cov.get("rules")),
    )
    r = evh(
        "label-coverage", "--dataset-id", "tickets_v1", "--capture", "oc2", "--map", "map_age.yaml", "--items"
    )
    check(
        "label-coverage (text): the classes, the rules, and each item with its maturing date; nothing written",
        r.returncode == 0
        and "not yet mature" in r.stdout
        and "the unmatched lack: verdict (1)" in r.stdout
        and f"matures {ago(3 - 14)[:10]}" in r.stdout
        and not _runstore.exists(proj, "labels/tickets_v1/oc2"),
        said(r)[-800:],
    )
    name = "tickets_v1_outcomes"
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "outcomes",
        "--tier",
        "silver",
        "--name",
        name,
        "--reason",
        "What happened next ranks the arms, beside the gold.",
        "--by",
        "owner",
    )
    man = f"references/silver/{name}/manifest.json"
    m = _runstore.read_json(proj, man) if _runstore.is_file(proj, man) else {}
    check(
        "promoted to silver like any set: from the rule set, with its reason",
        r.returncode == 0
        and m.get("tier") == "silver"
        and (m.get("promoted_from") or {}).get("labels") == "outcomes"
        and m.get("caveat", "").startswith("SILVER:"),
        said(r)[-300:],
    )
    r = evh("validate")
    check("validate passes with it (V16, V19)", r.returncode == 0, said(r)[-400:])
    r = evh(
        "rescore",
        "--dataset-id",
        "tickets_v1",
        "--reference-id",
        f"silver/{name}",
    )
    check("the runs rescore against it", r.returncode == 0, said(r)[-300:])
    r = evh("goals", "--goal", "tickets_summary")
    lines = r.stdout.splitlines()
    check(
        "with gold beside it: one recommendation, from gold; the silver group shown, not recommended",
        r.returncode == 0
        and sum(ln.strip().startswith("recommended:") for ln in lines) == 1
        and "recommended: tickets_lead2_v1" in r.stdout
        and f"scored against silver/{name}" in r.stdout
        and "shown, not recommended" in r.stdout,
        r.stdout[-1500:],
    )

    # The views: a dataset's tags group and filter, and its origin is named (RFC-019 P7).
    _runstore.write_text(
        proj,
        "datasets/tickets_v1.json",
        json.dumps(
            {**_runstore.read_json(proj, "datasets/tickets_v1.json"), "tags": {"source": "support"}}, indent=2
        )
        + "\n",
    )
    r = evh("datasets", "--tag", "source=support")
    check(
        "evh datasets --tag: the datasets with that tag, with the tag shown",
        r.returncode == 0 and "tickets_v1" in r.stdout and "source=support" in r.stdout,
        said(r)[-600:],
    )
    r = evh("datasets", "--tag", "source=nothing")
    check(
        "evh datasets --tag no dataset has: none listed", r.returncode == 0 and "tickets_v1" not in r.stdout
    )
    r = evh("datasets", "--dataset-id", "tickets_v1")
    check("evh datasets --dataset-id: its tags", "tags: source=support" in r.stdout, said(r)[:500])
    r = evh("catalog")
    page = (proj / ".build" / "catalog" / "datasets.html").read_text() if r.returncode == 0 else ""
    check(
        "the catalog's datasets page: a tags column and a group-by chip per tag key",
        'data-group-by="tag-source"' in page and "source: support" in page,
        said(r)[-300:],
    )

    # With no gold, the promoted rule set is a silver like any (ADR-0022): its group recommends.
    _runstore.rmtree(proj, "references/gold")
    # (the runs' own scores go, the silver ones stay)
    for rid in _runstore.listdir(proj, "runs"):
        for key, lbl, _rec in _runview.scores_of(proj, rid):
            if lbl == "":
                _runstore.rmtree(proj, f"runs/{rid}/scores/{key}")
    r = evh("goals", "--goal", "tickets_summary")
    check(
        "NO GOLD: the promoted rule set is governed like any silver: its group recommends",
        r.returncode == 0 and f"scored against silver/{name}" in r.stdout and "recommended:" in r.stdout,
        r.stdout[-1500:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
