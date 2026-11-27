#!/usr/bin/env python3
"""A model record names the actor that made or changed it (RFC-027), as a round or a dataset does.

    python tests/test_model_actor.py

`evh model-new` and `evh model-set` with EVH_ACTOR and EVH_FOR set: the record's `actor` is that agent and the person it
acted for, so `evh validate` has no record to note as naming no actor; a change by `--by` replaces it, and a
change that changes nothing leaves it. A system file has no actor field (it is fingerprinted); `evh validate` counts none.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli
from evaluation_harness._check import check, summary

proj = Path(tempfile.mkdtemp(prefix="evh-model-actor-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-model-actor")
for k in ("EVAL_DATA_DIR", "EVH_ACTOR", "EVH_FOR"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")


def evh(*args: str, **extra: str):
    return _cli.run(proj, {**env, **extra}, *args)


def out(r) -> str:
    return (r.stdout + r.stderr)[-400:]


AGENT = {"EVH_ACTOR": "agent:claude", "EVH_FOR": "person:marko"}
WHO = {"type": "agent", "name": "claude", "for": "marko", "from": "environment"}

try:
    r = evh("init", "--store", env["EVAL_STORE"])
    check("setup: a project", r.returncode == 0, out(r))
    r = evh("model-new", "m1", "--set", "kind=llm", "--set", "aliases.0=m:1", **AGENT)
    rec = evh("model-show", "m1", "--json", **AGENT)
    got = (json.loads(rec.stdout).get("result") or {}).get("record") if rec.returncode == 0 else {}
    check(
        "model-new: the record names the agent and whom it acted for",
        (got or {}).get("actor") == WHO,
        out(r) + json.dumps(got),
    )
    r = evh("system-new", "s1", "--set", "params.provider=echo", **AGENT)
    check("system-new: made, and validate counts no system as naming no actor", r.returncode == 0, out(r))
    r = evh("model-set", "m1", "--set", "name=Model one", "--by", "person:ana")
    got = json.loads(evh("model-show", "m1", "--json").stdout)["result"]["record"]
    check(
        "model-set: the change's actor replaces it",
        r.returncode == 0 and got.get("actor", {}).get("name") == "ana" and got.get("name") == "Model one",
        out(r) + json.dumps(got.get("actor")),
    )
    r = evh("model-set", "m1", "--set", "name=Model one", **AGENT)
    got = json.loads(evh("model-show", "m1", "--json").stdout)["result"]["record"]
    check(
        "model-set that changes nothing leaves the actor", got.get("actor", {}).get("name") == "ana", out(r)
    )
    r = evh("validate", **AGENT)
    check(
        "validate notes no record as naming no actor",
        "name no actor" not in r.stdout + r.stderr,
        out(r),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
