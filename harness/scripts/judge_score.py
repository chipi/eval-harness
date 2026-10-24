#!/usr/bin/env python3
"""Re-measure a frozen experiment with a validated LLM judge (docs/adr/ADR-0001).

    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1 ARGS=--dry-run
    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1
    EVAL_RUNS_DIR=data/runs-judged/judge-summ-v1 make leaderboard DATASET_ID=cnn_dailymail_200

`evh judge` is the older judge PANEL (judge_panel.py): pointwise, finalists only, verdicts not
stored. This is the judging PASS: listwise, every arm, verdicts stored as a frozen record.

THE PASS, IN ORDER
  1. gate       the scorer must name a committed run that validates each judge (or
                --unvalidated, which labels every number "unvalidated").
  2. judging set  one item = the source + every arm's output for it. Arm identities are
                hidden and the order is shuffled per item with a seed. The arm set, the
                outputs, the seed and the block size are hashed into the set's id, and the
                manifest is written to data/judging-sets/. Listwise scores depend on who
                else is in the list, so a different arm set is a different set, never an
                append.
  3. verdicts   each judge reads each block and answers with JSON scores; the raw reply is
                stored per call under data/judge-verdicts/, written atomically, so a rerun
                skips what is stored (resume) and re-reading costs $0. Cost-capped mid-run;
                what was bought is kept.
  4. projection one score per arm per item (mean of the task's dimensions, per judge; the
                primary is the mean over judges) written as scored runs, shaped like
                rescore's, plus summary.json with the controls.

THE TASK. What is judged comes from the scorer's optional `task` block: the label of the
source item, the label of the numbered outputs, the dimensions and the scale. Without one it
is SummEval's (ARTICLE, SUMMARIES, coherence/consistency/fluency/relevance, 1-5), which the
committed summarisation scorer uses. A declared task is part of the judging set's hash.

BLOCKS. SummEval validated 16 summaries per call. With more arms than that, an item is
judged in the fewest blocks of at most `outputs_per_call`, sizes as equal as possible: 29
arms are 15 + 14, never 16 + 13, so no call is further from the validated size than it must
be, and no block is a runt. Arms are assigned to blocks by the per-item shuffle, so a block
is a random sample of the arms and the blocks of an item are exchangeable. The judge scores
each output on an ABSOLUTE scale per dimension, not a rank within the block, which is
what lets scores from different blocks be averaged together. That is an assumption, and the
position check tests it: its second shuffle re-forms the blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable

from _codeid import content_sha256, file_sha256
from _common import (
    BOOKKEEPING_PREFIXES,
    DATA,
    MATERIALIZED,
    ROOT,
    RUNS,
    CostCapExceeded,
    die,
    env_float,
    how,
    in_checkout,
    now,
    read_json,
    write_json,
    write_text_atomic,
)
from _record import aggregate_scores, derived_record
from _retry import call_with_retries
from _runs import mixed_versions, runs_on
from judging import (
    DIMS,
    FAKE,
    build_message,
    call_judge,
    kendall_tau_b,
    parse_block,
    render_prompt,  # noqa: F401 — re-exported: validate_tree and the tests call js.render_prompt
    shingles,
    spearman,
    task_of,
    withheld_reason,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

SCORERS = DATA / "scorers"
SETS = DATA / "judging-sets"
VERDICTS = DATA / "judge-verdicts"
JUDGED = DATA / "runs-judged"

PASSES = ("primary", "position", "noise")


class JudgeCallFailed(Exception):
    """A judge call failed after its retries, or was refused (a provider budget, a policy)."""


#: Describe the CALL that made an arm's output, not how it was measured: carried across as
#: rescore.py carries them.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd", "truncated", "reasoning_tokens")
#: Reply size per summary for the dry-run estimate: SummEval's gemma_l returned 217.5 tokens
#: for 16 summaries x 4 dimensions (committed run se_gemma_l_n100_v1, scores.tokens_out).
#: A task with other dimensions scales it by their number.
OUT_TOKENS_PER_SUMMARY = 14
OUT_TOKENS_FIXED = 10
CHARS_PER_TOKEN = 4


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def records_sha256(vdir: Path) -> str:
    """One hash over a judge's stored validation records (names and bytes, sorted), so a
    report built from them can be checked against them where the human data is absent."""
    h = hashlib.sha256()
    for f in sorted(p for p in vdir.glob("*.json") if p.name != "report.json"):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ── the scorer artifact and the validation gate ──────────────────────────────
def load_scorer(path: Path) -> dict[str, Any]:
    """Load and validate a judge scorer YAML file; die on schema or missing judges."""
    if not path.is_file():
        die(f"no such scorer: {path}")
    sc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Its content, not its bytes: a comment in the YAML is documentation and changes no judgement.
    sc["_sha256"] = content_sha256(sc)
    sc["_dir"] = str(path.resolve().parent)
    if sc.get("kind") != "judge":
        die(f"{path.name}: kind must be 'judge', got {sc.get('kind')!r}")
    for k in ("scorer_id", "dataset_id", "judges", "prompt", "protocol"):
        if not sc.get(k):
            die(f"{path.name}: missing {k!r}")
    fams = {j["params"].get("family") for j in sc["judges"]}
    if len(sc["judges"]) < 2 or len(fams) < 2:
        die(
            f"{path.name}: needs at least two judges from different vendor families "
            f"(ADR-0001 §4); got {sorted(map(str, fams))}"
        )
    try:
        sc["_task"] = task_of(sc)
    except ValueError as exc:
        die(f"{path.name}: {exc}")
    return sc


def task_for(sc: dict[str, Any]) -> dict[str, Any]:
    """The scorer's checked task: set by load_scorer, derived here for a scorer built in code."""
    if "_task" not in sc:
        try:
            sc["_task"] = task_of(sc)
        except ValueError as exc:
            die(f"scorer {sc.get('scorer_id')}: {exc}")
    return sc["_task"]


