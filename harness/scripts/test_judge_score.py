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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import functools
import operator

import judge_score as js
import judging
from _common import load_module

HERE = Path(__file__).resolve().parent
from _check import check, summary  # noqa: E402


def _exit(fn):
    """The message of the SystemExit fn raises, or '' if it does not."""
    try:
        fn()
    except SystemExit as exc:
        return str(exc.code)
    return ""


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
ARMS: list[dict] = [
    {"config_id": f"arm{k:02d}_v1", "run": f"arm{k:02d}_v1_2026", "dir": None, "family": FAMILIES[k % 4]}
    for k in range(N_ARMS)
]
ARTICLES = {i: f"Article text for {i}. It is long enough to be an article." for i in ITEMS}
OUTPUTS = {a["config_id"]: {i: f"summary q{k:02d} about {i}" for i in ITEMS} for k, a in enumerate(ARMS)}


def scorer(**over):
    sc = {
        "scorer_id": "judge-test-v1",
        "kind": "judge",
        "dataset_id": "ds",
        "_sha256": "0" * 64,
        "cost_cap_usd": 1.0,
        "judges": [
            {
                "id": "ja",
                "params": {
                    "model": "m_a",
                    "family": "gemma",
                    "usd_per_mtok_in": 1.0,
                    "usd_per_mtok_out": 2.0,
                },
            },
            {
                "id": "jb",
                "params": {"model": "m_b", "family": "qwen", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0},
            },
        ],
        "prompt": {"file": "examples/summeval-judging/prompt.txt"},
        "protocol": {
            "outputs_per_call": 16,
            "blinding": True,
            "order_seed": 0,
            "position_check_fraction": 0.34,
            "noise_check_fraction": 0.34,
            "contested_threshold": 0.5,
        },
    }
    sc.update(over)
    return sc


BASE = js.prompt_text(scorer())


def manifest_for(sc=None, outputs=None, arms=None):
    sc = sc or scorer()
    arms = arms or ARMS
    return js.build_manifest(sc, "ds", "i" * 64, ITEMS, arms, ARTICLES, outputs or OUTPUTS, BASE)


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
            d = {
                "coherence": s,
                "consistency": s,
                "fluency": [min(5, v + 1) for v in s],
                "relevance": [max(1, v - 1) for v in s],
            }
        else:
            t = [max(1, v - 1) for v in s]
            d = dict.fromkeys(js.DIMS, t)
        out = reply if reply is not None else json.dumps(d)
        return SimpleNamespace(
            output=out,
            tokens_in=100,
            tokens_out=20,
            cost_usd=cost,
            latency_ms=1.0,
            extra={"truncated": 0.0},
            meta={"finish_reason": "stop", "provider": "fake", "response_model": params["model"]},
        )

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
check(
    "the largest block never exceeds outputs_per_call",
    all(max(js.block_sizes(n, 16)) <= 16 for n in range(2, 80)),
)


def summeval_adapter():
    """SummEval's own adapter, loaded only here: the package no longer depends on it, and this
    is where the package's copies are held to it."""
    path = HERE.parents[1] / "examples" / "summeval-judging" / "adapter.py"
    return load_module(path, "summeval_judging_adapter")


ad = summeval_adapter()
item16: dict = {"article": "An article.", "summaries": [f"s{i}" for i in range(16)]}
mine = js.build_message(BASE, item16["article"], item16["summaries"])
check(
    "N=16: the message is byte-identical to SummEval's own _judge_message",
    mine == ad._judge_message(item16, {}),
)
check(
    "N=16: the prompt sha256 equals SummEval's _prompt_sha256",
    hashlib.sha256(js.render_prompt(BASE, 16).encode()).hexdigest() == ad._prompt_sha256({}),
)
real = js.load_scorer(HERE.parent / "data" / "scorers" / "judge-summ-v1.yaml")
check(
    "the committed scorer's sha256_at_16 is SummEval's prompt hash",
    real["prompt"]["sha256_at_16"] == ad._prompt_sha256({}),
)
check(
    "the N=16 rendering the package builds hashes to the committed sha256_at_16",
    hashlib.sha256(judging.render_prompt(js.prompt_text(real), 16).encode()).hexdigest()
    == real["prompt"]["sha256_at_16"],
)
p15 = js.render_prompt(BASE, 15)
check(
    "N=15: both count phrases say 15 and no other word of the prompt changed",
    "15 numbered summaries" in p15 and "a list of 15 integers" in p15 and p15.replace("15", "16") == BASE,
)

for n_, label_ in ((16, "N=16"), (15, "N=15"), (1, "N=1")):
    it_: dict = {"article": "  An article.\n", "summaries": [f" s{i} \n" for i in range(n_)]}
    check(
        f"{label_}: the package's message is byte-identical to the adapter's, for the same rendered prompt",
        judging.build_message(BASE, it_["article"], it_["summaries"])
        == ad._judge_message(it_, {"prompt": judging.render_prompt(BASE, n_)}),
    )
check(
    "the package's render_prompt is judge_score's (one implementation)",
    js.render_prompt is judging.render_prompt and js.build_message is judging.build_message,
)
a_, b_ = [3.0, 1.0, 2.0, 2.0, 5.0], [1.0, 1.0, 4.0, 2.0, 3.0]
check(
    "tau-b and Spearman equal the adapter's on tied data",
    judging.kendall_tau_b(a_, b_) == ad.kendall_tau_b(a_, b_)
    and judging.spearman(a_, b_) == ad.spearman(a_, b_),
)

reply16 = json.dumps({d: list(range(1, 6)) * 3 + [1] for d in js.DIMS})
theirs = ad.parse_scores(reply16)
check(
    "N=16: parse_block agrees with SummEval's parse_scores (mean of the four dimensions)",
    js.parse_block(reply16, 16) == [sum(theirs[d][i] for d in js.DIMS) / 4 for i in range(16)],
)
check(
    "a dimension with the wrong count is a parse failure",
    js.parse_block(json.dumps({d: [3] * 14 for d in js.DIMS}), 15) is None,
)
check(
    "a missing dimension is a parse failure",
    js.parse_block(json.dumps({d: [3] * 15 for d in js.DIMS[:3]}), 15) is None,
)
check(
    "a score outside 1..5 is a parse failure",
    js.parse_block(json.dumps({d: [3] * 14 + [9] for d in js.DIMS}), 15) is None,
)
check(
    "a reply wrapped in prose and fences still parses",
    js.parse_block("Sure:\n```json\n" + json.dumps({d: [4] * 15 for d in js.DIMS}) + "\n```", 15)
    == [4.0] * 15,
)

# ── the judging set: deterministic, hash-stable, pinned ──────────────────────
m1, m2 = manifest_for(), manifest_for()
check("the judging set is deterministic: same inputs, same hash", m1 == m2)
check(
    "its id pins the arm count and a hash prefix",
    m1["judging_set_id"] == f"ds-{N_ARMS}arms-{m1['judging_set_sha256'][:12]}",
)
check(
    "20 arms -> two blocks of 10 per item",
    all([len(b) for b in it["primary"]] == [10, 10] for it in m1["items"]),
)
check(
    "a different seed is a different set",
    manifest_for(scorer(protocol={**scorer()["protocol"], "order_seed": 1}))["judging_set_id"]
    != m1["judging_set_id"],
)
bumped = {a: dict(o) for a, o in OUTPUTS.items()}
bumped[ARMS[3]["config_id"]]["itemB"] += " changed"
check(
    "one changed output is a different set",
    manifest_for(outputs=bumped)["judging_set_id"] != m1["judging_set_id"],
)
check(
    "a different arm set is a different set (not an append)",
    manifest_for(arms=ARMS[:-1])["judging_set_id"] != m1["judging_set_id"],
)
check(
    "every arm sits in exactly one block per item, in every pass",
    all(
        sorted(functools.reduce(operator.iadd, it[k], [])) == sorted(a["config_id"] for a in ARMS)
        for it in m1["items"]
        for k in ("primary", "position")
    ),
)
check(
    "order differs between items",
    len({tuple(functools.reduce(operator.iadd, it["primary"], [])) for it in m1["items"]}) == 3,
)
check(
    "the position pass reshuffles (different blocks) on every item",
    all(it["primary"] != it["position"] for it in m1["items"]),
)
check(
    "control subsets are deterministic and sized by fraction",
    len(m1["position_items"]) == 1 and m1["noise_items"] == manifest_for()["noise_items"],
)

with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sets = Path(td)
    p = js.freeze(m1, sets)
    check("freeze writes the manifest under its id", p.name == f"{m1['judging_set_id']}.json")
    stamp = (p.read_bytes(), p.stat().st_mtime_ns)
    js.freeze(m1, sets)
    check(
        "freezing the same set again leaves the file as it was",
        (p.read_bytes(), p.stat().st_mtime_ns) == stamp,
    )
    bad = dict(m1, judging_set_sha256="deadbeef")
    check(
        "an existing set with a different hash is never rewritten", raises_exit(lambda: js.freeze(bad, sets))
    )

# ── blinding ─────────────────────────────────────────────────────────────────
msgs = [
    js.message_for(m1, BASE, ARTICLES, OUTPUTS, it, p, b)
    for it in m1["items"]
    for p in ("primary", "position")
    for b in range(2)
]
names = [a["config_id"] for a in ARMS] + [a["run"] for a in ARMS] + ["gemma", "qwen"]
check("no arm id, run name or family appears in any prompt", not any(n in m for m in msgs for n in names))
check(
    "summaries are numbered by position only",
    all(re.search(r"^1\. summary", m.split("SUMMARIES:\n")[1], re.M) for m in msgs),
)


# ── running the pass, projection, controls ───────────────────────────────────
def run_all(tmp, sc=None, call=None, cap=None, retry=False, m=None):
    m = m or m1
    return js.run_judging(
        m,
        sc or scorer(),
        BASE,
        ARTICLES,
        OUTPUTS,
        Path(tmp),
        call,
        cap,
        retry_unparsed=retry,
        log=lambda *_: None,
    )


