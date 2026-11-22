"""The adapter of a judge's validation (RFC-038 section 3.2): a judge measured against people's ratings, as a system.

    evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1

`evh judge-validate` writes one system per judge of a scorer (`data/systems/<scorer>__<judge>__validation.yaml`) whose
`adapter:` is this file (`scripts/judge_validation.py`), and runs each as an ordinary run over a rated dataset. The point
of a core adapter is that the judge sees the message `judge-score` sends: the message is built by `judging`, the same
functions, the blocks are `judge_score.block_sizes`, and a reply is read by `judging`'s parsers.

A RATED DATASET's item is one JSON document, {"source": text, "outputs": [text, ...]}, and its reference is one,
{"ratings": {dimension: [one number per output]}, "raters": [{dimension: [...]}, ...]} (`raters` optional): the mean
of the people's ratings, on any scale (only its order is used), and each person's own. The dimensions are the scorer's
`task.dimensions`.

WHAT A RUN STORES as `output` is the parsed verdict, in the item's own order, never a reply's text (a reply can quote
the rated item): {"scores": {dimension: [...]}} (grade), {"best": [numbers]} (pick), {"pairs": [{a, b, better}]}
(pairwise). A reply that does not parse leaves its sha256, its finish reason and its length.

  grade      `tau`: Kendall tau-b of the judge's scores with the ratings per dimension, averaged over the dimensions
             and the items; `rho` beside it. One call per block of at most `outputs_per_call` outputs.
  pick       `top1`: the share of the outputs the judge named that are among those people rate highest, beside
             `top1_chance`, what a random pick gets. One call.
  pairwise   `pair_agreement` over the sampled pairs people rank apart, a tie counting half, with `n_pairs`. One call
             per pair.

With `raters`, `human_tau` (`human_top1`, `human_pair_agreement`) is scored beside the judge: each person against the
mean of the others, rotating, which is what a person agrees with people by. A system whose provider is `random` is the
floor: seeded verdicts of the mode's shape, at no cost.

The system's params are the judge's, and `scorer`, `judge`, `mode`, `explain`, `outputs_per_call`, `order_seed`, `task`,
`prompt_path` (the prompt file, relative to the project) and `prompt_file` (its name, which the gate compares).
`order` is `blinded` (the default: the outputs are shown in an order seeded by `order_seed` and the item, as `judge-score`
shows its arms) or `original` (as the item lists them, which is how a hand-made validation such as SummEval's adapter shows
them); `evh judge-validate` never sets it, a system written by hand can.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import itertools
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation_harness import _providers, _store, judging
from evaluation_harness._common import ROOT
from evaluation_harness.adapter import Result

PAIRS_PER_ITEM = 8
PAIR_SEED = 20261015
FLOOR_SEED = 20261015
#: Two ratings closer than this are a tie.
TIE_EPS = 1e-9
RANDOM = "random"
#: A system with no model behind it: the floor's seeded verdicts, or a capture's recorded ones.
RECORDED = "recorded"

#: What a reply costs in output tokens, for the dry run: judge_score's estimate, the same constants.
OUT_TOKENS_PER_SUMMARY = 14
OUT_TOKENS_FIXED = 10
OUT_TOKENS_ANSWER = 12
OUT_TOKENS_WHY_PER_OUTPUT = 20
OUT_TOKENS_WHY = 40
CHARS_PER_TOKEN = 4


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── what the system is asked ─────────────────────────────────────────────────
def _mode(params: dict[str, Any]) -> str:
    mode = params.get("mode") or judging.DEFAULT_MODE
    if mode not in judging.MODES:
        raise ValueError(f"mode must be one of {', '.join(judging.MODES)}, got {mode!r}")
    return mode


def _task(params: dict[str, Any]) -> dict[str, Any]:
    return judging.task_of({"task": params.get("task")})


def _explain(params: dict[str, Any]) -> bool:
    return params.get("explain") is True


def prompt_text(params: dict[str, Any]) -> str:
    """The scorer's prompt, read from `prompt_path` (the project's, or an absolute path), as `judge_score.prompt_text`
    strips it."""
    path = params.get("prompt_path")
    if not path:
        raise ValueError("a judge validation names its prompt file in params.prompt_path")
    p = Path(str(path))
    p = p if p.is_absolute() else ROOT / p
    if not _store.is_file(p):
        raise ValueError(f"prompt file not found: {p}")
    return _store.read_text(p, encoding="utf-8").strip()


def parse_item(text: str) -> dict[str, Any]:
    """One rated item, {"source", "outputs"}; ValueError when it is not one."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        raise ValueError(
            'an item of a rated dataset is a JSON document {"source": text, "outputs": [text, ...]}'
        ) from None
    outs = d["outputs"] if isinstance(d, dict) and "outputs" in d else None
    if (
        not isinstance(d, dict)
        or not isinstance(d.get("source"), str)
        or not isinstance(outs, list)
        or not outs
        or not all(isinstance(o, str) for o in outs)
    ):
        raise ValueError(
            'an item of a rated dataset is a JSON document {"source": text, "outputs": [text, ...]}'
        )
    return d