def judge_params(sc: dict[str, Any], j: dict[str, Any]) -> dict[str, Any]:
    """What a judge is called with. A fake judge is also told the task, to answer in its
    shape; a real one is not (its request carries only its own params)."""
    p = dict(j["params"])
    if p.get("provider") == FAKE:
        p["_task"] = task_for(sc)
    return p


def prompt_candidates(sc: dict[str, Any], root: Path | None = None) -> list[Path]:
    """Where a scorer's `prompt.file` may be, in the order it is looked for.

    An absolute path is taken as written. A relative one resolves against the PROJECT root
    (EVAL_HOME, else the harness checkout), then the directory of the scorer file that names
    it, and, only in a checkout of this repository, the repository root, which is where the
    committed scorers' `examples/...` paths point. `root` replaces all of that with one base.
    """
    f = Path(sc["prompt"]["file"])
    if f.is_absolute():
        return [f]
    if root is not None:
        return [root / f]
    out = [ROOT / f]
    if sc.get("_dir"):
        out.append(Path(sc["_dir"]) / f)
    if in_checkout():
        out.append(ROOT.parent / f)
    return out


def prompt_text(sc: dict[str, Any], root: Path | None = None) -> str:
    """Read the scorer's prompt file; die if it is not found."""
    cands = prompt_candidates(sc, root)
    p = next((c for c in cands if c.is_file()), None)
    if p is None:
        die(f"prompt file not found: {sc['prompt']['file']} (looked in {', '.join(str(c) for c in cands)})")
    return p.read_text(encoding="utf-8").strip()


#: Params that change what a judge says. The validation run recorded them; the scorer must
#: still carry the same ones, or the number it cites was measured on a different judge.
OUTPUT_PARAMS = ("provider", "model", "temperature", "reasoning", "max_tokens")


def validation_problems(
    sc: dict[str, Any], runs_dir: Path = RUNS, prompt_root: Path | None = None
) -> list[str]:
    """Why this scorer is not validated; empty means it is."""
    fakes = [j["id"] for j in sc["judges"] if j["params"].get("provider") == FAKE]
    if fakes:
        return [f"judge {i!r} uses provider: fake, a stand-in that can never be validated" for i in fakes]
    v = sc.get("validation")
    if not isinstance(v, dict) or not v.get("runs"):
        return ["no `validation` block naming a committed run"]
    out: list[str] = []
    metric = v.get("metric")
    named = {r.get("judge"): r for r in v["runs"] if isinstance(r, dict)}
    want = sc["prompt"].get("sha256_at_16") or ""
    have = _sha(prompt_text(sc, prompt_root))
    if not want:
        out.append("prompt.sha256_at_16 is required once a `validation` block exists")
    elif want != have:
        out.append(
            "prompt.sha256_at_16 does not match the prompt file: the text the "
            "judges were validated on has changed"
        )
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
            out.append(
                f"judge {j['id']!r}: run {r['run']} is on {m.get('dataset_id')!r}, not {v['experiment']!r}"
            )
        got = (m.get("scores") or {}).get(metric)
        if got is None or r.get("value") is None or abs(float(got) - float(r["value"])) > 1e-6:
            out.append(
                f"judge {j['id']!r}: run {r['run']} has {metric}={got}, scorer claims {r.get('value')}"
            )
        floor = r.get("min_metric", v.get("min_metric"))
        if floor is not None and (got is None or float(got) < float(floor)):
            out.append(
                f"judge {j['id']!r}: run {r['run']} has {metric}={got}, below the scorer's min_metric {floor}"
            )
        rec = m.get("params") or {}
        for k in OUTPUT_PARAMS:
            if rec.get(k) != j["params"].get(k):
                out.append(
                    f"judge {j['id']!r}: run {r['run']} measured {k}={rec.get(k)!r}, "
                    f"the scorer uses {j['params'].get(k)!r}"
                )
        if rec.get("prompt_file") != Path(sc["prompt"]["file"]).name:
            out.append(
                f"judge {j['id']!r}: run {r['run']} used prompt file "
                f"{rec.get('prompt_file')!r}, the scorer uses {Path(sc['prompt']['file']).name!r}"
            )
        ran = (((m.get("fingerprint") or {}).get("system_under_test") or {}).get("model") or {}).get(
            "prompt_sha256"
        )
        if not ran:
            out.append(f"judge {j['id']!r}: run {r['run']} records no prompt sha256")
        elif want and ran != want:
            out.append(
                f"judge {j['id']!r}: run {r['run']} used prompt {ran[:12]}, the scorer names {want[:12]}"
            )
    return out


