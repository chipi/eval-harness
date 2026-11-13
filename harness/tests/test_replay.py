#!/usr/bin/env python3
"""Replay and faithfulness (RFC-030), $0 and offline: the replay example end to end, through the command line.

    python tests/test_replay.py

The example's history (examples/replay-filing/make_history.py): a filing system with three commits, production
running one a day over 20 decisions, people closing issues between them. Production's arm is a recorded arm from a
capture. Each replayed decision runs at the commit its day's deployment ran, each commit unpacked once; the ledger
the system writes survives the switches. A replay refuses --resume, --items and --repeat 2. Faithfulness agrees on
all 20 and its coverage names the rule no decision reaches; a replay is then scored against gold, and so is a
candidate at the third commit. An adapter that reads at the decision's stamp (after its own writes) disagrees: scoring
it is refused, a person's --unfaithful scores it and says so, an agent's is refused, and naming every disagreement
lets it through. Editing a support module or the deployed versions after the record closes the gate again. The code
record is a model record of kind: code; each faithfulness run writes its versions' summaries there. Mutants: three
killed, the fourth survives and coverage names why.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
EXAMPLE = HARNESS.parent / "examples" / "replay-filing"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-replay-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-replay")
env["PYTHONPATH"] = str(HARNESS) + os.pathsep + env.get("PYTHONPATH", "")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)
EVH = f"{sys.executable} {HERE / 'cli.py'}"


def evh(*args, extra=None):
    return subprocess.run([sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env={**env, **(extra or {})},
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)  # fmt: skip


def values(r):
    try:
        return (json.loads(r.stdout).get("result") or {}).get("values") or {}
    except ValueError:
        return {}


def run_id(r):
    runs = values(r).get("runs") or []
    return runs[0]["run_id"] if runs else None


def metrics(rid):
    return _runstore.read_json(proj, f"runs/{rid}/metrics.json")


def py(script, *args):
    return subprocess.run([sys.executable, str(MINE / script), *args], cwd=proj, env=env, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL)  # fmt: skip


#: The example as a person uses it: copied into the project, so its adapter is the project's.
MINE = proj / "examples" / "replay-filing"
try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")  # as evh init stamps it
    shutil.copytree(EXAMPLE, MINE, ignore=shutil.ignore_patterns("__pycache__"))
    made = py("make_history.py", "--out", "replay-filing")
    steps = [
        ("capture", "--importer", "jsonl", "--query", json.dumps({"path": "replay-filing/rows.jsonl"}), "--capture", "filing_prod"),
        ("dataset-from-capture", "filing_prod", "--dataset-id", "filing_history_v1", "--fieldset", "filing",
         "--field", "ts", "--field", "started", "--field", "production_issue"),
        ("dataset-materialize", "--dataset-id", "filing_history_v1"),
    ]  # fmt: skip
    r = None
    for argv in steps:
        r = evh(*argv)
        if r.returncode:
            break
    prod = evh(
        "run",
        "--system",
        "filing_production_v1",
        "--dataset",
        "filing_history_v1",
        "--goal",
        "filing",
        "--json",
    )
    prod_id = run_id(prod)
    check(
        "setup: the example's history made, captured as a dataset with datetime fields, production's recorded arm run",
        made.returncode == 0 and r is not None and r.returncode == 0 and prod.returncode == 0 and prod_id,
        (
            made.stdout[-300:] + made.stderr[-600:],
            (r.stdout + r.stderr)[-600:] if r else "",
            prod.stderr[-400:],
        ),
    )
    if not prod_id:
        sys.exit(summary())

    # ── a replay run ──────────────────────────────────────────────────────────────────────────────────────────────
    dry = evh(
        "faithfulness",
        "--system",
        "filing_replay_v1",
        "--dataset",
        "filing_history_v1",
        "--production",
        prod_id,
        "--dry-run",
        "--json",
    )
    plan = values(dry).get("plan") or {}
    check(
        "faithfulness --dry-run: 20 decisions at 3 commits, 8, 6 and 6, nothing called",
        dry.returncode == 0
        and plan.get("items") == 20
        and sorted((plan.get("commits") or {}).values()) == [6, 6, 8],
        (dry.stdout[-300:], dry.stderr[-300:]),
    )
    (proj / "two.txt").write_text("d01\nd02\n")
    refused = [
        evh(
            "run",
            "--system",
            "filing_replay_v1",
            "--dataset",
            "filing_history_v1",
            "--goal",
            "filing",
            *extra,
        )
        for extra in (["--resume", "x"], ["--items", "two.txt"], ["--repeat", "2"])
    ]
    check(
        "a replay run refuses --resume, --items and --repeat 2",
        all(x.returncode != 0 and "a replay run refuses" in x.stderr for x in refused),
        [x.stderr[-200:] for x in refused],
    )
    rr = evh(
        "run", "--system", "filing_replay_v1", "--dataset", "filing_history_v1", "--goal", "filing", "--json"
    )
    rep_id = run_id(rr)
    m = metrics(rep_id) if rep_id else {}
    code = ((m.get("fingerprint") or {}).get("deployment") or {}).get("code") or {}
    with _runstore._InProject(proj) as data:  # the run's rows, wherever the project's store keeps them
        rows = _runstore.rows(data / "runs" / rep_id) if rep_id else []
    changed = [x["item_id"] for x in rows if (x.get("_meta") or {}).get("changed")]
    copies = sorted(p.name for p in (proj / ".build" / "code" / "toy_filing").iterdir()) if rep_id else []
    check(
        "a replay with no reference runs (the gate is for scoring): each commit at its day, changed on its first item, "
        "each commit unpacked once, the fingerprint names the record and the commits",
        rr.returncode == 0
        and changed == ["d01", "d09", "d15"]
        and len(copies) == 3
        and code.get("record") == "toy_filing"
        and sorted(code.get("commits", {}).values()) == [6, 6, 8]
        and (m.get("faithfulness") or {}).get("faithful") is False,
        (rr.stderr[-500:], changed, copies, code),
    )
    stamp = (
        (proj / ".build" / "code" / "toy_filing" / copies[0] / ".evh-commit").stat().st_mtime_ns
        if copies
        else 0
    )

    # ── faithfulness ─────────────────────────────────────────────────────────────────────────────────────────────
    f1 = evh(
        "faithfulness",
        "--system",
        "filing_replay_v1",
        "--dataset",
        "filing_history_v1",
        "--production",
        prod_id,
        "--json",
    )
    rec = values(f1).get("faithfulness") or {}
    order = list(rec.get("commits") or {})  # the commits as first used: v1, v2, v3
    v3 = (rec.get("coverage") or {}).get(order[-1] if order else "", {})
    check(
        "faithfulness: the replay at the recorded commits agrees with production on all 20 (a reopen after a person "
        "closed an issue, a v2 key that files a new issue, the v3 info rule), and the copies are reused",
        f1.returncode == 0
        and rec.get("n") == 1
        and (rec.get("counts") or {}).get("agree") == 20
        and not rec.get("disagreements")
        and len(order) == 3
        and (proj / ".build" / "code" / "toy_filing" / copies[0] / ".evh-commit").stat().st_mtime_ns == stamp,
        (f1.stdout[-800:], f1.stderr[-600:]),
    )
    check(
        "coverage names the rule no decision reaches (filing.py:_cron_waits at the third commit)",
        "filing.py:_cron_waits" in (v3.get("never") or []) and v3.get("entered", 0) >= 4,
        v3,
    )

    # ── scored against gold ──────────────────────────────────────────────────────────────────────────────────────
    gold = [
        evh(*argv)
        for argv in (
            ("label-import", "replay-filing/gold", "--dataset-id", "filing_history_v1", "--set", "gold", "--by", "person:t"),
            ("reference-promote", "--dataset-id", "filing_history_v1", "--labels", "gold", "--tier", "gold",
             "--reason", "what each decision should have done", "--by", "person:t"),
        )
    ]  # fmt: skip
    scored = evh(
        "run", "--system", "filing_replay_v1", "--dataset", "filing_history_v1", "--goal", "filing", "--json"
    )
    cand = evh(
        "run",
        "--system",
        "filing_candidate_v3",
        "--dataset",
        "filing_history_v1",
        "--goal",
        "filing",
        "--json",
    )
    ms, mc = (metrics(run_id(x)) if run_id(x) else {} for x in (scored, cand))
    cc = ((mc.get("fingerprint") or {}).get("deployment") or {}).get("code") or {}
    check(
        "a faithful replay is scored against gold (19 of 20 exact: production filed the info alert), and a candidate "
        "made from it is scored too, every item at the third commit (the gate is the replay's record)",
        all(x.returncode == 0 for x in gold)
        and scored.returncode == 0
        and cand.returncode == 0
        and (ms.get("faithfulness") or {}).get("faithful") is True
        and (mc.get("faithfulness") or {}).get("faithful") is True
        and (ms.get("scores") or {}).get("exact") == 0.95
        and "exact" in (mc.get("scores") or {})
        and list((cc.get("commits") or {}).values()) == [20]
        and bool(order)
        and cc.get("candidate") == order[-1],
        (scored.stderr[-500:], cand.stderr[-500:], ms.get("scores"), mc.get("scores"), cc),
    )

    # ── an unfaithful replay ─────────────────────────────────────────────────────────────────────────────────────
    buggy_dir = proj / "buggy"
    buggy_dir.mkdir()
    shutil.copy(MINE / "replay_world.py", buggy_dir / "replay_world.py")
    text = (MINE / "replay_filing.py").read_text().replace('READ_AT = "started"', 'READ_AT = "ts"')
    (buggy_dir / "replay_filing.py").write_text(text)
    cfg = _runstore.read_text(proj, "systems/filing_replay_v1.yaml")
    adapter_line = next(x for x in cfg.splitlines() if x.startswith("adapter:"))
    _runstore.write_text(
        proj, "systems/filing_buggy.yaml",
        cfg.replace("system_id: filing_replay_v1", "system_id: filing_buggy").replace(adapter_line, "adapter: buggy/replay_filing.py"),
    )  # fmt: skip
    f2 = evh(
        "faithfulness",
        "--system",
        "filing_buggy",
        "--dataset",
        "filing_history_v1",
        "--production",
        prod_id,
        "--json",
    )
    rec2 = values(f2).get("faithfulness") or {}
    dis = [d["item_id"] for d in rec2.get("disagreements") or []]
    check(
        "an adapter that reads the tracker at the decision's stamp (after its own writes) disagrees on the reopens",
        f2.returncode == 0
        and rec2.get("n") == 2
        and dis
        and all(d["kind"] == "differ" for d in rec2["disagreements"])
        and all(d["production"].startswith("reopen") for d in rec2["disagreements"]),
        (f2.stderr[-500:], rec2.get("disagreements")),
    )
    no = evh("run", "--system", "filing_buggy", "--dataset", "filing_history_v1", "--goal", "filing")
    agent = evh("run", "--system", "filing_buggy", "--dataset", "filing_history_v1", "--goal", "filing", "--unfaithful",
                extra={"EVH_ACTOR": "agent:bot", "EVH_FOR": "person:t"})  # fmt: skip
    yes = evh(
        "run",
        "--system",
        "filing_buggy",
        "--dataset",
        "filing_history_v1",
        "--goal",
        "filing",
        "--unfaithful",
        "--json",
    )
    my = metrics(run_id(yes)) if run_id(yes) else {}
    check(
        "scoring the unfaithful replay is refused; an agent's --unfaithful is refused; a person's scores it, labelled",
        no.returncode != 0
        and "not-allowed" in no.stderr
        and "disagree" in no.stderr
        and agent.returncode != 0
        and "an agent cannot" in agent.stderr
        and yes.returncode == 0
        and ((my.get("faithfulness") or {}).get("unfaithful_by") or {}).get("name") == "test"
        and (my.get("faithfulness") or {}).get("faithful") is False,
        (no.stderr[-300:], agent.stderr[-300:], yes.stderr[-300:]),
    )
    show = evh("faithfulness-show", "--model", "toy_filing", "--json")
    ag_name = evh("faithfulness-name", "--model", "toy_filing", "--item", dis[0] if dis else "x", "--cause", "c",
                  extra={"EVH_ACTOR": "agent:bot", "EVH_FOR": "person:t"})  # fmt: skip
    names = [
        evh("faithfulness-name", "--model", "toy_filing", "--item", d, "--cause", "a test names it")
        for d in dis
    ]
    again = evh(
        "faithfulness-name", "--model", "toy_filing", "--item", dis[0] if dis else "x", "--cause", "twice"
    )
    ok = evh(
        "run", "--system", "filing_buggy", "--dataset", "filing_history_v1", "--goal", "filing", "--json"
    )
    mo = metrics(run_id(ok)) if run_id(ok) else {}
    check(
        "faithfulness-show prints the record; an agent cannot name a disagreement; a person names each (twice is "
        "refused); with every one named the replay is scored, and the run says how many were named",
        show.returncode == 0
        and (values(show).get("record") or {}).get("n") == 2
        and ag_name.returncode != 0
        and all(x.returncode == 0 for x in names)
        and again.returncode != 0
        and ok.returncode == 0
        and (mo.get("faithfulness") or {}).get("faithful") is True
        and (mo.get("faithfulness") or {}).get("named") == len(dis),
        (show.stderr[-200:], ag_name.stderr[-200:], [x.stderr[-200:] for x in names], ok.stderr[-400:]),
    )

    # ── a failing item is called once ────────────────────────────────────────────────────────────────────────────
    flaky_dir = proj / "flaky"
    flaky_dir.mkdir()
    shutil.copy(MINE / "replay_world.py", flaky_dir / "replay_world.py")
    flaky = (MINE / "replay_filing.py").read_text()
    anchor = '    code, fields = params["code"], params["item"]["fields"]\n'
    flaky = flaky.replace(
        anchor,
        anchor
        + '    if params["item"]["item_id"] == "d05":\n'
        + '        with open(Path(__file__).with_name("calls.txt"), "a") as fh:\n'
        + '            fh.write("d05\\n")\n'
        + '        raise TimeoutError("the tracker timed out")\n',
    )
    (flaky_dir / "replay_filing.py").write_text(flaky)
    _runstore.write_text(
        proj,
        "systems/filing_flaky.yaml",
        cfg.replace("system_id: filing_replay_v1", "system_id: filing_flaky").replace(
            adapter_line, "adapter: flaky/replay_filing.py"
        ),
    )
    fr = evh(
        "run",
        "--system",
        "filing_flaky",
        "--dataset",
        "filing_history_v1",
        "--goal",
        "filing",
        "--unfaithful",
        "--json",
    )
    mf = metrics(run_id(fr)) if run_id(fr) else {}
    calls = (flaky_dir / "calls.txt").read_text().split() if (flaky_dir / "calls.txt").is_file() else []
    check(
        "a replay calls a failing item once (a timeout, which a model run retries): recorded as failed, the pass goes on",
        anchor in flaky
        and fr.returncode == 0
        and calls == ["d05"]
        and [f["item_id"] for f in mf.get("failed_items") or []] == ["d05"]
        and mf.get("n_items") == 20,
        (fr.stderr[-500:], calls, mf.get("failed_items")),
    )

    # ── the gate closes again when what the record was made with moves ───────────────────────────────────────────
    with (buggy_dir / "replay_world.py").open("a") as fh:
        fh.write("\nEXTRA_RULE = 1\n")
    moved = evh("run", "--system", "filing_buggy", "--dataset", "filing_history_v1", "--goal", "filing")
    import yaml

    code_rec = _runstore.read_text(proj, "models/toy_filing.yaml")
    edited = yaml.safe_load(code_rec)
    edited["versions"][-1]["deployed"][0]["from"] = (
        "2026-10-04T00:00:01+00:00"  # v3 a second later: no item moves
    )
    _runstore.write_text(proj, "models/toy_filing.yaml", yaml.safe_dump(edited, sort_keys=False))
    moved2 = evh("run", "--system", "filing_replay_v1", "--dataset", "filing_history_v1", "--goal", "filing")
    _runstore.write_text(proj, "models/toy_filing.yaml", code_rec)
    check(
        "a support module edited after the record, or a version's deployed period in the code record, closes the gate "
        "for a new run, naming what moved",
        moved.returncode != 0
        and "another adapter or other support modules" in moved.stderr
        and moved2.returncode != 0
        and "other deployed versions in the code record" in moved2.stderr,
        (moved.stderr[-400:], moved2.stderr[-400:]),
    )
    late = evh(
        "run",
        "--system",
        "filing_buggy",
        "--dataset",
        "filing_history_v1",
        "--goal",
        "filing",
        "--unfaithful",
        "--json",
    )
    resc = evh("rescore", "--dataset-id", "filing_history_v1", "--match", "filing_buggy")
    resc_ok = evh(
        "rescore", "--dataset-id", "filing_history_v1", "--match", "filing_buggy", "--unfaithful", "--json"
    )
    rescored = [
        _runstore.read_json(proj, str(Path(x).relative_to(proj / "data")) + "/metrics.json")
        for x in values(resc_ok).get("rescored") or []
    ]
    check(
        "a finished replay is judged by what its own fingerprint names: rescoring an unfaithful one is refused, a "
        "person's --unfaithful rescores it, and the derived record carries the replay's faithfulness",
        late.returncode == 0
        and resc.returncode != 0
        and run_id(late) in resc.stderr
        and resc_ok.returncode == 0
        and rescored
        and all(isinstance(m.get("faithfulness"), dict) for m in rescored)
        and any((m["faithfulness"] or {}).get("unfaithful_by") for m in rescored),
        (late.stderr[-300:], resc.stderr[-300:], resc_ok.stderr[-400:]),
    )
    view = evh("models", "--model", "toy_filing")
    versions = yaml.safe_load(_runstore.read_text(proj, "models/toy_filing.yaml"))["versions"]
    summary_ = [v.get("faithfulness") or {} for v in versions]
    check(
        "the code record carries each version's latest faithfulness (record 2, its named disagreements), and "
        "evh models shows it",
        view.returncode == 0
        and all(f.get("run") == "toy_filing/2" for f in summary_)
        and sum(f.get("items", 0) for f in summary_) == 20
        and sorted(x for f in summary_ for x in f.get("exceptions") or []) == sorted(dis)
        and "toy_filing/2" in view.stdout
        and "named" in view.stdout,
        (view.stdout[-600:], summary_),
    )

    v_ok = evh("validate")
    ex = "faithfulness/toy_filing/2.exceptions.jsonl"
    before = _runstore.read_text(proj, ex)
    _runstore.write_text(
        proj,
        ex,
        before
        + json.dumps({"item_id": "d01", "cause": "x", "actor": {"type": "person", "name": "t"}})
        + "\n",
    )
    v_bad = evh("validate")
    _runstore.write_text(proj, ex, before)
    check(
        "validate V26: the faithfulness records pass; an exception naming an item that agreed fails; V24 takes a "
        "replay's code part (its record and commits, not one checkout)",
        "ok   V26" in v_ok.stdout
        and "FAIL V24" not in v_ok.stdout
        and "FAIL V26" in v_bad.stdout
        and "'d01', not one of its disagreements" in v_bad.stdout,
        (v_ok.stdout[-600:], v_bad.stdout[-600:]),
    )

    cat = evh("catalog")
    site = proj / ".build" / "catalog"
    model_page = (
        (site / "models" / "toy_filing.html").read_text()
        if (site / "models" / "toy_filing.html").is_file()
        else ""
    )
    pages = {f.name: f.read_text() for f in site.rglob("*.html")} if cat.returncode == 0 else {}
    buggy = [t for n, t in pages.items() if "filing_buggy" in n]
    replay_arm = [t for n, t in pages.items() if "filing_replay_v1" in n]
    check(
        "the code record's page lists its versions with their faithfulness; an arm page says it is a replay (linked "
        "to that page), and the unfaithful one carries the badge",
        cat.returncode == 0
        and "toy_filing/2" in model_page
        and "named" in model_page
        and any('href="../models/toy_filing.html"' in t for t in replay_arm)
        and any('class="badge unfaithful"' in t and "--unfaithful" in t for t in buggy)
        and any("faithful replay (toy_filing/1" in t for t in replay_arm),
        (cat.stderr[-300:], sorted(pages)[:40]),
    )

    # ── mutants ──────────────────────────────────────────────────────────────────────────────────────────────────
    mut = py("mutants.py", "--system", "replay-filing/system", "--production", prod_id, "--evh", EVH)
    check(
        "mutants: three killed, the fourth survives and coverage names _cron_waits, the rule no decision reaches",
        mut.returncode == 0
        and mut.stdout.count("killed (") == 3
        and "cron-waits-longer: SURVIVED" in mut.stdout
        and "_cron_waits" in mut.stdout,
        (mut.stdout[-800:], mut.stderr[-400:]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
