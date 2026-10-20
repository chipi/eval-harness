#!/usr/bin/env python3
"""Re-measure a frozen experiment with a validated LLM judge (docs/adr/ADR-0001).

    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1 ARGS=--dry-run
    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1
    EVAL_RUNS_DIR=data/runs-judged/judge-summ-v1 make leaderboard DATASET_ID=cnn_dailymail_200

`make judge` is the older judge PANEL (runner.py): pointwise, finalists only, verdicts not
stored. This is the judging PASS: listwise, every arm, verdicts stored as a frozen record.

THE PASS, IN ORDER
  1. gate       the scorer must name a committed run that validates each judge (or
                --unvalidated, which labels every number "unvalidated").
  2. judging set  one item = the article + every arm's output for it. Arm identities are
                hidden and the order is shuffled per item with a seed. The arm set, the
                outputs, the seed and the block size are hashed into the set's id, and the
                manifest is written to data/judging-sets/. Listwise scores depend on who
                else is in the list, so a different arm set is a different set, never an
                append.
  3. verdicts   each judge reads each block and answers with JSON scores; the raw reply is
                stored per call under data/judge-verdicts/, written atomically, so a rerun
                skips what is stored (resume) and re-reading costs $0. Cost-capped mid-run;
                what was bought is kept.
  4. projection one score per arm per item (mean of the four dimensions, per judge; the
                primary is the mean over judges) written as scored runs, shaped like
                rescore's, plus summary.json with the controls.

BLOCKS. SummEval validated 16 summaries per call. With more arms than that, an item is
judged in the fewest blocks of at most `outputs_per_call`, sizes as equal as possible: 29
arms are 15 + 14, never 16 + 13, so no call is further from the validated size than it must
be, and no block is a runt. Arms are assigned to blocks by the per-item shuffle, so a block
is a random sample of the arms and the blocks of an item are exchangeable. The judge scores
each summary on an ABSOLUTE 1-5 scale per dimension, not a rank within the block, which is
what lets scores from different blocks be averaged together. That is an assumption, and the
position check tests it: its second shuffle re-forms the blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    DATA, MATERIALIZED, ROOT, RUNS, CostCapExceeded, die, env_float, now, read_json,
    write_json, write_text_atomic,
)
from _retry import call_with_retries  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

SCORERS = DATA / "scorers"
SETS = DATA / "judging-sets"
VERDICTS = DATA / "judge-verdicts"
JUDGED = DATA / "runs-judged"
SUMMEVAL_ADAPTER = ROOT.parent / "examples" / "summeval-judging" / "adapter.py"

DIMS = ("coherence", "consistency", "fluency", "relevance")
PASSES = ("primary", "position", "noise")
#: Describe the CALL that made an arm's output, not how it was measured: carried across as
#: rescore.py carries them.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd", "truncated", "reasoning_tokens")
#: Reply size per summary for the dry-run estimate: SummEval's gemma_l returned 217.5 tokens
#: for 16 summaries x 4 dimensions (committed run se_gemma_l_n100_v1, scores.tokens_out).
OUT_TOKENS_PER_SUMMARY = 14
OUT_TOKENS_FIXED = 10
CHARS_PER_TOKEN = 4

_ADAPTER: Any = None


def summeval_adapter() -> Any:
    """The validated judge's own module: `_litellm`, `_judge_message`, `kendall_tau_b`."""
    global _ADAPTER
    if _ADAPTER is None:
        if not SUMMEVAL_ADAPTER.is_file():
            die(f"the SummEval judge is missing: {SUMMEVAL_ADAPTER}")
        spec = importlib.util.spec_from_file_location("summeval_judging_adapter", SUMMEVAL_ADAPTER)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[spec.name] = mod            # @dataclass looks its own module up
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _ADAPTER = mod
    return _ADAPTER


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ── the scorer artifact and the validation gate ──────────────────────────────
def load_scorer(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        die(f"no such scorer: {path}")
    sc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sc["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if sc.get("kind") != "judge":
        die(f"{path.name}: kind must be 'judge', got {sc.get('kind')!r}")
    for k in ("scorer_id", "dataset_id", "judges", "prompt", "protocol"):
        if not sc.get(k):
            die(f"{path.name}: missing {k!r}")
    fams = {j["params"].get("family") for j in sc["judges"]}
    if len(sc["judges"]) < 2 or len(fams) < 2:
        die(f"{path.name}: needs at least two judges from different vendor families "
            f"(ADR-0001 §4); got {sorted(map(str, fams))}")
    return sc


def prompt_text(sc: Dict[str, Any], root: Path = ROOT.parent) -> str:
    p = root / sc["prompt"]["file"]
    if not p.is_file():
        die(f"prompt file not found: {p}")
    return p.read_text(encoding="utf-8").strip()


def validation_problems(sc: Dict[str, Any], runs_dir: Path = RUNS,
                        prompt_root: Path = ROOT.parent) -> List[str]:
    """Why this scorer is not validated; empty means it is."""
    v = sc.get("validation")
    if not isinstance(v, dict) or not v.get("runs"):
        return ["no `validation` block naming a committed run"]
    out: List[str] = []
    metric = v.get("metric")
    named = {r.get("judge"): r for r in v["runs"] if isinstance(r, dict)}
    for j in sc["judges"]:
        r = named.get(j["id"])
        if not r:
            out.append(f"judge {j['id']!r}: no validation run names it")
            continue
        d = runs_dir / str(r.get("run", ""))
        if not (d / "metrics.json").is_file():
            out.append(f"judge {j['id']!r}: validation run {r.get('run')!r} is not in {runs_dir}")
            continue
        m = read_json(d / "metrics.json")
        if v.get("experiment") and m.get("dataset_id") != v["experiment"]:
            out.append(f"judge {j['id']!r}: run {r['run']} is on {m.get('dataset_id')!r}, "
                       f"not {v['experiment']!r}")
        got = (m.get("scores") or {}).get(metric)
        if got is None or r.get("value") is None or abs(float(got) - float(r["value"])) > 1e-6:
            out.append(f"judge {j['id']!r}: run {r['run']} has {metric}={got}, "
                       f"scorer claims {r.get('value')}")
        if (m.get("params") or {}).get("model") != j["params"].get("model"):
            out.append(f"judge {j['id']!r}: run {r['run']} measured model "
                       f"{(m.get('params') or {}).get('model')!r}, not {j['params'].get('model')!r}")
    want = (sc["prompt"].get("sha256_at_16") or "")
    if want and want != _sha(prompt_text(sc, prompt_root)):
        out.append("prompt.sha256_at_16 does not match the prompt file: the text the "
                   "judges were validated on has changed")
    return out


# ── the prompt, generalised only in its count ────────────────────────────────
def render_prompt(base: str, n: int) -> str:
    """SummEval's prompt for `n` summaries. Byte-identical to it when n == 16."""
    if n == 16:
        return base
    a, b = "16 numbered summaries", "a list of 16 integers"
    if a not in base or b not in base:
        die("the prompt no longer contains the two count phrases this pass rewrites "
            f"({a!r}, {b!r}); it cannot be rendered for {n} summaries")
    return base.replace(a, f"{n} numbered summaries").replace(b, f"a list of {n} integers")


def build_message(base: str, article: str, summaries: Sequence[str]) -> str:
    """The judge's input, assembled by SummEval's own function so the layout cannot drift."""
    return summeval_adapter()._judge_message(
        {"article": article, "summaries": list(summaries)},
        {"prompt": render_prompt(base, len(summaries))})


def parse_block(output: str, n: int) -> Optional[List[float]]:
    """Per-summary mean of the four dimensions, or None.

    Same reading as SummEval's `parse_scores` with the count a parameter: lenient about
    wrapping, strict about content. A dimension counts only with exactly `n` numbers, and
    a block counts only with all four, each in 1..5.
    """
    ad = summeval_adapter()
    m = ad._JSON.search(output or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    cols = []
    for d in DIMS:
        v = obj.get(d)
        if not isinstance(v, list) or len(v) != n:
            return None
        try:
            f = [float(x) for x in v]
        except (TypeError, ValueError):
            return None
        if any(not (1.0 <= x <= 5.0) for x in f):
            return None
        cols.append(f)
    return [statistics.fmean(c[i] for c in cols) for i in range(n)]


# ── order, blocks, subsets ───────────────────────────────────────────────────
def block_sizes(n_outputs: int, per_call: int) -> List[int]:
    """Fewest blocks of at most per_call, as equal as possible: 29, 16 -> [15, 14]."""
    k = max(1, math.ceil(n_outputs / per_call))
    base, extra = divmod(n_outputs, k)
    return [base + 1] * extra + [base] * (k - extra)


def shuffled(arm_ids: Sequence[str], seed: Any, salt: str, item_id: str) -> List[str]:
    return sorted(arm_ids, key=lambda a: _sha(f"{seed}|{salt}|{item_id}|{a}"))


def blocks_for(arm_ids: Sequence[str], seed: Any, salt: str, item_id: str,
               per_call: int) -> List[List[str]]:
    order = shuffled(arm_ids, seed, salt, item_id)
    out, i = [], 0
    for s in block_sizes(len(order), per_call):
        out.append(order[i:i + s])
        i += s
    return out


def pick_subset(item_ids: Sequence[str], frac: float, seed: Any, salt: str) -> List[str]:
    if not frac or frac <= 0:
        return []
    k = min(len(item_ids), max(1, round(frac * len(item_ids))))
    chosen = set(sorted(item_ids, key=lambda i: _sha(f"{seed}|{salt}|{i}"))[:k])
    return [i for i in item_ids if i in chosen]


# ── arms and the judging set ─────────────────────────────────────────────────
def discover_arms(dataset_id: str, match: str, runs_dir: Path = RUNS) -> List[Dict[str, Any]]:
    """The primary run of every arm on the dataset: config_id contains `match`, latest wins."""
    latest: Dict[str, Tuple[str, Path, Dict[str, Any]]] = {}
    for mj in sorted(runs_dir.glob("*/metrics.json")):
        m = read_json(mj)
        cid = m.get("config_id", "")
        if m.get("dataset_id") != dataset_id or match not in cid:
            continue
        key = m.get("created_at", "") + mj.parent.name
        if cid not in latest or key > latest[cid][0]:
            latest[cid] = (key, mj.parent, m)
    arms = []
    for cid, (_k, d, m) in sorted(latest.items()):
        arms.append({"config_id": cid, "run": d.name, "dir": d,
                     "family": (m.get("params") or {}).get("family")
                     or (m.get("fingerprint", {}).get("arm", {}).get("params") or {}).get("family")})
    return arms


def read_outputs(arm: Dict[str, Any], item_ids: Sequence[str]) -> Dict[str, str]:
    out = {}
    for i in item_ids:
        f = Path(arm["dir"]) / "outputs" / f"{i}.txt"
        if not f.is_file():
            die(f"{arm['run']}: no stored output for {i} — the judging set needs every "
                f"arm's output for every item")
        out[i] = f.read_text(encoding="utf-8")
    return out


def build_manifest(sc: Dict[str, Any], dataset_id: str, items_sha256: Optional[str],
                   item_ids: Sequence[str], arms: Sequence[Dict[str, Any]],
                   articles: Dict[str, str], outputs: Dict[str, Dict[str, str]],
                   base_prompt: str) -> Dict[str, Any]:
    """The frozen judging set. `outputs[config_id][item_id]` is that arm's text."""
    pr = sc["protocol"]
    seed, per_call = pr.get("order_seed", 0), int(pr["outputs_per_call"])
    arm_ids = [a["config_id"] for a in arms]
    if len(arm_ids) < 2:
        die("a judging set needs at least two arms")
    items = []
    for i in item_ids:
        items.append({
            "item_id": i,
            "article_sha256": _sha(articles[i]),
            "primary": blocks_for(arm_ids, seed, "primary", i, per_call),
            "position": blocks_for(arm_ids, seed, "position", i, per_call),
        })
    body = {
        "dataset_id": dataset_id,
        "dataset_items_sha256": items_sha256,
        "arms": [{"config_id": a["config_id"], "run": a["run"], "family": a.get("family"),
                  "outputs_sha256": _sha(_canon([[i, _sha(outputs[a["config_id"]][i])]
                                                 for i in item_ids]))} for a in arms],
        "protocol": {"outputs_per_call": per_call, "blinding": bool(pr.get("blinding", True)),
                     "order_seed": seed, "block_sizes": block_sizes(len(arm_ids), per_call)},
        "prompt_sha256_at_16": _sha(base_prompt),
        "items": items,
        "position_items": pick_subset(list(item_ids), pr.get("position_check_fraction", 0),
                                      seed, "position-subset"),
        "noise_items": pick_subset(list(item_ids), pr.get("noise_check_fraction", 0),
                                   seed, "noise-subset"),
    }
    digest = _sha(_canon(body))
    return {"judging_set_id": f"{dataset_id}-{len(arm_ids)}arms-{digest[:12]}",
            "judging_set_sha256": digest, **body}


def message_for(manifest: Dict[str, Any], base: str, articles: Dict[str, str],
                outputs: Dict[str, Dict[str, str]], item: Dict[str, Any], pass_name: str,
                block: int) -> str:
    key = "position" if pass_name == "position" else "primary"
    arm_ids = item[key][block]
    return build_message(base, articles[item["item_id"]], [outputs[a][item["item_id"]]
                                                          for a in arm_ids])


def freeze(manifest: Dict[str, Any], sets_dir: Path = SETS) -> Path:
    """Write the manifest once; an existing one with the same id must match byte for byte."""
    path = sets_dir / f"{manifest['judging_set_id']}.json"
    if path.is_file():
        if read_json(path).get("judging_set_sha256") != manifest["judging_set_sha256"]:
            die(f"{path.name} exists with a different hash: a frozen judging set is never "
                f"rewritten")
    else:
        write_json(path, manifest)
    return path


# ── verdicts ─────────────────────────────────────────────────────────────────
def judge_fingerprint(j: Dict[str, Any]) -> str:
    """Identity of a judge: its params. The cost cap and the controls are not part of it."""
    return _sha(_canon({"id": j["id"], "params": j["params"]}))[:16]


def verdict_path(vdir: Path, judge_id: str, item_id: str, pass_name: str, block: int) -> Path:
    return vdir / judge_id / f"{item_id}.{pass_name}.b{block}.json"


def tasks(manifest: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str, int]]:
    """Every (item, pass, block), in the order money should be spent: the primary pass over
    all items first, so a cap that bites leaves whole items rather than a few items with
    every control."""
    by_id = {it["item_id"]: it for it in manifest["items"]}
    out = [(it, "primary", b) for it in manifest["items"] for b in range(len(it["primary"]))]
    for name, ids in (("position", manifest["position_items"]), ("noise", manifest["noise_items"])):
        out += [(by_id[i], name, b) for i in ids
                for b in range(len(by_id[i]["position" if name == "position" else "primary"]))]
    return out


def stored_cost(vdir: Path) -> float:
    total = 0.0
    for f in vdir.glob("*/*.json"):
        try:
            total += float(read_json(f).get("cost_usd") or 0.0)
        except (OSError, ValueError):
            pass
    return total


def run_judging(manifest: Dict[str, Any], sc: Dict[str, Any], base: str,
                articles: Dict[str, str], outputs: Dict[str, Dict[str, str]], vdir: Path,
                call: Optional[Callable[[str, Dict[str, Any]], Any]],
                cap: Optional[float], retry_unparsed: bool = False,
                log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Run every judge over every block not already stored. Never loses a paid verdict:
    each is written atomically before the next call. `call=None` only re-reads."""
    spent = stored_cost(vdir)
    stats = {"calls": 0, "skipped": 0, "missing": 0, "aborted": False, "spent_usd": spent,
             "cap_usd": cap, "billed_this_run": 0.0}
    work = tasks(manifest)
    try:
        for item, pass_name, block in work:
            msg = None
            for j in sc["judges"]:
                path = verdict_path(vdir, j["id"], item["item_id"], pass_name, block)
                if path.is_file():
                    old = read_json(path)
                    if old.get("judge_fp") != judge_fingerprint(j):
                        die(f"{path}: stored by a different judge definition than "
                            f"{j['id']!r} in the scorer now; refusing to mix them")
                    if old.get("set_id") != manifest["judging_set_id"]:
                        die(f"{path}: belongs to judging set {old.get('set_id')}")
                    if old.get("scores") is not None or not retry_unparsed:
                        stats["skipped"] += 1
                        continue
                if call is None:
                    stats["missing"] += 1
                    continue
                if cap is not None and spent >= cap:
                    raise CostCapExceeded(f"spent ${spent:.4f} of the ${cap:.4f} cap")
                if msg is None:
                    msg = message_for(manifest, base, articles, outputs, item, pass_name, block)
                n = len(item["position" if pass_name == "position" else "primary"][block])
                res = call_with_retries(
                    call, (msg, dict(j["params"])),
                    label=f"{j['id']} {item['item_id'][:8]} {pass_name} b{block}")
                cost = float(res.cost_usd) if getattr(res, "cost_usd", None) is not None else 0.0
                meta = getattr(res, "meta", None) or {}
                scores = parse_block(res.output, n)
                write_json(path, {
                    "set_id": manifest["judging_set_id"], "judge": j["id"],
                    "judge_fp": judge_fingerprint(j), "item_id": item["item_id"],
                    "pass": pass_name, "block": block, "n": n,
                    "prompt_sha256": _sha(msg), "output": res.output,
                    "scores": scores, "tokens_in": res.tokens_in, "tokens_out": res.tokens_out,
                    "cost_usd": cost, "cost_known": getattr(res, "cost_usd", None) is not None,
                    "latency_ms": getattr(res, "latency_ms", None),
                    "truncated": (getattr(res, "extra", None) or {}).get("truncated"),
                    "finish_reason": meta.get("finish_reason"),
                    "provider": meta.get("provider"), "response_model": meta.get("response_model"),
                    "created_at": now()})
                spent += cost
                stats["billed_this_run"] += cost
                stats["calls"] += 1
                if scores is None:
                    log(f"    unparsed reply: {j['id']} {item['item_id'][:8]} {pass_name} b{block}")
                elif stats["calls"] % 25 == 0:
                    log(f"    {stats['calls']} calls, ${spent:.4f}")
    except CostCapExceeded as exc:
        stats["aborted"] = True
        log(f"  COST CAP: {exc}. Stopping; every stored verdict is kept and re-read for $0.")
    stats["spent_usd"] = spent
    return stats


# ── projection ───────────────────────────────────────────────────────────────
def load_scores(manifest: Dict[str, Any], sc: Dict[str, Any], vdir: Path
                ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
    """{judge: {pass: {item: {arm: score}}}} for the items whose every block parsed."""
    out: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    for j in sc["judges"]:
        out[j["id"]] = {p: {} for p in PASSES}
        for it in manifest["items"]:
            for p in PASSES:
                key = "position" if p == "position" else "primary"
                got: Dict[str, float] = {}
                ok = True
                for b, arm_ids in enumerate(it[key]):
                    f = verdict_path(vdir, j["id"], it["item_id"], p, b)
                    s = read_json(f).get("scores") if f.is_file() else None
                    if s is None:
                        ok = False
                        break
                    got.update(dict(zip(arm_ids, s)))
                if ok:
                    out[j["id"]][p][it["item_id"]] = got
    return out


def project(sc: Dict[str, Any], scores: Dict[str, Dict[str, Dict[str, Dict[str, float]]]],
            item_ids: Sequence[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """{item: {arm: {judge_id: s, '_mean': mean over judges}}}, only for items EVERY judge
    completed: a mean over a different set of judges per item would not be one measurement."""
    jids = [j["id"] for j in sc["judges"]]
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for i in item_ids:
        if not all(i in scores[j]["primary"] for j in jids):
            continue
        arms = scores[jids[0]]["primary"][i].keys()
        out[i] = {a: {**{j: scores[j]["primary"][i][a] for j in jids},
                      "_mean": statistics.fmean(scores[j]["primary"][i][a] for j in jids)}
                  for a in arms}
    return out


def _tau(a: List[float], b: List[float]) -> Optional[float]:
    v = summeval_adapter().kendall_tau_b(a, b)
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _mean(xs: Sequence[Optional[float]]) -> Optional[float]:
    v = [x for x in xs if x is not None]
    return round(statistics.fmean(v), 6) if v else None


def compare_passes(a: Dict[str, Dict[str, float]], b: Dict[str, Dict[str, float]]
                   ) -> Dict[str, Any]:
    """Two readings of the same arms on the same items: per-item tau across arms, and the
    mean absolute difference in score."""
    ids = [i for i in a if i in b]
    taus, diffs = [], []
    for i in ids:
        arms = sorted(a[i])
        taus.append(_tau([a[i][x] for x in arms], [b[i][x] for x in arms]))
        diffs += [abs(a[i][x] - b[i][x]) for x in arms]
    return {"n_items": len(ids), "mean_tau": _mean(taus),
            "mean_abs_diff": round(statistics.fmean(diffs), 6) if diffs else None}


def summarise(manifest: Dict[str, Any], sc: Dict[str, Any], arms: Sequence[Dict[str, Any]],
              scores: Dict[str, Any], proj: Dict[str, Dict[str, Dict[str, float]]],
              stats: Dict[str, Any], label: str, validated: bool, vdir: Path) -> Dict[str, Any]:
    jids = [j["id"] for j in sc["judges"]]
    fam = {j["id"]: j["params"].get("family") for j in sc["judges"]}
    thr = float(sc["protocol"].get("contested_threshold", 0.5))
    per_arm = {}
    for a in arms:
        cid = a["config_id"]
        col = {j: _mean([proj[i][cid][j] for i in proj]) for j in jids}
        pm = _mean([proj[i][cid]["_mean"] for i in proj])
        vals = [v for v in col.values() if v is not None]
        per_arm[cid] = {
            "family": a.get("family"), "judge_score": pm, **{f"judge_{j}": col[j] for j in jids},
            "self_family": {j: a.get("family") == fam[j] for j in jids},
            "contested": bool(len(vals) > 1 and max(vals) - min(vals) > thr)}
    agreement = {}
    for x in range(len(jids)):
        for y in range(x + 1, len(jids)):
            ja, jb = jids[x], jids[y]
            taus = []
            for i in proj:
                arm_ids = sorted(proj[i])
                taus.append(_tau([proj[i][c][ja] for c in arm_ids], [proj[i][c][jb] for c in arm_ids]))
            ma = [per_arm[c][f"judge_{ja}"] for c in per_arm]
            mb = [per_arm[c][f"judge_{jb}"] for c in per_arm]
            agreement[f"{ja}~{jb}"] = {
                "n_items": len(proj), "mean_item_tau": _mean(taus),
                "arm_mean_spearman": (round(summeval_adapter().spearman(ma, mb), 6)
                                      if all(v is not None for v in ma + mb) and len(ma) > 2 else None),
                "arm_mean_abs_diff": _mean([abs(p - q) for p, q in zip(ma, mb)
                                            if p is not None and q is not None])}
    self_gap = {}
    for j in jids:
        own = [per_arm[c][f"judge_{j}"] for c in per_arm if per_arm[c]["self_family"][j]]
        oth = [per_arm[c][f"judge_{j}"] for c in per_arm if not per_arm[c]["self_family"][j]]
        own, oth = [v for v in own if v is not None], [v for v in oth if v is not None]
        self_gap[j] = {"own_family_arms": len(own),
                       "own_minus_others": round(statistics.fmean(own) - statistics.fmean(oth), 6)
                       if own and oth else None}
    ctrl = {}
    for j in jids:
        p = scores[j]
        ctrl[j] = {"position": compare_passes(p["primary"], p["position"]),
                   "noise": compare_passes(p["primary"], p["noise"])}
    calls = {}
    for j in jids:
        files = sorted((vdir / j).glob("*.json")) if (vdir / j).is_dir() else []
        vs = [read_json(f) for f in files]
        calls[j] = {"verdicts": len(vs), "unparsed": sum(1 for v in vs if v.get("scores") is None),
                    "truncated": sum(1 for v in vs if v.get("truncated")),
                    "billed_usd": round(sum(float(v.get("cost_usd") or 0) for v in vs), 6),
                    "cost_unknown": sum(1 for v in vs if not v.get("cost_known", True))}
    return {
        "scorer_id": sc["scorer_id"], "scorer_sha256": sc["_sha256"], "label": label,
        "validated": validated, "judging_set_id": manifest["judging_set_id"],
        "judging_set_sha256": manifest["judging_set_sha256"],
        "items_total": len(manifest["items"]), "items_scored": len(proj),
        "partial": len(proj) < len(manifest["items"]),
        "protocol": manifest["protocol"], "cost": stats, "per_judge": calls,
        "per_arm": per_arm, "judge_agreement": agreement,
        "self_family_gap": self_gap, "controls": ctrl,
        "notes": [
            "Each judge scored each item's arms in blocks; scores are absolute 1-5 per "
            "dimension and block scores are pooled. The position control re-forms the blocks.",
            "self_family: the arm and the judge are the same vendor family. own_minus_others "
            "is a raw gap, not a bias estimate: families differ in real quality.",
            f"contested: two judges' arm means differ by more than {thr} (the judge panel's rule).",
        ]}


# ── scored runs ──────────────────────────────────────────────────────────────
def write_scored_runs(manifest: Dict[str, Any], sc: Dict[str, Any], arms: Sequence[Dict[str, Any]],
                      proj: Dict[str, Dict[str, Dict[str, float]]], out_root: Path,
                      label: str, validated: bool, self_path: Path = Path(__file__)) -> List[Path]:
    """One directory per original run, same name, predictions.jsonl + metrics.json, shaped
    like rescore's so leaderboard / family_test / pair_test read them with EVAL_RUNS_DIR."""
    sfx = "" if validated else "_unvalidated"
    primary = f"judge_score{sfx}"
    jids = [j["id"] for j in sc["judges"]]
    fam = {j["id"]: j["params"].get("family") for j in sc["judges"]}
    written = []
    for a in arms:
        cid, src = a["config_id"], Path(a["dir"])
        m = read_json(src / "metrics.json")
        old_rows = {}
        for line in (src / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                old_rows[r["item_id"]] = r
        rows = []
        for i in manifest["items"]:
            iid = i["item_id"]
            if iid not in proj:
                continue
            cell = proj[iid][cid]
            row: Dict[str, Any] = {"item_id": iid, primary: round(cell["_mean"], 10)}
            for j in jids:
                row[f"judge_{j}{sfx}"] = round(cell[j], 10)
                row[f"self_family_{j}"] = 1.0 if a.get("family") == fam[j] else 0.0
            for k, v in (old_rows.get(iid) or {}).items():
                if k in CARRY or k.startswith("_"):
                    row[k] = v
            rows.append(row)
        keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
        scores = {k: round(statistics.fmean(float(r[k]) for r in rows if k in r), 10)
                  for k in keys} if rows else {}
        for k in ("cost_usd", "tokens_in", "tokens_out"):
            vals = [float(r[k]) for r in rows if k in r]
            if vals:
                scores[f"total_{k}"] = round(sum(vals), 8)
        kinds = {k: v for k, v in (m.get("metric_kinds") or {}).items() if k in scores}
        for k in keys:
            kinds[k] = "descriptive" if k.startswith("self_family_") else \
                kinds.get(k, "quality" if k.startswith("judge_") else "descriptive")
        run_dir = out_root / src.name
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        for f in (src / "outputs").glob("*.txt"):
            shutil.copy2(f, run_dir / "outputs" / f.name)
        write_text_atomic(run_dir / "predictions.jsonl",
                          "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        new = dict(m)
        new.update({
            "scores": scores, "metric_kinds": kinds, "primary_metric": primary,
            "n_items": len(rows), "judged_from": src.name, "judged_at": now(),
            "judge_label": label,
            "judged_with": {
                "scorer_id": sc["scorer_id"], "scorer_sha256": sc["_sha256"],
                "judging_set_id": manifest["judging_set_id"],
                "judging_set_sha256": manifest["judging_set_sha256"],
                "prompt_sha256_at_16": manifest["prompt_sha256_at_16"],
                "protocol": manifest["protocol"], "validated": validated,
                "judges": [{"id": j["id"], "model": j["params"].get("model"),
                            "family": j["params"].get("family"), "fp": judge_fingerprint(j)}
                           for j in sc["judges"]],
                "self_family": {j: a.get("family") == fam[j] for j in jids}},
        })
        fp = new.get("fingerprint")
        if isinstance(fp, dict):
            fp = json.loads(json.dumps(fp))
            fp.setdefault("instrument", {})["adapter"] = {
                "id": "scripts/judge_score.py",
                "sha256": hashlib.sha256(self_path.read_bytes()).hexdigest()}
            fp["hash"] = None
            fp["hash_invalid_because"] = (
                "scores were produced by a judge scorer, not the adapter this fingerprint "
                "was built from; see judged_with")
            new["fingerprint"] = fp
        write_json(run_dir / "metrics.json", new)
        written.append(run_dir)
    return written


# ── the dry run ──────────────────────────────────────────────────────────────
def estimate(manifest: Dict[str, Any], sc: Dict[str, Any], base: str, articles: Dict[str, str],
             outputs: Dict[str, Dict[str, str]], vdir: Path) -> Dict[str, Any]:
    per_judge = {j["id"]: {"calls": 0, "stored": 0, "tokens_in": 0, "tokens_out": 0}
                 for j in sc["judges"]}
    for item, p, b in tasks(manifest):
        msg = message_for(manifest, base, articles, outputs, item, p, b)
        n = len(item["position" if p == "position" else "primary"][b])
        for j in sc["judges"]:
            e = per_judge[j["id"]]
            if verdict_path(vdir, j["id"], item["item_id"], p, b).is_file():
                e["stored"] += 1
                continue
            e["calls"] += 1
            e["tokens_in"] += math.ceil(len(msg) / CHARS_PER_TOKEN)
            e["tokens_out"] += OUT_TOKENS_FIXED + OUT_TOKENS_PER_SUMMARY * n
    for j in sc["judges"]:
        e, pr = per_judge[j["id"]], j["params"]
        e["est_cost_usd"] = round(e["tokens_in"] / 1e6 * float(pr["usd_per_mtok_in"])
                                  + e["tokens_out"] / 1e6 * float(pr["usd_per_mtok_out"]), 4)
    return per_judge


def effective_cap(sc: Dict[str, Any]) -> Optional[float]:
    caps = [c for c in (sc.get("cost_cap_usd"), env_float("EVAL_MAX_COST_USD")) if c is not None]
    return min(float(c) for c in caps) if caps else None


# ── main ─────────────────────────────────────────────────────────────────────
def real_call(message: str, params: Dict[str, Any]) -> Any:
    return summeval_adapter()._litellm(message, {**params, "_raw_message": True})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--scorer", required=True, help="scorer id (data/scorers/<id>.yaml)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the judging set; print calls, tokens and estimated cost; call nothing")
    ap.add_argument("--unvalidated", action="store_true",
                    help="run a scorer the gate refuses; every number is labelled 'unvalidated judge'")
    ap.add_argument("--no-calls", action="store_true",
                    help="project from stored verdicts only; never call a judge ($0)")
    ap.add_argument("--retry-unparsed", action="store_true",
                    help="call again for stored verdicts whose reply did not parse")
    ap.add_argument("--match", help="arm set: config_id substring (default: scorer's arms_match or _n200_v1)")
    ap.add_argument("--out", type=Path, default=JUDGED)
    args = ap.parse_args()

    sc = load_scorer(SCORERS / f"{args.scorer}.yaml")
    if sc["dataset_id"] != args.dataset_id:
        die(f"scorer {sc['scorer_id']} is for dataset {sc['dataset_id']!r}, not {args.dataset_id!r}")
    problems = validation_problems(sc)
    validated = not problems
    if problems and not args.unvalidated:
        print(f"REFUSED: judge scorer {sc['scorer_id']} is not validated:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("  Fix the `validation` block, or pass --unvalidated to run it labelled "
              "'unvalidated judge'.", file=sys.stderr)
        return 3
    label = "validated judge" if validated else "unvalidated judge"
    if not validated:
        print(f"WARNING: UNVALIDATED JUDGE. Every number is labelled; {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")

    ds_file = DATA / "datasets" / f"{args.dataset_id}.json"
    if not ds_file.is_file():
        die(f"no dataset {args.dataset_id}")
    ds = read_json(ds_file)
    items = ds["items"]
    item_ids = [it["item_id"] for it in items]
    mat = MATERIALIZED / args.dataset_id
    articles = {}
    for it in items:
        f = mat / (it.get("source_path") or f"{it['item_id']}.txt")
        if not f.is_file():
            die(f"{f} is missing: materialize the dataset first "
                f"(make dataset-materialize DATASET_ID={args.dataset_id})")
        articles[it["item_id"]] = f.read_text(encoding="utf-8", errors="replace")
    arms = discover_arms(args.dataset_id, args.match or sc.get("arms_match", "_n200_v1"))
    if len(arms) < 2:
        die(f"found {len(arms)} arm run(s) on {args.dataset_id} in {RUNS}")
    outputs = {a["config_id"]: read_outputs(a, item_ids) for a in arms}
    base = prompt_text(sc)
    items_sha = (read_json(RUNS / arms[0]["run"] / "metrics.json").get("fingerprint", {})
                 .get("data", {}).get("items_sha256"))
    manifest = build_manifest(sc, args.dataset_id, items_sha, item_ids, arms, articles, outputs, base)
    sid = manifest["judging_set_id"]
    vdir = VERDICTS / sc["scorer_id"] / sid
    cap = effective_cap(sc)
    print(f"judging set  {sid}")
    print(f"  arms {len(arms)}, items {len(item_ids)}, blocks per item "
          f"{manifest['protocol']['block_sizes']}, position items {len(manifest['position_items'])}, "
          f"noise items {len(manifest['noise_items'])}")

    if args.dry_run:
        est = estimate(manifest, sc, base, articles, outputs, vdir)
        print(f"DRY RUN (nothing called; tokens are chars/{CHARS_PER_TOKEN} estimates, cost from "
              f"the scorer's price table)")
        tc = tt_in = tt_out = 0
        tcost = 0.0
        for jid, e in est.items():
            print(f"  judge {jid:8s} calls {e['calls']:5d} (stored {e['stored']})  "
                  f"tokens in {e['tokens_in']:>10,}  out {e['tokens_out']:>8,}  "
                  f"est ${e['est_cost_usd']:.4f}")
            tc += e["calls"]; tt_in += e["tokens_in"]; tt_out += e["tokens_out"]
            tcost += e["est_cost_usd"]
        print(f"  TOTAL        calls {tc:5d}  tokens in {tt_in:>10,}  out {tt_out:>8,}  "
              f"est ${tcost:.4f}   cap {('$%.2f' % cap) if cap is not None else 'NONE'}")
        return 0

    freeze(manifest)
    call = None if args.no_calls else real_call
    if call and cap is None:
        die("no cost cap: set cost_cap_usd in the scorer or EVAL_MAX_COST_USD")
    stats = run_judging(manifest, sc, base, articles, outputs, vdir, call, cap,
                        retry_unparsed=args.retry_unparsed)
    scores = load_scores(manifest, sc, vdir)
    proj = project(sc, scores, item_ids)
    out_root = args.out / sc["scorer_id"]
    if not proj:
        print("no item has a complete verdict from every judge; nothing to project")
        return 2 if stats["aborted"] else 1
    summ = summarise(manifest, sc, arms, scores, proj, stats, label, validated, vdir)
    written = write_scored_runs(manifest, sc, arms, proj, out_root, label, validated)
    write_json(out_root / "summary.json", summ)
    print(f"\n{len(written)} scored run(s) -> {out_root}  ({len(proj)}/{len(item_ids)} items, {label})")
    print(f"  calls {stats['calls']}, billed this run ${stats['billed_this_run']:.4f}, "
          f"stored total ${stats['spent_usd']:.4f}")
    print(f"  EVAL_RUNS_DIR={out_root} make leaderboard DATASET_ID={args.dataset_id}")
    if stats["aborted"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
