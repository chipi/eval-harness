#!/usr/bin/env python3
"""A judge reply that is empty or cut off: stored the way V12 requires, said why, hinted.

    python tests/test_judge_replies.py

No network, no key, no money: a fake judge that answers nothing at finish_reason "length"
(a reasoning model that spent its max_tokens thinking), cut-off JSON, prose, and the right JSON.
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package

from evaluation_harness import judge_score as js
from evaluation_harness import validate_tree as vt
from evaluation_harness._check import check, summary

ITEMS = ["itemA"]
ARMS: list[dict[str, Any]] = [
    {"config_id": f"arm{k}_v1", "run": f"arm{k}_v1_2026", "dir": None, "family": "x"} for k in range(3)
]
ARTICLES = {"itemA": "Article text for itemA. It is long enough to be an article."}
OUTPUTS: dict[str, dict[str, str]] = {
    str(a["config_id"]): {"itemA": f"summary {k} about itemA"} for k, a in enumerate(ARMS)
}


def scorer(max_tokens=400, **over):
    params = {"model": "m_a", "family": "gemma", "max_tokens": max_tokens}
    sc = {
        "scorer_id": "judge-test-v1",
        "kind": "judge",
        "dataset_id": "ds",
        "_sha256": "0" * 64,
        "cost_cap_usd": 1.0,
        "judges": [{"id": "ja", "params": params}],
        "prompt": {"file": "examples/summeval-judging/prompt.txt"},
        "protocol": {
            "outputs_per_call": 16,
            "blinding": True,
            "order_seed": 0,
            "position_check_fraction": 0.0,
            "noise_check_fraction": 0.0,
            "contested_threshold": 0.5,
        },
    }
    sc.update(over)
    return sc


SC = scorer()
BASE = js.prompt_text(SC)
M = js.build_manifest(SC, "ds", "i" * 64, ITEMS, ARMS, ARTICLES, OUTPUTS, BASE)


def judge(output, finish="length", tokens_out=400):
    def call(message, params):
        return SimpleNamespace(
            output=output,
            tokens_in=100,
            tokens_out=tokens_out,
            cost_usd=0.01,
            latency_ms=1.0,
            extra={"truncated": 1.0 if finish == "length" else 0.0},
            meta={"finish_reason": finish, "provider": "fake", "response_model": "m_a"},
        )

    return call


def run(td, call, sc=SC, retry=False):
    logs: list[str] = []
    st = js.run_judging(
        M, sc, BASE, ARTICLES, OUTPUTS, Path(td), call, None, retry_unparsed=retry, log=logs.append
    )
    return st, logs


def only_record(td):
    recs = sorted(Path(td).glob("ja/*.json"))
    return recs, [json.loads(r.read_text()) for r in recs]


# 1. An empty reply at the token limit is withheld like any other unparsed reply, and V12 passes.
with tempfile.TemporaryDirectory() as tmp:
    st, logs = run(tmp, judge("", "length", 400))
    recs, vs = only_record(tmp)
    v = vs[0]
    check(
        "empty reply at finish_reason length: stored withheld, hash kept, never output ''",
        v["output"] is None
        and v["output_withheld"] is True
        and len(v["output_sha256"]) == 64
        and v["finish_reason"] == "length",
    )
    check("empty reply: the record says why it was withheld", v.get("withheld_reason") == "empty reply")
    check(
        "empty reply: V12's reply check accepts the stored record",
        all(vt.reply_problems(x) == [] for x in vs),
    )
    check(
        "empty reply: a record committed the old way (output '') is still a V12 failure",
        len(vt.reply_problems({**v, "output": "", "output_withheld": False})) == 1,
    )

    # 2. Each unparsed line says why, with the character count.
    lines = [x for x in logs if "unparsed reply" in x]
    check(
        "unparsed line: empty and cut off at the token limit, with 0 chars",
        lines
        and all(
            "empty" in x and "cut off at the token limit (finish_reason length)" in x and "0 chars" in x
            for x in lines
        ),
    )

    # 3. One hint line at the end: the share cut off, and both fixes.
    hints = [
        x
        for x in logs
        if "cut off at the token limit" in x and "max_tokens" in x and "unparsed reply" not in x
    ]
    check("hint: exactly one line", len(hints) == 1)
    h = hints[0] if hints else ""
    check(
        "hint: the share cut off (all of them), the limit, both fixes",
        f"{st['calls']} of {st['calls']}" in h
        and "100%" in h
        and "max_tokens" in h
        and "400" in h
        and "reasoning: {enabled: false}" in h
        and "new scorer" in h,
    )

# Other causes, each named with its characters.
cases = [
    (
        "cut-off JSON at the limit",
        judge('{"best": [1,', "length", 400),
        ("cut off at the token limit", "12 chars"),
    ),
    ("prose", judge("I cannot do this.", "stop", 5), ("not JSON", "17 chars")),
    ("empty, no limit hit", judge("", "stop", 0), ("empty", "finish_reason stop", "0 chars")),
    ("JSON of the wrong shape", judge('{"foo": 1}', "stop", 5), ("JSON", "not the expected", "10 chars")),
]
for name, call, needles in cases:
    with tempfile.TemporaryDirectory() as tmp:
        st, logs = run(tmp, call)
        lines = [x for x in logs if "unparsed reply" in x]
        check(f"unparsed line, {name}: {' / '.join(needles)}", lines and all(n in lines[0] for n in needles))
        hint = [x for x in logs if "unparsed reply" not in x and "raise" in x]
        if name.startswith("cut-off JSON"):
            check("no hint for cut-off replies that are not empty", not hint)

# A reply that parses prints no unparsed line and no hint.
good = json.dumps(
    {"coherence": [3, 3, 3], "consistency": [3, 3, 3], "fluency": [3, 3, 3], "relevance": [3, 3, 3]}
)
with tempfile.TemporaryDirectory() as tmp:
    st, logs = run(tmp, judge(good, "stop", 20))
    check(
        "a good reply: no unparsed line, no hint", not any("unparsed" in x or "max_tokens" in x for x in logs)
    )
    recs, vs = only_record(tmp)
    check("a good reply is stored as text", vs[0]["output"] == good and vs[0]["output_withheld"] is False)

# 1b. Recovery: --retry-unparsed rewrites an old-style record (output '') and V12 then passes.
with tempfile.TemporaryDirectory() as tmp:
    run(tmp, judge("", "length", 400))
    recs, vs = only_record(tmp)
    old = {**vs[0], "output": "", "output_withheld": False}
    old.pop("withheld_reason", None)
    recs[0].write_text(json.dumps(old))
    check("recovery setup: the old-style record fails V12", vt.reply_problems(old) != [])
    st, _ = run(tmp, judge(good, "stop", 20), retry=True)
    _, vs = only_record(tmp)
    check(
        "recovery: --retry-unparsed rewrites the old record; its cost stays, V12 passes",
        st["calls"] == 1 and vs[0]["scores"] is not None and vt.reply_problems(vs[0]) == [],
    )

# A judge that runs out on every reply is stopped after its first EARLY_CUTOFF calls, not after the whole pass
# (the 0.7.1 newcomer run: a thinking judge at max_tokens 400 was found only after paying for every call).
MANY = [f"item{k}" for k in range(6)]
ARTS6 = {i: ARTICLES["itemA"] + i for i in MANY}
OUTS6 = {c: {i: f"{v['itemA']} {i}" for i in MANY} for c, v in OUTPUTS.items()}
M6 = js.build_manifest(SC, "ds", "j" * 64, MANY, ARMS, ARTS6, OUTS6, BASE)


def run6(td, call):
    logs: list[str] = []
    st = js.run_judging(M6, SC, BASE, ARTS6, OUTS6, Path(td), call, None, log=logs.append)
    return st, logs


with tempfile.TemporaryDirectory() as tmp:
    st, logs = run6(tmp, judge("", "length", 400))
    check(
        f"a judge empty at the token limit on its first {js.EARLY_CUTOFF} replies: the pass stops there, kept, hinted",
        st["calls"] == js.EARLY_CUTOFF
        and st.get("aborted")
        and any("STOPPED EARLY" in x for x in logs)
        and any("HINT" in x and "max_tokens" in x for x in logs)
        and len(list(Path(tmp).glob("ja/*.json"))) == js.EARLY_CUTOFF,
        (st.get("calls"), logs[-3:]),
    )
replies = iter([good] + [""] * 20)


def first_good(message, params):
    out = next(replies)
    return judge(out, "stop" if out else "length", 20 if out else 400)(message, params)


with tempfile.TemporaryDirectory() as tmp:
    st, logs = run6(tmp, first_good)
    check(
        "a judge whose first reply parsed is not stopped early: the pass runs to the end",
        st["calls"] == len(MANY) and not st.get("cut_off_early"),
        (st.get("calls"), st.get("cut_off_early")),
    )

# The V12 failure names the command that fixes it.
msg = vt.reply_problems(
    {"output": "", "output_sha256": "x"}, fix="evh judge-score --dataset-id ds --scorer s --retry-unparsed"
)
check(
    "V12 message names the exact recovery command",
    len(msg) == 1
    and "not bare JSON (0 chars)" in msg[0]
    and "evh judge-score --dataset-id ds --scorer s --retry-unparsed" in msg[0],
)

# The scorer's `reasoning` key reaches the request body of an OpenAI-shaped provider.
from evaluation_harness import _providers as prov  # noqa: E402

check(
    "reasoning: the scorer's `reasoning` param is passed through on the wire",
    prov._BODY_PARAMS.get("reasoning") == "reasoning",
)

sys.exit(summary())
