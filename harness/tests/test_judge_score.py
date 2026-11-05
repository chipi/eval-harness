#!/usr/bin/env python3
"""Assertions for the judging pass. No network, no API key, no money: a fake judge.

    python tests/test_judge_score.py

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / "tools"))  # validate_judge_*
import functools
import operator

from evaluation_harness import judge_score as js
from evaluation_harness import judging
from evaluation_harness._common import load_module

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


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
    wrec = next(Path(td).glob("ja/*.json"))
    wtext = wrec.parent / ".withheld" / f"{wrec.stem}.txt"
    check(
        "a withheld reply's text is kept beside it, out of git, so its cause can be read",
        wtext.is_file()
        and wtext.read_text() == "I cannot do this."
        and (wrec.parent / ".withheld" / ".gitignore").read_text().strip() == "*",
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
    from evaluation_harness import validate_tree as _vt

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
    "a scorer with no validation.dataset_id gets a label, not a KeyError",
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
    "the label names validation.dataset_id's dataset and says it is provenance",
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
    mj_["fingerprint"]["settings"]["declared"]["prompt_sha256"] = "0" * 64
    mf.write_text(json.dumps(mj_))
    check(
        "gate: a validation run that used a different prompt: refused",
        any("used prompt" in p for p in js.validation_problems(real, rd)),
    )
    del mj_["fingerprint"]["settings"]["declared"]["prompt_sha256"]
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
    # The controls are not optional (ADR-0001 §4): a forgotten field cannot switch them off.
    clean = {k: v for k, v in real.items() if not k.startswith("_")}
    for label, proto, refused in (
        ("no noise_check_fraction", {"outputs_per_call": 16, "position_check_fraction": 0.1}, True),
        ("no position_check_fraction", {"outputs_per_call": 16, "noise_check_fraction": 0.1}, True),
        (
            "noise 0",
            {"outputs_per_call": 16, "position_check_fraction": 0.1, "noise_check_fraction": 0},
            True,
        ),
        (
            "position 0 on 16 per call",
            {"outputs_per_call": 16, "position_check_fraction": 0, "noise_check_fraction": 0.1},
            True,
        ),
        (
            "position 0 on 1 per call",
            {"outputs_per_call": 1, "position_check_fraction": 0, "noise_check_fraction": 0.1},
            False,
        ),
    ):
        pc = Path(td) / "controls.yaml"
        pc.write_text(yaml.safe_dump(dict(clean, protocol=proto)))
        check(
            f"controls: {label} {'is refused' if refused else 'is accepted (no order to check)'}",
            raises_exit(lambda p=pc: js.load_scorer(p)) == refused,
        )
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
        d.mkdir(parents=True)
        rows = []
        for i in ITEMS:
            _outputs.writer(d).add(i, OUTPUTS[a["config_id"]][i])
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
        and mj["derived"]["kind"] == "judge"
        and mj["derived"]["from"] == arms[0]["run"]
        and mj["derived"]["with"]["judging_set_id"] == m1["judging_set_id"]
        and mj["fingerprint"]["hash"] is None
        and "coverage" not in mj["scores"],
    )
    check("metrics.json: kinds mark judge columns quality", mj["metric_kinds"]["judge_score"] == "quality")
    check(
        "metrics.json: the source's cost and speed keep their kinds (the judged leaderboard has a frontier)",
        mj["metric_kinds"].get("cost_usd") == "cost" and mj["metric_kinds"].get("latency_ms") == "speed",
        str(mj["metric_kinds"]),
    )
    js.write_scored_runs(m1, sc, arms, proj, td / "unval", "unvalidated judge", False)
    mu = json.loads((td / "unval" / arms[0]["run"] / "metrics.json").read_text())
    check(
        "--unvalidated: the primary metric and the label say so",
        mu["primary_metric"] == "judge_score_unvalidated"
        and mu["derived"]["with"]["label"] == "unvalidated judge"
        and mu["derived"]["with"]["validated"] is False,
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


# ── one summary per call (the pointwise eval) ────────────────────────────────
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

from evaluation_harness import validate_tree as vt  # noqa: E402

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

# A judge goes where its `provider:` says; its keys are EVAL_JUDGE_<NAME> first, then <NAME>.
_keys = ("LITELLM_BASE_URL", "LITELLM_API_KEY", "OPENROUTER_API_KEY", "EVAL_JUDGE_LITELLM_API_KEY")
_saved = {k: os.environ.pop(k, None) for k in _keys}
try:
    _lj = {"provider": "litellm", "model": "eval-x", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 1.0}
    _sc_l = {"judges": [{"id": "lj", "params": _lj}]}
    _acc = js.judge_access(_sc_l)
    check(
        "judge access: a litellm judge with nothing set names both variables a judge may set",
        _acc[0][2]
        and any("EVAL_JUDGE_LITELLM_API_KEY or LITELLM_API_KEY" in p_ for p_ in _acc[0][2])
        and any("LITELLM_BASE_URL" in p_ for p_ in _acc[0][2]),
        str(_acc),
    )
    os.environ["OPENROUTER_API_KEY"] = "sk-or-only"
    check(
        "judge access: an OpenRouter key does not reach a judge that names litellm",
        js.judge_access(_sc_l)[0][2] != [],
    )
    os.environ.update(LITELLM_BASE_URL="http://proxy.invalid/", LITELLM_API_KEY="k-arms")
    _acc = js.judge_access(_sc_l)
    check(
        "judge access: with the arms' proxy key and no judge key, the judge shares the arms'",
        _acc[0][2] == []
        and "key LITELLM_API_KEY (shared with the arms)" in _acc[0][1]
        and "http://proxy.invalid/v1" in _acc[0][1],
        str(_acc),
    )
    os.environ["EVAL_JUDGE_LITELLM_API_KEY"] = "k-judging"
    _acc = js.judge_access(_sc_l)
    check(
        "judge access: EVAL_JUDGE_LITELLM_API_KEY is the judge's own key, used first",
        "key EVAL_JUDGE_LITELLM_API_KEY (judging's own)" in _acc[0][1],
        str(_acc),
    )
    check(
        "judge access: a fake judge calls nothing",
        js.judge_access({"judges": [{"id": "f", "params": {"provider": "fake", "model": "m"}}]})[0][
            1
        ].startswith("fake"),
    )
    check(
        "a judge's identity does not include which key pays for it",
        js.judge_fingerprint({"id": "lj", "params": _lj})
        == js.judge_fingerprint({"id": "lj", "params": {**_lj, "api_key_env": "OTHER_KEY"}})
        != js.judge_fingerprint({"id": "lj", "params": {**_lj, "provider": "openrouter"}}),
    )
finally:
    for k_, v_ in _saved.items():
        os.environ.pop(k_, None)
        if v_ is not None:
            os.environ[k_] = v_

# The committed scorers' judges kept their identity: every committed verdict's judge_fp is the
# fingerprint its scorer's judge has now.
_vroot = HERE.parent / "data" / "judge-verdicts"
_bad_fp = []
for _sf in sorted((HERE.parent / "data" / "scorers").glob("*.yaml")):
    _sc = js.load_scorer(_sf)
    _want = {j["id"]: js.judge_fingerprint(j) for j in _sc["judges"]}
    for _vf in (_vroot / _sc["scorer_id"]).glob("*/*/*.json") if (_vroot / _sc["scorer_id"]).is_dir() else []:
        _v = json.loads(_vf.read_text())
        if "judge_fp" in _v and _v.get("judge") in _want and _v["judge_fp"] != _want[_v["judge"]]:
            _bad_fp.append(str(_vf.relative_to(_vroot)))
check(
    "every committed verdict's judge_fp still matches its scorer's judge",
    not _bad_fp,
    f"{len(_bad_fp)} differ, e.g. {_bad_fp[:3]}",
)

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

from evaluation_harness import validate_tree as vt  # noqa: E402

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
        "protocol": {"outputs_per_call": 4, "position_check_fraction": 0.25, "noise_check_fraction": 0.25},
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
                "protocol": {
                    "outputs_per_call": 16,
                    "position_check_fraction": 0.25,
                    "noise_check_fraction": 0.25,
                },
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

from evaluation_harness import leaderboard as lb  # noqa: E402

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
        and js.config_versions([a for a in found if a["config_id"] != "a_v2"]) == []
        # different arms at different versions are not a mix (the newcomer trial's opus_v2 beside mistral_v1)
        and js.config_versions([{"config_id": "opus_v2"}, {"config_id": "mistral_v1"}]) == [],
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


# ══ judging modes: pick and pairwise (RFC-005 "Judging modes") ═══════════════════════════════════════
# A small world for the modes: 4 arms whose outputs differ only in length (arm k is k + 1 'w's longer
# than arm 0), 6 items. The fake judge ranks by length (`prefer: longer`), so who wins is known.
import itertools  # noqa: E402
import math  # noqa: E402

import jsonschema  # noqa: E402
import yaml  # noqa: E402

SCHEMAS = HERE.parent / "schemas"
EXAMPLE = HERE.parents[1] / "examples" / "summeval-judging"
MARMS = ARMS[:4]
MIDS = [a["config_id"] for a in MARMS]
MITEMS = [f"it{n}" for n in range(6)]
MARTICLES = {i: f"Article {i}. It is long enough to be an article." for i in MITEMS}


def m_outputs(extra=None):
    """arm k's text is 'summary' plus k + 1 w's; `extra` maps arm index -> w's, to make ties."""
    w = {k: k + 1 for k in range(4)} | (extra or {})
    return {a["config_id"]: {i: f"summary {'w' * w[k]} {i}" for i in MITEMS} for k, a in enumerate(MARMS)}


