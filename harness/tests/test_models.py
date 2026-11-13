#!/usr/bin/env python3
"""Model records (RFC-020) and their deployments (RFC-032 step 2): loading a model with its deployments, the weights
facts the arms page reads, the schemas, what V18 catches, and two writers each keeping their change.

python tests/test_models.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsonschema
import yaml
from _model_records import files_of, stamp
from evaluation_harness import _models
from evaluation_harness._check import check, summary


def write(base: Path, name: str, doc: dict) -> None:
    """The model's files under `base` (its record named `name`, whatever its id says), stamped."""
    for rel, text in files_of(doc).items():
        if rel.startswith("models/"):
            rel = f"models/{name}.yaml"
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(text)


with tempfile.TemporaryDirectory() as td:
    data = Path(td)
    stamp(data)
    check("no records: no facts, no problems", _models.facts(data) == {} and _models.problems(data) == [])
    write(
        data,
        "gemma4-12b",
        {
            "model_id": "gemma4-12b",
            "kind": "llm",
            "aliases": ["gemma4:12b", "eval-gemma-12b"],
            "weights": "open",
            "licence": "Apache-2.0",
        },
    )
    write(data, "span", {"model_id": "span", "kind": "ml", "aliases": ["org/span"]})
    facts = _models.facts(data)
    check(
        "facts: every alias of a record with weights", set(facts) == {"gemma4:12b", "eval-gemma-12b"}, facts
    )
    check("facts: weights and licence", facts["gemma4:12b"] == {"weights": "open", "licence": "Apache-2.0"})
    check("by_alias finds the record", _models.by_alias(data)["org/span"]["model_id"] == "span")
    check("find by id", (_models.find(data, "gemma4-12b") or {}).get("kind") == "llm")
    check("a clean set has no problems", _models.problems(data) == [], _models.problems(data))
    write(
        data,
        "set",
        {"model_id": "set", "kind": "llm", "aliases": ["set:1b"], "settings": {"reasoning_effort": "none"}},
    )
    got = _models.resolve(
        {"config_id": "a", "model_record": "set", "params": {"reasoning_effort": "low", "max_tokens": 2048}},
        data,
    )
    check(
        "resolve: the record's settings under the config's params, the config wins, model from the alias",
        got["params"] == {"reasoning_effort": "low", "max_tokens": 2048, "model": "set:1b"},
        got,
    )
    check(
        "resolve: a config naming no record is unchanged",
        _models.resolve({"params": {"x": 1}}, data) == {"params": {"x": 1}},
    )
    try:
        _models.resolve({"model_record": "nope"}, data)
        raised = False
    except ValueError:
        raised = True
    check("resolve: a record that does not exist is refused", raised)
    write(data, "other", {"model_id": "not-other", "kind": "llm", "aliases": ["gemma4:12b"]})
    probs = " | ".join(_models.problems(data))
    check("a file not named by its id is a problem", "is not the file's name" in probs, probs)
    check("an alias two records claim is a problem", "claimed by" in probs, probs)

with tempfile.TemporaryDirectory() as td:
    data = Path(td)
    stamp(data)
    write(
        data,
        "dep",
        {
            "model_id": "dep",
            "kind": "llm",
            "aliases": ["dep:1b"],
            "settings": {"reasoning_effort": "none"},
            "deployments": [{"id": "mac", "where": "mac"}, {"id": "dgx", "where": "dgx"}],
        },
    )
    rec = _models.find(data, "dep") or {}
    check(
        "find: a model with its deployments, in the order it lists them, each its own record",
        [d["id"] for d in rec.get("deployments") or []] == ["mac", "dgx"]
        and (data / "deployments" / "dep" / "dgx.yaml").is_file()
        and "deployments" not in yaml.safe_load((data / "models" / "dep.yaml").read_text()),
        rec,
    )
    check("deployment_of: by id", (_models.deployment_of(rec, "dgx") or {}).get("where") == "dgx")
    check("deployment_of: an id the record lacks is None", _models.deployment_of(rec, "x3") is None)
    got = _models.resolve({"config_id": "a", "model_record": "dep", "deployment": "mac", "params": {}}, data)
    check(
        "resolve: a config naming a deployment keeps both, and takes the record's settings",
        got["model_record"] == "dep"
        and got["deployment"] == "mac"
        and got["params"]["reasoning_effort"] == "none",
        got,
    )
    for name, cfg, words in (
        ("a deployment the record lacks", {"model_record": "dep", "deployment": "x3"}, "no such deployment (known: mac, dgx)"),
        ("a deployment without a record", {"deployment": "mac"}, "names no model_record"),
    ):  # fmt: skip
        try:
            _models.resolve(cfg, data)
            msg = ""
        except ValueError as exc:
            msg = str(exc)
        check(f"resolve: {name} is refused", words in msg, msg)
    (data / "deployments" / "ghost").mkdir(parents=True)
    (data / "deployments" / "ghost" / "x.yaml").write_text(
        yaml.safe_dump({"model_id": "ghost", "deployment_id": "x", "where": "x"})
    )
    (data / "deployments" / "dep" / "lost.yaml").write_text(
        yaml.safe_dump({"model_id": "dep", "deployment_id": "other", "where": "x"})
    )
    probs = " | ".join(_models.problems(data))
    check(
        "a deployment of no model, or not named by its folder and file, is a problem",
        "deployments/ghost/x.yaml: no model 'ghost'" in probs
        and "deployments/dep/lost.yaml: model_id and deployment_id" in probs,
        probs,
    )

