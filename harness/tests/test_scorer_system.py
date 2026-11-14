#!/usr/bin/env python3
"""A judge that is a system (RFC-032 step 7), in the suite's store.

    python tests/test_scorer_system.py

A judge names `system: <system_id>` instead of `params`, and is read as that system's settings (under the record of the
model the system names, as a run reads them): the scorer judges a fixture with the fake provider, every verdict
carries the judge's fingerprint, and that fingerprint is the one of the same scorer written with the system's params
inline; the scorer's hash is of the file as written, so a changed system moves the fingerprint and not the hash; a judge
that names a system that does not exist, or both a system and params, is refused by load, by validate (V13) and by
`scorer-new`'s check; the schema takes a judge with `system` or with `params` and no other.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-scorer-system-"))
vroot = Path(tempfile.mkdtemp(prefix="evh-scorer-system-verdicts-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
import jsonschema  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness import judge_score as js  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model.entity import Problem  # noqa: E402
from evaluation_harness.model.scorers import SCORER  # noqa: E402

PARAMS_A = {"provider": "fake", "model": "fake-a", "family": "vendor_a", "temperature": 0.0,
            "usd_per_mtok_in": 0.0, "usd_per_mtok_out": 0.0}  # fmt: skip
#: judge b's system names a model record: the record's settings and first alias complete its params.
PARAMS_B = {
    "provider": "fake",
    "family": "vendor_b",
    "temperature": 0.0,
    "usd_per_mtok_in": 0.0,
    "usd_per_mtok_out": 0.0,
}
RECORD_B = {
    "model_id": "mdl_b",
    "kind": "llm",
    "aliases": ["fake-b"],
    "settings": {"reasoning": {"enabled": False}},
}
INLINE_B = {**PARAMS_B, "model": "fake-b", "reasoning": {"enabled": False}}
BASE = {
    "kind": "judge",
    "dataset_id": "ds",
    "task": {"source_label": "TICKET", "output_label": "SUMMARIES", "dimensions": ["accuracy", "usefulness"], "scale": [1, 5]},
    "prompt": {"file": "judge_prompt.txt"},
    "protocol": {"outputs_per_call": 2, "blinding": True, "order_seed": 0, "position_check_fraction": 0.5, "noise_check_fraction": 0.5},
}  # fmt: skip


def write(rel: str, doc: object) -> None:
    _runstore.write_text(proj, rel, yaml.safe_dump(doc, sort_keys=False))


def scorer(sid: str, judges: list) -> Path:
    """A scorer's file in the project, its path."""
    write(f"scorers/{sid}.yaml", {"scorer_id": sid, **BASE, "judges": judges})
    return proj / "data" / "scorers" / f"{sid}.yaml"


def refused(fn) -> str:
    """The message of the SystemExit fn raises, '' if it does not."""
    try:
        fn()
    except SystemExit as exc:
        return str(exc.code)
    return ""


def verdict_fps(sid: str, items: list, arms: list, articles: dict, outputs: dict) -> dict[str, set]:
    """Judge the fixture with the fake judges the scorer names; each judge's fingerprints in its verdicts."""
    sc = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")
    man = js.build_manifest(sc, "ds", "i" * 64, items, arms, articles, outputs, js.prompt_text(sc))
    vdir = vroot / sid
    st = js.run_judging(
        man, sc, js.prompt_text(sc), articles, outputs, vdir, js.real_call, 1.0, log=lambda *_: None
    )
    out: dict[str, set] = {}
    for f in sorted(vdir.glob("*/*.json")):
        out.setdefault(f.parent.name, set()).add(json.loads(f.read_text())["judge_fp"])
    out["_calls"] = {st["calls"]}
    return out


