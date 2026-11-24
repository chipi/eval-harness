#!/usr/bin/env python3
"""`evh judge-validate` (RFC-038 section 3): a judge measured against people's ratings, as ordinary runs.

    python tests/test_judge_validate.py

In a throwaway project, with a scripted judge (nothing is called, nothing is paid):

- the core adapter sends the message `judge-score` sends (byte for byte, in each mode), maps each reply back to the item's
  own order, scores tau, top1 or pair agreement against the ratings, and keeps no reply text;
- the command runs each judge of a scorer and a seeded random floor as runs of systems it writes, prints the block the
  gate reads, and with --fill writes it through the scorer's own operation, after which the gate's `validation_problems`
  is empty (grade, pick and pairwise);
- every refusal of section 3.5 happens before a call is made, and the dry run calls nothing.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-judge-validate-"))
os.environ.setdefault("EVAL_STORE", "files")
os.environ.update(
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-judge-validate",
    EVH_ACTOR="person:tester",
    OPENAI_API_KEY="test-not-a-key",
    OPENROUTER_API_KEY="test-not-a-key",
)
for k in (
    "EVAL_DATA_DIR",
    "EVAL_GOALS_DIR",
    "EVAL_MAX_COST_USD",
    "EVAL_JUDGE_MAX_COST_USD",
    "EVAL_JUDGE_OPENAI_API_KEY",
):
    os.environ.pop(k, None)

import _cli  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as _model_runs  # noqa: E402

ENV = dict(os.environ)
TASK = {
    "source_label": "TICKET",
    "output_label": "REPLIES",
    "dimensions": ["accuracy", "usefulness"],
    "scale": [1, 5],
}
PROMPT = (
    "You are checking replies to a customer ticket. Read the ticket, then rate each of the {n} numbered replies on\n"
    'accuracy and usefulness, from 1 to 5. Reply with JSON only: {"accuracy": [...], "usefulness": [...]}'
)
# four outputs per item; an output's length in words is what the scripted judge, and the ratings, go by
LENGTHS = [[1, 2, 3, 4], [4, 1, 3, 2], [2, 4, 1, 3], [3, 1, 4, 2], [1, 3, 2, 4]]
PA = {"provider": "openai", "model": "m-good", "family": "a", "temperature": 0.0, "usd_per_mtok_in": 1.0,
      "usd_per_mtok_out": 1.0, "max_tokens": 400}  # fmt: skip
PB = {"provider": "openrouter", "model": "m-bad", "family": "b", "temperature": 0.0, "usd_per_mtok_in": 1.0,
      "usd_per_mtok_out": 1.0, "max_tokens": 400}  # fmt: skip


def evh(*args):
    return _cli.run(proj, ENV, *args)


def out(r):
    return r.stdout + r.stderr


def attempt(label, fn, detail=None):
    """One check whose body may raise (the code under test does not exist yet): a raise is a failed check."""
    try:
        got = fn()
    except SystemExit as exc:
        return check(label, False, f"exit {exc.code!r}")
    except Exception as exc:  # noqa: BLE001
        return check(label, False, f"{type(exc).__name__}: {exc}")
    return check(label, got, detail() if callable(detail) else detail)


def refusal(fn):
    """The message of the SystemExit fn raises, or '' when it does not (or raises something else)."""
    try:
        fn()
    except SystemExit as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001
        return f"RAISED {type(exc).__name__}: {exc}"
    return ""


def item_json(i):
    return {
        "source": f"Ticket {i}a: the customer cannot export a report.",
        "outputs": [" ".join(f"w{i}{k}" for k in range(n)) for k, n in enumerate(LENGTHS[i])],
    }


def reference_json(i):
    by_len = [float(n) for n in LENGTHS[i]]
    swapped = list(by_len)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    return {
        "ratings": {"accuracy": by_len, "usefulness": by_len},
        "raters": [
            {"accuracy": by_len, "usefulness": by_len},
            {"accuracy": by_len, "usefulness": by_len},
            {"accuracy": swapped, "usefulness": swapped},
        ],
    }


SOURCE_PY = f"""
import json

LENGTHS = {LENGTHS!r}


class Source:
    def __init__(self, options):
        self.options = options

    def describe(self, query):
        return {{"source": {{"provider": "test"}}}}

    def items(self, query):
        for i, lengths in enumerate(LENGTHS):
            src = f"Ticket {{i}}a: the customer cannot export a report."
            outs = [" ".join(f"w{{i}}{{k}}" for k in range(n)) for k, n in enumerate(lengths)]
            by_len = [float(n) for n in lengths]
            swapped = list(by_len)
            swapped[0], swapped[1] = swapped[1], swapped[0]
            ans = {{"ratings": {{"accuracy": by_len, "usefulness": by_len}},
                    "raters": [{{"accuracy": by_len, "usefulness": by_len}}, {{"accuracy": by_len, "usefulness": by_len}},
                               {{"accuracy": swapped, "usefulness": swapped}}]}}
            yield {{"item_id": f"r{{i}}", "text": json.dumps({{"source": src, "outputs": outs}}), "answer": json.dumps(ans)}}
