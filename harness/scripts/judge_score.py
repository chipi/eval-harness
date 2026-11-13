#!/usr/bin/env python3
"""Re-measure a frozen eval with a validated LLM judge (docs/adr/ADR-0001).

    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1 ARGS=--dry-run
    make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1
    make leaderboard DATASET_ID=cnn_dailymail_200 ARGS='--label judged/judge-summ-v1'

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
                primary is the mean over judges) written as a score under each judged
                run (key <scorer>@<judging set>, label judged/<scorer>), plus
                data/judge-summaries/<scorer>@<judging set>.json with the controls.

THE TASK. What is judged comes from the scorer's optional `task` block: the label of the
source item, the label of the numbered outputs, the dimensions and the scale. Without one it
is SummEval's (ARTICLE, SUMMARIES, coherence/consistency/fluency/relevance, 1-5), which the
committed summarisation scorer uses. A declared task is part of the judging set's hash.

MODES. The scorer's `mode` is what a judge is asked: `grade` (the default, all of the above),
`pick` (one call per item: the best of every arm's output, `{"best": [3]}`) or `pairwise` (one
call per pair of arms: `{"better": 1}`). Pick and pairwise store `best` / `better` in place of
`scores`, project `won` per arm per item (judged runs' primary `judge_won`) and summarise win
rates and Bradley-Terry strengths. Only a declared non-default mode enters the judging set's hash.

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

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import itertools
import json
import math
import random
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable

from evaluation_harness import _jsonout, _outputs, _providers, _runs, _store
from evaluation_harness._codeid import content_sha256, file_sha256
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    DATA,
    EXIT_NOTHING,
    EXIT_STOPPED,
    EXIT_UNVALIDATED,
    MATERIALIZED,
    ROOT,
    CostCapExceeded,
    classify_metrics,
    dataset_id_ok,
    die,
    env_float,
    evh_prog,
    how,
    in_checkout,
    now,
    read_json,
    write_json,
)
from evaluation_harness._fingerprint import seal
from evaluation_harness._providers import identity_params
from evaluation_harness._record import aggregate_scores, derived_record
from evaluation_harness._retry import call_with_retries
from evaluation_harness._runs import mixed_versions, runs_on
from evaluation_harness.judging import (
    DEFAULT_MODE,
    DIMS,
    FAKE,
    MODES,
    build_message,
    build_pairwise_message,
    build_pick_message,
    call_judge,
    json_only,
    kendall_tau_b,
    parse_block,
    parse_pairwise,
    parse_pick,
    render_prompt,  # noqa: F401 — re-exported: validate_tree and the tests call js.render_prompt
    shingles,
    spearman,
    task_of,
    withheld_reason,
)
from evaluation_harness.model import runs as _model_runs

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt", "missing-dependency")

SCORERS = DATA / "scorers"
SETS = DATA / "judging-sets"
VERDICTS = DATA / "judge-verdicts"
SUMMARIES = DATA / "judge-summaries"

PASSES = ("primary", "position", "noise")

#: The key a verdict stores its parsed answer under, by mode.
VERDICT_KEY = {"grade": "scores", "pick": "best", "pairwise": "better"}
#: A pairwise outcome that is a tie (no arm id is empty).
TIE = ""
#: Bradley-Terry: bootstrap resamples of the items, the interval's coverage, and the virtual
#: draw between every two arms. The draw keeps an arm that never won (or never lost) at a finite
#: strength, which the maximum-likelihood fit does not have; its weight (half a comparison per
#: pair) is small against a real eval's thousands of comparisons.
BT_RESAMPLES = 1000
BT_COVERAGE = 0.95
BT_PRIOR = 0.5
BT_TOL = 1e-9
BT_MAX_ITER = 5000


class JudgeCallFailed(Exception):
    """A judge call failed after its retries, or was refused (a provider budget, a policy)."""


#: Describe the CALL that made an arm's output, not how it was measured: carried across as
#: rescore.py carries them.
CARRY = (
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "truncated",
    "reasoning_tokens",
    "resumed",
    "failed",
)
#: Reply size per summary for the dry-run estimate: SummEval's gemma_l returned 217.5 tokens
#: for 16 summaries x 4 dimensions (committed run se_gemma_l_n100_v1, scores.tokens_out).
#: A task with other dimensions scales it by their number.
OUT_TOKENS_PER_SUMMARY = 14
OUT_TOKENS_FIXED = 10
#: A pick or pairwise reply is one short JSON object ({"best": [3, 7]}, {"better": "tie"}).
OUT_TOKENS_ANSWER = 12
CHARS_PER_TOKEN = 4


def _keep_withheld(record: Path, text: str) -> Path:
    """A withheld reply's text in `<record dir>/.withheld/<record>.txt`, a directory that
    ignores itself in git: the record keeps only the hash, the text stays on this machine."""
    d = record.parent / ".withheld"
    _store.mkdir(d, parents=True, exist_ok=True)
    _store.write_text(d / ".gitignore", "*\n", encoding="utf-8")
    out = d / f"{record.stem}.txt"
    _store.write_text(out, text, encoding="utf-8")
    return out


def unparsed_cause(output: str | None, finish_reason: Any, mode: str) -> str:
    """Why a reply gave no verdict, for the line judge-score prints: empty, cut off at the
    token limit, not JSON, or JSON of the wrong shape, with its character count."""
    n = len(output or "")
    cut = finish_reason == "length"
    if not output:
        return (
            "empty, cut off at the token limit (finish_reason length), 0 chars"
            if cut
            else f"empty (finish_reason {finish_reason}), 0 chars"
        )
    if cut:
        return f"cut off at the token limit (finish_reason length), {n} chars"
    if not json_only(output):
        return f"not JSON, {n} chars"
    return f"JSON, but not the expected {VERDICT_KEY[mode]} (the shape the prompt asks for), {n} chars"


#: A judge whose first this-many replies all come back empty at the token limit stops the pass (JudgeCutOff).
EARLY_CUTOFF = 3


class JudgeCutOff(Exception):
    """A judge's first replies all came back empty at the token limit: the rest would too."""


