#!/usr/bin/env python3
"""Studies (RFC-029), $0 and offline: research over trials on validation items, evidence only from a confirmation.

    python tests/test_study.py

24 tickets of four sentences, their gold the first two: an arm that keeps two sentences beats one that keeps one.
A grid study from the one-sentence arm keeps `sentences: 2` and drops 3 and 4, closing its round; an agent study
asks and tells (a used ask refused, a trial that changes nothing noted as no effect, and V5 notes it); its round
does not hold back a plain round and is not closed by hand; a changed spec stops a study; a command sampler
plugs in; study-confirm on the test set is one look (1.52%), runs on the items no study saw, and finds the trial
better; results.tsv imports as a closed study.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import _runview  # noqa: E402
from evaluation_harness import _format  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-study-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-study")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)
WORDS = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "omicron",
    "pi",
    "rho",
    "sigma",
    "tau",
]


def evh(*args, extra=None):
    return subprocess.run([sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env={**env, **(extra or {})},
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)  # fmt: skip


def values(r):
    try:
        return (json.loads(r.stdout).get("result") or {}).get("values") or {}
    except ValueError:
        return {}


def system(name, sentences):
    _runstore.write_text(proj, f"systems/{name}.yaml",
                         f"system_id: {name}\nparams:\n  provider: echo\n  sentences: {sentences}\n")  # fmt: skip


def spec(name, text):
    p = proj / f"{name}.yaml"
    p.write_text(text)
    return str(p)


try:
    for side, rng in (("val", range(12)), ("test", range(12, 24))):
        src, gold = proj / f"src_{side}", proj / f"gold_{side}"
        src.mkdir(parents=True)
        gold.mkdir()
        for i in rng:
            s = [
                f"Ticket{i} " + " ".join(WORDS[(i + j * 3 + w) % len(WORDS)] for w in range(5)) + "."
                for j in range(4)
            ]
            (src / f"t{i:02d}.txt").write_text(" ".join(s) + "\n")
            (gold / f"t{i:02d}.txt").write_text(" ".join(s[:2]) + "\n")
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    r = None
    for ds, side in (("tk_val", "val"), ("tk_test", "test")):
        for argv in (
            ("dataset-create", "--dataset-id", ds, "--source-dir", f"src_{side}"),
            ("dataset-materialize", "--dataset-id", ds),
            ("label-import", f"gold_{side}", "--dataset-id", ds, "--set", "g", "--by", "t"),
            ("reference-promote", "--dataset-id", ds, "--labels", "g", "--tier", "gold", "--reason", "the first two sentences", "--by", "t"),
        ):  # fmt: skip
            r = evh(*argv)
            if r.returncode:
                break
    _runstore.write_text(
        proj, "goals/g.yaml",
        "goal_id: g\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n  - {dataset_id: tk_test, role: test}\n",
    )  # fmt: skip
    system("one_v1", 1)
    rb = evh("run", "--system", "one_v1", "--dataset", "tk_val", "--goal", "g")
    check("setup: validation and test sets of 12, their gold, a goal, the one-sentence arm run",
          r is not None and r.returncode == 0 and rb.returncode == 0, ((r.stderr if r else "") + rb.stderr)[-400:])  # fmt: skip

    # ── a grid study ──────────────────────────────────────────────────────────────────────────────────────────────
    grid = spec("grid", "dataset: tk_val\nbaseline: {system: one_v1}\nmeasure: overlap_f1\nsampler: grid\n"
                "accept: {point: {min_gain: 0}}\nstop: {trials: 5}\n"
                "space:\n  groups:\n    - {name: length, reason: how much to keep, params: {sentences: [2, 3, 4]}}\n")  # fmt: skip
    dry = evh("study-run", "g/s1", "--spec", grid, "--dry-run")
    r = evh("study-run", "g/s1", "--json")
    st = values(evh("studies", "--study", "g/s1", "--json")).get("study") or {}
    outs = {t["change"]["params"]["sentences"]: t["outcome"] for t in st.get("trials", [])}
    rounds = [
        _runstore.read_json(proj, f"rounds/g/{n}") if n.endswith(".json") else None
        for n in _runstore.listdir(proj, "rounds/g")
    ]
    check(
        "a grid study: sentences 2 kept, 3 and 4 dropped (measured against the best so far), the space exhausted",
        dry.returncode == 0 and "Nothing was called" in dry.stdout and r.returncode == 0
        and outs == {2: "kept", 3: "dropped", 4: "dropped"} and st.get("status") == "ended"
        and (st.get("best") or {}).get("config_id") == "s1-t1",
        (dry.stderr[-200:], r.stderr[-600:], outs, st.get("status")),
    )  # fmt: skip
    import yaml

    rnd = (
        yaml.safe_load(_runstore.read_text(proj, f"rounds/g/{st.get('round')}.yaml"))
        if st.get("round")
        else {}
    )
    check(
        "the study's round: marked study, closed when it ended, its dropped trials retired with their reasons, the baseline carried in",
        rnd.get("study") == "s1" and rnd.get("status") == "closed"
        and {a["system"] for a in rnd.get("arms") or [] if a.get("retired")} == {"s1-t2", "s1-t3"}
        and all(a["retired"]["reason"] for a in rnd["arms"] if a.get("retired"))
        and {a["system"]: a["entered"]["how"] for a in rnd["arms"]}
        == {"one_v1": "carried", "s1-t1": "ran", "s1-t2": "ran", "s1-t3": "ran"},
        rnd,
    )  # fmt: skip

    # ── an agent study ────────────────────────────────────────────────────────────────────────────────────────────
    agent = spec("agent", "dataset: tk_val\nbaseline: {system: one_v1}\nmeasure: overlap_f1\nsampler: agent\n"
                 "accept: {point: {min_gain: 0}}\nstop: {trials: 10}\ndirections: keep what a reader needs\n")  # fmt: skip
    r = evh("study-run", "g/s2", "--spec", agent)
    a1 = values(evh("study-ask", "g/s2", "--json")).get("ask_id")
    t1 = evh("study-tell", "g/s2", "--ask", str(a1), "--proposal-json",
             json.dumps({"params": {"sentences": 2}, "hypothesis": "two sentences cover the gold"}), "--json")  # fmt: skip
    again = evh(
        "study-tell", "g/s2", "--ask", str(a1), "--proposal-json", json.dumps({"params": {"sentences": 3}})
    )
    a2 = values(evh("study-ask", "g/s2", "--json")).get("ask_id")
    t2 = evh("study-tell", "g/s2", "--ask", str(a2), "--proposal-json",
             json.dumps({"params": {"note": "a knob the system does not read"}, "hypothesis": "nothing"}), "--json")  # fmt: skip
    check(
        "the agent sampler: ask, tell (kept), the same ask again refused, a change the system does not read: no effect",
        r.returncode == 0 and a1 and (values(t1).get("trial") or {}).get("outcome") == "kept"
        and again.returncode != 0 and "not the study's open ask" in again.stderr
        and (values(t2).get("trial") or {}).get("outcome") == "no effect",
        (r.stderr[-200:], t1.stderr[-300:], again.stderr[-200:], t2.stdout[-300:], t2.stderr[-300:]),
    )  # fmt: skip
    v = evh("validate")
    check("V5 notes the no-effect trial as the study's finding, not a copied result",
          "V5 study" in v.stdout and "g/s2" in v.stdout and "no effect" in v.stdout and "FAIL V5" not in v.stdout, v.stdout[-600:])  # fmt: skip
    plain = evh(
        "round-open", "--goal", "g", "--dataset", "tk_val", "--hypothesis", "a plain round beside the study"
    )
    st2 = values(evh("studies", "--study", "g/s2", "--json")).get("study") or {}
    by_hand = evh(
        "round-close", "--goal", "g", "--round", str(st2.get("round")), "--conclusion", "closed by hand here"
    )
    check(
        "a study's round holds no plain round back, and is not closed by hand",
        plain.returncode == 0 and by_hand.returncode != 0 and "closes when the study ends" in by_hand.stderr,
        (plain.stderr[-200:], by_hand.stderr[-200:]),
    )
    # A changed spec stops the study at its next step.
    _runstore.write_text(
        proj, "studies/g/s2.yaml", _runstore.read_text(proj, "studies/g/s2.yaml") + "# edited\n"
    )
    stopped = evh("study-ask", "g/s2")
    st2 = values(evh("studies", "--study", "g/s2", "--json")).get("study") or {}
    check("a spec changed mid-study stops it, with the reason",
          stopped.returncode != 0 and st2.get("status") == "ended" and "changed" in str((st2.get("end") or {}).get("reason")),
          (stopped.stderr[-300:], st2.get("end")))  # fmt: skip

    # ── the agent sampler as MCP tools (owner, 2026-11-09): the agent's own actor on what it does ──────────────────
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    r = evh("study-run", "g/s5", "--spec", agent)
    agent_env = {**env, "EVH_ACTOR": "agent:helper", "EVH_FOR": "person:test"}

    async def over_mcp():
        params = StdioServerParameters(
            command=sys.executable, args=[str(HERE / "cli.py"), "mcp"], cwd=str(proj), env=agent_env
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as sess:
            await sess.initialize()
            asked = await sess.call_tool("study-ask", {"study": "g/s5"})
            ask_id = json.loads(asked.content[0].text)["result"]["values"]["ask_id"]
            told = await sess.call_tool("study-tell", {"study": "g/s5", "ask": ask_id, "proposal-json": json.dumps(
                {"params": {"sentences": 2}, "hypothesis": "proposed over MCP"})})  # fmt: skip
            return asked, told

    asked, told = asyncio.run(over_mcp())
    st5 = values(evh("studies", "--study", "g/s5", "--json")).get("study") or {}
    t5 = (st5.get("trials") or [{}])[0]
    check(
        "study-ask and study-tell as MCP tools: the trial run and kept, recorded as the agent's for its person",
        r.returncode == 0 and not asked.is_error and not told.is_error and t5.get("outcome") == "kept"
        and (t5.get("actor") or {}).get("name") == "helper" and (t5.get("actor") or {}).get("for") == "test",
        (asked.content[0].text[:300], told.content[0].text[-300:], t5.get("actor")),
    )  # fmt: skip

    # ── a command sampler ─────────────────────────────────────────────────────────────────────────────────────────
    (proj / "sampler.py").write_text(
        "import json, sys\nsent = [2]\nfor line in sys.stdin:\n    msg = json.loads(line)\n"
        "    if 'ask' in msg:\n        out = {'params': {'sentences': sent.pop()}, 'hypothesis': 'from a program'} if sent else {'stop': 'done'}\n"
        "    else:\n        out = {}\n    print(json.dumps(out), flush=True)\n"
    )  # fmt: skip
    cmd = spec("cmd", "dataset: tk_val\nbaseline: {system: one_v1}\nmeasure: overlap_f1\n"
               f"sampler: {{command: '{sys.executable} sampler.py'}}\naccept: {{point: {{min_gain: 0}}}}\nstop: {{trials: 4}}\n")  # fmt: skip
    r = evh("study-run", "g/s3", "--spec", cmd)
    st3 = values(evh("studies", "--study", "g/s3", "--json")).get("study") or {}
    check(
        "a command sampler speaking ask/tell: its one proposal kept, then it stops the study",
        r.returncode == 0 and [t["outcome"] for t in st3.get("trials", [])] == ["kept"]
        and "sampler stopped" in str((st3.get("end") or {}).get("reason")),
        (r.stderr[-400:], st3.get("end")),
    )  # fmt: skip

    # ── the confirmation ──────────────────────────────────────────────────────────────────────────────────────────
    d = evh("study-confirm", "g/s1", "--test", "tk_test", "--rule", "superiority", "--dry-run")
    c = evh("study-confirm", "g/s1", "--test", "tk_test", "--rule", "superiority", "--json")
    conf = values(c).get("confirm") or {}
    looks = (values(evh("looks", "--dataset", "tk_test", "--json")).get("sets") or [{}])[0]
    check(
        "study-confirm: the dry run runs nothing; then one look at 1.52% on the 12 test items, the trial better, "
        "promotion suggested",
        d.returncode == 0 and "look 1" in d.stdout and "12 test item(s)" in d.stdout
        and c.returncode == 0 and conf.get("outcome") == "better" and (conf.get("look") or {}).get("number") == 1
        and looks.get("next") == 2 and "run-promote" in c.stderr,
        (d.stdout[-300:], c.stderr[-500:], conf, looks.get("next")),
    )  # fmt: skip

    # ── what a sampler is shown, recorded ─────────────────────────────────────────────────────────────────────────
    evs = [json.loads(x) for x in _runstore.read_text(proj, "studies/g/s5.events.jsonl").splitlines()]
    ask_ev = next(e for e in evs if e.get("event") == "ask")
    tr_ev = next(e for e in evs if e.get("event") == "trial")
    st_seen = values(evh("study-ask", "g/s3", "--json"))  # an ended study: refused, nothing shown
    shown_state = json.loads(asked.content[0].text)["result"]["values"]["state"]
    check(
        "the agent is shown the best's 5 weakest validation items (their text); the ask and its trial record them",
        len(shown_state["weakest_items"]) == 5 and all(x["text"] for x in shown_state["weakest_items"])
        and len(ask_ev.get("shown") or []) == 5 and tr_ev.get("shown") == ask_ev.get("shown") and not st_seen,
        (len(shown_state.get("weakest_items") or []), ask_ev.get("shown"), tr_ev.get("shown")),
    )  # fmt: skip

    # ── a prompt root's varied file changed by a trial ────────────────────────────────────────────────────────────
    lib = proj / "lib"
    (lib / "sub").mkdir(parents=True)
    (lib / "sub" / "b.txt").write_text("system v1\n")
    (lib / "a.txt").write_text("fixed\n")
    _runstore.write_text(proj, "systems/root_v1.yaml", "system_id: root_v1\n"
                         "prompt_root: {name: lib, path: lib, vary: [sub/b.txt]}\nparams:\n  provider: echo\n  sentences: 1\n")  # fmt: skip
    rr = evh("run", "--system", "root_v1", "--dataset", "tk_val", "--goal", "g")
    rspec = spec("rootspec", "dataset: tk_val\nbaseline: {system: root_v1}\nmeasure: overlap_f1\nsampler: agent\n"
                 "accept: {point: {min_gain: -1}}\nstop: {trials: 3}\n")  # fmt: skip
    evh("study-run", "g/s6", "--spec", rspec)
    a6 = values(evh("study-ask", "g/s6", "--json")).get("ask_id")
    t6 = evh("study-tell", "g/s6", "--ask", str(a6), "--proposal-json",
             json.dumps({"prompts": {"lib/sub/b.txt": "system v2\n"}, "hypothesis": "a new system prompt"}), "--json")  # fmt: skip
    import yaml

    tcfg = (
        yaml.safe_load(_runstore.read_text(proj, "studies/g/s6/s6-t1.yaml"))
        if _runstore.exists(proj, "studies/g/s6/s6-t1.yaml")
        else {}
    )
    trial_run = next((n for n in _runstore.listdir(proj, "runs") if n.startswith("s6-t1_")), None)
    tfp = (_runview.record_of(proj, trial_run)[1].get("fingerprint") or {}) if trial_run else {}
    import hashlib

    check(
        "a trial changes a prompt root's varied file: its version in the trial's config, and in the run's settings",
        rr.returncode == 0 and t6.returncode == 0 and "sub/b.txt" in ((tcfg.get("prompt_root") or {}).get("versions") or {})
        and (tfp.get("settings") or {}).get("prompts", {}).get("lib/sub/b.txt") == hashlib.sha256(b"system v2\n").hexdigest(),
        (rr.stderr[-200:], t6.stderr[-300:], tcfg.get("prompt_root"), (tfp.get("settings") or {}).get("prompts")),
    )  # fmt: skip

    # ── the scorer changed mid-study stops it ─────────────────────────────────────────────────────────────────────
    (proj / "wrap.py").write_text(
        "import time\nfrom evaluation_harness.adapter import Result, score  # noqa: F401\n"
        "from evaluation_harness.adapter import call_system as _call\n"
        "def call_system(text, params):\n    time.sleep(float(params.get('sleep', 0)))\n    return _call(text, params)\n"
    )  # fmt: skip
    _runstore.write_text(proj, "systems/wrap_v1.yaml", "system_id: wrap_v1\nadapter: wrap.py\n"
                         "params:\n  provider: echo\n  sentences: 1\n")  # fmt: skip
    evh("run", "--system", "wrap_v1", "--dataset", "tk_val", "--goal", "g")
    wspec = spec("wrapspec", "dataset: tk_val\nbaseline: {system: wrap_v1}\nmeasure: overlap_f1\nsampler: agent\n"
                 "accept: {point: {min_gain: 0}}\nstop: {trials: 3}\n")  # fmt: skip
    evh("study-run", "g/s7", "--spec", wspec)
    (proj / "wrap.py").write_text((proj / "wrap.py").read_text() + "LIMIT = 3\n")
    sc = evh("study-ask", "g/s7")
    st7 = values(evh("studies", "--study", "g/s7", "--json")).get("study") or {}
    check("the scoring code changed mid-study (the baseline's adapter): the study stops, saying so",
          sc.returncode != 0 and "scoring code changed" in str((st7.get("end") or {}).get("reason")), (sc.stderr[-300:], st7.get("end")))  # fmt: skip

    # ── a study killed mid-trial, resumed ─────────────────────────────────────────────────────────────────────────
    import signal
    import time

    _runstore.write_text(proj, "systems/slow_v1.yaml", "system_id: slow_v1\nadapter: wrap.py\n"
                         "params:\n  provider: echo\n  sentences: 1\n  sleep: 0.4\n")  # fmt: skip
    evh("run", "--system", "slow_v1", "--dataset", "tk_val", "--goal", "g")
    kspec = spec("killspec", "dataset: tk_val\nbaseline: {system: slow_v1}\nmeasure: overlap_f1\nsampler: grid\n"
                 "accept: {point: {min_gain: 0}}\nstop: {trials: 3}\n"
                 "space:\n  groups:\n    - {name: length, reason: how much, params: {sentences: [2, 3]}}\n")  # fmt: skip
    log = proj / "s8.log"
    with open(log, "w") as fh:
        pk = subprocess.Popen([sys.executable, str(HERE / "cli.py"), "study-run", "g/s8", "--spec", kspec], cwd=proj, env=env,
                              stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)  # fmt: skip
    for _ in range(300):
        time.sleep(0.1)
        if _runstore.exists(proj, "studies/g/s8/s8-t1.yaml") and any(
            n.startswith("s8-t1_") for n in _runstore.listdir(proj, "runs")
        ):
            break
    os.killpg(pk.pid, signal.SIGKILL)
    pk.wait(timeout=30)
    res = evh("study-run", "g/s8", "--resume")
    st8 = values(evh("studies", "--study", "g/s8", "--json")).get("study") or {}
    outs8 = [(t.get("k"), t.get("outcome")) for t in st8.get("trials", [])]
    check(
        "a study killed mid-trial and resumed: the interrupted trial recorded as such, the grid tried again after it",
        res.returncode == 0 and "interrupted" in res.stdout and outs8[:2] == [(1, "failed"), (2, "kept")]
        and st8.get("status") == "ended",
        (res.stdout[-400:], res.stderr[-300:], outs8),
    )  # fmt: skip

    # ── the goal's page and evh goals show the studies ────────────────────────────────────────────────────────────
    gv = evh("goals", "--goal", "g")
    cat = evh("catalog")
    page = (proj / ".build" / "catalog" / "g" / "g.html").read_text() if cat.returncode == 0 else ""
    check(
        "the goal's page: each study's trials (change, hypothesis, outcome, why), its confirmation; evh goals too",
        "studies: research, then one confirmation" in page and "sentences = 2" in page and "confirmed on tk_test" in page
        and "study s1: ended" in gv.stdout and "confirmed on tk_test: better" in gv.stdout,
        (cat.stderr[-300:], gv.stdout[-600:]),
    )  # fmt: skip

    # ── results.tsv ───────────────────────────────────────────────────────────────────────────────────────────────
    (proj / "results.tsv").write_text(
        "commit\tval_bpb\tmemory_gb\tstatus\tdescription\n"
        "a1b2c3d\t0.997\t44.0\tkeep\tbaseline\nb2c3d4e\t0.993\t44.2\tkeep\tbigger lr\nc3d4e5f\t1.005\t44.0\tdiscard\tswiglu\n"
    )  # fmt: skip
    imp = evh("study-import", "results.tsv", "--goal", "g", "--study", "karpathy")
    st4 = values(evh("studies", "--study", "g/karpathy", "--json")).get("study") or {}
    ls = values(evh("studies", "--json")).get("studies") or []
    check(
        "results.tsv: a closed study of 3 trials (2 kept, 1 dropped), listed with the others",
        imp.returncode == 0 and [t["outcome"] for t in st4.get("trials", [])] == ["kept", "kept", "dropped"]
        and st4.get("status") == "ended" and len(ls) == 8,
        (imp.stderr[-300:], len(ls)),
    )  # fmt: skip
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