"""


def write(rel, text):
    _runstore.write_text(proj, rel, text)


def scorer(sid, mode="grade", outputs_per_call=2, explain=False, judges=None, **more):
    doc = {
        "scorer_id": sid, "kind": "judge", "dataset_id": "judged_v1", "mode": mode, "explain": explain, "task": TASK,
        "prompt": {"file": "judge_prompt.txt"},
        "protocol": {"outputs_per_call": outputs_per_call, "blinding": True, "order_seed": 0,
                     "position_check_fraction": 0.5, "noise_check_fraction": 0.5},
        "judges": judges or [{"id": "ja", "params": PA}, {"id": "jb", "params": PB}],
        "cost_cap_usd": 1.0, **more,
    }  # fmt: skip
    write(f"scorers/{sid}.yaml", yaml.safe_dump(doc, sort_keys=False))
    return proj / "data" / "scorers" / f"{sid}.yaml"


CALLS: list[str] = []


def scripted(message, params):
    """The judge by its model's name: m-good prefers the longer reply, m-bad the shorter, as the ratings do and do not."""
    from evaluation_harness.judging import JudgeResult  # noqa: PLC0415

    CALLS.append(message)
    shown = [
        ln.split(". ", 1)[1]
        for ln in message.rsplit("REPLIES:\n", 1)[1].split("\n\n")[0].split("\n")
        if ". " in ln
    ]
    n = [len(s.split()) for s in shown]
    good = params["model"] == "m-good"
    pref = n if good else [-x for x in n]
    if "BADREPLY" in os.environ.get("JV_MODE", "") and not good:
        text = "I would rather not say."
    elif '{"better": 1}' in message:
        text = json.dumps({"better": "tie" if pref[0] == pref[1] else (1 if pref[0] > pref[1] else 2)})
    elif '{"best": [3]}' in message:
        top = max(pref)
        text = json.dumps({"best": [i + 1 for i, v in enumerate(pref) if v == top]})
    else:
        score = [max(1, min(5, v)) if good else max(1, min(5, 5 - v)) for v in n]
        text = json.dumps({"accuracy": score, "usefulness": score})
    return JudgeResult(output=text, tokens_in=100, tokens_out=20, cost_usd=0.001, extra={"truncated": 0.0},
                       meta={"finish_reason": "stop", "provider": params["provider"], "response_model": params["model"]})  # fmt: skip


def run_cmd(**inputs):
    """judge-validate's body in this process: (exit code, what it printed, the message of a refusal)."""
    from evaluation_harness import judge_validate as jv  # noqa: PLC0415

    buf = io.StringIO()
    code, why = 0, ""
    with contextlib.redirect_stdout(buf):
        try:
            code = jv.body(**inputs)
        except SystemExit as exc:
            code, why = 1, str(exc.code)
    return code, buf.getvalue(), why


