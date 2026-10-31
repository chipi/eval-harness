#!/usr/bin/env python3
"""evh dataset-split (RFC-019 P5): dev and heldout as two ordinary datasets, stable across versions.

python tests/test_split.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-split-"))
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
    return json.loads((data / "datasets" / f"{name}.json").read_text())


def ids(name):
    return {it["item_id"] for it in ds(name)["items"]}


(data / "fields" / "g.yaml").write_text(
    "fieldset_id: g\ndescription: test\nfields:\n"
    "  - {name: group, type: text, label: Group, description: a group}\n"
    "  - {name: day, type: date, label: Day, description: a day}\n"
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

r = evh("dataset-split", "base_v2", "--heldout", "0.3", "--seed", "7")
dev, held = ids("base_v2_dev"), ids("base_v2_heldout")
check(
    "split: every item on exactly one side, about 30% heldout",
    r.returncode == 0 and dev | held == ids("base_v2") and not dev & held and 60 <= len(held) <= 120,
    f"{len(dev)} dev, {len(held)} heldout; " + out(r)[-200:],
)
sp = ds("base_v2_heldout").get("split", {})
check(
    "split: each side records the rule and its lineage to the parent",
    sp == {"from": "base_v2", "heldout": 0.3, "by": "hash", "key": None, "seed": 7, "part": "heldout"}
    and ds("base_v2_dev")["derived_from"]["dataset_id"] == "base_v2"
    and sorted(ds("base_v2_dev")["derived_from"]["removed"]) == sorted(held),
    sp,
)
r = evh("dataset-split", "base_v1", "--heldout", "0.3", "--seed", "7")
check(
    "split: a later version keeps every earlier item on its side",
    r.returncode == 0 and ids("base_v1_heldout") <= held and ids("base_v1_dev") <= dev,
    out(r)[-200:],
)
r = evh("dataset-split", "base_v2", "--heldout", "0.3", "--seed", "7", "--key", "group", "--force")
groups = {it["item_id"]: it["fields"]["group"] for it in ds("base_v2")["items"]}
gd = {groups[i] for i in ids("base_v2_dev")}
gh = {groups[i] for i in ids("base_v2_heldout")}
check("split --key: no group on both sides", r.returncode == 0 and not gd & gh and gd and gh, out(r)[-200:])
r = evh("dataset-split", "base_v1", "--heldout", "0.25", "--by", "time", "--key", "day", "--force")
days = {it["item_id"]: it["fields"]["day"] for it in ds("base_v1")["items"]}
check(
    "split --by time: the newest quarter is heldout",
    r.returncode == 0
    and len(ids("base_v1_heldout")) == 25
    and min(days[i] for i in ids("base_v1_heldout")) >= max(days[i] for i in ids("base_v1_dev")),
    out(r)[-200:],
)
r = evh("dataset-split", "base_v1", "--heldout", "0.25", "--seed", "1")
check("split: never overwrites without --force", r.returncode != 0 and "frozen" in out(r))
r = evh("dataset-split", "base_v1", "--heldout", "1.5")
check("split: a share outside (0, 1) is refused", r.returncode != 0)
r = evh("dataset-split", "base_v1", "--heldout", "0.5", "--by", "time")
check("split --by time without --key is refused", r.returncode != 0 and "--key" in out(r))
for name in ("base_v2_dev", "base_v2_heldout"):
    r = evh("dataset-materialize", "--dataset-id", name)
    check(f"split: {name} materializes from the parent's source files", r.returncode == 0, out(r)[-200:])
r = evh("validate")
check("split: validate passes (schema, lineage)", r.returncode == 0, out(r)[-400:])

sys.exit(summary())