def validated_label(sc: dict[str, Any]) -> str:
    """Says where the validation was done, not that the judge is valid for this use."""
    exp = (sc.get("validation") or {}).get("experiment")
    return (
        f"validated on {exp} (provenance)" if exp else "validated by the runs its scorer names (provenance)"
    )


# ── order, blocks, subsets ───────────────────────────────────────────────────
def block_sizes(n_outputs: int, per_call: int) -> list[int]:
    """Fewest blocks of at most per_call, as equal as possible: 29, 16 -> [15, 14]."""
    k = max(1, math.ceil(n_outputs / per_call))
    base, extra = divmod(n_outputs, k)
    return [base + 1] * extra + [base] * (k - extra)


def shuffled(arm_ids: Sequence[str], seed: Any, salt: str, item_id: str) -> list[str]:
    """The arms in a hashed order: different for each item and pass (salt), the same on a rerun."""
    return sorted(arm_ids, key=lambda a: _sha(f"{seed}|{salt}|{item_id}|{a}"))


def blocks_for(arm_ids: Sequence[str], seed: Any, salt: str, item_id: str, per_call: int) -> list[list[str]]:
    """Partition shuffled arms into balanced blocks (fewest blocks, roughly equal sizes)."""
    order = shuffled(arm_ids, seed, salt, item_id)
    out, i = [], 0
    for s in block_sizes(len(order), per_call):
        out.append(order[i : i + s])
        i += s
    return out


def pick_subset(item_ids: Sequence[str], frac: float, seed: Any, salt: str) -> list[str]:
    """Deterministically select a fraction of items (seeded by salt); empty list if frac <= 0."""
    if not frac or frac <= 0:
        return []
    k = min(len(item_ids), max(1, round(frac * len(item_ids))))
    chosen = set(sorted(item_ids, key=lambda i: _sha(f"{seed}|{salt}|{i}"))[:k])
    return [i for i in item_ids if i in chosen]


# ── arms and the judging set ─────────────────────────────────────────────────
def discover_arms(dataset_id: str, match: str, runs_dir: Path = RUNS) -> list[dict[str, Any]]:
    """The primary run of every arm on the dataset: config_id contains `match`, latest wins."""
    latest: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    # One run per arm, the latest, on purpose: judging scores an arm's outputs, so repeats
    # are not averaged as they are everywhere else (_runs.per_item).
    for d, m in runs_on(dataset_id, runs_dir=runs_dir, match=match or None):
        cid = m["config_id"]
        key = m.get("created_at", "") + d.name
        if cid not in latest or key > latest[cid][0]:
            latest[cid] = (key, d, m)
    arms = []
    for cid, (_k, d, m) in sorted(latest.items()):
        arms.append(
            {
                "config_id": cid,
                "run": d.name,
                "dir": d,
                "family": (m.get("params") or {}).get("family")
                or (m.get("fingerprint", {}).get("arm", {}).get("params") or {}).get("family"),
            }
        )
    return arms


def config_versions(arms: Sequence[dict[str, Any]]) -> list[str]:
    """The `_vN` endings of each arm present at more than one version (`_runs.mixed_versions`,
    the leaderboard's rule): v1 and v2 of one arm, judged as two. [] when there is no such arm."""
    return sorted({v for vs in mixed_versions(a["config_id"] for a in arms).values() for v in vs})


def select_arms(arms: Sequence[dict[str, Any]], spec: str) -> list[dict[str, Any]]:
    """Restrict to the comma-separated tokens: an exact config_id, else a substring of one.
    A token that matches nothing is an error, not a smaller set."""
    keep: list[dict[str, Any]] = []
    for tok in [t.strip() for t in spec.split(",") if t.strip()]:
        exact = [a for a in arms if a["config_id"] == tok]
        hit = exact or [a for a in arms if tok in a["config_id"]]
        if not hit:
            die(f"--arms {tok!r} matches none of the {len(arms)} discovered arms")
        keep += [a for a in hit if a not in keep]
    return sorted(keep, key=lambda a: a["config_id"])


def read_outputs(arm: dict[str, Any], item_ids: Sequence[str]) -> dict[str, str]:
    """All outputs of one arm; die if any item's file is missing."""
    out = {}
    for i in item_ids:
        f = Path(arm["dir"]) / "outputs" / f"{i}.txt"
        if not f.is_file():
            die(
                f"{arm['run']}: no stored output for {i} — the judging set needs every "
                f"arm's output for every item"
            )
        out[i] = f.read_text(encoding="utf-8")
    return out