N_TASKS = len(js.tasks(m1))
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    judge = fake_judge()
    st = run_all(td, call=judge)
    check(
        "calls = judges x (primary + position + noise blocks)",
        st["calls"] == 2 * N_TASKS and len(judge.seen) == 2 * N_TASKS,
    )
    sc = scorer()
    scores = js.load_scores(m1, sc, Path(td))
    proj = js.project(sc, scores, ITEMS)
    k_of = {a["config_id"]: k for k, a in enumerate(ARMS)}
    check(
        "projection: judge A's score for an arm is the mean of its four dimensions",
        all(abs(proj[i][c]["ja"] - expected_a(k)) < 1e-9 for i in ITEMS for c, k in k_of.items()),
    )
    check(
        "projection: judge B's score is right, wherever the shuffle put the arm",
        all(abs(proj[i][c]["jb"] - expected_b(k)) < 1e-9 for i in ITEMS for c, k in k_of.items()),
    )
    check(
        "projection: the primary is the mean over judges",
        all(
            abs(proj[i][c]["_mean"] - (expected_a(k) + expected_b(k)) / 2) < 1e-9
            for i in ITEMS
            for c, k in k_of.items()
        ),
    )

    # an item one judge has not finished is not scored by a mean over a different set of judges
    half = js.load_scores(m1, sc, Path(td))
    del half["jb"]["primary"]["itemB"]
    check(
        "an item missing one judge's verdict is dropped from the primary",
        sorted(js.project(sc, half, ITEMS)) == ["itemA", "itemC"],
    )

    first = sorted(Path(td).glob("*/*.json"))
    before = {f: f.read_bytes() for f in first}
    judge2 = fake_judge()
    st2 = run_all(td, call=judge2)
    check("resume: a second run makes no calls", st2["calls"] == 0 and not judge2.seen)
    check("resume: stored verdicts are untouched", all(f.read_bytes() == before[f] for f in first))
    victim = Path(td) / "jb" / "itemA.primary.b1.json"
    victim.unlink()
    judge3 = fake_judge()
    st3 = run_all(td, call=judge3)
    check("resume: one deleted verdict costs exactly one call", st3["calls"] == 1)
    check("--no-calls (call=None) re-reads and calls nothing", run_all(td, call=None)["calls"] == 0)

    # controls
    noise = js.compare_passes(scores["ja"]["primary"], scores["ja"]["noise"])
    check(
        "noise control: a deterministic judge repeats itself (tau 1, diff 0)",
        noise["n_items"] == 1 and noise["mean_tau"] == 1.0 and noise["mean_abs_diff"] == 0.0,
    )
    pos = js.compare_passes(scores["ja"]["primary"], scores["ja"]["position"])
    check(
        "position control: scores that depend only on content do not move with order",
        pos["n_items"] == 1 and pos["mean_abs_diff"] == 0.0,
    )
    pm = js.build_message(
        BASE, ARTICLES["itemA"], [OUTPUTS[a]["itemA"] for a in m1["items"][0]["primary"][0]]
    )
    check(
        "noise pass sends the primary pass's prompt (the same message, repeated)",
        js.message_for(m1, BASE, ARTICLES, OUTPUTS, m1["items"][0], "noise", 0) == pm,
    )
    stored = json.loads((Path(td) / "ja" / "itemA.primary.b0.json").read_text())
    check(
        "a stored verdict keeps the raw reply and the bill",
        stored["output"].startswith("{")
        and stored["cost_usd"] == 0.01
        and stored["prompt_sha256"] == hashlib.sha256(pm.encode()).hexdigest(),
    )

    summ = js.summarise(m1, sc, ARMS, scores, proj, st, "validated judge", True, Path(td))
    a0 = summ["per_arm"]["arm00_v1"]
    check(
        "self-family: an arm of the judge's own family is flagged in that judge's column",
        a0["self_family"] == {"ja": True, "jb": False}
        and summ["per_arm"]["arm01_v1"]["self_family"] == {"ja": False, "jb": True},
    )
    check(
        "summary: per-judge columns and primary are reported",
        a0["judge_ja"] is not None
        and a0["judge_jb"] is not None
        and abs(a0["judge_score"] - (a0["judge_ja"] + a0["judge_jb"]) / 2) < 1e-5,
    )
    check("summary: inter-judge agreement reported", summ["judge_agreement"]["ja~jb"]["n_items"] == 3)
    check(
        "summary: position and noise controls reported per judge",
        summ["controls"]["ja"]["noise"]["n_items"] == 1,
    )
    check(
        "contested: judges differing by more than the threshold on an arm are flagged",
        all((abs(v["judge_ja"] - v["judge_jb"]) > 0.5) == v["contested"] for v in summ["per_arm"].values()),
    )

# ── dry run ──────────────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    est = js.estimate(m1, scorer(), BASE, ARTICLES, OUTPUTS, Path(td))
    check(
        "dry-run: calls per judge = number of (item, pass, block) tasks",
        est["ja"]["calls"] == N_TASKS and est["jb"]["calls"] == N_TASKS,
    )
    check(
        "dry-run: tokens and cost are positive, cost from the price table",
        est["ja"]["tokens_in"] > 0 and est["ja"]["est_cost_usd"] > 0,
    )
    run_all(td, call=fake_judge(), cap=None)
    est2 = js.estimate(m1, scorer(), BASE, ARTICLES, OUTPUTS, Path(td))
    check(
        "dry-run: stored verdicts are not priced again",
        est2["ja"]["calls"] == 0 and est2["ja"]["stored"] == N_TASKS,
    )

# ── cost cap: abort mid-run, keep what was bought ────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    judge = fake_judge(cost=0.01)
    st = run_all(td, call=judge, cap=0.055)
    files = list(Path(td).glob("*/*.json"))
    check("cost cap: the pass aborts mid-run", st["aborted"] and st["calls"] == 6)
    check("cost cap: every paid verdict is kept on disk", len(files) == 6)
    check(
        "cost cap: spend does not run on past the cap by more than one call",
        st["spent_usd"] < 0.055 + 0.01 + 1e-9,
    )
    sc = scorer()
    part = js.project(sc, js.load_scores(m1, sc, Path(td)), ITEMS)
    check("cost cap: only items every judge finished are projected", len(part) < len(ITEMS))
    judge_b = fake_judge(cost=0.01)
    st_b = run_all(td, call=judge_b, cap=None)
    check(
        "cost cap: a rerun with room finishes only what is missing",
        st_b["calls"] == 2 * N_TASKS - 6 and not st_b["aborted"],
    )
    check(
        "cost cap: a stored bill counts against the cap on resume",
        run_all(td, call=fake_judge(), cap=0.01)["calls"] == 0,
    )
    zero = tempfile.mkdtemp(dir=td)
    check("cost cap: a cap of 0 makes no call", run_all(zero, call=fake_judge(), cap=0.0)["calls"] == 0)


# cost_usd None is unknown, not free
def no_cost_judge(tokens=True):
    inner = fake_judge()

    def call(message, params):
        r = inner(message, params)
        r.cost_usd = None
        if not tokens:
            r.tokens_in = r.tokens_out = None
        return r

    return call


with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    st = run_all(td, call=no_cost_judge(), cap=0.0004)
    one_call = (100 * 1.0 + 20 * 2.0) / 1e6
    v_ = json.loads(next(Path(td).glob("ja/*.json")).read_text())
    check(
        "cost None with token counts: counted at the price table, flagged cost_known false",
        abs(v_["cost_usd"] - one_call) < 1e-12 and v_["cost_known"] is False,
    )
    check(
        "cost None with token counts: the cap still stops the run",
        st["aborted"]
        and 0 < st["calls"] < 2 * N_TASKS
        and abs(st["spent_usd"] - st["calls"] * one_call) < 1e-9,
    )
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    st = run_all(td, call=no_cost_judge(tokens=False), cap=1.0)
    check(
        "cost None and no token counts: the verdict is kept, then the run stops",
        st["aborted"] and st["calls"] == 1 and len(list(Path(td).glob("*/*.json"))) == 1,
    )

with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    st = run_all(td, call=fake_judge(reply="I cannot do this."))
    sc = scorer()
    sc_scores = js.load_scores(m1, sc, Path(td))
    check(
        "an unparseable reply is stored with scores null, and the item is not scored",
        json.loads(next(Path(td).glob("ja/*.json")).read_text())["scores"] is None
        and js.project(sc, sc_scores, ITEMS) == {},
    )
    first = json.loads(next(Path(td).glob("ja/*.json")).read_text())
    check(
        "a reply that is not bare JSON is stored as its hash, not its text",
        first["output"] is None
        and first["output_withheld"] is True
        and first["withheld_reason"] == "not bare JSON"
        and first["output_sha256"] == hashlib.sha256(b"I cannot do this.").hexdigest(),
    )
    good = fake_judge()
    st2 = run_all(td, call=good)
    check("resume does not re-pay for unparsed replies unless asked", st2["calls"] == 0)
    st3 = run_all(td, call=good, retry=True)
    check("--retry-unparsed calls them again", st3["calls"] == 2 * N_TASKS)
    again = json.loads(next(Path(td).glob("ja/*.json")).read_text())
    check(
        "a retried block keeps the earlier call's cost: 0.01 + 0.01, attempt 2",
        abs(again["cost_usd"] - 0.02) < 1e-12
        and again["attempts"] == 2
        and abs(again["cost_usd_earlier_attempts"] - 0.01) < 1e-12
        and again["scores"] is not None,
    )
    check(
        "...and the stored bill counts both calls", abs(js.stored_cost(Path(td)) - 0.02 * 2 * N_TASKS) < 1e-9
    )