PICK_BASE = (EXAMPLE / "prompt_pick.txt").read_text(encoding="utf-8").strip()
PAIR_BASE = (EXAMPLE / "prompt_pairwise.txt").read_text(encoding="utf-8").strip()


def mscorer(mode, prefer=("longer", "longer"), position=0.5, noise=0.5, **over):
    sc = scorer(
        mode=mode,
        judges=[
            {
                "id": jid,
                "params": {
                    "provider": "fake",
                    "model": f"m_{jid}",
                    "family": fam_,
                    "prefer": pf,
                    "usd_per_mtok_in": 1.0,
                    "usd_per_mtok_out": 2.0,
                },
            }
            for jid, fam_, pf in zip(("ja", "jb"), ("gemma", "qwen"), prefer)
        ],
        prompt={"file": "examples/summeval-judging/prompt_pick.txt"},
        protocol={
            "outputs_per_call": 2 if mode == "pairwise" else 4,
            "blinding": True,
            "order_seed": 0,
            "position_check_fraction": position,
            "noise_check_fraction": noise,
        },
    )
    sc.update(over)
    return sc


def base_of(sc):
    return {"pairwise": PAIR_BASE, "pick": PICK_BASE}.get(mode_of_(sc), BASE)


def mmanifest(sc, outputs=None, arms=None):
    base = base_of(sc)
    return js.build_manifest(
        sc, "ds", "1" * 64, MITEMS, arms or MARMS, MARTICLES, outputs or m_outputs(), base
    )


def mode_of_(sc):
    return sc.get("mode") or "grade"


def mrun(vdir, sc, man, outputs=None, call=judging.call_judge, cap=None, retry=False):
    base = base_of(sc)
    return js.run_judging(
        man,
        sc,
        base,
        MARTICLES,
        outputs or m_outputs(),
        Path(vdir),
        call,
        cap,
        retry_unparsed=retry,
        log=lambda *_: None,
    )


def mproj(sc, man, vdir):
    return js.project(sc, js.load_scores(man, sc, Path(vdir)), MITEMS)


# ── parsers ──────────────────────────────────────────────────────────────────
check("parse_pick: one number", judging.parse_pick('{"best": [3]}', 16) == [3])
check("parse_pick: several, in the order given", judging.parse_pick('{"best": [7, 3]}', 16) == [7, 3])
check(
    "parse_pick: wrapped in a fence and a sentence still parses",
    judging.parse_pick('Here:\n```json\n{"best": [2]}\n```', 4) == [2],
)
for what_, reply_ in (
    ("a number out of range", '{"best": [5]}'),
    ("zero", '{"best": [0]}'),
    ("a repeat", '{"best": [2, 2]}'),
    ("an empty list", '{"best": []}'),
    ("a bare number, not a list", '{"best": 3}'),
    ("a string number", '{"best": ["3"]}'),
    ("true", '{"best": [true]}'),
    ("a float", '{"best": [2.0]}'),
    ("the wrong key", '{"better": [2]}'),
    ("no JSON", "number 3"),
    ("a JSON list", "[3]"),
    ("empty", ""),
):
    check(f"parse_pick: {what_} is None", judging.parse_pick(reply_, 4) is None)
check("parse_pick: None is None", judging.parse_pick(None, 4) is None)
check(
    "parse_pairwise: 1, 2 and tie",
    [judging.parse_pairwise(f'{{"better": {v}}}') for v in ("1", "2", '"tie"')] == [1, 2, "tie"],
)
check("parse_pairwise: Tie is a tie", judging.parse_pairwise('{"better": "Tie"}') == "tie")
for what_, reply_ in (
    ("3", '{"better": 3}'),
    ("0", '{"better": 0}'),
    ("true", '{"better": true}'),
    ('"1"', '{"better": "1"}'),
    ("1.0", '{"better": 1.0}'),
    ("a list", '{"better": [1]}'),
    ("the wrong key", '{"best": 1}'),
    ("no JSON", "the first"),
):
    check(f"parse_pairwise: {what_} is None", judging.parse_pairwise(reply_) is None)

# ── messages: layout, the reminder, and byte-equality with the SummEval adapter ──────────
ad_item: dict = {"article": "  An article.\n", "summaries": [f" s{i} \n" for i in range(16)]}
pm_ = judging.build_pick_message(PICK_BASE, ad_item["article"], ad_item["summaries"])
check(
    "pick message: prompt for 16, ARTICLE, numbered SUMMARIES, then the answer-only-JSON instruction",
    pm_.startswith("You will be shown a news article and 16 numbered summaries")
    and "\n\nARTICLE:\nAn article.\n\nSUMMARIES:\n1. s0\n2. s1\n" in pm_
    and pm_.endswith(judging.PICK_REMINDER)
    and "{n}" not in pm_,
)
check(
    "pick message: byte-identical to the SummEval adapter's own",
    pm_ == ad._pick_message(ad_item, {"prompt": PICK_BASE}),
)
pw_ = judging.build_pairwise_message(PAIR_BASE, ad_item["article"], ad_item["summaries"][3:5])
check(
    "pairwise message: two summaries, the pair reminder last, byte-identical to the adapter's own",
    "\n\nSUMMARIES:\n1. s3\n2. s4\n\n" in pw_
    and pw_.endswith(judging.PAIR_REMINDER)
    and "shown a news article and 2 numbered summaries" in pw_
    and pw_ == ad._pair_message(ad_item, 3, 4, {"prompt": PAIR_BASE}),
)
check(
    "the adapter's reminders are the package's",
    ad.PICK_REMINDER == judging.PICK_REMINDER and ad.PAIR_REMINDER == judging.PAIR_REMINDER,
)


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


check(
    "pairwise message: three outputs are refused",
    _raises(ValueError, lambda: judging.build_pairwise_message(PAIR_BASE, "a", ["x", "y", "z"])),
)
check(
    "the grade message is untouched by the modes",
    judging.build_message(BASE, ad_item["article"], ad_item["summaries"])
    == ad._judge_message(ad_item, {"prompt": judging.render_prompt(BASE, 16)}),
)

