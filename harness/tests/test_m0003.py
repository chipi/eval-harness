#!/usr/bin/env python3
"""`evh migrate`'s format 3 step (RFC-032 step 3): configs become systems; the folders config.yaml lists are kept in
validate.json.

    python tests/test_m0003.py

A project at format 2 whose configs are only in a config.yaml folder (outside data/), with a run of that config
(a project of the fleet's shape) and no data/validate.json: the migration reaches the last step (step 6 finds the
system in the folder the step wrote), data/validate.json is written listing the `systems` folder, and config.yaml no
longer lists `configs:`. When validate.json exists its other keys stay and the folder's glob is added to `systems`.
"""

from __future__ import annotations

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
from evaluation_harness._check import check, summary  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="evh-m0003-"))


def project(name: str, policy: str | None) -> Path:
    p = base / name
    (p / "data" / "datasets").mkdir(parents=True)
    (p / "projects" / "x" / "configs" / "v2").mkdir(parents=True)
    (p / "config.yaml").write_text(
        "store: files\nconfigs:\n  - projects/x/configs\n  - projects/x/configs/v2\n", encoding="utf-8"
    )
    (p / "data" / "project.yaml").write_text("format: 2\nwritten_by: 0.8.0\n", encoding="utf-8")
    (p / "data" / "datasets" / "ds1.json").write_text(
        json.dumps({"dataset_id": "ds1", "items": [{"item_id": "t01"}]}), encoding="utf-8"
    )
    (p / "projects" / "x" / "configs" / "arm_a_v1.yaml").write_text(
        "config_id: arm_a_v1\ndataset_id: ds1\nadapter: echo\n", encoding="utf-8"
    )
    (p / "projects" / "x" / "configs" / "v2" / "arm_b_v1.yaml").write_text(
        "config_id: arm_b_v1\ndataset_id: ds1\nadapter: echo\n", encoding="utf-8"
    )
    run = p / "data" / "runs" / "arm_a_v1_20261101T000000Z"
    (run / "outputs").mkdir(parents=True)
    (run / "outputs" / "t01.txt").write_text("one", encoding="utf-8")
    (run / "predictions.jsonl").write_text(
        json.dumps({"item_id": "t01", "acc": 1.0}) + "\n", encoding="utf-8"
    )
    (run / "metrics.json").write_text(
        json.dumps({"run_id": run.name, "dataset_id": "ds1", "config_id": "arm_a_v1",
                    "fingerprint": {"instrument": {"adapter": {"sha256": "a" * 64}}}}), encoding="utf-8"
    )  # fmt: skip
    if policy is not None:
        (p / "data" / "validate.json").write_text(policy, encoding="utf-8")
    return p


sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _cli
import _cli  # noqa: E402


def evh(proj: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "EVAL_DATA_DIR"}
    env.update(EVAL_HOME=str(proj), EVAL_STORE="files", EVAL_BUILD_REF="test-m0003")
    return _cli.run(proj, env, *args, timeout=300)


try:
    none = project("none", None)
    r = evh(none, "migrate")
    policy = none / "data" / "validate.json"
    doc = json.loads(policy.read_text(encoding="utf-8")) if policy.is_file() else {}
    check(
        "no validate.json: the migration reaches the last step, none of the moved systems is 'not a system'",
        r.returncode == 0 and "brought the data to format" in r.stdout,
        (r.returncode, r.stderr[-500:]),
    )
    check(
        "no validate.json: it is written with a `systems` glob for each folder the configs moved to",
        doc == {"systems": ["projects/x/systems/*.yaml", "projects/x/systems/v2/*.yaml"]}
        and (none / "projects" / "x" / "systems" / "arm_a_v1.yaml").is_file()
        and "configs:" not in (none / "config.yaml").read_text(encoding="utf-8"),
        (doc, r.stderr[-200:]),
    )

    has = project("has", json.dumps({"ignore": ["V5"], "configs": ["elsewhere/*.yaml"]}, indent=2) + "\n")
    r = evh(has, "migrate")
    doc = json.loads((has / "data" / "validate.json").read_text(encoding="utf-8"))
    check(
        "validate.json present: its other keys stay, `configs` becomes `systems`, the config.yaml folders are added",
        r.returncode == 0
        and doc.get("ignore") == ["V5"]
        and doc.get("systems")
        == ["elsewhere/*.yaml", "projects/x/systems/*.yaml", "projects/x/systems/v2/*.yaml"],
        (r.returncode, doc, r.stderr[-300:]),
    )

    dry = project("dry", None)
    r = evh(dry, "migrate", "--dry-run")
    check(
        "a dry run writes no validate.json into the project",
        r.returncode == 0 and not (dry / "data" / "validate.json").exists(),
        (r.returncode, r.stderr[-300:]),
    )
finally:
    shutil.rmtree(base, ignore_errors=True)
sys.exit(summary())