with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    quote = " ".join(ARTICLES["itemA"].split()[:8])
    run_all(td, call=fake_judge(reply=json.dumps({"note": quote})))
    recs = [json.loads(f.read_text()) for f in Path(td).glob("*/itemA.*.json")]
    check(
        "a bare-JSON reply that repeats 8 words of the article is stored as its hash",
        recs and all(r["output"] is None and r["withheld_reason"] == "repeats the source" for r in recs),
    )
    import validate_tree as _vt

    check(
        "V12's reply rule accepts a withheld record and bare JSON",
        all(_vt.reply_problems(r) == [] for r in recs)
        and _vt.reply_problems({"output": '```json\n{"coherence": [1]}\n```'}) == [],
    )
    check(
        "V12's reply rule refuses prose, a reply cut off, and text gone with no hash",
        _vt.reply_problems({"output": 'Let me think. {"a": 1}'}) != []
        and _vt.reply_problems({"output": '{"coherence": [5, 2'}) != []
        and _vt.reply_problems({"output": None}) != [],
    )

check(
    'parse_block refuses true and "4" as scores',
    js.parse_block(json.dumps({d: [True] for d in js.DIMS}), 1) is None
    and js.parse_block(json.dumps({d: ["4"] for d in js.DIMS}), 1) is None
    and js.parse_block(json.dumps({d: [4] for d in js.DIMS}), 1) == [4.0],
)
check(
    "a scorer with no validation.experiment gets a label, not a KeyError",
    js.validated_label({"validation": {}}).startswith("validated by"),
)

with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    run_all(td, call=fake_judge())
    other = scorer(
        judges=[
            dict(
                scorer()["judges"][0],
                params={"model": "m_a", "family": "gemma", "usd_per_mtok_in": 9.0, "usd_per_mtok_out": 2.0},
            ),
            scorer()["judges"][1],
        ]
    )
    check(
        "verdicts stored by a changed judge definition are refused, not mixed",
        raises_exit(lambda: run_all(td, sc=other, call=fake_judge())),
    )

# ── the validation gate ──────────────────────────────────────────────────────
real_runs = HERE.parent / "data" / "runs"
check(
    "the committed scorer passes the gate against the committed SummEval runs",
    js.validation_problems(real, real_runs) == [],
)
no_val = {k: v for k, v in real.items() if k != "validation"}
check("no validation block: refused", js.validation_problems(no_val, real_runs) != [])
ghost = dict(
    real,
    validation=dict(
        real["validation"], runs=[dict(r, run="se_nonexistent_run") for r in real["validation"]["runs"]]
    ),
)
check(
    "a validation that names no committed run: refused",
    any("is not in" in p for p in js.validation_problems(ghost, real_runs)),
)
wrong = dict(
    real, validation=dict(real["validation"], runs=[dict(r, value=0.9) for r in real["validation"]["runs"]])
)
check(
    "a claimed value that the committed run does not have: refused",
    any("claims" in p for p in js.validation_problems(wrong, real_runs)),
)
swap = dict(
    real,
    validation=dict(
        real["validation"],
        runs=[
            dict(r, judge=("qwen_s" if r["judge"] == "gemma_l" else "gemma_l"))
            for r in real["validation"]["runs"]
        ],
    ),
)
check(
    "a run that measured a different model than the judge: refused",
    any("measured model" in p for p in js.validation_problems(swap, real_runs)),
)
partial = dict(real, validation=dict(real["validation"], runs=real["validation"]["runs"][:1]))
check(
    "a judge no validation run names: refused",
    any("no validation run names it" in p for p in js.validation_problems(partial, real_runs)),
)
check(
    "a prompt that is not the validated one: refused",
    any(
        "sha256_at_16" in p
        for p in js.validation_problems(
            dict(real, prompt=dict(real["prompt"], sha256_at_16="0" * 64)), real_runs
        )
    ),
)
for k_, v_, what_ in (
    ("temperature", 0.7, "temperature"),
    ("max_tokens", 100, "max_tokens"),
    ("reasoning", {"enabled": True}, "reasoning"),
    ("provider", "other", "provider"),
    ("model", "eval-other", "model"),
):
    changed = dict(
        real,
        judges=[dict(real["judges"][0], params={**real["judges"][0]["params"], k_: v_}), real["judges"][1]],
    )
    check(
        f"gate: a scorer whose judge differs from the validated run in {what_}: refused",
        any(f"{k_}=" in p for p in js.validation_problems(changed, real_runs)),
    )
no_sha = dict(real, prompt={k: v for k, v in real["prompt"].items() if k != "sha256_at_16"})
check(
    "gate: a validation block without prompt.sha256_at_16: refused",
    any("required" in p for p in js.validation_problems(no_sha, real_runs)),
)
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    (Path(td) / "examples" / "summeval-judging").mkdir(parents=True)
    shutil.copy(
        HERE.parent.parent / "examples" / "summeval-judging" / "prompt.txt",
        Path(td) / "examples" / "summeval-judging" / "other.txt",
    )
    check(
        "gate: a different prompt file name: refused",
        any(
            "prompt file" in p
            for p in js.validation_problems(
                dict(real, prompt=dict(real["prompt"], file="examples/summeval-judging/other.txt")),
                real_runs,
                Path(td),
            )
        ),
    )
floor = dict(
    real,
    validation=dict(real["validation"], runs=[dict(r, min_metric=0.6) for r in real["validation"]["runs"]]),
)
check(
    "gate: a judge whose validation metric is below min_metric: refused",
    sum("below the scorer's min_metric" in p for p in js.validation_problems(floor, real_runs)) == 2,
)
check(
    "the committed scorer sets min_metric on every judge",
    all(r.get("min_metric") is not None for r in real["validation"]["runs"]),
)
check(
    "the label names the validation experiment and says it is provenance",
    js.validated_label(real) == "validated on summeval_100 (provenance)",
)
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    # a run recording a different prompt sha is refused (copy the committed run, edit one field)
    rd = Path(td) / "runs"
    for r_ in real["validation"]["runs"]:
        shutil.copytree(real_runs / r_["run"], rd / r_["run"])
    mf = rd / real["validation"]["runs"][0]["run"] / "metrics.json"
    mj_ = json.loads(mf.read_text())
    mj_["fingerprint"]["system_under_test"]["model"]["prompt_sha256"] = "0" * 64
    mf.write_text(json.dumps(mj_))
    check(
        "gate: a validation run that used a different prompt: refused",
        any("used prompt" in p for p in js.validation_problems(real, rd)),
    )
    del mj_["fingerprint"]["system_under_test"]["model"]["prompt_sha256"]
    mf.write_text(json.dumps(mj_))
    check(
        "gate: a validation run that recorded no prompt sha: refused",
        any("records no prompt sha256" in p for p in js.validation_problems(real, rd)),
    )