# ── the scorer: mode, its checks, and what only a declared mode changes ────────────────────
clean_ = {k: v for k, v in real.items() if not k.startswith("_")}
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)

    def load_with(label, **over):
        pth = td / f"{label}.yaml"
        pth.write_text(yaml.safe_dump(dict(clean_, **over)))
        return pth

    def refused_with(label, needle, **over):
        msg = _exit(lambda: js.load_scorer(load_with(label, **over)))
        return needle in msg

    val_pick = dict(clean_["validation"], mode="pick")
    val_pair = dict(clean_["validation"], mode="pairwise")
    pr2 = dict(clean_["protocol"], outputs_per_call=2)
    check("mode: an unknown mode is refused", refused_with("bogus", "mode must be one of", mode="bogus"))
    check(
        "mode: pick with a validation that has no mode (grade) is refused",
        refused_with("pick-grade", "validation.mode is 'grade' but mode is 'pick'", mode="pick"),
    )
    check(
        "mode: grade with validation.mode pick is refused",
        refused_with(
            "grade-pick", "validation.mode is 'pick' but mode is 'grade'", mode="grade", validation=val_pick
        ),
    )
    check(
        "mode: an absent mode with validation.mode pairwise is refused",
        refused_with("none-pair", "validation.mode is 'pairwise'", validation=val_pair),
    )
    check(
        "mode: pick whose validation.mode is pairwise is refused",
        refused_with(
            "pick-pair", "validation.mode is 'pairwise' but mode is 'pick'", mode="pick", validation=val_pair
        ),
    )
    ok_pick = js.load_scorer(load_with("ok-pick", mode="pick", validation=val_pick))
    check(
        "mode: pick with validation.mode pick loads",
        ok_pick["mode"] == "pick" and js.mode_of(ok_pick) == "pick",
    )
    check(
        "mode: pairwise with outputs_per_call 16 is refused, and says a pair is 2",
        refused_with("pair-16", "exactly 2 outputs", mode="pairwise", validation=val_pair),
    )
    ok_pair = js.load_scorer(load_with("ok-pair", mode="pairwise", validation=val_pair, protocol=pr2))
    check("mode: pairwise with outputs_per_call 2 loads", js.mode_of(ok_pair) == "pairwise")
    check(
        "mode: pairwise still needs its position check (a call of 2 has an order)",
        refused_with(
            "pair-nopos",
            "position_check_fraction",
            mode="pairwise",
            validation=val_pair,
            protocol=dict(pr2, position_check_fraction=0),
        ),
    )
    check(
        "mode: grade written out and absent are the same scorer in effect",
        js.mode_of(js.load_scorer(load_with("explicit-grade", mode="grade"))) == "grade"
        and js.mode_of(real) == "grade",
    )
    # the gate: a validation run measured in another mode does not validate the scorer
    prob_pick = js.validation_problems(
        dict(real, mode="pick", validation=val_pick), runs_dir=HERE.parent / "data" / "runs"
    )
    check(
        "gate: a validation run measured in grade mode does not validate a pick scorer",
        any("measured mode='grade', the scorer uses 'pick'" in p for p in prob_pick),
        str(prob_pick[:2]),
    )
    check(
        "gate: a scorer whose validation.mode differs from its mode is a problem even built in code",
        any("validation.mode" in p for p in js.validation_problems(dict(real, mode="pick"))),
    )
    check(
        "gate: the committed grade scorers still gate as before (a run's absent mode is grade)",
        js.validation_problems(real) == [],
    )

    # V13 reads a pick and a pairwise scorer as well-formed (their prompts render)
    sdir = td / "scorers"
    sdir.mkdir()
    for sid_, mode_, proto_ in (("judge-mode-pick", "pick", {}), ("judge-mode-pair", "pairwise", pr2)):
        body = {k: v for k, v in real.items() if not k.startswith("_") and k != "validation"} | {
            "scorer_id": sid_,
            "mode": mode_,
            "protocol": dict(real["protocol"]) | proto_,
            "prompt": {
                "file": f"examples/summeval-judging/prompt_{'pick' if mode_ == 'pick' else 'pairwise'}.txt"
            },
        }
        (sdir / f"{sid_}.yaml").write_text(yaml.safe_dump(body))
        jsonschema.validate(body, json.loads((SCHEMAS / "scorer.schema.json").read_text()))
    check(
        "V13: a pick and a pairwise scorer are well-formed",
        vt.scorer_problems(sdir) == [],
        str(vt.scorer_problems(sdir)),
    )
    bad_body = yaml.safe_load((sdir / "judge-mode-pick.yaml").read_text()) | {"mode": "sideways"}
    try:
        jsonschema.validate(bad_body, json.loads((SCHEMAS / "scorer.schema.json").read_text()))
        check("scorer schema: mode outside grade/pick/pairwise is invalid", False)
    except jsonschema.ValidationError:
        check("scorer schema: mode outside grade/pick/pairwise is invalid", True)

# pick needs one call per item
sc_pick_small = mscorer("pick", protocol={**mscorer("pick")["protocol"], "outputs_per_call": 3})
msg_ = _exit(lambda: mmanifest(sc_pick_small))
check(
    "pick: outputs_per_call below the number of arms is refused, and says why",
    "at least the number of arms (4)" in msg_ and "each block's winner, not the item's" in msg_,
    msg_,
)
check(
    "pick: outputs_per_call equal to the arms is accepted; above it too",
    not _exit(lambda: mmanifest(mscorer("pick")))
    and not _exit(
        lambda: mmanifest(mscorer("pick", protocol={**mscorer("pick")["protocol"], "outputs_per_call": 16}))
    ),
)

# ── the judging set ──────────────────────────────────────────────────────────
g_sc = scorer(protocol={**scorer()["protocol"], "outputs_per_call": 4})
g_plain = mmanifest(g_sc)
g_explicit = mmanifest(dict(g_sc, mode="grade"))
mp_, mw_ = mmanifest(mscorer("pick")), mmanifest(mscorer("pairwise"))
check(
    "grade: no `mode` key in the set, and `mode: grade` written out is the same set (same hash and id)",
    "mode" not in g_plain and g_plain == g_explicit,
)
check(
    "a declared mode enters the hash: pick, pairwise and grade are three different sets",
    len({g_plain["judging_set_sha256"], mp_["judging_set_sha256"], mw_["judging_set_sha256"]}) == 3
    and mp_["mode"] == "pick"
    and mw_["mode"] == "pairwise",
)
check(
    "every manifest recomputes to its stored hash (V11's rule) in every mode",
    all(js.manifest_hash(m) == m["judging_set_sha256"] for m in (g_plain, mp_, mw_)),
)
check(
    "pick: one block of all 4 arms per item, the position pass a permutation of it",
    all(
        len(it["primary"]) == 1
        and sorted(it["primary"][0]) == sorted(MIDS)
        and sorted(it["position"][0]) == sorted(MIDS)
        for it in mp_["items"]
    )
    and any(it["primary"] != it["position"] for it in mp_["items"])
    and mp_["protocol"]["block_sizes"] == [4],
)
want_pairs = {frozenset(p) for p in itertools.combinations(MIDS, 2)}
check(
    "pairwise: one block per pair of arms per item (n(n-1)/2 = 6), every pair once, blocks of 2",
    all(
        len(it["primary"]) == 6
        and {frozenset(b) for b in it["primary"]} == want_pairs
        and all(len(b) == 2 for b in it["primary"])
        for it in mw_["items"]
    )
    and mw_["protocol"]["block_sizes"] == [2],
)
check(
    "pairwise: the position pass is the same pairs in swapped order, block for block",
    all(it["position"] == [b[::-1] for b in it["primary"]] for it in mw_["items"]),
)
check(
    "pairwise: pairs are not oriented by one order per item (arms sit first and second across pairs)",
    any(
        len({b[0] for b in it["primary"]} | {b[1] for b in it["primary"]}) == 4
        and len({b[0] for b in it["primary"]}) > 1
        for it in mw_["items"]
    ),
)
check(
    "the control subsets are the same in every mode (a fraction of the items)",
    len(mp_["position_items"]) == 3 == len(mw_["noise_items"])
    and mp_["position_items"] == mw_["position_items"],
)
sets_schema = json.loads((SCHEMAS / "judging-set.schema.json").read_text())
check(
    "judging-set schema: pick and pairwise sets validate",
    all(jsonschema.Draft202012Validator(sets_schema).is_valid(m) for m in (mp_, mw_)),
)
check(
    "judging-set schema: a grade set (no mode) still validates",
    jsonschema.Draft202012Validator(sets_schema).is_valid(
        json.loads(next((HERE.parent / "data" / "judging-sets").glob("*.json")).read_text())
    ),
)
check(
    "the same arm outputs in a pairwise set: a changed output is a different set",
    mmanifest(mscorer("pairwise"), outputs=m_outputs({2: 9}))["judging_set_id"] != mw_["judging_set_id"],
)

# blinding: a pick or pairwise prompt names no arm, run or family
names_m = [*MIDS, *(a["run"] for a in MARMS), "gemma", "qwen"]
msgs_m = [
    js.message_for(m, PICK_BASE if m["mode"] == "pick" else PAIR_BASE, MARTICLES, m_outputs(), it, p, b)
    for m in (mp_, mw_)
    for it in m["items"]
    for p in ("primary", "position")
    for b in range(len(it[p]))
]
check(
    "pick and pairwise prompts name no arm, run or family", not any(n in m for m in msgs_m for n in names_m)
)
check(
    "pick prompts number 4 summaries; pairwise prompts number 2",
    all(
        len(re.findall(r"^\d+\. ", m.split("SUMMARIES:\n")[1], re.M))
        == (4 if "best" in m.rsplit("\n", 1)[-1] else 2)
        for m in msgs_m
    ),
)

# ── the fake judge answers in the shape of the mode ─────────────────────────────────────
fp_ = {"provider": "fake", "model": "m", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 1.0}
msg4 = judging.build_pick_message(PICK_BASE, "A", ["aa", "bbbb", "cc", "bbbb"])
check(
    "fake judge, pick: the longest outputs are named, all of them when equal",
    json.loads(judging.call_judge(msg4, fp_ | {"_mode": "pick"}).output) == {"best": [2, 4]}
    and json.loads(judging.call_judge(msg4, fp_ | {"_mode": "pick", "prefer": "shorter"}).output)
    == {"best": [1, 3]}
    and json.loads(judging.call_judge(msg4, fp_ | {"_mode": "pick", "prefer": "first"}).output)
    == {"best": [1]},
)
msg2 = judging.build_pairwise_message(PAIR_BASE, "A", ["aa", "bbb"])
msg2t = judging.build_pairwise_message(PAIR_BASE, "A", ["aa", "bb"])
check(
    "fake judge, pairwise: the longer wins, equal lengths tie, `first` always says 1",
    json.loads(judging.call_judge(msg2, fp_ | {"_mode": "pairwise"}).output) == {"better": 2}
    and json.loads(judging.call_judge(msg2, fp_ | {"_mode": "pairwise", "prefer": "shorter"}).output)
    == {"better": 1}
    and json.loads(judging.call_judge(msg2t, fp_ | {"_mode": "pairwise"}).output) == {"better": "tie"}
    and json.loads(judging.call_judge(msg2, fp_ | {"_mode": "pairwise", "prefer": "first"}).output)
    == {"better": 1},
)
check(
    "fake judge: its answers parse with the real parsers",
    judging.parse_pick(judging.call_judge(msg4, fp_ | {"_mode": "pick"}).output, 4) == [2, 4]
    and judging.parse_pairwise(judging.call_judge(msg2t, fp_ | {"_mode": "pairwise"}).output) == "tie",
)
check(
    "fake judge: an unknown `prefer` is an error, not a silent default",
    _raises(ValueError, lambda: judging.call_judge(msg4, fp_ | {"_mode": "pick", "prefer": "best"})),
)
check(
    "fake judge in grade mode is unchanged: no _mode, scores on the scale",
    sorted(json.loads(judging.call_judge(msg4.replace("\n\nAnswer only", "\n\nx"), fp_).output))
    == sorted(js.DIMS),
)
check(
    "judge_params tells a fake judge the mode, a real judge nothing",
    js.judge_params(mscorer("pick"), mscorer("pick")["judges"][0])["_mode"] == "pick"
    and "_mode"
    not in js.judge_params(mscorer("pick"), {"id": "x", "params": {"provider": "openai", "model": "m"}}),
)