try:
    # ── the project: a rated dataset, a plain one, prompts, scorers ──────────────────────────────────────────────────
    data = proj / "data"
    if not _runstore.sqlite():
        (data / "systems").mkdir(parents=True)
    write(_format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "judge_prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    (proj / "rated_source.py").write_text(SOURCE_PY, encoding="utf-8")
    r = evh(
        "dataset-create",
        "--dataset-id",
        "rated_v1",
        "--source",
        "rated_source.py:Source",
        "--query",
        '{"answer": "answer"}',
    )
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "rated_v1")
    r = r if r.returncode else evh("reference-promote", "--dataset-id", "rated_v1", "--labels", "answers", "--tier", "gold",
                                   "--reason", "people rated them", "--by", "tester")  # fmt: skip
    check("setup: a rated dataset with its ratings as the gold reference", r.returncode == 0, out(r)[-400:])
    (proj / "plain").mkdir()
    for i in range(3):
        (proj / "plain" / f"p{i}.txt").write_text(f"plain text {i}\n", encoding="utf-8")
    # the people rated one of the scorer's two dimensions only (Zhang's raters did not rate fluency)
    (proj / "rated_sub_source.py").write_text(
        "import json\n\nLENGTHS = "
        + repr(LENGTHS)
        + "\n\n\nclass Source:\n    def __init__(self, options):\n        pass\n\n"
        "    def describe(self, query):\n        return {'source': {'provider': 'test'}}\n\n"
        "    def items(self, query):\n        for i, lens in enumerate(LENGTHS):\n"
        "            outs = [' '.join(f'w{i}{k}' for k in range(n)) for k, n in enumerate(lens)]\n"
        "            r = {'accuracy': [float(n) for n in lens]}\n"
        "            yield {'item_id': f'r{i}', 'text': json.dumps({'source': f'Ticket {i}a: the customer cannot export a report.', 'outputs': outs}),\n"
        "                   'answer': json.dumps({'ratings': r, 'raters': [r, r]})}\n",
        encoding="utf-8",
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "rated_sub_v1",
        "--source",
        "rated_sub_source.py:Source",
        "--query",
        '{"answer": "answer"}',
    )
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "rated_sub_v1")
    r = r if r.returncode else evh("reference-promote", "--dataset-id", "rated_sub_v1", "--labels", "answers", "--tier", "gold", "--reason", "people rated one dimension", "--by", "tester")  # fmt: skip
    check(
        "setup: a rated dataset whose ratings carry one of the scorer's two dimensions",
        r.returncode == 0,
        out(r)[-400:],
    )
    r = evh("dataset-create", "--dataset-id", "plain_v1", "--source-dir", "plain")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "plain_v1")
    check("setup: a plain dataset that is not rated", r.returncode == 0, out(r)[-400:])
    sc_grade, sc_pick, sc_pair = (
        scorer("vj_grade_v1"),
        scorer("vj_pick_v1", "pick", 4),
        scorer("vj_pair_v1", "pairwise", 2),
    )

    import evaluation_harness.judging as judging

    judging.call_judge = scripted  # the whole suite pays nothing
    from evaluation_harness import judge_score as js

    # ── the adapter ───────────────────────────────────────────────────────────────────────────────────────────────────
    def adapter():
        from evaluation_harness import judge_validation as jva  # noqa: PLC0415

        return jva

    def jparams(mode="grade", **more):
        return {**PA, "mode": mode, "explain": False, "outputs_per_call": 2, "order_seed": 0, "task": TASK,
                "prompt_path": "judge_prompt.txt", "prompt_file": "judge_prompt.txt", **more}  # fmt: skip

    item0 = json.dumps(item_json(0))
    ref0 = json.dumps(reference_json(0))

    def grade_scores():
        CALLS.clear()
        res = adapter().call_system(item0, jparams())
        o = json.loads(res.output)
        want = [float(n) for n in LENGTHS[0]]
        return (
            len(CALLS) == 2
            and o["scores"]["accuracy"] == want
            and o["scores"]["usefulness"] == want
            and res.cost_usd == 0.002
            and res.tokens_in == 200
        )

    attempt(
        "adapter, grade: two blocks of two outputs, each reply mapped back to the item's own order",
        grade_scores,
    )

    def blocks_are_blinded():
        CALLS.clear()
        adapter().call_system(item0, jparams())
        shown = [
            [ln.split(". ", 1)[1] for ln in m.rsplit("REPLIES:\n", 1)[1].split("\n") if ". " in ln]
            for m in CALLS
        ]
        flat = [s for blk in shown for s in blk]
        return sorted(flat) == sorted(item_json(0)["outputs"]) and flat != item_json(0)["outputs"]

    attempt(
        "adapter, grade: the outputs are shown in a seeded order that is not the item's", blocks_are_blinded
    )

    def original_order():
        CALLS.clear()
        adapter().call_system(item0, jparams(outputs_per_call=4, order="original"))
        shown = [ln.split(". ", 1)[1] for ln in CALLS[0].rsplit("REPLIES:\n", 1)[1].split("\n") if ". " in ln]
        refused = refusal(lambda: adapter().call_system(item0, jparams(order="sideways")))
        return shown == item_json(0)["outputs"] and "order" in refused, (shown, refused)

    attempt(
        "adapter: `order: original` shows the outputs as the item has them (the default is the blinded, seeded order); another word is refused",
        lambda: original_order()[0],
        lambda: original_order()[1],
    )

    def message_equals_judge_score():
        from evaluation_harness import judging as j  # noqa: PLC0415

        base = js.prompt_text(js.load_scorer(sc_grade))
        item = item_json(0)
        order = [2, 0, 3, 1]
        shown = [item["outputs"][i] for i in order]
        results = []
        for mode, explain in (
            ("grade", False),
            ("grade", True),
            ("pick", False),
            ("pick", True),
            ("pairwise", False),
            ("pairwise", True),
        ):
            sel = shown[:2] if mode == "pairwise" else shown
            manifest = {"mode": mode, "explain": explain, "task": TASK}
            it = {"item_id": "x", "primary": [[f"a{i}" for i in range(len(sel))]]}
            outs = {f"a{i}": {"x": s} for i, s in enumerate(sel)}
            theirs = js.message_for(manifest, base, {"x": item["source"]}, outs, it, "primary", 0)
            ours = adapter().message_for(jparams(mode, explain=explain), item["source"], sel)
            results.append(theirs == ours)
        del j
        return all(results)

    attempt(
        "adapter: the message is the one judge-score sends, byte for byte, in each mode with and without a reason",
        message_equals_judge_score,
    )

    def pick_and_pairs():
        pick = json.loads(adapter().call_system(item0, jparams("pick", outputs_per_call=4)).output)
        pairs = json.loads(adapter().call_system(item0, jparams("pairwise", outputs_per_call=2)).output)
        longest = LENGTHS[0].index(max(LENGTHS[0])) + 1
        return (
            pick == {"best": [longest]}
            and len(pairs["pairs"]) == 6
            and all(p["better"] in (1, 2, "tie") for p in pairs["pairs"])
        )

    attempt(
        "adapter, pick and pairwise: the pick is named in the item's order; every pair of four outputs is sampled once",
        pick_and_pairs,
    )

    def scores_against_ratings():
        a = adapter()
        sg = a.score(a.call_system(item0, jparams()).output, ref0)
        sp = a.score(a.call_system(item0, jparams("pick", outputs_per_call=4)).output, ref0)
        sw = a.score(a.call_system(item0, jparams("pairwise", outputs_per_call=2)).output, ref0)
        bad = a.score(a.call_system(item0, jparams(model="m-bad")).output, ref0)
        return (
            sg["tau"] == 1.0 and sg["rho"] == 1.0 and bad["tau"] == -1.0
            and sp["top1"] == 1.0 and sp["top1_chance"] == 0.25
            and sw["pair_agreement"] == 1.0 and sw["n_pairs"] == 6.0
            and 0.0 < sg["human_tau"] < 1.0
        )  # fmt: skip

    attempt(
        "adapter: tau, top1 and pair agreement against the ratings, and the people's own agreement beside them",
        scores_against_ratings,
    )

    def unparsed_keeps_no_text():
        os.environ["JV_MODE"] = "BADREPLY"
        try:
            res = adapter().call_system(item0, jparams(model="m-bad", provider="openrouter"))
        finally:
            os.environ.pop("JV_MODE")
        o = json.loads(res.output)
        s = adapter().score(res.output, ref0)
        return (
            o["scores"] is None and "rather not say" not in res.output and len(o["unparsed"]) == 2
            and set(o["unparsed"][0]) == {"block", "sha256", "finish_reason", "chars"}
            and s["parsed"] == 0.0 and s["tau"] == 0.0
        )  # fmt: skip

    attempt(
        "adapter: a reply that does not parse is stored as its hash, finish reason and length, never its text; it scores 0",
        unparsed_keeps_no_text,
    )

    def floor_is_seeded():
        a = adapter()
        p = {"provider": "random", "mode": "grade", "task": TASK, "outputs_per_call": 2, "seed": 7}
        x, y = a.call_system(item0, p), a.call_system(item0, p)
        z = a.call_system(item0, {**p, "seed": 8})
        return x.output == y.output and x.output != z.output and x.cost_usd == 0.0 and not CALLS[len(CALLS) :]

    attempt(
        "adapter: the random floor is the seed's and the item's, costs nothing and calls no judge",
        floor_is_seeded,
    )

    def hooks():
        a = adapter()
        fp = a.fingerprint(jparams())
        return (
            a.primary_metric({"mode": "pick"}) == "top1" and a.primary_metric({"mode": "pairwise"}) == "pair_agreement"
            and a.primary_metric({}) == "tau"
            and fp["prompt_sha256"] == js._sha(js.prompt_text(js.load_scorer(sc_grade)))
            and "tau" in a.METRIC_KINDS
        )  # fmt: skip

    attempt(
        "adapter: the primary metric follows the mode and the fingerprint declares the prompt's sha256", hooks
    )

    def adapter_by_id():
        from evaluation_harness import _adapter  # noqa: PLC0415

        *_, path, _w, _f = _adapter.load_adapter("scripts/judge_validation.py", None)
        return Path(path).name == "judge_validation.py"

    attempt("a system's `adapter:` can name the core module: scripts/judge_validation.py", adapter_by_id)

    # ── the rated shape ──────────────────────────────────────────────────────────────────────────────────────────────
    def shape(refusals_of):
        from evaluation_harness import judge_validate as jv  # noqa: PLC0415

        sc = js.load_scorer(sc_grade)
        return jv.rated_problems(sc, *refusals_of)

    good_items = {f"r{i}": json.dumps(item_json(i)) for i in range(len(LENGTHS))}
    good_refs = {f"r{i}": json.dumps(reference_json(i)) for i in range(len(LENGTHS))}
    attempt("rated shape: the fixture is rated", lambda: shape((good_items, good_refs)) == [])
    attempt(
        "rated shape: an item that is not {source, outputs} is named",
        lambda: any("source" in p and "outputs" in p for p in shape(({"r0": "plain text"}, good_refs))),
    )
    attempt(
        "rated shape: an item with no reference is named",
        lambda: any("reference" in p for p in shape((good_items, {**good_refs, "r1": None}))),
    )
    attempt(
        "rated shape: a reference without ratings is named",
        lambda: any("ratings" in p for p in shape((good_items, {**good_refs, "r0": json.dumps({"x": 1})}))),
    )
    attempt("rated shape: a dimension the scorer names that the ratings lack is named",
            lambda: any("usefulness" in p for p in shape((good_items, {**good_refs, "r0": json.dumps({"ratings": {"accuracy": [1, 2, 3, 4]}})}))))  # fmt: skip
    only = {
        k: json.dumps({"ratings": {"accuracy": json.loads(v)["ratings"]["accuracy"]}})
        for k, v in good_refs.items()
    }
    attempt(
        "rated shape: ratings that carry some of the scorer's dimensions, the same in every item, are rated",
        lambda: shape((good_items, only)) == [],
    )
    attempt("rated shape: ratings that carry none of the scorer's dimensions are refused, naming them",
            lambda: any("none of" in p and "accuracy" in p for p in shape((good_items, {k: json.dumps({"ratings": {"witness": [1, 2, 3, 4]}}) for k in good_refs}))))  # fmt: skip
    attempt("rated shape: a dimension the scorer does not judge is named, not ignored",
            lambda: any("witness" in p for p in shape((good_items, {**good_refs, "r0": json.dumps({"ratings": {**json.loads(good_refs["r0"])["ratings"], "witness": [1, 2, 3, 4]}})}))))  # fmt: skip
    attempt("rated shape: items whose ratings carry different dimensions are named",
            lambda: any("r1" in p and "same" in p for p in shape((good_items, {**only, "r1": good_refs["r1"]}))))  # fmt: skip
    attempt("rated shape: a ratings list that is not one per output is named",
            lambda: any("4 outputs" in p for p in shape((good_items, {**good_refs, "r2": json.dumps({"ratings": {"accuracy": [1, 2], "usefulness": [1, 2]}})}))))  # fmt: skip

    # ── the command: refusals, before any call ───────────────────────────────────────────────────────────────────────
    CALLS.clear()
    attempt(
        "refused: a dataset that is not rated, naming what an item needs",
        lambda: "source" in run_cmd(scorer="vj_grade_v1", dataset="plain_v1", dry_run=True)[2],
    )
    attempt("refused: a pick scorer whose outputs_per_call is below the item's outputs",
            lambda: "outputs_per_call" in run_cmd(scorer=scorer("vj_pick_low_v1", "pick", 2).stem, dataset="rated_v1", dry_run=True)[2])  # fmt: skip
    (proj / "judge_prompt_nodims.txt").write_text(
        "Rate the {n} numbered replies. Reply with JSON.\n", encoding="utf-8"
    )
    scorer("vj_nodims_v1", prompt={"file": "judge_prompt_nodims.txt"})
    attempt(
        "refused: a grade prompt that does not name every dimension, as judge-score refuses",
        lambda: "dimension" in run_cmd(scorer="vj_nodims_v1", dataset="rated_v1", dry_run=True)[2],
    )
    scorer("vj_nocap_v1", cost_cap_usd=None)
    attempt("refused: no cost cap in the scorer or the environment, before any call, with what the dry run estimated",
            lambda: "cost cap" in run_cmd(scorer="vj_nocap_v1", dataset="rated_v1")[2])  # fmt: skip
    attempt("refused: --fill with a provider: fake judge (the gate never accepts one)",
            lambda: "fake" in run_cmd(scorer=scorer("vj_fake_v1", judges=[{"id": "fa", "params": {**PA, "provider": "fake", "model": "fk-a"}}, {"id": "fb", "params": {**PB, "provider": "fake", "model": "fk-b"}}]).stem,
                                      dataset="rated_v1", fill=True, reason="x")[2])  # fmt: skip
    attempt(
        "refused: --fill without a reason",
        lambda: "reason" in run_cmd(scorer="vj_grade_v1", dataset="rated_v1", fill=True)[2],
    )
    attempt(
        "refused: --fill with only some of the judges",
        lambda: (
            "every judge"
            in run_cmd(scorer="vj_grade_v1", dataset="rated_v1", judges="ja", fill=True, reason="r")[2]
        ),
    )
    attempt("no refusal made a call", lambda: CALLS == [])

    # ── the dry run: counts, calls nothing, writes nothing ───────────────────────────────────────────────────────────
    def dry():
        code, text, why = run_cmd(scorer="vj_grade_v1", dataset="rated_v1", dry_run=True)
        return (
            code == 0 and not why and "DRY RUN" in text and len(re.findall(rf"calls\s+{2 * len(LENGTHS)}\b", text)) == 2
            and "cap $1.00" in text and CALLS == [] and not _runstore.exists(proj, "systems/vj_grade_v1__ja__validation.yaml")
        )  # fmt: skip

    attempt("dry run: the calls and the estimate per judge, the cap, no call and no system written", dry)

    # ── the happy path in each mode: runs, the block, --fill, the gate ───────────────────────────────────────────────
    def validated(sid, mode, metric):
        CALLS.clear()
        code, text, why = run_cmd(
            scorer=sid,
            dataset="rated_v1",
            fill=True,
            reason="measured against people's ratings",
            what="the fixture",
            differs="it is a fixture",
        )
        sc = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")
        v = sc.get("validation") or {}
        runs = {r["judge"]: r for r in v.get("runs") or []}
        problems = js.validation_problems(sc)
        gate_wants_good = (runs.get("ja") or {}).get("value", 0) > (runs.get("jb") or {}).get("value", 1)
        return (
            code == 3 and not why and v.get("metric") == metric and v.get("dataset_id") == "rated_v1" and set(runs) == {"ja", "jb"}
            and gate_wants_good and bool(CALLS) and "random" in text
            and sc["prompt"]["sha256_at_16"] == js._sha(js.prompt_text(sc)) and v.get("what") == "the fixture"
            and (mode == "grade" or v.get("mode") == mode),
            problems,
            f"exit {code} {why} | {text[-900:]}",
        )  # fmt: skip

    for sid, mode, metric in (
        ("vj_grade_v1", "grade", "tau"),
        ("vj_pick_v1", "pick", "top1"),
        ("vj_pair_v1", "pairwise", "pair_agreement"),
    ):
        res: dict[str, Any] = {}

        def once(sid=sid, mode=mode, metric=metric, res=res):
            ok, problems, res["detail"] = validated(sid, mode, metric)
            res["problems"] = problems
            return ok

        attempt(
            f"{mode}: the command writes a block the scorer's own fill accepts",
            once,
            lambda res=res: res.get("detail"),
        )
        # the bad judge (tau -1, top1 0, pair agreement 0) is below the floor the gate holds it to: the gate names it, the command wrote it
        attempt(f"{mode}: the gate's answer after --fill is the gate's own (the judge below the random floor is named)",
                lambda res=res: any("jb" in p and "below" in p for p in res.get("problems", ["not run"])) and not any("ja" in p for p in res["problems"]))  # fmt: skip

    def fill_ok_with_good_judges():
        sid = "vj_goodonly_v1"
        scorer(sid, judges=[{"id": "ja", "params": PA}, {"id": "jc", "params": {**PB, "model": "m-good"}}])
        code, text, why = run_cmd(scorer=sid, dataset="rated_v1", fill=True, reason="r")  # noqa: RUF059
        sc = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")
        return code == 0 and js.validation_problems(sc) == [] and "validation_problems: none" in text

    attempt(
        "--fill: with judges above the floor the gate's validation_problems is empty, and the command says so",
        fill_ok_with_good_judges,
    )

    def systems_written():
        f = proj / "data" / "systems" / "vj_grade_v1__ja__validation.yaml"
        d = (
            yaml.safe_load(f.read_text(encoding="utf-8"))
            if f.exists()
            else _runstore.read_text(proj, "systems/vj_grade_v1__ja__validation.yaml")
        )
        d = d if isinstance(d, dict) else yaml.safe_load(d)
        p = d["params"]
        return (
            d["adapter"] == "scripts/judge_validation.py"
            and p["model"] == "m-good"
            and p["mode"] == "grade"
            and p["prompt_file"] == "judge_prompt.txt"
            and p["explain"] is False
        )

    attempt(
        "systems: one per judge, `<scorer>__<judge>__validation`, params the judge's plus the fields the gate compares",
        systems_written,
    )

    def history_and_why():
        from evaluation_harness.model.scorers import SCORER  # noqa: PLC0415

        h = SCORER.history("vj_grade_v1")
        sc = js.load_scorer(proj / "data" / "scorers" / "vj_grade_v1.yaml")
        return (
            bool(h)
            and h[0]["by"] == "person:tester"
            and "measured against" in (sc["validation"].get("why") or "")
        )

    attempt("--fill: who and why are recorded (the scorer's history, and the block's `why`)", history_and_why)

    def refill():
        before = js.load_scorer(proj / "data" / "scorers" / "vj_grade_v1.yaml")["validation"]
        _code, _text, why = run_cmd(scorer="vj_grade_v1", dataset="rated_v1", fill=True, reason="again")
        return (
            "replace" in why
            and js.load_scorer(proj / "data" / "scorers" / "vj_grade_v1.yaml")["validation"] == before
        )

    attempt(
        "--fill over an existing, different block is refused without --replace, and the block stays", refill
    )

    def resume_reuses_finished_runs():
        sid = "vj_resume_v1"
        scorer(sid)
        CALLS.clear()
        first = run_cmd(scorer=sid, dataset="rated_v1")
        made = len(CALLS)
        second = run_cmd(scorer=sid, dataset="rated_v1", resume=True)
        runs = [r for r in _model_runs.run_ids() if r.startswith(f"{sid}__")]
        return (
            first[0] == 0 and made > 0 and len(CALLS) == made and second[0] == 0
            and second[1].count("is finished, used as it is") == 3 and len(runs) == 3
        ), (first[2], second[1][-400:], runs)  # fmt: skip

    attempt(
        "--resume: a finished run of each system is used as it is, nothing is called again",
        lambda: resume_reuses_finished_runs()[0],
        lambda: resume_reuses_finished_runs()[1:],
    )

    def without_resume_runs_again():
        sid = "vj_resume_v1"
        before = len(CALLS)
        again = run_cmd(scorer=sid, dataset="rated_v1")
        return again[0] == 0 and len(CALLS) > before

    attempt("without --resume the same command runs again, as evh run does", without_resume_runs_again)

    def judges_subset():
        sid = "vj_subset_v1"
        scorer(sid)
        code, text, why = run_cmd(scorer=sid, dataset="rated_v1", judges="ja")  # noqa: RUF059
        runs = sorted({r.split("_2026")[0] for r in _model_runs.run_ids() if r.startswith(f"{sid}__")})
        return code == 0 and not why and runs == [f"{sid}__ja__validation", f"{sid}__random__validation"], (
            why,
            runs,
        )

    attempt(
        "--judges: only the named judge and the floor are run",
        lambda: judges_subset()[0],
        lambda: judges_subset()[1],
    )

    def floor_run_names_another_run():
        import _runfix  # noqa: PLC0415

        sid = "vj_floor_v1"
        scorer(sid)
        base_run = max(r for r in _model_runs.run_ids() if r.startswith("vj_grade_v1__random__validation_"))
        floor = _model_runs.record(_model_runs.first_score(base_run))["scores"]["tau"]
        _runfix.put_run(
            proj / "data",
            {
                "run_id": "arm_floor_other",
                "system_id": "arm_other",
                "dataset_id": "judged_v1",
                "scores": {"tau": 0.5},
            },
            [{"item_id": "a", "tau": 0.5}],
        )
        code, text, why = run_cmd(scorer=sid, dataset="rated_v1", floor_run=base_run)
        other = run_cmd(scorer=sid, dataset="rated_v1", floor_run="arm_floor_other")[2]
        missing = run_cmd(scorer=sid, dataset="rated_v1", floor_run="no_such_run")[2]
        return (
            code == 0
            and f"floor    {base_run}" in text
            and f"{floor:.4f}" in text
            and not any(r.startswith(f"{sid}__random__") for r in _model_runs.run_ids())
            and not _runstore.exists(proj, f"systems/{sid}__random__validation.yaml")
            and "is on 'judged_v1'" in other
            and "no such run" in missing
        ), (code, why, text[-300:], other, missing)

    attempt(
        "--floor-run: the named run is the floor and the random floor is neither made nor run; a run on another dataset, or none, is refused",
        lambda: floor_run_names_another_run()[0],
        lambda: floor_run_names_another_run()[1],
    )

    def replace_replaces():
        sid = "vj_goodonly_v1"
        before = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")["validation"]
        code, text, why = run_cmd(
            scorer=sid, dataset="rated_v1", fill=True, reason="again, on new runs", replace=True
        )
        after = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")["validation"]
        return code == 0 and not why and after["why"] == "again, on new runs" and after["runs"] != before[
            "runs"
        ], (why, text[-300:])

    attempt(
        "--fill --replace: the block is replaced by the one the new runs make",
        lambda: replace_replaces()[0],
        lambda: replace_replaces()[1],
    )

    def subset_is_said_not_averaged():
        sid = "vj_sub_v1"
        scorer(sid)
        code, text, why = run_cmd(
            scorer=sid, dataset="rated_sub_v1", fill=True, reason="people rated accuracy only"
        )
        sc = js.load_scorer(proj / "data" / "scorers" / f"{sid}.yaml")
        v = sc.get("validation") or {}
        problems = js.validation_problems(sc)
        ja = next(r for r in v["runs"] if r["judge"] == "ja")
        return (
            code == 3 and not why and v.get("dimensions") == ["accuracy"] and ja["value"] == 1.0
            and "dimension usefulness: not validated on rated_sub_v1 (its ratings carry accuracy)" in problems
            and "usefulness: not validated on rated_sub_v1" in text
        ), (code, why, v.get("dimensions"), problems)  # fmt: skip

    attempt(
        "a dataset rated on some dimensions: the block says which, the gate names the one not validated, nothing is averaged in",
        lambda: subset_is_said_not_averaged()[0],
        lambda: subset_is_said_not_averaged()[1],
    )

    def scorer_show_says_which_dimension():
        from evaluation_harness import ops as o  # noqa: PLC0415

        got = o.OPS["scorer-show"].call(scorer="vj_sub_v1")
        rows = [r for r in got["validation_runs"] if r["dataset"] == "rated_sub_v1" and r["judge"] == "ja"]
        say = o.OPS["scorer-show"].say(got)
        return (
            rows and rows[0]["dimensions"] == ["accuracy"] and rows[0]["not_validated"] == ["usefulness"]
            and "usefulness: not validated on rated_sub_v1" in say
            and any("usefulness: not validated on rated_sub_v1" in p for p in got["validation"]["problems"])
        ), (rows, say[-400:])  # fmt: skip

    attempt(
        "scorer-show says which dimension is not validated on which set, for its validation runs and its gate",
        lambda: scorer_show_says_which_dimension()[0],
        lambda: scorer_show_says_which_dimension()[1],
    )

    def recorded_output_hook():
        a = adapter()
        verdict = {"scores": {"accuracy": [1.0, 2.0], "usefulness": [1.0, 2.0]}, "blocks": 1, "parsed": 1}
        return json.loads(a.recorded_output({"id": "r0", "body": verdict})) == verdict

    attempt("recorded_output(record): a capture's record body is the run's output", recorded_output_hook)

    def recorded_arm_scores():
        (proj / "rec_importer.py").write_text(
            "import json\n\n\nclass Importer:\n    def __init__(self, options):\n        pass\n\n"
            "    def records(self, query):\n        for i in range(" + str(len(LENGTHS)) + "):\n"
            "            n = len(json.loads(open(f'item_{i}.json').read())['outputs'])\n"
            "            yield {'id': f'r{i}', 'body': {'scores': {d: [float(k + 1) for k in range(n)] for d in ('accuracy', 'usefulness')}, 'blocks': 1, 'parsed': 1}}\n",
            encoding="utf-8",
        )
        for i in range(len(LENGTHS)):
            (proj / f"item_{i}.json").write_text(json.dumps(item_json(i)), encoding="utf-8")
        made = evh(
            "capture",
            "--importer",
            "rec_importer.py:Importer",
            "--query",
            "{}",
            "--capture",
            "vj_cap",
            "--by",
            "tester",
        )
        _runstore.write_text(
            proj, "systems/vj_rec_v1.yaml",
            yaml.safe_dump({"system_id": "vj_rec_v1", "adapter": "scripts/judge_validation.py",
                            "params": {"provider": "recorded", "capture": "vj_cap", "mode": "grade", "task": TASK}}),
        )  # fmt: skip
        ran = evh("run", "--system", "vj_rec_v1", "--dataset", "rated_v1")
        runs = [r for r in _model_runs.run_ids() if r.startswith("vj_rec_v1_")]
        rec = _model_runs.record(_model_runs.first_score(runs[-1])) if runs else {}
        # item r0 has lengths 1,2,3,4: scores 1,2,3,4 rank like them (tau 1); r1 has 4,1,3,2: not
        return made.returncode == 0 and ran.returncode == 0 and rec.get("scores", {}).get(
            "parsed"
        ) == 1.0 and 0 < rec["scores"]["tau"] < 1, out(ran)[-500:]

    attempt(
        "a recorded arm of the core adapter: a capture of verdicts is a run scored like a live one",
        lambda: recorded_arm_scores()[0],
        lambda: recorded_arm_scores()[1],
    )

    def judged_scorer_refused():
        sid = "vj_judged_v1"
        scorer(sid)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _runfix  # noqa: PLC0415

        _runfix.put_run(
            proj / "data",
            {
                "run_id": "arm_x_1",
                "system_id": "arm_x",
                "dataset_id": "judged_v1",
                "scores": {"judge_score": 0.5},
            },
            [{"item_id": "a", "judge_score": 0.5}],
            label=f"judged/{sid}",
            scorer=sid,
            reference="set1",
        )
        why = run_cmd(scorer=sid, dataset="rated_v1", fill=True, reason="r")[2]
        return "scorer-new" in why and "supersedes" in why

    attempt(
        "--fill on a scorer that has judged scores is refused, naming scorer-new --supersedes",
        judged_scorer_refused,
    )

    def scorer_set_takes_a_list_of_objects():
        scorer("vj_setlist_v1")
        r = evh("scorer-set", "vj_setlist_v1", "--by", "person:tester", "--set", "validation.dataset_id=rated_v1", "--set",
                "validation.metric=tau", "--set", "validation.runs=[{judge: ja, run: r1, value: 0.5, min_metric: 0.1}]")  # fmt: skip
        got = js.load_scorer(proj / "data" / "scorers" / "vj_setlist_v1.yaml").get("validation") or {}
        return r.returncode == 0 and got.get("runs") == [
            {"judge": "ja", "run": "r1", "value": 0.5, "min_metric": 0.1}
        ], out(r)[-300:]

    attempt(
        "`scorer-set --set validation.runs=[{...}]` takes a list of objects (the same write --fill makes)",
        scorer_set_takes_a_list_of_objects,
    )

    def scorer_show_lists_the_runs():
        from evaluation_harness import ops as o  # noqa: PLC0415

        got = o.OPS["scorer-show"].call(scorer="vj_grade_v1")
        rows = got.get("validation_runs") or []
        by = {(r["judge"], r["dataset"]): r for r in rows}
        say = o.OPS["scorer-show"].say(got)
        return (
            {"ja", "jb", "random"} <= {r["judge"] for r in rows}
            and by[("ja", "rated_v1")]["metric"] == "tau"
            and by[("ja", "rated_v1")]["value"] == 1.0
            and by[("ja", "rated_v1")]["n_items"] == len(LENGTHS)
            and "validated by" in say and "random" in say
        ), say  # fmt: skip

    attempt(
        "scorer-show lists the validation runs: judge, dataset, metric, value, items",
        lambda: scorer_show_lists_the_runs()[0],
        lambda: scorer_show_lists_the_runs()[1],
    )

    def scorer_show_offers_the_rated_datasets():
        from evaluation_harness import ops as o  # noqa: PLC0415

        got = o.OPS["scorer-show"].call(scorer="vj_grade_v1")
        return got.get("rated_datasets") == [
            "rated_sub_v1",
            "rated_v1",
        ] and "rated datasets  rated_sub_v1, rated_v1" in o.OPS["scorer-show"].say(got), got.get(
            "rated_datasets"
        )

    attempt(
        "scorer-show names the datasets that are rated for the scorer (what the Workbench offers to validate on)",
        lambda: scorer_show_offers_the_rated_datasets()[0],
        lambda: scorer_show_offers_the_rated_datasets()[1],
    )

    def ops():
        from evaluation_harness import ops as o  # noqa: PLC0415

        op = o.OPS["judge-validate"]
        return (
            op.kind == "work"
            and op.spends
            and {"scorer", "dataset", "judges", "floor_run", "dry_run", "fill", "reason"} <= set(op.inputs)
        )

    attempt("the operation: a work job that spends, with the command's inputs", ops)

    def cli_help():
        r = evh("judge-validate", "--help")
        return r.returncode == 0 and "--scorer" in out(r) and "--fill" in out(r) and "--floor-run" in out(r)

    attempt("the command: `evh judge-validate --help`", cli_help)

    def cli_refusal():
        r = evh("judge-validate", "--scorer", "vj_grade_v1", "--dataset", "plain_v1", "--dry-run")
        return r.returncode == 1 and "Traceback" not in out(r) and "outputs" in out(r)

    attempt("the command: a dataset that is not rated is refused on the command line, exit 1", cli_refusal)
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
