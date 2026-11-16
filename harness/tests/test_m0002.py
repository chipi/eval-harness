#!/usr/bin/env python3
"""`evh migrate`'s format 2 step (RFC-032 step 2): a model's deployments and arm smokes become deployment records.

    python tests/test_m0002.py

A project at format 1 whose configs are in a folder config.yaml's `configs:` names (outside data/), the way the
fleet's are: the model has two deployments and a smoke kept by config id, and the config names its `deployment:`.
The step finds the config there as it finds one in data/configs, so the smoke becomes a check of the deployment the
config names; a smoke whose config names none is still refused, naming it, when the model has several.
"""

from __future__ import annotations

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

base = Path(tempfile.mkdtemp(prefix="evh-m0002-"))
MODEL = """model_id: m1
deployments:
  - id: dep_a
  - id: dep_b
smokes:
  arm_a_v1:
    at: '2026-11-01T00:00:00Z'
    ok: true
"""


def project(name: str, config: str) -> Path:
    p = base / name
    (p / "data" / "models").mkdir(parents=True)
    (p / "projects" / "x" / "configs").mkdir(parents=True)
    (p / "config.yaml").write_text("store: files\nconfigs:\n  - projects/x/configs\n")
    (p / "data" / "project.yaml").write_text("format: 1\nwritten_by: 0.8.0\n")
    (p / "data" / "models" / "m1.yaml").write_text(MODEL)
    (p / "projects" / "x" / "configs" / "arm_a_v1.yaml").write_text(config)
    return p


def evh(proj: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "EVAL_DATA_DIR"}
    env.update(EVAL_HOME=str(proj), EVAL_STORE="files", EVAL_BUILD_REF="test-m0002")
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


try:
    named = project("named", "config_id: arm_a_v1\ndeployment: dep_b\nadapter: echo\n")
    r = evh(named, "migrate")
    dep_a = named / "data" / "deployments" / "m1" / "dep_a.yaml"
    dep_b = named / "data" / "deployments" / "m1" / "dep_b.yaml"
    check(
        "a config in a folder config.yaml names is found: its smoke becomes a check of the deployment it names",
        r.returncode == 0
        and dep_b.is_file()
        and "kind: smoke" in dep_b.read_text()
        and dep_a.is_file()
        and "kind: smoke" not in dep_a.read_text(),
        (r.returncode, r.stdout[-300:], r.stderr[-400:]),
    )

    none = project("none", "config_id: arm_a_v1\nadapter: echo\n")
    r = evh(none, "migrate")
    check(
        "a smoke whose config names no deployment, the model having two, is refused naming it, writing nothing",
        r.returncode != 0
        and "its config names none, and the model has 2" in r.stderr
        and not (none / "data" / "deployments").exists(),
        (r.returncode, r.stderr[-400:]),
    )
finally:
    shutil.rmtree(base, ignore_errors=True)
sys.exit(summary())