# ── pick, end to end with fake judges ───────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc = mscorer("pick")
    man = mp_
    n_tasks = len(js.tasks(man))
    st = mrun(td, sc, man)
    check(
        "pick: calls = judges x (items + position items + noise items) = 2 x (6 + 3 + 3)",
        st["calls"] == 2 * 12 == 2 * n_tasks and st["skipped"] == 0 and not st["aborted"],
    )
    stored = json.loads((td / "ja" / f"{MITEMS[0]}.primary.b0.json").read_text())
    check(
        "pick: a verdict stores `best` (1-based, block order) in place of `scores`, with the reply",
        "scores" not in stored
        and stored["best"] == [man["items"][0]["primary"][0].index(MIDS[3]) + 1]
        and json.loads(stored["output"]) == {"best": stored["best"]}
        and stored["n"] == 4
        and stored["pass"] == "primary",
        str(stored),
    )
    proj = mproj(sc, man, td)
    check(
        "pick: the longest arm alone wins every item -> won 1, the others 0, for both judges and the mean",
        all(
            proj[i][c][k] == (1.0 if c == MIDS[3] else 0.0)
            for i in MITEMS
            for c in MIDS
            for k in ("ja", "jb", "_mean")
        ),
    )
    summ = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), proj, st, "unvalidated judge", False, td)
    pa = summ["per_arm"]
    check(
        "pick summary: judge_won and win_rate per arm; no judge_score (that is grade's)",
        pa[MIDS[3]]["judge_won"] == 1.0
        and pa[MIDS[3]]["win_rate"] == 1.0
        and pa[MIDS[0]]["win_rate"] == 0.0
        and "judge_score" not in pa[MIDS[0]]
        and pa[MIDS[3]]["judge_ja"] == 1.0
        and summ["mode"] == "pick",
    )
    bt = {c: pa[c]["bt_strength"] for c in MIDS}
    check(
        "pick summary: Bradley-Terry puts the winner first, the three losers (never compared with each other) level",
        bt[MIDS[3]] > bt[MIDS[0]] == bt[MIDS[1]] == bt[MIDS[2]] and abs(math.prod(bt.values()) - 1.0) < 1e-4,
        str(bt),
    )
    check(
        "pick summary: identical items give a degenerate interval (every resample is the full sample)",
        all(pa[c]["bt_low"] == pa[c]["bt_strength"] == pa[c]["bt_high"] for c in MIDS),
    )
    check(
        "pick summary: position and noise kept every verdict (the longest wins wherever it sits)",
        all(
            summ["controls"][j][k]["agreement"] == 1.0 and summ["controls"][j][k]["n_verdicts"] == 3
            for j in ("ja", "jb")
            for k in ("position", "noise")
        ),
        str(summ["controls"]),
    )
    check(
        "pick summary: the two judges name the same winner on every item",
        summ["judge_agreement"]["ja~jb"]["winner_agreement"] == 1.0
        and summ["judge_agreement"]["ja~jb"]["n_items"] == 6,
    )
    check(
        "pick summary: 5 sections kept: per_judge counts, controls per judge, bradley_terry method",
        summ["per_judge"]["ja"]["verdicts"] == 12
        and summ["per_judge"]["ja"]["unparsed"] == 0
        and summ["bradley_terry"]["comparisons"] == 6 * 2 * 3
        and summ["bradley_terry"]["resamples"] == js.BT_RESAMPLES,
        str(summ["bradley_terry"]),
    )
    # resume and $0 re-read
    before = {f: f.read_bytes() for f in td.glob("*/*.json")}
    j2 = {"n": 0}

    def counting(m, p):
        j2["n"] += 1
        return judging.call_judge(m, p)

    st2 = mrun(td, sc, man, call=counting)
    check(
        "pick: a second run makes no call and rewrites nothing",
        j2["n"] == 0 and st2["calls"] == 0 and all(f.read_bytes() == b for f, b in before.items()),
    )
    victim_ = next(td.glob("jb/*.primary.b0.json"))
    victim_.unlink()
    st3 = mrun(td, sc, man, call=counting)
    check("pick: one deleted verdict costs exactly one call", st3["calls"] == 1 and j2["n"] == 1)
    check(
        "pick: --no-calls (call=None) re-reads and calls nothing", mrun(td, sc, man, call=None)["calls"] == 0
    )
    again = mproj(sc, man, td)
    check("pick: the re-read projection equals the first", again == proj)
    est = js.estimate(man, sc, PICK_BASE, MARTICLES, m_outputs(), Path(tempfile.mkdtemp(dir=td)))
    check(
        "pick: dry-run counts one call per item, position item and noise item, per judge",
        est["ja"]["calls"] == est["jb"]["calls"] == 12
        and est["ja"]["tokens_in"] > 0
        and est["ja"]["tokens_out"] == 12 * js.OUT_TOKENS_ANSWER,
    )
    check(
        "pick: dry-run does not price what is stored",
        js.estimate(man, sc, PICK_BASE, MARTICLES, m_outputs(), td)["ja"]["calls"] == 0,
    )
    # schema and V11/V12 on what the pass wrote
    vschema = jsonschema.Draft202012Validator(json.loads((SCHEMAS / "verdict.schema.json").read_text()))
    check(
        "verdict schema: stored pick verdicts validate",
        all(vschema.is_valid(json.loads(f.read_text())) for f in td.glob("*/*.json")),
    )
    root_ = Path(tempfile.mkdtemp(dir=td))
    sets_ = root_ / "judging-sets"
    js.freeze(man, sets_)
    vroot_ = root_ / "judge-verdicts" / sc["scorer_id"] / man["judging_set_id"]
    shutil.copytree(td / "ja", vroot_ / "ja")
    shutil.copytree(td / "jb", vroot_ / "jb")
    check(
        "V11 and V12 accept a pick set and its verdicts",
        vt.judging_set_problems(sets_) == [] and vt.verdict_problems(root_ / "judge-verdicts", sets_) == [],
        str(vt.verdict_problems(root_ / "judge-verdicts", sets_)[:2]),
    )

# a shared pick: arms 1 and 2 are the equally longest
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc, outs = mscorer("pick"), m_outputs({0: 3, 1: 4, 2: 4, 3: 1})
    man = mmanifest(sc, outputs=outs)
    st = mrun(td, sc, man, outputs=outs)
    proj = mproj(sc, man, td)
    check(
        "pick: two arms named together share the item: won 1/2 each, 0 for the rest",
        all(proj[i][c]["_mean"] == {MIDS[1]: 0.5, MIDS[2]: 0.5}.get(c, 0.0) for i in MITEMS for c in MIDS),
    )
    stored = json.loads(next(td.glob("ja/*.primary.b0.json")).read_text())
    check("pick: the shared verdict stores both numbers", len(stored["best"]) == 2)
    comps = js.item_comparisons("pick", man["items"][0]["primary"], {0: tuple(sorted(MIDS[1:3]))})
    check(
        "Bradley-Terry input from a shared pick: each named arm beats each unnamed; the named tie",
        sorted(comps)
        == sorted(
            [
                (MIDS[1], MIDS[0], 1.0, 0.0),
                (MIDS[1], MIDS[3], 1.0, 0.0),
                (MIDS[2], MIDS[0], 1.0, 0.0),
                (MIDS[2], MIDS[3], 1.0, 0.0),
                (MIDS[1], MIDS[2], 0.5, 0.5),
            ]
        ),
        str(comps),
    )
    sm = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), proj, st, "unvalidated judge", False, td)
    pa = sm["per_arm"]
    check(
        "shared pick: the tied arms get one strength, above the unnamed arms'",
        pa[MIDS[1]]["bt_strength"]
        == pa[MIDS[2]]["bt_strength"]
        > pa[MIDS[0]]["bt_strength"]
        == pa[MIDS[3]]["bt_strength"],
    )

