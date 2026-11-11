#!/usr/bin/env python3
"""A dataset's content version, MAJOR.MINOR (PLAN_0.8.0 E3, owner 2026-11-05).

    python tests/test_dataset_version.py

The rule on its own (1.10 follows 1.9; added only is MINOR + 1; removed or changed is MAJOR + 1; the same items keep
the parent's), then through the commands in a throwaway project: a first dataset is 1.0, one made `--from` it with an
item added 1.1, with one removed 2.0, a split's sides 1.0 naming the parent's version; `validate` V22 agrees, then
catches a hand-edited version; `evh migrate` writes it back and a second run changes nothing.
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
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _dataset_version as dv  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

check("1.9 and an added item: 1.10, not 2.0", dv.next_version("1.9", {"added": ["x"]}) == "1.10")
check(
    "an item removed: MAJOR + 1, MINOR 0",
    dv.next_version("1.10", {"removed": ["x"], "added": ["y"]}) == "2.0",
)
check("an item changed: MAJOR + 1", dv.next_version("3.2", {"changed": ["x"]}) == "4.0")
check("the same items under a new id keep the parent's", dv.next_version("2.3", {"added": []}) == "2.3")
check(
    "a parent that is gone counts as 1.0",
    dv.expected({"derived_from": {"dataset_id": "g", "added": ["x"]}}, lambda _: None) == "1.1",
)
check(
    "a split side is 1.0 whatever it removed",
    dv.expected(
        {"split": {"from": "p"}, "derived_from": {"dataset_id": "p", "removed": ["x"]}}, lambda _: "3.4"
    )
    == "1.0",
)
check("two integers only", dv.parse("1.10") == (1, 10) and dv.parse("1.01") is None and dv.parse("1") is None)

proj = Path(tempfile.mkdtemp(prefix="evh-dsver-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-dataset-version")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def ds(i):
    return _runstore.read_json(proj, f"datasets/{i}.json")


try:
    src = proj / "src"
    for d, names in (("a", "abcd"), ("b", "abcde"), ("c", "abc")):
        (src / d).mkdir(parents=True)
        for n in names:
            (src / d / f"{n}.txt").write_text(f"item {n}\n")
    r = evh("dataset-create", "--dataset-id", "t_v1", "--source-dir", "src/a")
    check("a first dataset is 1.0", r.returncode == 0 and ds("t_v1")["version"] == "1.0", r.stderr[-300:])
    r = evh("dataset-create", "--dataset-id", "t_v2", "--source-dir", "src/b", "--from", "t_v1")
    check(
        "made from it with an item added: 1.1",
        r.returncode == 0 and ds("t_v2")["version"] == "1.1",
        r.stderr[-300:],
    )
    r = evh("dataset-create", "--dataset-id", "t_v3", "--source-dir", "src/c", "--from", "t_v2")
    check(
        "then with items removed: 2.0", r.returncode == 0 and ds("t_v3")["version"] == "2.0", r.stderr[-300:]
    )
    r = evh("dataset-split", "t_v2", "--test", "0.4", "--seed", "1")
    sides = [
        n.removesuffix(".json")
        for n in _runstore.listdir(proj, "datasets")
        if n.startswith("t_v2_") and n.endswith(".json")
    ]
    check(
        "a split's sides are 1.0, each naming its parent's version",
        r.returncode == 0
        and len(sides) == 2
        and all(ds(s)["version"] == "1.0" and ds(s)["split"]["from_version"] == "1.1" for s in sides),
        (r.stdout + r.stderr)[-300:] + str(sides),
    )
    r = evh("validate")
    v22 = [ln for ln in r.stdout.splitlines() if "V22" in ln]
    check(
        "validate V22: every version is its lineage's",
        bool(v22) and v22[0].lstrip().startswith("ok"),
        "\n".join(v22) or r.stdout[-400:],
    )
    doc = ds("t_v3")
    doc["version"] = "1.2"
    _runstore.write_text(proj, "datasets/t_v3.json", json.dumps(doc, indent=1))
    r = evh("validate")
    check(
        "validate V22: a hand-edited version is caught, naming what the lineage gives",
        r.returncode != 0 and "version '1.2', its lineage gives 2.0" in r.stdout,
        r.stdout[-500:],
    )
    r = evh("migrate", "--dry-run")
    check(
        "migrate --dry-run says what it would write, and writes nothing",
        r.returncode == 0 and "t_v3: version '1.2' -> 2.0" in r.stdout and ds("t_v3")["version"] == "1.2",
        r.stdout[-300:],
    )
    r = evh("migrate")
    r2 = evh("migrate")
    check(
        "migrate writes it; a second run changes nothing",
        r.returncode == 0
        and ds("t_v3")["version"] == "2.0"
        and "0 changed: already in this format" in r2.stdout,
        r.stdout[-300:] + r2.stdout[-200:],
    )

    # The fleet's feedback 16: a version made (and cited by runs) without --from gains its lineage afterwards,
    # its items untouched.
    evh("dataset-create", "--dataset-id", "t_v4", "--source-dir", "src/b", "--tag", "x")
    _runstore.write_text(
        proj, "datasets/t_v4.json", json.dumps({**ds("t_v4"), "tags": {"purpose": "tuning"}})
    )
    before = ds("t_v4")
    r = evh("dataset-create", "--dataset-id", "t_v4", "--from", "t_v1", "--lineage-only")
    after = ds("t_v4")
    check(
        "dataset-create --lineage-only: the lineage recorded, the version follows (1.0 -> 1.1), says so",
        r.returncode == 0
        and after["derived_from"]["dataset_id"] == "t_v1"
        and len(after["derived_from"]["added"]) == 1
        and not after["derived_from"]["removed"] + after["derived_from"]["changed"]
        and after["version"] == "1.1"
        and "version 1.0 -> 1.1" in r.stdout,
        (r.stdout + r.stderr)[-400:],
    )
    check(
        "dataset-create --lineage-only: items, created_at and the record's other keys untouched",
        after["items"] == before["items"]
        and after["created_at"] == before["created_at"]
        and after.get("tags") == {"purpose": "tuning"},
    )
    refusals = {
        "no --from": evh("dataset-create", "--dataset-id", "t_v4", "--lineage-only"),
        "another parent": evh("dataset-create", "--dataset-id", "t_v4", "--from", "t_v2", "--lineage-only"),
        "a loop": evh("dataset-create", "--dataset-id", "t_v1", "--from", "t_v4", "--lineage-only"),
        "a split side": evh("dataset-create", "--dataset-id", sides[0], "--from", "t_v1", "--lineage-only")
        if sides
        else evh("nope"),
        "no such dataset": evh("dataset-create", "--dataset-id", "t_v9", "--from", "t_v1", "--lineage-only"),
    }
    said = {k: (x.stdout + x.stderr) for k, x in refusals.items()}
    check(
        "dataset-create --lineage-only refuses: no --from, another parent, a loop, a split side, no such dataset",
        all(x.returncode != 0 for x in refusals.values())
        and "needs --from" in said["no --from"]
        and "already records it was made from t_v1" in said["another parent"]
        and "(a loop)" in said["a loop"]
        and "side of a split" in said["a split side"]
        and "no dataset at" in said["no such dataset"]
        and "derived_from" not in ds("t_v1"),
        {k: v[-200:] for k, v in said.items()},
    )
    r = evh("validate")
    v22 = [ln for ln in r.stdout.splitlines() if "V22" in ln]
    check(
        "validate V22 after --lineage-only: the version is its lineage's",
        bool(v22) and v22[0].lstrip().startswith("ok"),
        "\n".join(v22) or r.stdout[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