one_family = dict(real, judges=[real["judges"][0], real["judges"][0]])
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    pth = Path(td) / "x.yaml"
    import yaml

    pth.write_text(yaml.safe_dump({k: v for k, v in one_family.items() if not k.startswith("_")}))
    check("a scorer whose judges share a vendor family is refused", raises_exit(lambda: js.load_scorer(pth)))
    # the CLI: refuses an unvalidated scorer before reading data or calling anything
    pth2 = Path(td) / "judge-test-unval.yaml"
    pth2.write_text(
        yaml.safe_dump(
            {k: v for k, v in no_val.items() if not k.startswith("_")} | {"scorer_id": "judge-test-unval"}
        )
    )
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
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    runs = td / "runs"
    arms = []
    for a in ARMS:
        d = runs / a["run"]
        (d / "outputs").mkdir(parents=True)
        rows = []
        for i in ITEMS:
            (d / "outputs" / f"{i}.txt").write_text(OUTPUTS[a["config_id"]][i])
            rows.append(
                {
                    "item_id": i,
                    "coverage": 0.3,
                    "cost_usd": 0.001,
                    "latency_ms": 5.0,
                    "tokens_in": 10.0,
                    "_meta": {"usage": {"cost": 0.001}},
                }
            )
        (d / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (d / "metrics.json").write_text(
            json.dumps(
                {
                    "config_id": a["config_id"],
                    "run_id": a["run"],
                    "dataset_id": "ds",
                    "created_at": "2026",
                    "primary_metric": "coverage",
                    "scores": {"coverage": 0.3},
                    "metric_kinds": {"coverage": "quality", "cost_usd": "cost"},
                    "params": {"family": a["family"]},
                    "fingerprint": {
                        "hash": "abc",
                        "instrument": {"adapter": {"id": "old"}},
                        "arm": {"config_id": a["config_id"]},
                    },
                }
            )
        )
        arms.append(dict(a, dir=d))
    found = js.discover_arms("ds", "_v1", runs)
    check(
        "discover_arms finds one primary run per arm",
        [a["config_id"] for a in found] == sorted(a["config_id"] for a in ARMS),
    )
    before = {p: p.read_bytes() for p in runs.rglob("*") if p.is_file()}
    sc = scorer()
    vdir = td / "v"
    run_all(vdir, call=fake_judge())
    proj = js.project(sc, js.load_scores(m1, sc, vdir), ITEMS)
    out = td / "judged" / sc["scorer_id"]
    js.write_scored_runs(m1, sc, arms, proj, out, "validated judge", True)
    r0 = out / arms[0]["run"]
    check(
        "scored runs land in a separate dir, one per original run, same name",
        sorted(p.name for p in out.iterdir()) == sorted(a["run"] for a in ARMS),
    )
    check("the originals are untouched (byte for byte)", all(p.read_bytes() == b for p, b in before.items()))
    pr = [json.loads(x) for x in (r0 / "predictions.jsonl").read_text().splitlines()]
    mj = json.loads((r0 / "metrics.json").read_text())
    check(
        "predictions carry the primary, per-judge columns and the CARRY fields",
        len(pr) == 3
        and {"judge_score", "judge_ja", "judge_jb", "cost_usd", "latency_ms"} <= set(pr[0])
        and pr[0]["cost_usd"] == 0.001
        and "coverage" not in pr[0],
    )
    check(
        "metrics.json: primary_metric, scores, provenance, fingerprint hash invalidated",
        mj["primary_metric"] == "judge_score"
        and abs(mj["scores"]["judge_score"] - (expected_a(0) + expected_b(0)) / 2) < 1e-9
        and mj["judged_from"] == arms[0]["run"]
        and mj["judged_with"]["judging_set_id"] == m1["judging_set_id"]
        and mj["fingerprint"]["hash"] is None
        and "coverage" not in mj["scores"],
    )
    check("metrics.json: kinds mark judge columns quality", mj["metric_kinds"]["judge_score"] == "quality")
    js.write_scored_runs(m1, sc, arms, proj, td / "unval", "unvalidated judge", False)
    mu = json.loads((td / "unval" / arms[0]["run"] / "metrics.json").read_text())
    check(
        "--unvalidated: the primary metric and the label say so",
        mu["primary_metric"] == "judge_score_unvalidated"
        and mu["judge_label"] == "unvalidated judge"
        and mu["judged_with"]["validated"] is False,
    )
    # Python of the running interpreter: the same one that ran these assertions.
    env = dict(os.environ, EVAL_RUNS_DIR=str(out))
    lb_run = subprocess.run(
        [sys.executable, str(HERE / "leaderboard.py"), "--dataset-id", "ds"],
        cwd=HERE.parent,
        env=env,
        capture_output=True,
        text=True,
    )
    check(
        "leaderboard reads the scored runs with EVAL_RUNS_DIR (exit 0, shows judge_score)",
        lb_run.returncode == 0 and "judge_score" in lb_run.stdout,
    )
    if lb_run.returncode != 0:
        print((lb_run.stdout + lb_run.stderr)[-600:])


# ── one summary per call (the pointwise experiment) ──────────────────────────
p1 = js.render_prompt(BASE, 1)
check(
    "N=1: singular grammar in both count phrases",
    "1 numbered summary" in p1
    and "a list of 1 integer" in p1
    and "numbered summaries" not in p1
    and "integers" not in p1,
)
check(
    "N=1: the example shows one value per key",
    '{"coherence": [3], "consistency": [5], "fluency": [4], "relevance": [2]}' in p1 and "..." not in p1,
)
check("N=16 is still byte-identical after the N=1 branch", js.render_prompt(BASE, 16) == BASE)
check(
    "N=1: parse_block takes exactly one value per dimension",
    js.parse_block(json.dumps({"coherence": [4], "consistency": [3], "fluency": [5], "relevance": [4]}), 1)
    == [4.0]
    and js.parse_block(json.dumps({d: [3, 3] for d in js.DIMS}), 1) is None,
)
check("N=1: block_sizes gives one block per arm", js.block_sizes(2, 1) == [1, 1])
one = scorer(protocol={**scorer()["protocol"], "outputs_per_call": 1})
m_one = manifest_for(one, arms=ARMS[:2])
check(
    "N=1: every arm is its own block, and the prompt sent says 1 summary",
    all([len(b) for b in it["primary"]] == [1, 1] for it in m_one["items"])
    and "1 numbered summary"
    in js.message_for(m_one, BASE, ARTICLES, OUTPUTS, m_one["items"][0], "primary", 0),
)
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    st = js.run_judging(
        m_one, one, BASE, ARTICLES, OUTPUTS, Path(td), fake_judge(), None, log=lambda *_: None
    )
    pr1 = js.project(one, js.load_scores(m_one, one, Path(td)), ITEMS)
    check(
        "N=1: a fake judge's pointwise verdicts parse and project for both arms",
        st["calls"] == 2 * len(js.tasks(m_one))
        and sorted(pr1["itemA"]) == sorted(a["config_id"] for a in ARMS[:2])
        and abs(pr1["itemA"]["arm00_v1"]["ja"] - expected_a(0)) < 1e-9,
    )

# ── --arms: a subset is its own judging set ──────────────────────────────────
sub = js.select_arms(ARMS, "arm03_v1,arm07")
check(
    "--arms: an exact id and a substring both select",
    [a["config_id"] for a in sub] == ["arm03_v1", "arm07_v1"],
)
check(
    "--arms: an exact id wins over substrings that also match",
    [a["config_id"] for a in js.select_arms([*ARMS, dict(ARMS[0], config_id="arm00_v1_x")], "arm00_v1")]
    == ["arm00_v1"],
)
check(
    "--arms: a token that matches nothing is refused, not ignored",
    raises_exit(lambda: js.select_arms(ARMS, "arm03_v1,nope")),
)
m_sub = manifest_for(arms=sub)
check(
    "--arms: the subset has its own id (arm count and hash differ from the full set)",
    m_sub["judging_set_id"].startswith("ds-2arms-") and m_sub["judging_set_id"] != m1["judging_set_id"],
)

# ── latency, and verdicts stored before it was measured ──────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)

    def slow(message, params):
        import time as _t  # noqa: PLC0415

        _t.sleep(0.03)
        return fake_judge()(message, params)

    js.run_judging(m_one, one, BASE, ARTICLES, OUTPUTS, Path(td), slow, None, log=lambda *_: None)
    lat = [json.loads(f.read_text())["latency_ms"] for f in Path(td).glob("*/*.json")]
    check(
        "latency: every verdict stores the wall-clock of its call, not the judge's own field",
        lat and all(isinstance(x, float) and 25 <= x < 2000 for x in lat),
    )
    f0 = next(Path(td).glob("ja/*.json"))
    v0 = json.loads(f0.read_text())
    v0["latency_ms"] = None
    f0.write_text(json.dumps(v0))
    check(
        "latency: an old verdict with latency_ms null is still read, skipped and projected",
        js.run_judging(
            m_one, one, BASE, ARTICLES, OUTPUTS, Path(td), fake_judge(), None, log=lambda *_: None
        )["calls"]
        == 0
        and js.project(one, js.load_scores(m_one, one, Path(td)), ITEMS) != {}
        and js.summarise(
            m_one,
            one,
            ARMS[:2],
            js.load_scores(m_one, one, Path(td)),
            js.project(one, js.load_scores(m_one, one, Path(td)), ITEMS),
            {},
            "unvalidated judge",
            False,
            Path(td),
        )["per_judge"]["ja"]["verdicts"]
        > 0,
    )

# ── the committed pointwise scorer is unvalidated, and says so ───────────────
pw = js.load_scorer(HERE.parent / "data" / "scorers" / "judge-summ-pointwise-v1.yaml")
check(
    "pointwise scorer: same judges and prompt as judge-summ-v1, one summary per call",
    pw["judges"] == real["judges"]
    and pw["prompt"] == real["prompt"]
    and pw["protocol"]["outputs_per_call"] == 1
    and not pw["protocol"]["position_check_fraction"],
)
check(
    "pointwise scorer: no validation block, so the gate refuses it",
    "validation" not in pw and js.validation_problems(pw, real_runs) != [],
)
argv0 = sys.argv
sys.argv = ["judge_score.py", "--dataset-id", pw["dataset_id"], "--scorer", pw["scorer_id"]]
try:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = js.main()
finally:
    sys.argv = argv0
check(
    "pointwise scorer: without --unvalidated the CLI exits 3 and says REFUSED",
    rc == 3 and "REFUSED" in buf.getvalue(),
)

# ── validate_judge_goyal: the human comparison, from stored records, no calls ──
import validate_judge_goyal as vg  # noqa: E402


def ann(best, worst):
    return {"best_summary": best, "worst_summary": worst}


check(
    "credit: a tie for top earns 1/k, a miss 0, an unambiguous hit 1",
    vg.credit(["a", "b", "c"], ["a"]) == 1 / 3
    and vg.credit(["a"], ["b"]) == 0
    and vg.credit(["a"], ["a"]) == 1
    and vg.credit(["a", "b"], ["a"]) == 0.5,
)
check(
    "credit: a split reference is drawn uniformly (picks a, refs a|b -> 1/2)",
    vg.credit(["a"], ["a", "b"]) == 0.5,
)
w = vg.wilson(50, 100)
check("wilson: 50/100 is the textbook [0.404, 0.596]", w == [0.4038, 0.5961] or w == [0.4038, 0.5962])
check("wilson: 0/0 has no interval", vg.wilson(0, 0) is None)
trio = [ann(["gpt3"], ["t0"]), ann(["gpt3"], ["brio"]), ann(["brio"], ["t0"])]
check("majority best: two of three name the same system", vg.majority_best(trio) == "gpt3")
check(
    "majority best: no two agree -> none",
    vg.majority_best([ann(["gpt3"], []), ann(["brio"], []), ann(["t0"], [])]) is None,
)
check(
    "pairwise human preference: the majority of three implied orderings",
    vg.human_pair_pref(trio) == "gpt3"
    and vg.human_pair_pref([ann(["gpt3"], ["t0"]), ann(["brio"], ["t0"])]) is None,
)
ref = vg.loo_refs(trio)
check(
    "leave-one-out: the reference is the other two's top-voted best(s)",
    ref[0][1] == ["brio", "gpt3"] and ref[1][1] == ["brio", "gpt3"] and ref[2][1] == ["gpt3"],
)

G = {"a1": {"annotators": trio}, "a2": {"annotators": [ann(["brio"], ["gpt3"])] * 3}}
R = {
    "a1": {"order": ["gpt3", "brio", "t0"], "scores": [4.0, 4.0, 3.0]},
    "a2": {"order": ["t0", "gpt3", "brio"], "scores": [2.0, 3.0, 5.0]},
}
st = vg.judge_stats(G, R)
check(
    "judge stats: a tie for top between gpt3 and brio earns 1/2 against human best gpt3, "
    "an exact hit earns 1",
    st["best_pick_partial_credit"]["k"] == 1.5
    and st["best_pick_partial_credit"]["n"] == 2
    and st["best_pick_agreement"] == "1/2",
)
check(
    "judge stats: a judge tie on gpt3 vs brio is skipped, a decided one is compared per article",
    st["pairwise_gpt3_vs_brio_per_article"]["articles_both_decided"] == 1
    and st["pairwise_gpt3_vs_brio_per_article"]["agreement"]["k"] == 1
    and st["pairwise_gpt3_vs_brio_per_article"]["judge_tied"] == 1,
)

record = {"judge_fp": "f", "prompt_sha": "p", "order": ["x"]}
check("record check: a matching record is accepted", vg.record_problem(record, ["x"], "p", "f") is None)
check(
    "record check: another judge definition, another prompt, another order, or no stamp: refused",
    all(
        vg.record_problem(r_, ["x"], "p", "f")
        for r_ in (
            dict(record, judge_fp="g"),
            dict(record, prompt_sha="q"),
            dict(record, order=["y"]),
            {"order": ["x"]},
        )
    ),
)
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    (td / "scorers").mkdir()
    shutil.copy(
        HERE.parent / "data" / "scorers" / "judge-summ-v1.yaml", td / "scorers" / "judge-summ-v1.yaml"
    )
    synth = {
        "a1": {
            "article": "An article.",
            "gpt3": {"text": "g"},
            "brio": {"text": "b"},
            "t0": {"text": "t"},
            "annotators": trio,
        }
    }
    saved = (vg.DATA, vg.load, sys.argv)
    vg.DATA, vg.load = td, lambda: synth
    sys.argv = ["validate_judge_goyal.py", "--scorer", "judge-summ-v1", "--no-calls"]
    try:
        try:
            vg.main()
            msg_ = ""
        except SystemExit as exc:
            msg_ = str(exc)
        check(
            "--no-calls with a record missing: errors and lists it",
            "missing" in msg_ and "gemma_l" in msg_ and "qwen_s" in msg_,
        )
        sc_ = js.load_scorer(td / "scorers" / "judge-summ-v1.yaml")
        so_, sha_ = vg.expected(js.prompt_text(sc_), "a1", synth["a1"])
        for j_ in sc_["judges"]:
            f_ = vg.record_path(td / "judge-validation" / "judge-summ-v1" / "goyal2022-cnn" / j_["id"], "a1")
            f_.parent.mkdir(parents=True, exist_ok=True)
            f_.write_text(
                json.dumps(
                    {
                        "article_id": "a1",
                        "order": so_,
                        "scores": [3.0, 4.0, 2.0],
                        "cost_usd": 0.0,
                        "judge_fp": js.judge_fingerprint(j_),
                        "prompt_sha": sha_,
                    }
                )
            )
        check(
            "--no-calls with every record stored: writes the report, calls nothing",
            vg.main() == 0
            and (td / "judge-validation" / "judge-summ-v1" / "goyal2022-cnn" / "report.json").is_file(),
        )
        f_.write_text(json.dumps({**json.loads(f_.read_text()), "judge_fp": "0" * 16}))
        try:
            vg.main()
            msg_ = ""
        except SystemExit as exc:
            msg_ = str(exc)
        check(
            "a stored record from a different judge definition is refused, not reused",
            "refused" in msg_ and "qwen_s" in msg_,
        )
    finally:
        vg.DATA, vg.load, sys.argv = saved

# ── validate_judge_zhang: statistics, loading, the record checks, withholding ──
import validate_judge_zhang as vz  # noqa: E402

pt = vz.paired_test({"x": 1.0, "y": 1.0, "z": 1.0}, {"x": 0.0, "y": 0.0, "z": 0.0, "w": 9.0})
check(
    "paired test: only shared articles count; three +1 differences give p near 2/8",
    pt["articles"] == 3
    and pt["mean_difference"] == 1.0
    and pt["a_ahead"] == 3
    and pt["b_ahead"] == 0
    and 0.22 < pt["p_two_sided"] < 0.28,
)
pt = vz.paired_test({str(i): 1.0 for i in range(20)}, {str(i): 0.0 for i in range(20)})
check("paired test: twenty +1 differences are significant (p < 0.001)", pt["p_two_sided"] < 0.001)
pt = vz.paired_test({"x": 1.0, "y": -1.0}, {"x": 0.0, "y": 0.0})
check(
    "paired test: differences that cancel are not (p = 1)",
    pt["p_two_sided"] == 1.0 and pt["a_ahead"] == 1 and pt["b_ahead"] == 1,
)

SYS3 = ["s1", "s2", "s3"]


def _refs(vals):
    """The three two-rater references of an article, all alike: [{system: {human dim: v}}]."""
    return [{m: {h: v for h, _ in vz.PAIRS} for m, v in zip(SYS3, vals)} for _ in range(3)]


def _jscores(vals):
    return {m: {jd: v for _, jd in vz.PAIRS} for m, v in zip(SYS3, vals)}


refs_ = {"a1": _refs([3.0, 2.0, 1.0]), "a2": _refs([1.0, 2.0, 3.0])}
same_ = {"a1": _jscores([5.0, 4.0, 1.0]), "a2": _jscores([1.0, 4.0, 5.0])}
jt_ = vz.judge_tau(same_, refs_, SYS3)
check(
    "judge tau: a judge ordering every article as the raters do is 1 on every dimension",
    jt_["mean"] == 1.0 and all(jt_[h] == 1.0 for h, _ in vz.PAIRS),
)
check(
    "judge tau: the reverse order is -1",
    vz.judge_tau({"a1": same_["a2"], "a2": same_["a1"]}, refs_, SYS3)["mean"] == -1.0,
)
mdata_ = {
    aid: {"systems": {"reference": {"summary": "r"}, **{m: {"summary": m} for m in SYS3}}}
    for aid in ("a1", "a2")
}
order_ = {"a1": {"s1": 3, "s2": 2, "s3": 1}, "a2": {"s1": 1, "s2": 2, "s3": 3}}
check(
    "metric tau: a constant metric orders nothing: 0, the convention of judging.kendall_tau_b",
    vz.metric_tau(mdata_, refs_, SYS3, lambda s, r: 1.0)["mean"] == 0.0,
)
check(
    "metric tau: a metric ordering the article as the raters do is 1",
    vz.metric_tau({"a1": mdata_["a1"]}, refs_, SYS3, lambda s, r: order_["a1"][s])["mean"] == 1.0,
)
check(
    "article taus: one value per article, averaged over references and dimensions",
    vz.article_taus(lambda aid, k, h: [order_[aid][m] for m in SYS3], refs_, SYS3, ["a1", "a2"])
    == {"a1": 1.0, "a2": 1.0},
)


def _rated(vals):
    return {m: {"ratings": [{h: v for h, _ in vz.PAIRS}] * 3} for m, v in zip(SYS3, vals)}


# Over both articles the raters put s2 first; on a1 alone, s1. A judge that scored a1 only
# and put s1 first agrees with the raters on the articles it scored.
smd = {"a1": {"systems": _rated([5.0, 4.0, 1.0])}, "a2": {"systems": _rated([1.0, 5.0, 1.0])}}
sm_ = vz.system_means(smd, SYS3, {"j": {"a1": _jscores([5.0, 4.0, 1.0])}})
check(
    "system means: the raters' ranking over every article puts s2 first", sm_["ranking"]["raters"]["s2"] == 1
)
check(
    "system means: a judge is compared with the raters on the articles it scored (Spearman 1)",
    sm_["ranking"]["spearman_vs_raters"]["j"] == 1.0 and sm_["ranking"]["judges"]["j"]["s1"] == 1,
)

with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    rows = [
        {
            "dataset": "cnndm",
            "article": "An article.",
            "model": "m",
            "summary": float("nan"),
            "coherence": 1,
            "relevance": 1,
            "faithfulness": 0,
        },
        {
            "dataset": "xsum",
            "article": "Other.",
            "model": "m",
            "summary": "s",
            "coherence": 5,
            "relevance": 5,
            "faithfulness": 1,
        },
    ]
    blob = json.dumps(rows).encode()
    saved_pins = (vz.FILE, vz.EXT, vz.PINNED)
    vz.EXT, vz.FILE, vz.PINNED = td, td / "f.json", hashlib.sha256(blob).hexdigest()
    try:
        (td / "f.json").write_bytes(blob)
        got = vz.load()
        one = next(iter(got.values()))
        check(
            "load: CNN/DailyMail rows only; a NaN summary is an empty one",
            len(got) == 1
            and one["systems"]["m"]["summary"] == ""
            and one["systems"]["m"]["ratings"] == [{"coherence": 1.0, "relevance": 1.0, "faithfulness": 0.0}],
        )
        vz.PINNED = "0" * 64
        check("load: a file that is not the pinned one is refused", "not the pinned" in _exit(vz.load))
    finally:
        vz.FILE, vz.EXT, vz.PINNED = saved_pins

# The whole script on a synthetic world with a fake call: a reply that quotes the article
# is not stored, the report is built, and the record checks refuse what they should.
ART = {
    "a1": "The café on the corner served coffee to every single visitor all morning long today.",
    "a2": "A storm closed the harbour for two days and the ferries stayed in port until Friday.",
    "a3": "The council voted to plant four hundred trees along the river before the spring.",
}
QUOTE = "the café on the corner served coffee to every"
SYSZ = ["reference", "s1", "s2", "s3"]
rng_ = __import__("random").Random(3)
synth_z = {
    aid: {
        "article": art,
        "systems": {
            m: {
                "summary": f"{m} wrote a summary of {aid} number {k}",
                "ratings": [
                    {
                        "coherence": float(rng_.randint(1, 5)),
                        "relevance": float(rng_.randint(1, 5)),
                        "faithfulness": float(rng_.randint(0, 1)),
                    }
                    for _ in range(3)
                ],
            }
            for k, m in enumerate(SYSZ)
        },
    }
    for aid, art in ART.items()
}


def zhang_reply(fn, args, label):
    msg, _params = args
    n = len(re.findall(r"^\d+\. ", msg.split("SUMMARIES:\n", 1)[1], re.M))
    body = json.dumps({d: [float(1 + (i % 5)) for i in range(n)] for d in js.DIMS})
    text = (f"As the article says, {QUOTE}. " + body) if "café" in msg else body
    return SimpleNamespace(output=text, tokens_in=10, tokens_out=10, cost_usd=0.0001)


with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    (td / "scorers").mkdir()
    shutil.copy(
        HERE.parent / "data" / "scorers" / "judge-summ-v1.yaml", td / "scorers" / "judge-summ-v1.yaml"
    )
    saved_vz = (vz.DATA, vz.load, vz.call_with_retries, sys.argv)
    vz.DATA, vz.load, vz.call_with_retries = td, lambda: synth_z, zhang_reply  # type: ignore[assignment]  # stubbed on purpose
    sys.argv = ["validate_judge_zhang.py", "--scorer", "judge-summ-v1"]
    try:
        rc = vz.main()
        vroot = td / "judge-validation" / "judge-summ-v1" / "zhang2023-cnndm"
        rep = json.loads((vroot / "report.json").read_text())
        f_a1 = vz.record_path(vroot / "gemma_l", "a1", 0)
        rec_a1 = json.loads(f_a1.read_text())
        rec_a2 = json.loads(vz.record_path(vroot / "gemma_l", "a2", 0).read_text())
        check(
            "main: a reply that quotes 8 words of the article is withheld (no text, its hash kept)",
            rc == 0
            and rec_a1["output"] is None
            and rec_a1["output_withheld"] is True
            and len(rec_a1["output_sha256"]) == 64
            and rec_a1["dims"] is not None,
        )
        check(
            "main: a reply that quotes nothing is stored as it came",
            rec_a2["output_withheld"] is False and rec_a2["output"].startswith("{"),
        )
        check(
            "main: the report counts the withheld replies and scores every article",
            rep["judges"]["gemma_l"]["withheld_replies"] == 1
            and rep["judges"]["gemma_l"]["articles_scored"] == 3
            and rep["articles"] == 3,
        )
        sc_z = js.load_scorer(td / "scorers" / "judge-summ-v1.yaml")
        args_z = (sc_z, js.prompt_text(sc_z), int(sc_z["protocol"]["outputs_per_call"]), synth_z, SYSZ, vroot)
        orig_a1 = f_a1.read_text()
        f_a1.write_text(json.dumps({**rec_a1, "judge_fp": "0" * 16}))
        check(
            "build_report: a record stored for another judge definition is refused",
            "different judge" in _exit(lambda: vz.build_report(*args_z)),
        )
        # json.dumps writes "café" as "café", so the raw file hides the quote; the
        # decoded reply does not.
        f_a1.write_text(json.dumps({**rec_a1, "output": f"{QUOTE} {{}}"}))
        check(
            "build_report: a stored reply quoting the article is refused even when JSON-escaped",
            "\\u00e9" in f_a1.read_text() and "repeats 8 words" in _exit(lambda: vz.build_report(*args_z)),
        )
        f_a1.write_text(orig_a1)
        check("build_report: the restored records build again", vz.build_report(*args_z)["articles"] == 3)
    finally:
        vz.DATA, vz.load, vz.call_with_retries, sys.argv = saved_vz

# ── validate_tree V11-V13 each fail on a deliberately broken copy ────────────
import shutil  # noqa: E402

import validate_tree as vt  # noqa: E402

DATA = HERE.parent / "data"
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    for sub_ in ("judging-sets", "judge-verdicts", "scorers"):
        shutil.copytree(DATA / sub_, td / sub_)
    sets_d, ver_d, sc_d = td / "judging-sets", td / "judge-verdicts", td / "scorers"
    check(
        "V11-V13 helpers: the committed data is clean",
        vt.judging_set_problems(sets_d) == []
        and vt.verdict_problems(ver_d, sets_d) == []
        and vt.scorer_problems(sc_d) == [],
    )

    sf = next(sets_d.glob("*.json"))
    orig = sf.read_text()
    man = json.loads(orig)
    # A real edit on any set: reversing a one-summary block (pointwise sets) would change nothing.
    man["items"][0]["article_sha256"] = "0" * 64
    sf.write_text(json.dumps(man))
    check(
        "V11: a judging set edited after its hash was stored fails",
        any("recomputed" in p for p in vt.judging_set_problems(sets_d)),
    )
    man = json.loads(orig)
    man["judging_set_sha256"] = "0" * 64
    sf.write_text(json.dumps(man))
    check("V11: a wrong stored hash fails", any("recomputed" in p for p in vt.judging_set_problems(sets_d)))
    sf.write_text(orig)

    vf = next(ver_d.glob("*/*/*/*.json"))
    vorig = vf.read_text()
    cases = {
        "an unknown item": ("item_id", "no-such-item"),
        "a block index that does not exist": ("block", 99),
        "an unknown pass": ("pass", "sideways"),
        "an n that is not the block's size": ("n", 999),
    }
    for what, (k, val) in cases.items():
        v = json.loads(vorig)
        v[k] = val
        vf.write_text(json.dumps(v))
        check(f"V12: a verdict with {what} fails", vt.verdict_problems(ver_d, sets_d) != [])
    vf.write_text(vorig)
    set_dir = vf.parent.parent
    set_dir.rename(set_dir.with_name("ds-9arms-ffffffffffff"))
    check(
        "V12: a verdict directory naming a judging set that does not exist fails",
        any("does not exist" in p for p in vt.verdict_problems(ver_d, sets_d)),
    )
    set_dir.with_name("ds-9arms-ffffffffffff").rename(set_dir)
    check("V12: restored copy is clean again", vt.verdict_problems(ver_d, sets_d) == [])

    pf = sc_d / "judge-summ-pointwise-v1.yaml"
    sorig = pf.read_text()
    broken = {
        "a missing judges key": sorig.replace("judges:", "judgez:", 1),
        "a scorer_id that is not its file name": sorig.replace(
            "scorer_id: judge-summ-pointwise-v1", "scorer_id: other", 1
        ),
        "a non-integer outputs_per_call": sorig.replace("outputs_per_call: 1", "outputs_per_call: lots", 1),
        "a judge with no model": sorig.replace("model: eval-gemma-31b", "", 1),
        "a prompt file that does not exist": sorig.replace(
            "examples/summeval-judging/prompt.txt", "nope/prompt.txt", 1
        ),
        "invalid yaml": "scorer_id: [unclosed\n",
    }
    for what, text in broken.items():
        pf.write_text(text)
        try:
            bad_sc = vt.scorer_problems(sc_d)
        except Exception as exc:  # noqa: BLE001 — a crash in the check is not a failing check
            bad_sc = []
            print("   check crashed:", type(exc).__name__, exc)
        check(f"V13: a scorer with {what} fails", bad_sc != [])
    pf.write_text(sorig)

# ── no dependency outside the package: routing, the fake judge, prompt resolution ──
check(
    "judge_score no longer loads the SummEval adapter",
    not hasattr(js, "summeval_adapter") and "adapter.py" not in (HERE / "judge_score.py").read_text(),
)
fake_sc = scorer(
    judges=[
        {
            "id": "fa",
            "params": {
                "provider": "fake",
                "model": "m_a",
                "family": "gemma",
                "usd_per_mtok_in": 1.0,
                "usd_per_mtok_out": 2.0,
            },
        },
        {
            "id": "fb",
            "params": {
                "provider": "fake",
                "model": "m_b",
                "family": "qwen",
                "usd_per_mtok_in": 1.0,
                "usd_per_mtok_out": 2.0,
            },
        },
    ]
)
check(
    "a provider: fake scorer can never pass the gate, validation block or not",
    js.validation_problems({**fake_sc, "validation": real["validation"]}, real_runs) != []
    and all("fake" in p_ for p_ in js.validation_problems(fake_sc, real_runs)),
)
msg_ = js.build_message(BASE, "An article.", ["one", "two", "three"])
r1, r2 = (
    judging.call_judge(msg_, fake_sc["judges"][0]["params"]),
    judging.call_judge(msg_, fake_sc["judges"][0]["params"]),
)
r3 = judging.call_judge(msg_, fake_sc["judges"][1]["params"])
check(
    "the fake judge is deterministic, parses at n, and differs by model",
    r1.output == r2.output
    and js.parse_block(r1.output, 3) is not None
    and r1.output != r3.output
    and r1.cost_usd is not None,
)

_keys = ("LITELLM_BASE_URL", "LITELLM_API_KEY", "OPENROUTER_API_KEY", "EVAL_MODELS_FILE", "MY_KEY")
_saved = {k: os.environ.pop(k, None) for k in _keys}
try:
    check(
        "routing: nothing configured is refused, naming both ways to fix it",
        "OPENROUTER_API_KEY" in _exit(lambda: judging.route({"model": "a/b"}))
        and "LITELLM_BASE_URL" in _exit(lambda: judging.route({"model": "a/b"})),
    )
    os.environ["OPENROUTER_API_KEY"] = "k-or"
    r_ = judging.route({"model": "vendor/model"})
    check(
        "routing: OpenRouter alone goes direct, with the id as written and usage accounting",
        r_["mode"] == "direct"
        and r_["model"] == "vendor/model"
        and judging.extra_body({}, r_) == {"usage": {"include": True}},
    )
    check(
        "routing: a bare alias with no models table is refused",
        "neither an alias" in str(_exit(lambda: judging.route({"model": "bare-alias"}))),
    )
    os.environ["LITELLM_BASE_URL"] = "http://proxy.invalid/"
    check(
        "routing: a proxy URL without its key is refused, not silently sent to OpenRouter",
        "LITELLM_API_KEY" in str(_exit(lambda: judging.route({"model": "x"}))),
    )
    os.environ["LITELLM_API_KEY"] = "k-px"
    r_ = judging.route({"model": "alias-x"})
    check(
        "routing: the proxy wins when both are set, with the model as written",
        r_["mode"] == "proxy"
        and r_["base_url"] == "http://proxy.invalid/v1"
        and r_["model"] == "alias-x"
        and judging.extra_body({}, r_) == {},
    )
    os.environ["MY_KEY"] = "k-own"
    r_ = judging.route({"model": "m", "base_url": "http://own.invalid", "api_key_env": "MY_KEY"})
    check(
        "routing: a judge's own base_url and api_key_env override the environment's",
        r_["base_url"] == "http://own.invalid/v1" and r_["key"] == "k-own",
    )
finally:
    for k_, v_ in _saved.items():
        os.environ.pop(k_, None)
        if v_ is not None:
            os.environ[k_] = v_

with tempfile.TemporaryDirectory() as td_:
    tdp = Path(td_)
    (tdp / "scorers").mkdir()
    (tdp / "scorers" / "mine.txt").write_text("beside the scorer\n")
    (tdp / "scorers" / "sub").mkdir()
    (tdp / "scorers" / "sub" / "p.txt").write_text("nested\n")
    here_sc = scorer(prompt={"file": "mine.txt"}, _dir=str(tdp / "scorers"))
    check(
        "prompt.file: relative to the scorer's own directory when the project root has none",
        js.prompt_text(here_sc) == "beside the scorer",
    )
    check(
        "prompt.file: the repo-relative path still resolves in this checkout",
        "16 numbered summaries" in js.prompt_text(scorer()),
    )
    check(
        "prompt.file: an absolute path is taken as written",
        js.prompt_text(scorer(prompt={"file": str(tdp / "scorers" / "mine.txt")})) == "beside the scorer",
    )
    check(
        "prompt.file: an explicit root replaces the search",
        js.prompt_text(scorer(prompt={"file": "sub/p.txt"}), tdp / "scorers") == "nested",
    )
    check(
        "prompt.file: missing everywhere is refused, listing where it looked",
        "looked in" in str(_exit(lambda: js.prompt_text(scorer(prompt={"file": "nope.txt"})))),
    )

# ── the task: what is judged, from the scorer ────────────────────────────────
check(
    "task: none declared is SummEval's (ARTICLE, SUMMARIES, four dimensions, 1-5)",
    judging.task_of({})
    == {
        "source_label": "ARTICLE",
        "output_label": "SUMMARIES",
        "dimensions": list(judging.DIMS),
        "scale": [1, 5],
    },
)
REL = {"source_label": "QUERY", "output_label": "PASSAGES", "dimensions": ["relevance"], "scale": [0, 3]}
check("task: a declared one replaces the defaults it names", judging.task_of({"task": REL}) == REL)
check(
    "task: a partial one keeps the other defaults",
    judging.task_of({"task": {"dimensions": ["helpfulness"]}})["output_label"] == "SUMMARIES",
)
for bad_task, why in (
    ({"labels": "x"}, "an unknown key"),
    ({"dimensions": []}, "no dimensions"),
    ({"dimensions": ["a", "a"]}, "a repeated dimension"),
    ({"scale": [5, 1]}, "a scale whose low is not below its high"),
    ({"scale": [1]}, "a scale that is not two numbers"),
    ({"scale": [1.0, 5.0]}, "a scale in floats"),
    ({"scale": [0.5, 3.5]}, "a fractional scale"),
    ({"source_label": "A:B"}, "a label with ':'"),
    ({"output_label": "two\nlines"}, "a two-line label"),
):
    try:
        judging.task_of({"task": bad_task})
        refused_ = False
    except ValueError:
        refused_ = True
    check(f"task: {why} is refused", refused_)
check(
    "task: a bad task is refused by name",
    "task.scale" in _exit(lambda: js.task_for(scorer(task={"scale": [3, 3]}))),
)

GEN = "Rate how well each of the {n} numbered passages answers the query, 0 to 3."
check(
    "prompt: {n} is replaced by the count and nothing else changes",
    judging.render_prompt(GEN, 3) == GEN.replace("{n}", "3")
    and judging.render_prompt(GEN, 16) == GEN.replace("{n}", "16"),
)
check(
    "prompt: a prompt with neither {n} nor SummEval's phrases is refused, naming {n}",
    "{n}" in _exit(lambda: judging.render_prompt("Rate them.", 3)),
)
gm = judging.build_message(GEN, "what is x?", ["x is y", "no idea"], "QUERY", "PASSAGES")
check(
    "message: the task's labels head the source and the numbered outputs",
    gm == GEN.replace("{n}", "2") + "\n\nQUERY:\nwhat is x?\n\nPASSAGES:\n1. x is y\n2. no idea",
)
check(
    "message: the default labels are unchanged (SummEval's layout)",
    judging.build_message(BASE, "a", ["s"])
    == judging.build_message(BASE, "a", ["s"], "ARTICLE", "SUMMARIES"),
)
check(
    "parse: the task's dimensions and scale",
    judging.parse_block('{"relevance": [0, 3, 2]}', 3, ["relevance"], [0, 3]) == [0.0, 3.0, 2.0],
)
check(
    "parse: a number outside the task's scale is refused",
    judging.parse_block('{"relevance": [0, 4, 2]}', 3, ["relevance"], [0, 3]) is None,
)
check(
    "parse: a missing task dimension is refused",
    judging.parse_block('{"relevance": [1]}', 1, ["relevance", "grounded"], [0, 3]) is None,
)
fk = judging.call_judge(gm, {"provider": judging.FAKE, "model": "fa", "_task": REL})
fv = json.loads(fk.output)
check(
    "fake judge: answers in the task's dimensions, on its scale, one number per output",
    list(fv) == ["relevance"] and len(fv["relevance"]) == 2 and all(0 <= x <= 3 for x in fv["relevance"]),
)

check(
    "judging set: a scorer without a task keeps the id it had (the task is not hashed)",
    "task" not in m1 and manifest_for()["judging_set_id"] == m1["judging_set_id"],
)
check(
    "judging set: declaring even the default task is a different set (it is hashed)",
    manifest_for(scorer(task=judging.task_of({})))["judging_set_id"] != m1["judging_set_id"],
)
check(
    "judging set: a different declared task is a different set",
    manifest_for(scorer(task=REL))["judging_set_id"]
    != manifest_for(scorer(task={**REL, "scale": [0, 2]}))["judging_set_id"],
)

with tempfile.TemporaryDirectory() as td_:
    prompt_ = Path(td_) / "rel.txt"
    prompt_.write_text(GEN + '\nReply as JSON: {"relevance": [one integer per passage]}\n')
    fake_ = {"provider": judging.FAKE, "temperature": 0.0, "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0}
    rel_sc = scorer(
        task=REL,
        prompt={"file": str(prompt_)},
        judges=[
            {"id": "fa", "params": {**fake_, "model": "fake-a", "family": "gemma"}},
            {"id": "fb", "params": {**fake_, "model": "fake-b", "family": "qwen"}},
        ],
    )
    rel_base = js.prompt_text(rel_sc)
    rel_m = js.build_manifest(rel_sc, "ds", "i" * 64, ITEMS, ARMS, ARTICLES, OUTPUTS, rel_base)
    rel_msgs = [js.message_for(rel_m, rel_base, ARTICLES, OUTPUTS, it, "primary", 0) for it in rel_m["items"]]
    check(
        "a declared task reaches the message: its labels, and the count in place of {n}",
        all(
            "\n\nQUERY:\n" in m_ and "\n\nPASSAGES:\n1. " in m_ and "the 10 numbered passages" in m_
            for m_ in rel_msgs
        ),
    )
    st_ = js.run_judging(
        rel_m, rel_sc, rel_base, ARTICLES, OUTPUTS, Path(td_) / "v", js.real_call, 1.0, log=lambda *_: None
    )
    sc_ = js.load_scores(rel_m, rel_sc, Path(td_) / "v")
    vals_ = [v for p_ in sc_.values() for i_ in p_["primary"].values() for v in i_.values()]
    check(
        "a declared task end to end with fake judges: every block parses, scores on its scale",
        st_["calls"] > 0 and len(vals_) == 2 * len(ITEMS) * N_ARMS and all(0 <= v <= 3 for v in vals_),
    )
    check(
        "a fake judge's task is not sent as one of a real judge's params",
        "_task" not in js.judge_params(rel_sc, {"id": "r", "params": {"provider": "litellm"}})
        and js.judge_params(rel_sc, rel_sc["judges"][0])["_task"] == REL,
    )

import validate_tree as vt  # noqa: E402

with tempfile.TemporaryDirectory() as td_:
    sdir = Path(td_)
    (sdir / "good.txt").write_text("Rate each of the {n} numbered answers.\n")
    (sdir / "bad.txt").write_text("Rate the answers.\n")
    base_ = {
        "kind": "judge",
        "dataset_id": "ds",
        "prompt": {"file": str(sdir / "good.txt")},
        "judges": [
            {
                "id": "fa",
                "params": {
                    "provider": "fake",
                    "model": "a",
                    "family": "x",
                    "usd_per_mtok_in": 0,
                    "usd_per_mtok_out": 0,
                },
            },
            {
                "id": "fb",
                "params": {
                    "provider": "fake",
                    "model": "b",
                    "family": "y",
                    "usd_per_mtok_in": 0,
                    "usd_per_mtok_out": 0,
                },
            },
        ],
        "protocol": {"outputs_per_call": 4},
        "task": {"dimensions": ["correct"]},
    }
    (sdir / "s-good.yaml").write_text(json.dumps({**base_, "scorer_id": "s-good"}))
    check("V13: a scorer with a declared task and a {n} prompt passes", vt.scorer_problems(sdir) == [])
    (sdir / "s-bad.yaml").write_text(
        json.dumps(
            {
                **base_,
                "scorer_id": "s-bad",
                "prompt": {"file": str(sdir / "bad.txt")},
                "protocol": {"outputs_per_call": 16},
            }
        )
    )
    (sdir / "s-task.yaml").write_text(json.dumps({**base_, "scorer_id": "s-task", "task": {"scale": [3, 1]}}))
    probs_ = vt.scorer_problems(sdir)
    check(
        "V13: a prompt that cannot be rendered (no {n}, not SummEval's) is reported",
        any(p.startswith("s-bad.yaml") and "{n}" in p for p in probs_),
    )
    check(
        "V13: a bad task block is reported",
        any(p.startswith("s-task.yaml") and "task.scale" in p for p in probs_),
    )

tut = js.load_scorer(HERE.parent / "tutorial" / "scorers" / "tickets-judge-v1.yaml")
tut_prompt = js.prompt_text(tut)
check(
    "tutorial scorer: loads, declares its task, and its prompt renders with the count",
    tut["_task"]["dimensions"] == ["accuracy", "usefulness"]
    and "each of the 4 numbered summaries" in judging.render_prompt(tut_prompt, 4)
    and "{n}" not in judging.render_prompt(tut_prompt, 4),
)
check(
    "tutorial scorer: refused by the gate (fake judges), so it runs only --unvalidated",
    js.validation_problems(tut) != [],
)

import leaderboard as lb  # noqa: E402

check(
    "leaderboard: judge means (quarters, sixths) are exact, so no precision note",
    lb._small_fractions([3.25, 2.5, 4.0, 1.75, 2 / 3, 13 / 6]),
)
check(
    "leaderboard: scores rounded to 6 decimals still get the note",
    not lb._small_fractions([0.25, 0.333333]) and not lb._small_fractions([0.123457]),
)
check("leaderboard: no values is not 'all exact'", not lb._small_fractions([]))
check(
    "leaderboard: judge means as stored (round 10) never get the note: exact or >= 8 decimals",
    all(
        lb._small_fractions([round(v, 10)]) or lb._stored_decimals([round(v, 10)]) >= lb._MIN_TIE_DECIMALS
        for v in (3.25, 2.5, 2 / 3, 13 / 6, 4.0833333333)
    ),
)

check(
    "prompt: {n} together with SummEval's fixed phrases is refused (they would stay at 16)",
    "16"
    in _exit(
        lambda: judging.render_prompt("Rate the {n} items: 16 numbered summaries, a list of 16 integers.", 5)
    ),
)

# The default arm set: every config on the dataset, latest run per config; another dataset's
# runs are not in it; a mix of config versions is reported.
with tempfile.TemporaryDirectory() as td_:
    rd = Path(td_)
    for name, cid, ds, at in (
        ("a_v1_r1", "a_v1", "ds", "2026-01-01"),
        ("a_v1_r2", "a_v1", "ds", "2026-01-02"),
        ("b_v1_r1", "b_v1", "ds", "2026-01-01"),
        ("a_v2_r1", "a_v2", "ds", "2026-01-03"),
        ("c_v1_r1", "c_v1", "other", "2026-01-01"),
    ):
        (rd / name).mkdir()
        (rd / name / "metrics.json").write_text(
            json.dumps({"config_id": cid, "dataset_id": ds, "created_at": at, "params": {"family": "x"}})
        )
    found = js.discover_arms("ds", "", rd)
    check(
        "default arms: every config on the dataset, none from another dataset",
        [a["config_id"] for a in found] == ["a_v1", "a_v2", "b_v1"],
    )
    check(
        "default arms: repeat runs of one config are one arm, the latest",
        next(a for a in found if a["config_id"] == "a_v1")["run"] == "a_v1_r2",
    )
    check(
        "default arms: a mix of config versions is reported",
        js.config_versions(found) == ["_v1", "_v2"]
        and js.config_versions([a for a in found if a["config_id"] != "a_v2"]) == ["_v1"],
    )

# A real judge is never handed the fake judge's task, whatever run_judging does.
with tempfile.TemporaryDirectory() as td_:
    handed: list = []

    def rec(message, params):
        handed.append(dict(params))
        n_ = len(re.findall(r"^\d+\. ", message.rsplit("SUMMARIES:\n", 1)[1], re.M))
        return SimpleNamespace(
            output=json.dumps({d: [3] * n_ for d in judging.DIMS}),
            tokens_in=10,
            tokens_out=10,
            cost_usd=0.0,
            extra={},
            meta={},
        )

    real_sc = scorer(
        task={"dimensions": list(judging.DIMS)},
        judges=[
            {
                "id": "ra",
                "params": {
                    "provider": "litellm",
                    "model": "m_a",
                    "family": "gemma",
                    "usd_per_mtok_in": 1.0,
                    "usd_per_mtok_out": 2.0,
                },
            },
            {
                "id": "rb",
                "params": {
                    "provider": "litellm",
                    "model": "m_b",
                    "family": "qwen",
                    "usd_per_mtok_in": 1.0,
                    "usd_per_mtok_out": 2.0,
                },
            },
        ],
    )
    js.run_judging(
        manifest_for(real_sc), real_sc, BASE, ARTICLES, OUTPUTS, Path(td_), rec, 1.0, log=lambda *_: None
    )
    check("run_judging: no real judge's call carries _task", handed and all("_task" not in p for p in handed))

# A provider refusing mid-pass (its own budget guardrail, 403) stops the pass like the cost cap:
# no traceback, every verdict bought so far kept, and the same command resumes.
with tempfile.TemporaryDirectory() as td_:
    good = fake_judge()
    n_ok = [0]

    def refusing(message, params):
        if n_ok[0] >= 5:
            raise RuntimeError("Error code: 403 - Budget limit exceeded (weekly limit)")
        n_ok[0] += 1
        return good(message, params)

    st_r = run_all(td_, call=refusing)
    kept = len(list(Path(td_).glob("*/*.json")))
    check(
        "a refused judge call stops the pass cleanly, verdicts so far kept",
        st_r["aborted"] and "403" in st_r.get("call_failed", "") and kept == 5 and st_r["calls"] == 5,
    )
    st_r2 = run_all(td_, call=fake_judge())
    check(
        "after a refusal the same pass resumes: only the missing verdicts are bought",
        not st_r2["aborted"] and st_r2["skipped"] == 5 and st_r2["calls"] == 2 * N_TASKS - 5,
    )

# ── validate_judge_zhang: the parts that keep the third-party text out of the records ──
import validate_judge_zhang as vz  # noqa: E402

art = "The council approved the new bridge on Tuesday after a long and heated debate about its cost"
summs = ["The council approved a new bridge.", ""]
src = vz.shingles([art, *summs])
check(
    "zhang: a reply quoting eight words of the article is detected (and so withheld)",
    vz.quotes_source('{"coherence": [5]} the council approved the new bridge on tuesday after', src),
)
check(
    "zhang: an ordinary JSON reply is not",
    not vz.quotes_source(
        '{"coherence": [5, 4], "consistency": [5, 1], "fluency": [5, 1], "relevance": [4, 1]}', src
    ),
)
check(
    "zhang: dimensions parsed per dimension, each in 1..5, n numbers",
    vz.parse_dims('{"coherence": [5, 1], "consistency": [4, 1], "fluency": [5, 2], "relevance": [3, 1]}', 2)
    == {"coherence": [5.0, 1.0], "consistency": [4.0, 1.0], "fluency": [5.0, 2.0], "relevance": [3.0, 1.0]}
    and vz.parse_dims('{"coherence": [5, 1]}', 2) is None
    and vz.parse_dims(
        '{"coherence": [5, 9], "consistency": [4, 1], "fluency": [5, 2], "relevance": [3, 1]}', 2
    )
    is None,
)
_ho = vz.held_out(
    [
        {"coherence": 5, "relevance": 4, "faithfulness": 1},
        {"coherence": 3, "relevance": 2, "faithfulness": 0},
        {"coherence": 1, "relevance": 5, "faithfulness": 1},
    ],
    "a",
    "m",
)
check(
    "zhang: each rating is held out once against the mean of the other two",
    len(_ho) == 3
    and sorted(h["coherence"] for h, _ in _ho) == [1, 3, 5]
    and all(abs(rest["coherence"] - (9 - h["coherence"]) / 2) < 1e-9 for h, rest in _ho),
)
_bl = vz.blocks("a1", [f"s{i:02d}" for i in range(19)], 16)
check(
    "zhang: 19 summaries in blocks of 10 and 9, each summary once, order seeded per article",
    [len(b) for b in _bl] == [10, 9]
    and sorted(functools.reduce(operator.iadd, _bl, [])) == [f"s{i:02d}" for i in range(19)]
    and _bl == vz.blocks("a1", [f"s{i:02d}" for i in range(19)], 16)
    and functools.reduce(operator.iadd, _bl, [])
    != functools.reduce(operator.iadd, vz.blocks("a2", [f"s{i:02d}" for i in range(19)], 16), []),
)

# ── the package's gateway is examples/_shared/gateway.py's, by test ─────────────────────
# Two copies on purpose (the package cannot import the examples), so they are held to each
# other here, as the judge prompt and parser are above: same route, same request body.
sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))
import gateway as _gw  # noqa: E402