# a judge with position bias, and two judges that disagree
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc = mscorer("pick", prefer=("longer", "first"))
    man = mmanifest(sc)
    st = mrun(td, sc, man)
    proj = mproj(sc, man, td)
    firsts = {it["item_id"]: it["primary"][0][0] for it in man["items"]}
    check(
        "pick: a judge that always names the first-listed output wins the arm that was listed first",
        all(proj[i][c]["jb"] == (1.0 if c == firsts[i] else 0.0) for i in MITEMS for c in MIDS),
    )
    sm = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), proj, st, "unvalidated judge", False, td)
    held = sum(
        man["items"][int(i[2:])]["primary"][0][0] == man["items"][int(i[2:])]["position"][0][0]
        for i in man["position_items"]
    )
    check(
        "pick: position agreement is the share of re-shuffles whose first-listed arm is unchanged (the biased judge); the content judge keeps all",
        sm["controls"]["jb"]["position"]["kept"] == held
        and sm["controls"]["jb"]["position"]["n_verdicts"] == 3
        and sm["controls"]["ja"]["position"]["agreement"] == 1.0
        and sm["controls"]["jb"]["noise"]["agreement"] == 1.0,
        str(sm["controls"]["jb"]) + f" held={held}",
    )
    expect_agree = sum({MIDS[3]} == {firsts[i]} for i in MITEMS) / len(MITEMS)
    check(
        "pick: inter-judge winner agreement = the share of items where the biased judge's first arm is the longest",
        abs(sm["judge_agreement"]["ja~jb"]["winner_agreement"] - round(expect_agree, 6)) < 1e-9,
    )

# unparsed replies, --retry-unparsed
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc, man = mscorer("pick"), mp_
    reply_budget = {"left": 2}

    def garbage_first(m, p):
        if p["model"] == "m_ja" and reply_budget["left"] > 0:
            reply_budget["left"] -= 1
            return SimpleNamespace(
                output='{"best": [9]}', tokens_in=10, tokens_out=3, cost_usd=0.001, extra={}, meta={}
            )
        return judging.call_judge(m, p)

    st = mrun(td, sc, man, call=garbage_first)
    bad_recs = [f for f in td.glob("ja/*.json") if json.loads(f.read_text())["best"] is None]
    check(
        "pick: an out-of-range pick is stored unparsed (best null), the reply kept",
        len(bad_recs) == 2 and all(json.loads(f.read_text())["output"] == '{"best": [9]}' for f in bad_recs),
    )
    p_unparsed = mproj(sc, man, td)
    check(
        "pick: an item with an unparsed verdict is not projected",
        len(p_unparsed)
        == 6
        - len(
            {
                json.loads(f.read_text())["item_id"]
                for f in bad_recs
                if json.loads(f.read_text())["pass"] == "primary"
            }
        ),
    )
    check("pick: a rerun without --retry-unparsed keeps them", mrun(td, sc, man)["calls"] == 0)
    st_r = mrun(td, sc, man, retry=True)
    check(
        "pick: --retry-unparsed calls again exactly the unparsed ones",
        st_r["calls"] == 2
        and all(json.loads(f.read_text())["best"] is not None for f in td.glob("ja/*.json")),
    )
    smu = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), mproj(sc, man, td), st_r, "x", False, td)
    check("pick: the summary counts no unparsed once retried", smu["per_judge"]["ja"]["unparsed"] == 0)

# cost cap
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)

    def priced(m, p):
        r = judging.call_judge(m, p)
        r.cost_usd = 0.01
        return r

    st = mrun(td, mscorer("pick"), mp_, call=priced, cap=0.055)
    check(
        "pick: the cost cap stops the pass mid-run and keeps what was bought",
        st["aborted"] and st["calls"] == 6 and len(list(td.glob("*/*.json"))) == 6,
    )
    check(
        "pick: a rerun with room finishes only what is missing",
        mrun(td, mscorer("pick"), mp_, call=priced, cap=1.0)["calls"] == 24 - 6,
    )

# ── pairwise, end to end ────────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc, man = mscorer("pairwise"), mw_
    st = mrun(td, sc, man)
    n_tasks = len(js.tasks(man))
    check(
        "pairwise: calls = judges x (36 pairs + 18 position + 18 noise) = 2 x 72",
        st["calls"] == 144 == 2 * n_tasks and not st["aborted"],
    )
    first = man["items"][0]["primary"][0]
    stored = json.loads((td / "ja" / f"{MITEMS[0]}.primary.b0.json").read_text())
    check(
        "pairwise: a verdict stores `better` (1 or 2 = the arm listed first or second), n 2",
        "scores" not in stored
        and stored["better"] == (1 if MIDS.index(first[0]) > MIDS.index(first[1]) else 2)
        and stored["n"] == 2
        and json.loads(stored["output"]) == {"better": stored["better"]},
        str(stored),
    )
    proj = mproj(sc, man, td)
    k_of = {c: k for k, c in enumerate(MIDS)}
    check(
        "pairwise: an arm's won is its share of its 3 pairs it won: 0, 1/3, 2/3, 1 by length",
        all(
            abs(proj[i][c][k] - k_of[c] / 3) < 1e-12
            for i in MITEMS
            for c in MIDS
            for k in ("ja", "jb", "_mean")
        ),
        str({c: proj[MITEMS[0]][c]["_mean"] for c in MIDS}),
    )
    sm = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), proj, st, "unvalidated judge", False, td)
    pa = sm["per_arm"]
    check(
        "pairwise summary: win rate = mean won; Bradley-Terry orders the arms by length, geometric mean 1",
        all(
            abs(pa[c]["win_rate"] - k_of[c] / 3) < 1e-6 and pa[c]["judge_won"] == pa[c]["win_rate"]
            for c in MIDS
        )
        and pa[MIDS[0]]["bt_strength"]
        < pa[MIDS[1]]["bt_strength"]
        < pa[MIDS[2]]["bt_strength"]
        < pa[MIDS[3]]["bt_strength"]
        and abs(math.prod(pa[c]["bt_strength"] for c in MIDS) - 1.0) < 1e-3,
        str({c: pa[c]["bt_strength"] for c in MIDS}),
    )
    check(
        "pairwise summary: every comparison is a pairwise outcome: 6 items x 2 judges x 6 pairs",
        sm["bradley_terry"]["comparisons"] == 72,
    )
    check(
        "pairwise summary: position (swapped pair) and noise (repeat) kept every verdict; judges agree on the winner",
        all(
            sm["controls"][j][k]["agreement"] == 1.0 and sm["controls"][j][k]["n_verdicts"] == 18
            for j in ("ja", "jb")
            for k in ("position", "noise")
        )
        and sm["judge_agreement"]["ja~jb"]["winner_agreement"] == 1.0,
        str(sm["controls"]),
    )
    # resume
    before = {f: f.read_bytes() for f in td.glob("*/*.json")}
    cnt = {"n": 0}

    def counting_pw(m, p):
        cnt["n"] += 1
        return judging.call_judge(m, p)

    check(
        "pairwise: a second run makes no call and rewrites nothing",
        mrun(td, sc, man, call=counting_pw)["calls"] == 0
        and cnt["n"] == 0
        and all(f.read_bytes() == b for f, b in before.items()),
    )
    next(td.glob("ja/*.position.b3.json")).unlink()
    check(
        "pairwise: one deleted verdict costs exactly one call",
        mrun(td, sc, man, call=counting_pw)["calls"] == 1,
    )
    check(
        "pairwise: --no-calls re-reads for $0 and projects the same",
        mrun(td, sc, man, call=None)["calls"] == 0 and mproj(sc, man, td) == proj,
    )
    est = js.estimate(man, sc, PAIR_BASE, MARTICLES, m_outputs(), Path(tempfile.mkdtemp(dir=td)))
    check(
        "pairwise: dry-run counts 72 calls per judge",
        est["ja"]["calls"] == est["jb"]["calls"] == 72,
        str(est["ja"]),
    )
    vschema = jsonschema.Draft202012Validator(json.loads((SCHEMAS / "verdict.schema.json").read_text()))
    check(
        "verdict schema: stored pairwise verdicts validate",
        all(vschema.is_valid(json.loads(f.read_text())) for f in td.glob("*/*.json")),
    )
    root_ = Path(tempfile.mkdtemp(dir=td))
    js.freeze(man, root_ / "judging-sets")
    vroot_ = root_ / "judge-verdicts" / sc["scorer_id"] / man["judging_set_id"]
    shutil.copytree(td / "ja", vroot_ / "ja")
    shutil.copytree(td / "jb", vroot_ / "jb")
    check(
        "V11 and V12 accept a pairwise set (blocks of 2) and its verdicts",
        vt.judging_set_problems(root_ / "judging-sets") == []
        and vt.verdict_problems(root_ / "judge-verdicts", root_ / "judging-sets") == [],
        str(vt.verdict_problems(root_ / "judge-verdicts", root_ / "judging-sets")[:2]),
    )

