#!/usr/bin/env python3
"""validate holds the records of the dataset layer to their schemas and links (RFC-032 step 6).

    python tests/test_validate_records.py

In a throwaway project ($0, offline), in whichever store the suite runs in: a sound project (a dataset made from a
capture that exists, a sealed side with an exposure register, a label set, a tag set, a pick list) passes V2, V19, V21
and V22; then each defect is planted and named by its check: a dataset made from a capture that is not there (V2), a
label set and a tag set that break their schemas (V19, V21), an exposure register of a dataset that is not a sealed side
and a row that breaks its schema, and a pick line that breaks its schema (V22).
"""

import hashlib
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
from evaluation_harness._seal import items_digest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-validate-rec-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-validate-records")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR"):
    env.pop(k, None)


def validate():
    r = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), "validate"], cwd=proj, env=env, capture_output=True, text=True
    )
    return r.stdout + r.stderr


def lines_of(out, tag):
    """One check's lines: the details it prints, then its result line (ok, FAIL or --)."""
    pending = []
    for ln in out.splitlines():
        pending.append(ln)
        if ln.startswith(("  ok   V", "  FAIL V", "  --   V")):
            if ln.split()[1] == tag:
                return pending
            pending = []
    return []


def failed(out, tag):
    return any(ln.startswith("  FAIL") for ln in lines_of(out, tag))


def put(rel, doc):
    _runstore.write_text(proj, rel, doc if isinstance(doc, str) else json.dumps(doc, indent=1) + "\n")


def dataset(i, sealed=None, **more):
    items = [
        {"item_id": n, "source_path": f"{n}.txt", "source_sha256": hashlib.sha256(n.encode()).hexdigest()}
        for n in "ab"
    ]
    rec = {
        "dataset_id": i,
        "version": "1.0",
        "description": i,
        "created_at": "2026-11-10T00:00:00Z",
        "items": items,
    }
    if sealed:
        rec["sealed"] = {
            "at": "2026-11-10T00:00:00Z",
            "open_side": "open_v1",
            "open_sha256": items_digest(sealed["items"]),
        }
    put(f"datasets/{i}.json", {**rec, **more})
    return rec


ROW = {
    "item_id": "a",
    "what": "a comparison",
    "at": "2026-11-12T10:00:00Z",
    "by": "person:ana",
    "recorded_at": "2026-11-12T10:00:00Z",
    "recorded_by": "person:ana",
    "source": "hand",
}
PICK = {"action": "pick", "item": "a", "from": "open_v1", "for": [], "at": "2026-11-12T10:00:00Z"}
LABEL = {
    "dataset_id": "open_v1",
    "set": "l1",
    "source": {"kind": "person"},
    "created_at": "2026-11-12T10:00:00Z",
    "n_items": 1,
    "items": {"a": {"sha256": hashlib.sha256(b"x\n").hexdigest()}},
}
TAGS = {
    "kind": "tag-set",
    "dataset_id": "open_v1",
    "set": "t1",
    "failure_modes": "m",
    "created_at": "2026-11-12T10:00:00Z",
    "n_tagged": 1,
    "runs": {"r1": {"a": {"modes": ["too-long"]}}},
}
try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    open_rec = dataset("open_v1")
    dataset("held_v1", sealed=open_rec)
    dataset("from_cap_v1", made_from={"capture": "c1"})
    put("captures/c1/capture.json", {"capture_id": "c1"})
    put("labels/open_v1/l1/labels.json", LABEL)
    put("labels/open_v1/l1/a.txt", "x\n")
    put("failure-modes/m.yaml", "failure_modes_id: m\nmodes:\n  - id: too-long\n")
    put("tags/open_v1/t1/tags.json", TAGS)
    put("exposure/held_v1.jsonl", json.dumps(ROW) + "\n")
    put("picks.jsonl", json.dumps(PICK) + "\n")

    out = validate()
    for tag in ("V2", "V19", "V21", "V22"):
        check(
            f"a sound project: {tag} is ok",
            lines_of(out, tag) and not failed(out, tag),
            "\n".join(lines_of(out, tag)),
        )

    # ── planted defects ───────────────────────────────────────────────────────────────────────────────────────
    dataset("lost_v1", made_from={"capture": "nocap"})
    put("labels/open_v1/l1/labels.json", {**LABEL, "source": {"kind": "robot"}})
    put("tags/open_v1/t1/tags.json", {k: v for k, v in TAGS.items() if k != "created_at"})
    put(
        "exposure/open_v1.jsonl",
        json.dumps(ROW) + "\n" + json.dumps({k: v for k, v in ROW.items() if k != "by"}) + "\n",
    )
    put("exposure/held_v1.jsonl", json.dumps(ROW) + "\n" + json.dumps({**ROW, "source": "dream"}) + "\n")
    put("picks.jsonl", json.dumps(PICK) + "\n" + json.dumps({**PICK, "action": "zap"}) + "\n" + "{not json\n")

    out = validate()
    v2, v19, v21, v22 = (" ".join(lines_of(out, t)) for t in ("V2", "V19", "V21", "V22"))
    check(
        "V2: a dataset made from a capture that is not there is named; one made from a capture that is, is not",
        failed(out, "V2") and "lost_v1 made from capture nocap" in v2 and "from_cap_v1" not in v2,
        v2,
    )
    check(
        "V19: a label set that breaks its schema is named",
        failed(out, "V19") and "open_v1/l1" in v19 and "robot" in v19,
        v19,
    )
    check(
        "V21: a tag set that breaks its schema is named",
        failed(out, "V21") and "open_v1/t1" in v21 and "created_at" in v21,
        v21,
    )
    check(
        "V22: a register of a dataset that is not a sealed side is named",
        failed(out, "V22") and "exposure/open_v1.jsonl: open_v1 is not a sealed side" in v22,
        v22,
    )
    check(
        "V22: a register row that breaks its schema is named, with its line",
        "exposure/open_v1.jsonl: line 2: 'by' is a required property" in v22
        and "exposure/held_v1.jsonl: line 2" in v22
        and "dream" in v22,
        v22,
    )
    check(
        "V22: a pick line that breaks its schema, and one that is not JSON, are named, with their lines",
        "picks.jsonl: line 2" in v22 and "zap" in v22 and "picks.jsonl: line 3 does not parse" in v22,
        v22,
    )
    check(
        "V22: the sound register's row is not named",
        "exposure/held_v1.jsonl: line 1" not in v22 and "picks.jsonl: line 1" not in v22,
        v22,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
