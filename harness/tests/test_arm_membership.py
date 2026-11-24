#!/usr/bin/env python3
"""Which runs make up an arm: one function says it, every reader reads it (RFC-041 F2).

    python tests/test_arm_membership.py

In a throwaway project ($0, offline, the echo provider), shaped as the fleet's (2026-11-21): a `--repeat 3` set that
lost its third pass, then `--purpose repeat --of <the first pass>` with the same configuration. The repeat is the
same measurement taken again (same fingerprint hash), so it is one arm with the two passes left: the leaderboard,
pair-test, runs-list, cost-report, the catalog's arm and a round all see three runs, and validate's V8 passes. With a
setting changed the hash differs: it is another measurement, stays under `repeats`, and `evh run` says why, before
its first call and in its last line. A user's `--run-id foo_r1` and `foo_r2` are two plain runs, not a set. The latest
run is the greatest (created_at, run_id), by the system its record names. An arm's runs scored against another
reference than its latest run's are named and never averaged in. The `_rN` suffix is read in model/runs.py only.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-arms-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD"):
    os.environ.pop(k, None)
import _cli  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format, _runs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import runs as R  # noqa: E402

KIT = HARNESS / "tutorial"
SCRIPTS = HARNESS / "scripts"
env = dict(os.environ, EVAL_BUILD_REF="test-arms", EVAL_MAX_RETRIES="0", EVH_ACTOR="person:test")
DS = "tickets_v1"

ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output=text[: int(params.get("n", 40))], tokens_in=10, tokens_out=5, cost_usd=None,
                           latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split()))}

PRIMARY_METRIC = "words"
"""


def evh(*args):
    _store.close()
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


def system(name, **params):
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    _runstore.write_text(
        proj, f"systems/{name}.yaml", f"system_id: {name}\nadapter: a.py\nparams:\n  provider: echo\n{body}"
    )


def run_ids(sid, ds=DS):
    """The ids of the system's runs on the dataset, under any label."""
    _store.close()
    return sorted(R.run_of(sd).name for sd, _rec in R.scored(ds, system_id=sid, label_is=None))


def scores_of(sid, ds=DS):
    """Every score of the system on the dataset, any label, with its arm as model.runs says it."""
    return [(sd, rec, R.arm_of(sd, rec)) for sd, rec in R.scored(ds, system_id=sid, label_is=None)]


def arms_of(sid, ds=DS):
    found: dict[str, list[str]] = {}
    for sd, _rec, arm in scores_of(sid, ds):
        found.setdefault(arm, []).append(R.run_of(sd).name)
    return {a: sorted(v) for a, v in sorted(found.items())}


def v8():
    """The V8 line of `evh validate`: (ok, its text)."""
    text = out(evh("validate"))
    line = next((ln for ln in text.splitlines() if "V8" in ln), "")
    return line.strip().startswith("ok"), text


