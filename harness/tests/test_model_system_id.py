#!/usr/bin/env python3
"""A run's `config_id` names its system (RFC-032 step 8): the format 6 migration, in the suite's store.

    python tests/test_model_system_id.py

A format 5 project made here holds every kind of record that carries the key. `evh migrate` moves it to format 6, and
then:

- the key is `system_id` in a run's run.json, a score's metrics.json and `unset`, a faithfulness record, a study log's
  lines (an imported trial, which names no system, keeps a null one) and a sealed dataset's unseals; each file reads as
  it did but for the key (its other keys in their order), and the run reads back through the model with `system_id`;
- the keys inside a hash keep their name, their files byte for byte: the run's fingerprint, a judging set, a label set
  and a reference's manifest, and the hashes made of them are the ones they were (the set's id, the reference's
  digest, the label set's digest);
- a migrated project migrates to nothing, and the step run again on format 6 data changes nothing;
- refused, nothing written: a record with both keys, a run of a system the project does not have, an unseal of one.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-sysid-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runfix  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _fingerprint, _format, _outputs, _store, judge_score  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.model import runs as R  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-system-id")
DATA = proj / "data"
ROWS = [{"item_id": "i1", "acc": 1.0}]
FP = {"version": 5, "arm": {"config_id": "sys_a", "labels": None}, "hash": "f" * 64}


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
        text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def put(rel: str, doc: object, *, sort: bool = True, ascii_: bool = True) -> None:
    """A JSON file as the harness writes one (`write_json`: indented, keys sorted), or as run.json is (as it comes)."""
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2, sort_keys=sort, ensure_ascii=ascii_) + "\n")


def jsonl(rel: str, docs: list[dict]) -> None:
    _runstore.write_text(proj, rel, "".join(json.dumps(d, sort_keys=True) + "\n" for d in docs))


def tree() -> dict[str, bytes]:
    return {r: _runstore.read_bytes(proj, r) for r in _runstore.files_under(proj, "")}


def build() -> None:
    """A format 5 project with each record that carries the key, and each kept place."""
    _outputs.reset()
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir()
    evh("init", "--store", store_under_test())
    _runstore.write_text(proj, "project.yaml", "format: 5\n")
    for s in ("sys_a", "sys_b"):
        _runstore.write_text(proj, f"systems/{s}.yaml", f"system_id: {s}\n")
    # a trial's system lives in its study's folder
    _runstore.write_text(proj, "studies/g1/s1/s1-t1.yaml", "system_id: s1-t1\n")
    # run 1: run.json as write_json lays it out (keys sorted); run 2: in the order it came, a non-ASCII text escaped
    _runfix.put_run(DATA, {"run_id": "a_1", "config_id": "sys_a", "dataset_id": "ds_v1", "scores": {"acc": 1.0},
                           "primary_metric": "acc", "fingerprint": FP}, ROWS, scorer="s1")  # fmt: skip
    put("runs/a_1/run.json", {"run_id": "a_1", "config_id": "sys_a", "dataset_id": "ds_v1", "fingerprint": FP,
                              "purpose": "run", "note": "z"})  # fmt: skip
    put("runs/b_1/run.json", {"run_id": "b_1", "dataset_id": "ds_v1", "note": "café", "config_id": "sys_b",
                              "purpose": "run", "fingerprint": {**FP, "arm": {"config_id": "sys_b", "labels": None}}},
        sort=False)  # fmt: skip
    # a score that names the key itself, and one whose record unsets it
    put("runs/a_1/scores/s1@none/score.json", {"scorer": "s1", "reference": None, "label": "", "first": True,
                                               "unset": ["config_id", "n_items"]})  # fmt: skip
    put("runs/a_1/scores/s1@none/metrics.json", {"config_id": "sys_a", "scores": {"acc": 1.0}})
    put(
        "faithfulness/code1/1.json",
        {"n": 1, "model_id": "code1", "config_id": "sys_a", "dataset_id": "ds_v1"},
    )
    jsonl("studies/g1/s1.events.jsonl", [
        {"event": "start", "round": "r1", "baseline": "sys_a"},
        {"event": "trial", "k": 1, "config_id": "s1-t1", "outcome": "kept"},
        {"event": "trial", "k": 2, "config_id": None, "imported": True, "outcome": "kept"},
        {"event": "end", "reason": "done"},
    ])  # fmt: skip
    put("datasets/ds_v1_test.json", {"dataset_id": "ds_v1_test", "sealed": {"by": "x"}, "unsealed": [
        {"config_id": "sys_a", "at": "2026-11-01T00:00:00Z", "reason": "r", "commit": "c", "hypothesis": {"against": "sys_b"}},
        {"config_id": "sys_b", "at": "2026-11-02T00:00:00Z", "reason": "r", "commit": "c", "hypothesis": {"against": "sys_a"}},
    ]})  # fmt: skip
    # what stays: a judging set (its id hashes the key), a label set, a reference's manifest
    js_doc = {
        "judging_set_id": "set1",
        "dataset_id": "ds_v1",
        "arms": [{"config_id": "sys_a", "run": "a_1", "outputs_sha256": "0" * 64}],
    }
    js_doc["judging_set_sha256"] = judge_score.manifest_hash(js_doc)
    put("judging-sets/set1.json", js_doc)
    src = {
        "kind": "model",
        "run_id": "a_1",
        "config_id": "sys_a",
        "fingerprint_hash": "f" * 64,
        "build": {"ref": "x"},
    }
    put("labels/ds_v1/set1/labels.json", {"dataset_id": "ds_v1", "set": "set1", "source": src, "items": {}})
    put("references/silver/ds_v1/manifest.json", {"dataset_id": "ds_v1", "authored_by": "sys_a", "model": "m",
        "from_run": src, "promoted_from": {"labels": "set1", "dataset_id": "ds_v1", "source": src}, "caveat": "c"})  # fmt: skip
    _runstore.write_text(proj, "references/silver/ds_v1/i1.txt", "text\n")


def digests() -> dict:
    return {
        "reference": _fingerprint.references_digest(proj, "silver/ds_v1", DATA),
        "labels": _fingerprint.references_digest(proj, "labels/ds_v1/set1", DATA),
        "set": judge_score.manifest_hash(_runstore.read_json(proj, "judging-sets/set1.json")),
    }


def renamed(doc: dict) -> dict:
    """`doc` as the step should leave it: the top-level key of a record named `system_id`, in the same place."""
    return {("system_id" if k == "config_id" else k): v for k, v in doc.items()}


KEPT = ("judging-sets/set1.json", "labels/ds_v1/set1/labels.json", "references/silver/ds_v1/manifest.json",
        "references/silver/ds_v1/i1.txt")  # fmt: skip

try:
    build()
    before = tree()
    hashes = digests()
    dry = evh("migrate", "--dry-run")
    _outputs.reset()
    check(
        "--dry-run names what it would rename, by kind, and writes nothing",
        dry.returncode == 0
        and "7 file(s) renamed `config_id` to `system_id`" in dry.stdout
        and "faithfulness records" in dry.stdout
        and "study logs" in dry.stdout
        and tree() == before,
        (dry.stdout + dry.stderr)[-500:],
    )
    m = evh("migrate")
    _outputs.reset()
    after = tree()
    check(
        "evh migrate brings it to the release's format",
        m.returncode == 0 and f"format: {_format.FORMAT}" in _runstore.read_text(proj, "project.yaml"),
        (m.stdout + m.stderr)[-500:],
    )
    check("this release's format is the one that renames the key", _format.FORMAT >= 6, _format.FORMAT)

    def doc(t: dict[str, bytes], rel: str) -> Any:
        return json.loads(t[f"{rel}"].decode())

    for rel in ("runs/a_1/run.json", "runs/b_1/run.json", "runs/a_1/scores/s1@none/metrics.json",
                "faithfulness/code1/1.json"):  # fmt: skip
        want = renamed(doc(before, rel))
        got = doc(after, rel)
        # a file laid out with its keys sorted stays sorted (system_id moves to its place); one in the order its
        # keys came keeps that order
        in_order = list(got) == (list(want) if rel == "runs/b_1/run.json" else sorted(want))
        check(
            f"{rel}: the key is system_id, the file otherwise as it was, in its layout",
            got == want and in_order,
            (got, want),
        )
    check(
        "the layout is kept: run b_1 (keys as they came, a non-ASCII text escaped) is written as it was, only the key changed",
        after["runs/b_1/run.json"].decode()
        == before["runs/b_1/run.json"]
        .decode()
        .replace('"config_id": "sys_b",\n  "purpose"', '"system_id": "sys_b",\n  "purpose"', 1),
        after["runs/b_1/run.json"].decode()[:300],
    )
    sc = doc(after, "runs/a_1/scores/s1@none/score.json")
    check("a score's `unset` names system_id", sc["unset"] == ["system_id", "n_items"], sc)
    us = doc(after, "datasets/ds_v1_test.json")["unsealed"]
    check(
        "a sealed dataset's unseals name system_id, nothing else changed",
        [u.get("system_id") for u in us] == ["sys_a", "sys_b"]
        and not any("config_id" in u for u in us)
        and [u["hypothesis"] for u in us] == [{"against": "sys_b"}, {"against": "sys_a"}],
        us,
    )
    lines = [json.loads(x) for x in after["studies/g1/s1.events.jsonl"].decode().splitlines()]
    check(
        "a study log's trial lines name system_id; an imported trial keeps its null one; other lines are untouched",
        [x.get("system_id", "-") for x in lines] == ["-", "s1-t1", None, "-"]
        and not any("config_id" in x for x in lines)
        and after["studies/g1/s1.events.jsonl"].decode().splitlines()[0]
        == before["studies/g1/s1.events.jsonl"].decode().splitlines()[0],
        lines,
    )
    run = R.run("a_1") or {}
    check("the run reads back through the model with system_id", run.get("system_id") == "sys_a" and "config_id" not in run, run)  # fmt: skip

    check(
        "what is hashed keeps its key, byte for byte: the judging set, the label set, the reference's manifest",
        all(after[r] == before[r] for r in KEPT),
        [r for r in KEPT if after[r] != before[r]],
    )
    check(
        "the fingerprint's arm keeps config_id (the run's hash is made of it)",
        doc(after, "runs/a_1/run.json")["fingerprint"]["arm"] == {"config_id": "sys_a", "labels": None}
        and doc(after, "runs/b_1/run.json")["fingerprint"]["arm"]["config_id"] == "sys_b",
    )
    check("the hashes made of those are the ones they were: the reference, the label set, the judging set's id", digests() == hashes, (digests(), hashes))  # fmt: skip
    changed = sorted(r for r in after if after[r] != before.get(r))
    check(
        "nothing else changed: the renamed files and the format stamp",
        changed
        == sorted(
            [
                "project.yaml",
                "runs/a_1/run.json",
                "runs/b_1/run.json",
                "runs/a_1/scores/s1@none/metrics.json",
                "runs/a_1/scores/s1@none/score.json",
                "faithfulness/code1/1.json",
                "datasets/ds_v1_test.json",
                "studies/g1/s1.events.jsonl",
            ]
        ),
        changed,
    )

    again = evh("migrate")
    _outputs.reset()
    check("a migrated project migrates to nothing", again.returncode == 0 and tree() == after and "nothing to do" in again.stdout, (again.stdout + again.stderr)[-300:])  # fmt: skip
    _runstore.write_text(proj, "project.yaml", "format: 5\n")
    third = evh("migrate")
    _outputs.reset()
    check(
        "the step run again on migrated data says so and changes nothing",
        third.returncode == 0
        and "0 changed: already in this format" in third.stdout
        and {r: b for r, b in tree().items() if r != "project.yaml"}
        == {r: b for r, b in after.items() if r != "project.yaml"},
        (third.stdout + third.stderr)[-300:],
    )

    # refusals: nothing written
    def refused(why: str, says: str, mutate: Callable[[], None]) -> None:
        build()
        mutate()
        snap = tree()
        r = evh("migrate")
        _outputs.reset()
        check(
            f"refused: {why}, nothing written",
            r.returncode != 0 and says in r.stderr and tree() == snap,
            r.stderr[-400:],
        )

    refused(
        "a run record with both keys",
        "has both `config_id` and `system_id`",
        lambda: put(
            "runs/b_1/run.json",
            {
                "run_id": "b_1",
                "dataset_id": "ds_v1",
                "config_id": "sys_b",
                "system_id": "sys_b",
                "purpose": "run",
            },
        ),
    )
    refused(
        "a run of a system the project does not have",
        "`config_id` is 'gone_v1', which is not the id of a system",
        lambda: put(
            "runs/b_1/run.json",
            {"run_id": "b_1", "dataset_id": "ds_v1", "config_id": "gone_v1", "purpose": "run"},
        ),
    )
    refused(
        "an unseal of a system the project does not have",
        "unsealed[1]",
        lambda: put(
            "datasets/ds_v1_test.json",
            {
                "dataset_id": "ds_v1_test",
                "sealed": {"by": "x"},
                "unsealed": [
                    {"config_id": "sys_a", "at": "a", "reason": "r", "commit": "c", "hypothesis": {}},
                    {"config_id": "nobody", "at": "a", "reason": "r", "commit": "c", "hypothesis": {}},
                ],
            },
        ),
    )
    refused(
        "a study's trial line with both keys",
        "s1.events.jsonl:2",
        lambda: jsonl(
            "studies/g1/s1.events.jsonl",
            [{"event": "start"}, {"event": "trial", "config_id": "s1-t1", "system_id": "s1-t1"}],
        ),
    )
finally:
    _outputs.reset()
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
