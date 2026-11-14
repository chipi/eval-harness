#!/usr/bin/env python3
"""Datasets, fieldsets, failure modes, label sets, tag sets, references and captures through both surfaces (RFC-032
step 6), in the suite's store.

    python tests/test_model_datasets_ops.py

In a project `evh init` makes, with two versions of a dataset and a sealed one, a fieldset and a failure-mode list made
with their commands, two label sets (a person's, a rule over a capture), three references (one promoted under another
name, one from a script), a capture and a tag set written as their commands write them: `dataset-list` and
`dataset-show` give the record without its items, the parts and where they are, the lineage with its counts, and what
hangs on the dataset; the label sets, tag sets, references and captures list and show without the lists that grow with
the items; the fieldset and failure-mode commands make and change their own files, keeping a file's comments, and refuse
an id that is taken, a record that does not check and an id that does not exist; no command edits a dataset, a label
set, a reference or a capture; the API's resources give the command line's answers, and its edits record who sent them.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-dsops-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-datasets-ops")
SHA = "a" * 64
SHA2 = "b" * 64


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def put(rel: str, doc: dict) -> None:
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2) + "\n")


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError(f"the server did not start: {(p.communicate()[0] or '')[-500:]}")


def call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """One API call with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"text": raw.decode(errors="replace")[-500:]}


def stored(rel: str) -> str:
    """A file of the project's data, "" when it is not there."""
    return _runstore.read_text(proj, rel) if _runstore.is_file(proj, rel) else ""


