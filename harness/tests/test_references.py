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

    r0 = evh("reference-manifest", "--reference-id", "gold/toy_v1", "--source", "fetch.py")
    check(
        "reference-manifest without a reason, who promotes and whose labels: refused (ADR-0022: a promotion)",
        r0.returncode != 0 and not (gold / "manifest.json").exists(),
        r0.stdout + r0.stderr,
    )
    r = evh(
        "reference-manifest",
        "--reference-id",
        "gold/toy_v1",
        "--source",
        "fetch.py",
        "--not-redistributed",
        "--labelled-by",
        "the dataset's authors",
        "--reason",
        "the dataset's own labels decide",
        "--by",
        "owner",
    )
    mf = json.loads((gold / "manifest.json").read_text()) if (gold / "manifest.json").is_file() else {}
    pf = mf.get("promoted_from") or {}
    check(
        "reference-manifest: the checksum of every item, how to rebuild it, not redistributed, and its promotion",
        r.returncode == 0
        and mf.get("n_items") == 2
        and set(mf.get("items_sha256") or {}) == {"a", "b"}
        and mf.get("source") == "fetch.py"
        and mf.get("redistributed") is False
        and pf.get("labels") is None
        and pf.get("source") == {"kind": "person", "by": "the dataset's authors", "via": "fetch.py"}
        and mf.get("reason") == "the dataset's own labels decide"
        and mf.get("promoted_by") == "owner",
        r.stdout + r.stderr + str(mf),
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

    # A second gold for one dataset has a name of its own; its manifest names the dataset.
    adj = proj / "data" / "references" / "gold" / "toy_v1_adj1"
    adj.mkdir(parents=True)
    (adj / "a.txt").write_text("shipping", encoding="utf-8")
    r = evh(
        "reference-manifest",
        "--reference-id",
        "gold/toy_v1_adj1",
        "--dataset-id",
        "toy_v1",
        "--source",
        "adj.py",
        "--labelled-by",
        "one reader's adjudication",
        "--reason",
        "the adjudicated labels sit beside the dataset's own",
        "--by",
        "owner",
    )
    refs = HarnessAdapter(proj / "data").references()
    check(
        "--dataset-id: a reference named on its own is listed under the dataset its manifest names",
        r.returncode == 0
        and json.loads((adj / "manifest.json").read_text()).get("dataset_id") == "toy_v1"
        and any(x["id"] == "gold/toy_v1_adj1" and x["dataset"] == "toy_v1" for x in refs),
        str(refs) + r.stderr,
    )
    shutil.rmtree(adj)

    shutil.rmtree(gold)
    silver = proj / "data" / "references" / "silver" / "toy_v1"
    silver.mkdir(parents=True)
    (silver / "a.txt").write_text("billing", encoding="utf-8")
    r = evh("validate")
    check(
        "V16: a reference with no manifest fails (ADR-0022: made only by promoting labels), saying how to make one",
        r.returncode != 0
        and "FAIL V16" in r.stdout
        and "silver/toy_v1: no manifest" in r.stdout
        and "reference-promote" in r.stdout,
        r.stdout[-600:],
    )

    # The hand-made folder made right where it is: its texts imported as a person's labels, then promoted; the
    # promotion adopts the folder (its texts are the labels') and writes its manifest. A folder whose texts differ
    # from the labels is never overwritten.
    src = proj / "data" / "sources" / "toy"
    src.mkdir(parents=True)
    (src / "a.txt").write_text("I was charged twice.", encoding="utf-8")
    (src / "b.txt").write_text("Where is my parcel?", encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "toy_v1", "--source-dir", "data/sources/toy")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "toy_v1")
    (silver / "b.txt").write_text("shipping\n", encoding="utf-8")
    r = (
        r
        if r.returncode
        else evh(
            "label-import",
            "data/references/silver/toy_v1",
            "--dataset-id",
            "toy_v1",
            "--set",
            "hand",
            "--by",
            "me",
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "toy_v1",
            "--labels",
            "hand",
            "--tier",
            "silver",
            "--reason",
            "the answers I wrote by hand",
            "--by",
            "me",
        )
    )
    mf = json.loads((silver / "manifest.json").read_text()) if (silver / "manifest.json").is_file() else {}
    check(
        "a hand-made folder, imported and promoted where it is: adopted, its manifest written, validate passes",
        r.returncode == 0
        and (mf.get("promoted_from") or {}).get("labels") == "hand"
        and mf.get("n_items") == 2
        and "ok   V16" in evh("validate").stdout,
        (r.stdout + r.stderr)[-500:] + str(mf)[:200],
    )
    other = proj / "data" / "references" / "gold" / "toy_v1"
    other.mkdir(parents=True)
    (other / "a.txt").write_text("refund", encoding="utf-8")
    r = evh(
        "reference-promote",
        "--dataset-id",
        "toy_v1",
        "--labels",
        "hand",
        "--tier",
        "gold",
        "--reason",
        "the answers I wrote by hand",
        "--by",
        "me",
    )
    check(
        "a folder whose texts are not the labels' is never overwritten",
        r.returncode != 0
        and "never overwritten" in (r.stdout + r.stderr)
        and (other / "a.txt").read_text() == "refund"
        and not (other / "manifest.json").exists(),
        (r.stdout + r.stderr)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
