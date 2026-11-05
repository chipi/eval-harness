#!/usr/bin/env python3
"""A dataset's licence: optional, picked from a list that ships with the package (PLAN_0.8.0 E2, owner 2026-11-05).

    python tests/test_licences.py

`evh licences` lists the SPDX ids a line each, searchable and as JSON; `dataset-create --licence` records one in
SPDX's spelling whatever its case, refuses one not on the list (naming the near ones); `unknown` and LicenseRef-<name>
are allowed. `dataset-describe` changes a licence or a description and leaves the items and the version; `validate`
V22 refuses a licence a hand edit put there.
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
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-licences-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-licences")
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
    return json.loads((proj / "data" / "datasets" / f"{i}.json").read_text())


try:
    r = evh("licences")
    check(
        "evh licences lists SPDX ids a line each",
        r.returncode == 0 and "CC-BY-SA-4.0" in r.stdout and "unknown" in r.stdout,
        r.stdout[-300:],
    )
    r = evh("licences", "--search", "share", "--json")
    ids = [x["id"] for x in json.loads(r.stdout)["licences"]] if r.returncode == 0 else []
    check(
        "--search keeps the matching ones, --json gives each its SPDX page",
        "CC-BY-SA-4.0" in ids
        and "MIT" not in ids
        and all(x["url"].startswith("https://spdx.org/") for x in json.loads(r.stdout)["licences"]),
        r.stdout[-300:],
    )
    src = proj / "src"
    src.mkdir()
    for n in "abc":
        (src / f"{n}.txt").write_text(f"item {n}\n")
    r = evh("dataset-create", "--dataset-id", "l_v1", "--source-dir", "src", "--licence", "cc-by-4.0")
    check(
        "dataset-create --licence records it in SPDX's spelling",
        r.returncode == 0 and ds("l_v1").get("licence") == "CC-BY-4.0",
        r.stderr[-300:],
    )
    r = evh("dataset-create", "--dataset-id", "l_v2", "--source-dir", "src", "--licence", "CC-BY-SA-5.0")
    check(
        "a licence not on the list is refused, naming the near ones, and nothing is written",
        r.returncode != 0
        and "did you mean" in r.stderr
        and "CC-BY-SA-4.0" in r.stderr
        and not (proj / "data" / "datasets" / "l_v2.json").exists(),
        r.stderr[-300:],
    )
    r = evh("dataset-create", "--dataset-id", "l_v3", "--source-dir", "src")
    check(
        "without --licence the dataset has none (it is optional)",
        r.returncode == 0 and "licence" not in ds("l_v3"),
        r.stderr[-300:],
    )
    before = ds("l_v1")
    r = evh(
        "dataset-describe",
        "--dataset-id",
        "l_v1",
        "--licence",
        "LicenseRef-our-terms",
        "--description",
        "three items",
    )
    after = ds("l_v1")
    check(
        "dataset-describe changes the licence and description; the items and the version stay",
        r.returncode == 0
        and after["licence"] == "LicenseRef-our-terms"
        and after["description"] == "three items"
        and after["items"] == before["items"]
        and after["version"] == before["version"] == "1.0",
        r.stdout[-300:] + r.stderr[-300:],
    )
    r = evh("dataset-describe", "--dataset-id", "l_v1", "--licence", "none")
    check("--licence none takes it off", r.returncode == 0 and "licence" not in ds("l_v1"), r.stdout[-200:])
    doc = ds("l_v3")
    doc["licence"] = "free-ish"
    (proj / "data" / "datasets" / "l_v3.json").write_text(json.dumps(doc, indent=1))
    r = evh("validate")
    check(
        "validate V22 refuses a licence a hand edit put there",
        r.returncode != 0 and "licence 'free-ish'" in r.stdout,
        r.stdout[-500:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
