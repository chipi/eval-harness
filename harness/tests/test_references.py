#!/usr/bin/env python3
"""Reference manifests and validate's V16: checksums committed, texts checked against them.

    python tests/test_references.py

In a throwaway project ($0, offline): a gold reference built outside the harness gets a manifest
from `evh reference-manifest`; V16 passes it, fails a text that drifted, passes a manifest whose
texts are not here when they are not redistributed (fetched elsewhere), fails one whose committed
texts are missing; the catalog lists a manifest-only reference as fetched.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-refs-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-references")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    """Run an evh command in the throwaway project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def v16():
    """The V16 line of a validate run."""
    r = evh("validate")
    return next((ln for ln in r.stdout.splitlines() if "V16" in ln and ("ok" in ln or "FAIL" in ln)), "")


try:
    gold = proj / "data" / "references" / "gold" / "toy_v1"
    gold.mkdir(parents=True)
    (gold / "a.txt").write_text("billing", encoding="utf-8")
    (gold / "b.txt").write_text("shipping", encoding="utf-8")

    r = evh(
        "reference-manifest", "--reference-id", "gold/toy_v1", "--source", "fetch.py", "--not-redistributed"
    )
    mf = json.loads((gold / "manifest.json").read_text()) if (gold / "manifest.json").is_file() else {}
    check(
        "reference-manifest: the checksum of every item, how to rebuild it, not redistributed",
        r.returncode == 0
        and mf.get("n_items") == 2
        and set(mf.get("items_sha256") or {}) == {"a", "b"}
        and mf.get("source") == "fetch.py"
        and mf.get("redistributed") is False,
        r.stdout + r.stderr,
    )
    line = v16()
    check("V16: texts that match their manifest pass", line.startswith("  ok") and "1 checked" in line, line)

    (gold / "b.txt").write_text("billing", encoding="utf-8")
    line = v16()
    check("V16: a text that drifted from its checksum fails", "FAIL" in line, line)
    (gold / "b.txt").write_text("shipping", encoding="utf-8")

    for f in gold.glob("*.txt"):
        f.unlink()
    line = v16()
    check(
        "V16: no texts, not redistributed: a reference fetched elsewhere, not a failure",
        line.startswith("  ok") and "1 fetched elsewhere" in line,
        line,
    )
    sys.path.insert(0, str(HERE))
    os.environ["EVAL_HOME"] = str(proj)
    from evaluation_harness.catalog_adapter import HarnessAdapter

    refs = HarnessAdapter(proj / "data").references()
    check(
        "catalog: a manifest-only reference is listed, as fetched, with its item count",
        any(x["id"] == "gold/toy_v1" and x["fetched"] and x["items"] == 2 for x in refs),
        str(refs),
    )

    mf["redistributed"] = True
    (gold / "manifest.json").write_text(json.dumps(mf))
    line = v16()
    check("V16: committed (redistributed) texts that are missing fail", "FAIL" in line, line)

    shutil.rmtree(gold)
    silver = proj / "data" / "references" / "silver" / "toy_v1"
    silver.mkdir(parents=True)
    (silver / "a.txt").write_text("billing", encoding="utf-8")
    r = evh("validate")
    check(
        "V16: a reference with no manifest is a note (how to add one), not a failure",
        "V16: silver/toy_v1 has no manifest" in r.stdout and "FAIL V16" not in r.stdout,
        r.stdout[-600:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
