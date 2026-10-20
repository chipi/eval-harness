#!/usr/bin/env python3
"""Assertions for the judging pass. No network, no API key, no money: a fake judge.

    python scripts/test_judge_score.py

Covers ADR-0001's controls: the validation gate, a hash-stable judging set, blinding,
projection, resume, the mid-run cost cap with partial results kept, and that the prompt
for 16 summaries is byte-identical to the one SummEval validated.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_score as js  # noqa: E402

HERE = Path(__file__).resolve().parent
ok = []


def check(label, cond):
    ok.append((label, bool(cond)))
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises_exit(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


# ── a small world: 20 arms, 3 items, two judges ──────────────────────────────
N_ARMS = 20
ITEMS = ["itemA", "itemB", "itemC"]
FAMILIES = ["gemma", "qwen", "other", "other"]
ARMS = [{"config_id": f"arm{k:02d}_v1", "run": f"arm{k:02d}_v1_2026", "dir": None,
         "family": FAMILIES[k % 4]} for k in range(N_ARMS)]
ARTICLES = {i: f"Article text for {i}. It is long enough to be an article." for i in ITEMS}
OUTPUTS = {a["config_id"]: {i: f"summary q{k:02d} about {i}" for i in ITEMS}
           for k, a in enumerate(ARMS)}


def scorer(**over):
    sc = {
        "scorer_id": "judge-test-v1", "kind": "judge", "dataset_id": "ds",
        "_sha256": "0" * 64, "cost_cap_usd": 1.0,
        "judges": [
            {"id": "ja", "params": {"model": "m_a", "family": "gemma", "usd_per_mtok_in": 1.0,
                                    "usd_per_mtok_out": 2.0}},
            {"id": "jb", "params": {"model": "m_b", "family": "qwen", "usd_per_mtok_in": 1.0,
                                    "usd_per_mtok_out": 2.0}}],
        "prompt": {"file": "examples/summeval-judging/prompt.txt"},
        "protocol": {"outputs_per_call": 16, "blinding": True, "order_seed": 0,
                     "position_check_fraction": 0.34, "noise_check_fraction": 0.34,
                     "contested_threshold": 0.5},
    }
    sc.update(over)
    return sc


BASE = js.prompt_text(scorer())


def manifest_for(sc=None, outputs=None, arms=None):
    sc = sc or scorer()
    arms = arms or ARMS
    return js.build_manifest(sc, "ds", "i" * 64, ITEMS, arms, ARTICLES,
                             outputs or OUTPUTS, BASE)


def quality(s):
    return 1 + (int(re.search(r"q(\d+)", s).group(1)) % 5)


def fake_judge(cost=0.01, reply=None):
    """Scores a summary from the 'qNN' marker in its text. Judge A: dims s, s, s+1, s-1
    (mean s, clipped); judge B: s-1 on every dimension. Records every call."""
    seen = []

    def call(message, params):
        seen.append((params["model"], message))
        body = message.split("SUMMARIES:\n", 1)[1]
        sums = re.findall(r"^\d+\. (.*)$", body, re.M)
        s = [quality(x) for x in sums]
        if params["model"] == "m_a":
            d = {"coherence": s, "consistency": s,
                 "fluency": [min(5, v + 1) for v in s], "relevance": [max(1, v - 1) for v in s]}
        else:
            t = [max(1, v - 1) for v in s]
            d = {k: t for k in js.DIMS}
        out = reply if reply is not None else json.dumps(d)
        return SimpleNamespace(output=out, tokens_in=100, tokens_out=20, cost_usd=cost,
                               latency_ms=1.0, extra={"truncated": 0.0},
                               meta={"finish_reason": "stop", "provider": "fake",
                                     "response_model": params["model"]})
    call.seen = seen
    return call


def expected_a(k):
    s = 1 + k % 5
    return (s + s + min(5, s + 1) + max(1, s - 1)) / 4


def expected_b(k):
    return max(1, 1 + k % 5 - 1)


# ── blocks and the prompt ────────────────────────────────────────────────────
check("29 outputs at 16 per call -> blocks 15 + 14, not 16 + 13", js.block_sizes(29, 16) == [15, 14])
check("16 outputs -> one block of 16", js.block_sizes(16, 16) == [16])
check("17 outputs -> 9 + 8", js.block_sizes(17, 16) == [9, 8])
check("5 outputs -> one block of 5", js.block_sizes(5, 16) == [5])
check("the largest block never exceeds outputs_per_call",
      all(max(js.block_sizes(n, 16)) <= 16 for n in range(2, 80)))

ad = js.summeval_adapter()
item16 = {"article": "An article.", "summaries": [f"s{i}" for i in range(16)]}
mine = js.build_message(BASE, item16["article"], item16["summaries"])
check("N=16: the message is byte-identical to SummEval's own _judge_message",
      mine == ad._judge_message(item16, {}))
check("N=16: the prompt sha256 equals SummEval's _prompt_sha256",
      hashlib.sha256(js.render_prompt(BASE, 16).encode()).hexdigest() == ad._prompt_sha256({}))
real = js.load_scorer(HERE.parent / "data" / "scorers" / "judge-summ-v1.yaml")
check("the committed scorer's sha256_at_16 is SummEval's prompt hash",
      real["prompt"]["sha256_at_16"] == ad._prompt_sha256({}))
p15 = js.render_prompt(BASE, 15)
check("N=15: both count phrases say 15 and no other word of the prompt changed",
      "15 numbered summaries" in p15 and "a list of 15 integers" in p15
      and p15.replace("15", "16") == BASE)

reply16 = json.dumps({d: list(range(1, 6)) * 3 + [1] for d in js.DIMS})
theirs = ad.parse_scores(reply16)
check("N=16: parse_block agrees with SummEval's parse_scores (mean of the four dimensions)",
      js.parse_block(reply16, 16) == [sum(theirs[d][i] for d in js.DIMS) / 4 for i in range(16)])
check("a dimension with the wrong count is a parse failure",
      js.parse_block(json.dumps({d: [3] * 14 for d in js.DIMS}), 15) is None)
check("a missing dimension is a parse failure",
      js.parse_block(json.dumps({d: [3] * 15 for d in js.DIMS[:3]}), 15) is None)
check("a score outside 1..5 is a parse failure",
      js.parse_block(json.dumps({d: [3] * 14 + [9] for d in js.DIMS}), 15) is None)
check("a reply wrapped in prose and fences still parses",
      js.parse_block("Sure:\n```json\n" + json.dumps({d: [4] * 15 for d in js.DIMS}) + "\n```", 15)
      == [4.0] * 15)

# ── the judging set: deterministic, hash-stable, pinned ──────────────────────
m1, m2 = manifest_for(), manifest_for()
check("the judging set is deterministic: same inputs, same hash", m1 == m2)
check("its id pins the arm count and a hash prefix",
      m1["judging_set_id"] == f"ds-{N_ARMS}arms-{m1['judging_set_sha256'][:12]}")
check("20 arms -> two blocks of 10 per item", all([len(b) for b in it["primary"]] == [10, 10]
                                                    for it in m1["items"]))
check("a different seed is a different set",
      manifest_for(scorer(protocol={**scorer()["protocol"], "order_seed": 1}))["judging_set_id"]
      != m1["judging_set_id"])
bumped = {a: dict(o) for a, o in OUTPUTS.items()}
bumped[ARMS[3]["config_id"]]["itemB"] += " changed"
check("one changed output is a different set", manifest_for(outputs=bumped)["judging_set_id"]
      != m1["judging_set_id"])
check("a different arm set is a different set (not an append)",
      manifest_for(arms=ARMS[:-1])["judging_set_id"] != m1["judging_set_id"])
check("every arm sits in exactly one block per item, in every pass",
      all(sorted(sum(it[k], [])) == sorted(a["config_id"] for a in ARMS)
          for it in m1["items"] for k in ("primary", "position")))
check("order differs between items", len({tuple(sum(it["primary"], [])) for it in m1["items"]}) == 3)
check("the position pass reshuffles (different blocks) on every item",
      all(it["primary"] != it["position"] for it in m1["items"]))
check("control subsets are deterministic and sized by fraction",
      len(m1["position_items"]) == 1 and m1["noise_items"] == manifest_for()["noise_items"])

with tempfile.TemporaryDirectory() as td:
    sets = Path(td)
    p = js.freeze(m1, sets)
    check("freeze writes the manifest under its id", p.name == f"{m1['judging_set_id']}.json")
    js.freeze(m1, sets)
    check("freezing the same set again is a no-op", True)
    bad = dict(m1, judging_set_sha256="deadbeef")
    check("an existing set with a different hash is never rewritten",
          raises_exit(lambda: js.freeze(bad, sets)))

# ── blinding ─────────────────────────────────────────────────────────────────
msgs = [js.message_for(m1, BASE, ARTICLES, OUTPUTS, it, p, b)
        for it in m1["items"] for p in ("primary", "position") for b in range(2)]
names = [a["config_id"] for a in ARMS] + [a["run"] for a in ARMS] + ["gemma", "qwen"]
check("no arm id, run name or family appears in any prompt",
      not any(n in m for m in msgs for n in names))
check("summaries are numbered by position only",
      all(re.search(r"^1\. summary", m.split("SUMMARIES:\n")[1], re.M) for m in msgs))

# ── running the pass, projection, controls ───────────────────────────────────
def run_all(tmp, sc=None, call=None, cap=None, retry=False, m=None):
    m = m or m1
    return js.run_judging(m, sc or scorer(), BASE, ARTICLES, OUTPUTS, Path(tmp), call, cap,
                          retry_unparsed=retry, log=lambda *_: None)


N_TASKS = len(js.tasks(m1))
with tempfile.TemporaryDirectory() as td:
    judge = fake_judge()
    st = run_all(td, call=judge)
    check("calls = judges x (primary + position + noise blocks)",
          st["calls"] == 2 * N_TASKS and len(judge.seen) == 2 * N_TASKS)
    sc = scorer()
    scores = js.load_scores(m1, sc, Path(td))
    proj = js.project(sc, scores, ITEMS)
    k_of = {a["config_id"]: k for k, a in enumerate(ARMS)}
    check("projection: judge A's score for an arm is the mean of its four dimensions",
          all(abs(proj[i][c]["ja"] - expected_a(k)) < 1e-9 for i in ITEMS for c, k in k_of.items()))
    check("projection: judge B's score is right, wherever the shuffle put the arm",
          all(abs(proj[i][c]["jb"] - expected_b(k)) < 1e-9 for i in ITEMS for c, k in k_of.items()))
    check("projection: the primary is the mean over judges",
          all(abs(proj[i][c]["_mean"] - (expected_a(k) + expected_b(k)) / 2) < 1e-9
              for i in ITEMS for c, k in k_of.items()))

    # an item one judge has not finished is not scored by a mean over a different set of judges
    half = js.load_scores(m1, sc, Path(td))
    del half["jb"]["primary"]["itemB"]
    check("an item missing one judge's verdict is dropped from the primary",
          sorted(js.project(sc, half, ITEMS)) == ["itemA", "itemC"])

    first = sorted(Path(td).glob("*/*.json"))
    before = {f: f.read_bytes() for f in first}
    judge2 = fake_judge()
    st2 = run_all(td, call=judge2)
    check("resume: a second run makes no calls", st2["calls"] == 0 and not judge2.seen)
    check("resume: stored verdicts are untouched",
          all(f.read_bytes() == before[f] for f in first))
    victim = Path(td) / "jb" / f"itemA.primary.b1.json"
    victim.unlink()
    judge3 = fake_judge()
    st3 = run_all(td, call=judge3)
    check("resume: one deleted verdict costs exactly one call", st3["calls"] == 1)
    check("--no-calls (call=None) re-reads and calls nothing",
          run_all(td, call=None)["calls"] == 0)

    # controls
    noise = js.compare_passes(scores["ja"]["primary"], scores["ja"]["noise"])
    check("noise control: a deterministic judge repeats itself (tau 1, diff 0)",
          noise["n_items"] == 1 and noise["mean_tau"] == 1.0 and noise["mean_abs_diff"] == 0.0)
    pos = js.compare_passes(scores["ja"]["primary"], scores["ja"]["position"])
    check("position control: scores that depend only on content do not move with order",
          pos["n_items"] == 1 and pos["mean_abs_diff"] == 0.0)
    pm = js.build_message(BASE, ARTICLES["itemA"],
                          [OUTPUTS[a]["itemA"] for a in m1["items"][0]["primary"][0]])
    check("noise pass sends the primary pass's prompt (the same message, repeated)",
          js.message_for(m1, BASE, ARTICLES, OUTPUTS, m1["items"][0], "noise", 0) == pm)
    stored = json.loads((Path(td) / "ja" / "itemA.primary.b0.json").read_text())
    check("a stored verdict keeps the raw reply and the bill",
          stored["output"].startswith("{") and stored["cost_usd"] == 0.01
          and stored["prompt_sha256"] == hashlib.sha256(pm.encode()).hexdigest())

    summ = js.summarise(m1, sc, ARMS, scores, proj, st, "validated judge", True, Path(td))
    a0 = summ["per_arm"]["arm00_v1"]
    check("self-family: an arm of the judge's own family is flagged in that judge's column",
          a0["self_family"] == {"ja": True, "jb": False}
          and summ["per_arm"]["arm01_v1"]["self_family"] == {"ja": False, "jb": True})
    check("summary: per-judge columns and primary are reported",
          a0["judge_ja"] is not None and a0["judge_jb"] is not None
          and abs(a0["judge_score"] - (a0["judge_ja"] + a0["judge_jb"]) / 2) < 1e-5)
    check("summary: inter-judge agreement reported", summ["judge_agreement"]["ja~jb"]["n_items"] == 3)
    check("summary: position and noise controls reported per judge",
          summ["controls"]["ja"]["noise"]["n_items"] == 1)
    check("contested: judges differing by more than the threshold on an arm are flagged",
          all((abs(v["judge_ja"] - v["judge_jb"]) > 0.5) == v["contested"]
              for v in summ["per_arm"].values()))

# ── dry run ──────────────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    est = js.estimate(m1, scorer(), BASE, ARTICLES, OUTPUTS, Path(td))
    check("dry-run: calls per judge = number of (item, pass, block) tasks",
          est["ja"]["calls"] == N_TASKS and est["jb"]["calls"] == N_TASKS)
    check("dry-run: tokens and cost are positive, cost from the price table",
          est["ja"]["tokens_in"] > 0 and est["ja"]["est_cost_usd"] > 0)
    run_all(td, call=fake_judge(), cap=None)
    est2 = js.estimate(m1, scorer(), BASE, ARTICLES, OUTPUTS, Path(td))
    check("dry-run: stored verdicts are not priced again", est2["ja"]["calls"] == 0
          and est2["ja"]["stored"] == N_TASKS)

# ── cost cap: abort mid-run, keep what was bought ────────────────────────────
with tempfile.TemporaryDirectory() as td:
    judge = fake_judge(cost=0.01)
    st = run_all(td, call=judge, cap=0.055)
    files = list(Path(td).glob("*/*.json"))
    check("cost cap: the pass aborts mid-run", st["aborted"] and st["calls"] == 6)
    check("cost cap: every paid verdict is kept on disk", len(files) == 6)
    check("cost cap: spend does not run on past the cap by more than one call",
          st["spent_usd"] < 0.055 + 0.01 + 1e-9)
    sc = scorer()
    part = js.project(sc, js.load_scores(m1, sc, Path(td)), ITEMS)
    check("cost cap: only items every judge finished are projected", len(part) < len(ITEMS))
    judge_b = fake_judge(cost=0.01)
    st_b = run_all(td, call=judge_b, cap=None)
    check("cost cap: a rerun with room finishes only what is missing",
          st_b["calls"] == 2 * N_TASKS - 6 and not st_b["aborted"])
    check("cost cap: a stored bill counts against the cap on resume",
          run_all(td, call=fake_judge(), cap=0.01)["calls"] == 0)
    zero = tempfile.mkdtemp(dir=td)
    check("cost cap: a cap of 0 makes no call", run_all(zero, call=fake_judge(), cap=0.0)["calls"] == 0)

with tempfile.TemporaryDirectory() as td:
    st = run_all(td, call=fake_judge(reply="I cannot do this."))
    sc = scorer()
    sc_scores = js.load_scores(m1, sc, Path(td))
    check("an unparseable reply is stored with scores null, and the item is not scored",
          json.loads(next(Path(td).glob("ja/*.json")).read_text())["scores"] is None
          and js.project(sc, sc_scores, ITEMS) == {})
    good = fake_judge()
    st2 = run_all(td, call=good)
    check("resume does not re-pay for unparsed replies unless asked", st2["calls"] == 0)
    st3 = run_all(td, call=good, retry=True)
    check("--retry-unparsed calls them again", st3["calls"] == 2 * N_TASKS)

with tempfile.TemporaryDirectory() as td:
    run_all(td, call=fake_judge())
    other = scorer(judges=[dict(scorer()["judges"][0], params={"model": "m_a", "family": "gemma",
                                                               "usd_per_mtok_in": 9.0,
                                                               "usd_per_mtok_out": 2.0}),
                           scorer()["judges"][1]])
    check("verdicts stored by a changed judge definition are refused, not mixed",
          raises_exit(lambda: run_all(td, sc=other, call=fake_judge())))

# ── the validation gate ──────────────────────────────────────────────────────
real_runs = HERE.parent / "data" / "runs"
check("the committed scorer passes the gate against the committed SummEval runs",
      js.validation_problems(real, real_runs) == [])
no_val = {k: v for k, v in real.items() if k != "validation"}
check("no validation block: refused", js.validation_problems(no_val, real_runs) != [])
ghost = dict(real, validation=dict(real["validation"], runs=[
    dict(r, run="se_nonexistent_run") for r in real["validation"]["runs"]]))
check("a validation that names no committed run: refused",
      any("is not in" in p for p in js.validation_problems(ghost, real_runs)))
wrong = dict(real, validation=dict(real["validation"], runs=[
    dict(r, value=0.9) for r in real["validation"]["runs"]]))
check("a claimed value that the committed run does not have: refused",
      any("claims" in p for p in js.validation_problems(wrong, real_runs)))
swap = dict(real, validation=dict(real["validation"], runs=[
    dict(r, judge=("qwen_s" if r["judge"] == "gemma_l" else "gemma_l"))
    for r in real["validation"]["runs"]]))
check("a run that measured a different model than the judge: refused",
      any("measured model" in p for p in js.validation_problems(swap, real_runs)))
partial = dict(real, validation=dict(real["validation"], runs=real["validation"]["runs"][:1]))
check("a judge no validation run names: refused",
      any("no validation run names it" in p for p in js.validation_problems(partial, real_runs)))
check("a prompt that is not the validated one: refused",
      any("sha256_at_16" in p for p in js.validation_problems(
          dict(real, prompt=dict(real["prompt"], sha256_at_16="0" * 64)), real_runs)))
one_family = dict(real, judges=[real["judges"][0], real["judges"][0]])
with tempfile.TemporaryDirectory() as td:
    pth = Path(td) / "x.yaml"
    import yaml
    pth.write_text(yaml.safe_dump({k: v for k, v in one_family.items() if not k.startswith("_")}))
    check("a scorer whose judges share a vendor family is refused",
          raises_exit(lambda: js.load_scorer(pth)))
    # the CLI: refuses an unvalidated scorer before reading data or calling anything
    pth2 = Path(td) / "judge-test-unval.yaml"
    pth2.write_text(yaml.safe_dump({k: v for k, v in no_val.items() if not k.startswith("_")}
                                   | {"scorer_id": "judge-test-unval"}))
    old = (js.SCORERS, sys.argv)
    js.SCORERS = Path(td)
    sys.argv = ["judge_score.py", "--dataset-id", real["dataset_id"], "--scorer", "judge-test-unval"]
    try:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = js.main()
    finally:
        js.SCORERS, sys.argv = old
    check("CLI: an unvalidated scorer exits 3 and says REFUSED", rc == 3 and "REFUSED" in buf.getvalue())

# ── scored runs: shape, provenance, originals untouched, readable by the leaderboard ──
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    runs = td / "runs"
    arms = []
    for k, a in enumerate(ARMS):
        d = runs / a["run"]
        (d / "outputs").mkdir(parents=True)
        rows = []
        for i in ITEMS:
            (d / "outputs" / f"{i}.txt").write_text(OUTPUTS[a["config_id"]][i])
            rows.append({"item_id": i, "coverage": 0.3, "cost_usd": 0.001, "latency_ms": 5.0,
                         "tokens_in": 10.0, "_meta": {"usage": {"cost": 0.001}}})
        (d / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (d / "metrics.json").write_text(json.dumps({
            "config_id": a["config_id"], "run_id": a["run"], "dataset_id": "ds", "created_at": "2026",
            "primary_metric": "coverage", "scores": {"coverage": 0.3},
            "metric_kinds": {"coverage": "quality", "cost_usd": "cost"},
            "params": {"family": a["family"]}, "fingerprint": {"hash": "abc", "instrument": {
                "adapter": {"id": "old"}}, "arm": {"config_id": a["config_id"]}}}))
        arms.append(dict(a, dir=d))
    found = js.discover_arms("ds", "_v1", runs)
    check("discover_arms finds one primary run per arm", [a["config_id"] for a in found]
          == sorted(a["config_id"] for a in ARMS))
    before = {p: p.read_bytes() for p in runs.rglob("*") if p.is_file()}
    sc = scorer()
    vdir = td / "v"
    run_all(vdir, call=fake_judge())
    proj = js.project(sc, js.load_scores(m1, sc, vdir), ITEMS)
    out = td / "judged" / sc["scorer_id"]
    js.write_scored_runs(m1, sc, arms, proj, out, "validated judge", True)
    r0 = out / arms[0]["run"]
    check("scored runs land in a separate dir, one per original run, same name",
          sorted(p.name for p in out.iterdir()) == sorted(a["run"] for a in ARMS))
    check("the originals are untouched (byte for byte)",
          all(p.read_bytes() == b for p, b in before.items()))
    pr = [json.loads(x) for x in (r0 / "predictions.jsonl").read_text().splitlines()]
    mj = json.loads((r0 / "metrics.json").read_text())
    check("predictions carry the primary, per-judge columns and the CARRY fields",
          len(pr) == 3 and {"judge_score", "judge_ja", "judge_jb", "cost_usd", "latency_ms"}
          <= set(pr[0]) and pr[0]["cost_usd"] == 0.001 and "coverage" not in pr[0])
    check("metrics.json: primary_metric, scores, provenance, fingerprint hash invalidated",
          mj["primary_metric"] == "judge_score" and abs(mj["scores"]["judge_score"]
          - (expected_a(0) + expected_b(0)) / 2) < 1e-9 and mj["judged_from"] == arms[0]["run"]
          and mj["judged_with"]["judging_set_id"] == m1["judging_set_id"]
          and mj["fingerprint"]["hash"] is None and "coverage" not in mj["scores"])
    check("metrics.json: kinds mark judge columns quality", mj["metric_kinds"]["judge_score"] == "quality")
    js.write_scored_runs(m1, sc, arms, proj, td / "unval", "unvalidated judge", False)
    mu = json.loads((td / "unval" / arms[0]["run"] / "metrics.json").read_text())
    check("--unvalidated: the primary metric and the label say so",
          mu["primary_metric"] == "judge_score_unvalidated" and mu["judge_label"] == "unvalidated judge"
          and mu["judged_with"]["validated"] is False)
    # Python of the running interpreter: the same one that ran these assertions.
    env = dict(os.environ, EVAL_RUNS_DIR=str(out))
    lb = subprocess.run([sys.executable, str(HERE / "leaderboard.py"), "--dataset-id", "ds"],
                        cwd=HERE.parent, env=env, capture_output=True, text=True)
    check("leaderboard reads the scored runs with EVAL_RUNS_DIR (exit 0, shows judge_score)",
          lb.returncode == 0 and "judge_score" in lb.stdout)
    if lb.returncode != 0:
        print((lb.stdout + lb.stderr)[-600:])

bad = [l for l, c in ok if not c]
print(f"\n{len(ok) - len(bad)}/{len(ok)} assertions passed")
if bad:
    print("FAILED:", *bad, sep="\n  ")
    sys.exit(1)
