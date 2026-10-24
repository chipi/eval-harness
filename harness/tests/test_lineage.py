#!/usr/bin/env python3
"""Assertions for dataset lineage: `dataset-create --from`, validate V2, the catalog's versions.

    python tests/test_lineage.py

In a throwaway project built from the tutorial ($0, offline): a version made from another
records what it adds, removes and changes; a missing or self parent is refused; V2 fails a
dataset whose parent is gone; the catalog links the versions both ways, and a version no arm
has run on yet still gets a page.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(HERE))  # the core modules
KIT = HERE.parent / "tutorial"
from _check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-lineage-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-lineage")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    v1_src, v2_src = proj / "src_v1", proj / "src_v2"
    shutil.copytree(KIT / "tickets", v1_src)
    shutil.copytree(KIT / "tickets", v2_src)
    (v2_src / "t06_mobile.txt").unlink()  # removed
    (v2_src / "t07_new.txt").write_text("A new ticket about invoices.\n")  # added
    (v2_src / "t01_login.txt").write_text((v1_src / "t01_login.txt").read_text() + " Edited.\n")  # changed
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "src_v1")
    check("setup: v1 is frozen", r.returncode == 0, r.stderr[-300:])

    r = evh("dataset-create", "--dataset-id", "tickets_v2", "--source-dir", "src_v2", "--from", "tickets_v9")
    check(
        "--from a dataset that does not exist is refused",
        r.returncode != 0 and "no dataset" in r.stdout + r.stderr,
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v2", "--source-dir", "src_v2", "--from", "tickets_v2")
    check(
        "--from itself is refused", r.returncode != 0 and "cannot be made from itself" in r.stdout + r.stderr
    )

    r = evh("dataset-create", "--dataset-id", "tickets_v2", "--source-dir", "src_v2", "--from", "tickets_v1")
    doc = json.loads((data / "datasets" / "tickets_v2.json").read_text()) if r.returncode == 0 else {}
    check(
        "--from records the parent and the item ids added, removed and changed",
        doc.get("derived_from")
        == {
            "dataset_id": "tickets_v1",
            "added": ["t07_new"],
            "removed": ["t06_mobile"],
            "changed": ["t01_login"],
        },
        doc.get("derived_from"),
    )
    check("--from says so", "derived from tickets_v1: 1 added, 1 removed, 1 changed" in r.stdout, r.stdout)

    r = evh("validate")
    check(
        "validate: V1 accepts derived_from, V2 resolves it",
        "FAIL V1" not in r.stdout and "FAIL V2" not in r.stdout,
    )

    # A run on v1 only: v2 has no arm, and still gets a page because it is v1's version.
    shutil.copy(KIT / "configs" / "tickets_lead1.yaml", data / "configs")
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = evh("experiment-run", "--config", "data/configs/tickets_lead1.yaml")
    check("setup: an arm runs on v1", r.returncode == 0, r.stderr[-300:])
    r = evh("catalog")
    out = proj / ".build" / "catalog"
    v1 = (out / "d/tickets_v1.html").read_text() if (out / "d/tickets_v1.html").is_file() else ""
    v2 = (out / "d/tickets_v2.html").read_text() if (out / "d/tickets_v2.html").is_file() else ""
    home = (out / "index.html").read_text() if (out / "index.html").is_file() else ""
    check(
        "catalog: v1 links forward to v2, v2 back to v1 with what changed",
        'Made into <a class="cell-link" href="../d/tickets_v2.html">' in v1
        and 'Made from <a class="cell-link" href="../d/tickets_v1.html">' in v2
        and "1 added, 1 removed, 1 changed" in v2,
    )
    check(
        "catalog: the home page says which version a dataset came from",
        'from <a class="cell-link" href="d/tickets_v1.html">' in home,
    )

    (data / "datasets" / "tickets_v1.json").unlink()
    r = evh("validate")
    check(
        "validate: V2 fails a dataset whose parent is gone",
        "derived from tickets_v1, which does not exist" in r.stdout,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