# pairwise ties, and a judge that is all position bias
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc = mscorer("pairwise", prefer=("longer", "first"))
    outs = m_outputs({1: 1})  # arms 0 and 1 are the same length: their pair is a tie
    man = mmanifest(sc, outputs=outs)
    st = mrun(td, sc, man, outputs=outs)
    proj = mproj(sc, man, td)
    exp_a = {MIDS[0]: 0.5 / 3, MIDS[1]: 0.5 / 3, MIDS[2]: 2 / 3, MIDS[3]: 1.0}
    check(
        "pairwise: a tie counts half to each side: the longer judge's won is exact",
        all(abs(proj[i][c]["ja"] - exp_a[c]) < 1e-12 for i in MITEMS for c in MIDS),
        str({c: proj[MITEMS[0]][c]["ja"] for c in MIDS}),
    )
    firsts_n = {
        i: {c: sum(b[0] == c for b in it["primary"]) for c in MIDS}
        for it in man["items"]
        for i in [it["item_id"]]
    }
    check(
        "pairwise: the first-listed judge's won is the share of pairs in which the arm was listed first",
        all(abs(proj[i][c]["jb"] - firsts_n[i][c] / 3) < 1e-12 for i in MITEMS for c in MIDS),
    )
    sm = js.summarise(man, sc, MARMS, js.load_scores(man, sc, td), proj, st, "unvalidated judge", False, td)
    check(
        "pairwise: the swapped pair flips every verdict of the biased judge (agreement 0) and none of the content judge's, except ties",
        sm["controls"]["jb"]["position"]["agreement"] == 0.0
        and sm["controls"]["jb"]["position"]["kept"] == 0
        and sm["controls"]["jb"]["noise"]["agreement"] == 1.0
        and sm["controls"]["ja"]["position"]["agreement"] == 1.0,
        str(sm["controls"]),
    )
    check(
        'pairwise: the content judge\'s tie is stored as better "tie" and is a tie after the swap',
        any(json.loads(f.read_text())["better"] == "tie" for f in td.glob("ja/*.json")),
    )
    check(
        "pairwise: the judges disagree on some item's winner",
        sm["judge_agreement"]["ja~jb"]["winner_agreement"] < 1.0,
    )
    check(
        "pairwise: the self-family flag and contested use the win rates",
        sm["per_arm"][MIDS[0]]["self_family"] == {"ja": True, "jb": False}
        and all(
            (abs(v["judge_ja"] - v["judge_jb"]) > 0.25) == v["contested"] for v in sm["per_arm"].values()
        ),
    )

# ── Bradley-Terry ────────────────────────────────────────────────────────────────────
r_ = js._bt_solve([[0.0, 3.0], [1.0, 0.0]], [1.0, 1.0])
check(
    "Bradley-Terry: 3 wins to 1 with the half-draw prior fits p0/p1 = (3 + .25)/(1 + .25) = 2.6, geometric mean 1",
    abs(r_[0] / r_[1] - 2.6) < 1e-6 and abs(r_[0] * r_[1] - 1.0) < 1e-9,
    str(r_),
)
cyc = js._bt_solve([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]], [1.0] * 3)
check("Bradley-Terry: a symmetric 3-cycle gives equal strengths", all(abs(x - 1.0) < 1e-9 for x in cyc))
never = js._bt_solve([[0.0, 5.0], [0.0, 0.0]], [1.0, 1.0])
check(
    "Bradley-Terry: an arm that never won has a finite, positive strength (the prior)",
    0 < never[1] < 1 < never[0] < 1e6,
    str(never),
)
mm = js._bt_solve([[0.0, 6.0, 3.0], [2.0, 0.0, 5.0], [4.0, 1.0, 0.0]], [1.0] * 3)
grad = []  # MM's fixed point: each W_i = sum_j n_ij p_i/(p_i + p_j)
w3 = [[0.0, 6.0, 3.0], [2.0, 0.0, 5.0], [4.0, 1.0, 0.0]]
for r_i in range(3):
    n_i = sum(
        (w3[r_i][j] + w3[j][r_i] + js.BT_PRIOR) * mm[r_i] / (mm[r_i] + mm[j]) for j in range(3) if j != r_i
    )
    grad.append(n_i - (sum(w3[r_i]) + 2 * js.BT_PRIOR / 2))
check(
    "Bradley-Terry: the fit solves the likelihood equations (W_i = sum_j n_ij p_i / (p_i + p_j))",
    all(abs(g) < 1e-6 for g in grad),
    str(grad),
)

