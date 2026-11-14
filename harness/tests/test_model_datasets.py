#!/usr/bin/env python3
"""Datasets and what belongs to them through the model (RFC-032 step 6), in the suite's store.

    python tests/test_model_datasets.py

In a project `evh init` makes, with a dataset, its fieldset, a label set, two references (one promoted under another
name), a capture and a tag set written as their commands write them:

- each entity lists its records by their ids: a record that is a folder's file (`<id>/capture.json`,
  `<dataset>/<set>/labels.json`, `<tier>/<name>/manifest.json`) is found by its place;
- a dataset's references are found by the dataset their manifest names, the one promoted under another name too;
- a dataset's item folder is the one its record names, relative to the project, whatever directory asks;
- a label set's score label is built and recognised by one rule;
- a dataset's links (its fieldset, its parent, its capture) are checked, and a record written by its own commands
  is refused as an edit.
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
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-datasets-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-datasets")
SHA = "a" * 64


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
        text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def put(rel: str, doc: dict) -> None:
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2) + "\n")


try:
    evh("init")
    item = {"item_id": "i1", "source_path": "i1.txt", "source_sha256": SHA}
    put("datasets/ds_v1.json", {"dataset_id": "ds_v1", "version": "1.0", "created_at": "2026-11-14T00:00:00Z",
                                "items": [item], "source_dir": "data/sources/ds_v1", "fieldset": "f1"})  # fmt: skip
    put("datasets/ds_v2.json", {"dataset_id": "ds_v2", "version": "2.0", "created_at": "2026-11-14T00:00:00Z",
                                "items": [item], "derived_from": {"dataset_id": "ds_v1", "added": [], "removed": [],
                                "changed": ["i1"]}, "made_from": {"capture": "cap_1"}})  # fmt: skip
    _runstore.write_text(proj, "fields/f1.yaml", "fieldset_id: f1\nfields: []\n")
    put("labels/ds_v1/gold_ds_v1/labels.json", {"dataset_id": "ds_v1", "set": "gold_ds_v1", "created_at": "x",
        "source": {"kind": "person", "by": "owner"}, "n_items": 1, "items": {"i1": {"sha256": SHA}}})  # fmt: skip
    for name in ("ds_v1", "ds_v1_adj1"):
        put(f"references/gold/{name}/manifest.json", {"dataset_id": "ds_v1", "tier": "gold", "reason": "r",
            "promoted_from": {"dataset_id": "ds_v1", "labels": "gold_ds_v1"}, "items_sha256": {"i1": SHA}})  # fmt: skip
    put("captures/cap_1/capture.json", {"capture_id": "cap_1", "records": []})
    put("tags/ds_v1/first/tags.json", {"kind": "tag-set", "dataset_id": "ds_v1", "set": "first",
                                       "failure_modes": "m", "created_at": "x", "runs": {}})  # fmt: skip
    _runstore.migrate_in(proj)

    from evaluation_harness.model import datasets as m
    from evaluation_harness.model.entity import Problem

    check(
        "each entity lists its records by their ids, a folder's file found by its place",
        m.DATASET.ids() == ["ds_v1", "ds_v2"] and m.FIELDSET.ids() == ["f1"]
        and m.LABEL_SET.ids() == ["ds_v1/gold_ds_v1"] and m.CAPTURE.ids() == ["cap_1"]
        and m.REFERENCE.ids() == ["gold/ds_v1", "gold/ds_v1_adj1"] and m.TAG_SET.ids() == ["ds_v1/first"]
        and m.label_sets_of("ds_v1") == ["ds_v1/gold_ds_v1"],
        [m.DATASET.ids(), m.LABEL_SET.ids(), m.REFERENCE.ids(), m.CAPTURE.ids(), m.TAG_SET.ids()],
    )  # fmt: skip
    check(
        "a dataset's references are those whose manifest names it, one promoted under another name too",
        m.references_of("ds_v1") == ["gold/ds_v1", "gold/ds_v1_adj1"] and m.references_of("ds_v2") == [],
        m.references_of("ds_v1"),
    )
    elsewhere = Path(tempfile.mkdtemp(prefix="evh-elsewhere-"))
    here = Path.cwd()
    try:
        os.chdir(elsewhere)
        got = m.source_dir(m.DATASET.get("ds_v1"))
    finally:
        os.chdir(here)
        shutil.rmtree(elsewhere, ignore_errors=True)
    check(
        "a dataset's item folder is the one its record names, relative to the project, from any directory; "
        "a record naming none reads data/sources",
        got == proj.resolve() / "data" / "sources" / "ds_v1"
        and m.source_dir(m.DATASET.get("ds_v2")).resolve() == (proj / "data" / "sources").resolve(),
        str(got),
    )
    check(
        "a label set's score label is labels-<dataset>-<set>, recognised as the dataset's and no other's",
        m.label_of("ds_v1/gold_ds_v1") == "labels-ds_v1-gold_ds_v1"
        and m.is_label_of("labels-ds_v1-gold_ds_v1", "ds_v1")
        and not m.is_label_of("labels-ds_v1-gold_ds_v1", "ds")
        and not m.is_label_of("rescored abcd1234", "ds_v1"),
        m.label_of("ds_v1/gold_ds_v1"),
    )
    ok = m.DATASET.problems("ds_v1", m.DATASET.get("ds_v1")) + m.DATASET.problems(
        "ds_v2", m.DATASET.get("ds_v2")
    )
    broken = dict(m.DATASET.get("ds_v2"), fieldset="nope", made_from={"capture": "gone"},
                  derived_from={"dataset_id": "ds_v0", "added": [], "removed": [], "changed": []})  # fmt: skip
    said = {".".join(map(str, p["path"])) for p in m.DATASET.problems("ds_v2", broken)}
    check(
        "a dataset's fieldset, parent and capture are checked links; the stored ones hold",
        not ok and said == {"fieldset", "derived_from.dataset_id", "made_from.capture"},
        [ok, sorted(said)],
    )
    try:
        m.DATASET.save("ds_v1", m.DATASET.get("ds_v1"), "person:tester")
        refused = ""
    except Problem as exc:
        refused = exc.kind
    check("a dataset is written by its own commands: an edit is refused, nothing written", refused == "not-allowed",
          refused)  # fmt: skip
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
