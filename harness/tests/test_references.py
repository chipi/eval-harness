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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-refs-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-references")
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    """Run an evh command in the throwaway project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def texts(rel):
    """The .txt files of a folder under data/, by name, their bytes."""
    return {
        n: _runstore.read_bytes(proj, f"{rel}/{n}")
        for n in _runstore.listdir(proj, rel)
        if n.endswith(".txt")
    }


def v16():
    """The V16 line of a validate run."""
    r = evh("validate")
    return next((ln for ln in r.stdout.splitlines() if "V16" in ln and ("ok" in ln or "FAIL" in ln)), "")


try:
    gold = proj / "data" / "references" / "gold" / "toy_v1"
    gold.mkdir(parents=True)
    GOLD = "references/gold/toy_v1"
    _runstore.write_text(proj, f"{GOLD}/a.txt", "billing")
    _runstore.write_text(proj, f"{GOLD}/b.txt", "shipping")

    r0 = evh("reference-manifest", "--reference-id", "gold/toy_v1", "--source", "fetch.py")
    check(
        "reference-manifest without a reason, who promotes and whose labels: refused (ADR-0022: a promotion)",
        r0.returncode != 0 and not _runstore.exists(proj, f"{GOLD}/manifest.json"),
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
    mf = (
        _runstore.read_json(proj, f"{GOLD}/manifest.json")
        if _runstore.is_file(proj, f"{GOLD}/manifest.json")
        else {}
    )
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

    _runstore.write_text(proj, f"{GOLD}/b.txt", "billing")
    line = v16()
    check("V16: a text that drifted from its checksum fails", "FAIL" in line, line)
    _runstore.write_text(proj, f"{GOLD}/b.txt", "shipping")

    for n in texts(GOLD):
        _runstore.unlink(proj, f"{GOLD}/{n}")
    line = v16()
    check(
        "V16: no texts, not redistributed: a reference fetched elsewhere, not a failure",
        line.startswith("  ok") and "1 fetched elsewhere" in line,
        line,
    )
    sys.path.insert(0, str(HERE))
    os.environ["EVAL_HOME"] = str(proj)
    from evaluation_harness.catalog_adapter import HarnessAdapter

    with _runstore._InProject(proj) as data:
        refs = HarnessAdapter(data).references()
    check(
        "catalog: a manifest-only reference is listed, as fetched, with its item count",
        any(x["id"] == "gold/toy_v1" and x["fetched"] and x["items"] == 2 for x in refs),
        str(refs),
    )

    mf["redistributed"] = True
    _runstore.write_text(proj, f"{GOLD}/manifest.json", json.dumps(mf))
    line = v16()
    check("V16: committed (redistributed) texts that are missing fail", "FAIL" in line, line)

    # A second gold for one dataset has a name of its own; its manifest names the dataset.
    ADJ = "references/gold/toy_v1_adj1"
    (proj / "data" / ADJ).mkdir(parents=True)
    _runstore.write_text(proj, f"{ADJ}/a.txt", "shipping")
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
    with _runstore._InProject(proj) as data:
        refs = HarnessAdapter(data).references()
    check(
        "--dataset-id: a reference named on its own is listed under the dataset its manifest names",
        r.returncode == 0
        and _runstore.read_json(proj, f"{ADJ}/manifest.json").get("dataset_id") == "toy_v1"
        and any(x["id"] == "gold/toy_v1_adj1" and x["dataset"] == "toy_v1" for x in refs),
        str(refs) + r.stderr,
    )
    _runstore.rmtree(proj, ADJ)

    _runstore.rmtree(proj, GOLD)
    SILVER = "references/silver/toy_v1"
    (proj / "data" / SILVER).mkdir(parents=True)
    _runstore.write_text(proj, f"{SILVER}/a.txt", "billing")
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
    (proj / "data" / "sources" / "toy").mkdir(parents=True)
    _runstore.write_text(proj, "sources/toy/a.txt", "I was charged twice.")
    _runstore.write_text(proj, "sources/toy/b.txt", "Where is my parcel?")
    r = evh("dataset-create", "--dataset-id", "toy_v1", "--source-dir", "data/sources/toy")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "toy_v1")
    _runstore.write_text(proj, f"{SILVER}/b.txt", "shipping")  # by hand: no newline at the end
    before = texts(SILVER)
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
    mf = (
        _runstore.read_json(proj, f"{SILVER}/manifest.json")
        if _runstore.is_file(proj, f"{SILVER}/manifest.json")
        else {}
    )
    check(
        "a hand-made folder, imported and promoted where it is: adopted, its manifest written, validate passes",
        r.returncode == 0
        and (mf.get("promoted_from") or {}).get("labels") == "hand"
        and mf.get("n_items") == 2
        and "ok   V16" in evh("validate").stdout,
        (r.stdout + r.stderr)[-500:] + str(mf)[:200],
    )
    after = texts(SILVER)
    check(
        "the adopted folder's files keep their bytes (no newline added), so no run's reference digest moves",
        after == before,
        f"{before} -> {after}",
    )
    (proj / "data" / GOLD).mkdir(parents=True, exist_ok=True)
    _runstore.write_text(proj, f"{GOLD}/a.txt", "refund")
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
        and _runstore.read_text(proj, f"{GOLD}/a.txt") == "refund"
        and not _runstore.exists(proj, f"{GOLD}/manifest.json"),
        (r.stdout + r.stderr)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