def cutoff_hint(cut_empty: int, calls: int, sc: dict[str, Any]) -> str:
    """One line for a run whose replies came back empty at the token limit: a reasoning model
    spent its max_tokens thinking. Empty when none did."""
    if not cut_empty:
        return ""
    limits = ", ".join(sorted({str(j["params"].get("max_tokens", "default")) for j in sc["judges"]}))
    return (
        f"  HINT: {cut_empty} of {calls} replies this run ({100 * cut_empty // max(calls, 1)}%) came back empty, "
        f"cut off at the token limit (finish_reason length): a reasoning model spent its max_tokens "
        f"({limits}) thinking. Raise max_tokens in the scorer, or turn the model's reasoning off with "
        "`reasoning: {enabled: false}` in the judge's params (not for provider anthropic). Either "
        "changes the judge, so save it as a new scorer version (a new scorer_id) and run again."
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def records_sha256(vdir: Path) -> str:
    """One hash over a judge's stored validation records (names and bytes, sorted), so a
    report built from them can be checked against them where the human data is absent."""
    h = hashlib.sha256()
    for f in sorted(p for p in _store.glob(vdir, "*.json") if p.name != "report.json"):
        h.update(f.name.encode() + b"\0" + _store.read_bytes(f) + b"\0")
    return h.hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ── the scorer artifact and the validation gate ──────────────────────────────
def load_scorer(path: Path) -> dict[str, Any]:
    """Load and validate a judge scorer YAML file; die on schema or missing judges."""
    if not _store.is_file(path):
        die(f"no such scorer: {path}", "not-found")
    sc = yaml.safe_load(_store.read_text(path, encoding="utf-8")) or {}
    # Its content, not its bytes: a comment in the YAML is documentation and changes no judgement.
    sc["_sha256"] = content_sha256(sc)
    sc["_dir"] = str(path.resolve().parent)
    if sc.get("kind") != "judge":
        die(f"{path.name}: kind must be 'judge', got {sc.get('kind')!r}", "invalid-file")
    for k in ("scorer_id", "dataset_id", "judges", "prompt", "protocol"):
        if not sc.get(k):
            die(f"{path.name}: missing {k!r}", "invalid-file")
    fams = {j["params"].get("family") for j in sc["judges"]}
    if len(sc["judges"]) < 2 or len(fams) < 2:
        die(
            f"{path.name}: needs at least two judges from different vendor families "
            f"(ADR-0001 §4); got {sorted(map(str, fams))}",
            "invalid-file",
        )
    # The controls are part of the pass, not optional (ADR-0001 §4): a scorer states both, so a
    # forgotten field cannot switch them off. Position needs an order, so it may be 0 only when
    # every call sees one output.
    pr = sc["protocol"]
    for k in ("position_check_fraction", "noise_check_fraction"):
        if k not in pr:
            die(
                f"{path.name}: protocol.{k} is required (ADR-0001 §4: the controls are not optional)",
                "invalid-file",
            )
    if not pr["noise_check_fraction"] > 0:
        die(
            f"{path.name}: protocol.noise_check_fraction must be above 0: the judge's own noise is measured",
            "invalid-file",
        )
    if int(pr.get("outputs_per_call", 1)) > 1 and not pr["position_check_fraction"] > 0:
        die(
            f"{path.name}: protocol.position_check_fraction must be above 0 when a call sees "
            f"{pr['outputs_per_call']} outputs: their order can move a verdict",
            "invalid-file",
        )
    bad = mode_problems(sc)
    if bad:
        die(f"{path.name}: {bad[0]}", "invalid-file")
    try:
        sc["_task"] = task_of(sc)
    except ValueError as exc:
        die(f"{path.name}: {exc}", "invalid-file")
    return sc


def mode_of(doc: dict[str, Any]) -> str:
    """What a judge is asked: the scorer's (or a frozen set's) `mode`, `grade` when it has none."""
    return doc.get("mode") or DEFAULT_MODE


def mode_problems(sc: dict[str, Any]) -> list[str]:
    """What is wrong with a scorer's `mode` and what hangs on it; empty when nothing is.

    Whether a pick scorer's `outputs_per_call` covers the arms is checked when the arms are
    known (build_manifest)."""
    mode = mode_of(sc)
    if mode not in MODES:
        return [f"mode must be one of {', '.join(MODES)}, got {mode!r}"]
    v = sc.get("validation")
    if isinstance(v, dict) and mode_of(v) != mode:
        return [
            (
                f"validation.mode is {mode_of(v)!r} but mode is {mode!r}: a judge is validated in the "
                f"mode it is used in (one that grades like people says nothing about how it picks)"
            )
        ]
    n = (sc.get("protocol") or {}).get("outputs_per_call")
    if mode == "pairwise" and n != 2:
        return [
            (
                f"protocol.outputs_per_call is {n!r} but a pairwise call judges exactly 2 outputs: "
                f"every pair of arms is its own call, so set it to 2"
            )
        ]
    return []


def task_for(sc: dict[str, Any]) -> dict[str, Any]:
    """The scorer's checked task: set by load_scorer, derived here for a scorer built in code."""
    if "_task" not in sc:
        try:
            sc["_task"] = task_of(sc)
        except ValueError as exc:
            die(f"scorer {sc.get('scorer_id')}: {exc}", "invalid-file")
    return sc["_task"]


def judge_params(sc: dict[str, Any], j: dict[str, Any]) -> dict[str, Any]:
    """What a judge is called with. A fake judge is also told the task, to answer in its
    shape; a real one is not (its request carries only its own params)."""
    p = dict(j["params"])
    if p.get("provider") == FAKE:
        p["_task"] = task_for(sc)
        p["_mode"] = mode_of(sc)
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
    p = next((c for c in cands if _store.is_file(c)), None)
    if p is None:
        die(
            f"prompt file not found: {sc['prompt']['file']} (looked in {', '.join(str(c) for c in cands)})",
            "not-found",
        )
    return _store.read_text(p, encoding="utf-8").strip()


#: Params that change what a judge says. The validation run recorded them; the scorer must
#: still carry the same ones, or the number it cites was measured on a different judge.
OUTPUT_PARAMS = ("provider", "model", "temperature", "reasoning", "max_tokens")


def validation_problems(
    sc: dict[str, Any], prompt_root: Path | None = None, runs_dir: Path | None = None
) -> list[str]:
    """Why this scorer is not validated; empty means it is. The validation runs are run ids under `runs_dir`
    (default data/runs), each read as the score it made when it ran."""
    fakes = [j["id"] for j in sc["judges"] if j["params"].get("provider") == FAKE]
    if fakes:
        return [f"judge {i!r} uses provider: fake, a stand-in that can never be validated" for i in fakes]
    v = sc.get("validation")
    if not isinstance(v, dict) or not v.get("runs"):
        return ["no `validation` block naming a committed run"]
    out: list[str] = mode_problems(sc)
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
        first = _model_runs.first_score((runs_dir or _model_runs.root()) / str(r.get("run", "")))
        m = _model_runs.record(first) if first else None
        if m is None:
            out.append(f"judge {j['id']!r}: validation run {r.get('run')!r} is not in data/runs")
            continue
        if v.get("dataset_id") and m.get("dataset_id") != v["dataset_id"]:
            out.append(
                f"judge {j['id']!r}: run {r['run']} is on {m.get('dataset_id')!r}, not {v['dataset_id']!r}"
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
        if mode_of(rec) != mode_of(sc):
            out.append(
                f"judge {j['id']!r}: run {r['run']} measured mode={mode_of(rec)!r}, "
                f"the scorer uses {mode_of(sc)!r}"
            )
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
        ran = (((m.get("fingerprint") or {}).get("settings") or {}).get("declared") or {}).get(
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
    exp = (sc.get("validation") or {}).get("dataset_id")
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


def _blocks_of(
    mode: str, arm_ids: Sequence[str], seed: Any, item_id: str, per_call: int
) -> tuple[list[list[str]], list[list[str]]]:
    """An item's (primary, position) blocks.

    grade: balanced blocks of at most per_call, the position pass a second shuffle.
    pick: one block of every arm (per_call covers them), the position pass a second shuffle.
    pairwise: one block per pair of arms, each pair in a seeded order; the position pass is the
    same pairs in the swapped order.
    """
    if mode != "pairwise":
        return (
            blocks_for(arm_ids, seed, "primary", item_id, per_call),
            blocks_for(arm_ids, seed, "position", item_id, per_call),
        )
    primary = [
        shuffled(pair, seed, f"primary|{pair[0]}|{pair[1]}", item_id)
        for pair in itertools.combinations(sorted(arm_ids), 2)
    ]
    return primary, [b[::-1] for b in primary]


def pick_subset(item_ids: Sequence[str], frac: float, seed: Any, salt: str) -> list[str]:
    """Deterministically select a fraction of items (seeded by salt); empty list if frac <= 0."""
    if not frac or frac <= 0:
        return []
    k = min(len(item_ids), max(1, round(frac * len(item_ids))))
    chosen = set(sorted(item_ids, key=lambda i: _sha(f"{seed}|{salt}|{i}"))[:k])
    return [i for i in item_ids if i in chosen]


# ── arms and the judging set ─────────────────────────────────────────────────
def discover_arms(dataset_id: str, match: str) -> list[dict[str, Any]]:
    """The primary run of every arm on the dataset: config_id contains `match`, latest wins. `dir` is the score the
    run made, whose outputs and rows are read."""
    latest: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    # One run per arm, the latest, on purpose: judging scores an arm's outputs, so repeats
    # are not averaged as they are everywhere else (_runs.per_item).
    for d, m in runs_on(dataset_id, match=match or None):
        cid = m["config_id"]
        key = m.get("created_at", "") + m["run_id"]
        if cid not in latest or key > latest[cid][0]:
            latest[cid] = (key, d, m)
    arms = []
    for cid, (_k, d, m) in sorted(latest.items()):
        arms.append(
            {
                "config_id": cid,
                "run": m["run_id"],
                "dir": d,
                "family": (m.get("params") or {}).get("family")
                or (m.get("fingerprint", {}).get("settings") or {}).get("family"),
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
            die(f"--arms {tok!r} matches none of the {len(arms)} discovered arms", "not-found")
        keep += [a for a in hit if a not in keep]
    return sorted(keep, key=lambda a: a["config_id"])


def read_outputs(arm: dict[str, Any], item_ids: Sequence[str]) -> dict[str, str]:
    """All outputs of one arm; die if any item's file is missing."""
    out = {}
    for i in item_ids:
        text = _outputs.output(Path(arm["dir"]), i)
        if text is None:
            die(
                f"{arm['run']}: no stored output for {i} — the judging set needs every "
                f"arm's output for every item",
                "not-enough",
            )
        out[i] = text
    return out


def as_judged(dataset_id: str, arms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The arms under the ids a stored judging set of exactly these runs gave them, when there is one (owner,
    2026-11-13: a judging set is frozen evidence and keeps the ids it was judged under, RFC-032 step 3). Its arm order
    and its blocks are made of those ids, so the set rebuilt from them is the stored one and its verdicts are found;
    a judged run still takes its run's own id (its metrics are its source run's)."""
    runs = {a["run"] for a in arms}
    for f in sorted(_store.glob(SETS, f"{dataset_id}-*.json")) if _store.is_dir(SETS) else []:
        by_run = {x.get("run"): x.get("config_id") for x in read_json(f).get("arms") or []}
        if set(by_run) == runs and any(by_run[a["run"]] != a["config_id"] for a in arms):
            return sorted(({**a, "config_id": by_run[a["run"]]} for a in arms), key=lambda a: a["config_id"])
    return arms


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
        die("a judging set needs at least two arms", "not-enough")
    mode = mode_of(sc)
    if mode not in MODES:
        die(f"mode must be one of {', '.join(MODES)}, got {mode!r}", "invalid-file")
    if mode == "pick" and per_call < len(arm_ids):
        die(
            f"a pick scorer needs protocol.outputs_per_call of at least the number of arms "
            f"({len(arm_ids)}), got {per_call}: a pick made in blocks would name each block's winner, "
            f"not the item's. Raise outputs_per_call, or judge fewer arms (--match, --arms)",
            "not-enough",
        )
    items = []
    for i in item_ids:
        items.append(
            {
                "item_id": i,
                "article_sha256": _sha(articles[i]),
                **dict(zip(("primary", "position"), _blocks_of(mode, arm_ids, seed, i, per_call))),
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
            "block_sizes": [2] if mode == "pairwise" else block_sizes(len(arm_ids), per_call),
        },
        "prompt_sha256_at_16": _sha(base_prompt),
        # Only a declared task and a declared mode are hashed, so a grade scorer keeps the set id it had.
        **({"task": task_for(sc)} if sc.get("task") else {}),
        **({"mode": mode} if mode != DEFAULT_MODE else {}),
        "items": items,
        "position_items": pick_subset(list(item_ids), pr["position_check_fraction"], seed, "position-subset"),
        "noise_items": pick_subset(list(item_ids), pr["noise_check_fraction"], seed, "noise-subset"),
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
    build = {"pick": build_pick_message, "pairwise": build_pairwise_message}.get(
        mode_of(manifest), build_message
    )
    return build(
        base,
        articles[item["item_id"]],
        [outputs[a][item["item_id"]] for a in arm_ids],
        task["source_label"],
        task["output_label"],
    )


def freeze(manifest: dict[str, Any], sets_dir: Path = SETS) -> Path:
    """Write the manifest once; an existing one with the same id must match byte for byte."""
    path = sets_dir / f"{manifest['judging_set_id']}.json"
    if _store.is_file(path):
        if read_json(path).get("judging_set_sha256") != manifest["judging_set_sha256"]:
            die(
                f"{path.name} exists with a different hash: a frozen judging set is never rewritten",
                "would-overwrite",
            )
    else:
        write_json(path, manifest)
    return path


# ── verdicts ─────────────────────────────────────────────────────────────────
def judge_fingerprint(j: dict[str, Any]) -> str:
    """Identity of a judge: its params, without the credential that pays for its calls. The
    cost cap and the controls are not part of it."""
    return _sha(_canon({"id": j["id"], "params": identity_params(j["params"])}))[:16]


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
    for f in _store.glob(vdir, "*/*.json"):
        try:
            total += float(read_json(f).get("cost_usd") or 0.0)
        except (OSError, ValueError):
            pass
    return total


def parse_reply(mode: str, output: str, n: int, task: dict[str, Any]) -> dict[str, Any]:
    """The verdict fields a reply parses to, under the key its mode stores them in; None when
    it did not parse."""
    if mode == "pick":
        return {"best": parse_pick(output, n)}
    if mode == "pairwise":
        return {"better": parse_pairwise(output)}
    return {"scores": parse_block(output, n, task["dimensions"], task["scale"])}


def verdict_parsed(rec: dict[str, Any]) -> bool:
    """Whether a stored verdict holds an answer (of any mode) rather than an unreadable reply."""
    return any(rec.get(k) is not None for k in VERDICT_KEY.values())


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
    cut_empty = 0
    first_replies: dict[str, list[bool]] = {}  # per judge: its first replies, empty at the token limit
    work = tasks(manifest)
    try:
        for item, pass_name, block in work:
            msg = None
            for j in sc["judges"]:
                path = verdict_path(vdir, j["id"], item["item_id"], pass_name, block)
                if _store.is_file(path):
                    old = read_json(path)
                    if old.get("judge_fp") != judge_fingerprint(j):
                        die(
                            f"{path}: stored by a different judge definition than "
                            f"{j['id']!r} in the scorer now; refusing to mix them",
                            "not-allowed",
                        )
                    if old.get("set_id") != manifest["judging_set_id"]:
                        die(f"{path}: belongs to judging set {old.get('set_id')}", "mismatch")
                    if old.get(VERDICT_KEY[mode_of(manifest)]) is not None or not retry_unparsed:
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
                answer = parse_reply(mode_of(manifest), res.output, n, task_for(sc))
                arms = item["position" if pass_name == "position" else "primary"][block]  # noqa: S105 — a judging pass, not a password
                why = withheld_reason(
                    res.output,
                    shingles([articles[item["item_id"]], *(outputs[a][item["item_id"]] for a in arms)]),
                )
                # Nothing to quote is still not bare JSON: V12 refuses a committed `""`.
                if not why and not res.output:
                    why = "empty reply"
                # A retried block replaces the stored reply; the earlier calls were paid for
                # too, so their cost stays in the record (and in every bill read from it).
                prior = read_json(path) if _store.is_file(path) else {}
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
                        **answer,
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
                if why and res.output:
                    # Kept out of git (V12: a committed reply is bare JSON and never repeats the
                    # source), but readable here, so an unparsed reply's cause is not a guess.
                    local = _keep_withheld(path, res.output or "")
                    log(
                        f"    reply not committed as text ({why}), only its hash; "
                        f"readable, git-ignored, at {local}: "
                        f"{j['id']} {item['item_id'][:8]} {pass_name} b{block}"
                    )
                if all(v is None for v in answer.values()):
                    fr = meta.get("finish_reason")
                    cut_empty += 1 if (not res.output and fr == "length") else 0
                    # A judge whose first replies all come back empty at the token limit will do so for the whole
                    # pass (a reasoning model spending its max_tokens thinking): stop after EARLY_CUTOFF calls, not
                    # after paying for every one (the 0.7.1 newcomer run: tutorial 3's thinking judge at 400).
                    first = first_replies.setdefault(j["id"], [])
                    if len(first) < EARLY_CUTOFF:
                        first.append(not res.output and fr == "length")
                        if len(first) == EARLY_CUTOFF and all(first):
                            raise JudgeCutOff(
                                f"{j['id']}: its first {EARLY_CUTOFF} replies came back empty at the token limit"
                            )
                    log(
                        f"    unparsed reply: {j['id']} {item['item_id'][:8]} {pass_name} b{block}: "
                        f"{unparsed_cause(res.output, fr, mode_of(manifest))}"
                    )
                else:
                    parsed = first_replies.setdefault(j["id"], [])
                    if len(parsed) < EARLY_CUTOFF:
                        parsed.append(
                            False
                        )  # a reply that parsed: this judge is not one that always runs out
                    if stats["calls"] % 25 == 0:
                        log(f"    {stats['calls']} calls, ${spent:.4f}")
    except CostCapExceeded as exc:
        stats["aborted"] = True
        log(f"  COST CAP: {exc}. Stopping; every stored verdict is kept and re-read for $0.")
    except JudgeCutOff as exc:
        stats["aborted"] = True
        stats["cut_off_early"] = str(exc)
        log(
            f"  STOPPED EARLY: {exc}, so the rest of the pass would too. Every stored verdict is kept; "
            "fix the judge (below) and run again."
        )
    except JudgeCallFailed as exc:
        stats["aborted"] = True
        stats["call_failed"] = str(exc)
        log(
            f"  JUDGE CALL FAILED after retries or refused: {exc}\n  Stopping; every stored verdict is kept. "
            "Fix the cause and run the same command again: it resumes where it stopped."
        )
    stats["spent_usd"] = spent
    if cut_empty:
        log(cutoff_hint(cut_empty, stats["calls"], sc))
    return stats


# ── projection ───────────────────────────────────────────────────────────────
def block_outcome(mode: str, arm_ids: Sequence[str], value: Any) -> Any:
    """What a stored verdict says about the arms of its block: a pick, the arms named best
    (a sorted tuple); a pairwise call, the winning arm or TIE."""
    if mode == "pick":
        return tuple(sorted(arm_ids[i - 1] for i in value))
    return TIE if value == "tie" else arm_ids[value - 1]


def load_readings(
    manifest: dict[str, Any], sc: dict[str, Any], vdir: Path
) -> dict[str, dict[str, dict[str, dict[int, Any]]]]:
    """{judge: {pass: {item: {block: outcome}}}} for pick and pairwise: every stored verdict that
    parsed, by block (`block_outcome`). An item may hold only some of its blocks."""
    mode = mode_of(manifest)
    out: dict[str, dict[str, dict[str, dict[int, Any]]]] = {}
    for j in sc["judges"]:
        out[j["id"]] = {p: {} for p in PASSES}
        for it in manifest["items"]:
            for p in PASSES:
                blocks = it["position" if p == "position" else "primary"]
                for b, arm_ids in enumerate(blocks):
                    f = verdict_path(vdir, j["id"], it["item_id"], p, b)
                    v = read_json(f).get(VERDICT_KEY[mode]) if _store.is_file(f) else None
                    if v is not None:
                        out[j["id"]][p].setdefault(it["item_id"], {})[b] = block_outcome(mode, arm_ids, v)
    return out


def won_from(mode: str, blocks: Sequence[Sequence[str]], outcomes: dict[int, Any]) -> dict[str, float]:
    """Each arm's `won` on one item from a judge's complete reading of it.

    pick: 1 when the arm alone was named best, 1/k when it shares the best with k - 1 others,
    else 0. pairwise: the share of the arm's pairs it won, a tie counting a half.
    """
    if mode == "pick":
        best = outcomes[0]
        return {a: (1.0 / len(best) if a in best else 0.0) for a in blocks[0]}
    wins: dict[str, float] = {}
    for b, pair in enumerate(blocks):
        for a in pair:
            wins.setdefault(a, 0.0)
            if outcomes[b] == TIE:
                wins[a] += 0.5
            elif outcomes[b] == a:
                wins[a] += 1.0
    return {a: w / (len(wins) - 1) for a, w in wins.items()}


def load_scores(
    manifest: dict[str, Any], sc: dict[str, Any], vdir: Path
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """{judge: {pass: {item: {arm: score}}}} for the items whose every block parsed. For pick and
    pairwise the number is the arm's `won` on the item (see `won_from`)."""
    out: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    mode = mode_of(manifest)
    if mode != DEFAULT_MODE:
        readings = load_readings(manifest, sc, vdir)
        for j in sc["judges"]:
            out[j["id"]] = {p: {} for p in PASSES}
            for it in manifest["items"]:
                for p in PASSES:
                    blocks = it["position" if p == "position" else "primary"]
                    read = readings[j["id"]][p].get(it["item_id"])
                    if read is not None and len(read) == len(blocks):
                        out[j["id"]][p][it["item_id"]] = won_from(mode, blocks, read)
        return out
    for j in sc["judges"]:
        out[j["id"]] = {p: {} for p in PASSES}
        for it in manifest["items"]:
            for p in PASSES:
                key = "position" if p == "position" else "primary"
                got: dict[str, float] = {}
                ok = True
                for b, arm_ids in enumerate(it[key]):
                    f = verdict_path(vdir, j["id"], it["item_id"], p, b)
                    s = read_json(f).get("scores") if _store.is_file(f) else None
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


_MODE_NOTES = {
    "pick": (
        "Each judge named the best of an item's outputs in one call. won is 1 for an arm named alone, "
        "1/k when k share the best, else 0; win_rate is its mean. The position control re-shuffles the "
        "item and the share of picks that kept the same arms is controls.position.agreement."
    ),
    "pairwise": (
        "Each judge compared every pair of an item's outputs in its own call. won is the share of an "
        "arm's pairs it won, a tie half; win_rate is its mean. The position control swaps the pair and "
        "the share of verdicts that kept the same winner (or tie) is controls.position.agreement."
    ),
}


def item_comparisons(
    mode: str, blocks: Sequence[Sequence[str]], outcomes: dict[int, Any]
) -> list[tuple[str, str, float, float]]:
    """(arm, arm, first's win, second's win) for every comparison one judge's reading of an item
    holds, a tie being half a win each way. A pick: each arm named best beats each arm not named;
    arms sharing the best tie with each other. A pairwise call: its pair."""
    out: list[tuple[str, str, float, float]] = []
    if mode == "pick":
        best = outcomes[0]
        out += [(w, a, 1.0, 0.0) for w in best for a in blocks[0] if a not in best]
        out += [(x, y, 0.5, 0.5) for x, y in itertools.combinations(best, 2)]
        return out
    for b, (x, y) in enumerate(blocks):
        o = outcomes[b]
        out.append((x, y, 0.5, 0.5) if o == TIE else (x, y, 1.0, 0.0) if o == x else (x, y, 0.0, 1.0))
    return out


def _bt_solve(w: list[list[float]], p: list[float]) -> list[float]:
    """Bradley-Terry strengths from w[i][j], i's (fractional) wins over j, by the MM iteration
    (Hunter 2004, eq. 3): p_i <- W_i / sum_j n_ij / (p_i + p_j), scaled to geometric mean 1.
    Every pair carries the virtual draw BT_PRIOR, so the fit exists for any data."""
    n = len(w)
    tot = [[w[i][j] + w[j][i] + BT_PRIOR for j in range(n)] for i in range(n)]
    won = [sum(w[i]) + (n - 1) * BT_PRIOR / 2 for i in range(n)]
    for _ in range(BT_MAX_ITER):
        new = [won[i] / sum(tot[i][j] / (p[i] + p[j]) for j in range(n) if j != i) for i in range(n)]
        g = math.exp(sum(math.log(x) for x in new) / n)
        new = [x / g for x in new]
        done = max(abs(a / b - 1.0) for a, b in zip(new, p)) < BT_TOL
        p = new
        if done:
            break
    return p


def _quantile(xs: Sequence[float], q: float) -> float:
    """The q-quantile of sorted xs, linearly interpolated."""
    pos = q * (len(xs) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def bradley_terry(
    arm_ids: Sequence[str], per_item: Sequence[Sequence[tuple[str, str, float, float]]], seed: str
) -> dict[str, dict[str, float]]:
    """{arm: {strength, low, high}}: each arm's Bradley-Terry strength over every comparison
    (geometric mean 1 across arms: 2.0 is twice as strong as the average arm) and a 95% percentile
    interval from BT_RESAMPLES resamples of the items with replacement, seeded by `seed`."""
    n, m = len(arm_ids), len(per_item)
    idx = {a: i for i, a in enumerate(arm_ids)}
    items = [[(idx[a], idx[b], x, y) for a, b, x, y in comps] for comps in per_item]

    def matrix(counts: Sequence[int]) -> list[list[float]]:
        w = [[0.0] * n for _ in range(n)]
        for comps, c in zip(items, counts):
            for a, b, x, y in comps if c else []:
                w[a][b] += c * x
                w[b][a] += c * y
        return w

    full = _bt_solve(matrix([1] * m), [1.0] * n)
    rng = random.Random(seed)
    reps: list[list[float]] = []
    for _ in range(BT_RESAMPLES):
        counts = [0] * m
        for _ in range(m):
            counts[rng.randrange(m)] += 1
        reps.append(_bt_solve(matrix(counts), full))
    tail = (1.0 - BT_COVERAGE) / 2
    out = {}
    for i, a in enumerate(arm_ids):
        col = sorted(r[i] for r in reps)
        out[a] = {
            "strength": round(full[i], 6),
            "low": round(_quantile(col, tail), 6),
            "high": round(_quantile(col, 1.0 - tail), 6),
        }
    return out


def verdict_agreement(base: dict[str, dict[int, Any]], other: dict[str, dict[int, Any]]) -> dict[str, Any]:
    """How many of `other`'s verdicts say what `base`'s do for the same block: the position check
    (the reshuffled pick, the swapped pair) or the noise check (the repeat) of a pick or pairwise
    judge. A pick is kept when the same arms are named best."""
    items = kept = total = 0
    for item, blocks in other.items():
        shared = [b for b in blocks if b in (base.get(item) or {})]
        if shared:
            items += 1
        for b in shared:
            total += 1
            kept += blocks[b] == base[item][b]
    return {
        "n_items": items,
        "n_verdicts": total,
        "kept": kept,
        "agreement": round(kept / total, 6) if total else None,
    }


def winner_set(cells: dict[str, float]) -> frozenset[str]:
    """The arms with the highest `won` on an item: its winner, or its winners when they tie."""
    top = max(cells.values())
    return frozenset(a for a, v in cells.items() if abs(v - top) < 1e-12)


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
    lengths: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Summarize the judging: per-arm scores, judge agreement, controls, and cost. `lengths` ({config_id: {item:
    words}}) gives each judge's length bias: how far its score follows how long an output is. For pick and
    pairwise the per-arm number is the win rate (mean `won`), with Bradley-Terry strengths beside
    it, and the controls are how often the position and noise checks kept the verdict."""
    mode = mode_of(manifest)
    graded = mode == DEFAULT_MODE
    pkey = "judge_score" if graded else "judge_won"
    jids = [j["id"] for j in sc["judges"]]
    fam = {j["id"]: j["params"].get("family") for j in sc["judges"]}
    # `won` runs 0..1, so the panel's 0.5 on a 1-5 scale would never flag anything.
    thr = float(sc["protocol"].get("contested_threshold", 0.5 if graded else 0.25))
    per_arm: dict = {}
    for a in arms:
        cid = a["config_id"]
        col = {j: _mean([proj[i][cid][j] for i in proj]) for j in jids}
        pm = _mean([proj[i][cid]["_mean"] for i in proj])
        vals = [v for v in col.values() if v is not None]
        per_arm[cid] = {
            "family": a.get("family"),
            pkey: pm,
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
                **(
                    {}
                    if graded
                    else {
                        "winner_agreement": round(
                            statistics.fmean(
                                winner_set({c: proj[i][c][ja] for c in proj[i]})
                                == winner_set({c: proj[i][c][jb] for c in proj[i]})
                                for i in proj
                            ),
                            6,
                        )
                    }
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
    # Length bias (C2): Spearman's rho of each judge's score with the output's length in words, over every (item,
    # arm) judged. Judges are known to favour longer answers; a rho well above 0 says this one may.
    length_bias: dict[str, Any] = {}
    for j in jids:
        pairs = [
            (lengths[c][i], proj[i][c][j])
            for i in proj
            for c in proj[i]
            if lengths and c in lengths and i in lengths[c] and proj[i][c].get(j) is not None
        ]
        length_bias[j] = (
            {
                "n": len(pairs),
                "spearman_length": round(spearman([a for a, _ in pairs], [b for _, b in pairs]), 4),
            }
            if len(pairs) > 2
            else None
        )
    ctrl = {}
    for j in jids if graded else []:
        p = scores[j]
        ctrl[j] = {
            "position": compare_passes(p["primary"], p["position"]),
            "noise": compare_passes(p["primary"], p["noise"]),
        }
    bt_meta: dict[str, Any] = {}
    if not graded:
        readings = load_readings(manifest, sc, vdir)
        ctrl = {
            j: {
                "position": verdict_agreement(readings[j]["primary"], readings[j]["position"]),
                "noise": verdict_agreement(readings[j]["primary"], readings[j]["noise"]),
            }
            for j in jids
        }
        by_id = {it["item_id"]: it for it in manifest["items"]}
        per_item = [
            [c for j in jids for c in item_comparisons(mode, by_id[i]["primary"], readings[j]["primary"][i])]
            for i in proj
        ]
        arm_ids = sorted(per_arm)
        seed = f"{manifest['protocol']['order_seed']}|bradley-terry|{manifest['judging_set_id']}"
        bt = bradley_terry(arm_ids, per_item, seed)
        for cid, r in bt.items():
            per_arm[cid].update(
                win_rate=per_arm[cid][pkey], bt_strength=r["strength"], bt_low=r["low"], bt_high=r["high"]
            )
        bt_meta = {
            "bradley_terry": {
                "method": "MM algorithm (Hunter 2004), strengths scaled to geometric mean 1",
                "comparisons": sum(len(c) for c in per_item),
                "resamples": BT_RESAMPLES,
                "interval": f"{BT_COVERAGE:.0%} percentile, items resampled with replacement",
                "seed": seed,
                "virtual_draw_per_pair": BT_PRIOR,
            }
        }
    calls = {}
    for j in jids:
        files = sorted(_store.glob(vdir / j, "*.json")) if _store.is_dir(vdir / j) else []
        vs = [read_json(f) for f in files]
        calls[j] = {
            "verdicts": len(vs),
            "unparsed": sum(1 for v in vs if not verdict_parsed(v)),
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
        "length_bias": length_bias,
        "controls": ctrl,
        **({} if graded else {"mode": mode, **bt_meta}),
        "notes": [
            (
                (
                    f"Each judge scored each item's arms in blocks; scores are absolute "
                    f"{task_for(sc)['scale'][0]:g}-{task_for(sc)['scale'][1]:g} per "
                    "dimension and block scores are pooled. The position control re-forms the blocks."
                )
                if graded
                else _MODE_NOTES[mode]
            ),
            (
                "self_family: the arm and the judge are the same vendor family. own_minus_others "
                "is a raw gap, not a bias estimate: families differ in real quality."
            ),
            (
                f"contested: two judges' arm means differ by more than {thr} (the judge panel's rule)."
                if graded
                else f"contested: two judges' win rates for an arm differ by more than {thr}."
            ),
        ],
    }


# ── scored runs ──────────────────────────────────────────────────────────────
def write_scored_runs(
    manifest: dict[str, Any],
    sc: dict[str, Any],
    arms: Sequence[dict[str, Any]],
    proj: dict[str, dict[str, dict[str, float]]],
    label: str,
    validated: bool,
    self_path: Path = Path(__file__),
) -> list[Path]:
    """One score under each judged run (key <scorer>@<judging set>, read as `judged/<scorer>`), so leaderboard /
    family_test / pair_test read them with `--label judged/<scorer>`. A pass run again over more stored verdicts
    replaces its own earlier score of the same key; the same rows are not written twice. The scores' directories."""
    sfx = "" if validated else "_unvalidated"
    mode = mode_of(manifest)
    primary = f"{'judge_score' if mode == DEFAULT_MODE else 'judge_won'}{sfx}"
    jids = [j["id"] for j in sc["judges"]]
    fam = {j["id"]: j["params"].get("family") for j in sc["judges"]}
    written = []
    for a in arms:
        cid, src = a["config_id"], Path(a["dir"])
        m = _model_runs.record(src) or {}
        old_rows = {r["item_id"]: r for r in _runs.item_rows(src)}
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
            old_row = old_rows.get(iid) or {}
            for k, v in old_row.items():
                # The adapter's call-time extras (`_extra` names them) describe the call too.
                if k in CARRY or k in (old_row.get("_extra") or {}) or k.startswith("_"):
                    row[k] = v
            rows.append(row)
        keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
        scores = aggregate_scores(rows)
        kinds = {k: v for k, v in (m.get("metric_kinds") or {}).items() if k in scores}
        # The source run's cost and speed are still the arm's cost and speed: known names keep
        # their kind (cost_usd, latency_ms), so the judged leaderboard has its frontier.
        known = classify_metrics()
        for k in keys:
            kinds[k] = (
                "descriptive"
                if k.startswith(BOOKKEEPING_PREFIXES)
                else kinds.get(k) or known.get(k) or ("quality" if k.startswith("judge_") else "descriptive")
            )
        # A judge reads no reference, so the source run's tier does not describe these scores;
        # it is kept, as the source's, in derived.with.
        source_tier = m.get("reference_tier")
        new = derived_record(
            m,
            kind="judge",
            source_dir=a["run"],
            scores=scores,
            n_items=len(rows),
            drop=("reference_tier",),
            metric_kinds=kinds,
            primary_metric=primary,
            with_={
                "label": label,
                **({} if mode == DEFAULT_MODE else {"mode": mode}),
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
            seal(fp, whole=False)
            fp["hash_invalid_because"] = (
                "scores were produced by a judge scorer, not the adapter this fingerprint "
                "was built from; see derived.with"
            )
            new["fingerprint"] = fp
        key = _model_runs.key(sc["scorer_id"], manifest["judging_set_id"])
        held = _model_runs.run_dir(a["run"]) / "scores" / key
        text = "".join(_outputs.row_line(r) for r in rows)
        if _model_runs.record(held) is None or _outputs.rows_text(held) != text:
            held = _model_runs.write_score(
                a["run"],
                sc["scorer_id"],
                manifest["judging_set_id"],
                new,
                label_as=f"judged/{sc['scorer_id']}",
            )
            _outputs.write_rows(held, rows)  # no outputs of its own: they are its run's (RFC-024)
        written.append(held)
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
            if _store.is_file(verdict_path(vdir, j["id"], item["item_id"], p, b)):
                e["stored"] += 1
                continue
            e["calls"] += 1
            e["tokens_in"] += math.ceil(len(msg) / CHARS_PER_TOKEN)
            e["tokens_out"] += (
                OUT_TOKENS_FIXED
                + math.ceil(OUT_TOKENS_PER_SUMMARY * len(task_for(sc)["dimensions"]) / len(DIMS)) * n
                if mode_of(manifest) == DEFAULT_MODE
                else OUT_TOKENS_ANSWER
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


def judge_access(sc: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    """(judge id, where its calls go and which key pays, what is missing) for every judge,
    resolved without a call: a judge reads EVAL_JUDGE_<NAME> first, then the arms' <NAME>."""
    out: list[tuple[str, str, list[str]]] = []
    for j in sc["judges"]:
        p = j["params"]
        if p.get("provider") == FAKE:
            out.append((j["id"], "fake: no call, $0", []))
            continue
        found = _providers.problems(p, "judge")
        if p.get("provider") not in _providers.SPECS:
            out.append((j["id"], f"provider {p.get('provider')!r}", found))
            continue
        r = _providers.route(p, "judge")
        whose = "judging's own" if r.key_var.startswith(_providers.JUDGE_PREFIX) else "shared with the arms"
        at = f" at {r.base_url}" if r.base_url else ""
        out.append((j["id"], f"{r.provider} {p.get('model')}{at}, key {r.key_var} ({whose})", found))
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def print_win_summary(summ: dict[str, Any]) -> None:
    """The pick / pairwise summary on the terminal: each arm's win rate and Bradley-Terry strength
    with its interval, then how often the controls kept the verdict and the judges' winners agree."""
    bt = summ["bradley_terry"]
    print(f"\n  {summ['mode']}: win rate and Bradley-Terry strength ({bt['interval']}), best first")
    for cid, a in sorted(summ["per_arm"].items(), key=lambda kv: -(kv[1]["win_rate"] or 0.0)):
        print(
            f"    {cid:40s} win {a['win_rate']:.3f}  strength {a['bt_strength']:7.3f} "
            f"[{a['bt_low']:.3f}, {a['bt_high']:.3f}]"
        )

    def share(c: dict[str, Any]) -> str:
        return f"{c['agreement']:.3f} of {c['n_verdicts']}" if c["agreement"] is not None else "n/a"

    for j, c in summ["controls"].items():
        print(f"  judge {j:8s} position kept {share(c['position'])}, noise kept {share(c['noise'])}")
    for pair, a in summ["judge_agreement"].items():
        print(f"  judges {pair}: same item winner on {a['winner_agreement']:.3f} of {a['n_items']} items")


def real_call(message: str, params: dict[str, Any]) -> Any:
    """Call a judge; the call_with_retries hook."""
    return call_judge(message, params)


def main() -> int:
    """Re-measure a frozen eval with a validated LLM judge."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
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
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("judge-score", args.json, live=sys.stderr):
        # Piped or redirected to a log, stdout is block-buffered and the progress lines came all at once at the end
        # (as in `evh run`): a line is written when it is printed.
        for stream in (sys.stdout, sys.stderr):
            if not stream.isatty() and hasattr(stream, "reconfigure"):
                stream.reconfigure(line_buffering=True)

        sc = load_scorer(SCORERS / f"{args.scorer}.yaml")
        if sc["dataset_id"] != args.dataset_id:
            die(
                f"scorer {sc['scorer_id']} is for dataset {sc['dataset_id']!r}, not {args.dataset_id!r}",
                "mismatch",
            )
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
            return EXIT_UNVALIDATED
        label = validated_label(sc) if validated else "unvalidated judge"
        if not validated:
            print(f"WARNING: UNVALIDATED JUDGE. Every number is labelled; {len(problems)} problem(s):")
            for p in problems:
                print(f"  - {p}")

        ds_file = DATA / "datasets" / f"{dataset_id_ok(args.dataset_id)}.json"
        if not _store.is_file(ds_file):
            die(f"no dataset {args.dataset_id}", "not-found")
        ds = read_json(ds_file)
        items = ds["items"]
        item_ids = [it["item_id"] for it in items]
        mat = MATERIALIZED / args.dataset_id
        articles = {}
        for it in items:
            f = mat / (it.get("source_path") or f"{it['item_id']}.txt")
            if not _store.is_file(f):
                die(
                    f"{f} is missing: materialize the dataset first "
                    f"({how(f'evh dataset-materialize --dataset-id {args.dataset_id}', f'make dataset-materialize DATASET_ID={args.dataset_id}')})",
                    "not-materialized",
                )
            articles[it["item_id"]] = _store.read_text(f, encoding="utf-8", errors="replace")
        arms = discover_arms(args.dataset_id, args.match or sc.get("arms_match", ""))
        if args.arms:
            arms = select_arms(arms, args.arms)
        if len(arms) < 2:
            die(f"found {len(arms)} arm run(s) on {args.dataset_id} in data/runs", "not-enough")
        vers = config_versions(arms)
        if len(vers) > 1:
            print(
                f"WARNING: the arm set mixes system versions {', '.join(vers)}: v1 and v2 of one arm are "
                "judged as two arms. Narrow it with --match _v2 (or the scorer's arms_match) if that "
                "is not what you mean."
            )
        arms = as_judged(args.dataset_id, arms)
        outputs = {a["config_id"]: read_outputs(a, item_ids) for a in arms}
        base = prompt_text(sc)
        items_sha = (
            (_model_runs.record(Path(arms[0]["dir"])) or {})
            .get("fingerprint", {})
            .get("data", {})
            .get("items_sha256")
        )
        manifest = build_manifest(sc, args.dataset_id, items_sha, item_ids, arms, articles, outputs, base)
        sid = manifest["judging_set_id"]
        vdir = VERDICTS / sc["scorer_id"] / sid
        cap = effective_cap(sc)
        print(f"judging set  {sid}")
        mode = mode_of(manifest)
        per_item = {
            "grade": f"blocks per item {manifest['protocol']['block_sizes']}",
            "pick": "one pick of all the arms per item",
            "pairwise": f"{len(arms) * (len(arms) - 1) // 2} pair calls per item",
        }[mode]
        print(
            f"  arms {len(arms)}, items {len(item_ids)}, "
            + (f"mode {mode}, " if mode != DEFAULT_MODE else "")
            + f"{per_item}, position items {len(manifest['position_items'])}, "
            f"noise items {len(manifest['noise_items'])}"
        )
        blocked = False
        for jid, where, found in judge_access(sc):
            print(f"  judge {jid:8s} {where}")
            # --no-calls reads stored verdicts only: a key it never uses is not missing.
            for p in [] if args.no_calls else found:
                print(f"    MISSING: {p}")
            blocked = blocked or bool(found)

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

        call = None if args.no_calls else real_call
        if call and blocked:
            die(
                "a judge cannot be called (MISSING above): nothing was sent. `evh env-check` shows what each role reads.",
                "not-configured",
            )
        freeze(manifest)
        if call and cap is None:
            die("no cost cap: set cost_cap_usd in the scorer or EVAL_MAX_COST_USD", "not-configured")
        stats = run_judging(
            manifest, sc, base, articles, outputs, vdir, call, cap, retry_unparsed=args.retry_unparsed
        )
        scores = load_scores(manifest, sc, vdir)
        proj = project(sc, scores, item_ids)
        if not proj:
            print("no item has a complete verdict from every judge; nothing to project")
            return EXIT_STOPPED if stats["aborted"] else EXIT_NOTHING
        if sc.get("supersedes"):
            print(f"  {sc['scorer_id']} supersedes {sc['supersedes']}: {sc.get('why')}")
        words = {c: {i: len(str(t).split()) for i, t in o.items()} for c, o in outputs.items()}
        summ = summarise(manifest, sc, arms, scores, proj, stats, label, validated, vdir, lengths=words)
        written = write_scored_runs(manifest, sc, arms, proj, label, validated)
        summary = SUMMARIES / f"{_model_runs.key(sc['scorer_id'], sid)}.json"
        _store.mkdir(SUMMARIES, parents=True, exist_ok=True)
        write_json(summary, summ)
        for j, lb in (summ.get("length_bias") or {}).items():
            if lb:
                print(
                    f"  judge {j}: its score against the output's length in words, Spearman {lb['spearman_length']:+.2f} over {lb['n']}"
                )
        print(
            f"\n{len(written)} score(s) under their runs, read as judged/{sc['scorer_id']}  "
            f"({len(proj)}/{len(item_ids)} items, {label}); summary {summary.relative_to(DATA)}"
        )
        if mode != DEFAULT_MODE:
            print_win_summary(summ)
        print(
            f"  calls {stats['calls']}, spent this run ${stats['billed_this_run']:.4f}, "
            f"stored total ${stats['spent_usd']:.4f}  (the provider's bill where it reports one, else the price table)"
        )
        print(
            "  "
            + how(
                f"evh leaderboard --dataset-id {args.dataset_id} --label judged/{sc['scorer_id']}",
                f"make leaderboard DATASET_ID={args.dataset_id} ARGS='--label judged/{sc['scorer_id']}'",
            )
        )
        if stats["aborted"]:
            return EXIT_STOPPED
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