try:
    shutil.copy(HARNESS / "tutorial" / "judge_prompt.txt", proj / "judge_prompt.txt")
    _format.stamp(data=proj / "data")
    write("systems/jsys_a.yaml", {"system_id": "jsys_a", "params": PARAMS_A})
    write("systems/jsys_b.yaml", {"system_id": "jsys_b", "model_record": "mdl_b", "params": PARAMS_B})
    write("models/mdl_b.yaml", RECORD_B)
    by_system = scorer("by_system_v1", [{"id": "ja", "system": "jsys_a"}, {"id": "jb", "system": "jsys_b"}])
    inline = scorer("inline_v1", [{"id": "ja", "params": PARAMS_A}, {"id": "jb", "params": INLINE_B}])

    # -- read as the system's settings
    a, b = js.load_scorer(by_system), js.load_scorer(inline)
    check(
        "load: a judge that names a system is called with the system's params, a model record's settings and alias under them",
        a["judges"][0]["params"] == PARAMS_A
        and a["judges"][1]["params"] == INLINE_B
        and [j["params"] for j in b["judges"]] == [j["params"] for j in a["judges"]],
        [j["params"] for j in a["judges"]],
    )
    fps = [js.judge_fingerprint(j) for j in a["judges"]]
    check(
        "the fingerprint of a judge naming a system is that of the judge written with the system's params inline",
        fps == [js.judge_fingerprint(j) for j in b["judges"]] and len(set(fps)) == 2,
        fps,
    )
    check(
        "the scorer's hash is of the file as written: naming a system is not writing its params",
        a["_sha256"] != b["_sha256"] and a["judges"][0]["system"] == "jsys_a",
    )

    # -- judged with the fake provider
    items = ["i1", "i2"]
    arms = [{"config_id": f"{k}_v1", "run": f"{k}_v1_r", "dir": None, "family": k} for k in ("a", "b")]
    articles = {i: f"Ticket {i}: the customer cannot log in." for i in items}
    outputs = {x["config_id"]: {i: f"{x['config_id']} summary of {i}" for i in items} for x in arms}
    got_s = verdict_fps("by_system_v1", items, arms, articles, outputs)
    got_i = verdict_fps("inline_v1", items, arms, articles, outputs)
    check(
        "a scorer whose judges name systems judges the fixture with the fake provider, a verdict per judge and block",
        got_s["_calls"] == got_i["_calls"]
        and got_s["_calls"] != {0}
        and set(got_s) == {"ja", "jb", "_calls"},
        got_s,
    )
    check(
        "every verdict carries its judge's fingerprint, the same as the scorer with the params inline",
        got_s["ja"] == {fps[0]} and got_s["jb"] == {fps[1]} and got_s == got_i,
        (got_s, got_i, fps),
    )

    # -- a system that changes: the fingerprint moves, the scorer's hash does not
    write("systems/jsys_a.yaml", {"system_id": "jsys_a", "params": {**PARAMS_A, "temperature": 0.7}})
    c = js.load_scorer(by_system)
    check(
        "a changed system moves its judge's fingerprint (its verdicts are read as another judge's) and not the scorer's hash",
        js.judge_fingerprint(c["judges"][0]) != fps[0]
        and js.judge_fingerprint(c["judges"][1]) == fps[1]
        and c["_sha256"] == a["_sha256"],
    )
    write("systems/jsys_a.yaml", {"system_id": "jsys_a", "params": PARAMS_A})

    # -- refused
    ghost = scorer("ghost_v1", [{"id": "ja", "system": "no_such_system"}, {"id": "jb", "system": "jsys_b"}])
    both = scorer(
        "both_v1", [{"id": "ja", "system": "jsys_a", "params": PARAMS_A}, {"id": "jb", "params": INLINE_B}]
    )
    norecord = scorer("norecord_v1", [{"id": "ja", "system": "jsys_a"}, {"id": "jb", "system": "jsys_c"}])
    write("systems/jsys_c.yaml", {"system_id": "jsys_c", "model_record": "no_such_model", "params": PARAMS_B})
    msg_g, msg_b, msg_r = (refused(lambda p=p: js.load_scorer(p)) for p in (ghost, both, norecord))
    check(
        "load refuses a judge naming a system that does not exist, naming the judge, the file and the systems there are",
        "ghost_v1.yaml: judge 'ja': no system 'no_such_system': one of " in msg_g
        and "jsys_a" in msg_g
        and msg_g.startswith("ERROR (not-found)"),
        msg_g,
    )
    check(
        "load refuses a judge that names a system and params, and a system whose model record is not there",
        "both_v1.yaml: judge 'ja': names a system and params; name one" in msg_b
        and "norecord_v1.yaml: judge 'jb': system 'jsys_c'" in msg_r
        and "no_such_model" in msg_r,
        (msg_b, msg_r),
    )
    probs = vt.scorer_problems(proj / "data" / "scorers")
    check(
        "V13: the scorers that do not load are named with the reason, the ones that do are clean",
        sum(
            1
            for p in probs
            if p.startswith("ghost_v1.yaml: does not load") and "no system 'no_such_system'" in p
        )
        == 1
        and sum(1 for p in probs if p.startswith("both_v1.yaml: does not load")) == 1
        and sum(1 for p in probs if p.startswith("norecord_v1.yaml: does not load")) == 1
        and not any(p.startswith(("by_system_v1", "inline_v1")) for p in probs),
        probs,
    )
    record = yaml.safe_load(_runstore.read_text(proj, "scorers/by_system_v1.yaml"))
    try:
        SCORER.save(
            "new_v1",
            {
                **record,
                "scorer_id": "new_v1",
                "judges": [{"id": "ja", "system": "nope_sys"}, record["judges"][1]],
            },
            "person:t",
            new=True,
        )
        saved = ""
    except Problem as exc:
        saved = str(exc)
    check(
        "a scorer whose judge names a system that is not there is not saved, the problem at the judge's field",
        "judges.0.system" in saved
        and "no system 'nope_sys'" in saved
        and not _runstore.is_file(proj, "scorers/new_v1.yaml"),
        saved,
    )

    # -- the schema
    schema = json.loads((HARNESS / "schemas" / "scorer.schema.json").read_text())
    ok = jsonschema.Draft202012Validator(schema)
    doc = yaml.safe_load(_runstore.read_text(proj, "scorers/by_system_v1.yaml"))
    neither = {**doc, "judges": [{"id": "ja"}, doc["judges"][1]]}
    twice = {**doc, "judges": [{"id": "ja", "system": "jsys_a", "params": PARAMS_A}, doc["judges"][1]]}
    badid = {**doc, "judges": [{"id": "ja", "system": "has space"}, doc["judges"][1]]}
    check(
        "the schema takes a judge with a system or with params, not both, not neither, and a system id that is one",
        ok.is_valid(doc) and ok.is_valid(yaml.safe_load(_runstore.read_text(proj, "scorers/inline_v1.yaml")))
        and not ok.is_valid(neither) and not ok.is_valid(twice) and not ok.is_valid(badid),
    )  # fmt: skip
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(vroot, ignore_errors=True)
sys.exit(summary())