def build_manifest(
    sc: dict[str, Any],
    dataset_id: str,
    items_sha256: str | None,
    item_ids: Sequence[str],
    arms: Sequence[dict[str, Any]],
    articles: dict[str, str],
    outputs: dict[str, dict[str, str]],
    base_prompt: str,
) -> dict[str, Any]:
    """The frozen judging set. `outputs[config_id][item_id]` is that arm's text."""
    pr = sc["protocol"]
    seed, per_call = pr.get("order_seed", 0), int(pr["outputs_per_call"])
    arm_ids = [a["config_id"] for a in arms]
    if len(arm_ids) < 2:
        die("a judging set needs at least two arms")
    items = []
    for i in item_ids:
        items.append(
            {
                "item_id": i,
                "article_sha256": _sha(articles[i]),
                "primary": blocks_for(arm_ids, seed, "primary", i, per_call),
                "position": blocks_for(arm_ids, seed, "position", i, per_call),
            }
        )
    body = {
        "dataset_id": dataset_id,
        "dataset_items_sha256": items_sha256,
        "arms": [
            {
                "config_id": a["config_id"],
                "run": a["run"],
                "family": a.get("family"),
                "outputs_sha256": _sha(_canon([[i, _sha(outputs[a["config_id"]][i])] for i in item_ids])),
            }
            for a in arms
        ],
        "protocol": {
            "outputs_per_call": per_call,
            "blinding": bool(pr.get("blinding", True)),
            "order_seed": seed,
            "block_sizes": block_sizes(len(arm_ids), per_call),
        },
        "prompt_sha256_at_16": _sha(base_prompt),
        # Only a declared task is hashed, so a scorer without one keeps the set id it had.
        **({"task": task_for(sc)} if sc.get("task") else {}),
        "items": items,
        "position_items": pick_subset(
            list(item_ids), pr.get("position_check_fraction", 0), seed, "position-subset"
        ),
        "noise_items": pick_subset(list(item_ids), pr.get("noise_check_fraction", 0), seed, "noise-subset"),
    }
    digest = _sha(_canon(body))
    return {
        "judging_set_id": f"{dataset_id}-{len(arm_ids)}arms-{digest[:12]}",
        "judging_set_sha256": digest,
        **body,
    }


def manifest_hash(manifest: dict[str, Any]) -> str:
    """Recompute a stored manifest's hash: everything but the two identity fields."""
    return _sha(
        _canon({k: v for k, v in manifest.items() if k not in ("judging_set_id", "judging_set_sha256")})
    )


def message_for(
    manifest: dict[str, Any],
    base: str,
    articles: dict[str, str],
    outputs: dict[str, dict[str, str]],
    item: dict[str, Any],
    pass_name: str,
    block: int,
) -> str:
    """Build the judge prompt for this item's block in this pass."""
    key = "position" if pass_name == "position" else "primary"  # noqa: S105 — a judging pass, not a password
    arm_ids = item[key][block]
    task = manifest.get("task") or task_of({})
    return build_message(
        base,
        articles[item["item_id"]],
        [outputs[a][item["item_id"]] for a in arm_ids],
        task["source_label"],
        task["output_label"],
    )


def freeze(manifest: dict[str, Any], sets_dir: Path = SETS) -> Path:
    """Write the manifest once; an existing one with the same id must match byte for byte."""
    path = sets_dir / f"{manifest['judging_set_id']}.json"
    if path.is_file():
        if read_json(path).get("judging_set_sha256") != manifest["judging_set_sha256"]:
            die(f"{path.name} exists with a different hash: a frozen judging set is never rewritten")
    else:
        write_json(path, manifest)
    return path


# ── verdicts ─────────────────────────────────────────────────────────────────
def judge_fingerprint(j: dict[str, Any]) -> str:
    """Identity of a judge: its params. The cost cap and the controls are not part of it."""
    return _sha(_canon({"id": j["id"], "params": j["params"]}))[:16]


def call_cost(res: Any, params: dict[str, Any]) -> tuple[float | None, bool]:
    """(cost, known). A reply with no `cost_usd` is unknown, not free: it is counted at the
    scorer's price table from the token counts (known=False), and if there are none either
    the cost is None and the caller must stop, because the cap can no longer be enforced."""
    c = getattr(res, "cost_usd", None)
    if c is not None:
        return float(c), True
    tin, tout = getattr(res, "tokens_in", None), getattr(res, "tokens_out", None)
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if tin is None or tout is None or pin is None or pout is None:
        return None, False
    return float(tin) / 1e6 * float(pin) + float(tout) / 1e6 * float(pout), False


def verdict_path(vdir: Path, judge_id: str, item_id: str, pass_name: str, block: int) -> Path:
    """Path to a judge's stored verdict for one item's block in one pass."""
    return vdir / judge_id / f"{item_id}.{pass_name}.b{block}.json"


def tasks(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], str, int]]:
    """Every (item, pass, block), in the order money should be spent: the primary pass over
    all items first, so a cap that bites leaves whole items rather than a few items with
    every control."""
    by_id = {it["item_id"]: it for it in manifest["items"]}
    out = [(it, "primary", b) for it in manifest["items"] for b in range(len(it["primary"]))]
    for name, ids in (("position", manifest["position_items"]), ("noise", manifest["noise_items"])):
        out += [
            (by_id[i], name, b)
            for i in ids
            for b in range(len(by_id[i]["position" if name == "position" else "primary"]))
        ]
    return out


def stored_cost(vdir: Path) -> float:
    """Sum cost_usd over all verdicts in the judge directory."""
    total = 0.0
    for f in vdir.glob("*/*.json"):
        try:
            total += float(read_json(f).get("cost_usd") or 0.0)
        except (OSError, ValueError):
            pass
    return total


