#!/usr/bin/env python3
"""`evh inspect --crosstab` and `--items-out`, on the committed triage runs ($0, offline).

    python tests/test_inspect_crosstab.py

The crosstab counts a run's items by two of their scores, per group of a recorded field (here `_meta.gates`, whose
dismiss gate is a part of a compound string: `--group-match`). On the triage baseline the dismiss gate downgraded 20
dismissals: 12 had been false dismissals (the model's dismissal against a label that is not dismiss), 8 had been right
dismissals that the gate turned into a false alarm. `--items-out` reads the same items with each run's whole output.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation_harness._check import check, summary  # noqa: E402

CLI = ROOT / "scripts" / "cli.py"
BASE = "triage_baseline_pro_v1"
OTHER = "triage_deepseek_41flash_v1"
GATE = ("--group", "_meta.gates", "--group-match", r"d:(n/a|[^/]+)")
DOWN = "downgraded (no corroboration)"
env = {k: v for k, v in os.environ.items() if not k.startswith(("EVAL_", "EVH_"))}


def evh(*args, public=False):
    e = dict(env, EVH_PUBLIC="1") if public else env
    return subprocess.run(
        [sys.executable, str(CLI), "inspect", *args], cwd=ROOT, env=e, capture_output=True, text=True
    )


def js(*args):
    r = evh(*args, "--json")
    return r, (json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {})


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in r.stderr and text in r.stderr


def cell(group, a, b):
    return next((c for c in group["cells"] if (c["a"], c["b"]) == (a, b)), {"n": 0, "item_ids": []})


def groups_of(ct):
    return {g["group"]: g for g in ct["groups"]}


# ── the crosstab ─────────────────────────────────────────────────────────────────────────────────
r, v = js("--runs", BASE, "--crosstab", "model_false_dismiss,false_dismiss", *GATE)
check("crosstab: runs", r.returncode == 0, r.stderr[-300:])
g = groups_of(v["crosstab"])
check("crosstab: a group per gate outcome", set(g) == {DOWN, "n/a", "passed"}, sorted(g))
saved = cell(g[DOWN], "1", "0")
check(
    "crosstab: the downgrades that saved a false dismissal are 12, each item named",
    saved["n"] == 12 and len(saved["item_ids"]) == 12 and not saved["diagonal"],
    saved["n"],
)
check(
    "crosstab: a score an item has no value for counts as none",
    cell(g[DOWN], "none", "none")["n"] == 8 and cell(g[DOWN], "none", "none")["diagonal"],
)
check("crosstab: totals add up", sum(x["items"] for x in g.values()) == 65, [x["items"] for x in g.values()])
v2 = js("--runs", BASE, "--crosstab", "model_false_alarm,false_alarm", *GATE)[1]
cost = cell(groups_of(v2["crosstab"])[DOWN], "0", "1")
check(
    "crosstab: the downgrades that turned a right dismissal into a false alarm are 8",
    cost["n"] == 8,
    cost["n"],
)
check(
    "crosstab: the 12 and the 8 are different items",
    not set(saved["item_ids"]) & set(cost["item_ids"]),
)
v3 = js("--runs", BASE, "--crosstab", "model_correct,correct", *GATE)[1]
still = cell(groups_of(v3["crosstab"])[DOWN], "0", "0")
check(
    "crosstab: one of the 12 saved is still wrong (the gate sent a file to escalate): item named",
    still["n"] == 1 and still["item_ids"] == ["orrery-ORRERY-PROD-1P-2026-10-20T06:42:52Z"],
    still,
)
check(
    "crosstab: the group field itself, whole, when no --group-match",
    "i:n/a/c:n/a/d:downgraded (no corroboration)/e:n/a"
    in groups_of(
        js("--runs", BASE, "--crosstab", "correct,escalated", "--group", "_meta.gates")[1]["crosstab"]
    ),
)

r = evh("--runs", BASE, "--crosstab", "model_false_dismiss,false_dismiss", *GATE, "--max-ids", "3")
check(
    "crosstab text: counts, the table, ids cut at --max-ids with how many more",
    r.returncode == 0
    and f"_meta.gates = {DOWN} · 20" in r.stdout
    and "model_false_dismiss=1, false_dismiss=0: 12" in r.stdout
    and "… and 9 more" in r.stdout
    and "total" in r.stdout,
    r.stdout[:900],
)
r = evh("--runs", BASE, "--crosstab", "correct,escalated")
check(
    "crosstab: without --group one group over all the items",
    r.returncode == 0 and "all items · 65" in r.stdout,
    r.stdout[:300],
)
vw = js("--runs", BASE, "--crosstab", "correct,escalated", "--where", "decision_kind:model")[1]["crosstab"]
check(
    "crosstab: --where keeps the items whose field matches",
    0 < vw["groups"][0]["items"] < 65,
    vw["groups"][0]["items"],
)
check(
    "crosstab: --json carries blocks and the crosstab",
    {"command", "result"}
    <= set(json.loads(evh("--runs", BASE, "--crosstab", "correct,escalated", "--json").stdout)),
)

for what, args, text in (
    ("one score", ("--crosstab", "correct"), "two per-item scores"),
    ("an unknown score", ("--crosstab", "correct,nope"), "no per-item 'nope' on record"),
    (
        "an unknown group field",
        ("--crosstab", "correct,escalated", "--group", "nope.x"),
        "no per-item 'nope'",
    ),
    ("--group-match alone", ("--crosstab", "correct,escalated", "--group-match", "x"), "with --group FIELD"),
    (
        "a bad regex",
        ("--crosstab", "correct,escalated", "--group", "_meta.gates", "--group-match", "("),
        "--group-match",
    ),
    ("--group alone", ("--group", "_meta.gates"), "--group: with --crosstab"),
    ("--max-chars alone", ("--max-chars", "5"), "--max-chars: with --items-out"),
    ("both views", ("--crosstab", "correct,escalated", "--items-out"), "one at a time"),
    ("--disagree", ("--crosstab", "correct,escalated", "--disagree"), "--disagree"),
    ("an unknown field to filter", ("--crosstab", "correct,escalated", "--where", "nope:1"), "nope"),
):
    check(
        f"crosstab refuses {what}",
        refused(evh("--runs", BASE, *args), text),
        evh("--runs", BASE, *args).stderr[-200:],
    )
check("crosstab refuses no --runs", refused(evh("--crosstab", "correct,escalated"), "--runs"))

pub = evh("--runs", BASE, "--crosstab", "correct,escalated", public=True)
check("crosstab, public: two scores are numbers and ids: served", pub.returncode == 0, pub.stderr[-200:])
check(
    "crosstab, public: a recorded field can hold text: --group is not",
    refused(
        evh("--runs", BASE, "--crosstab", "correct,escalated", "--group", "_meta.gates", public=True),
        "not served publicly",
    ),
)

# ── the items, with their outputs ────────────────────────────────────────────────────────────────
r, v = js("--runs", f"{BASE},{OTHER}", "--items-out")
check("items-out: runs", r.returncode == 0, r.stderr[-300:])
io = v["items_out"]
check(
    "items-out: one record per item of the dataset",
    io["dataset_id"] == "orrery_triage_v1_labelled" and len(io["items"]) == 65,
)
rec = next(i for i in io["items"] if i["item_id"] == "orrery-ORRERY-PROD-1P-2026-10-20T06:42:52Z")
base = rec["arms"][BASE]
check(
    "items-out: each run's whole output, and its decision beside it",
    base["decision"] == "escalate" and "dismiss gate" in json.loads(base["output"])["reason"],
    base["decision"],
)
check(
    "items-out: the JSON keeps what the terminal leaves out (the probe trace)",
    "_probe_trace" in json.loads(base["output"]),
)
check(
    "items-out: the run's scores, recorded facts, the reference and the labels",
    base["scores"].get("model_false_dismiss") == 1.0
    and DOWN in base["meta"]["gates"]
    and rec["references"] == {"gold/orrery_triage_v1_labelled": "file"}
    and rec["labels"].get("orrery_triage_v1_labelled/gold_orrery_triage_v1_labelled") == "file",
    rec["labels"],
)
check("items-out: both runs on every item", set(rec["arms"]) == {BASE, OTHER} and OTHER in rec["arms"])

vd = js("--runs", f"{BASE},{OTHER}", "--items-out", "--disagree")[1]["items_out"]["items"]
check(
    "items-out: --disagree keeps the items the runs decided differently (17 on this pair)",
    0 < len(vd) < 65 and all(i["signals"].get("disagree") for i in vd),
    len(vd),
)
vw = js("--runs", f"{BASE},{OTHER}", "--items-out", "--where", "decision_kind:model")[1]["items_out"]["items"]
check("items-out: --where keeps the items whose field matches", 0 < len(vw) < 65, len(vw))

r = evh("--runs", BASE, "--items-out", "--max-chars", "120", "--where", "decision_kind:model")
check(
    "items-out text: an output cut at --max-chars with its length, the probe trace left out, the reference and label shown",
    r.returncode == 0
    and "chars)" in r.stdout
    and "_probe_trace" not in r.stdout
    and "reference gold/" in r.stdout
    and "label " in r.stdout,
    r.stdout[:800],
)
whole = evh("--runs", BASE, "--items-out", "--max-chars", "0").stdout
check(
    "items-out text: --max-chars 0 cuts nothing",
    "chars)" not in whole and "dismiss gate: no independent" in whole,
)
r = evh("--runs", f"{OTHER},{BASE}", "--baseline", BASE, "--items-out", "--disagree")
check(
    "items-out: --baseline puts a run first",
    r.returncode == 0 and r.stdout.index(f"[{BASE}]") < r.stdout.index(f"[{OTHER}]"),
)

REFUSALS: list[tuple[str, tuple[str, ...], str]] = [
    ("--disagree on one run", ("--runs", BASE, "--items-out", "--disagree"), "two runs or more"),
    ("--round", ("--round", "r1", "--items-out"), "--round"),
    ("--sheet", ("--runs", BASE, "--items-out", "--sheet"), "--sheet"),
    ("no --runs", ("--items-out",), "--runs"),
    (
        "a baseline not among the runs",
        ("--runs", BASE, "--baseline", OTHER, "--items-out"),
        "not among --runs",
    ),
]
for what, refused_argv, text in REFUSALS:
    check(f"items-out refuses {what}", refused(evh(*refused_argv), text), evh(*refused_argv).stderr[-200:])
check(
    "items-out, public: an item's text is never served",
    refused(evh("--runs", BASE, "--items-out", public=True), "not served publicly"),
)

sys.exit(summary())