_gw_keys = ("LITELLM_BASE_URL", "LITELLM_API_KEY", "OPENROUTER_API_KEY")
_gw_saved = {k: os.environ.pop(k, None) for k in _gw_keys}
try:
    _cases = [
        ({"OPENROUTER_API_KEY": "sk-or-test"}, {"model": "eval-claude-haiku"}),
        ({"OPENROUTER_API_KEY": "sk-or-test"}, {"model": "vendor/my-model"}),
        (
            {
                "OPENROUTER_API_KEY": "sk-or-test",
                "LITELLM_BASE_URL": "http://127.0.0.1:9",
                "LITELLM_API_KEY": "k",
            },
            {"model": "eval-claude-haiku"},
        ),
        ({}, {"model": "eval-claude-haiku"}),
    ]
    for _env, _params in _cases:
        for k in _gw_keys:
            os.environ.pop(k, None)
        os.environ.update(_env)
        _got: list[tuple] = []
        for _fn in (judging.route, _gw.route):
            try:
                _r = _fn(dict(_params))
                _got.append(
                    (
                        "route",
                        _r,
                        judging.extra_body(dict(_params), _r)
                        if _fn is judging.route
                        else _gw.extra_body(dict(_params), _r),
                    )
                )
            except SystemExit:
                _got.append(("refused",))
        check(
            f"gateway parity: {sorted(_env) or 'no keys'} / {_params['model']}: same route and body",
            _got[0] == _got[1],
        )
finally:
    for k, v in _gw_saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

sys.exit(summary())