def values(r):
    try:
        return (json.loads(r.stdout).get("result") or {}).get("values") or {}
    except ValueError:
        print("  (not JSON)", out(r)[:600])
        return {}


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "a.py").write_text(ADAPTER, encoding="utf-8")
    _runstore.write_text(proj, "validate.json", json.dumps({"committed": ["runs", "repeats"]}))
    _runstore.write_text(
        proj,
        "goals/tickets_summary.yaml",
        (KIT / "goals" / "tickets_summary.yaml").read_text(encoding="utf-8").replace("overlap_f1", "words"),
    )
    for ds in (DS, "tickets_v2"):
        r = evh("dataset-create", "--dataset-id", ds, "--source-dir", "tutorial/tickets")
        r = r if r.returncode else evh("dataset-materialize", "--dataset-id", ds)
        check(f"setup: dataset {ds}", r.returncode == 0, out(r)[-300:])
    system("fleet_v1")
    system("other_v1", n=20)

    # -- the fleet's shape: a --repeat 3 set that lost a pass, and a repeat of its first pass, the same configuration
    r = evh("run", "--system", "fleet_v1", "--dataset", DS, "--repeat", "3")
    first = sorted(run_ids("fleet_v1"))
    check("setup: a --repeat 3 set", r.returncode == 0 and len(first) == 3, out(r)[-300:])
    r1, r3 = first[0], first[2]
    r = evh("data-rm", "--path", f"runs/{r3}")
    check("setup: the third pass is lost", r.returncode == 0 and len(run_ids("fleet_v1")) == 2, out(r)[-300:])
    r = evh("run", "--system", "fleet_v1", "--dataset", DS, "--purpose", "repeat", "--of", r1)
    ran = run_ids("fleet_v1")
    again = next((x for x in ran if x not in first), "")
    check("setup: a repeat of the first pass", r.returncode == 0 and len(ran) == 3, out(r)[-400:])
    run_r = out(r)
    fp = lambda rid: (R.run(rid) or {}).get("fingerprint", {}).get("hash")  # noqa: E731
    check(
        "setup: the repeat has the same fingerprint hash as its original",
        fp(again) == fp(r1) and fp(r1),
        (fp(again), fp(r1)),
    )
    evh("run", "--system", "other_v1", "--dataset", DS)

    arms = arms_of("fleet_v1")
    check(
        "arm_of: a repeat of a run with the same fingerprint hash is read in its arm: one arm, three runs",
        list(arms) == ["runs/tickets_v1/fleet_v1"] and len(arms["runs/tickets_v1/fleet_v1"]) == 3,
        arms,
    )
    lst = json.loads(evh("runs-list", "--json").stdout)["result"]
    check(
        "runs-list reads the three runs of the arm, and no `repeats` label",
        len([m for m in lst["runs"] if m["system_id"] == "fleet_v1"]) == 3
        and "repeats" not in (lst.get("labels") or []),
        ([m["run_id"] for m in lst["runs"]], lst.get("labels")),
    )
    pv = values(evh("pair-test", DS, "--a", "fleet_v1", "--b", "other_v1", "--metric", "words", "--json"))
    check(
        "pair-test reads the three runs of the arm",
        len(pv.get("run_ids_a") or []) == 3
        and (pv.get("repeats") or {}).get("fleet_v1", {}).get("runs") == 3,
        (pv.get("run_ids_a"), pv.get("repeats")),
    )
    lb = values(evh("leaderboard", DS, "--json"))
    lrows = [a for g in lb.get("groups") or [] for a in g["arms"] if a["system_id"] == "fleet_v1"]
    check(
        "leaderboard: one row for the system, over its three runs",
        [(a["arm"], a["n_runs"]) for a in lrows] == [("runs/tickets_v1/fleet_v1", 3)],
        lrows and [(a["arm"], a["n_runs"]) for a in lrows],
    )
    cr = evh("cost-report", "--dataset-id", DS, "--json")
    check(
        "cost-report lists the three runs of the arm, each its own row",
        sorted(set(re.findall(r"fleet_v1 r(\d)", out(cr)))) == ["1", "2", "3"],
        out(cr)[-700:],
    )
    A = HarnessAdapter(proj / "data")
    fleet_arms = [a for a in A.arms() if a.endswith("/fleet_v1")]
    check(
        "the catalog's arm: one, `runs/tickets_v1/fleet_v1`, through three runs",
        fleet_arms == ["runs/tickets_v1/fleet_v1"] and len(A._dirs(fleet_arms[0])) == 3,
        (fleet_arms, [len(A._dirs(a)) for a in fleet_arms]),
    )
    ok, text = v8()
    check("validate: V8 accepts a --repeat set with a repeat joined to it", ok, text[-600:])
    members = R.set_of([(sd, rec) for sd, rec, _a in scores_of("fleet_v1")])
    check(
        "set_of: the three runs are the arm's repeat set (a repeat_index, or a joined repeat, or the run it names)",
        sorted(R.run_of(sd).name for sd, _r in members) == ran,
        sorted(R.run_of(sd).name for sd, _r in members),
    )
    lines = [ln for ln in run_r.splitlines() if ln.strip()]
    first_call = next((i for i, ln in enumerate(lines) if "[1/6]" in ln), -1)
    said = [i for i, ln in enumerate(lines) if "repeat of" in ln and r1 in ln]
    check(
        "evh run --purpose repeat --of: says before its first call that it joins the arm of the run it repeats, and "
        "again in its last line",
        len(said) >= 2
        and said[0] < first_call
        and "joins" in lines[said[0]]
        and "runs/tickets_v1/fleet_v1" in lines[said[0]]
        and said[-1] == len(lines) - 1
        and "joined" in lines[-1],
        (said, first_call, len(lines), lines[-3:]),
    )

    # -- a round: a repeat made in it joins the arm of the run it repeats
    system("round_v1")
    r = evh("round-open", "--goal", "tickets_summary", "--dataset", DS)
    check("setup: a round", r.returncode == 0, out(r)[-300:])
    rn = ("--goal", "tickets_summary", "--round", "r1")
    r = evh("run", "--system", "round_v1", "--dataset", DS, "--repeat", "2", *rn)
    rids = run_ids("round_v1")
    r2 = evh("run", "--system", "round_v1", "--dataset", DS, "--purpose", "repeat", "--of", rids[0], *rn)
    doc = yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml")) or {}
    rarms = [a for a in doc.get("arms") or [] if a.get("system") == "round_v1"]
    check(
        "a round: a repeat made in it joins the round arm of the run it repeats (one arm, three runs, no `repeats`)",
        r.returncode == 0
        and r2.returncode == 0
        and len(rarms) == 1
        and len(rarms[0].get("runs") or []) == 3
        and not rarms[0].get("label"),
        (out(r2)[-300:], rarms),
    )

    # a repeat of a retired arm's run is refused, before any call: it would bring the arm back into play
    system("ret_v1")
    r = evh("run", "--system", "ret_v1", "--dataset", DS, *rn)
    ret = run_ids("ret_v1")
    r = evh(
        "round-retire",
        *rn[:2],
        "--round",
        "r1",
        "--arm",
        "ret_v1",
        "--reason",
        "A retired arm stays retired.",
    )
    refused = evh("run", "--system", "ret_v1", "--dataset", DS, "--purpose", "repeat", "--of", ret[0], *rn)
    doc = yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml")) or {}
    retired = [a for a in doc.get("arms") or [] if a.get("system") == "ret_v1"]
    check(
        "a round: a repeat of a retired arm's run is refused, naming the retirement; nothing run, the arm still retired",
        r.returncode == 0
        and refused.returncode != 0
        and "retired" in out(refused)
        and "bring it back" in out(refused)
        and run_ids("ret_v1") == ret
        and len(retired) == 1
        and retired[0].get("retired")
        and retired[0]["runs"] == ret,
        (out(r)[-200:], out(refused)[-400:], retired),
    )

    # a closed round's numbers never change: a repeat joining its arm afterwards is named in `since_then`, never read in
    def strip(x):
        return {k: strip(v) for k, v in x.items() if k != "notes"} if isinstance(x, dict) else x

    before = evh("round-evidence", "tickets_summary", "r1", "--json")
    closing = evh(
        "round-close", *rn[:2], "--round", "r1", "--conclusion", "closed to repeat a run after it in the test"
    )
    ev0 = json.loads(evh("round-evidence", "tickets_summary", "r1", "--json").stdout)["result"]
    late = evh("run", "--system", "round_v1", "--dataset", DS, "--purpose", "repeat", "--of", rids[0])
    ev1 = json.loads(evh("round-evidence", "tickets_summary", "r1", "--json").stdout)["result"]
    check(
        "a closed round: a repeat that joins its arm later changes none of its numbers, and is named as made since",
        before.returncode == 0
        and closing.returncode == 0
        and late.returncode == 0
        and len(run_ids("round_v1")) == 4
        and strip(ev0) == strip(ev1)
        and "round_v1: 1 run(s) since then not read here" in json.dumps(ev1)
        and "round_v1: 1 run(s) since then" not in json.dumps(ev0),
        (
            out(closing)[-200:],
            out(late)[-200:],
            list(ev1.get("notes", [])) if isinstance(ev1, dict) else ev1,
        ),
    )

    # -- a changed setting: another measurement, under `repeats`, and the run says why
    system("drift_v1")
    r = evh("run", "--system", "drift_v1", "--dataset", DS, "--repeat", "2")
    d1 = run_ids("drift_v1")[0]
    system("drift_v1", n=30)
    r = evh("run", "--system", "drift_v1", "--dataset", DS, "--purpose", "repeat", "--of", d1)
    lines = [ln for ln in out(r).splitlines() if ln.strip()]
    changed = next((x for x in run_ids("drift_v1") if x not in (d1, run_ids("drift_v1")[1])), "")
    check(
        "setup: a repeat with a changed setting",
        r.returncode == 0 and len(run_ids("drift_v1")) == 3,
        out(r)[-300:],
    )
    check(
        "setup: the repeat's fingerprint hash differs from its original's",
        fp(changed) and fp(changed) != fp(d1),
        (fp(changed), fp(d1)),
    )
    arms = arms_of("drift_v1")
    check(
        "arm_of: a repeat whose fingerprint hash differs stays under `repeats`",
        sorted(arms) == ["repeats/tickets_v1/drift_v1", "runs/tickets_v1/drift_v1"]
        and arms["repeats/tickets_v1/drift_v1"] == [changed],
        arms,
    )
    first_call = next((i for i, ln in enumerate(lines) if "[1/6]" in ln), -1)
    said = [i for i, ln in enumerate(lines) if "repeat of" in ln and d1 in ln]
    check(
        "evh run --purpose repeat --of: with another hash it says before its first call that it is read under "
        "`repeats` and which part differs, and again in its last line",
        len(said) >= 2
        and said[0] < first_call
        and "repeats" in lines[said[0]]
        and "settings" in lines[said[0]]
        and said[-1] == len(lines) - 1
        and "repeats" in lines[-1]
        and "settings" in lines[-1],
        (said, first_call, lines[-3:]),
    )
    ok, text = v8()
    check("validate: V8 passes with a repeat under `repeats` and the set under `runs`", ok, text[-600:])

    # -- what the same measurement is: the system, the dataset, the data, the deployment, the settings and the adapter;
    # the harness's own code may differ, and is named
    def fprint(**over):
        base = {
            "version": 5,
            "data_sha256": "d",
            "deployment_sha256": "p",
            "settings_sha256": "s",
            "instrument": {"adapter": {"sha256": "a"}, "harness": {"code_sha256": "h1"}},
        }
        return {**base, **over}

    def rec_of(**over):
        return {"system_id": "s", "dataset_id": "d", "fingerprint": fprint(), **over}

    same = R.same_measurement
    inst = lambda a, h: {"instrument": {"adapter": {"sha256": a}, "harness": {"code_sha256": h}}}  # noqa: E731
    check(
        "same_measurement: equal parts are the same measurement; another harness build still is, and is named",
        same(rec_of(), rec_of()) == (True, [])
        and same(rec_of(), rec_of(fingerprint=fprint(**inst("a", "h2")))) == (True, [R.HARNESS]),
        (same(rec_of(), rec_of()), same(rec_of(), rec_of(fingerprint=fprint(**inst("a", "h2"))))),
    )
    check(
        "same_measurement: another setting, deployment, data or adapter is not, and is named; so is another system or "
        "dataset",
        same(rec_of(), rec_of(fingerprint=fprint(settings_sha256="x"))) == (False, ["settings"])
        and same(rec_of(), rec_of(fingerprint=fprint(deployment_sha256="x"))) == (False, ["deployment"])
        and same(rec_of(), rec_of(fingerprint=fprint(data_sha256="x"))) == (False, ["data"])
        and same(rec_of(), rec_of(fingerprint=fprint(**inst("b", "h1")))) == (False, ["adapter"])
        and same(rec_of(), rec_of(system_id="t")) == (False, ["system"])
        and same(rec_of(), rec_of(dataset_id="e")) == (False, ["dataset"]),
    )
    check(
        "same_measurement: no fingerprint, another version, or a part one side never recorded is not the same, and says "
        "which; a harness build that differs does not hide it",
        same(rec_of(), {"system_id": "s", "dataset_id": "d"}) == (False, ["fingerprint (not recorded)"])
        and same(rec_of(), rec_of(fingerprint=fprint(version=4))) == (False, ["fingerprint version"])
        and same(rec_of(), rec_of(fingerprint={k: v for k, v in fprint().items() if k != "settings_sha256"}))
        == (False, ["settings (not recorded)"])
        and same(rec_of(), rec_of(fingerprint=fprint(settings_sha256="x", **inst("a", "h2"))))
        == (False, ["settings", R.HARNESS]),
    )

    # -- another harness build only: the repeat joins, and the run and the listing of the arm's runs say so
    system("build_v1")
    evh("run", "--system", "build_v1", "--dataset", DS)
    (b1,) = run_ids("build_v1")
    _store.close()
    rec = R.run(b1) or {}
    inst_ = rec["fingerprint"]["instrument"]
    rec["fingerprint"] = {
        **rec["fingerprint"],
        "instrument": {**inst_, "harness": {**inst_["harness"], "code_sha256": "0" * 64}},
    }
    R.write_run(b1, rec)
    r = evh("run", "--system", "build_v1", "--dataset", DS, "--purpose", "repeat", "--of", b1)
    lines = [ln for ln in out(r).splitlines() if ln.strip()]
    b2 = next((x for x in run_ids("build_v1") if x != b1), "")
    listed = json.loads(evh("runs-list", "--json").stdout)["result"]["runs"]
    mark = next((x.get("joined") for x in listed if x["run_id"] == b2), None)
    check(
        "a repeat made on another harness build joins its original's arm; `evh run` names the build in its first and "
        "last lines, and runs-list where the arm's runs are listed",
        r.returncode == 0
        and list(arms_of("build_v1")) == ["runs/tickets_v1/build_v1"]
        and any("joins" in ln and "harness build" in ln for ln in lines)
        and "joined" in lines[-1]
        and "harness build" in lines[-1]
        and mark == {"of": b1, "differs": ["harness build"]},
        (out(r)[-500:], arms_of("build_v1"), mark),
    )

    # -- a repeat of a repeat follows `of` to the root; one that names a repeat read under `repeats`, or a run that is
    # gone, is read under `repeats` too, and says why
    system("chain_v1")
    evh("run", "--system", "chain_v1", "--dataset", DS)
    (x0,) = run_ids("chain_v1")
    evh("run", "--system", "chain_v1", "--dataset", DS, "--purpose", "repeat", "--of", x0)
    c1 = next(x for x in run_ids("chain_v1") if x != x0)
    evh("run", "--system", "chain_v1", "--dataset", DS, "--purpose", "repeat", "--of", c1)
    c2 = next(x for x in run_ids("chain_v1") if x not in (x0, c1))
    system("chain_v1", n=30)
    evh("run", "--system", "chain_v1", "--dataset", DS, "--purpose", "repeat", "--of", x0)
    d0 = next(x for x in run_ids("chain_v1") if x not in (x0, c1, c2))
    evh("run", "--system", "chain_v1", "--dataset", DS, "--purpose", "repeat", "--of", d0)
    e0 = next(x for x in run_ids("chain_v1") if x not in (x0, c1, c2, d0))
    arms = arms_of("chain_v1")
    check(
        "a repeat of a repeat joins the root's arm; a repeat of one read under `repeats` is read under `repeats`",
        arms
        == {
            "repeats/tickets_v1/chain_v1": sorted([d0, e0]),
            "runs/tickets_v1/chain_v1": sorted([x0, c1, c2]),
        },
        arms,
    )
    _store.close()
    mine = {"dataset_id": DS, "system_id": "chain_v1", "fingerprint": (R.run(e0) or {})["fingerprint"]}
    why = R.repeat_reading(d0, mine)["why"]
    check(
        "a repeat of a repeat that is read under `repeats` says so, and why",
        why and "is itself read under repeats" in why[0] and "settings" in why[0],
        why,
    )
    # d0 and e0 are two measurements of chain_v1 under `repeats` (neither joins an arm): what validate fails, as it
    # failed any two runs of one arm; the project allows them, and the checks below are about the other arms
    _runstore.write_text(
        proj,
        "validate.json",
        json.dumps({"committed": ["runs", "repeats"], "duplicate_ok": [[DS, "chain_v1"]]}),
    )
    system("gone_v1")
    evh("run", "--system", "gone_v1", "--dataset", DS)
    (z0,) = run_ids("gone_v1")
    evh("run", "--system", "gone_v1", "--dataset", DS, "--purpose", "repeat", "--of", z0)
    f0 = next(x for x in run_ids("gone_v1") if x != z0)
    evh("data-rm", "--path", f"runs/{z0}")
    arms = arms_of("gone_v1")
    gone_why = R.repeat_reading(z0, {"dataset_id": DS, "system_id": "gone_v1", "fingerprint": {}})["why"]
    ok, text = v8()
    check(
        "a repeat of a run that was deleted is read under `repeats`, and says the run is not there; validate notes it",
        list(arms) == ["repeats/tickets_v1/gone_v1"]
        and arms["repeats/tickets_v1/gone_v1"] == [f0]
        and gone_why == [f"{z0} is not there"]
        and ok
        and f"{f0} is a repeat of {z0}, which is not there" in text,
        (arms, gone_why, text[-300:]),
    )

    # -- `of` names a run of the repeat's own system and dataset: refused before any call, and validate fails one
    before = len(run_ids("other_v1")) + len(run_ids("fleet_v1"))
    r = evh("run", "--system", "other_v1", "--dataset", DS, "--purpose", "repeat", "--of", r1)
    check(
        "evh run --purpose repeat --of a run of another system is refused by name, before any call; nothing written",
        r.returncode != 0
        and "a repeat names a run of its own system and dataset" in out(r)
        and "[1/6]" not in out(r)
        and len(run_ids("other_v1")) + len(run_ids("fleet_v1")) == before,
        out(r)[-500:],
    )
    _store.close()
    forged = R.run(f0) or {}
    R.write_run(f0, {**forged, "of": b1})  # a committed repeat naming a run of another system
    ok, text = v8()
    v29 = next((ln for ln in text.splitlines() if "V29" in ln), "")
    check(
        "validate: V29 fails a repeat whose `of` names a run of another system, naming it",
        "FAIL V29" in text and f"run {f0} is a repeat of {b1}, a run of build_v1" in text,
        v29,
    )
    R.write_run(f0, forged)

    # -- membership is what the record says, in both shapes: a `--repeat` set of plain runs, and one of repeats
    system("shape_v1")
    evh("run", "--system", "shape_v1", "--dataset", DS)
    (s0,) = run_ids("shape_v1")
    r = evh(
        "run", "--system", "shape_v1", "--dataset", DS, "--purpose", "repeat", "--of", s0, "--repeat", "2"
    )
    shape = [(sd, rec) for sd, rec, _a in scores_of("shape_v1")]
    ok, text = v8()
    check(
        "a `--repeat 2` set made with --purpose repeat --of joins the run's arm: three runs, one set, V8 passes",
        r.returncode == 0
        and len(run_ids("shape_v1")) == 3
        and list(arms_of("shape_v1")) == ["runs/tickets_v1/shape_v1"]
        and len(R.set_of(shape)) == 3
        and R.is_set(shape)
        and ok
        and sorted(rec.get("repeat_index") or 0 for _s, rec in shape) == [0, 1, 2],
        (out(r)[-300:], arms_of("shape_v1"), text[-300:]),
    )

    # -- a round that recorded a repeat under `repeats` no longer reads it there once it joins its original's arm: a round
    # reads what it recorded (RUNBOOK:1531) and there is no migration, so validate notes it and does not fail
    _runstore.write_text(
        proj,
        "rounds/tickets_summary/r9.yaml",
        "round_id: r9\ngoal: tickets_summary\ndataset_id: tickets_v1\nstatus: closed\nopened_at: '2026-11-01T00:00:00Z'\n"
        f"arms:\n- system: chain_v1\n  label: repeats\n  runs:\n  - {c1}\n  entered: {{how: ran, at: '2026-11-01T00:00:00Z'}}\n"
        "conclusion:\n  text: closed under 0.8.0\n",
    )
    r = evh("validate")
    text = out(r)
    check(
        "validate: V29 notes a round arm that records a repeat under `repeats` where it is no longer read; no FAIL, exit 0",
        "FAIL V29" not in text
        and r.returncode == 0
        and any(
            ln.lstrip().startswith("note:")
            and f"round r9 of tickets_summary records {c1} in its arm repeats/tickets_v1/chain_v1" in ln
            for ln in text.splitlines()
        ),
        ([ln for ln in text.splitlines() if "r9" in ln or "FAIL" in ln][:4], r.returncode),
    )
    _runstore.unlink(proj, "rounds/tickets_summary/r9.yaml")

    # -- the latest run, by the system its record names
    system("smoke_v1")
    system("smoke")
    evh("run", "--system", "smoke_v1", "--dataset", DS)
    evh("run", "--system", "smoke", "--dataset", DS)
    mine = run_ids("smoke")
    import evaluation_harness.judge_validate as jv

    check(
        "latest run: system `smoke` is its own run, not `smoke_v1`'s (a name prefix and a string max took smoke_v1's)",
        len(mine) == 1 and jv._latest_run("smoke", DS) == mine[0],
        (mine, jv._latest_run("smoke", DS)),
    )
    a = (Path("a"), {"run_id": "b_1", "created_at": "2026-11-02T00:00:00Z"})
    b = (Path("b"), {"run_id": "a_2", "created_at": "2026-11-03T00:00:00Z"})
    c = (Path("c"), {"run_id": "z_0", "created_at": "2026-11-03T00:00:00Z"})
    check(
        "latest(): the greatest (created_at, run_id), whatever the run ids sort as; None for none",
        R.latest([a, b]) is b and R.latest([b, a]) is b and R.latest([a, b, c]) is c and R.latest([]) is None,
    )

    # -- a user's run ids ending _r1 and _r2 are two plain runs, not a set (validate fails V8, as for any two)
    system("plain_v1")
    for n in ("foo_r1", "foo_r2"):
        r = evh("run", "--system", "plain_v1", "--dataset", DS, "--run-id", n)
    check("setup: two plain runs named foo_r1 and foo_r2", len(run_ids("plain_v1")) == 2, out(r)[-300:])
    ok, text = v8()
    named = [ln for ln in text.splitlines() if "runs claim" in ln]
    check(
        "validate: two plain runs of one system fail V8 even when their ids end _r1 and _r2, and only they do",
        not ok and len(named) == 1 and "plain_v1" in named[0],
        named or text[-600:],
    )

    # -- three `--repeat` invocations of one system are three sets, not one arm of six: an index two of the arm's runs
    # carry (two `r1`) comes from two invocations, so V8 fails them as it fails two plain runs, and notes them when the
    # project allows them (RFC-041 F2; the fleet's b95efa9, 6 runs over 3 invocations)
    system("many_v1")
    allow = lambda *ids: _runstore.write_text(  # noqa: E731
        proj,
        "validate.json",
        json.dumps({"committed": ["runs", "repeats"], "duplicate_ok": [[DS, s] for s in ("chain_v1", *ids)]}),
    )
    allow(
        "many_v1"
    )  # `evh run` refuses a second --repeat set beside a measured run unless the project allows the pair
    ran = [
        evh("run", "--system", "many_v1", "--dataset", DS, "--repeat", n, "--run-id", f"many_v1_{x}")
        for x, n in (("A", "2"), ("B", "2"), ("C", "3"))
    ]
    evh("data-rm", "--path", "runs/many_v1_A_r2")
    allow()
    many = [(sd, rec) for sd, rec, _a in scores_of("many_v1")]
    check(
        "setup: six runs over three --repeat invocations",
        len(run_ids("many_v1")) == 6,
        ([r.returncode for r in ran], run_ids("many_v1")),
    )
    ok, text = v8()
    named = [ln for ln in text.splitlines() if "runs claim" in ln]
    check(
        "validate: six runs of three `--repeat` invocations are not one repeat set: V8 fails them, naming the runs",
        not R.is_set(many) and not ok and any("6 runs claim 'many_v1'" in ln for ln in named),
        (R.is_set(many), named),
    )
    allow("many_v1")
    ok, text = v8()
    note = f"6 'many_v1' runs on {DS} (allowed: duplicate_ok in validate.json)"
    check(
        "validate: with the project's `duplicate_ok` the six runs are noted, not failed",
        any(ln.lstrip().startswith("note:") and note in ln for ln in text.splitlines())
        and not any("many_v1" in ln for ln in text.splitlines() if "runs claim" in ln),
        [ln for ln in text.splitlines() if "many_v1" in ln],
    )
    one = [(sd, rec) for sd, rec in many if R.run_of(sd).name.startswith("many_v1_C")]
    check(
        "set_of: one invocation's runs are still a set, the passes of two are not",
        len(R.set_of(one)) == 3 and R.is_set(one) and not R.set_of(many) and not R.is_set(many),
        (len(R.set_of(one)), len(R.set_of(many))),
    )

    # -- runs scored against another reference than the arm's latest run's are named and not averaged in
    system("mixed_v1")
    evh("run", "--system", "mixed_v1", "--dataset", "tickets_v2")
    r = evh(
        "label-import",
        "--sheet",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v2",
        "--set",
        "g",
        "--by",
        "owner",
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v2", "--labels", "g", "--tier", "gold", "--reason", "The kit's hand-written summaries decide.", "--by", "owner"
    )  # fmt: skip
    check("setup: a gold reference on tickets_v2", r.returncode == 0, out(r)[-300:])
    evh("run", "--system", "mixed_v1", "--dataset", "tickets_v2")
    mixed = [(sd, rec) for sd, rec in R.scored("tickets_v2", system_id="mixed_v1", label_is=None)]
    kept, left = R.runs_of_arm(mixed)
    by_name = lambda xs: sorted(R.run_of(sd).name for sd, _r in xs)  # noqa: E731
    check(
        "runs_of_arm: an arm's runs are read against the reference of its latest run; the other is named, not kept",
        len(mixed) == 2 and len(kept) == 1 and len(left) == 1 and by_name(kept) == [by_name(mixed)[1]],
        (by_name(kept), by_name(left)),
    )
    left_name = by_name(left)[0] if left else "?"
    seen = _runs.runs_on("tickets_v2", system_id="mixed_v1")
    check(
        "runs_on: the arm's runs scored against another reference are never averaged in",
        by_name(seen) == by_name(kept),
        by_name(seen),
    )
    warned = evh("pair-test", "tickets_v2", "--a", "mixed_v1", "--b", "mixed_v1", "--metric", "words")
    check(
        "a command that reads the arm names the run it left out, and why",
        left_name in out(warned) and "reference" in out(warned),
        out(warned)[-500:],
    )
    A2 = HarnessAdapter(proj / "data")
    check(
        "the catalog reads the same runs of that arm",
        by_name([(d, {}) for d in A2._dirs("runs/tickets_v2/mixed_v1")]) == by_name(kept),
        by_name([(d, {}) for d in A2._dirs("runs/tickets_v2/mixed_v1")]),
    )

    # -- the `_rN` suffix is read in model/runs.py only (run.py writes it, nothing else reads it)
    suffix = re.compile(r"_\(?r\\d|_r\*|_r\[|[\"']_r[\"']")
    readers = sorted(
        p.relative_to(SCRIPTS).as_posix()
        for p in SCRIPTS.rglob("*.py")
        if "migrations" not in p.parts
        and p.relative_to(SCRIPTS).as_posix() != "model/runs.py"
        and any(suffix.search(ln) for ln in p.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
    )  # fmt: skip
    check("the `_rN` run-id suffix is read only in model/runs.py", readers == [], readers)

    # -- a rescored repeat set (a 0.7 `--repeat 3` set: `purpose: repeat`, no `of`, re-scored): every arm `arm-list`
    # lists is shown by `arm-show`, and a reader that groups runs by arm (runs-list, metric-show) names the id arm-list
    # does, through the CLI, the API and the MCP server's reads (RFC-041 F2: the id is `model.runs.arm_of`'s alone)
    system("resc_v1")
    evh("run", "--system", "resc_v1", "--dataset", DS, "--repeat", "2", "--run-id", "resc_v1_A")
    _store.close()
    for n in ("resc_v1_A_r1", "resc_v1_A_r2"):
        R.write_run(n, {**(R.run(n) or {}), "purpose": "repeat"})
    (proj / "a.py").write_text(
        ADAPTER.replace("float(len(output.split()))", "float(len(output.split())) + 1"), encoding="utf-8"
    )
    r = evh("rescore", "--dataset-id", DS, "--match", "resc_v1", "--label", "rescored 3d3a6afd")
    resc = arms_of("resc_v1")
    check(
        "setup: a rescored repeat set is read as `rescored 3d3a6afd, repeats`, under a slug that is not the label",
        r.returncode == 0
        and sorted(resc) == ["repeats/tickets_v1/resc_v1", "rescored-3d3a6afd-repeats/tickets_v1/resc_v1"],
        (out(r)[-300:], resc),
    )

    class Readers:
        """One reader's `read(op, **params)`: the CLI's JSON, the API of a local `evh catalog-serve`, the MCP server's
        read operations in this process."""

        def __init__(self, how):
            self.how = how
            self.srv = None

        def __enter__(self):
            if self.how == "api":
                import _serve  # noqa: PLC0415

                self.srv, self.port, _lines = _serve.start(proj, env)
                tok = proj / ".build" / "api-token"
                self.token = tok.read_text(encoding="utf-8").strip() if tok.exists() else None
            return self

        def __exit__(self, *_exc):
            if self.srv is not None:
                self.srv.terminate()
                self.srv.wait(15)

        def read(self, op, **params):
            from evaluation_harness.ops import OPS  # noqa: PLC0415

            if self.how == "cli":
                pos = [params[k] for k in ("label", "dataset", "system", "metric") if k in params]
                opt = [
                    x for k, v in params.items() if k == "label" and op == "runs-list" for x in ("--label", v)
                ]
                r = evh(op, *(pos if op != "runs-list" else []), *opt, "--json")
                if r.returncode:
                    raise LookupError(out(r)[-200:])
                return json.loads(r.stdout)["result"]
            if self.how == "mcp":
                from evaluation_harness import mcp_server  # noqa: PLC0415

                _store.close()
                try:
                    return mcp_server.run_op(OPS[op], params, False)["result"]
                except Exception as exc:  # noqa: BLE001 - a refusal of any type is what the check reports
                    raise LookupError(f"{type(exc).__name__}: {exc}") from None
            import urllib.error  # noqa: PLC0415
            import urllib.parse  # noqa: PLC0415
            import urllib.request  # noqa: PLC0415

            spec = OPS[op]
            route = spec.route
            for k in spec.path_params():
                route = route.replace("{" + k + "}", urllib.parse.quote(str(params[k]), safe=""))
            query = urllib.parse.urlencode({k: v for k, v in params.items() if k not in spec.path_params()})
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/v1{route}" + (f"?{query}" if query else ""),
                headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 # nosec B310 - this test's server
                    return json.loads(resp.read().decode())["result"]
            except urllib.error.HTTPError as exc:
                raise LookupError(f"HTTP {exc.code}: {exc.read().decode()[:200]}") from None

    for how in ("cli", "api", "mcp"):
        with Readers(how) as rd:
            listed = [a["arm"] for a in rd.read("arm-list")["arms"]]
            refused = []
            for arm in listed:
                label, ds, sid = arm.split("/", 2)
                try:
                    shown = rd.read("arm-show", label=label, dataset=ds, system=sid)["arm"]
                except LookupError as exc:
                    refused.append((arm, str(exc)))
                else:
                    if shown != arm:
                        refused.append((arm, f"shows {shown}"))
            check(
                f"{how}: every arm `arm-list` lists ({len(listed)}) is shown by `arm-show`, a rescored repeat set's too",
                bool(listed) and "rescored-3d3a6afd-repeats/tickets_v1/resc_v1" in listed and not refused,
                refused[:3],
            )
            n_runs = 0
            unlisted: list[tuple] = []
            labels = ["", *[x for x in rd.read("runs-list")["labels"] if x]]
            for lab in labels:
                for row in rd.read("runs-list", **({"label": lab} if lab else {}))["runs"]:
                    n_runs += 1
                    if row.get("arm") not in listed:
                        unlisted.append((lab, row["run_id"], row.get("arm")))
            check(
                f"{how}: runs-list names each run's arm by the id `arm-list` lists ({n_runs} runs, under {len(labels)} labels)",
                n_runs > 0 and not unlisted,
                unlisted[:3],
            )
            rows = [a for d in rd.read("metric-show", metric="words")["datasets"] for a in d["arms"]]
            bad = [a["arm"] for a in rows if a.get("arm_id") not in listed]
            check(
                f"{how}: metric-show names each arm row by the id `arm-list` lists ({len(rows)} rows)",
                bool(rows) and not bad,
                bad[:3],
            )

    # -- an arm has one value: the mean over its items, repeats pooled per item (RUNBOOK: an arm's repeats are averaged per
    # item). Two runs that score different item counts: the mean of the runs' means is another number, and the
    # leaderboard, arm-show and metric-show give the item-pooled one, through the CLI, the API and the MCP reads
    partial = """
from types import SimpleNamespace

SEEN = [0]

def call_system(text, params):
    return SimpleNamespace(output=text[:40], tokens_in=10, tokens_out=5, cost_usd=None, latency_ms=None, extra={}, meta={})

def score(output, reference):
    SEEN[0] += 1
    return {"words": 1.0, **({"partial": VALUE} if SEEN[0] <= K else {})}

PRIMARY_METRIC = "words"
"""
    system("val_v1")
    allow("many_v1", "val_v1")
    for tag, n_seen, v in (("a", 3, "1.0"), ("b", 1, "0.0")):
        (proj / f"p_{tag}.py").write_text(partial + f"K = {n_seen}\nVALUE = {v}\n", encoding="utf-8")
        _runstore.write_text(
            proj,
            "systems/val_v1.yaml",
            f"system_id: val_v1\nadapter: p_{tag}.py\nparams:\n  provider: echo\n",
        )
        r = evh("run", "--system", "val_v1", "--dataset", DS, "--run-id", f"val_v1_{tag}")
    vruns = [(sd, rec) for sd, rec, _a in scores_of("val_v1")]
    run_means: list[float] = sorted((rec.get("scores") or {}).get("partial", -1.0) for _sd, rec in vruns)
    check(
        "setup: two runs of one arm scoring one item count and another",
        len(vruns) == 2 and run_means == [0.0, 1.0],
        (out(r)[-300:], run_means),
    )
    for how in ("cli", "api", "mcp"):
        with Readers(how) as rd:
            arm = "runs/tickets_v1/val_v1"
            shown = {
                m["metric"]: m["mean"]
                for m in rd.read("arm-show", label="runs", dataset=DS, system="val_v1")["metrics"]
            }
            metric = {
                a["arm_id"]: a["mean"]
                for d in rd.read("metric-show", metric="partial")["datasets"]
                for a in d["arms"]
            }
            lb = rd.read("leaderboard", dataset=DS)
            board = {a["arm"]: a["metrics"] for g in (lb.get("values") or lb)["groups"] for a in g["arms"]}
            got: tuple = (shown.get("partial"), metric.get(arm), (board.get(arm) or {}).get("partial"))
            check(
                f"{how}: an arm whose runs score different item counts has one value on `partial`: "
                "arm-show, metric-show and the leaderboard agree, and it is not the mean of the runs' means",
                None not in got
                and got[0] == got[1]
                and abs(got[0] - got[2]) < 1e-9
                and abs(got[0] - sum(run_means) / 2) > 1e-6,
                (got, run_means),
            )
finally:
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