def run_judging(
    manifest: dict[str, Any],
    sc: dict[str, Any],
    base: str,
    articles: dict[str, str],
    outputs: dict[str, dict[str, str]],
    vdir: Path,
    call: Callable[[str, dict[str, Any]], Any] | None,
    cap: float | None,
    retry_unparsed: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run every judge over every block not already stored. Never loses a paid verdict:
    each is written atomically before the next call. `call=None` only re-reads."""
    spent = stored_cost(vdir)
    stats: dict = {
        "calls": 0,
        "skipped": 0,
        "missing": 0,
        "aborted": False,
        "spent_usd": spent,
        "cap_usd": cap,
        "billed_this_run": 0.0,
    }
    work = tasks(manifest)
    try:
        for item, pass_name, block in work:
            msg = None
            for j in sc["judges"]:
                path = verdict_path(vdir, j["id"], item["item_id"], pass_name, block)
                if path.is_file():
                    old = read_json(path)
                    if old.get("judge_fp") != judge_fingerprint(j):
                        die(
                            f"{path}: stored by a different judge definition than "
                            f"{j['id']!r} in the scorer now; refusing to mix them"
                        )
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
                n = len(item["position" if pass_name == "position" else "primary"][block])  # noqa: S105 — a judging pass, not a password
                took: list[float] = []

                def timed(m: str, prm: dict[str, Any], _call=call, _took=took) -> Any:
                    t0 = time.perf_counter()
                    try:
                        return _call(m, prm)
                    finally:
                        _took.append((time.perf_counter() - t0) * 1000.0)

                try:
                    res = call_with_retries(
                        timed,
                        (msg, judge_params(sc, j)),
                        label=f"{j['id']} {item['item_id'][:8]} {pass_name} b{block}",
                    )
                except SystemExit:
                    raise
                except Exception as exc:  # provider SDKs vary too much to enumerate
                    # Refused (e.g. a provider's own budget guardrail), or still failing after
                    # call_with_retries' retries. Stop like the cost cap does.
                    raise JudgeCallFailed(f"{j['id']}: {type(exc).__name__}: {str(exc)[:300]}") from exc
                est, known = call_cost(res, j["params"])
                cost = est if est is not None else 0.0
                meta = getattr(res, "meta", None) or {}
                scores = parse_block(res.output, n, task_for(sc)["dimensions"], task_for(sc)["scale"])
                arms = item["position" if pass_name == "position" else "primary"][block]  # noqa: S105 — a judging pass, not a password
                why = withheld_reason(
                    res.output,
                    shingles([articles[item["item_id"]], *(outputs[a][item["item_id"]] for a in arms)]),
                )
                # A retried block replaces the stored reply; the earlier calls were paid for
                # too, so their cost stays in the record (and in every bill read from it).
                prior = read_json(path) if path.is_file() else {}
                earlier = float(prior.get("cost_usd") or 0.0)
                write_json(
                    path,
                    {
                        "set_id": manifest["judging_set_id"],
                        "judge": j["id"],
                        "judge_fp": judge_fingerprint(j),
                        "item_id": item["item_id"],
                        "pass": pass_name,
                        "block": block,
                        "n": n,
                        "prompt_sha256": _sha(msg),
                        "output": None if why else res.output,
                        "output_sha256": _sha(res.output or ""),
                        "output_withheld": bool(why),
                        **({"withheld_reason": why} if why else {}),
                        "scores": scores,
                        "tokens_in": res.tokens_in,
                        "tokens_out": res.tokens_out,
                        "cost_usd": cost + earlier,
                        "cost_known": known and prior.get("cost_known", True),
                        **(
                            {
                                "attempts": int(prior.get("attempts") or 1) + 1,
                                "cost_usd_earlier_attempts": round(earlier, 8),
                            }
                            if prior
                            else {}
                        ),
                        "latency_ms": round(took[-1], 3),
                        "truncated": (getattr(res, "extra", None) or {}).get("truncated"),
                        "finish_reason": meta.get("finish_reason"),
                        "provider": meta.get("provider"),
                        "response_model": meta.get("response_model"),
                        "created_at": now(),
                    },
                )
                spent += cost
                stats["billed_this_run"] += cost
                stats["calls"] += 1
                if est is None:
                    raise CostCapExceeded(
                        f"{j['id']} returned no cost and no token counts: "
                        "the spend is unknown, so the cap cannot be enforced"
                    )
                if why:
                    log(
                        f"    reply not stored as text ({why}), only its hash: "
                        f"{j['id']} {item['item_id'][:8]} {pass_name} b{block}"
                    )
                if scores is None:
                    log(f"    unparsed reply: {j['id']} {item['item_id'][:8]} {pass_name} b{block}")
                elif stats["calls"] % 25 == 0:
                    log(f"    {stats['calls']} calls, ${spent:.4f}")
    except CostCapExceeded as exc:
        stats["aborted"] = True
        log(f"  COST CAP: {exc}. Stopping; every stored verdict is kept and re-read for $0.")
    except JudgeCallFailed as exc:
        stats["aborted"] = True
        stats["call_failed"] = str(exc)
        log(
            f"  JUDGE CALL FAILED after retries or refused: {exc}\n  Stopping; every stored verdict is kept. "
            "Fix the cause and run the same command again: it resumes where it stopped."
        )
    stats["spent_usd"] = spent
    return stats


# ── projection ───────────────────────────────────────────────────────────────
def load_scores(
    manifest: dict[str, Any], sc: dict[str, Any], vdir: Path
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """{judge: {pass: {item: {arm: score}}}} for the items whose every block parsed."""
    out: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for j in sc["judges"]:
        out[j["id"]] = {p: {} for p in PASSES}
        for it in manifest["items"]:
            for p in PASSES:
                key = "position" if p == "position" else "primary"
                got: dict[str, float] = {}
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


def project(
    sc: dict[str, Any], scores: dict[str, dict[str, dict[str, dict[str, float]]]], item_ids: Sequence[str]
) -> dict[str, dict[str, dict[str, float]]]:
    """{item: {arm: {judge_id: s, '_mean': mean over judges}}}, only for items EVERY judge
    completed: a mean over a different set of judges per item would not be one measurement."""
    jids = [j["id"] for j in sc["judges"]]
    out: dict[str, dict[str, dict[str, float]]] = {}
    for i in item_ids:
        if not all(i in scores[j]["primary"] for j in jids):
            continue
        arms = scores[jids[0]]["primary"][i].keys()
        out[i] = {
            a: {
                **{j: scores[j]["primary"][i][a] for j in jids},
                "_mean": statistics.fmean(scores[j]["primary"][i][a] for j in jids),
            }
            for a in arms
        }
    return out


def _mean(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return round(statistics.fmean(v), 6) if v else None


def compare_passes(a: dict[str, dict[str, float]], b: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Two readings of the same arms on the same items: per-item tau across arms, and the
    mean absolute difference in score."""
    ids = [i for i in a if i in b]
    taus, diffs = [], []
    for i in ids:
        arms = sorted(a[i])
        taus.append(kendall_tau_b([a[i][x] for x in arms], [b[i][x] for x in arms]))
        diffs += [abs(a[i][x] - b[i][x]) for x in arms]
    return {
        "n_items": len(ids),
        "mean_tau": _mean(taus),
        "mean_abs_diff": round(statistics.fmean(diffs), 6) if diffs else None,
    }


def summarise(
    manifest: dict[str, Any],
    sc: dict[str, Any],
    arms: Sequence[dict[str, Any]],
    scores: dict[str, Any],
    proj: dict[str, dict[str, dict[str, float]]],
    stats: dict[str, Any],
    label: str,
    validated: bool,
    vdir: Path,
) -> dict[str, Any]:
    """Summarize the judging: per-arm scores, judge agreement, controls, and cost."""
    jids = [j["id"] for j in sc["judges"]]
    fam = {j["id"]: j["params"].get("family") for j in sc["judges"]}
    thr = float(sc["protocol"].get("contested_threshold", 0.5))
    per_arm: dict = {}
    for a in arms:
        cid = a["config_id"]
        col = {j: _mean([proj[i][cid][j] for i in proj]) for j in jids}
        pm = _mean([proj[i][cid]["_mean"] for i in proj])
        vals = [v for v in col.values() if v is not None]
        per_arm[cid] = {
            "family": a.get("family"),
            "judge_score": pm,
            **{f"judge_{j}": col[j] for j in jids},
            "self_family": {j: a.get("family") == fam[j] for j in jids},
            "contested": bool(len(vals) > 1 and max(vals) - min(vals) > thr),
        }
    agreement = {}
    for x in range(len(jids)):
        for y in range(x + 1, len(jids)):
            ja, jb = jids[x], jids[y]
            taus = []
            for i in proj:
                arm_ids = sorted(proj[i])
                taus.append(
                    kendall_tau_b([proj[i][c][ja] for c in arm_ids], [proj[i][c][jb] for c in arm_ids])
                )
            ma = [per_arm[c][f"judge_{ja}"] for c in per_arm]
            mb = [per_arm[c][f"judge_{jb}"] for c in per_arm]
            agreement[f"{ja}~{jb}"] = {
                "n_items": len(proj),
                "mean_item_tau": _mean(taus),
                "arm_mean_spearman": (
                    round(spearman(ma, mb), 6)
                    if all(v is not None for v in ma + mb) and len(ma) > 2
                    else None
                ),
                "arm_mean_abs_diff": _mean(
                    [abs(p - q) for p, q in zip(ma, mb) if p is not None and q is not None]
                ),
            }
    self_gap = {}
    for j in jids:
        own = [per_arm[c][f"judge_{j}"] for c in per_arm if per_arm[c]["self_family"][j]]
        oth = [per_arm[c][f"judge_{j}"] for c in per_arm if not per_arm[c]["self_family"][j]]
        own, oth = [v for v in own if v is not None], [v for v in oth if v is not None]
        self_gap[j] = {
            "own_family_arms": len(own),
            "own_minus_others": round(statistics.fmean(own) - statistics.fmean(oth), 6)
            if own and oth
            else None,
        }
    ctrl = {}
    for j in jids:
        p = scores[j]
        ctrl[j] = {
            "position": compare_passes(p["primary"], p["position"]),
            "noise": compare_passes(p["primary"], p["noise"]),
        }
    calls = {}
    for j in jids:
        files = sorted((vdir / j).glob("*.json")) if (vdir / j).is_dir() else []
        vs = [read_json(f) for f in files]
        calls[j] = {
            "verdicts": len(vs),
            "unparsed": sum(1 for v in vs if v.get("scores") is None),
            "truncated": sum(1 for v in vs if v.get("truncated")),
            "billed_usd": round(sum(float(v.get("cost_usd") or 0) for v in vs), 6),
            "cost_unknown": sum(1 for v in vs if not v.get("cost_known", True)),
        }
    return {
        "scorer_id": sc["scorer_id"],
        "scorer_sha256": sc["_sha256"],
        "label": label,
        "validated": validated,
        "judging_set_id": manifest["judging_set_id"],
        "judging_set_sha256": manifest["judging_set_sha256"],
        "items_total": len(manifest["items"]),
        "items_scored": len(proj),
        "partial": len(proj) < len(manifest["items"]),
        "protocol": manifest["protocol"],
        "cost": stats,
        "per_judge": calls,
        "per_arm": per_arm,
        "judge_agreement": agreement,
        "self_family_gap": self_gap,
        "controls": ctrl,
        "notes": [
            (
                f"Each judge scored each item's arms in blocks; scores are absolute "
                f"{task_for(sc)['scale'][0]:g}-{task_for(sc)['scale'][1]:g} per "
                "dimension and block scores are pooled. The position control re-forms the blocks."
            ),
            (
                "self_family: the arm and the judge are the same vendor family. own_minus_others "
                "is a raw gap, not a bias estimate: families differ in real quality."
            ),
            f"contested: two judges' arm means differ by more than {thr} (the judge panel's rule).",
        ],
    }


# ── scored runs ──────────────────────────────────────────────────────────────
def write_scored_runs(
    manifest: dict[str, Any],
    sc: dict[str, Any],
    arms: Sequence[dict[str, Any]],
    proj: dict[str, dict[str, dict[str, float]]],
    out_root: Path,
    label: str,
    validated: bool,
    self_path: Path = Path(__file__),
) -> list[Path]:
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
            row: dict[str, Any] = {"item_id": iid, primary: round(cell["_mean"], 10)}
            for j in jids:
                row[f"judge_{j}{sfx}"] = round(cell[j], 10)
                row[f"self_family_{j}"] = 1.0 if a.get("family") == fam[j] else 0.0
            for k, v in (old_rows.get(iid) or {}).items():
                if k in CARRY or k.startswith("_"):
                    row[k] = v
            rows.append(row)
        keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
        scores = aggregate_scores(rows)
        kinds = {k: v for k, v in (m.get("metric_kinds") or {}).items() if k in scores}
        for k in keys:
            kinds[k] = (
                "descriptive"
                if k.startswith(BOOKKEEPING_PREFIXES)
                else kinds.get(k, "quality" if k.startswith("judge_") else "descriptive")
            )
        run_dir = out_root / src.name
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        for f in (src / "outputs").glob("*.txt"):
            shutil.copy2(f, run_dir / "outputs" / f.name)
        write_text_atomic(
            run_dir / "predictions.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        )
        # A judge reads no reference, so the source run's tier does not describe these scores;
        # it is kept, as the source's, in derived.with.
        source_tier = m.get("reference_tier")
        new = derived_record(
            m,
            kind="judge",
            source_dir=src.name,
            scores=scores,
            n_items=len(rows),
            drop=("reference_tier",),
            metric_kinds=kinds,
            primary_metric=primary,
            with_={
                "label": label,
                "scorer_id": sc["scorer_id"],
                "scorer_sha256": sc["_sha256"],
                "judging_set_id": manifest["judging_set_id"],
                "judging_set_sha256": manifest["judging_set_sha256"],
                "prompt_sha256_at_16": manifest["prompt_sha256_at_16"],
                "protocol": manifest["protocol"],
                "validated": validated,
                "judges": [
                    {
                        "id": j["id"],
                        "model": j["params"].get("model"),
                        "family": j["params"].get("family"),
                        "fp": judge_fingerprint(j),
                    }
                    for j in sc["judges"]
                ],
                "self_family": {j: a.get("family") == fam[j] for j in jids},
                "source_reference_tier": source_tier,
            },
        )
        fp = new.get("fingerprint")
        if isinstance(fp, dict):
            fp = json.loads(json.dumps(fp))
            fp.setdefault("instrument", {})["adapter"] = {
                "id": f"judge-score:{sc['scorer_id']}",
                # By behaviour (_codeid): documentation in judge_score.py is not a new scorer.
                "sha256": file_sha256(self_path),
            }
            fp["hash"] = None
            fp["hash_invalid_because"] = (
                "scores were produced by a judge scorer, not the adapter this fingerprint "
                "was built from; see derived.with"
            )
            new["fingerprint"] = fp
        write_json(run_dir / "metrics.json", new)
        written.append(run_dir)
    return written


# ── the dry run ──────────────────────────────────────────────────────────────
def estimate(
    manifest: dict[str, Any],
    sc: dict[str, Any],
    base: str,
    articles: dict[str, str],
    outputs: dict[str, dict[str, str]],
    vdir: Path,
) -> dict[str, Any]:
    """Estimate tokens and cost for dry-run output; counts already-stored verdicts."""
    per_judge: dict[str, dict] = {
        j["id"]: {"calls": 0, "stored": 0, "tokens_in": 0, "tokens_out": 0} for j in sc["judges"]
    }
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
            e["tokens_out"] += (
                OUT_TOKENS_FIXED
                + math.ceil(OUT_TOKENS_PER_SUMMARY * len(task_for(sc)["dimensions"]) / len(DIMS)) * n
            )
    for j in sc["judges"]:
        e, pr = per_judge[j["id"]], j["params"]
        e["est_cost_usd"] = round(
            e["tokens_in"] / 1e6 * float(pr["usd_per_mtok_in"])
            + e["tokens_out"] / 1e6 * float(pr["usd_per_mtok_out"]),
            4,
        )
    return per_judge


def effective_cap(sc: dict[str, Any]) -> float | None:
    """The smaller of the scorer's cost_cap_usd and EVAL_MAX_COST_USD, or None."""
    caps = [c for c in (sc.get("cost_cap_usd"), env_float("EVAL_MAX_COST_USD")) if c is not None]
    return min(float(c) for c in caps) if caps else None


# ── main ─────────────────────────────────────────────────────────────────────
def real_call(message: str, params: dict[str, Any]) -> Any:
    """Call a judge; the call_with_retries hook."""
    return call_judge(message, params)


def main() -> int:
    """Re-measure a frozen experiment with a validated LLM judge."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--scorer", required=True, help="scorer id (data/scorers/<id>.yaml)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="build the judging set; print calls, tokens and estimated cost; call nothing",
    )
    ap.add_argument(
        "--unvalidated",
        action="store_true",
        help="run a scorer the gate refuses; every number is labelled 'unvalidated judge'",
    )
    ap.add_argument(
        "--no-calls", action="store_true", help="project from stored verdicts only; never call a judge ($0)"
    )
    ap.add_argument(
        "--retry-unparsed",
        action="store_true",
        help="call again for stored verdicts whose reply did not parse",
    )
    ap.add_argument(
        "--match",
        help="arm set: config_id substring (default: the scorer's arms_match, else every arm on the dataset)",
    )
    ap.add_argument(
        "--arms",
        help="comma-separated config_ids or substrings: judge only these "
        "arms (a subset is its own judging set id)",
    )
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
        print(
            "  Fix the `validation` block, or pass --unvalidated to run it labelled 'unvalidated judge'.",
            file=sys.stderr,
        )
        return 3
    label = validated_label(sc) if validated else "unvalidated judge"
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
            die(
                f"{f} is missing: materialize the dataset first "
                f"({how(f'evh dataset-materialize --dataset-id {args.dataset_id}', f'make dataset-materialize DATASET_ID={args.dataset_id}')})"
            )
        articles[it["item_id"]] = f.read_text(encoding="utf-8", errors="replace")
    arms = discover_arms(args.dataset_id, args.match or sc.get("arms_match", ""))
    if args.arms:
        arms = select_arms(arms, args.arms)
    if len(arms) < 2:
        die(f"found {len(arms)} arm run(s) on {args.dataset_id} in {RUNS}")
    vers = config_versions(arms)
    if len(vers) > 1:
        print(
            f"WARNING: the arm set mixes config versions {', '.join(vers)}: v1 and v2 of one arm are "
            "judged as two arms. Narrow it with --match _v2 (or the scorer's arms_match) if that "
            "is not what you mean."
        )
    outputs = {a["config_id"]: read_outputs(a, item_ids) for a in arms}
    base = prompt_text(sc)
    items_sha = (
        read_json(RUNS / arms[0]["run"] / "metrics.json")
        .get("fingerprint", {})
        .get("data", {})
        .get("items_sha256")
    )
    manifest = build_manifest(sc, args.dataset_id, items_sha, item_ids, arms, articles, outputs, base)
    sid = manifest["judging_set_id"]
    vdir = VERDICTS / sc["scorer_id"] / sid
    cap = effective_cap(sc)
    print(f"judging set  {sid}")
    print(
        f"  arms {len(arms)}, items {len(item_ids)}, blocks per item "
        f"{manifest['protocol']['block_sizes']}, position items {len(manifest['position_items'])}, "
        f"noise items {len(manifest['noise_items'])}"
    )

    if args.dry_run:
        est = estimate(manifest, sc, base, articles, outputs, vdir)
        print(
            f"DRY RUN (nothing called; tokens are chars/{CHARS_PER_TOKEN} estimates, cost from "
            f"the scorer's price table)"
        )
        tc = tt_in = tt_out = 0
        tcost = 0.0
        for jid, e in est.items():
            print(
                f"  judge {jid:8s} calls {e['calls']:5d} (stored {e['stored']})  "
                f"tokens in {e['tokens_in']:>10,}  out {e['tokens_out']:>8,}  "
                f"est ${e['est_cost_usd']:.4f}"
            )
            tc += e["calls"]
            tt_in += e["tokens_in"]
            tt_out += e["tokens_out"]
            tcost += e["est_cost_usd"]
        print(
            f"  TOTAL        calls {tc:5d}  tokens in {tt_in:>10,}  out {tt_out:>8,}  "
            f"est ${tcost:.4f}   cap {(f'${cap:.2f}') if cap is not None else 'NONE'}"
        )
        return 0

    freeze(manifest)
    call = None if args.no_calls else real_call
    if call and cap is None:
        die("no cost cap: set cost_cap_usd in the scorer or EVAL_MAX_COST_USD")
    stats = run_judging(
        manifest, sc, base, articles, outputs, vdir, call, cap, retry_unparsed=args.retry_unparsed
    )
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
    print(
        f"  calls {stats['calls']}, billed this run ${stats['billed_this_run']:.4f}, "
        f"stored total ${stats['spent_usd']:.4f}"
    )
    print(
        f"  EVAL_RUNS_DIR={out_root} "
        + how(
            f"evh leaderboard --dataset-id {args.dataset_id}",
            f"make leaderboard DATASET_ID={args.dataset_id}",
        )
    )
    if stats["aborted"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