try:
    r = evh("init")
    r = r if r.returncode else evh("catalog")
    check("setup: a project and its catalog", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    one = {"item_id": "i1", "source_path": "i1.txt", "source_sha256": SHA}
    two = {"item_id": "i2", "source_path": "i2.txt", "source_sha256": SHA2}
    put("datasets/ds_v1.json", {"dataset_id": "ds_v1", "version": "1.0", "created_at": "2026-11-14T00:00:00Z",
                                "description": "the first", "items": [one], "source_dir": "data/sources/ds_v1",
                                "fieldset": "f1", "made_from": {"capture": "cap_1"}})  # fmt: skip
    put("datasets/ds_v2.json", {"dataset_id": "ds_v2", "version": "2.0", "created_at": "2026-11-14T00:00:00Z",
                                "items": [one, two], "fieldset": "f1", "derived_from": {"dataset_id": "ds_v1",
                                "added": ["i2"], "removed": [], "changed": ["i1"]}})  # fmt: skip
    put("datasets/ds_v2_test.json", {"dataset_id": "ds_v2_test", "version": "2.0", "created_at": "x",
                                     "items": [two], "sealed": {"at": "2026-11-14T00:00:00Z"}})  # fmt: skip
    _runstore.write_text(proj, "sources/ds_v1/i1.txt", "one\n")
    put("sources/ds_v1.rows.json", {"i1": {"row": 1}})
    put("profiles/ds_v1.json", {"dataset_id": "ds_v1", "rows": []})
    for name, who in (("gold_ds_v1", {"kind": "person", "by": "owner"}),
                      ("rule_cap", {"kind": "rule", "capture": "cap_1"})):  # fmt: skip
        put(f"labels/ds_v1/{name}/labels.json", {"dataset_id": "ds_v1", "set": name, "created_at": "2026-11-14T01:00:00Z",
            "source": who, "n_items": 1, "note": "n", "items": {"i1": {"sha256": SHA, "item_sha256": SHA}}})  # fmt: skip
    put("references/gold/ds_v1/manifest.json", {"dataset_id": "ds_v1", "tier": "gold", "reason": "the owner's", "n_items": 1,
        "caveat": "c", "promoted_by": "owner", "promoted_from": {"dataset_id": "ds_v1", "labels": "gold_ds_v1",
        "source": {"kind": "person", "by": "owner"}}, "items_sha256": {"i1": SHA}})  # fmt: skip
    put("references/gold/ds_v1_adj1/manifest.json", {"dataset_id": "ds_v1", "tier": "gold", "reason": "adjudicated",
        "n_items": 1, "caveat": "c", "source": "fetch.py", "promoted_from": {"dataset_id": "ds_v1", "labels": None,
        "source": {"kind": "person"}}, "items_sha256": {"i1": SHA}})  # fmt: skip
    put("references/silver/ds_v1_rule/manifest.json", {"dataset_id": "ds_v1", "tier": "silver", "reason": "outcomes",
        "n_items": 1, "caveat": "c", "promoted_from": {"dataset_id": "ds_v1", "labels": "rule_cap",
        "source": {"kind": "rule"}}, "items_sha256": {"i1": SHA}})  # fmt: skip
    put("captures/cap_1/capture.json", {"capture_id": "cap_1", "importer": "jsonl", "captured_at": "2026-11-13T00:00:00Z",
        "n_records": 2, "window": {}, "query": {"path": "x"}, "records": [{"id": "a"}, {"id": "b"}]})  # fmt: skip
    put("tags/ds_v1/first/tags.json", {"kind": "tag-set", "dataset_id": "ds_v1", "set": "first",
        "failure_modes": "summaries", "created_at": "2026-11-14T02:00:00Z",
        "runs": {"r1": {"i1": {"modes": ["too-long"]}}, "r2": {"i1": {"modes": ["too-long", "misses-ask"]}}}})  # fmt: skip
    _runstore.migrate_in(proj)

    made = evh("fieldset-new", "f1", "--set", "description=the facts", "--set", "fields.0.name=kind",
               "--set", "fields.0.type=text")  # fmt: skip
    check("setup: fieldset-new makes the fieldset", made.returncode == 0, (made.stdout + made.stderr)[-300:])
    made = evh("failure-modes-new", "summaries", "--set", "modes.0.id=too-long", "--set", "modes.1.id=misses-ask",
               "--set", "description=ways a summary is wrong")  # fmt: skip
    check("setup: failure-modes-new makes the list", made.returncode == 0, (made.stdout + made.stderr)[-300:])

    # -- datasets
    dl = result(evh("dataset-list", "--json"))["datasets"]
    by = {d["dataset"]: d for d in dl}
    check(
        "dataset-list: every dataset with its version, items, parent, seal, label sets and references",
        sorted(by) == ["ds_v1", "ds_v2", "ds_v2_test"]
        and by["ds_v1"]["items"] == 1 and by["ds_v2"]["items"] == 2 and by["ds_v1"]["version"] == "1.0"
        and by["ds_v2"]["parent"] == "ds_v1" and by["ds_v1"]["parent"] is None
        and by["ds_v2_test"]["sealed"] and not by["ds_v1"]["sealed"]
        and by["ds_v1"]["label_sets"] == ["ds_v1/gold_ds_v1", "ds_v1/rule_cap"]
        and by["ds_v1"]["references"] == ["gold/ds_v1", "gold/ds_v1_adj1", "silver/ds_v1_rule"]
        and by["ds_v1"]["fieldset"] == "f1" and by["ds_v1"]["description"] == "the first",
        dl,
    )  # fmt: skip
    check(
        "dataset-list: which parts are here (source folder, row map, profile; not the materialized copy)",
        by["ds_v1"]["parts"] == {"source": True, "rows": True, "profile": True, "materialized": False}
        and by["ds_v2"]["parts"]["profile"] is False,
        by["ds_v1"]["parts"],
    )
    text = evh("dataset-list").stdout
    check(
        "dataset-list in words: a line a dataset, with its parent, seal and counts",
        "ds_v2  " in text and "from ds_v1" in text and "sealed" in text and "3 reference(s)" in text,
        text,
    )
    show = result(evh("dataset-show", "ds_v1", "--json"))
    check(
        "dataset-show: the record without its items (the count instead), its parts with project-relative paths",
        show["n_items"] == 1 and "items" not in show["record"] and show["record"]["version"] == "1.0"
        and show["file"] == "data/datasets/ds_v1.json"
        and show["parts"]["source"] == {"path": "data/sources/ds_v1", "present": True}
        and show["parts"]["rows"]["path"] == "data/sources/ds_v1.rows.json"
        and show["parts"]["materialized"] == {"path": "data/materialized/ds_v1", "present": False}
        and "exposure" not in show["parts"],
        show,
    )  # fmt: skip
    check(
        "dataset-show: the children with their counts, the label sets, the references (one promoted under another "
        "name too), the capture and the tag sets",
        show["lineage"] == {"parent": None, "children": [{"dataset": "ds_v2", "added": 1, "removed": 0, "changed": 1}]}
        and [s["set"] for s in show["label_sets"]] == ["ds_v1/gold_ds_v1", "ds_v1/rule_cap"]
        and [x["reference"] for x in show["references"]] == ["gold/ds_v1", "gold/ds_v1_adj1", "silver/ds_v1_rule"]
        and show["captures"] == ["cap_1"] and [t["set"] for t in show["tag_sets"]] == ["ds_v1/first"],
        show,
    )  # fmt: skip
    v2 = result(evh("dataset-show", "ds_v2", "--json"))
    check(
        "dataset-show: the parent with the version's added, removed and changed counts",
        v2["lineage"]["parent"] == {"dataset": "ds_v1", "exists": True, "added": 1, "removed": 0, "changed": 1}
        and v2["lineage"]["children"] == [],
        v2["lineage"],
    )  # fmt: skip
    sealed = result(evh("dataset-show", "ds_v2_test", "--json"))
    check(
        "dataset-show: a sealed side shows its exposure register's place",
        sealed["parts"]["exposure"] == {"path": "data/exposure/ds_v2_test.jsonl", "present": False},
        sealed["parts"],
    )
    words = evh("dataset-show", "ds_v1").stdout
    check(
        "dataset-show in words: the record, parts, label sets and references",
        "ds_v1  v1.0  1 items  (data/datasets/ds_v1.json)" in words and "made into    ds_v2: 1 added" in words
        and "label set    ds_v1/gold_ds_v1: person" in words and "reference    gold/ds_v1_adj1" in words
        and "made from    capture cap_1" in words,
        words,
    )  # fmt: skip
    gone = evh("dataset-show", "nope_v1")
    check(
        "dataset-show of a dataset that does not exist is refused, naming those there are",
        gone.returncode == 1 and "ERROR (not-found): no dataset 'nope_v1': one of ds_v1" in gone.stderr,
        gone.stderr[-200:],
    )

    # -- fieldsets and failure modes
    fl = result(evh("fieldset-list", "--json"))["fieldsets"]
    check(
        "fieldset-list: the fields counted, the datasets that use it, its file",
        fl == [{"fieldset": "f1", "description": "the facts", "fields": 1, "datasets": ["ds_v1", "ds_v2"],
                "file": "data/fields/f1.yaml"}],
        fl,
    )  # fmt: skip
    fs = result(evh("fieldset-show", "f1", "--json"))
    check(
        "fieldset-show: its record, file and datasets",
        fs["record"]["fields"] == [{"name": "kind", "type": "text"}] and fs["datasets"] == ["ds_v1", "ds_v2"],
        fs,
    )
    path = proj / "data" / "fields" / "f1.yaml"
    if path.is_file():
        path.write_text("# the facts\n" + path.read_text())
    else:
        _runstore.write_text(proj, "fields/f1.yaml", "# the facts\n" + stored("fields/f1.yaml"))
    before = stored("fields/f1.yaml")
    again = evh("fieldset-new", "f1", "--set", "description=x")
    bad = evh("fieldset-set", "f1", "--set", "fields.0.type=sideways")
    nope = evh("fieldset-set", "nope", "--set", "description=x")
    check(
        "fieldset-new refuses an id that is taken, fieldset-set a record that does not check and an id that does not "
        "exist; nothing written",
        again.returncode == 1 and "ERROR (would-overwrite)" in again.stderr
        and bad.returncode == 1 and "ERROR (invalid-file)" in bad.stderr and "fields.0.type" in bad.stderr
        and nope.returncode == 1 and "ERROR (not-found): no fieldset 'nope'" in nope.stderr
        and stored("fields/f1.yaml") == before,
        (again.stderr[-150:], bad.stderr[-200:], nope.stderr[-150:]),
    )  # fmt: skip
    changed = evh("fieldset-set", "f1", "--set", "description=the facts each item carries")
    text = stored("fields/f1.yaml")
    check(
        "fieldset-set changes one field and keeps the file's comments",
        changed.returncode == 0 and "# the facts" in text and "the facts each item carries" in text
        and "f1: saved" in changed.stdout,
        (changed.stderr[-200:], text),
    )  # fmt: skip
    fm = result(evh("failure-modes-list", "--json"))["failure_modes"]
    check(
        "failure-modes-list: the modes counted, the tag sets made from it, its file",
        fm == [{"failure_modes": "summaries", "description": "ways a summary is wrong", "modes": 2,
                "tag_sets": ["ds_v1/first"], "file": "data/failure-modes/summaries.yaml"}],
        fm,
    )  # fmt: skip
    fms = result(evh("failure-modes-show", "summaries", "--json"))
    check(
        "failure-modes-show: its record and the tag sets made from it",
        [m["id"] for m in fms["record"]["modes"]] == ["too-long", "misses-ask"] and fms["tag_sets"] == ["ds_v1/first"],
        fms,
    )  # fmt: skip
    fmset = evh("failure-modes-set", "summaries", "--set", "modes.1.label=Misses the ask")
    fmbad = evh("failure-modes-set", "summaries", "--set", "modes.0.id=Too Long")
    fmagain = evh("failure-modes-new", "summaries", "--set", "modes.0.id=x")
    check(
        "failure-modes-set changes a mode; an id that does not check and an id that is taken are refused",
        fmset.returncode == 0 and "Misses the ask" in stored("failure-modes/summaries.yaml")
        and fmbad.returncode == 1 and "ERROR (invalid-file)" in fmbad.stderr
        and fmagain.returncode == 1 and "ERROR (would-overwrite)" in fmagain.stderr,
        (fmset.stderr[-150:], fmbad.stderr[-150:], fmagain.stderr[-150:]),
    )  # fmt: skip
    words = evh("failure-modes-show", "summaries").stdout
    check(
        "failure-modes-show in words: a mode a line",
        "mode         too-long" in words and "mode         misses-ask: Misses the ask" in words
        and "tag sets     ds_v1/first" in words,
        words,
    )  # fmt: skip

    # -- label sets, tag sets
    ls = result(evh("label-set-list", "ds_v1", "--json"))
    check(
        "label-set-list: a dataset's sets with who gave them, how many and when; another dataset's none",
        [(s["set"], s["kind"], s["items"]) for s in ls["label_sets"]]
        == [("ds_v1/gold_ds_v1", "person", 1), ("ds_v1/rule_cap", "rule", 1)]
        and result(evh("label-set-list", "ds_v2", "--json"))["label_sets"] == [],
        ls,
    )  # fmt: skip
    lss = result(evh("label-set-show", "ds_v1", "rule_cap", "--json"))
    check(
        "label-set-show: the record without the items map (the count instead), the folder and the references "
        "promoted from it",
        lss["items"] == 1 and "items" not in lss["record"] and lss["record"]["source"]["capture"] == "cap_1"
        and lss["record"]["note"] == "n" and lss["folder"] == "data/labels/ds_v1/rule_cap"
        and [x["reference"] for x in lss["references"]] == ["silver/ds_v1_rule"],
        lss,
    )  # fmt: skip
    lss = result(evh("label-set-show", "ds_v1", "gold_ds_v1", "--json"))
    check(
        "label-set-show: a reference promoted under another name (no label set) is not this set's",
        [x["reference"] for x in lss["references"]] == ["gold/ds_v1"],
        lss["references"],
    )
    nols = evh("label-set-show", "ds_v1", "nope")
    nods = evh("label-set-list", "nope_v1")
    check(
        "an unknown label set or dataset is refused",
        nols.returncode == 1 and "ERROR (not-found): no label set 'ds_v1/nope'" in nols.stderr
        and nods.returncode == 1 and "ERROR (not-found): no dataset 'nope_v1'" in nods.stderr,
        (nols.stderr[-200:], nods.stderr[-200:]),
    )  # fmt: skip
    check(
        "label-set-show in words: where the labels came from and the references",
        "ds_v1/rule_cap  1 items" in evh("label-set-show", "ds_v1", "rule_cap").stdout
        and "reference    silver/ds_v1_rule" in evh("label-set-show", "ds_v1", "rule_cap").stdout,
        evh("label-set-show", "ds_v1", "rule_cap").stdout,
    )  # fmt: skip
    ts = result(evh("tag-set-list", "ds_v1", "--json"))["tag_sets"]
    check(
        "tag-set-list: the list each is named from, the runs and the outputs tagged",
        ts == [{"set": "ds_v1/first", "dataset": "ds_v1", "failure_modes": "summaries", "runs": 2, "tagged": 2,
                "created_at": "2026-11-14T02:00:00Z"}],
        ts,
    )  # fmt: skip
    tss = result(evh("tag-set-show", "ds_v1", "first", "--json"))
    check(
        "tag-set-show: the record without the tags, and each failure mode counted",
        tss["modes"] == {"too-long": 2, "misses-ask": 1} and "runs" not in tss["record"] and tss["runs"] == 2
        and tss["file"] == "data/tags/ds_v1/first/tags.json",
        tss,
    )  # fmt: skip
    check(
        "an unknown tag set is refused; a dataset with none says so",
        "ERROR (not-found): no tag set 'ds_v1/nope'" in evh("tag-set-show", "ds_v1", "nope").stderr
        and "ds_v2 has no tag sets" in evh("tag-set-list", "ds_v2").stdout,
        evh("tag-set-list", "ds_v2").stdout,
    )  # fmt: skip

    # -- references
    rl = result(evh("reference-list", "--json"))["references"]
    check(
        "reference-list: tier, dataset, items, the label set and who it came from",
        [(x["reference"], x["tier"], x["dataset"], x["items"], x["label_set"], x["kind"]) for x in rl]
        == [("gold/ds_v1", "gold", "ds_v1", 1, "ds_v1/gold_ds_v1", "person"),
            ("gold/ds_v1_adj1", "gold", "ds_v1", 1, None, "person"),
            ("silver/ds_v1_rule", "silver", "ds_v1", 1, "ds_v1/rule_cap", "rule")],
        rl,
    )  # fmt: skip
    rs = result(evh("reference-show", "gold", "ds_v1_adj1", "--json"))
    check(
        "reference-show: the manifest without its checksums (the count instead), where it came from, its folder",
        rs["items"] == 1 and "items_sha256" not in rs["record"] and rs["record"]["source"] == "fetch.py"
        and rs["label_set"] is None and rs["folder"] == "data/references/gold/ds_v1_adj1",
        rs,
    )  # fmt: skip
    words = evh("reference-show", "silver", "ds_v1_rule").stdout
    check(
        "reference-show in words: the label set and the reason",
        "label set    ds_v1/rule_cap" in words and "reason       outcomes" in words,
        words,
    )
    nor = evh("reference-show", "gold", "nope")
    badid = evh("reference-show", "gold", "..x")
    check(
        "an unknown reference is refused, and an id that is not one",
        nor.returncode == 1 and "ERROR (not-found): no reference 'gold/nope'" in nor.stderr
        and badid.returncode == 1 and "ERROR (bad-argument)" in badid.stderr,
        (nor.stderr[-150:], badid.stderr[-150:]),
    )  # fmt: skip

    # -- captures
    cl = result(evh("capture-list", "--json"))["captures"]
    check(
        "capture-list: what read it, when, how many records, the datasets and label sets made from it",
        cl == [{"capture": "cap_1", "importer": "jsonl", "captured_at": "2026-11-13T00:00:00Z", "records": 2,
                "scrubbed": False, "continues": None, "datasets": ["ds_v1"], "label_sets": ["ds_v1/rule_cap"]}],
        cl,
    )  # fmt: skip
    cs = result(evh("capture-show", "cap_1", "--json"))
    check(
        "capture-show: the record without its records (the count instead) and what was made from it",
        cs["records"] == 2 and "records" not in cs["record"] and cs["record"]["query"] == {"path": "x"}
        and cs["datasets"] == ["ds_v1"] and cs["file"] == "data/captures/cap_1/capture.json",
        cs,
    )  # fmt: skip
    nocap = evh("capture-show", "nope")
    check(
        "an unknown capture is refused",
        nocap.returncode == 1 and "ERROR (not-found): no capture 'nope': one of cap_1" in nocap.stderr,
        nocap.stderr[-200:],
    )

    # -- nothing edits what a command wrote
    check(
        "no command edits a dataset, a label set, a tag set, a reference or a capture",
        all(
            (got := evh(c, "x")).returncode == 2 and "unknown command" in got.stderr
            for c in (
                "dataset-set",
                "dataset-new",
                "label-set-set",
                "reference-set",
                "capture-set",
                "tag-set-set",
            )
        ),
        got.stderr[:100],
    )

    # -- the API gives what the command line gives
    srv, port = serve()
    try:
        pairs = {
            "dataset-list": ("/datasets", ()),
            "dataset-show": ("/datasets/ds_v1", ("ds_v1",)),
            "fieldset-list": ("/fieldsets", ()),
            "fieldset-show": ("/fieldsets/f1", ("f1",)),
            "failure-modes-list": ("/failure-modes", ()),
            "failure-modes-show": ("/failure-modes/summaries", ("summaries",)),
            "label-set-list": ("/datasets/ds_v1/label-sets", ("ds_v1",)),
            "label-set-show": ("/datasets/ds_v1/label-sets/rule_cap", ("ds_v1", "rule_cap")),
            "tag-set-list": ("/datasets/ds_v1/tag-sets", ("ds_v1",)),
            "tag-set-show": ("/datasets/ds_v1/tag-sets/first", ("ds_v1", "first")),
            "reference-list": ("/references", ()),
            "reference-show": ("/references/silver/ds_v1_rule", ("silver", "ds_v1_rule")),
            "capture-list": ("/captures", ()),
            "capture-show": ("/captures/cap_1", ("cap_1",)),
        }
        differ = [
            name
            for name, (route, args) in pairs.items()
            if call(port, "GET", route)[1].get("result") != result(evh(name, *args, "--json"))
        ]
        check("the API's resources give the command line's answer, for every read", not differ, differ)
        codes = [
            call(port, "GET", "/datasets/nope_v1")[0], call(port, "GET", "/datasets/ds_v1/label-sets/nope")[0],
            call(port, "GET", "/references/gold/nope")[0], call(port, "GET", "/captures/nope")[0],
            call(port, "GET", "/fieldsets/nope")[0], call(port, "GET", "/datasets/nope_v1/tag-sets")[0],
        ]  # fmt: skip
        check("the API answers 404 for an id that does not exist", set(codes) == {404}, codes)
        edits = [
            call(port, "PATCH", "/datasets/ds_v1", {"set": {"version": "9"}, "by": "person:api"})[0],
            call(port, "POST", "/datasets/ds_v1/label-sets/rule_cap", {"set": {}, "by": "person:api"})[0],
            call(port, "PATCH", "/references/gold/ds_v1", {"set": {"reason": "x"}, "by": "person:api"})[0],
            call(port, "PATCH", "/captures/cap_1", {"set": {"importer": "x"}, "by": "person:api"})[0],
        ]  # fmt: skip
        check(
            "the API has no edit of a dataset, a label set, a reference or a capture; nothing written",
            set(edits) == {404}
            and result(evh("dataset-show", "ds_v1", "--json"))["record"]["version"] == "1.0",
            edits,
        )
        code, body = call(
            port, "PATCH", "/fieldsets/f1", {"set": {"description": "from the API"}, "by": "person:api"}
        )
        history = [json.loads(x) for x in stored("history/fieldsets/f1.jsonl").splitlines() if x.strip()]
        check(
            "the API's fieldset edit goes through the model, recorded as who sent it",
            code == 200 and body["result"]["changed"] and history and history[-1]["by"] == "person:api"
            and "from the API" in stored("fields/f1.yaml"),
            (code, body, history[-1:]),
        )  # fmt: skip
        code, body = call(
            port, "PATCH", "/fieldsets/f1", {"set": {"fields.0.type": "sideways"}, "by": "person:api"}
        )
        code_new, _ = call(
            port, "POST", "/failure-modes/summaries", {"set": {"modes.0.id": "x"}, "by": "person:api"}
        )
        check(
            "the API refuses a record that does not check (422) and an id that is taken (409)",
            code == 422 and body.get("problems") and code_new == 409,
            (code, code_new),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