def message_for(params: dict[str, Any], source: str, shown: list[str]) -> str:
    """The message one call sends: these outputs, in this order, in the params' mode: what `judge_score.message_for`
    builds for a block of an item, with the reason's request when the scorer asks for one."""
    mode, task = _mode(params), _task(params)
    build = {"pick": judging.build_pick_message, "pairwise": judging.build_pairwise_message}.get(
        mode, judging.build_message
    )
    msg = build(prompt_text(params), source, shown, task["source_label"], task["output_label"])
    if not _explain(params):
        return msg
    return judging.with_reason(msg, mode, len(shown), task["source_label"], task["output_label"])


def _order(text: str, n: int, params: dict[str, Any]) -> list[int]:
    """The outputs' indices in the blinded order the judge sees them: seeded by `order_seed` and the item alone, so a
    rerun shows the same order and the order says nothing about the ratings."""
    order = params.get("order") or "blinded"
    if order not in ("blinded", "original"):
        raise ValueError(f"order must be blinded or original, got {order!r}")
    if order == "original":
        return list(range(n))
    seed, ident = params.get("order_seed", 0), _sha(text)
    return sorted(range(n), key=lambda i: _sha(f"{seed}|{ident}|{i}"))


def _block_sizes(n: int, per_call: int) -> list[int]:
    from evaluation_harness.judge_score import block_sizes  # noqa: PLC0415

    return block_sizes(n, per_call)