schemas = Path(__file__).resolve().parents[1] / "schemas"
model_v = jsonschema.Draft202012Validator(json.loads((schemas / "model.schema.json").read_text()))
dep_v = jsonschema.Draft202012Validator(json.loads((schemas / "deployment.schema.json").read_text()))
rec = {"model_id": "m", "kind": "llm", "aliases": ["m"]}
dep = {
    "model_id": "m",
    "deployment_id": "mac",
    "where": "mac",
    "backend": "metal",
    "checks": [{"kind": "onboarding", "status": "pass", "at": "2026-10-31"}],
}
hosted = {
    "model_id": "m",
    "deployment_id": "or",
    "where": "openrouter",
    "backend": "hosted",
    "provider_routing": ["nebius"],
}
check(
    "schema: a deployment has its model, its id, a backend, a provider route and its checks",
    not list(dep_v.iter_errors(dep)) and not list(dep_v.iter_errors(hosted)),
)
check("schema: a deployment needs its model and its id", bool(list(dep_v.iter_errors({"where": "mac"}))))
check(
    "schema: a check has a kind of the three, and a time",
    bool(list(dep_v.iter_errors({**dep, "checks": [{"kind": "guess", "at": "x"}]})))
    and bool(list(dep_v.iter_errors({**dep, "checks": [{"kind": "smoke"}]}))),
)
check(
    "schema: a model holds no deployments and no smokes",
    bool(list(model_v.iter_errors({**rec, "deployments": []})))
    and bool(list(model_v.iter_errors({**rec, "smokes": {}}))),
)
check("schema: builds are gone", bool(list(model_v.iter_errors({**rec, "builds": [{"where": "mac"}]}))))
check(
    "schema: onboarding is a deployment's check, not the model's",
    bool(list(model_v.iter_errors({**rec, "onboarding": {"status": "pass", "at": "2026-10-31"}}))),
)


# Two commands writing one record each keep their own change (model-onboard on two machines, two arm-smokes):
# each applies its change to the record as it is on disk when it writes, not to the copy it read at its start.
with tempfile.TemporaryDirectory() as td:
    data = Path(td) / "data"
    stamp(data)
    write(
        data,
        "two",
        {
            "model_id": "two",
            "kind": "llm",
            "aliases": ["two:1b"],
            "deployments": [{"id": "here", "where": "here"}],
        },
    )
    stale = _models.find(data, "two")  # what both commands read when they started
    for cid, status, at in (("arm_a", "pass", "01"), ("arm_b", "check", "02"), ("arm_a", "check", "03")):
        _models.add_check(
            data,
            "two",
            "here",
            {"kind": "smoke", "system": cid, "status": status, "at": f"2026-11-13T{at}:00:00Z"},
        )
    got = _models.find(data, "two") or {}
    checks = yaml.safe_load((data / "deployments" / "two" / "here.yaml").read_text())["checks"]
    check(
        "add_check: each check kept, none written over, each naming who made it; the view gives each arm's latest smoke",
        len(checks) == 3
        and {k: {f: v for f, v in s.items() if f != "by"} for k, s in (got.get("smokes") or {}).items()}
        == {
            "arm_a": {"status": "check", "at": "2026-11-13T03:00:00Z"},
            "arm_b": {"status": "check", "at": "2026-11-13T02:00:00Z"},
        }
        and all(c.get("by") for c in checks)
        and "smokes" not in (stale or {}),
        (checks, got.get("smokes")),
    )
    _models.update_record(
        data, "two", lambda d: d.setdefault("history", []).append({"at": "a", "what": "one"})
    )
    _models.update_record(
        data, "two", lambda d: d.setdefault("history", []).append({"at": "b", "what": "two"})
    )
    check(
        "a deployment's record names no actor of its own: its checks name who made them",
        "actor" not in yaml.safe_load((data / "deployments" / "two" / "here.yaml").read_text()),
    )
    check(
        "update_record: the second change keeps the first",
        [h["what"] for h in (_models.find(data, "two") or {}).get("history") or []] == ["one", "two"],
    )
    try:
        _models.update_record(data, "two", lambda d: d.__setitem__("smokes", {}))
        refused = ""
    except ValueError as exc:
        refused = str(exc)
    check(
        "update_record: putting smokes back into the model is refused",
        "records of their own" in refused,
        refused,
    )

acc_rec = {
    "accepted": {"reasoning": "it cannot stop"},
    "deployments": [
        {"id": "hosted", "accepted": {"where it ran": "a gateway has no build to pin"}},
        {"id": "x3"},
    ],
}
acc_flags = ["reasoning: 3 calls", "where it ran: not pinned", "determinism: differs"]
check(
    "split_accepted: the record's kinds, and the named deployment's, are accepted; the rest are left",
    _models.split_accepted(acc_rec, acc_flags, "hosted")
    == (["determinism: differs"], ["reasoning: 3 calls", "where it ran: not pinned"]),
)
check(
    "split_accepted: another deployment's acceptance does not carry over",
    _models.split_accepted(acc_rec, acc_flags, "x3")
    == (["where it ran: not pinned", "determinism: differs"], ["reasoning: 3 calls"])
    and _models.split_accepted(acc_rec, acc_flags)[1] == ["reasoning: 3 calls"],
)

sys.exit(summary())
