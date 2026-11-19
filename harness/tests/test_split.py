#!/usr/bin/env python3
"""evh dataset-split (RFC-019 P5): validation and test as two ordinary datasets, stable across versions.

python tests/test_split.py
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _tmp
import _tmp  # noqa: E402

proj = Path(_tmp.mkdtemp(prefix="evh-split-"))
data = proj / "data"
(data / "fields").mkdir(parents=True)
env = dict(os.environ, EVAL_HOME=str(proj))
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def ds(name):
    return _runstore.read_json(proj, f"datasets/{name}.json")


def ids(name):
    return {it["item_id"] for it in ds(name)["items"]}


_runstore.write_text(
    proj,
    "fields/g.yaml",
    "fieldset_id: g\ndescription: test\nfields:\n"
    "  - {name: group, type: text, label: Group, description: a group}\n"
    "  - {name: day, type: date, label: Day, description: a day}\n",
)
src = proj / "src"
src.mkdir()
rows = ["item_id,group,day"]
for i in range(300):
    (src / f"i{i:03d}.txt").write_text(f"item {i}")
    rows.append(f"i{i:03d},g{i % 60},2026-{1 + i % 12:02d}-{1 + i % 28:02d}")
(proj / "fields.csv").write_text("\n".join(rows) + "\n")
(proj / "fields_v1.csv").write_text("\n".join(rows[:101]) + "\n")
r = evh(
    "dataset-create",
    "--dataset-id",
    "base_v1",
    "--source-dir",
    "src",
    "--glob",
    "i0*",
    "--fieldset",
    "g",
    "--fields",
    "fields_v1.csv",
)
check("setup: base_v1 (100 items)", r.returncode == 0 and len(ds("base_v1")["items"]) == 100, out(r)[-300:])
r = evh(
    "dataset-create",
    "--dataset-id",
    "base_v2",
    "--source-dir",
    "src",
    "--fieldset",
    "g",
    "--fields",
    "fields.csv",
    "--from",
    "base_v1",
)
check(
    "setup: base_v2 (300 items, grown from v1)",
    r.returncode == 0 and len(ds("base_v2")["items"]) == 300,
    out(r)[-300:],
)

r = evh("dataset-split", "--dataset-id", "base_v2", "--test", "0.3", "--seed", "7")
dev, held = ids("base_v2_validation"), ids("base_v2_test")
check(
    "split: every item on exactly one side, about 30% test",
    r.returncode == 0 and dev | held == ids("base_v2") and not dev & held and 60 <= len(held) <= 120,
    f"{len(dev)} validation, {len(held)} test; " + out(r)[-200:],
)
sp = ds("base_v2_test").get("split", {})
check(
    "split: each side records the rule, its parent's version and its lineage; it is 1.0 itself",
    sp
    == {
        "from": "base_v2",
        "test": 0.3,
        "split_by": "hash",
        "key": None,
        "seed": 7,
        "part": "test",
        "from_version": "1.1",
    }
    and ds("base_v2_test")["version"] == ds("base_v2_validation")["version"] == "1.0"
    and ds("base_v2_validation")["derived_from"]["dataset_id"] == "base_v2"
    and sorted(ds("base_v2_validation")["derived_from"]["removed"]) == sorted(held),
    sp,
)
r = evh("dataset-split", "--dataset-id", "base_v1", "--test", "0.3", "--seed", "7")
check(
    "split: a later version keeps every earlier item on its side",
    r.returncode == 0 and ids("base_v1_test") <= held and ids("base_v1_validation") <= dev,
    out(r)[-200:],
)
r = evh(
    "dataset-split", "--dataset-id", "base_v2", "--test", "0.3", "--seed", "7", "--key", "group", "--force"
)
groups = {it["item_id"]: it["fields"]["group"] for it in ds("base_v2")["items"]}
gd = {groups[i] for i in ids("base_v2_validation")}
gh = {groups[i] for i in ids("base_v2_test")}
check("split --key: no group on both sides", r.returncode == 0 and not gd & gh and gd and gh, out(r)[-200:])
r = evh(
    "dataset-split",
    "--dataset-id",
    "base_v1",
    "--test",
    "0.25",
    "--split-by",
    "time",
    "--key",
    "day",
    "--force",
)
days = {it["item_id"]: it["fields"]["day"] for it in ds("base_v1")["items"]}
check(
    "split --split-by time: the newest quarter is test",
    r.returncode == 0
    and len(ids("base_v1_test")) == 25
    and min(days[i] for i in ids("base_v1_test")) >= max(days[i] for i in ids("base_v1_validation")),
    out(r)[-200:],
)
r = evh("dataset-split", "--dataset-id", "base_v1", "--test", "0.25", "--seed", "1")
check("split: never overwrites without --force", r.returncode != 0 and "frozen" in out(r))
r = evh("dataset-split", "--dataset-id", "base_v1", "--test", "1.5")
check("split: a share outside (0, 1) is refused", r.returncode != 0)
r = evh("dataset-split", "--dataset-id", "base_v1", "--test", "0.5", "--split-by", "time")
check("split --split-by time without --key is refused", r.returncode != 0 and "--key" in out(r))
for name in ("base_v2_validation", "base_v2_test"):
    r = evh("dataset-materialize", "--dataset-id", name)
    check(f"split: {name} materializes from the parent's source files", r.returncode == 0, out(r)[-200:])

# Each side gets the parent's references (owner, 2026-11-19; the 0.8.0 newcomer run copied each side's gold by hand).
gold = proj / "gold"
gold.mkdir()
for i in range(100, 200):
    (gold / f"i{i:03d}.txt").write_text(f"summary {i}\n")
evh("dataset-create", "--dataset-id", "kit_v1", "--source-dir", "src", "--glob", "i1*")
evh("dataset-materialize", "--dataset-id", "kit_v1")
evh("label-import", "--sheet", "gold", "--dataset-id", "kit_v1", "--set", "g", "--by", "t")
evh(
    "reference-promote",
    "--dataset-id",
    "kit_v1",
    "--labels",
    "g",
    "--tier",
    "gold",
    "--reason",
    "the test's own gold",
    "--by",
    "t",
)
split = ("dataset-split", "--dataset-id", "kit_v1", "--test", "0.3", "--seed", "7")
nobody = evh(*split)
check(
    "split: a parent with a reference is split only by someone named, nothing written before",
    nobody.returncode != 0
    and "--by person:NAME" in out(nobody)
    and not _runstore.exists(proj, "datasets/kit_v1_test.json"),
    out(nobody)[-300:],
)
r = evh(*split, "--by", "t")
got = {}
for part in ("validation", "test"):
    m = _runstore.read_json(proj, f"references/gold/kit_v1_{part}/manifest.json") if r.returncode == 0 else {}
    got[part] = (
        set(m.get("items_sha256") or {}) == ids(f"kit_v1_{part}"),
        (m.get("promoted_from") or {}).get("labels"),
    )
check(
    "split: each side gets the parent's reference on its own items, promoted from the same label set",
    r.returncode == 0 and got == {"validation": (True, "g"), "test": (True, "g")},
    (out(r)[-400:], got),
)
r = evh(*split, "--by", "t", "--force", "--seal")
check(
    "split --seal: the sealed side gets no reference, and the command for once it is unsealed",
    r.returncode == 0
    and "not promoted on the sealed side" in out(r)
    and "--labels kit_v1/g --tier gold" in out(r),
    out(r)[-400:],
)

r = evh("validate")
check("split: validate passes (schema, lineage)", r.returncode == 0, out(r)[-400:])

sys.exit(summary())