def pairs_per_item(params: dict[str, Any], n: int) -> int:
    """The pairs one item is judged in: `pairs_per_item` (else the default), never more than its n outputs make."""
    k = params.get("pairs_per_item", PAIRS_PER_ITEM)
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"pairs_per_item must be a whole number above 0, got {k!r}")
    return min(k, n * (n - 1) // 2)


def _pairs(item: dict[str, Any], params: dict[str, Any]) -> list[tuple[int, int]]:
    """The pairs of an item's outputs a pairwise judge compares, each as (shown first, shown second): `pairs_per_item`
    of them, seeded by `pair_seed` and the item alone, so every judge sees the same pairs and none of them depends on
    the ratings."""
    n = len(item["outputs"])
    ident = _sha("\x00".join([item["source"], *item["outputs"]]))
    rng = random.Random(f"{params.get('pair_seed', PAIR_SEED)}:{ident}")
    chosen = rng.sample(list(itertools.combinations(range(n), 2)), pairs_per_item(params, n))
    return [(a, b) if rng.random() < 0.5 else (b, a) for a, b in chosen]


@dataclass
class Call:
    """One judge call of an item: the output indices it shows, in order, and the message."""

    shown: list[int]
    message: str


def plan(text: str, params: dict[str, Any]) -> list[Call]:
    """The calls an item takes: grade, one per block of the blinded order; pick, one with every output; pairwise, one
    per sampled pair."""
    item, mode = parse_item(text), _mode(params)
    outs, n = item["outputs"], len(item["outputs"])
    if mode == "pairwise":
        groups = [[a, b] for a, b in _pairs(item, params)]
    elif mode == "pick":
        groups = [_order(text, n, params)]
    else:
        order, groups, i = _order(text, n, params), [], 0
        for size in _block_sizes(n, int(params.get("outputs_per_call") or n)):
            groups.append(order[i : i + size])
            i += size
    return [Call(g, message_for(params, item["source"], [outs[i] for i in g])) for g in groups]


def estimate(texts: list[str], params: dict[str, Any]) -> dict[str, Any]:
    """The calls, tokens and cost of validating on these items, counted before anything is called, as judge-score's dry
    run counts them: chars / 4 in, and a reply as long as the mode's answer is; the price from the params."""
    mode, dims = _mode(params), len(_task(params)["dimensions"])
    calls = tin = tout = 0
    for t in texts:
        for c in plan(t, params):
            n = len(c.shown)
            calls += 1
            tin += math.ceil(len(c.message) / CHARS_PER_TOKEN)
            grade = mode == judging.DEFAULT_MODE
            tout += (
                OUT_TOKENS_FIXED + math.ceil(OUT_TOKENS_PER_SUMMARY * dims / len(judging.DIMS)) * n
                if grade
                else OUT_TOKENS_ANSWER
            ) + ((OUT_TOKENS_WHY_PER_OUTPUT * n if grade else OUT_TOKENS_WHY) if _explain(params) else 0)
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    cost = tin / 1e6 * float(pin) + tout / 1e6 * float(pout) if pin is not None and pout is not None else None
    return {"calls": calls, "tokens_in": tin, "tokens_out": tout, "est_cost_usd": cost}


# ── the call ─────────────────────────────────────────────────────────────────
def _total(values: list[Any]) -> Any:
    """The sum of the calls' counts, or None when any call did not report one (None is not 0)."""
    return None if any(v is None for v in values) else round(sum(values), 10)


def _unparsed(res: Any, **where: Any) -> dict[str, Any]:
    """What is kept of a reply that did not parse: not its text (it can quote the rated item), its hash, its finish reason
    and its length."""
    out = res.output or ""
    return {
        **where,
        "sha256": _sha(out),
        "finish_reason": (getattr(res, "meta", None) or {}).get("finish_reason"),
        "chars": len(out),
    }


def _ask(message: str, params: dict[str, Any]) -> Any:
    """One reply from the judge: through `judging.call_judge`, as judge-score calls it. A fake judge is told the task, as
    judge-score tells it."""
    p = dict(params)
    if p.get("provider") == judging.FAKE:
        p.update(_task=_task(params), _mode=_mode(params), _explain=_explain(params))
    return judging.call_judge(message, p)


def _cost(res: Any, params: dict[str, Any]) -> float | None:
    from evaluation_harness.judge_score import call_cost  # noqa: PLC0415

    return call_cost(res, params)[0]


def call_system(text: str, params: dict[str, Any]) -> Result:
    """One rated item judged: every call the mode needs, the verdict read back into the item's own order."""
    started = time.perf_counter()
    if params.get("provider") == RANDOM:
        res = _floor(text, params)
    else:
        res = _judge(text, params)
    res.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return res


def _judge(text: str, params: dict[str, Any]) -> Result:
    item, mode, task = parse_item(text), _mode(params), _task(params)
    n, calls = len(item["outputs"]), plan(text, params)
    replies = [_ask(c.message, params) for c in calls]
    unparsed: list[dict[str, Any]] = []
    if mode == "grade":
        cols: dict[str, list[float | None]] = {d: [None] * n for d in task["dimensions"]}
        for b, (c, r) in enumerate(zip(calls, replies, strict=True)):
            got = judging.parse_columns(r.output, len(c.shown), task["dimensions"], task["scale"])
            if got is None:
                unparsed.append(_unparsed(r, block=b))
                continue
            for d, vals in got.items():
                for i, v in zip(c.shown, vals, strict=True):
                    cols[d][i] = v
        verdict: dict[str, Any] = {
            "scores": None if unparsed else cols,
            "blocks": len(calls),
            "parsed": len(calls) - len(unparsed),
            **({"unparsed": unparsed} if unparsed else {}),
        }
    elif mode == "pick":
        picked = judging.parse_pick(replies[0].output, n)
        if picked is None:
            unparsed.append(_unparsed(replies[0]))
        verdict = {"best": sorted(calls[0].shown[p - 1] + 1 for p in picked) if picked else None}
        if unparsed:
            verdict["unparsed"] = unparsed
    else:
        pairs = []
        for c, r in zip(calls, replies, strict=True):
            better = judging.parse_pairwise(r.output)
            row: dict[str, Any] = {"a": c.shown[0], "b": c.shown[1], "better": better}
            if better is None:
                row.update(_unparsed(r))
            pairs.append(row)
        verdict = {"pairs": pairs}
    costs = [_cost(r, params) for r in replies]
    extra: dict[str, float] = {"truncated": max((r.extra or {}).get("truncated", 0.0) for r in replies)}
    if all("reasoning_tokens" in (r.extra or {}) for r in replies):
        extra["reasoning_tokens"] = float(sum(r.extra["reasoning_tokens"] for r in replies))
    metas = [r.meta or {} for r in replies]
    return Result(
        output=json.dumps(verdict),
        tokens_in=_total([r.tokens_in for r in replies]),
        tokens_out=_total([r.tokens_out for r in replies]),
        cost_usd=_total(costs),
        extra=extra,
        # The harness reads meta["calls"] as a list of call records and meta["finish_reason"] as the provider's string
        # ("length" marks a reply cut at max_tokens).
        meta={
            "finish_reason": next(
                (f for m in metas if (f := m.get("finish_reason")) == "length"), metas[0].get("finish_reason")
            ),
            "response_model": metas[0].get("response_model"),
            "provider": metas[0].get("provider"),
            "calls": [
                {
                    "finish_reason": m.get("finish_reason"),
                    "tokens_in": r.tokens_in,
                    "tokens_out": r.tokens_out,
                }
                for m, r in zip(metas, replies, strict=True)
            ],
        },
    )


def _floor(text: str, params: dict[str, Any]) -> Result:
    """The floor: verdicts of the mode's shape drawn at random, seeded by `seed` and the item alone."""
    item, mode, task = parse_item(text), _mode(params), _task(params)
    n = len(item["outputs"])
    rng = random.Random(f"{params.get('seed', FLOOR_SEED)}:{_sha(text)}")
    if mode == "grade":
        lo, hi = task["scale"]
        verdict: dict[str, Any] = {
            "scores": {d: [float(rng.randint(lo, hi)) for _ in range(n)] for d in task["dimensions"]},
            "blocks": 1,
            "parsed": 1,
        }
    elif mode == "pick":
        verdict = {"best": [rng.randint(1, n)]}
    else:
        verdict = {"pairs": [{"a": a, "b": b, "better": rng.choice([1, 2])} for a, b in _pairs(item, params)]}
    return Result(output=json.dumps(verdict), cost_usd=0.0)


# ── how good it was ──────────────────────────────────────────────────────────
def _verdict(output: str) -> dict[str, Any] | None:
    try:
        v = json.loads(output)
    except (TypeError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _means(ratings: dict[str, list[float]]) -> list[float]:
    """Each output's rating over the dimensions."""
    cols = list(ratings.values())
    return [sum(c[i] for c in cols) / len(cols) for i in range(len(cols[0]))]


def _best_set(means: list[float]) -> set[int]:
    """The outputs people rate highest, 1-based: ties form the set."""
    top = max(means)
    return {i + 1 for i, v in enumerate(means) if top - v < TIE_EPS}


def _top1(named: list[int], best: set[int]) -> float:
    """The share of the outputs named that are in the best set: 1 for a correct single pick; a pick of several scores
    the chance of drawing a correct one from them."""
    return sum(k in best for k in named) / len(named) if named else 0.0


def _others(raters: list[dict[str, list[float]]], k: int) -> dict[str, list[float]]:
    """The mean of the raters but the k-th, per dimension."""
    rest = [r for j, r in enumerate(raters) if j != k]
    return {d: [sum(r[d][i] for r in rest) / len(rest) for i in range(len(rest[0][d]))] for d in rest[0]}


def _parsed_share(v: dict[str, Any]) -> float:
    if "scores" in v:
        return (v.get("parsed") or 0) / v["blocks"] if v.get("blocks") else 0.0
    if "best" in v:
        return 1.0 if v["best"] else 0.0
    pairs = v.get("pairs") or []
    return sum(p.get("better") is not None for p in pairs) / len(pairs) if pairs else 0.0


def score(output: str, reference: str | None) -> dict[str, float]:
    """One item's agreement with people, by the kind of verdict the output holds. An unreadable verdict scores 0 on the
    quality metrics, never skipped, and `parsed` says how much of it was readable."""
    v = _verdict(output)
    if v is None or not ({"scores", "best", "pairs"} & set(v)):
        return {"parsed": 0.0}
    out: dict[str, float] = {"parsed": round(_parsed_share(v), 10)}
    if reference is None:
        return out
    ref = json.loads(reference)
    ratings: dict[str, list[float]] = ref["ratings"]
    raters: list[dict[str, list[float]]] = ref.get("raters") or []
    if "scores" in v:
        return {**out, **_score_grade(v, ratings, raters)}
    if "best" in v:
        return {**out, **_score_pick(v, ratings, raters)}
    return {**out, **_score_pairs(v, ratings, raters)}


def _tau_rho(a: list[float], b: list[float]) -> tuple[float, float]:
    return judging.kendall_tau_b(a, b), judging.spearman(a, b)


def _score_grade(
    v: dict[str, Any], ratings: dict[str, list[float]], raters: list[dict[str, list[float]]]
) -> dict[str, float]:
    got = v.get("scores") or {}
    out: dict[str, float] = {}
    taus, rhos = [], []
    for d, gold in ratings.items():
        mine = got.get(d)
        t, r = (0.0, 0.0) if mine is None else _tau_rho([float(x) for x in mine], gold)
        out[f"tau_{d}"], out[f"rho_{d}"] = round(t, 10), round(r, 10)
        taus.append(t)
        rhos.append(r)
    out["tau"], out["rho"] = round(sum(taus) / len(taus), 10), round(sum(rhos) / len(rhos), 10)
    if len(raters) > 1:
        each = [
            sum(judging.kendall_tau_b(r[d], _others(raters, k)[d]) for d in ratings) / len(ratings)
            for k, r in enumerate(raters)
        ]
        out["human_tau"] = round(sum(each) / len(each), 10)
    return out


def _score_pick(
    v: dict[str, Any], ratings: dict[str, list[float]], raters: list[dict[str, list[float]]]
) -> dict[str, float]:
    means = _means(ratings)
    best = _best_set(means)
    named = v.get("best") or []
    out = {"top1": round(_top1(named, best), 10), "top1_chance": round(len(best) / len(means), 10)}
    if len(raters) > 1:
        each = [
            _top1(sorted(_best_set(_means(r))), _best_set(_means(_others(raters, k))))
            for k, r in enumerate(raters)
        ]
        out["human_top1"] = round(sum(each) / len(each), 10)
    return out


def _credit(first: float, second: float, preferred_first: bool) -> float:
    """A tie counts half; else whether the one preferred is the one people prefer."""
    if abs(first - second) < TIE_EPS:
        return 0.5
    return 1.0 if (first > second) == preferred_first else 0.0


def _score_pairs(
    v: dict[str, Any], ratings: dict[str, list[float]], raters: list[dict[str, list[float]]]
) -> dict[str, float]:
    means, pairs = _means(ratings), v.get("pairs") or []
    credit = []
    for p in pairs:
        a, b = p["a"], p["b"]
        if abs(means[a] - means[b]) < TIE_EPS:
            continue
        better = p.get("better")
        credit.append(
            0.0
            if better is None
            else 0.5
            if better == "tie"
            else 1.0
            if better == (1 if means[a] > means[b] else 2)
            else 0.0
        )
    out = {
        "pair_agreement": round(sum(credit) / len(credit), 10) if credit else 0.5,
        "n_pairs": float(len(credit)),
    }
    if len(raters) > 1:
        each = []
        for k, r in enumerate(raters):
            rest, mine = _means(_others(raters, k)), _means(r)
            cs = [
                _credit(mine[p["a"]], mine[p["b"]], rest[p["a"]] > rest[p["b"]])
                for p in pairs
                if abs(rest[p["a"]] - rest[p["b"]]) >= TIE_EPS
            ]
            if cs:
                each.append(sum(cs) / len(cs))
        if each:
            out["human_pair_agreement"] = round(sum(each) / len(each), 10)
    return out


# ── what the harness reads of an adapter ─────────────────────────────────────
def primary_metric(params: dict[str, Any]) -> str:
    """The run's headline by its mode: tau for grade, top1 for pick, pair_agreement for pairwise."""
    return {"pick": "top1", "pairwise": "pair_agreement"}.get(
        str(params.get("mode") or judging.DEFAULT_MODE), "tau"
    )


METRIC_KINDS = {
    "tau": "quality",
    "rho": "quality",
    "top1": "quality",
    "pair_agreement": "quality",
    "top1_chance": "descriptive",
    "n_pairs": "descriptive",
    "parsed": "descriptive",
    "human_tau": "descriptive",
    "human_top1": "descriptive",
    "human_pair_agreement": "descriptive",
    "truncated": "descriptive",
    "reasoning_tokens": "descriptive",
}

METRIC_DESCRIPTIONS = {
    "tau": "Kendall's tau-b between the judge's scores and the people's ratings of an item's outputs, per dimension, "
    "averaged over the dimensions: how well the judge orders outputs as people do. A dimension the judge did not return "
    "counts 0.",
    "rho": "Spearman's rho between the judge's scores and the people's ratings, averaged over the dimensions: kept for "
    "comparison with the literature.",
    "top1": "Pick mode: how often the judge's pick of the best output of an item is one people rate best (highest mean "
    "over the dimensions; ties among people form the best set). 1 for a correct single pick; a pick of several scores "
    "the share of them that are correct; an unreadable pick scores 0.",
    "top1_chance": "Pick mode: what a random pick scores on the item, the share of its outputs people rate best.",
    "pair_agreement": "Pairwise mode: among the sampled pairs of an item's outputs that people rank apart, the share "
    "where the judge preferred the output people prefer; a tie counts half and an unreadable answer 0. Chance is 0.5.",
    "n_pairs": "Pairwise mode: how many of the item's sampled pairs people ranked apart, the pairs pair_agreement is "
    "averaged over.",
    "parsed": "The share of the judge's replies the item took that could be read as an answer in the mode's shape.",
    "human_tau": "What one person's ratings agree with the mean of the others' by tau, rotating over the people: the "
    "ceiling a judge is read against (only when the ratings come with each person's own).",
    "human_top1": "What one person's best outputs agree with the best of the others' by top1, rotating.",
    "human_pair_agreement": "What one person's order of the sampled pairs agrees with the others' mean, rotating.",
}


def recorded_output(record: dict[str, Any]) -> str:
    """A recorded arm's output (RFC-023): a capture's record whose `body` is a verdict in this adapter's output form
    (`{"scores": ...}`, `{"best": ...}` or `{"pairs": ...}`), as the run stores one; it is scored as a live one is."""
    return json.dumps(record["body"])


def warmup(params: dict[str, Any]) -> None:
    """What stops a call before it is made: the prompt not there, a provider's key or address missing. Nothing is
    called: a validation is billed, and the first item says if the model is not."""
    if params.get("provider") in (RANDOM, RECORDED, judging.FAKE):
        return
    prompt_text(params)
    found = _providers.problems(params, "judge")
    if found:
        raise RuntimeError("; ".join(found))


def prompts(params: dict[str, Any]) -> dict[str, str]:
    """The prompt a call sends, by name: the text this adapter's fingerprint hashes as `prompt_sha256`, which the gate
    compares with the scorer's."""
    if params.get("provider") in (RANDOM, RECORDED):
        return {}
    return {f"judge-validation/{Path(str(params.get('prompt_file') or 'prompt')).stem}": prompt_text(params)}


def fingerprint(params: dict[str, Any]) -> dict[str, Any]:
    """What this system is, as a judge: the model asked, how, the mode and the prompt's sha256."""
    mode = _mode(params)
    if params.get("provider") in (RANDOM, RECORDED):
        return {
            "provider": params["provider"],
            "id": params["provider"],
            "mode": mode,
            "kind": "seeded random verdicts, no model and no network"
            if params["provider"] == RANDOM
            else "a judge's recorded verdicts, read from a capture: nothing was called",
            "identity_declared": False,
            "revision_source": "not-a-model",
            "seed": params.get("seed", FLOOR_SEED),
        }
    return {
        "id": params.get("model"),
        "alias": params.get("model"),
        "revision": None,
        "revision_source": "api-model-string",
        "temperature": params.get("temperature"),
        "reasoning": params.get("reasoning"),
        "prompt_sha256": _sha(prompt_text(params)),
        "mode": mode,
        "explain": _explain(params),
        "outputs_per_call": params.get("outputs_per_call"),
        "order_seed": params.get("order_seed", 0),
        "order": params.get("order") or "blinded",
        **(
            {
                "pairs_per_item": params.get("pairs_per_item", PAIRS_PER_ITEM),
                "pair_seed": params.get("pair_seed", PAIR_SEED),
            }
            if mode == "pairwise"
            else {}
        ),
    }