per_item_v = [[("a", "b", 1.0, 0.0)] * 1 for _ in range(7)] + [[("a", "b", 0.0, 1.0)] for _ in range(3)]
old_res = js.BT_RESAMPLES
js.BT_RESAMPLES = 200
bt1 = js.bradley_terry(["a", "b"], per_item_v, "seed-1")
bt2 = js.bradley_terry(["a", "b"], per_item_v, "seed-1")
bt3 = js.bradley_terry(["a", "b"], per_item_v, "seed-2")
js.BT_RESAMPLES = old_res
check("Bradley-Terry bootstrap: seeded, so a rerun gives the same numbers", bt1 == bt2)
check("Bradley-Terry bootstrap: another seed resamples differently", bt1 != bt3)
check(
    "Bradley-Terry bootstrap: 7 wins in 10 items gives a proper interval around the strength",
    bt1["a"]["low"] < bt1["a"]["strength"] < bt1["a"]["high"]
    and bt1["a"]["strength"] > 1 > bt1["b"]["strength"],
    str(bt1),
)
check(
    "Bradley-Terry bootstrap: the interval is on the strength scale and 95% wide (2.5% - 97.5% quantiles)",
    js._quantile([0.0, 1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    and abs(js._quantile([0.0, 10.0], 0.025) - 0.25) < 1e-12,
)

# ── the projection and the judged runs ───────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    sc, man = mscorer("pick"), mp_
    vdir = td / "v"
    mrun(vdir, sc, man)
    proj = mproj(sc, man, vdir)
    runs = td / "runs"
    arms_d = []
    for a in MARMS:
        d = runs / a["run"]
        d.mkdir(parents=True)
        outs = m_outputs()
        for i in MITEMS:
            _outputs.writer(d).add(i, outs[a["config_id"]][i])
        (d / "predictions.jsonl").write_text(
            "".join(
                json.dumps({"item_id": i, "coverage": 0.3, "cost_usd": 0.001, "latency_ms": 5.0}) + "\n"
                for i in MITEMS
            )
        )
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
        arms_d.append(dict(a, dir=d))
    out = td / "judged" / sc["scorer_id"]
    js.write_scored_runs(man, sc, arms_d, proj, out, "unvalidated judge", False)
    win_dir = out / MARMS[3]["run"]
    rows = [json.loads(x) for x in (win_dir / "predictions.jsonl").read_text().splitlines()]
    mj = json.loads((win_dir / "metrics.json").read_text())
    check(
        "pick judged runs: the primary is judge_won (judge_won_unvalidated while unvalidated), with per-judge columns",
        mj["primary_metric"] == "judge_won_unvalidated"
        and rows[0]["judge_won_unvalidated"] == 1.0
        and {"judge_ja_unvalidated", "judge_jb_unvalidated", "cost_usd"} <= set(rows[0])
        and "judge_score_unvalidated" not in rows[0]
        and mj["scores"]["judge_won_unvalidated"] == 1.0
        and mj["derived"]["with"]["mode"] == "pick",
    )
    js.write_scored_runs(man, sc, arms_d, proj, td / "judged2", "validated judge", True)
    mv = json.loads((td / "judged2" / MARMS[0]["run"] / "metrics.json").read_text())
    check(
        "pick judged runs: validated, the primary is judge_won and a quality metric; a loser scores 0",
        mv["primary_metric"] == "judge_won"
        and mv["scores"]["judge_won"] == 0.0
        and mv["metric_kinds"]["judge_won"] == "quality"
        and mv["metric_kinds"]["judge_ja"] == "quality",
    )
    env_ = dict(os.environ, EVAL_RUNS_DIR=str(td / "judged2"))
    lb_pick = subprocess.run(
        [sys.executable, str(HERE / "leaderboard.py"), "--dataset-id", "ds"],
        cwd=HERE.parent,
        env=env_,
        capture_output=True,
        text=True,
    )
    check(
        "pick judged runs: the leaderboard reads them (exit 0, shows judge_won)",
        lb_pick.returncode == 0 and "judge_won" in lb_pick.stdout,
        (lb_pick.stdout + lb_pick.stderr)[-300:],
    )
    # a grade scorer's judged run carries no mode in its provenance
    gsc = mscorer("grade")
    del gsc["mode"]
    gman = mmanifest(gsc)
    gv = td / "gv"
    mrun(gv, gsc, gman, outputs=m_outputs())
    gproj = js.project(gsc, js.load_scores(gman, gsc, gv), MITEMS)
    js.write_scored_runs(gman, gsc, arms_d, gproj, td / "gjudged", "validated judge", True)
    gm = json.loads((td / "gjudged" / MARMS[0]["run"] / "metrics.json").read_text())
    check(
        "grade judged runs are as before: primary judge_score, no mode in their provenance",
        gm["primary_metric"] == "judge_score" and "mode" not in gm["derived"]["with"],
    )
    gsm = js.summarise(gman, gsc, MARMS, js.load_scores(gman, gsc, gv), gproj, {}, "x", True, gv)
    check(
        "grade summary has none of the modes' keys: no mode, no bradley_terry, no win_rate, no winner_agreement",
        not ({"mode", "bradley_terry"} & set(gsm))
        and not any({"win_rate", "judge_won", "bt_strength"} & set(v) for v in gsm["per_arm"].values())
        and all("winner_agreement" not in v for v in gsm["judge_agreement"].values())
        and "judge_score" in gsm["per_arm"][MIDS[0]],
    )
    gverdict = json.loads(next(gv.glob("ja/*.json")).read_text())
    check(
        "grade verdicts keep `scores` and gain neither `best` nor `better`",
        "scores" in gverdict and "best" not in gverdict and "better" not in gverdict,
    )

# ── the committed grade data is untouched ───────────────────────────────────────────
committed_sets = sorted((HERE.parent / "data" / "judging-sets").glob("*.json"))
check(
    "the committed judging sets still recompute to their stored hashes and ids",
    len(committed_sets) >= 2
    and all(
        js.manifest_hash(json.loads(f.read_text())) == json.loads(f.read_text())["judging_set_sha256"]
        and f.stem.endswith(js.manifest_hash(json.loads(f.read_text()))[:12])
        for f in committed_sets
    ),
)
check(
    "the committed grading sets carry no mode; a pick or pairwise set declares its own",
    all(
        json.loads(f.read_text()).get("mode", "grade") in ("grade", "pick", "pairwise")
        for f in committed_sets
    )
    and all(json.loads(f.read_text()).get("mode") != "grade" for f in committed_sets)
    and sum("mode" not in json.loads(f.read_text()) for f in committed_sets) >= 2,
)
for sid_ in ("judge-summ-v1", "judge-summ-v2"):
    sc_ = js.load_scorer(HERE.parent / "data" / "scorers" / f"{sid_}.yaml")
    sdir_ = next((HERE.parent / "data" / "judge-verdicts" / sid_).iterdir())
    man_ = json.loads((HERE.parent / "data" / "judging-sets" / f"{sdir_.name}.json").read_text())
    old_summ = json.loads((HERE.parent / "data" / "runs-judged" / sid_ / "summary.json").read_text())
    st_ = js.run_judging(man_, sc_, js.prompt_text(sc_), {}, {}, sdir_, None, None, log=lambda *_: None)
    got_ = js.load_scores(man_, sc_, sdir_)
    proj_ = js.project(sc_, got_, [it["item_id"] for it in man_["items"]])
    check(
        f"{sid_}: the committed verdicts re-read for $0 (no call, none missing) and project the items the committed summary scored",
        st_["calls"] == 0 and st_["missing"] == 0 and len(proj_) == old_summ["items_scored"],
        str(st_),
    )
    arms_ = [{"config_id": c, "family": a["family"]} for c, a in old_summ["per_arm"].items()]
    # The outputs' lengths, as judge-score reads them, for each judge's length bias.
    found_ = {a["config_id"]: a for a in js.discover_arms(sc_["dataset_id"], sc_.get("arms_match", ""))}
    ids_ = [it["item_id"] for it in man_["items"]]
    words_ = {
        c: {i: len(t.split()) for i, t in js.read_outputs(found_[c], ids_).items()}
        for c in old_summ["per_arm"]
    }
    new_summ = js.summarise(
        man_,
        sc_,
        arms_,
        got_,
        proj_,
        old_summ["cost"],
        old_summ["label"],
        old_summ["validated"],
        sdir_,
        lengths=words_,
    )
    check(
        f"{sid_}: re-summarising the committed verdicts gives the committed summary.json, key for key",
        new_summ == old_summ,
        str([k for k in old_summ if new_summ.get(k) != old_summ[k]]),
    )

# ── the SummEval adapter: pick and pairwise validation ──────────────────────────────────
gold_ = {d: [float(k % 5) for k in range(16)] for d in ad.DIMS}
gold_["coherence"][7] = 9.0  # mean 3.75: still below the 4.0 of summaries 4, 9, 14
ref_ = json.dumps(gold_)
means_ = ad._expert_means(ref_)
check(
    "adapter: the experts' mean over the four dimensions per summary",
    abs(means_[7] - 3.75) < 1e-12 and means_[4] == 4.0 and means_[0] == 0.0,
)
sp = lambda best: ad.score(json.dumps({"best": best}), ref_)  # noqa: E731
check(
    "adapter pick: a pick among the experts' best (ties form the set) scores 1, chance 3/16",
    sp([5])["top1"] == 1.0
    and sp([10])["top1"] == 1.0
    and sp([15])["top1"] == 1.0
    and sp([5])["top1_chance"] == 0.1875,
    str(sp([5])),
)
check(
    "adapter pick: a pick outside the best set scores 0 (summary 8 is 3.75)",
    sp([8])["top1"] == 0.0 and sp([1])["top1"] == 0.0,
)
check(
    "adapter pick: several named score the share of them that are best",
    sp([5, 8])["top1"] == 0.5 and sp([5, 10, 15])["top1"] == 1.0 and sp([1, 5, 8, 2])["top1"] == 0.25,
)
check(
    "adapter pick: not a valid pick (out of range, repeat, null) scores 0 and parsed 0, with the chance beside it",
    all(
        ad.score(json.dumps({"best": b}), ref_) == {"parsed": 0.0, "top1": 0.0, "top1_chance": 0.1875}
        for b in (None, [], [17], [0], [2, 2], "3")
    ),
)
check(
    "adapter pick: without a reference only `parsed` is reported",
    ad.score('{"best": [3]}', None) == {"parsed": 1.0},
)
pairs_out = lambda *ps: json.dumps({"pairs": [{"a": a, "b": b, "better": v} for a, b, v in ps]})  # noqa: E731
sw = lambda *ps: ad.score(pairs_out(*ps), ref_)  # noqa: E731
# summaries 4 (mean 4.0) and 0 (0.0): experts prefer 4. shown (a=4, b=0): 1 prefers a.
check(
    "adapter pairwise: the judge preferring the expert-preferred summary scores 1, either way round",
    sw((4, 0, 1))["pair_agreement"] == 1.0 and sw((0, 4, 2))["pair_agreement"] == 1.0,
)
check(
    "adapter pairwise: the opposite scores 0",
    sw((4, 0, 2))["pair_agreement"] == 0.0 and sw((0, 4, 1))["pair_agreement"] == 0.0,
)
check("adapter pairwise: a tie counts half", sw((4, 0, "tie"))["pair_agreement"] == 0.5)
check(
    "adapter pairwise: a pair the experts tie (summaries 4 and 9 are both 4.0) is left out; n_pairs counts the rest",
    sw((4, 9, 1), (4, 0, 1)) == {"parsed": 1.0, "pair_agreement": 1.0, "n_pairs": 1.0},
    str(sw((4, 9, 1), (4, 0, 1))),
)
check(
    "adapter pairwise: an unreadable answer scores 0 and lowers `parsed`",
    sw((4, 0, 1), (3, 1, None)) == {"parsed": 0.5, "pair_agreement": 0.5, "n_pairs": 2.0},
    str(sw((4, 0, 1), (3, 1, None))),
)
check(
    "adapter pairwise: an article with no pair the experts rank apart scores the 0.5 chance with n_pairs 0",
    sw((4, 9, 1)) == {"parsed": 1.0, "pair_agreement": 0.5, "n_pairs": 0.0},
)
grade_reply = json.dumps({d: [float(k + 1) for k in range(16)] for d in ad.DIMS})
check(
    "adapter grade scoring is untouched: an ordered reply against ordered gold is tau 1, no pick or pair keys",
    ad.score(grade_reply, json.dumps({d: [float(k) for k in range(16)] for d in ad.DIMS}))["tau"] == 1.0
    and "top1" not in ad.score(grade_reply, ref_)
    and "pair_agreement" not in ad.score(grade_reply, ref_),
)
ad_text = json.dumps(
    {"article": "An article.", "summaries": [f"summary {k}" for k in range(16)], "references": ["r"]}
)
ad_item2 = json.loads(ad_text)
p1_, p2_ = ad._pairs(ad_item2, {}), ad._pairs(ad_item2, {})
check(
    "adapter pairs: 8 distinct pairs of the 16, deterministic, the same for every arm (the seed is the article's)",
    p1_ == p2_
    and len(p1_) == 8
    and len({frozenset(p) for p in p1_}) == 8
    and all(a != b and 0 <= a < 16 and 0 <= b < 16 for a, b in p1_),
)
check(
    "adapter pairs: another article, another seed or another pairs_per_item gives another sample; the orientation varies",
    ad._pairs({**ad_item2, "article": "Another."}, {}) != p1_
    and ad._pairs(ad_item2, {"pair_seed": 1}) != p1_
    and len(ad._pairs(ad_item2, {"pairs_per_item": 3})) == 3
    and len({a < b for a, b in ad._pairs(ad_item2, {"pairs_per_item": 100})}) == 2,
)
check(
    "adapter pairs: pairs_per_item must be a whole number from 1 to 120",
    all(
        raises_exit(lambda v=v: ad._pairs(ad_item2, {"pairs_per_item": v})) for v in (0, 121, 2.5, "8", True)
    ),
)
r_pick = [ad.call_system(ad_text, {"provider": "random", "mode": "pick", "seed": s}) for s in range(300)]
tops = [ad.score(r.output, ref_) for r in r_pick]
check(
    "adapter random floor, pick: a valid pick every time, cost 0, top1 near its chance (3/16)",
    all(t["parsed"] == 1.0 for t in tops)
    and 0.10 < sum(t["top1"] for t in tops) / 300 < 0.27
    and all(r.cost_usd == 0.0 for r in r_pick),
    str(sum(t["top1"] for t in tops) / 300),
)
r_pw = [ad.call_system(ad_text, {"provider": "random", "mode": "pairwise", "seed": s}) for s in range(300)]
pas = [ad.score(r.output, ref_)["pair_agreement"] for r in r_pw]
check(
    "adapter random floor, pairwise: 8 pairs, the same pairs for every seed, pair_agreement near 0.5",
    all(len(json.loads(r.output)["pairs"]) == 8 for r in r_pw)
    and len({tuple((p["a"], p["b"]) for p in json.loads(r.output)["pairs"]) for r in r_pw}) == 1
    and 0.40 < sum(pas) / 300 < 0.60,
    str(sum(pas) / 300),
)
check(
    "adapter random floor: seeded, so a rerun is identical",
    ad.call_system(ad_text, {"provider": "random", "mode": "pick", "seed": 5}).output == r_pick[5].output,
)
grade_rand = ad.call_system(ad_text, {"provider": "random", "seed": 5})
check(
    "adapter random floor in grade mode is unchanged: 4 dimensions x 16 integers 1..5",
    sorted(json.loads(grade_rand.output)) == sorted(ad.DIMS)
    and all(len(v) == 16 and all(1 <= x <= 5 for x in v) for v in json.loads(grade_rand.output).values()),
)
check(
    "adapter: mode on a provider that cannot pick (rouge) is refused; an unknown mode too",
    raises_exit(lambda: ad.call_system(ad_text, {"provider": "rouge", "mode": "pick"}))
    and raises_exit(lambda: ad.call_system(ad_text, {"provider": "random", "mode": "tournament"})),
)
fp_pick = ad.fingerprint({"provider": "random", "mode": "pick"})
check(
    "adapter fingerprint: the random floor in pick mode records its mode and a code hash that is not grade's",
    fp_pick["mode"] == "pick"
    and fp_pick["code_sha256"] != ad.fingerprint({"provider": "random"})["code_sha256"]
    and "mode" not in ad.fingerprint({"provider": "random"}),
)
check(
    "adapter: pick and pairwise outputs are canonical JSON even when the judge's reply is not",
    json.loads(ad._pick_output("I think 3."))["best"] is None
    and json.loads(ad._pick_output("I think 3."))["reply"] == "I think 3."
    and json.loads(ad._pick_output('Sure: {"best": [3]}')) == {"best": [3]}
    and ad.score(ad._pick_output("I think 3."), ref_)["parsed"] == 0.0,
)
check(
    "adapter: the metrics are classified (top1 and pair_agreement quality; top1_chance and n_pairs descriptive) and described",
    ad.METRIC_KINDS["top1"] == ad.METRIC_KINDS["pair_agreement"] == "quality"
    and ad.METRIC_KINDS["top1_chance"] == ad.METRIC_KINDS["n_pairs"] == "descriptive"
    and all(k in ad.METRIC_DESCRIPTIONS for k in ("top1", "top1_chance", "pair_agreement", "n_pairs")),
)
chat_calls: list = []


def fake_chat(content, params):
    chat_calls.append(content)
    reply = '{"best": [3]}' if '"best"' in content.rsplit("\n", 1)[-1] else '{"better": 2}'
    return ad.Result(
        output=reply,
        tokens_in=10,
        tokens_out=3,
        cost_usd=0.001,
        extra={"truncated": 0.0},
        meta={"finish_reason": "stop"},
    )


real_chat, ad._chat = ad._chat, fake_chat
try:
    res_pick = ad._litellm(ad_text, {"mode": "pick", "prompt": PICK_BASE})
    n_pick, chat_calls[:] = len(chat_calls), []
    res_pair = ad._litellm(ad_text, {"mode": "pairwise", "prompt": PAIR_BASE})
    n_pair = len(chat_calls)
    res_grade = ad._litellm(ad_text, {"prompt": "grade it"})
finally:
    ad._chat = real_chat
check(
    "adapter judge, pick: one call; the output is the canonical pick",
    n_pick == 1 and json.loads(res_pick.output) == {"best": [3]} and res_pick.cost_usd == 0.001,
)
check(
    "adapter judge, pairwise: one call per sampled pair (8), tokens and cost summed, a verdict per pair",
    n_pair == 8
    and res_pair.tokens_in == 80
    and res_pair.tokens_out == 24
    and abs(res_pair.cost_usd - 0.008) < 1e-12
    and [(p["a"], p["b"]) for p in json.loads(res_pair.output)["pairs"]] == ad._pairs(ad_item2, {})
    and all(p["better"] == 2 for p in json.loads(res_pair.output)["pairs"]),
)
from evaluation_harness.run import _unreachable  # noqa: E402

# The first paid pairwise validation (2026-11-02) stopped before its first item: the merged result's
# meta["calls"] was the number of calls, and `evh run` reads that key as a list of call records.
check(
    "adapter judge, pairwise: meta follows the run's contract (calls a list of records, finish_reason a string)",
    isinstance(res_pair.meta["calls"], list)
    and len(res_pair.meta["calls"]) == 8
    and res_pair.meta["finish_reason"] == "stop"
    and _unreachable(res_pair) is None,
    str(res_pair.meta)[:300],
)
_pick_file = (
    (HERE.parents[1] / "examples" / "summeval-judging" / "prompt_pick.txt")
    .read_text(encoding="utf-8")
    .strip()
)
_pair_file = (
    (HERE.parents[1] / "examples" / "summeval-judging" / "prompt_pairwise.txt")
    .read_text(encoding="utf-8")
    .strip()
)
check(
    "the pick and pairwise messages the harness sends equal the validation arm's, byte for byte (as grading's at 16)",
    js.build_pick_message(_pick_file, ad_item2["article"].strip(), [s.strip() for s in ad_item2["summaries"]])
    == ad._pick_message(ad_item2, {"prompt_file": "prompt_pick.txt"})
    and js.build_pairwise_message(
        _pair_file,
        ad_item2["article"].strip(),
        [ad_item2["summaries"][3].strip(), ad_item2["summaries"][9].strip()],
    )
    == ad._pair_message(ad_item2, 3, 9, {"prompt_file": "prompt_pairwise.txt"}),
)
check(
    "adapter judge, grade: the message is _judge_message's and the reply passes through unchanged",
    chat_calls[-1] == ad._judge_message(ad_item2, {"prompt": "grade it"})
    and res_grade.output == '{"better": 2}',
)
# Answer first (owner, 2026-11-02): qwen_s wrote its analysis before the JSON and was cut at max_tokens on 8-13%
# of the validation's pick replies. The JSON begins the reply now; the explanation after it may hold braces, or be
# cut off, and the verdict still reads.
_first = '{"best": [3, 7]}\nBecause summary 3 keeps {the key facts} and 7 ties with it; summary 12'
_pair_first = '{"better": 2}\nSummary 2 says {"who": "the council"}, and summary 1'
check(
    "pick and pairwise replies: the first JSON object is the verdict, whatever follows it (both sides read it so)",
    js.parse_pick(_first, 16) == [3, 7]
    and ad._read_pick(_first) == [3, 7]
    and js.parse_pairwise(_pair_first) == 2
    and ad._read_better(_pair_first) == 2
    and js.parse_pick("I think summary 3 is the best.", 16) is None,
)
check(
    "the pick and pairwise prompts ask for the JSON first and nothing after it",
    all("Begin your reply with" in t and "nothing after it" in t for t in (_pick_file, _pair_file))
    and "Begin your reply with the JSON object" in judging.PICK_REMINDER
    and "Begin your reply with the JSON object" in judging.PAIR_REMINDER,
)

sys.exit(summary())
